"""Tests for execution progress checkpoints."""

from omega_agent.core.progress import RunProgress
from omega_agent.core.types import ExecutionContext


def test_run_progress_checkpoints():
    p = RunProgress()
    p.checkpoint("discovery", "Web search 1/3", 0.05, "query text")
    p.checkpoint("verify", "Build verify 2/5", 0.65, "npm ci && npm run build")
    assert p.fraction == 0.65
    assert "Web search" in p.format_log()
    assert "Build verify" in p.format_log()


def test_execution_context_checkpoint():
    ctx = ExecutionContext(goal="test")
    p = RunProgress()
    ctx.run_progress = p
    ctx.checkpoint("start", "Starting", 0.01)
    assert p.message == "Starting"
