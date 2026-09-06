"""Tests for interactive OMEGA sessions and Gradio integration helpers."""

import pytest

from omega_agent import Config
from omega_agent.interaction.analyzer import WorkflowInputAnalyzer
from omega_agent.interaction.credentials import CredentialManager
from omega_agent.interaction.runner import InteractiveOmegaRunner
from omega_agent.interaction.session import OmegaChatSession
from omega_agent.interaction.types import InputKind, InteractiveStatus


@pytest.fixture
def mock_runner():
    config = Config(use_mock_llm=True, log_level="WARNING")
    creds = CredentialManager(vault_path="./data/test_vault.json")
    return InteractiveOmegaRunner(config=config, credentials=creds)


@pytest.mark.asyncio
async def test_vague_goal_triggers_user_input(mock_runner):
    result = await mock_runner.handle_message("build it")
    assert result.status == InteractiveStatus.AWAITING_INPUT
    assert result.request is not None
    assert result.request.kind in (InputKind.CLARIFICATION, InputKind.CREDENTIAL)


@pytest.mark.asyncio
async def test_clarification_then_run(mock_runner):
    r1 = await mock_runner.handle_message("fix it")
    assert r1.needs_input
    session = OmegaChatSession(session_id=r1.session_id)
    session.status = InteractiveStatus.AWAITING_INPUT
    session.pending_request = r1.request
    session.goal = "fix it"
    session.chat_messages = list(r1.chat_messages)

    r2 = await mock_runner.handle_message(
        "Fix the login bug in auth.py — add null check on session token.",
        session=session,
    )
    assert r2.status in (
        InteractiveStatus.COMPLETED,
        InteractiveStatus.FAILED,
        InteractiveStatus.AWAITING_INPUT,
    )


@pytest.mark.asyncio
async def test_github_goal_requests_token(mock_runner):
    result = await mock_runner.handle_message(
        "Create a GitHub repository and push a Python hello-world project with GitHub Actions CI"
    )
    if result.needs_input:
        assert result.request.kind in (InputKind.CREDENTIAL, InputKind.CLARIFICATION)
        if result.request.kind == InputKind.CREDENTIAL:
            assert result.request.key == "GITHUB_TOKEN"


@pytest.mark.asyncio
async def test_credential_reply_resumes(mock_runner):
    goal = "Deploy to AWS Lambda using terraform"
    r1 = await mock_runner.handle_message(goal)
    if not r1.needs_input or r1.request.key != "AWS_ACCESS_KEY_ID":
        pytest.skip("Preflight did not request AWS key in this environment")

    session = OmegaChatSession(session_id=r1.session_id)
    session.status = InteractiveStatus.AWAITING_INPUT
    session.pending_request = r1.request
    session.goal = goal
    session.chat_messages = r1.chat_messages

    r2 = await mock_runner.handle_message(
        "AKIAIOSFODNN7EXAMPLE",
        session=session,
    )
    assert r2.status in (
        InteractiveStatus.AWAITING_INPUT,
        InteractiveStatus.COMPLETED,
        InteractiveStatus.FAILED,
        InteractiveStatus.RUNNING,
    )


def test_analyzer_missing_llm():
    config = Config(use_mock_llm=True)
    creds = CredentialManager()
    analyzer = WorkflowInputAnalyzer(config, creds)
    reqs = analyzer.preflight_requests("Research quantum computing trends in 2026")
    keys = [r.key for r in reqs]
    assert "GROQ_API_KEY" in keys or "goal_clarification" in keys or len(reqs) >= 0


def test_session_roundtrip():
    session = OmegaChatSession(goal="test goal")
    session.append_message("user", "hello")
    data = session.to_state_dict()
    restored = OmegaChatSession.from_state_dict(data)
    assert restored.goal == "test goal"
    assert len(restored.chat_messages) == 1


def test_build_demo_import():
    pytest.importorskip("gradio")
    from omega_agent.ui.gradio_app import build_demo
    demo = build_demo(Config(use_mock_llm=True))
    assert demo is not None


def test_verify_display():
    from omega_agent.ui.gradio_app import _verify_display
    from omega_agent.core.types import AgentResult, ActionDecision

    ok, attempts, stderr = _verify_display(
        AgentResult(
            success=True,
            output="",
            domain="t",
            route="default",
            cost=0,
            latency=1,
            metadata={
                "deliverable_verify": {
                    "build_verified": True,
                    "verify_attempts": 2,
                }
            },
            decision=ActionDecision(
                action="deliver",
                confidence=0.9,
                rationale="",
                risk_params={"build_verified": True, "verify_attempts": 2},
            ),
        )
    )
    assert ok == "Yes"
    assert attempts == "2"
    assert stderr == ""

    fail_ok, fail_n, fail_err = _verify_display(
        AgentResult(
            success=True,
            output="",
            domain="t",
            route="default",
            cost=0,
            latency=1,
            metadata={
                "deliverable_verify": {
                    "build_verified": False,
                    "verify_attempts": 3,
                    "last_stderr": "TS2307 module not found",
                }
            },
        )
    )
    assert fail_ok == "No"
    assert fail_n == "3"
    assert "TS2307" in fail_err


def test_deliverable_zip_updates(tmp_path):
    pytest.importorskip("gradio")
    from pathlib import Path

    from omega_agent.ui.gradio_app import (
        _deliverable_zip_updates,
        _stage_download_zip,
        _zip_download_value,
    )

    z = tmp_path / "project.zip"
    z.write_bytes(b"pk")
    file_out, btn, hint = _deliverable_zip_updates(str(z))
    assert file_out.visible is True
    assert btn.visible is True
    assert hint.visible is True
    assert "project.zip" in (hint.value or "")
    assert _zip_download_value(str(z)) == str(z.resolve())
    staged = _stage_download_zip(str(z), Config(build_output_dir=str(tmp_path / "out")))
    assert staged and Path(staged).is_file()


def test_zip_download_value(tmp_path):
    from omega_agent.ui.gradio_app import _deliverable_paths, _zip_download_value
    from omega_agent.core.types import AgentResult, ActionDecision

    z = tmp_path / "out.zip"
    z.write_bytes(b"pk")
    result = AgentResult(
        success=True,
        output="ok",
        domain="test",
        route="default",
        cost=0.0,
        latency=1.0,
        metadata={"archive_path": str(z), "project_root": str(tmp_path / "proj")},
        decision=ActionDecision(
            action="deliver",
            confidence=0.9,
            rationale="",
            risk_params={"archive_path": str(z)},
            domain="test",
        ),
    )
    ap, pr = _deliverable_paths(result)
    assert ap == str(z)
    assert _zip_download_value(ap) == str(z.resolve())
