"""Stream execution results and ActionDecision to UI via SSE."""

import json
import logging
from typing import Callable, Optional

from omega_agent.core.types import ActionDecision

logger = logging.getLogger("omega_agent.api.sse_output")

async def stream_action_decision(
    action_decision: ActionDecision,
    event_callback: Optional[Callable] = None,
    progress_queue: Optional[object] = None,
) -> None:
    """Push ActionDecision to the UI event stream."""
    
    # Safely extract Markdown output whether it relies on a helper or the rationale
    output_text = action_decision.to_output() if hasattr(action_decision, 'to_output') else action_decision.rationale
    
    event_payload = {
        "type": "action_decision",
        "domain": action_decision.domain,
        "action": action_decision.action,
        "confidence": round(action_decision.confidence, 2),
        "output": output_text,
        "immediate_actions": [
            {
                "title": a.get("title", ""),
                "url": a.get("url", "#"),
                "detail": a.get("detail", ""),
                "priority": a.get("priority", 2),
            }
            for a in action_decision.immediate_actions
        ],
        "next_steps": action_decision.next_steps,
        "success": action_decision.action != "FAIL",
    }
    
    # Dispatch directly via UI Callback hook
    if event_callback:
        try:
            await event_callback(event_payload)
        except Exception as e:
            logger.warning(f"Callback error: {e}")
    
    # Or dispatch via traditional Gradio/FastAPI Async Queue
    if progress_queue:
        try:
            sse_event = {
                "type": "event",
                "data": json.dumps(event_payload),
            }
            progress_queue.put_nowait(sse_event)
        except Exception as e:
            logger.warning(f"Queue error: {e}")