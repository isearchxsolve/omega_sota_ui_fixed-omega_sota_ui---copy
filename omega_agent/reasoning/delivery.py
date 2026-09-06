"""Assemble deliverable outcomes from workspace tool results — no domain hardcoding."""

from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from omega_agent.core.types import ActionDecision

DELIVERABLE_TOOLS = frozenset(
    {
        "write_files",
        "modify_file",
        "run_shell",
        "archive_zip",
        "llm_generate_files",
    }
)

# Emergency tools produce `executed_actions` — they ARE action-takers, not suggesters.
# Including them here prevents _finalize_deliverables from short-circuiting.
EMERGENCY_ACTION_TOOLS = frozenset(
    {
        "emergency_food_lookup",
        "emergency_cash_lookup",
        "emergency_assistance_programs",
        "emergency_gig_income",
    }
)

# Emergency domain keywords — trigger action-taking mode instead of deliverable mode
EMERGENCY_DOMAIN_SIGNALS = frozenset(
    {"emergency", "hunger", "hungry", "food", "starving", "cash", "money", "funds",
     "homeless", "shelter", "crisis", "urgent", "immediately", "assistance"}
)


def find_tool_results(task_results: Dict[str, Any], tool_names: frozenset) -> List[Dict[str, Any]]:
    found = []
    for value in task_results.values():
        if isinstance(value, dict) and value.get("action_taken"):
            found.append(value)
    return found


def collect_deliverable_artifacts(task_results: Dict[str, Any]) -> Dict[str, Any]:
    artifacts: Dict[str, Any] = {
        "project_root": None,
        "files_written": [],
        "archive_path": None,
        "shell_runs": [],
        "commands_suggested": [],
        "zip_error": None,
    }

    for key, result in task_results.items():
        if isinstance(result, dict) and "finalize_zip" in str(key) and not result.get("success"):
            artifacts["zip_error"] = result.get("error")

    for key, result in task_results.items():
        if isinstance(result, dict) and result.get("archive_path"):
            artifacts["archive_path"] = result["archive_path"]

    for result in find_tool_results(task_results, DELIVERABLE_TOOLS):
        if result.get("project_root"):
            artifacts["project_root"] = result["project_root"]
        if result.get("files_written"):
            artifacts["files_written"].extend(result["files_written"])
        if result.get("archive_path"):
            artifacts["archive_path"] = result["archive_path"]
        if result.get("command"):
            artifacts["shell_runs"].append(
                {
                    "command": result["command"],
                    "success": result.get("success"),
                    "returncode": result.get("returncode"),
                }
            )
        for cmd in result.get("post_install_commands") or []:
            artifacts["commands_suggested"].append(cmd)

    artifacts["file_count"] = len(artifacts["files_written"])
    return artifacts


def format_deliverable_manifest(artifacts: Dict[str, Any]) -> str:
    lines = ["## DELIVERABLE", ""]
    if artifacts.get("project_root"):
        lines.append(f"**Project:** `{artifacts['project_root']}`")
    if artifacts.get("archive_path"):
        lines.append(f"**Download zip:** `{artifacts['archive_path']}`")
    if artifacts.get("file_count"):
        lines.append(f"**Files written:** {artifacts['file_count']}")
    if artifacts.get("build_verified") is True:
        lines.append("")
        lines.append("**Build verified:** install + build + test passed")
    elif artifacts.get("build_verified") is False:
        lines.append("")
        lines.append(
            f"**Build verification failed** after {artifacts.get('verify_attempts', 0)} attempt(s)"
        )
    if artifacts.get("shell_runs"):
        lines.append("")
        lines.append("### Commands executed")
        for run in artifacts["shell_runs"]:
            status = "ok" if run.get("success") else "failed"
            lines.append(f"- `{run.get('command')}` ({status})")
    suggested = artifacts.get("commands_suggested") or []
    if suggested:
        lines.append("")
        lines.append("### Suggested commands")
        for cmd in suggested[:5]:
            lines.append(f"```bash\n{cmd}\n```")
    if artifacts.get("project_root") and not artifacts.get("archive_path"):
        lines.append("")
        zip_err = artifacts.get("zip_error")
        if zip_err:
            lines.append(f"**Zip failed:** {zip_err}")
        else:
            lines.append("Zip was not produced for this run (check logs).")
    return "\n".join(lines)


def enrich_deliverable_decision(
    decision: "ActionDecision",
    task_results: Dict[str, Any],
    goal: str,
) -> "ActionDecision":
    artifacts = collect_deliverable_artifacts(task_results)
    if not artifacts.get("project_root") and not artifacts.get("archive_path"):
        return decision

    manifest = format_deliverable_manifest(artifacts)
    decision.action = "deliver_artifacts" if artifacts.get("archive_path") else "project_written"
    decision.immediate_actions = []

    if artifacts.get("archive_path"):
        decision.immediate_actions.append(
            {
                "action": "download",
                "title": "Download project zip",
                "url": f"file://{artifacts['archive_path']}",
                "detail": artifacts["archive_path"],
                "priority": 1,
            }
        )
    if artifacts.get("project_root"):
        decision.immediate_actions.append(
            {
                "action": "open_folder",
                "title": "Open project folder",
                "detail": artifacts["project_root"],
                "priority": 2,
            }
        )

    decision.next_steps = [
        f"Project at `{artifacts.get('project_root')}`",
    ]
    if artifacts.get("archive_path"):
        decision.next_steps.insert(0, f"Deliver zip: `{artifacts['archive_path']}`")

    if not decision.risk_params:
        decision.risk_params = {}
    verify = task_results.get("deliverable_verify")
    if isinstance(verify, dict):
        artifacts["build_verified"] = verify.get("build_verified")
        artifacts["verify_attempts"] = verify.get("verify_attempts", 0)

    decision.risk_params.update(
        {
            "project_root": artifacts.get("project_root"),
            "archive_path": artifacts.get("archive_path"),
            "files_written": artifacts.get("file_count", 0),
            "build_mode": "workspace_deliverable",
            "build_verified": artifacts.get("build_verified"),
            "verify_attempts": artifacts.get("verify_attempts", 0),
        }
    )
    if artifacts.get("build_verified"):
        decision.confidence = max(decision.confidence, 0.95)
    elif artifacts.get("build_verified") is False and artifacts.get("verify_attempts", 0) > 0:
        decision.confidence = min(decision.confidence, 0.55)
        decision.action = "deliverable_verify_failed"
    else:
        decision.confidence = max(decision.confidence, 0.9 if artifacts.get("file_count", 0) > 3 else 0.75)
    decision.rationale = (
        f"{manifest}\n\n### Summary\n"
        f"OMEGA used workspace tools (write / shell / zip) for: {goal[:200]}\n\n"
        f"{decision.rationale[:1200] if decision.rationale else ''}"
    )
    return decision


def profile_wants_deliverables(
    recommended_tools: List[str],
    quality_criteria: List[str],
    goal: str = "",
    web_context: Optional[Dict[str, Any]] = None,
    catalog: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    if DELIVERABLE_TOOLS.intersection(recommended_tools):
        return True
    # Emergency tools are action-takers — allow finalize path but skip zip/write_files
    if EMERGENCY_ACTION_TOOLS.intersection(recommended_tools):
        return True
    blob = " ".join(quality_criteria).lower()
    if any(k in blob for k in ("file", "zip", "artifact", "deliver", "runnable", "workspace")):
        return True
    if goal and catalog:
        from omega_agent.reasoning.evidence import rank_tools_by_evidence

        ranked = rank_tools_by_evidence("dynamic", web_context or {}, catalog, top_k=8, goal=goal)
        if DELIVERABLE_TOOLS.intersection(ranked):
            return True
    return False


def is_emergency_goal(goal: str, domain: str = "") -> bool:
    """Return True when the goal is clearly an emergency humanitarian request."""
    text = (goal + " " + domain).lower()
    matches = sum(1 for s in EMERGENCY_DOMAIN_SIGNALS if s in text)
    return matches >= 2
