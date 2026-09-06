"""FAISS-backed semantic memory (optional — falls back to keyword recall)."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("omega_agent.memory.embeddings")

try:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False


class EmbeddingMemory:
    """Vector similarity memory using FAISS + sentence-transformers."""

    def __init__(self, index_path: str = "./data/omega_faiss.index", model_name: str = "all-MiniLM-L6-v2"):
        self.index_path = index_path
        self.enabled = FAISS_AVAILABLE
        self.model = None
        self.index = None
        self.documents: List[Dict[str, Any]] = []

        if not self.enabled:
            logger.info("FAISS/embeddings unavailable — using keyword fallback")
            return

        Path(index_path).parent.mkdir(parents=True, exist_ok=True)
        self.model = SentenceTransformer(model_name)
        dim = self.model.get_sentence_embedding_dimension()

        if Path(index_path).exists():
            try:
                self.index = faiss.read_index(index_path)
                logger.info("Loaded FAISS index from %s", index_path)
            except Exception as e:
                logger.warning("FAISS load failed: %s", e)

        if self.index is None:
            self.index = faiss.IndexFlatIP(dim)

    def add(self, text: str, metadata: Dict[str, Any]) -> None:
        if not self.enabled or not self.model or not self.index:
            return
        emb = self.model.encode([text], normalize_embeddings=True)
        self.index.add(emb.astype("float32"))
        self.documents.append({"text": text, **metadata})

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.enabled or not self.model or not self.index or self.index.ntotal == 0:
            return []

        emb = self.model.encode([query], normalize_embeddings=True).astype("float32")
        k = min(limit, self.index.ntotal)
        scores, indices = self.index.search(emb, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and idx < len(self.documents):
                results.append({**self.documents[idx], "similarity": float(score)})
        return results

    def persist(self) -> None:
        if self.enabled and self.index:
            try:
                faiss.write_index(self.index, self.index_path)
            except Exception as e:
                logger.warning("FAISS persist failed: %s", e)
