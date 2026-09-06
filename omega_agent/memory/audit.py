"""Immutable audit trail for all executions."""

import hashlib
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from omega_agent.core.config import Config

logger = logging.getLogger("omega_agent.memory.audit")


class AuditTrail:
    """Append-only audit log with content hashes for immutability verification."""

    def __init__(self, config: Config):
        self.db_path = config.memory_db_path.replace(".db", "_audit.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    domain TEXT,
                    payload TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    prev_hash TEXT
                )
                """
            )

    def _last_hash(self) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT content_hash FROM audit_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else None

    @staticmethod
    def _hash(payload: str, prev_hash: Optional[str]) -> str:
        content = (prev_hash or "") + payload
        return hashlib.sha256(content.encode()).hexdigest()

    def record(
        self,
        event_type: str,
        goal: str,
        payload: Dict[str, Any],
        domain: Optional[str] = None,
    ) -> str:
        payload_str = json.dumps(payload, sort_keys=True, default=str)
        prev = self._last_hash()
        content_hash = self._hash(payload_str, prev)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO audit_log (timestamp, event_type, goal, domain, payload, content_hash, prev_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(),
                    event_type,
                    goal[:500],
                    domain,
                    payload_str,
                    content_hash,
                    prev,
                ),
            )
        return content_hash

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT timestamp, event_type, goal, domain, content_hash
                FROM audit_log ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {"timestamp": r[0], "event_type": r[1], "goal": r[2], "domain": r[3], "hash": r[4]}
            for r in rows
        ]

    def verify_chain(self) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT payload, content_hash, prev_hash FROM audit_log ORDER BY id"
            ).fetchall()

        prev = None
        for payload, stored_hash, prev_hash in rows:
            if prev_hash != prev:
                return False
            expected = self._hash(payload, prev_hash)
            if expected != stored_hash:
                return False
            prev = stored_hash
        return True
