"""Generic workspace tools: files, shell, zip — no domain-specific logic."""

import asyncio
import json
import logging
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("omega_agent.tools.workspace")

WORKSPACE_ROOT = Path("./outputs/workspaces")


def _root(base: str = "") -> Path:
    if base:
        return Path(base).resolve()
    return WORKSPACE_ROOT.resolve()


def resolve_workspace(
    workspace_id: str,
    output_base: str = "",
    tenant_id: str = "default",
) -> Path:
    from omega_agent.core.tenant import sanitize_tenant_id

    tid = sanitize_tenant_id(tenant_id)
    wid = re.sub(r"[^a-zA-Z0-9_-]", "-", (workspace_id or "default"))[:64]
    return _root(output_base) / tid / wid


def safe_relative_path(relative: str) -> str:
    rel = (relative or "").replace("\\", "/").lstrip("/")
    parts = Path(rel).parts
    if ".." in parts:
        raise ValueError(f"Path traversal not allowed: {relative}")
    return rel


def workspace_project_dir(
    workspace_id: str,
    output_base: str = "",
    subdir: str = "project",
    tenant_id: str = "default",
) -> Path:
    ws = resolve_workspace(workspace_id, output_base, tenant_id=tenant_id)
    proj = ws / safe_relative_path(subdir or "project")
    proj.mkdir(parents=True, exist_ok=True)
    return proj


async def write_files(
    files: Union[List[Dict[str, str]], str],
    workspace_id: str = "default",
    output_base: str = "",
    project_subdir: str = "project",
    goal: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Create or overwrite files under the workspace project directory."""
    if isinstance(files, str):
        try:
            files = json.loads(files)
        except json.JSONDecodeError:
            files = [{"path": "notes.txt", "content": files}]

    tenant_id = kwargs.get("tenant_id", "default")
    root = workspace_project_dir(workspace_id, output_base, project_subdir, tenant_id=tenant_id)
    written: List[str] = []

    for item in files or []:
        if not isinstance(item, dict):
            continue
        rel = safe_relative_path(item.get("path", "untitled.txt"))
        content = item.get("content", "")
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content, indent=2), encoding="utf-8")
        written.append(rel)

    return {
        "success": bool(written),
        "workspace_id": workspace_id,
        "project_root": str(root),
        "files_written": written,
        "file_count": len(written),
        "action_taken": f"Wrote {len(written)} file(s) to {root}",
        "goal": goal[:200],
    }


async def modify_file(
    path: str,
    workspace_id: str = "default",
    output_base: str = "",
    project_subdir: str = "project",
    content: str = "",
    old_string: str = "",
    new_string: str = "",
    append: bool = False,
    **kwargs,
) -> Dict[str, Any]:
    """Modify a single file: full replace, patch, or append."""
    tenant_id = kwargs.get("tenant_id", "default")
    root = workspace_project_dir(workspace_id, output_base, project_subdir, tenant_id=tenant_id)
    rel = safe_relative_path(path)
    target = root / rel
    if not target.exists() and not content and not new_string:
        return {"success": False, "error": f"File not found: {rel}"}

    original = target.read_text(encoding="utf-8") if target.exists() else ""
    if content:
        updated = content
        mode = "replace"
    elif old_string and new_string is not None:
        if old_string not in original:
            return {"success": False, "error": "old_string not found in file", "path": rel}
        updated = original.replace(old_string, new_string, 1)
        mode = "patch"
    elif append:
        updated = original + (new_string or content or "")
        mode = "append"
    else:
        return {"success": False, "error": "Provide content, or old_string+new_string, or append"}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(updated, encoding="utf-8")
    return {
        "success": True,
        "path": rel,
        "project_root": str(root),
        "mode": mode,
        "action_taken": f"Modified {rel} ({mode})",
    }


async def run_shell(
    command: str,
    workspace_id: str = "default",
    output_base: str = "",
    project_subdir: str = "project",
    timeout: int = 120,
    **kwargs,
) -> Dict[str, Any]:
    """Run a shell command (npm, pip, etc.) with cwd = workspace project root."""
    tenant_id = kwargs.get("tenant_id", "default")
    cwd = workspace_project_dir(workspace_id, output_base, project_subdir, tenant_id=tenant_id)
    if not command or not str(command).strip():
        return {"success": False, "error": "Empty command"}

    logger.info("run_shell cwd=%s cmd=%s", cwd, command[:200])

    def _run():
        import subprocess
        import sys

        return subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=None,
        )

    try:
        proc = await asyncio.get_event_loop().run_in_executor(None, _run)
        return {
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[:8000],
            "stderr": (proc.stderr or "")[:4000],
            "command": command,
            "cwd": str(cwd),
            "action_taken": f"Executed: {command[:120]}",
        }
    except Exception as e:
        return {"success": False, "error": str(e), "command": command, "cwd": str(cwd)}


async def archive_zip(
    workspace_id: str = "default",
    output_base: str = "",
    project_subdir: str = "project",
    archive_name: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Zip the workspace project directory for delivery."""
    tenant_id = kwargs.get("tenant_id", "default")
    root = workspace_project_dir(workspace_id, output_base, project_subdir, tenant_id=tenant_id)
    if not any(root.iterdir()) if root.exists() else True:
        return {"success": False, "error": "Project directory is empty", "project_root": str(root)}

    ws = resolve_workspace(workspace_id, output_base, tenant_id=tenant_id)
    name = archive_name or f"{workspace_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    if not name.endswith(".zip"):
        name += ".zip"
    zip_path = ws / name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in root.rglob("*"):
            if file_path.is_file():
                arcname = str(Path(project_subdir) / file_path.relative_to(root))
                zf.write(file_path, arcname.replace("\\", "/"))

    size_kb = zip_path.stat().st_size / 1024
    return {
        "success": True,
        "archive_path": str(zip_path.resolve()),
        "archive_name": name,
        "project_root": str(root),
        "size_kb": round(size_kb, 1),
        "action_taken": f"Created zip {zip_path} ({size_kb:.1f} KB)",
    }


def register_workspace_tools(registry) -> None:
    tools = [
        (
            "write_files",
            "ACT: create/overwrite multiple files in the workspace (JSON list of {path, content})",
            write_files,
            {
                "files": "list or JSON string — [{path, content}]",
                "workspace_id": "string — workspace folder name",
                "output_base": "string — optional root (default ./outputs/workspaces)",
                "project_subdir": "string — default project",
                "goal": "string — optional context",
            },
            "Use to materialize code/docs after research or llm_generate_files",
        ),
        (
            "modify_file",
            "ACT: patch or replace one file in the workspace",
            modify_file,
            {
                "path": "string — relative file path",
                "workspace_id": "string",
                "content": "string — full file content (optional)",
                "old_string": "string — patch find (optional)",
                "new_string": "string — patch replace (optional)",
                "append": "bool — append to file",
            },
            "Use for incremental edits after initial write_files",
        ),
        (
            "run_shell",
            "ACT: run shell command (npm install, pip install, pytest, etc.) in workspace project dir",
            run_shell,
            {
                "command": "string — full shell command",
                "workspace_id": "string",
                "timeout": "int — seconds (default 120)",
            },
            "Use to install deps, build, test — after files exist",
        ),
        (
            "archive_zip",
            "ACT: zip the workspace project for download/delivery",
            archive_zip,
            {
                "workspace_id": "string",
                "archive_name": "string — optional zip filename",
            },
            "Use as final delivery step after build succeeds",
        ),
    ]
    for name, desc, handler, args, hint in tools:
        registry.register(name, desc, handler, args=args, usage_hint=hint)
