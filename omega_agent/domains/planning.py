"""Planning domain persona — structured execution."""

from typing import Any, Dict, List

from omega_agent.core.types import ActionDecision, ExecutionContext, TaskNode
from omega_agent.domains.base import BaseDomain, DomainRouting


class PlanningDomain(BaseDomain):
    name = "planning"
    keywords = ["plan", "schedule", "organize", "roadmap", "strategy"]

    EXECUTION_STYLE = {
        "decision_urgency": "medium",
        "risk_tolerance": "moderate",
        "research_depth": "medium",
    }

    def get_system_prompt(self) -> str:
        return (
            "You are OMEGA Planner — a strategic execution architect.\n"
            "RULES:\n"
            "1. Break goals into concrete, actionable steps\n"
            "2. Include timelines and priorities\n"
            "3. Identify dependencies and blockers\n"
            "4. End with ACTION: execute, delegate, or schedule\n"
            "5. Each step must be specific and measurable"
        )

    def get_routing(self, goal: str, ctx: ExecutionContext) -> DomainRouting:
        return DomainRouting(
            primary_model="claude-sonnet-4-20250514",
            backup_model="gpt-4o",
            tools=["web_search", "task_decomposer"],
            decision_depth="strategic",
            reflection_level="medium",
            temperature=0.6,
            max_tokens=2048,
            system_prompt=self.get_system_prompt(),
        )

    def build_plan(self, goal: str, ctx: ExecutionContext) -> List[TaskNode]:
        return [
            TaskNode(
                id="research_context",
                name="Research Context",
                description="Gather context for planning",
                tool_name="web_search",
                arguments={"query": goal[:200]},
                timeout=20,
            ),
            TaskNode(
                id="decompose",
                name="Decompose Goal",
                description="Break goal into actionable steps",
                tool_name="task_decomposer",
                arguments={"goal": goal, "context": "$research_context"},
                dependencies=["research_context"],
                timeout=15,
            ),
        ]

    def synthesize_decision(
        self,
        goal: str,
        task_results: Dict[str, Any],
        llm_output: str,
        ctx: ExecutionContext,
    ) -> ActionDecision:
        steps = task_results.get("decompose", {}).get("steps", [])
        if not steps:
            steps = [line.strip() for line in llm_output.split("\n") if line.strip().startswith(("1.", "2.", "-", "*"))][:7]

        return ActionDecision(
            action="execute",
            confidence=0.8,
            rationale=llm_output,
            risk_params={"step_count": len(steps)},
            next_steps=steps if isinstance(steps, list) else [str(steps)],
            domain=self.name,
        )

    def get_tools(self) -> List[str]:
        return ["web_search", "task_decomposer"]
