"""Tool registration and discovery — LLM selects tools dynamically."""

import logging
from typing import Any, Callable, Dict, List, Optional

from omega_agent.tools import chat

logger = logging.getLogger("omega_agent.tools.registry")

TOOL_ARG_SCHEMAS: Dict[str, Dict[str, str]] = {
    "web_search": {"query": "string — search query", "max_results": "int — max results (default 5)"},
    "crypto_price_api": {"symbol": "string — coin id e.g. solana, bitcoin", "timeframe": "string — e.g. 1h"},
    "arxiv_search": {"query": "string — academic search query", "max_results": "int"},
    "semantic_scholar": {"query": "string", "max_results": "int"},
    "sentiment_analysis": {"text": "string — text to analyze", "domain": "string — context label"},
    "text_synthesizer": {"inputs": "list — prior task outputs", "goal": "string"},
    "code_generator": {"prompt": "string — coding task", "language": "string — e.g. python"},
    "code_validator": {"code": "string — Python source code"},
    "code_executor": {"code": "string — Python source to run", "timeout": "int — seconds"},
    "task_decomposer": {"goal": "string", "context": "any — prior context"},
    "emergency_food_lookup": {"location": "string — REQUIRED. DO NOT GUESS. If the user did not provide a city or ZIP, you MUST use send_chat_message to ask them first."},
    "emergency_cash_lookup": {"location": "string — REQUIRED. DO NOT GUESS. If missing, use send_chat_message first."},
    "emergency_assistance_programs": {
        "location": "string — REQUIRED. DO NOT GUESS.",
        "need_type": "string — food|housing|medical|cash",
    },
    "emergency_gig_income": {
        "location": "string — REQUIRED. DO NOT GUESS.",
        "skills": "string — optional",
    },
    # Browser automation tools
    "browser_navigate": {
        "url": "string — full URL",
        "wait_for": "string — domcontentloaded|networkidle",
        "timeout": "int — seconds",
        "screenshot_dir": "string — optional",
    },
    "browser_fill_form": {
        "url": "string — form page URL",
        "fields": "list — [{selector, value} or {label, value}]",
        "submit_selector": "string — CSS selector (optional)",
        "screenshot_dir": "string — optional",
        "timeout": "int — seconds",
    },
    "browser_click": {
        "url": "string",
        "selector": "string — CSS selector",
        "wait_after": "float — seconds",
        "screenshot_dir": "string — optional",
    },
    "browser_ocr_page": {
        "url": "string",
        "screenshot_dir": "string — optional",
        "timeout": "int — seconds",
    },
    "browser_emergency_locate_food": {
        "zip_code": "string — 5-digit US ZIP",
        "screenshot_dir": "string — optional",
    },
    "browser_emergency_benefits_screener": {
        "location": "string — city, state, or ZIP",
        "need_types": "list — e.g. ['food', 'cash']",
        "screenshot_dir": "string — optional",
    },
    "send_chat_message": {
        "message": "string — The complete message. MUST explicitly ask the user for missing details (e.g., location, pincode, bank account info) if needed to complete a goal.",
        "urgency": "string — 'low', 'normal', or 'high' depending on message context.",
    },
    "write_files": {
        "files": "list — [{path, content}]",
        "workspace_id": "string",
        "output_base": "string — optional",
    },
    "modify_file": {
        "path": "string",
        "workspace_id": "string",
        "content": "string — optional",
        "old_string": "string — optional",
        "new_string": "string — optional",
    },
    "run_shell": {"command": "string", "workspace_id": "string", "timeout": "int"},
    "archive_zip": {"workspace_id": "string", "archive_name": "string — optional"},
    "llm_generate_files": {
        "goal": "string — full goal description",
        "workspace_id": "string — workspace folder name",
        "output_base": "string — optional workspace root",
        "web_context": "object — {snippets:[...]} from prior web_search; richer evidence = better code",
        "project_subdir": "string — subdirectory within workspace (default: project)",
    },
}

class ToolRegistry:
    """Registry of available tools — all tools visible to LLM planner."""

    def __init__(self):
        self.tools: Dict[str, Dict[str, Any]] = {}
        self.handlers: Dict[str, Callable] = {}
        
        # Self-register the newly created send_chat_message tool automatically
        self.register(
            "send_chat_message",
            "ACT: Send a direct, conversational text message to the user in the Web UI.",
            chat.send_chat_message,
        )

    def register(
        self,
        name: str,
        description: str,
        handler: Callable,
        args: Optional[Dict[str, str]] = None,
        usage_hint: str = "",
    ) -> None:
        # FORCE the central registry schemas to override individual tool schemas
        strict_args = TOOL_ARG_SCHEMAS.get(name) if name in TOOL_ARG_SCHEMAS else (args or {})

        self.tools[name] = {
            "name": name,
            "description": description,
            "args": strict_args,
            "usage_hint": usage_hint,
        }
        self.handlers[name] = handler
        logger.debug("Registered tool: %s", name)

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self.tools.get(name)

    def get_handler(self, name: str) -> Optional[Callable]:
        return self.handlers.get(name)

    def get_catalog_for_llm(self) -> List[Dict[str, Any]]:
        """Full tool catalog for dynamic LLM planning."""
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "args": t.get("args", {}),
                "usage_hint": t.get("usage_hint", ""),
            }
            for t in self.tools.values()
        ]

    def get_tools_for_domain(self, domain: str) -> List[Dict[str, Any]]:
        """Legacy — returns full catalog; domain filtering is LLM-driven now."""
        return self.get_catalog_for_llm()

    def list_tools(self) -> List[str]:
        return list(self.tools.keys())