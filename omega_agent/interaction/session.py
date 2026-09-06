"""Stateful chat session for interactive OMEGA runs."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from omega_agent.core.types import AgentResult
from omega_agent.interaction.types import InteractiveStatus, UserInputRequest


@dataclass
class OmegaChatSession:
    """Conversation + automation state across multiple UI turns."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: InteractiveStatus = InteractiveStatus.IDLE
    goal: str = ""
    clarified_goal: str = ""
    pending_request: Optional[UserInputRequest] = None
    pending_queue: List[UserInputRequest] = field(default_factory=list)
    agent_result: Optional[AgentResult] = None
    chat_messages: List[Dict[str, str]] = field(default_factory=list)
    user_inputs: Dict[str, str] = field(default_factory=dict)
    run_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def append_message(self, role: str, content: str) -> None:
        self.chat_messages.append({"role": role, "content": content})

    def to_state_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "goal": self.goal,
            "clarified_goal": self.clarified_goal,
            "pending_request": self.pending_request.to_dict() if self.pending_request else None,
            "pending_queue": [r.to_dict() for r in self.pending_queue],
            "agent_result": self.agent_result.to_dict() if self.agent_result else None,
            "chat_messages": self.chat_messages,
            "user_inputs": dict(self.user_inputs),
            "run_count": self.run_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_state_dict(cls, data: Optional[Dict[str, Any]]) -> "OmegaChatSession":
        if not data:
            return cls()
        session = cls(session_id=data.get("session_id", str(uuid.uuid4())[:8]))
        session.status = InteractiveStatus(data.get("status", InteractiveStatus.IDLE.value))
        session.goal = data.get("goal", "")
        session.clarified_goal = data.get("clarified_goal", "")
        session.chat_messages = list(data.get("chat_messages") or [])
        session.user_inputs = dict(data.get("user_inputs") or {})
        session.run_count = int(data.get("run_count", 0))
        session.metadata = dict(data.get("metadata") or {})
        if data.get("pending_request"):
            session.pending_request = UserInputRequest.from_dict(data["pending_request"])
        session.pending_queue = [
            UserInputRequest.from_dict(r) for r in (data.get("pending_queue") or [])
        ]
        if data.get("agent_result"):
            ar = data["agent_result"]
            from omega_agent.core.types import ActionDecision

            decision = None
            if ar.get("decision"):
                d = ar["decision"]
                decision = ActionDecision(
                    action=d.get("action", ""),
                    confidence=float(d.get("confidence", 0)),
                    rationale=d.get("rationale", ""),
                    risk_params=d.get("risk_params", {}),
                    next_steps=d.get("next_steps", []),
                    immediate_actions=list(d.get("immediate_actions") or []),
                    domain=d.get("domain", ""),
                )
            session.agent_result = AgentResult(
                success=bool(ar.get("success")),
                output=ar.get("output", ""),
                domain=ar.get("domain", "unknown"),
                route=ar.get("route", ""),
                cost=float(ar.get("cost", 0)),
                latency=float(ar.get("latency", 0)),
                metadata=ar.get("metadata", {}),
                decision=decision,
            )
        return session
