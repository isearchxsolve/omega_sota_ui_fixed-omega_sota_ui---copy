"""Dynamic Result Synthesizer - Formats outputs and streams to UI natively."""

import json
import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger("omega_agent.reasoning.synthesizer")

class DynamicSynthesizer:
    def __init__(self, orchestrator=None, config=None, **kwargs):
        self.orchestrator = orchestrator
        self.config = config

    async def synthesize(self, *args, **kwargs) -> Tuple[Any, str, float]:
        logger.info("DynamicSynthesizer engaged. Formatting results for UI.")
        
        goal = kwargs.get("goal", args[0] if len(args) > 0 else "Unknown Goal")
        ctx = kwargs.get("ctx", args[2] if len(args) > 2 else None)
        results = kwargs.get("results", args[3] if len(args) > 3 else {})
            
        if not results and ctx and hasattr(ctx, "task_results"):
            results = ctx.task_results
        if not results:
            results = {}
            
        domain = getattr(ctx, "domain", "general") if ctx else "general"

        # 1. Format the raw tool JSON into beautiful UI Markdown
        try:
            from omega_agent.synthesis.action_formatter import format_execution_results_to_action
            decision = await format_execution_results_to_action(
                goal=goal,
                domain=domain,
                tool_results=results
            )
        except Exception as e:
            from omega_agent.core.types import ActionDecision
            logger.error(f"Error formatting ActionDecision: {e}")
            decision = ActionDecision(
                action="COMPLETE",
                confidence=1.0,
                rationale=f"Execution completed, but formatting failed: {e}",
                domain=domain,
                immediate_actions=[],
                next_steps=[]
            )

        # 2. STREAM DIRECTLY TO UI WITH ROBUST QUEUE DETECTION
        target_queue = None
        if ctx and hasattr(ctx, 'run_progress') and ctx.run_progress:
            target_queue = getattr(ctx.run_progress, '_tqueue', None) or getattr(ctx.run_progress, '_queue', None)
            
        if target_queue:
            try:
                output_text = decision.to_output() if hasattr(decision, 'to_output') else decision.rationale
                
                event_payload = {
                    "type": "action_decision",
                    "domain": decision.domain,
                    "action": decision.action,
                    "confidence": round(decision.confidence, 2),
                    "output": output_text,
                    "immediate_actions": [
                        {
                            "title": a.get("title", ""),
                            "url": a.get("url", "#"),
                            "detail": a.get("detail", ""),
                            "priority": a.get("priority", 2),
                        }
                        for a in decision.immediate_actions
                    ],
                    "next_steps": decision.next_steps,
                    "success": decision.action != "FAIL",
                }
                
                target_queue.put_nowait({"type": "event", "data": json.dumps(event_payload)})
                logger.info("Successfully pushed beautifully formatted results to UI Stream!")
            except Exception as e:
                logger.warning(f"Failed to push to UI queue: {e}")
        else:
            logger.warning("No valid UI progress queue found. Results won't stream live.")
            
        return decision, decision.rationale, 0.0