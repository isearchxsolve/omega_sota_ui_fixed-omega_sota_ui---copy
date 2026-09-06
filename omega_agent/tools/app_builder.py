"""app_builder.py — REMOVED.

This module previously contained `scaffold_crypto_trading_app` and `scaffold_web_app`,
which were hardcoded templates that produced an ETH/USDT trading UI regardless of the
user's actual goal. They have been deleted.

OMEGA generates all projects through:
  1. web_search  — gather real evidence about best tools, stack, libraries, patterns
  2. llm_generate_files — LLM reasons over that evidence and writes goal-specific files

There are no templates. There are no scaffolds. Every project is built from first principles
for the specific goal. This applies to every domain: CRM, data pipeline, CLI, API, dashboard,
game, whatever. The web search + LLM is the scaffold.

If you are reading this because a tool call to `scaffold_web_app` or
`scaffold_crypto_trading_app` returned nothing — that is correct. Those tools no longer
exist in the registry. The planner should use `llm_generate_files` after `web_search`.
"""


def register_app_builder_tools(registry) -> None:
    """No-op. scaffold_* tools have been removed. See module docstring."""
    pass
