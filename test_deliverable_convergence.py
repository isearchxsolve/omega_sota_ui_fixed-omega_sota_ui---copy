"""Unit tests for deliverable verify/learn/fix convergence."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from omega_agent.core.config import Config
from omega_agent.reflection.deliverable_convergence import (
    DeliverableConvergenceEngine,
    infer_verify_command,
    wants_deliverable_verify,
)
from omega_agent.reasoning.types import DynamicDomainProfile


def test_infer_verify_command_npm_ci_with_lockfile():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "package.json").write_text(
            json.dumps({"scripts": {"build": "vite build", "test": "vitest"}}),
            encoding="utf-8",
        )
        (root / "package-lock.json").write_text('{"lockfileVersion": 3}', encoding="utf-8")
        cmd = infer_verify_command(root)
        assert cmd.startswith("npm ci")
        assert "npm run build" in cmd
        assert "npm test" in cmd


def test_infer_verify_command_npm_with_test():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "package.json").write_text(
            json.dumps(
                {
                    "scripts": {
                        "build": "tsc -b && vite build",
                        "test": "vitest run",
                    }
                }
            ),
            encoding="utf-8",
        )
        cmd = infer_verify_command(root)
        assert cmd == "npm install && npm run build && npm test"


def test_infer_verify_command_npm_build_only():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "package.json").write_text(
            json.dumps({"scripts": {"build": "vite build"}}),
            encoding="utf-8",
        )
        cmd = infer_verify_command(root)
        assert cmd == "npm install && npm run build"
        assert "test" not in cmd


def test_infer_verify_command_python():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "requirements.txt").write_text("pytest\n", encoding="utf-8")
        cmd = infer_verify_command(root)
        assert "pip install" in cmd
        assert "pytest" in cmd


def test_wants_deliverable_verify_build_goal():
    profile = DynamicDomainProfile(
        domain="frontend",
        recommended_tools=["web_search"],
        quality_criteria=[],
    )
    assert wants_deliverable_verify(
        "Build a production-ready React trading app with Vite",
        profile,
        {},
    )


@pytest.mark.asyncio
async def test_converge_mock_shell_fail_then_fix_pass(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps({"scripts": {"build": "echo ok", "test": "echo test"}}),
        encoding="utf-8",
    )

    config = Config(use_mock_llm=False, deliverable_verify_max_retries=2, groq_api_key="test-key")

    orchestrator = MagicMock()
    orchestrator.invoke_json = AsyncMock(
        return_value=(
            {
                "strategy": "fix package",
                "root_cause": "missing dep",
                "files": [{"path": "fix.txt", "content": "ok"}],
                "patches": [],
            },
            0.0,
        )
    )

    call_count = 0

    async def fake_execute(tool_name, args, domain):
        nonlocal call_count
        if tool_name == "run_shell":
            call_count += 1
            if call_count == 1:
                return {"success": False, "stderr": "error TS2307", "stdout": ""}, 0.0
            return {"success": True, "stdout": "ok"}, 0.0
        if tool_name == "write_files":
            return {"success": True, "files_written": ["fix.txt"], "project_root": str(project)}, 0.0
        return {"success": True}, 0.0

    executor = MagicMock()
    executor.execute = AsyncMock(side_effect=fake_execute)

    engine = DeliverableConvergenceEngine(config, orchestrator, executor)
    profile = DynamicDomainProfile(domain="frontend", recommended_tools=["llm_generate_files"])
    task_results = {
        "materialize_1": {"success": True, "project_root": str(project), "files_written": ["package.json"]}
    }

    results, meta, cost = await engine.converge(
        "Build app", profile, "ws", str(tmp_path), task_results, lambda _: None
    )
    assert meta["build_verified"] is True
    assert meta["verify_attempts"] >= 2
    assert call_count >= 2


@pytest.mark.asyncio
async def test_converge_skips_when_dag_verify_passed(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "package.json").write_text('{"scripts": {"build": "true"}}', encoding="utf-8")

    config = Config(deliverable_verify_max_retries=5, groq_api_key="x", use_mock_llm=False)
    executor = MagicMock()
    engine = DeliverableConvergenceEngine(config, MagicMock(), executor)
    profile = DynamicDomainProfile(domain="x")
    task_results = {
        "materialize_1": {"project_root": str(project), "files_written": ["package.json"]},
        "verify_deliverable": {"success": True, "command": "npm install && npm run build"},
    }

    _, meta, _ = await engine.converge("g", profile, "ws", str(tmp_path), task_results, lambda _: None)
    assert meta["build_verified"] is True
    assert meta.get("skip_reason") == "dag_verify_already_passed"
    executor.execute.assert_not_called()


def test_wants_deliverable_verify_research_only():
    profile = DynamicDomainProfile(
        domain="research",
        recommended_tools=["web_search"],
        quality_criteria=["evidence", "citations"],
    )
    assert not wants_deliverable_verify(
        "Summarize best practices for delta-neutral options",
        profile,
        {},
    )
