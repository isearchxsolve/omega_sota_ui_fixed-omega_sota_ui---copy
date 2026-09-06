"""Episodic memory — specific experiences stored in SQLite."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from omega_agent.core.config import Config
from omega_agent.core.types import AgentResult

logger = logging.getLogger("omega_agent.memory.episodic")


class EpisodicMemory:
    """Store and recall specific execution experiences."""

    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.memory_db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episodic (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    route TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    output TEXT NOT NULL,
                    cost REAL NOT NULL,
                    latency REAL NOT NULL,
                    metadata TEXT,
                    timestamp TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_episodic_domain ON episodic(domain)"
            )

    async def save(
        self,
        goal: str,
        domain: str,
        result: AgentResult,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO episodic (goal, domain, route, success, output, cost, latency, metadata, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    goal[:1000],
                    domain,
                    result.route,
                    int(result.success),
                    result.output[:5000],
                    result.cost,
                    result.latency,
                    json.dumps(result.metadata),
                    datetime.now().isoformat(),
                ),
            )
        logger.info("Saved episodic memory for domain=%s", domain)

    async def recall_similar(
        self,
        goal: str,
        domain: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        goal_words = set(goal.lower().split())
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT goal, domain, route, success, output, cost, latency, timestamp
                FROM episodic
                WHERE domain = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (domain, limit * 3),
            ).fetchall()

        scored = []
        for row in rows:
            row_words = set(row[0].lower().split())
            overlap = len(goal_words & row_words) / max(1, len(goal_words))
            scored.append((overlap, {
                "goal": row[0],
                "domain": row[1],
                "route": row[2],
                "success": bool(row[3]),
                "output": row[4][:500],
                "cost": row[5],
                "latency": row[6],
                "timestamp": row[7],
            }))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM episodic").fetchone()[0]
