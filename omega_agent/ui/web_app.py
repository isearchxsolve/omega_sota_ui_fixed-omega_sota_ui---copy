"""OMEGA Web UI — FastAPI + SSE via GET EventSource (reliable live progress)."""

from __future__ import annotations

import os
import asyncio
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from omega_agent import Config, OmegaAgent
from omega_agent.interaction.runner import InteractiveOmegaRunner
from omega_agent.interaction.session import OmegaChatSession
from omega_agent.interaction.types import InteractiveRunResult, InteractiveStatus
from omega_agent.ui.progress_bridge import ThreadSafeProgress
from omega_agent.ui.shared import deliverable_payload

logger = logging.getLogger("omega_agent.ui.web")

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_STARTUP_LOG = (
    ">> OMEGA ORCHESTRATION ENGINE ACTIVATED\n"
    "-> Initializing AI reasoning system...\n"
    "-> Loading execution models and components...\n"
    "-> Preparing automation workspace...\n"
    "-> Connecting to execution queue...\n"
    "-> Standing by for workflow analysis..."
)

def _sse(event: str, payload: Dict[str, Any]) -> str:
    body = json.dumps(payload)
    return f"event: {event}\ndata: {body}\n\n"

class GoalRequest(BaseModel):
    goal: str = Field(..., description="The high-level goal.")
    domain: Optional[str] = Field(None, description="Optional domain hint.")
    max_time: int = Field(600, ge=5, le=3600, description="Max execution time in seconds.")
    user_inputs: Optional[Dict[str, str]] = Field(default_factory=dict)
    tenant_id: Optional[str] = Field("default")
    user_id: Optional[str] = Field(None)

def create_web_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="OMEGA SOTA Engine UI", version="7.5.0")
    runner = InteractiveOmegaRunner(agent=OmegaAgent(config=cfg), config=cfg)
    sessions: Dict[str, Dict[str, Any]] = {}
    jobs: Dict[str, asyncio.Task] = {}
    progress_map: Dict[str, ThreadSafeProgress] = {}  # Map job_id to progress object
    jobs_lock = threading.Lock()

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        idx = _STATIC_DIR / "index.html"
        if idx.exists():
            return idx.read_text(encoding="utf-8")
        return "<html><body><h1>OMEGA API Online</h1><p>No static/index.html found.</p></body></html>"

    # RESTORED ROUTE NAMES TO MATCH FRONTEND APP.JS
    @app.get("/api/chat/init")
    async def init_session():
        sess = OmegaChatSession()
        sessions[sess.session_id] = sess.to_state_dict()
        return {
            "session_id": sess.session_id,
            "status": "idle",
            "startup_log": _STARTUP_LOG,
        }

    @app.post("/api/chat/start")
    async def run_goal(req: GoalRequest):
        sid = OmegaChatSession().session_id
        if sid not in sessions:
            sessions[sid] = OmegaChatSession(session_id=sid).to_state_dict()

        progress = ThreadSafeProgress()
        job_id = str(uuid.uuid4())
        
        async def _run_task():
            session = OmegaChatSession.from_state_dict(sessions[sid])
            session.metadata["tenant_id"] = req.tenant_id or "default"
            if req.user_id:
                session.metadata["user_id"] = req.user_id
            if req.user_inputs:
                session.user_inputs.update(req.user_inputs)
            
            try:
                res = await runner.handle_message(
                    message=req.goal,
                    session=session,
                    max_time=req.max_time or 600,
                    progress=progress,
                )
                sessions[sid] = session.to_state_dict()
                return res
            except Exception as e:
                logger.error("Run error: %s", e, exc_info=True)
                return None
            finally:
                progress.mark_done()

        task = asyncio.create_task(_run_task())
        with jobs_lock:
            jobs[job_id] = task
            progress_map[job_id] = progress  # Store progress object for this job

        return {"job_id": job_id, "session_id": sid, "events_url": f"/api/chat/events/{job_id}"}

    @app.get("/api/chat/events/{job_id}")
    async def stream_job(job_id: str):
        with jobs_lock:
            task = jobs.get(job_id)
            prog = progress_map.get(job_id)

        if not task:
            raise HTTPException(status_code=404, detail="Job not found")

        async def event_stream() -> AsyncIterator[str]:
            yield _sse("status", {"message": "Attached to execution stream"})
            
            # Heartbeat loop while task is running — drain real progress events
            import asyncio
            checkpoint_count = 0
            while not task.done():
                # Drain any real progress events from the progress queue
                if prog:
                    events = prog.drain()
                    for evt in events:
                        if not evt.get("done"):
                            checkpoint_count += 1
                            yield _sse("progress", {
                                "elapsed": checkpoint_count,
                                "message": evt.get("message", "Processing..."),
                                "fraction": evt.get("fraction", 0.5),
                                "percent": int(evt.get("fraction", 0.5) * 100),
                                "log": evt.get("log", ""),
                                "phase": evt.get("phase", "processing"),
                            })
                
                # Send heartbeat to keep connection alive
                await asyncio.sleep(0.5)
            
            # Task completed — get result
            try:
                result = await task
            except Exception as e:
                yield _sse("complete", {
                    "success": False,
                    "output": f"Error: {str(e)}",
                    "needs_input": False,
                    "chat_messages": [],
                    "deliverable": None,
                })
                return
            
            # Extract any chat messages that were sent during execution
            # (e.g., validation blocks from emergency tools)
            chat_messages_from_execution = []
            if result and result.agent_result:
                meta = getattr(result.agent_result, "metadata", {}) or {}
                if meta.get("chat_messages_sent"):
                    chat_messages_from_execution = meta.get("chat_messages_sent", [])
            
            # Build Enriched SOTA Payload
            deliverable = deliverable_payload(result.agent_result if result else None, cfg) if result else None
            chat_messages = (result.chat_messages if result else []) + chat_messages_from_execution
            
            yield _sse(
                "complete",
                {
                    "success": bool(result and result.status == InteractiveStatus.COMPLETED),
                    "output": result.agent_result.output if (result and result.agent_result) else "Failed",
                    "needs_input": bool(result and result.needs_input),
                    "status": result.status.value if result else "failed",
                    "chat_messages": chat_messages,
                    "deliverable": deliverable,
                    "awaiting": "Yes — reply in the chat." if (result and result.needs_input) else "No",
                },
            )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive"},
        )
        
    @app.post("/api/chat/reset")
    async def reset_session():
        sid = OmegaChatSession().session_id
        sessions[sid] = OmegaChatSession(session_id=sid).to_state_dict()
        return {"session_id": sid, "status": "idle"}

    # ==========================================
    # ENTERPRISE SOTA TELEMETRY ENDPOINTS
    # ==========================================
    TELEMETRY_LOG = os.path.join(os.getcwd(), "logs", "omega_telemetry.jsonl")
    
    def _read_last_n_lines(file_path: str, n: int = 100) -> List[Dict[str, Any]]:
        if not os.path.exists(file_path): return []
        entries = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip(): entries.append(json.loads(line.strip()))
        except: pass
        return entries[-n:][::-1]

    @app.get("/api/telemetry/summary")
    async def get_telemetry_summary():
        """Aggregates rolling metrics across execution history for the UI."""
        entries = _read_last_n_lines(TELEMETRY_LOG, n=500)
        total_runs, successful_runs = 0, 0
        sota_scores = []
        domain_dist = {}
        
        for entry in entries:
            event = entry.get("event")
            data = entry.get("data", {})
            if event == "Workflow_Started":
                total_runs += 1
            elif event == "Workflow_Completed":
                successful_runs += 1
                if "sota_score" in data: sota_scores.append(data["sota_score"])
                domain = entry.get("domain", "general")
                domain_dist[domain] = domain_dist.get(domain, 0) + 1

        avg_sota = sum(sota_scores) / len(sota_scores) if sota_scores else 1.0
        success_rate = (successful_runs / total_runs * 100) if total_runs > 0 else 100.0

        return {
            "metrics": {
                "total_executions": total_runs,
                "success_rate_percentage": round(success_rate, 2),
                "average_sota_score": round(avg_sota, 2),
                "domains": domain_dist
            }
        }

    # ==========================================
    # DELIVERABLE DOWNLOAD ENDPOINT
    # ==========================================
    @app.get("/api/download")
    async def download_deliverable(path: str):
        """Serve a previously staged deliverable zip file."""
        import os
        from fastapi.responses import FileResponse
        
        if not path:
            raise HTTPException(status_code=400, detail="path parameter required")
        
        # Security: prevent path traversal
        file_path = Path(path).resolve()
        downloads_dir = Path(cfg.build_output_dir).resolve() / "downloads"
        
        if not file_path.is_relative_to(downloads_dir):
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        
        filename = file_path.name
        return FileResponse(
            path=file_path,
            media_type="application/zip",
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app

def launch_web_ui(config: Optional[Config] = None, host: str = "0.0.0.0", port: int = 7860) -> None:
    import uvicorn
    cfg = config or Config()
    app = create_web_app(cfg)
    logger.info("OMEGA SOTA Web UI online at http://%s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")