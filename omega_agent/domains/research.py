"""Research domain persona — thorough, cited, structured."""

import re
from typing import Any, Dict, List

from omega_agent.core.types import ActionDecision, ExecutionContext, TaskNode
from omega_agent.domains.base import BaseDomain, DomainRouting


class ResearchDomain(BaseDomain):
    name = "research"
    keywords = ["research", "analyze", "review", "literature", "paper"]

    EXECUTION_STYLE = {
        "decision_urgency": "low",
        "risk_tolerance": "low",
        "research_depth": "high",
    }

    def get_system_prompt(self) -> str:
        return (
            "You are OMEGA Research — a rigorous academic analyst and synthesis engine.\n"
            "RULES:\n"
            "1. Structure output: Background, Methods/Approaches, Findings, Gaps, Conclusion\n"
            "2. Include citations or reference markers (Author, Year) where possible\n"
            "3. Use critical thinking: however, although, limitation, future work\n"
            "4. End with ACTION: publish_draft, deep_dive, or summarize\n"
            "5. Be comprehensive (>800 words for complex topics)\n"
            "6. Identify gaps and unresolved problems explicitly"
        )

    def get_routing(self, goal: str, ctx: ExecutionContext) -> DomainRouting:
        return DomainRouting(
            primary_model="claude-sonnet-4-20250514",
            backup_model="gpt-4o",
            tools=["web_search", "arxiv_search", "semantic_scholar"],
            decision_depth="strategic",
            reflection_level="deep",
            temperature=0.5,
            max_tokens=4096,
            system_prompt=self.get_system_prompt(),
        )

    def build_plan(self, goal: str, ctx: ExecutionContext) -> List[TaskNode]:
        return [
            TaskNode(
                id="web_research",
                name="Web Research",
                description="Search web for current information",
                tool_name="web_search",
                arguments={"query": goal[:200]},
                timeout=25,
            ),
            TaskNode(
                id="arxiv_search",
                name="Academic Search",
                description="Search arXiv for academic papers",
                tool_name="arxiv_search",
                arguments={"query": goal[:150], "max_results": 5},
                timeout=25,
            ),
            TaskNode(
                id="synthesis_prep",
                name="Prepare Synthesis",
                description="Combine research sources",
                tool_name="text_synthesizer",
                arguments={"inputs": ["$web_research", "$arxiv_search"], "goal": goal},
                dependencies=["web_research", "arxiv_search"],
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
        action = "summarize"
        if "deep" in llm_output.lower() or len(llm_output) > 2000:
            action = "deep_dive"
        if "publish" in llm_output.lower() or "draft" in llm_output.lower():
            action = "publish_draft"

        return ActionDecision(
            action=action,
            confidence=0.85 if len(llm_output) > 500 else 0.6,
            rationale=llm_output,
            risk_params={"citation_count": str(llm_output.count("(") + llm_output.count("["))},
            next_steps=[
                "Review citations for accuracy",
                "Expand gaps section if needed",
                "Validate claims against primary sources",
            ],
            domain=self.name,
        )

    def get_tools(self) -> List[str]:
        return ["web_search", "arxiv_search", "semantic_scholar", "text_synthesizer"]
