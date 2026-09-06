# Backward compatibility shim — use omega_agent package
from omega_agent import OmegaAgent, Config, AgentResult, ActionDecision, ExecutionContext
from omega_agent.core.types import TaskNode, ExecutionStatus

__all__ = [
    "OmegaAgent",
    "Config",
    "AgentResult",
    "ActionDecision",
    "ExecutionContext",
    "TaskNode",
    "ExecutionStatus",
]
