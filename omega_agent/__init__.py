"""OMEGA Agent — Multi-domain action-taking orchestrator."""

from omega_agent.agents.omega import OmegaAgent
from omega_agent.core.config import Config
from omega_agent.core.types import AgentResult, ActionDecision, ExecutionContext
from omega_agent.reasoning.types import DynamicDomainProfile
from omega_agent.interaction.runner import InteractiveOmegaRunner
from omega_agent.interaction.types import InteractiveRunResult, UserInputRequest

__version__ = "1.2.0"
__all__ = [
    "OmegaAgent",
    "Config",
    "AgentResult",
    "ActionDecision",
    "ExecutionContext",
    "DynamicDomainProfile",
    "InteractiveOmegaRunner",
    "InteractiveRunResult",
    "UserInputRequest",
]
