"""Goal analysis utilities for build/create/implement goals.

No domain-specific templates, no hardcoded stacks, no scaffold tool references.
The only allowed output artifacts from a build goal flow through:
  web_search -> llm_generate_files -> run_shell -> (verify/fix loop)
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from omega_agent.core.types import ActionDecision

# Keywords that signal the user wants a deliverable artifact written to disk
BUILD_KEYWORDS = (
    "build", "create", "implement", "develop", "write", "generate",
    "make", "scaffold", "set up", "setup", "bootstrap", "initialize",
    "produce", "ship", "deploy", "publish",
)

# Keywords that signal the deliverable is a runnable application or codebase
APP_SIGNALS = (
    "app", "application", "service", "api", "cli", "tool", "dashboard",
    "interface", "ui", "frontend", "backend", "full-stack", "fullstack",
    "website", "platform", "system", "pipeline", "bot", "agent", "server",
    "microservice", "library", "package", "module", "plugin", "extension",
)


def is_app_build_goal(goal: str) -> bool:
    """True when the goal implies producing a runnable codebase or application."""
    text = goal.lower()
    has_build = any(k in text for k in BUILD_KEYWORDS)
    has_app = any(k in text for k in APP_SIGNALS)
    return has_build and has_app


def slug_from_goal(goal: str) -> str:
    words = re.findall(r"[a-z0-9]+", goal.lower())[:6]
    base = "-".join(w for w in words if w not in ("a", "the", "with", "and", "for", "an"))[:40]
    return base or "omega-project"


def discovery_queries_from_goal(goal: str) -> List[str]:
    """Produce targeted web search queries that gather real stack/tooling evidence.

    Queries are derived entirely from the goal. No domain assumptions.
    The aim is to surface: best libraries, architectural patterns, getting-started docs,
    and real implementation examples for whatever the user is actually building.
    """
    g = goal.strip()
    # Extract the core subject (what is being built) — first ~60 chars is usually enough
    subject = g[:80]

    return [
        f"{subject} best framework library 2024 2025",
        f"{subject} architecture patterns production",
        f"{subject} implementation tutorial getting started",
        f"{subject} open source example GitHub",
        f"{subject} best practices pitfalls performance",
    ]


def format_build_result(build_result: Dict[str, Any]) -> str:
    """Format a successful llm_generate_files result into a human-readable summary."""
    root = build_result.get("project_root", "")
    files = build_result.get("files_written", [])
    summary = build_result.get("llm_summary", "")
    post_cmds = build_result.get("post_install_commands", [])

    lines = [
        "## BUILT FOR YOU",
        "",
        f"**Project path:** `{root}`",
        f"**Files written:** {len(files)}",
        f"**Evidence snippets used:** {build_result.get('evidence_snippets_used', 'N/A')}",
        "",
    ]

    if summary:
        lines += ["### What was built and why", summary, ""]

    if post_cmds:
        lines += ["### Run it", "```bash", f"cd {root}"]
        lines += post_cmds
        lines += ["```", ""]

    lines += ["### Files generated"]
    for f in files[:25]:
        lines.append(f"- `{f}`")
    if len(files) > 25:
        lines.append(f"- … and {len(files) - 25} more files")

    return "\n".join(lines)


def enrich_build_decision(
    decision: "ActionDecision",
    build_result: Dict[str, Any],
    goal: str,
) -> "ActionDecision":
    """Enrich an ActionDecision with build result metadata."""
    if not build_result.get("success"):
        decision.action = "build_failed"
        decision.confidence = 0.3
        decision.rationale = (
            f"Build failed: {build_result.get('error', 'unknown error')}\n\n"
            f"{decision.rationale[:800]}"
        )
        return decision

    manifest = format_build_result(build_result)
    post_cmds = build_result.get("post_install_commands", [])

    decision.action = "deliverable_written"
    decision.immediate_actions = []
    for i, cmd in enumerate(post_cmds[:4], 1):
        decision.immediate_actions.append({
            "action": "run_terminal",
            "title": cmd,
            "detail": f"cd {build_result.get('project_root', '.')} && {cmd}",
            "priority": i,
        })

    decision.next_steps = [
        f"Open `{build_result.get('project_root')}` in your editor",
        *post_cmds[:3],
        "Read the generated README for project-specific instructions",
    ]

    if not decision.risk_params:
        decision.risk_params = {}
    decision.risk_params["project_root"] = build_result.get("project_root")
    decision.risk_params["files_written"] = len(build_result.get("files_written", []))
    decision.risk_params["generation_mode"] = build_result.get("generation_mode", "llm_evidence_driven")
    decision.confidence = max(decision.confidence, 0.88)
    decision.rationale = (
        f"{manifest}\n\n"
        f"### Execution summary\n"
        f"OMEGA reasoned over web evidence and wrote source files to disk for: {goal[:200]}\n"
        f"Generation mode: {build_result.get('generation_mode', 'llm_evidence_driven')}\n"
        f"This is not a suggestion-only plan — open the project folder and run the commands above."
    )
    return decision
