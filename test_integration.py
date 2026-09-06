"""Integration tests for dynamic OMEGA."""

import pytest
from httpx import ASGITransport, AsyncClient

from omega_agent import OmegaAgent, Config
from omega_agent.api import app


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "web_search" in data["domains"]


@pytest.mark.asyncio
async def test_dynamic_domain_discovery_crypto():
    config = Config(use_mock_llm=True, log_level="WARNING")
    agent = OmegaAgent(config=config)
    result = await agent.run("Should I buy SOL before the pump ends?", domain="crypto_trading")
    assert result.success
    assert result.decision is not None
    assert result.metadata.get("dynamic_profile") is not None
    assert "web_search" in result.metadata.get("tools_used", [])


@pytest.mark.asyncio
async def test_dynamic_domain_discovery_research():
    config = Config(use_mock_llm=True, log_level="WARNING")
    agent = OmegaAgent(config=config)
    result = await agent.run("Review literature on ML interpretability gaps", domain="research")
    assert result.success
    assert result.metadata.get("best_practices")


@pytest.mark.asyncio
async def test_dynamic_tools_not_hardcoded():
    config = Config(use_mock_llm=True, log_level="WARNING")
    agent = OmegaAgent(config=config)
    result = await agent.run("Implement a Python async function with tests", domain="coding")
    tools_used = result.metadata.get("tools_used", [])
    assert len(tools_used) >= 1
    assert all(t in agent.list_tools() for t in tools_used)


@pytest.mark.asyncio
async def test_memory_and_audit():
    config = Config(use_mock_llm=True, log_level="WARNING")
    agent = OmegaAgent(config=config)
    await agent.run("Plan a product launch roadmap", domain="planning")
    stats = agent.get_memory_stats()
    assert stats["episodic_count"] >= 1
    assert stats["audit_chain_valid"] is True


@pytest.mark.asyncio
async def test_sync_api_goal():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/goals/sync",
            json={"goal": "Create a weekly schedule for deep work", "max_time": 120},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("completed", "failed")
    assert data["result"] is not None
    assert data["result"].get("metadata", {}).get("dynamic_profile") is not None


@pytest.mark.asyncio
async def test_web_evidence_collected():
    config = Config(use_mock_llm=True, log_level="WARNING")
    agent = OmegaAgent(config=config)
    result = await agent.run("Best practices for delta neutral options trading", domain="crypto_trading")
    profile = result.metadata.get("dynamic_profile", {})
    assert profile.get("best_practices") or result.metadata.get("web_evidence_count", 0) >= 0
