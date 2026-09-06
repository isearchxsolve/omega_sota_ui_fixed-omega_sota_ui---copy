"""Base domain persona."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List

from omega_agent.core.types import ActionDecision, ExecutionContext, TaskNode


@dataclass
class DomainRouting:
    primary_model: str
    backup_model: str
    tools: List[str]
    decision_depth: str
    reflection_level: str
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: str = ""
    output_format: str = "action_decision"


class BaseDomain(ABC):
    """Base class for domain-specific execution personalities."""

    name: str = "general"
    keywords: List[str] = []

    EXECUTION_STYLE: Dict[str, str] = {
        "decision_urgency": "medium",
        "risk_tolerance": "moderate",
        "research_depth": "medium",
    }

    @abstractmethod
    def get_system_prompt(self) -> str:
        pass

    @abstractmethod
    def get_routing(self, goal: str, ctx: ExecutionContext) -> DomainRouting:
        pass

    @abstractmethod
    def build_plan(self, goal: str, ctx: ExecutionContext) -> List[TaskNode]:
        pass

    @abstractmethod
    def synthesize_decision(
        self,
        goal: str,
        task_results: Dict[str, Any],
        llm_output: str,
        ctx: ExecutionContext,
    ) -> ActionDecision:
        pass

    def get_tools(self) -> List[str]:
        return []

    def enhance_prompt(self, goal: str) -> str:
        return goal
