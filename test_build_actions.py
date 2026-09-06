"""Build goals must use workspace tools and deliver files/zip — not advice only."""

import pytest
from pathlib import Path

from omega_agent import OmegaAgent, Config
from omega_agent.reasoning.build import is_app_build_goal
from omega_agent.reasoning.delivery import profile_wants_deliverables


GOAL = (
    "Build a production-ready crypto trading app with real-time Web3 charts, "
    "MetaMask wallet integration, dark/light mode toggle, and order book visualization. "
    "Include SOTA UI/UX matching emergent.ai standards."
)


def test_app_build_goal_detection():
    assert is_app_build_goal(GOAL)


@pytest.mark.asyncio
async def test_crypto_app_workspace_delivery(tmp_path):
    ws_root = tmp_path / "workspaces"
    config = Config(
        use_mock_llm=True,
        log_level="WARNING",
        workspace_root=str(ws_root),
        max_total_time=180,
    )
    agent = OmegaAgent(config=config)
    result = await agent.run(GOAL, max_time=180)

    assert result.success
    assert result.decision is not None
    profile = result.metadata.get("dynamic_profile", {})
    assert profile_wants_deliverables(
        profile.get("recommended_tools", []),
        profile.get("quality_criteria", []),
    )

    root = result.decision.risk_params.get("project_root")
    assert root
    project = Path(root)
    assert project.is_dir()
    assert (project / "package.json").is_file()
    assert (project / "src" / "App.tsx").is_file()

    assert result.decision.action in (
        "deliver_artifacts",
        "project_written",
        "scaffold_deployed",
        "deliverable_verify_failed",
    )
    assert "DELIVERABLE" in result.output
    assert "Call the MetaMask" not in result.output

    zip_path = result.decision.risk_params.get("archive_path")
    if zip_path:
        assert Path(zip_path).is_file()
