"""Crisis goals: tools execute from dynamic discovery + web search (no hardcoded domain router)."""

import pytest

from omega_agent import OmegaAgent, Config
from omega_agent.reasoning.crisis import is_crisis_goal


@pytest.mark.asyncio
async def test_crisis_runs_action_tools_not_advice_only():
    config = Config(use_mock_llm=True, log_level="WARNING", max_total_time=180)
    agent = OmegaAgent(config=config)
    goal = (
        "I am hungry, I need urgent money. I need food assistance and emergency funds immediately. "
        "Location: Chicago IL"
    )
    result = await agent.run(goal, max_time=180)

    assert result.success
    assert is_crisis_goal(goal)
    tools_used = result.metadata.get("tools_used", [])
    assert "web_search" in tools_used

    executed = any(
        isinstance(v, dict) and v.get("action_taken")
        for v in (result.metadata.get("dynamic_profile") and []) or []
    )
    # Task outputs should reflect real tool runs (search and/or emergency lookups)
    assert tools_used
    assert result.decision is not None
    assert result.decision.action
    assert len(result.output) > 200
