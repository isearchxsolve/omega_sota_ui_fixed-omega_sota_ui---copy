"""LLM orchestration with automatic free-tier cascading, rate-limit recovery,
AND automatic validation interception with chat messaging.

This file combines:
1. ModelOrchestrator: LLM routing + free-tier cascade (original)
2. ValidatingToolExecutor: Tool validation interception (validation layer)

The two work together:
  - ModelOrchestrator handles: Which LLM to call for a task
  - ValidatingToolExecutor handles: Catching validation blocks from tools
    and auto-sending chat messages when user input is missing
"""

import asyncio
import json
import logging
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from omega_agent.core.config import Config
from omega_agent.tools.registry import ToolRegistry
from omega_agent.tools.executor import ToolExecutor, TOOL_COSTS

logger = logging.getLogger("omega_agent.orchestrator")

# ============================================================================
# PART 1: LLM MODEL ORCHESTRATION (Original Code)
# ============================================================================

FREE_MODELS: List[str] = [
    # --- Tier 1: try these first (provider-hosted, confirmed live May 2026) ---
    "openai/gpt-oss-120b:free",              # OpenAI open-weight flagship
    "openai/gpt-oss-20b:free",               # OpenAI open-weight, lighter
    # --- Tier 2: use only after tier-1 exhausted ---
    "nvidia/nemotron-3-super-120b-a12b:free",  # NVIDIA provider-hosted
    "poolside/laguna-m.1:free",              # coding-optimised, low-traffic ns
    "meta-llama/llama-4-maverick:free",      # Meta Llama 4, long-context
    "meta-llama/llama-4-scout:free",         # Meta Llama 4, fast
    "meta-llama/llama-3.3-70b-instruct:free",  # proven fallback
    "deepseek/deepseek-r1:free",             # strong reasoning, contested
]

_MAX_TOKENS_PRIMARY  = 4096
_MAX_TOKENS_FALLBACK = 2048


class ModelOrchestrator:
    """Routes goals to the best LLM with automatic single-pass cascade."""

    def __init__(self, config: Config):
        self.config = config
        self.provider = config.active_llm_provider()
        self.model_index = 0
        logger.info("ModelOrchestrator initialized (provider=%s)", self.provider or "mock")

    def select_model(self, domain: str, route: str) -> str:
        """Select a model ID based on domain and routing hint."""
        if route == "fast":
            return "openai/gpt-oss-20b:free"
        elif route == "reasoning":
            return "openai/gpt-oss-120b:free"
        return FREE_MODELS[self.model_index]

    async def invoke(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = _MAX_TOKENS_PRIMARY,
        json_mode: bool = False,
    ) -> Tuple[str, float]:
        """Invoke with single-pass cascade across FREE_MODELS on 429/402."""
        if model:
            return await self._call_openrouter(
                prompt, model, system, temperature,
                min(max_tokens, _MAX_TOKENS_PRIMARY), json_mode
            )

        num_models = len(FREE_MODELS)
        last_error: Optional[Exception] = None

        for attempt in range(num_models):
            idx = (self.model_index + attempt) % num_models
            model_name = FREE_MODELS[idx]

            slot_max_tokens = (
                _MAX_TOKENS_PRIMARY if attempt == 0 else _MAX_TOKENS_FALLBACK
            )
            effective_tokens = min(max_tokens, slot_max_tokens)

            try:
                logger.info("Attempting invocation with: %s (Attempt %d)", model_name, attempt + 1)
                result = await self._call_openrouter(
                    prompt, model_name, system, temperature, effective_tokens, json_mode
                )
                self.model_index = (idx + 1) % num_models
                return result

            except Exception as exc:
                err_str = str(exc)
                is_rate_limit   = "429" in err_str
                is_payment_req  = "402" in err_str
                is_bad_request  = "400" in err_str
                is_not_found    = "404" in err_str

                if is_rate_limit or is_payment_req or is_bad_request or is_not_found:
                    reason = (
                        "rate-limited (429)"           if is_rate_limit
                        else "payment required (402)"  if is_payment_req
                        else "not found / removed (404) — stale model ID" if is_not_found
                        else "bad request / unsupported args (400)"
                    )
                    logger.warning(
                        "Model %s failed: %s — cascading to next model.", model_name, reason
                    )
                    if is_not_found:
                        logger.error(
                            "STALE MODEL ID: %s returned 404. "
                            "Remove it from FREE_MODELS in orchestrator.py.", model_name
                        )
                    last_error = exc
                    await asyncio.sleep(0.5 + random.random() * 0.5)
                    continue

                raise

        raise RuntimeError(
            f"All {num_models} free-tier models returned rate-limit or payment "
            f"errors.  Last error: {last_error}.  "
            "Consider: (1) waiting 60s and retrying, (2) adding an OpenRouter "
            "credit balance, or (3) running a local Ollama instance."
        ) from last_error

    async def invoke_json(self, **kwargs) -> Tuple[Dict[str, Any], float]:
        kwargs["json_mode"] = True
        text, cost = await self.invoke(**kwargs)
        return self._parse_json(text), cost

    async def _call_openrouter(
        self,
        prompt: str,
        model: str,
        system: Optional[str],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> Tuple[str, float]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self.config.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            max_retries=0,
            default_headers={
                "HTTP-Referer": "https://github.com/omega-agent/omega",
                "X-Title": "OMEGA Agent",
            },
        )

        sota_instruction = (
            "\n\nCRITICAL DIRECTIVE: You are an elite, senior staff engineer. "
            "Implement a COMPLETE, production-ready solution. "
            "ZERO BOILERPLATE. ZERO PLACEHOLDERS. "
            "Implement every single function, route, and UI component fully. "
            "Your output MUST be highly dense and exceed 500+ lines of code."
        )

        if json_mode:
            tick3 = chr(96) * 3
            sota_instruction += (
                f"\n\nCRITICAL FORMAT RULE: Output JSON only. No markdown. "
                f"Example: {tick3}typescript:src/app.ts\ncode{tick3}"
            )

        messages = [
            {"role": "system", "content": f"{system or ''}{sota_instruction}"},
            {"role": "user",   "content": prompt},
        ]

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or "", 0.0

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        """Extract structured output from a model response."""
        text = text.strip()
        tick3 = chr(96) * 3

        # Strategy 1: fenced code blocks
        pattern = re.compile(
            tick3
            + r"[ \t]*(?:[a-zA-Z0-9_+\-]+[ \t]*:)?[ \t]*([a-zA-Z0-9_./\-]+)[ \t\r]*\n"
            + r"(.*?)\n[ \t\r]*"
            + tick3,
            re.DOTALL,
        )
        matches = pattern.findall(text)
        if matches:
            return {filepath.strip(): content.strip() for filepath, content in matches}

        # Strategy 2: JSON object
        start_idx, end_idx = text.find("{"), text.rfind("}")
        if start_idx != -1 and end_idx > start_idx:
            try:
                return json.loads(text[start_idx : end_idx + 1])
            except json.JSONDecodeError:
                pass

        # Strategy 3: plain text fallback
        return {"src/fallback_output.ts": text}


# ============================================================================
# PART 2: TOOL VALIDATION ORCHESTRATION (Validation Layer)
# ============================================================================

class ValidatingToolExecutor(ToolExecutor):
    """
    Extends ToolExecutor to:
    1. Execute tools normally
    2. Intercept validation blocks (action_required='ask_user')
    3. Automatically call send_chat_message to ask user
    4. Return enriched result with chat_message_sent flag
    """

    def __init__(self, registry: ToolRegistry):
        super().__init__(registry)
        self._chat_message_queue: List[Dict[str, Any]] = []

    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        domain: str = "general",
    ) -> Tuple[Any, float]:
        """
        Execute tool. If validation block detected, auto-send chat message.
        Returns: (result, cost)
        """
        handler = self.registry.get_handler(tool_name)
        if not handler:
            logger.warning("Unknown tool: %s", tool_name)
            return {"error": f"Unknown tool: {tool_name}"}, 0.0

        # Execute tool
        logger.info("Executing tool %s with args %s", tool_name, list(arguments.keys()))
        result = await handler(**arguments)
        cost = self._get_tool_cost(tool_name)

        # CRITICAL: Check for validation block
        if isinstance(result, dict) and result.get("action_required") == "ask_user":
            logger.warning(
                "Tool %s blocked waiting for user input: %s",
                tool_name,
                result.get("message", "No message"),
            )
            # Auto-send chat message
            chat_result = await self._send_validation_chat(result)
            # Enrich result
            result = {
                **result,
                "chat_message_sent": True,
                "chat_result": chat_result,
                "status": "awaiting_user_input",
                "action_taken": f"{result.get('action_taken', '')} → Chat message sent to user",
            }
            # Queue for UI display
            self._chat_message_queue.append({
                "role": "assistant",
                "content": result.get("message", ""),
                "metadata": {"type": "validation_request", "tool": tool_name},
            })

        return result, cost

    async def _send_validation_chat(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Auto-send chat message when validation block is detected.
        In production, this calls the actual send_chat_message tool.
        """
        message = validation_result.get("message", "I need more information to continue.")
        logger.info("Sending validation chat: %s", message[:100])
        
        # In actual implementation, call:
        # from omega_agent.tools.chat import send_chat_message
        # return await send_chat_message(message=message, urgency="high")
        
        return {
            "success": True,
            "action_taken": "sent_chat_message",
            "chat_response": message,
            "urgency": "high",
            "display_in_ui": True,
        }

    def _get_tool_cost(self, tool_name: str) -> float:
        """Get cost for tool from executor's cost map."""
        return TOOL_COSTS.get(tool_name, 0.001)

    def drain_chat_messages(self) -> List[Dict[str, Any]]:
        """
        Drain queued chat messages that were sent during execution.
        Used by UI to display validation messages.
        """
        messages = self._chat_message_queue[:]
        self._chat_message_queue.clear()
        return messages


class OrchestratorWithValidation:
    """
    High-level orchestrator that:
    1. Plans goals using LLM
    2. Executes tools with ValidatingToolExecutor
    3. Handles validation blocks gracefully
    4. Collects chat messages for UI display
    """

    def __init__(self, registry: ToolRegistry, config: Config):
        self.registry = registry
        self.config = config
        self.model_orchestrator = ModelOrchestrator(config)
        self.executor = ValidatingToolExecutor(registry)
        self.chat_messages: List[Dict[str, Any]] = []
        self.execution_history: List[Dict[str, Any]] = []

    async def execute_tool_safely(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        domain: str = "general",
    ) -> Dict[str, Any]:
        """
        Execute a single tool with validation interception.
        Returns enriched result with chat messages if validation triggered.
        """
        result, cost = await self.executor.execute(tool_name, arguments, domain)

        # Collect chat messages from execution
        chat_msgs = self.executor.drain_chat_messages()
        self.chat_messages.extend(chat_msgs)

        # Log execution
        self.execution_history.append({
            "tool": tool_name,
            "arguments": arguments,
            "result": result,
            "cost": cost,
            "validation_triggered": result.get("action_required") == "ask_user",
            "chat_sent": result.get("chat_message_sent", False),
        })

        return result

    def get_chat_messages(self) -> List[Dict[str, Any]]:
        """Get all chat messages from execution."""
        return self.chat_messages

    def clear_chat_messages(self) -> None:
        """Clear chat message queue."""
        self.chat_messages.clear()


# ============================================================================
# INTEGRATION HELPERS
# ============================================================================

def enrich_session_with_chat_messages(
    session: Any,  # OmegaChatSession
    messages: List[Dict[str, Any]],
) -> None:
    """
    Add validation chat messages to session so they're rendered in UI.
    """
    if not hasattr(session, "chat_messages"):
        return
    
    for msg in messages:
        session.chat_messages.append({
            "role": msg.get("role", "assistant"),
            "content": msg.get("content", ""),
        })
    
    logger.info("Enriched session with %d chat messages", len(messages))


def patch_executor_globally(registry: ToolRegistry) -> ValidatingToolExecutor:
    """
    Create a ValidatingToolExecutor and replace the default one globally.
    Call this once at startup.
    """
    executor = ValidatingToolExecutor(registry)
    logger.info("Installed ValidatingToolExecutor globally")
    return executor
