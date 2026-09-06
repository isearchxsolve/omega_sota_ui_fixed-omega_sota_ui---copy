"""Semantic memory — general knowledge store."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from omega_agent.core.config import Config

logger = logging.getLogger("omega_agent.memory.semantic")


class SemanticMemory:
    """Store general knowledge extracted from executions."""

    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.memory_db_path.replace(".db", "_semantic.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS semantic (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL DEFAULT 0.5,
                    timestamp TEXT NOT NULL,
                    UNIQUE(domain, key)
                )
                """
            )

    async def store(self, domain: str, key: str, value: Any, confidence: float = 0.5) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO semantic (domain, key, value, confidence, timestamp)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(domain, key) DO UPDATE SET
                    value = excluded.value,
                    confidence = excluded.confidence,
                    timestamp = excluded.timestamp
                """,
                (domain, key, json.dumps(value), confidence, datetime.now().isoformat()),
            )

    async def recall(self, domain: str, key: str) -> Any:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM semantic WHERE domain = ? AND key = ?",
                (domain, key),
            ).fetchone()
        if row:
            return json.loads(row[0])
        return None

    async def recall_domain(self, domain: str, limit: int = 20) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT key, value, confidence FROM semantic WHERE domain = ? LIMIT ?",
                (domain, limit),
            ).fetchall()
        return [{"key": r[0], "value": json.loads(r[1]), "confidence": r[2]} for r in rows]
