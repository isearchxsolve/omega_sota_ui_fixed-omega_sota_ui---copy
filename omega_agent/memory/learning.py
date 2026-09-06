"""
OMEGA Three-Mode Learning System
Handles proactive pattern matching, in-flight adaptations, and reactive post-mortems.
"""
import logging
from typing import Dict, Any, List
import time

logger = logging.getLogger(__name__)

class OmegaLearningEngine:
    def __init__(self, memory_store):
        """
        Expects a vector database or knowledge graph instance passed as memory_store.
        """
        self.memory = memory_store
        self.session_insights = []

    def proactive_learning(self, goal: str, context: Dict[str, Any]) -> List[str]:
        """
        Triggered before execution. 
        Retrieves historical anti-patterns and successful strategies for similar goals.
        """
        logger.info(f"Initiating Proactive Learning for goal: {goal}")
        try:
            # Pseudo-code for memory retrieval mapping to your specific FAISS/Graph setup
            past_insights = self.memory.query(f"Lessons learned regarding: {goal}", top_k=3)
            return [doc['content'] for doc in past_insights] if past_insights else []
        except Exception as e:
            logger.warning(f"Proactive learning retrieval failed: {e}")
            return []

    def in_flight_learning(self, task_id: str, error_msg: str, current_state: Dict) -> None:
        """
        Triggered during execution failures.
        Caches immediate blockers to prevent repeating the same mistake in the current session.
        """
        insight = f"Task {task_id} failed with error: {error_msg}. Avoid current approach."
        self.session_insights.append({
            "timestamp": time.time(),
            "type": "in_flight_correction",
            "insight": insight,
            "state": current_state
        })
        logger.info(f"Registered In-Flight Adaptation: {insight}")

    def reactive_learning(self, goal: str, execution_trace: List[Dict], success: bool) -> None:
        """
        Triggered after a goal completes (or fatally fails).
        Synthesizes the trace into long-term knowledge graph/vector rules.
        """
        logger.info("Initiating Reactive Post-Mortem Learning...")
        status = "SUCCESS" if success else "FAILURE"
        
        summary = f"Goal: {goal} | Status: {status} | Steps taken: {len(execution_trace)}"
        if not success:
            errors = [step.get('error') for step in execution_trace if step.get('error')]
            summary += f" | Critical Blockers: {', '.join(errors)}"
        
        try:
            # Store the synthesized learning in long-term memory
            self.memory.add_document({
                "content": summary,
                "metadata": {"type": "post_mortem", "success": success}
            })
            logger.info("Reactive learning successfully committed to long-term memory.")
        except Exception as e:
            logger.error(f"Failed to commit reactive learning: {e}")