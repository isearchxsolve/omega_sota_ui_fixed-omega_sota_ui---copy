"""Success metrics and monitoring."""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class DomainMetrics:
    success_rate: float = 0.0
    avg_latency: float = 0.0
    avg_cost: float = 0.0
    trials: int = 0
    avg_quality: float = 0.0


class MetricsCollector:
    """Collect and aggregate OMEGA performance metrics."""

    def __init__(self, db_path: str = "./data/omega_metrics.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    route TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    quality REAL NOT NULL,
                    cost REAL NOT NULL,
                    latency REAL NOT NULL,
                    goal TEXT NOT NULL
                )
                """
            )

    def record(
        self,
        domain: str,
        route: str,
        success: bool,
        quality: float,
        cost: float,
        latency: float,
        goal: str,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO metrics (timestamp, domain, route, success, quality, cost, latency, goal)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(),
                    domain,
                    route,
                    int(success),
                    quality,
                    cost,
                    latency,
                    goal[:500],
                ),
            )

    def get_domain_metrics(self, domain: Optional[str] = None) -> Dict[str, DomainMetrics]:
        query = "SELECT domain, success, quality, cost, latency FROM metrics"
        params: tuple = ()
        if domain:
            query += " WHERE domain = ?"
            params = (domain,)

        aggregated: Dict[str, Dict[str, float]] = {}
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()

        for dom, success, quality, cost, latency in rows:
            if dom not in aggregated:
                aggregated[dom] = {
                    "successes": 0,
                    "trials": 0,
                    "quality_sum": 0.0,
                    "cost_sum": 0.0,
                    "latency_sum": 0.0,
                }
            aggregated[dom]["trials"] += 1
            aggregated[dom]["successes"] += success
            aggregated[dom]["quality_sum"] += quality
            aggregated[dom]["cost_sum"] += cost
            aggregated[dom]["latency_sum"] += latency

        result: Dict[str, DomainMetrics] = {}
        for dom, data in aggregated.items():
            trials = max(1, data["trials"])
            result[dom] = DomainMetrics(
                success_rate=data["successes"] / trials,
                avg_quality=data["quality_sum"] / trials,
                avg_cost=data["cost_sum"] / trials,
                avg_latency=data["latency_sum"] / trials,
                trials=data["trials"],
            )
        return result

    def get_summary(self) -> Dict[str, Any]:
        by_domain = self.get_domain_metrics()
        if not by_domain:
            return {"domains": {}, "overall": {"success_rate": 0, "avg_cost": 0, "trials": 0}}

        total_trials = sum(m.trials for m in by_domain.values())
        total_successes = sum(m.success_rate * m.trials for m in by_domain.values())
        total_cost = sum(m.avg_cost * m.trials for m in by_domain.values())

        return {
            "domains": {
                name: {
                    "success_rate": round(m.success_rate, 3),
                    "avg_latency": round(m.avg_latency, 2),
                    "avg_cost": round(m.avg_cost, 4),
                    "avg_quality": round(m.avg_quality, 3),
                    "trials": m.trials,
                }
                for name, m in by_domain.items()
            },
            "overall": {
                "success_rate": round(total_successes / max(1, total_trials), 3),
                "avg_cost": round(total_cost / max(1, total_trials), 4),
                "trials": total_trials,
            },
        }
