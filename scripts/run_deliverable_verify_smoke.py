#!/usr/bin/env python3
"""
Smoke-test deliverable verify loop with a real LLM (requires GROQ_API_KEY or other provider).

Usage:
  set GROQ_API_KEY=...
  python scripts/run_deliverable_verify_smoke.py
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from omega_agent import Config, OmegaAgent


GOAL = (
    "Build a minimal Vite + React todo list app with TypeScript. "
    "Include package.json scripts for build and a simple vitest test."
)


async def main() -> int:
    config = Config(use_mock_llm=False, log_level="INFO")
    if not config.has_llm_credentials():
        print("No LLM credentials. Set GROQ_API_KEY (or OPENAI/ANTHROPIC) and retry.")
        return 1

    agent = OmegaAgent(config=config)
    result = await agent.run(GOAL, max_time=600)

    verify = (result.metadata or {}).get("deliverable_verify") or {}
    print("\n=== OMEGA deliverable verify smoke ===")
    print(f"success: {result.success}")
    print(f"action: {result.decision.action if result.decision else 'n/a'}")
    print(f"build_verified: {verify.get('build_verified')}")
    print(f"verify_attempts: {verify.get('verify_attempts')}")
    print(f"verify_command: {verify.get('verify_command')}")
    print(f"strategies: {verify.get('strategies')}")
    if verify.get("last_stderr"):
        print(f"last_stderr (truncated): {verify.get('last_stderr')[:500]}")
    print(json.dumps(verify, indent=2)[:2000])

    return 0 if verify.get("build_verified") else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
