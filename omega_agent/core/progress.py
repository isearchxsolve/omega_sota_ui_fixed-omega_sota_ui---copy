"""Live execution progress checkpoints for UI and logging."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RunProgress:
    """Collects checkpoint events and optionally pushes them to an async queue."""

    lines: List[str] = field(default_factory=list)
    fraction: float = 0.0
    message: str = "Starting…"
    phase: str = "init"
    _queue: Optional[asyncio.Queue] = field(default=None, repr=False)

    def attach_queue(self, queue: asyncio.Queue) -> None:
        self._queue = queue

    def checkpoint(
        self,
        phase: str,
        message: str,
        fraction: float,
        detail: str = "",
    ) -> None:
        self.phase = phase
        self.message = message
        self.fraction = max(0.0, min(1.0, fraction))
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {message}"
        if detail:
            line += f"\n    └ {detail}"
        self.lines.append(line)
        if self._queue is not None:
            try:
                self._queue.put_nowait(
                    {
                        "fraction": self.fraction,
                        "message": message,
                        "log": self.format_log(),
                        "phase": phase,
                    }
                )
            except asyncio.QueueFull:
                pass

    def format_log(self) -> str:
        return "\n".join(self.lines[-50:])

    def snapshot(self) -> Dict[str, Any]:
        return {
            "fraction": self.fraction,
            "message": self.message,
            "log": self.format_log(),
            "phase": self.phase,
        }
