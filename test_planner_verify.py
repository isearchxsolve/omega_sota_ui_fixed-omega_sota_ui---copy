"""Planner DAG ordering for verify and zip."""

from omega_agent.core.config import Config
from omega_agent.core.types import ExecutionContext
from omega_agent.core.orchestrator import ModelOrchestrator
from omega_agent.reasoning.planner import DynamicPlanner
from omega_agent.reasoning.types import DynamicDomainProfile
from omega_agent.tools.registry import ToolRegistry
from omega_agent.tools.stdlib import register_all_tools


BUILD_GOAL = "Build a production-ready React trading app with Vite and tests"


def test_evidence_plan_defers_verify_and_zip_to_finalize():
    """Default: npm verify + zip run in finalize, not blocking the DAG."""
    config = Config(use_mock_llm=False, groq_api_key="test-key", deliverable_verify_in_dag=False)
    registry = ToolRegistry()
    register_all_tools(registry)
    planner = DynamicPlanner(config, ModelOrchestrator(config), registry)
    catalog = {t["name"]: t for t in registry.get_catalog_for_llm()}

    profile = DynamicDomainProfile(
        domain="frontend",
        recommended_tools=["web_search", "llm_generate_files", "run_shell", "archive_zip"],
        quality_criteria=["artifacts_delivered", "runnable_scaffold"],
    )
    ctx = ExecutionContext(goal=BUILD_GOAL, workspace_id="test-ws", workspace_root="./outputs/workspaces")

    tasks = planner._plan_from_evidence(BUILD_GOAL, profile, catalog, {}, ctx)
    ids = [t.id for t in tasks]
    assert "verify_deliverable" not in ids
    assert "deliver_zip" not in ids
    assert any(t.tool_name.startswith("scaffold_") or t.tool_name == "llm_generate_files" for t in tasks)


def test_evidence_plan_includes_dag_verify_when_enabled():
    config = Config(
        use_mock_llm=False,
        groq_api_key="test-key",
        deliverable_verify_in_dag=True,
    )
    registry = ToolRegistry()
    register_all_tools(registry)
    planner = DynamicPlanner(config, ModelOrchestrator(config), registry)
    catalog = {t["name"]: t for t in registry.get_catalog_for_llm()}

    profile = DynamicDomainProfile(
        domain="frontend",
        recommended_tools=["web_search", "llm_generate_files", "run_shell", "archive_zip"],
        quality_criteria=["artifacts_delivered", "runnable_scaffold"],
    )
    ctx = ExecutionContext(goal=BUILD_GOAL, workspace_id="test-ws", workspace_root="./outputs/workspaces")

    tasks = planner._plan_from_evidence(BUILD_GOAL, profile, catalog, {}, ctx)
    ids = [t.id for t in tasks]
    assert "verify_deliverable" in ids
    zip_task = next(t for t in tasks if t.id == "deliver_zip")
    assert "verify_deliverable" in zip_task.dependencies
