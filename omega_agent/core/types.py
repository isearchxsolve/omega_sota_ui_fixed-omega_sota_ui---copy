"""Core type definitions for OMEGA execution."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from omega_agent.reasoning.types import DynamicDomainProfile


class ExecutionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class TaskNode:
    """A single task in the execution DAG."""
    id: str
    name: str
    description: str
    tool_name: str
    arguments: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    timeout: int = 30
    max_retries: int = 3
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class ActionDecision:
    """Structured action output — every domain ends here."""
    action: str
    confidence: float
    rationale: str
    risk_params: Dict[str, Any] = field(default_factory=dict)
    next_steps: List[str] = field(default_factory=list)
    immediate_actions: List[Dict[str, Any]] = field(default_factory=list)
    domain: str = "general"

    def to_output(self) -> str:
        if self.rationale.strip().startswith("## DELIVERABLE") or self.rationale.strip().startswith("## BUILT FOR YOU"):
            header = f"**Domain:** {self.domain}\n\n" if self.domain else ""
            return header + self.rationale.strip()

        if self.rationale.strip().startswith("## DO THIS NOW"):
            header = f"**Domain:** {self.domain}\n\n" if self.domain else ""
            return header + self.rationale.strip()

        if self.rationale.strip().startswith("## ACTION"):
            header = f"**Domain:** {self.domain}\n\n" if self.domain else ""
            return header + self.rationale.strip()

        lines = [
            f"## ACTION: {self.action.upper()}",
            f"**Confidence:** {self.confidence:.0%}",
            f"**Domain:** {self.domain}",
            "",
        ]
        if self.immediate_actions:
            from omega_agent.reasoning.crisis import format_immediate_actions
            lines.append(format_immediate_actions(self.immediate_actions))
            lines.append("")
        lines.extend(["### Rationale", self.rationale])
        if self.risk_params:
            lines.extend(["", "### Risk Parameters"])
            for key, value in self.risk_params.items():
                lines.append(f"- **{key}:** {value}")
        if self.next_steps:
            lines.extend(["", "### Next Steps"])
            for i, step in enumerate(self.next_steps, 1):
                lines.append(f"{i}. {step}")
        return "\n".join(lines)


@dataclass
class AgentResult:
    """Final result from OMEGA execution."""
    success: bool
    output: str
    domain: str
    route: str
    cost: float
    latency: float
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    decision: Optional[ActionDecision] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "domain": self.domain,
            "route": self.route,
            "cost": self.cost,
            "latency": self.latency,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "decision": {
                "action": self.decision.action,
                "confidence": self.decision.confidence,
                "rationale": self.decision.rationale,
                "risk_params": self.decision.risk_params,
                "next_steps": self.decision.next_steps,
                "immediate_actions": self.decision.immediate_actions,
                "domain": self.decision.domain,
            }
            if self.decision
            else None,
        }


@dataclass
class ExecutionContext:
    """Execution context with UI callback support."""
    goal: str
    domain: Optional[str] = None
    max_time: int = 300
    start_time: datetime = field(default_factory=datetime.now)
    cost_so_far: float = 0.0
    errors: List[str] = field(default_factory=list)
    learning_progress: Dict[str, Any] = field(default_factory=dict)
    task_results: Dict[str, Any] = field(default_factory=dict)
    route: str = "default"
    retry_count: int = 0
    sota_attempt: int = 0
    web_context: Dict[str, Any] = field(default_factory=dict)
    dynamic_profile: Optional[Any] = None  # DynamicDomainProfile at runtime
    user_inputs: Dict[str, str] = field(default_factory=dict)
    clarification_rounds: int = 0
    workspace_id: str = ""
    workspace_root: str = "./outputs/workspaces"
    tenant_id: str = "default"
    user_id: Optional[str] = None
    
    # NEW FIELDS FOR UI INTERACTION
    ui_event_handler: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    run_progress: Optional[Any] = None  # RunProgress object with _queue
    
    def set_ui_callback(self, callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None, progress: Optional[Any] = None) -> None:
        """Set UI callback and progress reference for async messaging to frontend."""
        self.ui_event_handler = callback
        self.run_progress = progress

    def checkpoint(self, phase: str, message: str, fraction: float, detail: str = "") -> None:
        if self.run_progress is not None:
            self.run_progress.checkpoint(phase, message, fraction, detail)

    def get_elapsed_time(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()

    def get_remaining_time(self) -> float:
        return self.max_time - self.get_elapsed_time()

    def is_timed_out(self) -> bool:
        return self.get_remaining_time() <= 0

    def add_error(self, error: str) -> None:
        self.errors.append(f"[{datetime.now().isoformat()}] {error}")

    def get_learning_progress(self) -> Dict[str, Any]:
        return self.learning_progress or {}

    def add_cost(self, amount: float) -> None:
        self.cost_so_far += amount