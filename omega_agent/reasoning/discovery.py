"""Dynamic domain, best-practices, and tool discovery via web search + LLM.

No hardcoded domains. No scaffold tools. No template shortcuts.
Everything is derived from the goal and real web evidence.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from omega_agent.core.config import Config
from omega_agent.core.orchestrator import ModelOrchestrator
from omega_agent.core.types import ExecutionContext
from omega_agent.reasoning.crisis import (
    crisis_discovery_queries,
    crisis_recommended_tools,
    extract_location,
    is_crisis_goal,
)
from omega_agent.reasoning.evidence import (
    build_tool_guidance_from_evidence,
    extract_practices_from_snippets,
    infer_domain_label,
    rank_tools_by_evidence,
)
from omega_agent.reasoning.types import DynamicDomainProfile
from omega_agent.tools.executor import ToolExecutor
from omega_agent.tools.registry import ToolRegistry

logger = logging.getLogger("omega_agent.reasoning.discovery")

DISCOVERY_SYSTEM = """You are OMEGA Discovery Engine. Your job is to analyze a user goal and
web evidence, then produce a precise execution profile.

RULES:
- Never use a fixed domain taxonomy. Infer everything from the goal and evidence.
- recommended_tools must come ONLY from the catalog provided. Never invent tool names.
- For goals that produce a deliverable (app, script, config, report, data pipeline, etc.):
    Wave 1 tools: web_search (gather evidence on best stack, libraries, patterns)
    Wave 2 tools: llm_generate_files (generate goal-specific files from evidence)
    Wave 3 tools: run_shell (install, build, test)
  Do NOT recommend scaffold_* tools — they do not exist.
- best_practices must come from web snippets, not generic advice.
- quality_criteria must be measurable (e.g. "npm run build exits 0", "all tests pass",
  "API returns 200 on /health", "file count > 10").
- system_prompt must make the agent a genuine expert on the specific goal domain.
- tool_usage_guidance must explain HOW to use each tool for THIS specific goal.

Return JSON with these keys:
- domain: descriptive slug inferred from goal (free-form, e.g. "crm-web-app", "ml-data-pipeline")
- sub_domain: more specific label
- confidence: 0-1
- best_practices: list of strings grounded in web evidence
- execution_style: {urgency, depth, risk_tolerance} each low/medium/high
- recommended_tools: list of tool names FROM THE CATALOG ONLY
- tool_usage_guidance: {tool_name: "how to use it for this specific goal"}
- system_prompt: expert persona for this specific goal
- output_format: measurable deliverable description
- quality_criteria: list of measurable success criteria grounded in evidence
- model_priority: "speed" or "accuracy"
"""


def _discovery_queries_from_goal(goal: str) -> List[str]:
    """Produce rich, targeted search queries that gather real evidence for this goal."""
    g = goal.strip()
    subject = g[:80]

    return [
        f"{subject} best tools libraries frameworks 2024 2025",
        f"{subject} production architecture patterns",
        f"{subject} step by step implementation tutorial",
        f"{subject} open source example best practices",
        f"{subject} common pitfalls performance tips",
    ]


class DynamicDiscoveryEngine:
    """Discover domain, practices, and tools via web search + LLM reasoning."""

    def __init__(
        self,
        config: Config,
        orchestrator: ModelOrchestrator,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
    ):
        self.config = config
        self.orchestrator = orchestrator
        self.tools = tool_registry
        self.tool_executor = tool_executor

    async def discover(
        self,
        goal: str,
        ctx: ExecutionContext,
        domain_hint: Optional[str] = None,
    ) -> Tuple[DynamicDomainProfile, float]:
        ctx.checkpoint("discovery", "Gathering web evidence for goal", 0.04, goal[:80])
        web_context, web_cost = await self._gather_web_context(
            goal, ctx=ctx, user_inputs=ctx.user_inputs
        )
        ctx.web_context = web_context

        catalog = self.tools.get_catalog_for_llm()
        # Filter out scaffold tools if they somehow made it into the registry
        catalog = [t for t in catalog if not t["name"].startswith("scaffold_")]

        past_practices = ctx.learning_progress.get("known_practices", [])
        prompt = self._build_discovery_prompt(goal, web_context, catalog, domain_hint, past_practices)

        llm_cost = 0.0
        if self.config.has_llm_credentials():
            ctx.checkpoint("discovery", "LLM analyzing goal and evidence", 0.10)
            data, initial_cost = await self.orchestrator.invoke_json(
                prompt=prompt,
                system=DISCOVERY_SYSTEM,
                temperature=0.3,
            )
            llm_cost += initial_cost
            profile = self._validate_profile(data, catalog, web_context, goal)
        else:
            profile = self._discover_from_evidence(goal, web_context, catalog, domain_hint)

        # =========================================================================
        # THE DYNAMIC ARCHITECT PATTERN: Generate a rigid contract on the fly
        # =========================================================================
        is_build_goal = any(kw in goal.lower() for kw in ("build", "create", "develop", "make", "app", "crm", "platform", "system"))
        
        if is_build_goal and self.config.has_llm_credentials():
            ctx.checkpoint("discovery", "Synthesizing dynamic SOTA architectural contract...", 0.12)
            contract_text, arch_cost = await self._synthesize_architectural_contract(goal, web_context.get("snippets", []))
            llm_cost += arch_cost
            
            # Safely inject the strict contract directly into the Coder tool's guidance
            if not profile.tool_usage_guidance:
                profile.tool_usage_guidance = {}
            
            profile.tool_usage_guidance["llm_generate_files"] = contract_text
            
            # Reinforce the agent's overall persona
            profile.system_prompt += f"\n\nCRITICAL ARCHITECTURAL CONTRACT TO ENFORCE:\n{contract_text}"

        ctx.checkpoint(
            "discovery",
            f"Domain: {profile.domain}",
            0.14,
            ", ".join(profile.recommended_tools[:5]) or "tools TBD",
        )
        return profile, web_cost + llm_cost

    async def _synthesize_architectural_contract(self, goal: str, web_snippets: List[str]) -> Tuple[str, float]:
        """Acts as an Elite Enterprise Architect to enforce non-negotiable coding standards."""
        system_prompt = (
            "You are an elite Enterprise Software Architect. Your job is to analyze web research "
            "and define a STRICT, unforgiving Architectural Contract for a senior coding agent to follow. "
            "Do NOT write the actual application code. Write the RULES."
        )
        
        snippets_text = "\n".join(f"- {s}" for s in web_snippets[:15])
        user_prompt = f"""
        GOAL: {goal}
        
        LIVE WEB RESEARCH ON SOTA PATTERNS:
        {snippets_text}
        
        TASK:
        Based on the research above and your expert knowledge, synthesize a rigid, 5-to-9 pillar ARCHITECTURAL CONTRACT.
        You must explicitly mandate:
        1. The core design pattern (e.g., DDD, MVC, Microservices, Hexagonal, etc.)
        2. Specific state-of-the-art libraries/frameworks to use.
        3. Mandatory security, validation, error-handling, and scalability mechanisms.
        4. Structural file organization logic.
        
        Format this as a highly dense, bulleted list of non-negotiable rules. 
        END YOUR RESPONSE EXACTLY WITH THIS PHRASE: 
        'CRITICAL SOTA RULE: You MUST output highly dense, production-ready code exceeding 500 lines. ZERO BOILERPLATE. You must return a valid JSON mapping file paths to code.'
        """
        
        # Call the Orchestrator to generate the contract
        contract, cost = await self.orchestrator.invoke(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.2, # Low temp for strict, objective rules
            max_tokens=1024
        )
        return contract, cost

    async def _gather_web_context(
        self,
        goal: str,
        ctx: Optional[ExecutionContext] = None,
        user_inputs: Optional[Dict[str, str]] = None,
    ) -> Tuple[Dict[str, Any], float]:
        total_cost = 0.0
        location = extract_location(goal, user_inputs)
        if is_crisis_goal(goal):
            queries = crisis_discovery_queries(goal, location)
        else:
            queries = _discovery_queries_from_goal(goal)

        if user_inputs:
            for key, val in user_inputs.items():
                if val and key.upper() not in ("GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
                    queries.append(f"{goal[:60]} {key}: {val[:40]}")

        all_results: List[Dict[str, Any]] = []
        snippets: List[str] = []
        query_list = queries[:6]

        for idx, query in enumerate(query_list):
            if ctx is not None:
                ctx.checkpoint("discovery", f"Web search {idx + 1}/{len(query_list)}", 0.04 + 0.08 * idx / max(len(query_list), 1), query[:72])
            result, cost = await self.tool_executor.execute("web_search", {"query": query, "max_results": 5}, "discovery")
            total_cost += cost
            all_results.append(result)
            for item in result.get("results", []):
                snip = item.get("snippet") or item.get("title", "")
                if snip:
                    snippets.append(snip[:400])

        return {"queries": queries, "results": all_results, "snippets": snippets[:20]}, total_cost

    def _build_discovery_prompt(self, goal, web_context, catalog, domain_hint, past_practices) -> str:
        snippets = "\n".join(f"[{i+1}] {s}" for i, s in enumerate(web_context.get("snippets", [])[:12]))
        tools_block = "\n".join(f"  - {t['name']}: {t['description']} | args: {t.get('args', {})}" for t in catalog)
        hint = f"\nUser domain hint: {domain_hint}" if domain_hint else ""
        past = "\n".join(f"- {p}" for p in past_practices[:5]) if past_practices else "None"

        return f"""GOAL:\n{goal}\n{hint}\n\nWEB SEARCH EVIDENCE:\n{snippets or "No web results"}\n\nAVAILABLE TOOLS:\n{tools_block}\n\nPAST PRACTICES:\n{past}\n\nProduce a precise execution profile."""

    def _validate_profile(self, data, catalog, web_context, goal) -> DynamicDomainProfile:
        valid_names = {t["name"] for t in catalog}
        valid_names -= {n for n in valid_names if n.startswith("scaffold_")}
        recommended = [t for t in data.get("recommended_tools", []) if t in valid_names]

        if not recommended:
            recommended = rank_tools_by_evidence(data.get("domain", "general"), web_context, catalog, top_k=6, goal=goal)
            for must_have in ("web_search", "llm_generate_files"):
                if must_have not in recommended and must_have in valid_names:
                    recommended.insert(0, must_have)

        if is_crisis_goal(goal):
            data["domain"] = data.get("domain") or "emergency-assistance"
            for tool in crisis_recommended_tools():
                if tool in valid_names and tool not in recommended:
                    recommended.insert(0, tool)

        data["recommended_tools"] = recommended
        data["web_evidence"] = web_context.get("snippets", [])[:8]

        if not data.get("system_prompt"):
            data["system_prompt"] = self._default_system_prompt(data.get("domain", "general"), data.get("best_practices", []))
        if not data.get("quality_criteria"):
            data["quality_criteria"] = ["actionable output produced", "grounded in web evidence", "complete and runnable"]

        return DynamicDomainProfile.from_dict(data)

    def _discover_from_evidence(self, goal, web_context, catalog, domain_hint) -> DynamicDomainProfile:
        combined = (goal + " " + " ".join(web_context.get("snippets", []))).lower()
        domain = domain_hint or infer_domain_label(combined, goal)
        best_practices = extract_practices_from_snippets(web_context.get("snippets", []))
        if not best_practices:
            best_practices = ["Gather web evidence", "Generate all files through LLM", "Deliver a complete runnable artifact"]

        clean_catalog = [t for t in catalog if not t["name"].startswith("scaffold_")]
        if is_crisis_goal(goal):
            domain = "emergency-assistance"
            recommended = [t for t in crisis_recommended_tools() if t in {x["name"] for x in clean_catalog}]
        else:
            recommended = rank_tools_by_evidence(domain, web_context, clean_catalog, top_k=7, goal=goal)
            for must_have in ("web_search", "llm_generate_files", "run_shell"):
                if must_have not in recommended:
                    recommended.append(must_have)

        urgency = "high" if any(w in combined for w in ("urgent", "asap", "now")) else "medium"
        tool_guidance = {}
        for tool_name in recommended:
            tool = next((t for t in clean_catalog if t["name"] == tool_name), None)
            if tool:
                tool_guidance[tool_name] = build_tool_guidance_from_evidence(tool, goal, web_context)

        return DynamicDomainProfile(
            domain=domain, sub_domain=domain.split("_")[-1] if "_" in domain else domain,
            confidence=0.65, best_practices=best_practices,
            execution_style={"urgency": urgency, "depth": "high", "risk_tolerance": "moderate"},
            recommended_tools=recommended, tool_usage_guidance=tool_guidance,
            system_prompt=self._default_system_prompt(domain, best_practices),
            output_format="complete runnable deliverable",
            quality_criteria=["deliverable written to disk", "grounded in web evidence", "complete — no placeholders"],
            web_evidence=web_context.get("snippets", [])[:8],
            model_priority="speed" if urgency == "high" else "accuracy",
        )

    @staticmethod
    def _default_system_prompt(domain: str, practices: List[str]) -> str:
        practice_block = "\n".join(f"- {p}" for p in practices[:6])
        return f"You are OMEGA — expert action-taker for: {domain.replace('_', ' ')}.\nApply these best practices:\n{practice_block}\n"