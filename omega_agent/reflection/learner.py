"""Learning-to-route: update weights from outcomes."""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from omega_agent.core.config import Config
from omega_agent.core.types import AgentResult

logger = logging.getLogger("omega_agent.reflection.learner")


class OmegaLearner:
    """Update routing weights based on execution outcomes."""

    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.routing_db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.routing_weights: Dict[str, Dict[str, Dict[str, float]]] = self._load_weights()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    route TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    quality REAL NOT NULL,
                    cost REAL NOT NULL,
                    latency REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS routing_weights (
                    domain TEXT NOT NULL,
                    route TEXT NOT NULL,
                    successes REAL DEFAULT 0,
                    trials REAL DEFAULT 0,
                    avg_quality REAL DEFAULT 0.5,
                    avg_cost REAL DEFAULT 0.01,
                    PRIMARY KEY (domain, route)
                )
                """
            )

    def _load_weights(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        weights: Dict[str, Dict[str, Dict[str, float]]] = {}
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT domain, route, successes, trials, avg_quality, avg_cost FROM routing_weights"
            ).fetchall()
        for domain, route, successes, trials, avg_quality, avg_cost in rows:
            weights.setdefault(domain, {})[route] = {
                "successes": successes,
                "trials": trials,
                "avg_quality": avg_quality,
                "avg_cost": avg_cost,
            }
        return weights

    async def update_from_outcome(
        self,
        goal: str,
        domain: str,
        route: str,
        outcome: AgentResult,
        quality: float = 0.5,
    ) -> None:
        success = int(outcome.success)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO outcomes (goal, domain, route, success, quality, cost, latency)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (goal[:500], domain, route, success, quality, outcome.cost, outcome.latency),
            )

            existing = conn.execute(
                "SELECT successes, trials, avg_quality, avg_cost FROM routing_weights WHERE domain = ? AND route = ?",
                (domain, route),
            ).fetchone()

            if existing:
                s, t, aq, ac = existing
                t += 1
                s += success
                aq = aq * 0.9 + quality * 0.1
                ac = ac * 0.9 + outcome.cost * 0.1
                conn.execute(
                    """
                    UPDATE routing_weights SET successes=?, trials=?, avg_quality=?, avg_cost=?
                    WHERE domain = ? AND route = ?
                    """,
                    (s, t, aq, ac, domain, route),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO routing_weights (domain, route, successes, trials, avg_quality, avg_cost)
                    VALUES (?, ?, ?, 1, ?, ?)
                    """,
                    (domain, route, success, quality, outcome.cost),
                )

        self.routing_weights = self._load_weights()
        logger.info("Updated routing weights for domain=%s route=%s", domain, route)

    def get_best_route(self, domain: str) -> str:
        routes = self.routing_weights.get(domain, {})
        if not routes:
            defaults = {
                "crypto_trading": "fast",
                "research": "deep",
                "coding": "accurate",
                "planning": "default",
            }
            return defaults.get(domain, "default")

        scored = {}
        for route, data in routes.items():
            trials = max(1, data["trials"])
            win_rate = data["successes"] / trials
            scored[route] = (
                win_rate * 0.5
                + data["avg_quality"] * 0.3
                + (1 / (data["avg_cost"] + 0.01)) * 0.2
            )
        return max(scored, key=scored.get)

    def get_domain_stats(self, domain: str) -> Dict[str, Any]:
        return self.routing_weights.get(domain, {})
