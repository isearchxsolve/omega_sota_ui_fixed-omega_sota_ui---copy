"""Failure analysis and recovery suggestions."""

import logging
from typing import Any, Dict, List

from omega_agent.core.types import AgentResult, ExecutionContext

logger = logging.getLogger("omega_agent.reflection.analyzer")


class FailureAnalyzer:
    """Analyze failed executions and suggest recovery."""

    def analyze(self, ctx: ExecutionContext, result: AgentResult) -> Dict[str, Any]:
        issues: List[str] = []
        suggestions: List[str] = []

        if not result.success:
            issues.append("Execution did not succeed")

        if ctx.errors:
            issues.extend(ctx.errors[-5:])

        if result.latency > ctx.max_time * 0.9:
            issues.append("Near-timeout execution")
            suggestions.append("Reduce task count or increase max_time")

        if result.cost > 0.05:
            issues.append("High cost execution")
            suggestions.append("Use fast_model for simpler subtasks")

        metadata = result.metadata or {}
        tasks_completed = metadata.get("tasks_completed", 0)
        tasks_total = metadata.get("tasks_total", 0)
        if tasks_total and tasks_completed < tasks_total:
            issues.append(f"Partial completion: {tasks_completed}/{tasks_total} tasks")
            suggestions.append("Retry failed tools or simplify plan")

        if result.decision and result.decision.confidence < 0.5:
            issues.append("Low confidence decision")
            suggestions.append("Gather more data before acting")

        return {
            "issues": issues,
            "suggestions": suggestions,
            "should_retry": len(issues) > 0 and result.decision is not None and result.decision.confidence < 0.6,
        }

    def suggest_route_change(self, domain: str, analysis: Dict[str, Any]) -> str:
        if "timeout" in str(analysis.get("issues", [])).lower():
            return "fast"
        if "cost" in str(analysis.get("issues", [])).lower():
            return "efficient"
        return "default"
