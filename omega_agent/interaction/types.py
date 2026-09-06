"""Types for interactive OMEGA sessions."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from omega_agent.core.types import AgentResult


class InputKind(str, Enum):
    """What OMEGA is asking the user for."""

    CREDENTIAL = "credential"
    CLARIFICATION = "clarification"
    CONFIRMATION = "confirmation"
    DETAIL = "detail"


class InteractiveStatus(str, Enum):
    """Lifecycle of an interactive run."""

    IDLE = "idle"
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class UserInputRequest:
    """OMEGA pauses automation until the user supplies this input."""

    kind: InputKind
    key: str
    prompt: str
    description: str = ""
    required: bool = True
    sensitive: bool = False
    options: List[str] = field(default_factory=list)
    help_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "key": self.key,
            "prompt": self.prompt,
            "description": self.description,
            "required": self.required,
            "sensitive": self.sensitive,
            "options": self.options,
            "help_url": self.help_url,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserInputRequest":
        return cls(
            kind=InputKind(data.get("kind", InputKind.DETAIL.value)),
            key=data["key"],
            prompt=data["prompt"],
            description=data.get("description", ""),
            required=data.get("required", True),
            sensitive=data.get("sensitive", False),
            options=list(data.get("options") or []),
            help_url=data.get("help_url"),
            metadata=dict(data.get("metadata") or {}),
        )

    def format_for_user(self) -> str:
        """Human-readable message shown in chat / Gradio."""
        lines = [
            "**OMEGA needs your input**",
            "",
            self.prompt,
        ]
        if self.description:
            lines.extend(["", self.description])
        if self.help_url:
            lines.extend(["", f"Get a key: {self.help_url}"])
        if self.options:
            lines.extend(["", "Options:", *[f"- {opt}" for opt in self.options]])
        if self.sensitive:
            lines.append("")
            lines.append("_Your reply will be stored for this session only and applied as an environment variable._")
        return "\n".join(lines)


@dataclass
class InteractiveRunResult:
    """Result of one interactive step (may be partial)."""

    status: InteractiveStatus
    session_id: str
    message: str = ""
    request: Optional[UserInputRequest] = None
    agent_result: Optional[AgentResult] = None
    chat_messages: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def needs_input(self) -> bool:
        return self.status == InteractiveStatus.AWAITING_INPUT and self.request is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "session_id": self.session_id,
            "message": self.message,
            "request": self.request.to_dict() if self.request else None,
            "agent_result": self.agent_result.to_dict() if self.agent_result else None,
            "chat_messages": self.chat_messages,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "needs_input": self.needs_input,
        }
