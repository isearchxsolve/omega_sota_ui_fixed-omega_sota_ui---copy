"""User preferences memory."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from omega_agent.core.config import Config

logger = logging.getLogger("omega_agent.memory.preferences")


class UserPreferences:
    """Store and recall user preferences that influence dynamic discovery."""

    def __init__(self, config: Config):
        self.db_path = config.memory_db_path.replace(".db", "_preferences.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def set(self, key: str, value: Any) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO preferences (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, json.dumps(value), datetime.now().isoformat()),
            )

    def get(self, key: str, default: Any = None) -> Any:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
        if row:
            return json.loads(row[0])
        return default

    def get_all(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT key, value FROM preferences").fetchall()
        return {k: json.loads(v) for k, v in rows}

    def get_practices_hints(self) -> List[str]:
        prefs = self.get("preferred_practices", [])
        return prefs if isinstance(prefs, list) else []

    def get_risk_tolerance(self) -> str:
        return self.get("risk_tolerance", "moderate")
