"""Interactive runner — pause/resume OMEGA when user input is required."""

import json
import logging
from typing import Any, Optional

# CRITICAL FIX: Removed the top-level OmegaAgent import to break the circular dependency.

from omega_agent.core.config import Config
from omega_agent.core.progress import RunProgress
from omega_agent.interaction.analyzer import WorkflowInputAnalyzer
from omega_agent.interaction.credentials import CredentialManager
from omega_agent.interaction.session import OmegaChatSession
from omega_agent.interaction.types import (
    InputKind,
    InteractiveRunResult,
    InteractiveStatus,
    UserInputRequest,
)

logger = logging.getLogger("omega_agent.interaction.runner")

class InteractiveOmegaRunner:
    """
    Drives OMEGA with human-in-the-loop.
    """

    def __init__(
        self,
        agent: Optional[Any] = None,  # Changed to Any to avoid type-hinting crashes
        config: Optional[Config] = None,
        credentials: Optional[CredentialManager] = None,
    ):
        self.config = config or Config()
        
        if agent is not None:
            self.agent = agent
        else:
            # CRITICAL FIX: Lazy import allows the app to boot before loading the agent
            from omega_agent.agents.omega import OmegaAgent
            self.agent = OmegaAgent(config=self.config)
            
        self.credentials = credentials or CredentialManager()
        self.analyzer = WorkflowInputAnalyzer(self.config, self.credentials)

    async def handle_message(
        self,
        message: str,
        session: Optional[OmegaChatSession] = None,
        max_time: Optional[int] = None,
        progress: Optional[RunProgress] = None,
    ) -> InteractiveRunResult:
        session = session or OmegaChatSession()
        text = (message or "").strip()
        if not text:
            return self._result(session, InteractiveStatus.IDLE, "Enter a goal or reply to OMEGA's question.")

        session.append_message("user", text)

        if session.status == InteractiveStatus.AWAITING_INPUT and session.pending_request:
            applied = self._apply_user_response(session, text)
            if applied is False:
                return InteractiveRunResult(
                    status=InteractiveStatus.AWAITING_INPUT,
                    session_id=session.session_id,
                    message=session.pending_request.format_for_user(),
                    request=session.pending_request,
                    chat_messages=session.chat_messages,
                )
            session.pending_request = None
            return await self._continue_after_input(session, max_time, progress=progress)

        if session.status in (InteractiveStatus.COMPLETED, InteractiveStatus.FAILED):
            session = OmegaChatSession(session_id=session.session_id)
            session.metadata["previous_session_reset"] = True

        if not session.goal:
            session.goal = text
        elif session.status == InteractiveStatus.IDLE:
            session.goal = text

        session.clarified_goal = session.clarified_goal or session.goal
        return await self._start_workflow(session, max_time, progress=progress)

    async def _start_workflow(
        self,
        session: OmegaChatSession,
        max_time: Optional[int],
        progress: Optional[RunProgress] = None,
    ) -> InteractiveRunResult:
        session.status = InteractiveStatus.RUNNING
        session.run_count += 1

        preflight = self.analyzer.preflight_requests(
            session.goal,
            clarified_goal=session.clarified_goal or None,
            user_inputs=session.user_inputs,
        )
        preflight = [r for r in preflight if r.key not in session.user_inputs]

        if preflight:
            return self._pause_for_requests(session, preflight)

        return await self._execute_omega(session, max_time, progress=progress)

    async def _continue_after_input(
        self,
        session: OmegaChatSession,
        max_time: Optional[int],
        progress: Optional[RunProgress] = None,
    ) -> InteractiveRunResult:
        if session.pending_queue:
            return self._pause_for_requests(session, session.pending_queue)

        if session.pending_request:
            return self._pause_for_requests(session, [session.pending_request])

        return await self._start_workflow(session, max_time, progress=progress)

    async def _execute_omega(
        self,
        session: OmegaChatSession,
        max_time: Optional[int],
        progress: Optional[RunProgress] = None,
    ) -> InteractiveRunResult:
        session.status = InteractiveStatus.RUNNING
        self.credentials.apply_to_environment()
        self._refresh_agent_config()

        ack = (
            f"**Processing your workflow** (run #{session.run_count})\n\n"
            f"Goal: {session.clarified_goal or session.goal}"
        )
        session.append_message("assistant", ack)

        async def ui_event_callback(event_payload: dict):
            if progress:
                # Handles both CLI _queue and Web UI _tqueue gracefully
                queue = getattr(progress, '_tqueue', getattr(progress, '_queue', None))
                if queue:
                    try:
                        sse_event = {"type": "event", "data": json.dumps(event_payload)}
                        queue.put_nowait(sse_event)
                    except Exception as e:
                        logger.warning(f"Failed to queue UI event: {e}")

        try:
            result = await self.agent.run(
                goal=session.clarified_goal or session.goal,
                max_time=max_time or self.config.max_total_time,
                user_inputs=dict(session.user_inputs),
                tenant_id=session.metadata.get("tenant_id") or self.config.default_tenant_id,
                user_id=session.metadata.get("user_id"),
                progress=progress,
                ui_event_callback=ui_event_callback,
            )
        except Exception as e:
            logger.error("Interactive run failed: %s", e, exc_info=True)
            session.status = InteractiveStatus.FAILED
            msg = f"**OMEGA encountered an error:** {e}"
            session.append_message("assistant", msg)
            return self._result(session, InteractiveStatus.FAILED, msg)

        session.agent_result = result
        post_requests = self.analyzer.postrun_requests(session.goal, result)
        post_requests = [r for r in post_requests if r.key not in session.user_inputs]

        if post_requests and not result.success:
            return self._pause_for_requests(session, post_requests)

        if result.success:
            action_val = str(getattr(result.decision, "action", "")).strip().upper()
            if result.decision and "AWAIT_INPUT" in action_val:
                # UNIVERSAL FIX: Use dynamic_clarification instead of "location"
                req = UserInputRequest(
                    kind=InputKind.CLARIFICATION,
                    key="dynamic_clarification",
                    prompt="missing details",
                    description="Awaiting missing details"
                )
                session.pending_queue = []
                session.pending_request = req
                session.status = InteractiveStatus.AWAITING_INPUT
                
                # Append the beautiful markdown to the chat
                session.append_message("assistant", result.output)
                
                return InteractiveRunResult(
                    status=InteractiveStatus.AWAITING_INPUT,
                    session_id=session.session_id,
                    message=result.output,
                    request=req,
                    chat_messages=session.chat_messages,
                    metadata={"awaiting_key": "dynamic_clarification", "queue_remaining": 0},
                )

            session.status = InteractiveStatus.COMPLETED
            summary = self._format_completion(result)
            session.append_message("assistant", summary)
            return InteractiveRunResult(
                status=InteractiveStatus.COMPLETED,
                session_id=session.session_id,
                message=summary,
                agent_result=result,
                chat_messages=session.chat_messages,
                metadata={"run_count": session.run_count},
            )

        session.status = InteractiveStatus.FAILED
        fail_msg = f"**Workflow finished with issues.**\n\n{result.output}"
        session.append_message("assistant", fail_msg)
        return InteractiveRunResult(
            status=InteractiveStatus.FAILED,
            session_id=session.session_id,
            message=fail_msg,
            agent_result=result,
            chat_messages=session.chat_messages,
        )

    def _pause_for_requests(self, session: OmegaChatSession, requests: list[UserInputRequest]) -> InteractiveRunResult:
        session.pending_queue = requests[1:]
        session.pending_request = requests[0]
        session.status = InteractiveStatus.AWAITING_INPUT

        prompt = session.pending_request.format_for_user()
        session.append_message("assistant", prompt)

        return InteractiveRunResult(
            status=InteractiveStatus.AWAITING_INPUT,
            session_id=session.session_id,
            message=prompt,
            request=session.pending_request,
            chat_messages=session.chat_messages,
            metadata={
                "awaiting_key": session.pending_request.key,
                "queue_remaining": len(session.pending_queue),
            },
        )

    def _apply_user_response(self, session: OmegaChatSession, text: str) -> bool:
        req = session.pending_request
        if not req:
            return True

        key = req.key
        session.user_inputs[key] = text

        if req.kind == InputKind.CREDENTIAL:
            err = self.credentials.validate(key, text)
            if err:
                session.pending_request = UserInputRequest(
                    kind=req.kind, key=req.key, prompt=f"{err}\n\nPlease try again.",
                    description=req.description, sensitive=True, help_url=req.help_url,
                )
                session.status = InteractiveStatus.AWAITING_INPUT
                session.append_message("assistant", session.pending_request.format_for_user())
                return False
            self.credentials.store(key, text)
            self._refresh_agent_config()
            session.append_message("assistant", f"**Received {key}** — stored for this session. Resuming workflow…")
            
        elif req.kind == InputKind.CLARIFICATION:
            # UNIVERSAL FIX: Anything you type will dynamically append to the goal here and resume!
            session.clarified_goal = f"{session.goal}\n\nAdditional details: {text}"
            session.append_message("assistant", "**Thanks** — using your clarification. Resuming…")
            
        elif req.kind == InputKind.CONFIRMATION:
            if text.lower() in ("no", "n", "cancel", "stop"):
                session.status = InteractiveStatus.IDLE
                session.append_message("assistant", "Cancelled. Send a new goal when ready.")
                return True
            session.append_message("assistant", "Confirmed. Resuming…")
        else:
            session.user_inputs[key] = text
            session.append_message("assistant", "Input recorded. Resuming…")
        return True

    def _refresh_agent_config(self) -> None:
        cfg = self.agent.config
        cfg.groq_api_key = self.credentials.get("GROQ_API_KEY") or cfg.groq_api_key
        cfg.anthropic_api_key = self.credentials.get("ANTHROPIC_API_KEY") or cfg.anthropic_api_key
        cfg.openai_api_key = self.credentials.get("OPENAI_API_KEY") or cfg.openai_api_key

    @staticmethod
    def _format_completion(result) -> str:
        lines = [
            "**OMEGA completed your workflow**",
            "",
            f"- Domain: `{result.domain}`",
            f"- Latency: {result.latency:.1f}s",
            f"- Cost: ${result.cost:.4f}",
        ]
        if result.decision:
            lines.append(f"- Action: **{result.decision.action}** ({result.decision.confidence:.0%} confidence)")
        lines.extend(["", "---", "", result.output])
        return "\n".join(lines)

    @staticmethod
    def _result(session: OmegaChatSession, status: InteractiveStatus, message: str) -> InteractiveRunResult:
        session.status = status
        if message:
            session.append_message("assistant", message)
        return InteractiveRunResult(status=status, session_id=session.session_id, message=message, chat_messages=session.chat_messages)