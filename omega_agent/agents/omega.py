"""Main OMEGA Agent — Autonomous AGI Orchestrator."""

import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional

from omega_agent.core.config import Config
from omega_agent.core.orchestrator import ModelOrchestrator
from omega_agent.core.execution import DAGExecutor
from omega_agent.core.progress import RunProgress
from omega_agent.core.types import AgentResult, ExecutionContext
from omega_agent.memory.system import MemorySystem
from omega_agent.reasoning.delivery import (
    DELIVERABLE_TOOLS,
    enrich_deliverable_decision,
    profile_wants_deliverables,
)
from omega_agent.reasoning.discovery import DynamicDiscoveryEngine
from omega_agent.reasoning.planner import DynamicPlanner
from omega_agent.reasoning.synthesizer import DynamicSynthesizer
from omega_agent.reasoning.types import DynamicDomainProfile
from omega_agent.reflection.analyzer import FailureAnalyzer
from omega_agent.reflection.learner import OmegaLearner
from omega_agent.reflection.deliverable_convergence import (
    DeliverableConvergenceEngine,
    wants_deliverable_verify,
)
from omega_agent.reflection.quality_gate import SOTAQualityGate as BaseSOTAGate
from omega_agent.tools.registry import ToolRegistry
from omega_agent.core.orchestrator import ValidatingToolExecutor
from omega_agent.reasoning.crisis import (
    build_immediate_actions,
    enrich_crisis_decision,
    extract_location,
    is_crisis_goal,
)
from omega_agent.tools.stdlib import register_all_tools
from omega_agent.utils.async_utils import OmegaRecursionGuard
from omega_agent.utils.metrics import MetricsCollector
from omega_agent.utils.logging import setup_logging

from omega_agent.advanced.self_consciousness import SelfConsciousnessMonitor, DynamicPersonaManager, Persona
from omega_agent.advanced.obedience_engine import ObedienceEngine, ObedienceConfig, ComplianceLevel
from omega_agent.advanced.enterprise_sota import TelemetrySystem, SOTAQualityGate, ZeroManualStepsEnforcer

# NEW: Pre-execution validation
from omega_agent.interaction.pre_execution_validator import quick_validate
from omega_agent.reasoning.crisis import validate_crisis_inputs

logger = logging.getLogger("omega_agent")

class OmegaAgent:
    def __init__(
        self,
        config: Optional[Config] = None,
        orchestrator: Optional[ModelOrchestrator] = None,
        memory: Optional[MemorySystem] = None,
        tools: Optional[ToolRegistry] = None,
        learner: Optional[OmegaLearner] = None,
        **kwargs 
    ):
        self.config = config or Config()
        setup_logging(self.config.log_level, self.config.log_file)

        self.orchestrator = orchestrator or ModelOrchestrator(self.config)
        self.memory = memory or MemorySystem(self.config)
        self.tools = tools or ToolRegistry()
        register_all_tools(self.tools)
        self.tool_executor = ValidatingToolExecutor(self.tools)
        self.dag_executor = DAGExecutor(self.config, self.tool_executor)

        self.discovery = DynamicDiscoveryEngine(self.config, self.orchestrator, self.tools, self.tool_executor)
        self.planner = DynamicPlanner(self.config, self.orchestrator, self.tools)
        self.synthesizer = DynamicSynthesizer(self.orchestrator)
        
        self.quality_gate = BaseSOTAGate(self.config, self.orchestrator, self.tool_executor)
        self.deliverable_convergence = DeliverableConvergenceEngine(self.config, self.orchestrator, self.tool_executor)

        self.learner = learner or OmegaLearner(self.config) if self.config.enable_learning else None
        self.analyzer = FailureAnalyzer()
        self.metrics = MetricsCollector()
        self._recursion_guard = OmegaRecursionGuard(self.config.recursion_limit)

        self.telemetry = TelemetrySystem()
        self.obedience_engine = ObedienceEngine(ObedienceConfig(compliance_level=ComplianceLevel.STRICT, force_action_first=True))
        self.persona_manager = DynamicPersonaManager()
        self.consciousness_monitor = None 

    async def run(
        self,
        goal: str,
        domain: Optional[str] = None,
        max_time: Optional[int] = None,
        user_inputs: Optional[Dict[str, str]] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        progress: Optional[RunProgress] = None,
        ui_event_callback: Optional[Callable] = None,
    ) -> AgentResult:
        if not goal or not isinstance(goal, str):
            raise ValueError("goal must be a non-empty string")

        self.telemetry.log_event("Workflow_Started", goal, {"user_inputs": user_inputs})
        self.consciousness_monitor = SelfConsciousnessMonitor(goal)
        self.persona_manager.set_monitor(self.consciousness_monitor)
        self.persona_manager.select_persona_for_task(goal, domain or "general")

        ctx = ExecutionContext(goal=goal, domain=domain or "general", max_time=max_time or self.config.max_total_time)
        if user_inputs: ctx.user_inputs.update(user_inputs)
        ctx.tenant_id = (tenant_id or "default").strip()[:48]
        ctx.user_id = (user_id or "").strip()[:64] or None
        ctx.workspace_id = self._workspace_id_for_goal(goal)
        ctx.workspace_root = self.config.workspace_root
        
        ctx.set_ui_callback(callback=ui_event_callback, progress=progress)
        
        if ctx.run_progress:
            ctx.run_progress.checkpoint("start", "Starting OMEGA workflow", 0.01, goal[:100])
            
        ctx.learning_progress["known_practices"] = self.memory.get_practices_hints()
        self.memory.audit.record("goal_received", goal, {"domain_hint": domain})

        start = time.time()
        with self._recursion_guard:
            try:
                # ====================================================================
                # NEW: PRE-EXECUTION VALIDATION GATE
                # ====================================================================
                # This runs BEFORE any planning or tool execution to catch missing
                # required inputs early, especially for interactive domains like SOS
                domain_for_validation = domain or "general"
                is_valid, validation_error = await quick_validate(
                    goal=goal,
                    domain=domain_for_validation,
                    config=self.config,
                    user_inputs=user_inputs
                )
                
                if not is_valid:
                    # Input validation failed - return AWAIT_INPUT without executing
                    logger.info(f"Pre-execution validation failed for goal: {goal[:50]}... domain: {domain_for_validation}")
                    
                    self.telemetry.log_event(
                        "PreValidation_Failed",
                        goal,
                        {"domain": domain_for_validation, "validation_error": validation_error[:100] if validation_error else ""}
                    )
                    
                    return AgentResult(
                        success=False,  # Not a failure, just paused
                        action="AWAIT_INPUT",
                        output=validation_error or "Missing required information to proceed.",
                        domain=domain_for_validation,
                        route=None,
                        cost=0.0,  # No cost since nothing was executed
                        latency=time.time() - start,
                        metadata={
                            "validation_failed": True,
                            "validation_reason": "missing_required_inputs",
                            "goal": goal,
                            "domain": domain_for_validation
                        }
                    )
                
                # ====================================================================
                # VALIDATION PASSED: Proceed with normal execution
                # ====================================================================
                logger.debug(f"Pre-execution validation passed for domain: {domain_for_validation}")
                
                return await self._execute_with_sota_guarantee(goal, ctx, start)
            except Exception as e:
                self.telemetry.log_error(goal, str(e))
                logger.error("Goal failed: %s", e, exc_info=True)
                return self._fail_result(str(e), ctx, start, "error", {"error": str(e)})

    async def _execute_with_sota_guarantee(self, goal: str, ctx: ExecutionContext, start: float) -> AgentResult:
        best_result: Optional[AgentResult] = None
        best_quality = 0.0
        last_result: Optional[AgentResult] = None

        current_sota_attempt = 0 
        max_retries = getattr(self.config, 'sota_max_retries', 3)

        while current_sota_attempt < max_retries:
            if ctx.is_timed_out(): break

            result = await self._execute_once(goal, ctx, start)
            last_result = result
            quality = result.metadata.get("sota_score", result.metadata.get("quality_score", 0.5))

            if quality > best_quality:
                best_quality = quality
                best_result = result

            if not self.quality_gate.should_retry(quality, current_sota_attempt):
                break

            current_sota_attempt += 1
            if ctx.run_progress:
                ctx.run_progress.checkpoint("retry", f"SOTA Quality {quality:.2f} too low. Retrying...", 0.1)

        return best_result or last_result

    async def _execute_once(self, goal: str, ctx: ExecutionContext, start: float) -> AgentResult:
        
        profile, discover_cost = await self.discovery.discover(goal, ctx, domain_hint=ctx.domain)
        ctx.dynamic_profile = profile
        ctx.domain = profile.domain
        ctx.add_cost(discover_cost) 
        
        profile.system_prompt += f"\n\n{SOTAQualityGate.inject_sota_pattern(ctx.domain)}"

        best_route = self.learner.get_best_route(profile.domain) if self.learner else profile.model_priority
        ctx.route = best_route if best_route != "default" else profile.model_priority
        model = self.orchestrator.select_model(profile.domain, ctx.route)

        dag, plan_cost = await self.planner.plan(goal, profile, ctx)
        ctx.add_cost(plan_cost)
        
        task_list = getattr(dag, "tasks", [])
        if ctx.run_progress:
            ctx.run_progress.checkpoint("plan", f"Plan ready — {len(task_list)} task(s)", 0.17, ", ".join(t.tool_name for t in task_list[:5]))

        async def _rewrite_llm(msgs):
            prompt_str = msgs[0]["content"] if isinstance(msgs, list) else str(msgs)
            res, _ = await self.orchestrator.invoke(prompt_str, temperature=0.2)
            return res
            
        await ZeroManualStepsEnforcer.enforce(str(dag), _rewrite_llm)

        task_results = await self.dag_executor.execute(dag, ctx)

        if ctx.run_progress:
            ctx.run_progress.checkpoint("synthesize", "Synthesizing results with LLM", 0.50)
            
        # Call the synthesizer cleanly
        decision, llm_output, synth_cost = await self.synthesizer.synthesize(
            goal=goal, profile=profile, ctx=ctx, results=task_results
        )
        ctx.add_cost(synth_cost)

        if is_crisis_goal(goal):
            loc = extract_location(goal, ctx.user_inputs)
            actions = build_immediate_actions(goal, task_results, loc)
            if not loc:
                decision.action = "AWAIT_INPUT"
                decision.rationale = (
                    "## ⏸ Paused for Your Input\n\n"
                    "🔴 I need your **city + state** or **ZIP code** to run localized food-bank "
                    "and emergency-cash searches near you.\n\n"
                    "Reply with your location (example: `Chicago, IL` or `60601`)."
                )
                decision.next_steps = ["Reply with your city or ZIP in the chat"]
                decision.risk_params = {**(decision.risk_params or {}), "urgency": "CRITICAL"}
            else:
                decision = enrich_crisis_decision(decision, actions, task_results)

        if ctx.run_progress:
            ctx.run_progress.checkpoint("finalize", "Finalizing deliverables (verify / zip)", 0.54)
            
        task_results = await self._finalize_deliverables(goal, ctx, profile, task_results)
        decision = enrich_deliverable_decision(decision, task_results, goal)

        if str(decision.action).upper() != "AWAIT_INPUT":
            validation_report = self.obedience_engine.validate_output(decision.action, goal)
            final_action_string = validation_report["corrected_output"]
        else:
            final_action_string = decision.action
        
        sota_score, failures = SOTAQualityGate.evaluate_dimensions(final_action_string, ctx.domain)
        
        # =========================================================================
        # CRITICAL BUG FIX: PRESERVE THE BEAUTIFUL MARKDOWN OUTPUT
        # Instead of overwriting the chat box with the 1-word "AWAIT_INPUT" action, 
        # we properly extract the formatted Markdown rationale from the decision object!
        # =========================================================================
        final_output = decision.to_output() if hasattr(decision, 'to_output') else decision.rationale
        decision.action = final_action_string

        verify_meta = task_results.get("deliverable_verify") if isinstance(task_results.get("deliverable_verify"), dict) else {}
        risk_params = getattr(decision, "risk_params", {}) or {}
        
        result = AgentResult(
            success=True,
            output=final_output,  # Now passing the full chat text, not "AWAIT_INPUT"
            domain=profile.domain,
            route=ctx.route,
            cost=ctx.cost_so_far,
            latency=time.time() - start,
            metadata={
                "model": model,
                "errors": ctx.errors,
                "dynamic_profile": profile.to_dict(),
                "tools_used": list({* [t.tool_name for t in task_list], *self._tools_from_results(task_results)}),
                "workspace_id": ctx.workspace_id,
                "archive_path": task_results.get("finalize_zip", {}).get("archive_path") or risk_params.get("archive_path"),
                "deliverable_verify": verify_meta,
                "sota_score": sota_score,
                "recovery_hints": SOTAQualityGate.get_recovery_strategy(failures) if failures else "None",
                "cognitive_state": self.consciousness_monitor.get_state_summary() if self.consciousness_monitor else "N/A"
            },
            decision=decision,
        )

        await self.memory.save_result(goal, result.domain, result)
        self.telemetry.log_event("Workflow_Completed", goal, {"sota_score": sota_score})

        if ctx.run_progress:
            ctx.run_progress.checkpoint("complete", f"Completed.", 1.0, f"{result.latency:.0f}s elapsed")
            
        return result

    async def _finalize_deliverables(self, goal: str, ctx: ExecutionContext, profile: DynamicDomainProfile, task_results: Dict[str, Any]) -> Dict[str, Any]:
        catalog = self.tools.get_catalog_for_llm()
        if not profile_wants_deliverables(profile.recommended_tools, profile.quality_criteria, goal=goal, web_context=ctx.web_context, catalog=catalog):
            return task_results

        ws = ctx.workspace_id
        base = self.config.workspace_root
        
        def _has_written_files():
            return any(isinstance(v, dict) and v.get("success") and v.get("files_written") for v in task_results.values())

        should_zip = _has_written_files()
        has_archive = any(isinstance(v, dict) and v.get("archive_path") for v in task_results.values())
        
        if should_zip and not has_archive:
            if ctx.run_progress:
                ctx.run_progress.checkpoint("zip", "Creating project zip archive", 0.92)
            z, cost = await self.tool_executor.execute("archive_zip", {"workspace_id": ws, "output_base": base, "tenant_id": ctx.tenant_id}, profile.domain)
            ctx.add_cost(cost)
            task_results["finalize_zip"] = z
            
        return task_results

    @staticmethod
    def _workspace_id_for_goal(goal: str) -> str:
        words = re.findall(r"[a-z0-9]+", goal.lower())[:8]
        return "-".join(words)[:48] or "omega-workspace"

    @staticmethod
    def _tools_from_results(task_results: Dict[str, Any]) -> List[str]:
        return [k.replace("finalize_", "") for k in task_results if k.startswith("finalize_")]

    @staticmethod
    def _fail_result(message: str, ctx: ExecutionContext, start: float, route: str, extra: Optional[Dict] = None) -> AgentResult:
        return AgentResult(
            success=False, output=f"Error: {message}", domain=ctx.domain or "unknown", route=route,
            cost=ctx.cost_so_far, latency=time.time() - start, metadata={**(extra or {}), "errors": ctx.errors}
        )