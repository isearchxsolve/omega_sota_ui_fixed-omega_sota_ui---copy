"""Thread-safe progress queue for UI streaming (Gradio, FastAPI SSE, etc.)."""

from __future__ import annotations

import queue as stdlib_queue
from typing import Any, Dict, List, Optional

from omega_agent.core.progress import RunProgress


class ThreadSafeProgress(RunProgress):
    """RunProgress that pushes checkpoint events to a threading.Queue."""

    def __init__(self) -> None:
        super().__init__()
        self._tqueue: stdlib_queue.Queue = stdlib_queue.Queue()

    def checkpoint(
        self,
        phase: str,
        message: str,
        fraction: float,
        detail: str = "",
    ) -> None:
        super().checkpoint(phase, message, fraction, detail)
        try:
            self._tqueue.put_nowait(
                {
                    "fraction": self.fraction,
                    "message": message,
                    "log": self.format_log(),
                    "phase": phase,
                    "done": False,
                }
            )
        except stdlib_queue.Full:
            pass

    def mark_done(self) -> None:
        self._tqueue.put_nowait({"done": True})

    def drain(self) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        while True:
            try:
                events.append(self._tqueue.get_nowait())
            except stdlib_queue.Empty:
                break
        return events
