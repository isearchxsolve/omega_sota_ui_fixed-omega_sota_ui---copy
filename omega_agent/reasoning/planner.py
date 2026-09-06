"""LLM-generated dynamic execution plans with evidence-driven mock fallback."""

import logging
from typing import Any, Dict, List, Tuple

from omega_agent.core.config import Config
from omega_agent.core.orchestrator import ModelOrchestrator
from omega_agent.core.types import ExecutionContext, TaskNode
from omega_agent.reasoning.arg_inference import EvidenceArgInference
from omega_agent.reasoning.crisis import extract_location, is_crisis_goal
from omega_agent.reasoning.evidence import is_action_tool, is_materialize_tool
from omega_agent.tools.registry import ToolRegistry
from omega_agent.reasoning.types import DynamicDomainProfile

logger = logging.getLogger("omega_agent.reasoning.planner")

class DynamicPlanner:
    """
    SOTA Planner: Uses a deterministic Python-based Map-Reduce strategy for build goals
    and delegates to the Orchestrator for complex, exploratory reasoning.
    """
    def __init__(self, config: Config, orchestrator: ModelOrchestrator, tool_registry: ToolRegistry):
        self.config = config
        self.orchestrator = orchestrator
        self.tools = tool_registry

    async def plan(self, goal: str, profile: DynamicDomainProfile, ctx: ExecutionContext) -> Tuple[List[TaskNode], float]:
        catalog = self.tools.get_catalog_for_llm()
        catalog_by_name = {t["name"]: t for t in catalog}
        
        is_build_goal = any(kw in goal.lower() for kw in ("build", "create", "develop", "make", "app", "system", "platform"))
        
        if is_build_goal and "llm_generate_files" in catalog_by_name:
            logger.info("Build goal detected — Bypassing LLM Planner for SOTA Map-Reduce DAG")
            return self._plan_from_evidence(goal, profile, catalog_by_name, ctx.web_context, ctx), 0.0

        prompt = f"GOAL: {goal}\nDOMAIN PROFILE: {profile.domain}\n"
        if self.config.has_llm_credentials():
            data, cost = await self.orchestrator.invoke_json(prompt=prompt, system="Generate a task DAG. Return valid JSON only.", temperature=0.2)
            tasks = self._parse_tasks(data, set(catalog_by_name.keys()))
            if tasks: return tasks, cost

        return self._plan_from_evidence(goal, profile, catalog_by_name, ctx.web_context, ctx), 0.0

    def _parse_tasks(self, data: Dict[str, Any], allowed: set) -> List[TaskNode]:
        return [TaskNode(
            id=t.get("id", f"task_{i}"), name=t.get("name", ""), description=t.get("description", ""),
            tool_name=t.get("tool_name", ""), arguments=t.get("arguments", {}), 
            dependencies=t.get("dependencies", []), timeout=int(t.get("timeout", 600))
        ) for i, t in enumerate(data.get("tasks", [])) if t.get("tool_name") in allowed]

    def _plan_from_evidence(self, goal: str, profile: DynamicDomainProfile, catalog_by_name: Dict[str, Dict[str, Any]], web_context: Dict[str, Any], ctx: ExecutionContext) -> List[TaskNode]:
        nodes: List[TaskNode] = []
        gather_ids: List[str] = []
        materialize_ids: List[str] = []

        infer_kw = dict(
            user_inputs=ctx.user_inputs, workspace_id=ctx.workspace_id,
            output_base=ctx.workspace_root or self.config.workspace_root,
        )

        loc = extract_location(goal, ctx.user_inputs)
        if is_crisis_goal(goal) and not loc and "send_chat_message" in catalog_by_name:
            msg = (
                "🔴 I need your **city + state** or **ZIP code** to find food banks, emergency cash, "
                "and local assistance programs near you. Please reply with your location."
            )
            nodes.append(
                TaskNode(
                    id="ask_location",
                    name="Request location",
                    description="Pause until user provides city or ZIP",
                    tool_name="send_chat_message",
                    arguments={"message": msg, "urgency": "high"},
                    timeout=30,
                )
            )
            return nodes

        search_count = 2 if not is_crisis_goal(goal) else 1
        for i in range(search_count):
            task_id = f"research_{i+1}"
            if "web_search" in catalog_by_name:
                args = EvidenceArgInference.infer_args(catalog_by_name["web_search"], goal, profile, web_context, [], **infer_kw)
                nodes.append(TaskNode(id=task_id, name=f"Research Phase {i+1}", description="Gather evidence", tool_name="web_search", arguments=args, timeout=self.config.max_task_timeout))
                gather_ids.append(task_id)

        mat_deps = list(gather_ids)
        action_ids: List[str] = []
        for j, tool_name in enumerate(self._action_tools_from_profile(profile.recommended_tools)[:4]):
            if tool_name not in catalog_by_name:
                continue
            entry = catalog_by_name[tool_name]
            args = EvidenceArgInference.infer_args(entry, goal, profile, web_context, mat_deps, **infer_kw)
            if "location" in entry.get("args", {}) and not (args.get("location") or "").strip():
                continue
            task_id = f"action_{j+1}"
            nodes.append(
                TaskNode(
                    id=task_id,
                    name=f"Execute {tool_name}",
                    description=f"Run {tool_name} for goal",
                    tool_name=tool_name,
                    arguments=args,
                    dependencies=mat_deps,
                    timeout=600,
                )
            )
            action_ids.append(task_id)
        mat_deps = mat_deps + action_ids
        is_build_goal = any(kw in goal.lower() for kw in ("build", "create", "develop", "make", "app"))

        if is_build_goal and "llm_generate_files" in catalog_by_name:
            entry = catalog_by_name["llm_generate_files"]
            categories = [("Core Data/Models", "data_layer"), ("Business Logic/Services", "business_logic"), ("Interface/UI", "interface")]
            dynamic_contract = profile.tool_usage_guidance.get("llm_generate_files", "")
            
            tick3 = chr(96) * 3
            
            for name, uid in categories:
                args = EvidenceArgInference.infer_args(entry, goal, profile, web_context, mat_deps, **infer_kw)
                
                args["prompt"] = (
                    f"Goal: {goal}.\n"
                    f"TASK: Implement the {name}.\n\n"
                    f"ARCHITECTURAL CONTRACT:\n{dynamic_contract}\n\n"
                    "CRITICAL FORMAT RULES:\n"
                    "1. DO NOT OUTPUT JSON. JSON escaping will ruin the code formatting.\n"
                    "2. You MUST output all files using Markdown code blocks.\n"
                    "3. The top of EVERY code block MUST contain the file path separated by a colon.\n"
                    "EXAMPLE:\n"
                    f"{tick3}typescript:src/index.ts\n"
                    "console.log('Hello');\n"
                    f"{tick3}\n"
                    "4. Write MASSIVE, dense implementations exceeding 500 lines total. Do NOT leave placeholders."
                )
                
                nodes.append(TaskNode(
                    id=f"generate_{uid}", name=f"Generate {name}", description=f"Implement {name}",
                    tool_name="llm_generate_files", dependencies=mat_deps, timeout=600, arguments=args
                ))
                materialize_ids.append(f"generate_{uid}")
        else:
            for j, tool_name in enumerate(self._dedupe_materialize(profile.recommended_tools)[:2]):
                task_id = f"materialize_{j+1}"
                nodes.append(TaskNode(id=task_id, name="Materialize", description="", tool_name=tool_name, arguments=EvidenceArgInference.infer_args(catalog_by_name[tool_name], goal, profile, web_context, mat_deps, **infer_kw), dependencies=mat_deps, timeout=600))
                materialize_ids.append(task_id)

        if "archive_zip" in catalog_by_name and materialize_ids:
            nodes.append(TaskNode(
                id="deliver_zip", name="Zip deliverable", description="Archive project",
                tool_name="archive_zip", arguments=EvidenceArgInference.infer_args(catalog_by_name["archive_zip"], goal, profile, web_context, materialize_ids, **infer_kw),
                dependencies=materialize_ids, timeout=120
            ))

        return nodes

    def _dedupe_materialize(self, tool_names: List[str]) -> List[str]:
        seen = set()
        return [n for n in tool_names if is_materialize_tool(n) and not (n in seen or seen.add(n))]

    @staticmethod
    def _action_tools_from_profile(tool_names: List[str]) -> List[str]:
        seen = set()
        return [n for n in tool_names if is_action_tool(n) and not (n in seen or seen.add(n))]