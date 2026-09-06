"""Shared UI helpers (FastAPI & Data Extraction)."""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path
from typing import Any, Optional, Tuple

from omega_agent import Config

def deliverable_paths(agent_result: Optional[Any]) -> Tuple[Optional[str], Optional[str]]:
    if agent_result is None:
        return None, None
    meta = getattr(agent_result, "metadata", None) or {}
    archive_path = meta.get("archive_path")
    project_root = meta.get("project_root")
    decision = getattr(agent_result, "decision", None)
    if decision and getattr(decision, "risk_params", None):
        archive_path = archive_path or decision.risk_params.get("archive_path")
        project_root = project_root or decision.risk_params.get("project_root")
    output = getattr(agent_result, "output", "") or ""
    if not archive_path and output:
        m = re.search(r"\*\*Download zip:\*\* `([^`]+)`", output)
        if m:
            archive_path = m.group(1).strip()
    if not project_root and output:
        m = re.search(r"\*\*Project:\*\* `([^`]+)`", output)
        if m:
            project_root = m.group(1).strip()
    return archive_path, project_root

def verify_display(agent_result: Optional[Any]) -> Tuple[bool, int, str]:
    if agent_result is None:
        return False, 0, ""
    meta = getattr(agent_result, "metadata", None) or {}
    vmeta = meta.get("deliverable_verify") or {}
    if not vmeta:
        decision = getattr(agent_result, "decision", None)
        if decision and getattr(decision, "risk_params", None):
            if decision.risk_params.get("build_verified"):
                return True, 1, ""
        return False, 0, ""
    ok = bool(vmeta.get("build_verified"))
    att = int(vmeta.get("verify_attempts", 0))
    err = str(vmeta.get("last_error") or vmeta.get("last_stderr") or "")
    return ok, att, err

def stage_download_zip(archive_path: Optional[str], config: Config) -> Optional[str]:
    def downloads_dir(cfg: Config) -> Path:
        d = Path(cfg.build_output_dir).resolve() / "downloads"
        d.mkdir(parents=True, exist_ok=True)
        return d

    if not archive_path:
        return None
    p = Path(archive_path)
    src = None
    if p.is_file():
        src = p
    elif p.is_dir():
        p = p / f"{p.name}.zip"
        if p.is_file():
            src = p
    else:
        p = Path(config.workspace_root) / p.name
        if p.is_file():
            src = p

    if src is None:
        return None
    dest_dir = downloads_dir(config)
    dest = dest_dir / src.name
    if dest.exists():
        try:
            if (
                dest.stat().st_size == src.stat().st_size
                and dest.read_bytes() == src.read_bytes()
            ):
                return str(dest.resolve())
        except OSError:
            pass
        dest = dest_dir / f"{src.stem}-{int(time.time())}{src.suffix}"
    shutil.copy2(src, dest)
    return str(dest.resolve())

def deliverable_payload(agent_result: Optional[Any], config: Config) -> dict:
    """Enriched payload containing standard execution data + Enterprise SOTA telemetry."""
    arch, proj = deliverable_paths(agent_result)
    build_ok, verify_att, verify_err = verify_display(agent_result)
    staged = stage_download_zip(arch, config)
    
    quality = "—"
    sota_score = "—"
    cognitive_state = "—"
    recovery_hints = "None"
    
    # BOMB-PROOF METADATA EXTRACTION: Impossible to throw 'NoneType' error
    meta = getattr(agent_result, "metadata", None) or {}
    
    if meta:
        qs = meta.get("quality_score")
        if qs is not None:
            quality = f"{float(qs) * 100:.0f}%"
            
        ss = meta.get("sota_score")
        if ss is not None:
            sota_score = f"{float(ss) * 100:.0f}%"
        else:
            sota_score = quality  # Fallback
            
        cognitive_state = meta.get("cognitive_state", "Stable")
        recovery_hints = meta.get("recovery_hints", "None required")

    domain = getattr(agent_result, "domain", "—") if agent_result else "—"
    latency = getattr(agent_result, "latency", 0)
    cost = getattr(agent_result, "cost", 0)

    return {
        "domain": domain,
        "quality": quality,
        "sota_score": sota_score,                  
        "cognitive_state": cognitive_state,        
        "recovery_hints": recovery_hints,          
        "latency": f"{latency:.1f}s" if agent_result else "—",
        "cost": f"${cost:.4f}" if agent_result else "—",
        "archive_url": f"/api/download?path={staged}" if staged else None,
        "project_root": proj,
        "build_verified": build_ok,
        "verify_attempts": verify_att,
        "verify_error": verify_err,
    }