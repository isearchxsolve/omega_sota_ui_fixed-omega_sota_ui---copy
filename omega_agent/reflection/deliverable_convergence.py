"""Verify → fail → learn → fix → re-verify loop for workspace deliverables."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from omega_agent.core.config import Config
from omega_agent.core.orchestrator import ModelOrchestrator
from omega_agent.core.types import ExecutionContext
from omega_agent.reasoning.build import is_app_build_goal
from omega_agent.reasoning.delivery import profile_wants_deliverables
from omega_agent.reasoning.types import DynamicDomainProfile
from omega_agent.tools.executor import ToolExecutor

logger = logging.getLogger("omega_agent.reflection.deliverable_convergence")

FIX_SYSTEM = """You are OMEGA Build Fixer. A project failed verification (build/test).
Analyze the error, reason about the root cause, and produce a precise fix.

Return JSON ONLY:
{
  "strategy": "one sentence describing the new approach — must differ from all prior attempts",
  "root_cause": "exact diagnosis: what failed and why",
  "web_search_queries": ["optional: 1-3 queries to search for the error or solution"],
  "files": [{"path": "relative/path", "content": "complete corrected file content"}],
  "patches": [{"path": "rel/path", "old_string": "exact substring", "new_string": "replacement"}]
}

Rules:
- Read the FULL stderr/stdout. The error message is ground truth — do not guess around it.
- Prefer minimal patches for small errors; provide full files for structural issues.
- Fix the ACTUAL error: missing dependencies in package.json, wrong import paths, type errors,
  missing config keys, incompatible library versions, etc.
- Never repeat a strategy that already failed (PRIOR STRATEGIES lists them).
- If the error suggests a library version conflict, fix the version in package.json or requirements.txt.
- If the error is an import failure, fix the import or add the missing dependency.
- If the error is a type error, fix the types — do not suppress with any-casts unless unavoidable.
- Paths are relative to project root; no .. segments.
- web_search_queries is optional but recommended when the error is ambiguous.
"""


def infer_verify_command(project_root: Path) -> Optional[str]:
    """Pick install + build + test command from project layout."""
    root = project_root.resolve()
    pkg = root / "package.json"
    if pkg.is_file():
        scripts = {}
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
        except json.JSONDecodeError:
            pass
        lock = root / "package-lock.json"
        shrink = root / "npm-shrinkwrap.json"
        parts = ["npm ci"] if lock.is_file() or shrink.is_file() else ["npm install"]
        if scripts.get("build"):
            parts.append("npm run build")
        elif scripts.get("compile"):
            parts.append("npm run compile")
        if scripts.get("test"):
            parts.append("npm test")
        return " && ".join(parts)

    if (root / "pyproject.toml").is_file() or (root / "setup.py").is_file():
        parts = []
        if (root / "requirements.txt").is_file():
            parts.append("pip install -r requirements.txt")
        elif (root / "pyproject.toml").is_file():
            parts.append("pip install -e .")
        parts.append("python -m pytest -q")
        return " && ".join(parts) if parts else "python -m pytest -q"

    if (root / "requirements.txt").is_file():
        return "pip install -r requirements.txt && python -m pytest -q"

    if (root / "Cargo.toml").is_file():
        return "cargo build && cargo test"

    return None


def wants_deliverable_verify(
    goal: str,
    profile: DynamicDomainProfile,
    task_results: Dict[str, Any],
    catalog: Optional[List[Dict[str, Any]]] = None,
    web_context: Optional[Dict[str, Any]] = None,
) -> bool:
    """Whether to run the verify/learn/fix convergence loop."""
    if is_app_build_goal(goal):
        return True
    if profile_wants_deliverables(
        profile.recommended_tools,
        profile.quality_criteria,
        goal=goal,
        web_context=web_context,
        catalog=catalog,
    ):
        return True
    for value in task_results.values():
        if isinstance(value, dict) and value.get("files_written"):
            root = value.get("project_root")
            if root and infer_verify_command(Path(root)):
                return True
    return False


def _project_tree_summary(root: Path, max_files: int = 35) -> str:
    if not root.is_dir():
        return "(empty project)"
    lines: List[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not any(p in path.parts for p in (".git", "node_modules", "dist", "__pycache__")):
            rel = path.relative_to(root).as_posix()
            lines.append(rel)
            if len(lines) >= max_files:
                lines.append("…")
                break
    return "\n".join(lines) or "(no files)"


def _read_files_for_context(root: Path, stderr: str, max_chars: int = 12000) -> str:
    """Include contents of files mentioned in errors or key config files."""
    priority_names = {
        "package.json",
        "tsconfig.json",
        "vite.config.ts",
        "pyproject.toml",
        "requirements.txt",
    }
    candidates: List[Path] = []
    for name in priority_names:
        p = root / name
        if p.is_file():
            candidates.append(p)

    for match in re.finditer(r"([\w./\\-]+\.(?:tsx?|jsx?|py|json|toml))", stderr):
        rel = match.group(1).replace("\\", "/").lstrip("./")
        p = root / rel
        if p.is_file() and p not in candidates:
            candidates.append(p)

    blocks: List[str] = []
    used = 0
    for path in candidates[:12]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        chunk = f"### {rel}\n```\n{text[:2500]}\n```\n"
        if used + len(chunk) > max_chars:
            break
        blocks.append(chunk)
        used += len(chunk)
    return "\n".join(blocks) or "(no file context)"


class DeliverableConvergenceEngine:
    """Materialize → verify → learn → fix → verify until pass or max attempts."""

    def __init__(
        self,
        config: Config,
        orchestrator: ModelOrchestrator,
        tool_executor: ToolExecutor,
    ):
        self.config = config
        self.orchestrator = orchestrator
        self.tool_executor = tool_executor

    async def converge(
        self,
        goal: str,
        profile: DynamicDomainProfile,
        workspace_id: str,
        output_base: str,
        task_results: Dict[str, Any],
        cost_callback,
        tenant_id: str = "default",
        ctx: Optional[ExecutionContext] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], float]:
        """
        Run verify/fix loop. Returns (updated task_results, meta, total_cost).
        meta keys: build_verified, verify_attempts, last_stderr, strategies
        """
        project_root = self._resolve_project_root(
            task_results, workspace_id, output_base, tenant_id=tenant_id
        )
        meta: Dict[str, Any] = {
            "build_verified": False,
            "verify_attempts": 0,
            "strategies": [],
            "last_stderr": "",
            "last_stdout": "",
        }
        total_cost = 0.0

        if not project_root:
            meta["skip_reason"] = "no_project_root"
            return task_results, meta, total_cost

        verify_cmd = infer_verify_command(project_root)
        if not verify_cmd:
            meta["skip_reason"] = "no_verify_command"
            return task_results, meta, total_cost

        if not self.config.has_llm_credentials():
            meta["skip_reason"] = "no_llm_credentials"
            return task_results, meta, total_cost

        prior = task_results.get("verify_deliverable")
        if isinstance(prior, dict) and prior.get("success"):
            meta["build_verified"] = True
            meta["verify_command"] = prior.get("command") or verify_cmd
            meta["verify_attempts"] = 1
            meta["skip_reason"] = "dag_verify_already_passed"
            return task_results, meta, total_cost

        strategies: List[str] = []
        shell_timeout = self.config.deliverable_verify_timeout
        last_error = ""
        max_attempts = self.config.deliverable_verify_max_retries

        for attempt in range(1, max_attempts + 1):
            meta["verify_attempts"] = attempt
            if ctx is not None:
                ctx.checkpoint(
                    "verify",
                    f"Build verify {attempt}/{max_attempts}",
                    0.58 + 0.28 * (attempt - 1) / max(max_attempts, 1),
                    verify_cmd[:100],
                )
            logger.info(
                "[DeliverableConvergence] attempt %d/%d | cmd=%s",
                attempt,
                self.config.deliverable_verify_max_retries,
                verify_cmd[:120],
            )

            verify_result, cost = await self.tool_executor.execute(
                "run_shell",
                {
                    "command": verify_cmd,
                    "workspace_id": workspace_id,
                    "output_base": output_base,
                    "tenant_id": tenant_id,
                    "timeout": shell_timeout,
                },
                profile.domain,
            )
            total_cost += cost
            cost_callback(cost)
            task_results[f"verify_attempt_{attempt}"] = verify_result

            if verify_result.get("success"):
                meta["build_verified"] = True
                meta["verify_command"] = verify_cmd
                meta["strategies"] = strategies
                if ctx is not None:
                    ctx.checkpoint("verify", "Build verified successfully", 0.88)
                logger.info("[DeliverableConvergence] verified on attempt %d", attempt)
                return task_results, meta, total_cost

            stderr = (verify_result.get("stderr") or "") + "\n" + (verify_result.get("stdout") or "")
            last_error = stderr.strip()[:6000] or verify_result.get("error", "verification failed")
            meta["last_stderr"] = verify_result.get("stderr", "")[:4000]
            meta["last_stdout"] = verify_result.get("stdout", "")[:4000]

            if attempt >= max_attempts:
                break

            if not self.config.has_llm_credentials():
                meta["skip_reason"] = "no_llm_for_fixes"
                break

            if ctx is not None:
                ctx.checkpoint(
                    "verify",
                    f"Build failed — LLM analyzing errors (attempt {attempt})",
                    0.60 + 0.26 * (attempt - 1) / max(max_attempts, 1),
                    (last_error[:120] + "…") if len(last_error) > 120 else last_error,
                )

            strategy = "initial" if attempt == 1 else strategies[-1] if strategies else "initial"
            fix_data, fix_cost = await self._learn_and_plan_fixes(
                goal=goal,
                profile=profile,
                project_root=project_root,
                error=last_error,
                strategy=strategy,
                prior_strategies=strategies,
            )
            total_cost += fix_cost
            cost_callback(fix_cost)

            new_strategy = fix_data.get("strategy", f"fix_attempt_{attempt}")
            strategies.append(new_strategy)
            meta["strategies"] = strategies
            meta["last_root_cause"] = fix_data.get("root_cause", "")

            applied, apply_cost = await self._apply_fix_plan(
                fix_data, workspace_id, output_base, tenant_id=tenant_id
            )
            total_cost += apply_cost
            cost_callback(apply_cost)
            if ctx is not None and applied:
                ctx.checkpoint(
                    "verify",
                    "Applied LLM fixes — re-running build",
                    0.62 + 0.24 * attempt / max(max_attempts, 1),
                    new_strategy[:80],
                )
            task_results[f"fix_attempt_{attempt}"] = {
                "success": applied,
                "strategy": new_strategy,
                "root_cause": fix_data.get("root_cause"),
                "files_patched": len(fix_data.get("patches", [])),
                "files_rewritten": len(fix_data.get("files", [])),
            }

            if not applied:
                logger.warning("[DeliverableConvergence] fix apply failed on attempt %d", attempt)

        meta["strategies"] = strategies
        meta["verify_command"] = verify_cmd
        meta["last_error"] = last_error[:2000]
        return task_results, meta, total_cost

    async def _learn_and_plan_fixes(
        self,
        goal: str,
        profile: DynamicDomainProfile,
        project_root: Path,
        error: str,
        strategy: str,
        prior_strategies: List[str],
    ) -> Tuple[Dict[str, Any], float]:
        tree = _project_tree_summary(project_root)
        file_ctx = _read_files_for_context(project_root, error)
        prior = "\n".join(f"- {s}" for s in prior_strategies) or "- (none)"

        prompt = f"""GOAL:
{goal}

CURRENT STRATEGY (failed): {strategy}
PRIOR STRATEGIES (do NOT repeat):
{prior}

VERIFICATION ERROR (stderr/stdout):
{error[:5000]}

PROJECT FILE TREE:
{tree}

KEY FILE CONTENTS:
{file_ctx}

Return the fix JSON."""

        data, cost = await self.orchestrator.invoke_json(
            prompt=prompt,
            system=FIX_SYSTEM,
            temperature=0.2,
        )
        if not isinstance(data, dict):
            data = {}
        if "files" not in data and "raw" in data:
            data = _parse_fix_json(data.get("raw", ""))

        # If the fixer requested web searches to resolve ambiguous errors, run them
        # and inject the evidence into a second LLM call for a more informed fix.
        search_queries = data.get("web_search_queries") or []
        if search_queries and self.tool_executor:
            extra_snippets: list = []
            extra_cost = 0.0
            for q in search_queries[:3]:
                result, sc = await self.tool_executor.execute(
                    "web_search", {"query": q, "max_results": 4}, "fix_search"
                )
                extra_cost += sc
                for item in result.get("results", []):
                    snip = item.get("snippet") or item.get("title", "")
                    if snip:
                        extra_snippets.append(snip[:300])
            cost += extra_cost

            if extra_snippets:
                evidence_block = "\n".join(f"[{i+1}] {s}" for i, s in enumerate(extra_snippets[:10]))
                enriched_prompt = (
                    prompt
                    + f"\n\nADDITIONAL WEB EVIDENCE (from error-specific searches):\n{evidence_block}"
                    + "\n\nUsing this evidence, produce a more precise fix."
                )
                data2, cost2 = await self.orchestrator.invoke_json(
                    prompt=enriched_prompt,
                    system=FIX_SYSTEM,
                    temperature=0.15,
                )
                cost += cost2
                if isinstance(data2, dict) and (data2.get("files") or data2.get("patches")):
                    data = data2

        return data, cost

    async def _apply_fix_plan(
        self,
        fix_data: Dict[str, Any],
        workspace_id: str,
        output_base: str,
        tenant_id: str = "default",
    ) -> Tuple[bool, float]:
        total_cost = 0.0
        any_ok = False

        for patch in fix_data.get("patches") or []:
            if not isinstance(patch, dict):
                continue
            path = patch.get("path")
            if not path:
                continue
            result, cost = await self.tool_executor.execute(
                "modify_file",
                {
                    "path": path,
                    "workspace_id": workspace_id,
                    "output_base": output_base,
                    "tenant_id": tenant_id,
                    "old_string": patch.get("old_string", ""),
                    "new_string": patch.get("new_string", ""),
                },
                "general",
            )
            total_cost += cost
            any_ok = any_ok or bool(result.get("success"))

        files = fix_data.get("files") or []
        if files:
            result, cost = await self.tool_executor.execute(
                "write_files",
                {
                    "files": files,
                    "workspace_id": workspace_id,
                    "output_base": output_base,
                    "tenant_id": tenant_id,
                },
                "general",
            )
            total_cost += cost
            any_ok = any_ok or bool(result.get("success"))

        return any_ok or bool(files or fix_data.get("patches")), total_cost

    @staticmethod
    def _resolve_project_root(
        task_results: Dict[str, Any],
        workspace_id: str,
        output_base: str,
        tenant_id: str = "default",
    ) -> Optional[Path]:
        for value in task_results.values():
            if isinstance(value, dict) and value.get("project_root"):
                return Path(value["project_root"])
        from omega_agent.tools.workspace import workspace_project_dir

        return workspace_project_dir(workspace_id, output_base, "project", tenant_id=tenant_id)


def _parse_fix_json(text: str) -> Dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return {}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {}
