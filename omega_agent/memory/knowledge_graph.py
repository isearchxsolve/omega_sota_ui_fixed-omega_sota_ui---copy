"""Knowledge graph — relationships between concepts and outcomes."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from omega_agent.core.config import Config

logger = logging.getLogger("omega_agent.memory.knowledge_graph")


class KnowledgeGraph:
    """Simple knowledge graph for domain relationships."""

    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.memory_db_path.replace(".db", "_kg.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    node_type TEXT NOT NULL,
                    properties TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    timestamp TEXT NOT NULL
                )
                """
            )

    async def add_node(self, name: str, node_type: str, properties: Optional[Dict] = None) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO nodes (name, node_type, properties) VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET properties = excluded.properties
                """,
                (name, node_type, json.dumps(properties or {})),
            )

    async def add_edge(self, source: str, target: str, relation: str, weight: float = 1.0) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO edges (source, target, relation, weight, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source, target, relation, weight, datetime.now().isoformat()),
            )

    async def get_related(self, name: str, relation: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT target, relation, weight FROM edges WHERE source = ?"
        params: tuple = (name,)
        if relation:
            query += " AND relation = ?"
            params = (name, relation)

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [{"target": r[0], "relation": r[1], "weight": r[2]} for r in rows]

    async def record_outcome(self, domain: str, action: str, success: bool) -> None:
        await self.add_node(domain, "domain")
        await self.add_node(action, "action")
        weight = 1.0 if success else 0.3
        await self.add_edge(domain, action, "produced", weight)
