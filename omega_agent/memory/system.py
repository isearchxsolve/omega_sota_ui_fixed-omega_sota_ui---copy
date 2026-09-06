"""Unified memory facade with FAISS, preferences, and audit."""

import logging
from typing import Any, Dict, List

from omega_agent.core.config import Config
from omega_agent.core.types import AgentResult
from omega_agent.memory.episodic import EpisodicMemory
from omega_agent.memory.semantic import SemanticMemory
from omega_agent.memory.knowledge_graph import KnowledgeGraph
from omega_agent.memory.embeddings import EmbeddingMemory
from omega_agent.memory.preferences import UserPreferences
from omega_agent.memory.audit import AuditTrail

logger = logging.getLogger("omega_agent.memory")


class MemorySystem:
    """Unified memory: episodic + semantic + FAISS + preferences + audit."""

    def __init__(self, config: Config):
        self.config = config
        self.episodic = EpisodicMemory(config)
        self.semantic = SemanticMemory(config) if config.enable_semantic_memory else None
        self.knowledge_graph = KnowledgeGraph(config)
        self.embeddings = EmbeddingMemory() if config.enable_faiss else None
        self.preferences = UserPreferences(config)
        self.audit = AuditTrail(config)
        logger.info("MemorySystem initialized (faiss=%s)", bool(self.embeddings and self.embeddings.enabled))

    async def save_result(
        self,
        goal: str,
        domain: str,
        result: AgentResult,
    ) -> None:
        if self.config.enable_episodic_memory:
            await self.episodic.save(goal, domain, result)

        if result.decision and self.semantic:
            await self.semantic.store(
                domain,
                f"action_{result.decision.action}",
                {
                    "confidence": result.decision.confidence,
                    "goal_prefix": goal[:100],
                    "best_practices_used": result.metadata.get("best_practices", []),
                },
                confidence=result.decision.confidence,
            )

        if self.embeddings and self.embeddings.enabled:
            self.embeddings.add(
                f"{goal} -> {result.output[:500]}",
                {"domain": domain, "success": result.success, "action": result.decision.action if result.decision else None},
            )
            self.embeddings.persist()

        if result.decision:
            await self.knowledge_graph.record_outcome(domain, result.decision.action, result.success)

        self.audit.record(
            "execution_complete",
            goal,
            result.to_dict(),
            domain=domain,
        )

    async def recall_similar(self, goal: str, domain: str, limit: int = 5) -> List[Dict[str, Any]]:
        if self.embeddings and self.embeddings.enabled:
            vector_results = self.embeddings.search(goal, limit=limit)
            if vector_results:
                return vector_results
        return await self.episodic.recall_similar(goal, domain, limit)

    async def get_domain_knowledge(self, domain: str) -> List[Dict[str, Any]]:
        if self.semantic:
            return await self.semantic.recall_domain(domain)
        return []

    def get_practices_hints(self) -> List[str]:
        return self.preferences.get_practices_hints()

    def stats(self) -> Dict[str, Any]:
        return {
            "episodic_count": self.episodic.count(),
            "semantic_enabled": self.semantic is not None,
            "faiss_enabled": bool(self.embeddings and self.embeddings.enabled),
            "audit_chain_valid": self.audit.verify_chain(),
            "preferences": list(self.preferences.get_all().keys()),
        }
