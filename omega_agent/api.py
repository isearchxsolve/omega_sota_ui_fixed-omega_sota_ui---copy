"""FastAPI REST API for OMEGA Agent — multi-tenant sessions and concurrent goals."""

import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from omega_agent import OmegaAgent, Config
from omega_agent.core.session_store import SessionStore, create_session_store
from omega_agent.core.tenant import TenantContext, sanitize_tenant_id
from omega_agent.core.types import AgentResult
from omega_agent.interaction.runner import InteractiveOmegaRunner
from omega_agent.interaction.session import OmegaChatSession

app = FastAPI(
    title="OMEGA Agent API",
    description="Multi-domain action-taking orchestrator with tenant isolation",
    version="1.2.0",
)

_config: Optional[Config] = None
_session_store: Optional[SessionStore] = None
_result_cache: Dict[str, Dict[str, Any]] = {}
_goal_semaphore: Optional[asyncio.Semaphore] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def get_session_store() -> SessionStore:
    global _session_store
    if _session_store is None:
        cfg = get_config()
        _session_store = create_session_store(
            redis_url=cfg.redis_url,
            ttl_seconds=cfg.session_ttl_seconds,
        )
    return _session_store


def get_goal_semaphore() -> asyncio.Semaphore:
    global _goal_semaphore
    if _goal_semaphore is None:
        _goal_semaphore = asyncio.Semaphore(get_config().max_concurrent_goals)
    return _goal_semaphore


def get_agent() -> OmegaAgent:
    """Fresh agent per heavy request avoids cross-tenant state bleed."""
    return OmegaAgent(config=get_config())


def get_interactive_runner() -> InteractiveOmegaRunner:
    return InteractiveOmegaRunner(agent=get_agent(), config=get_config())


def _tenant_from_headers(
    x_tenant_id: Optional[str],
    x_user_id: Optional[str],
) -> TenantContext:
    return TenantContext.from_headers(
        x_tenant_id,
        x_user_id,
        default_tenant=get_config().default_tenant_id,
    )


class GoalRequest(BaseModel):
    goal: str = Field(..., min_length=1, description="Natural language goal")
    domain: Optional[str] = Field(None, description="Domain hint (auto-detected if omitted)")
    max_time: int = Field(300, ge=5, le=600, description="Max execution seconds")
    tenant_id: Optional[str] = Field(None, description="Tenant namespace (or use X-Tenant-ID header)")
    user_id: Optional[str] = Field(None, description="End-user id within tenant")


class GoalResponse(BaseModel):
    request_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    cost: float = 0.0
    latency: float = 0.0
    tenant_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_mode: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    domains: list
    max_concurrent_goals: int
    session_backend: str


@app.get("/health", response_model=HealthResponse)
async def health():
    agent = get_agent()
    provider = agent.config.active_llm_provider()
    cfg = get_config()
    backend = "redis" if cfg.redis_url else "memory"
    return HealthResponse(
        status="ok",
        version="1.2.0",
        llm_mode="live" if provider else "mock",
        llm_provider=provider,
        llm_model=agent.config.primary_model if provider else None,
        domains=agent.list_tools(),
        max_concurrent_goals=cfg.max_concurrent_goals,
        session_backend=backend,
    )


async def _run_goal(
    request_id: str,
    goal: str,
    domain: Optional[str],
    max_time: int,
    tenant: TenantContext,
) -> None:
    sem = get_goal_semaphore()
    async with sem:
        agent = get_agent()
        result = await agent.run(
            goal=goal,
            domain=domain,
            max_time=max_time,
            tenant_id=tenant.tenant_id,
            user_id=tenant.user_id,
        )
        _result_cache[request_id] = {
            "status": "completed" if result.success else "failed",
            "result": result.to_dict(),
            "cost": result.cost,
            "latency": result.latency,
            "tenant_id": tenant.tenant_id,
        }


@app.post("/v1/goals", response_model=GoalResponse)
async def submit_goal(
    req: GoalRequest,
    bg_tasks: BackgroundTasks,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
):
    tenant = TenantContext.from_headers(
        req.tenant_id or x_tenant_id,
        req.user_id or x_user_id,
        default_tenant=get_config().default_tenant_id,
    )
    request_id = str(uuid.uuid4())
    _result_cache[request_id] = {"status": "running", "result": None, "tenant_id": tenant.tenant_id}

    bg_tasks.add_task(
        _run_goal,
        request_id,
        req.goal,
        req.domain,
        req.max_time,
        tenant,
    )
    return GoalResponse(
        request_id=request_id,
        status="running",
        tenant_id=tenant.tenant_id,
    )


@app.post("/v1/goals/sync", response_model=GoalResponse)
async def submit_goal_sync(
    req: GoalRequest,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
):
    tenant = TenantContext.from_headers(
        req.tenant_id or x_tenant_id,
        req.user_id or x_user_id,
        default_tenant=get_config().default_tenant_id,
    )
    request_id = str(uuid.uuid4())
    await _run_goal(request_id, req.goal, req.domain, req.max_time, tenant)
    cached = _result_cache[request_id]
    return GoalResponse(
        request_id=request_id,
        status=cached["status"],
        result=cached.get("result"),
        cost=cached.get("cost", 0.0),
        latency=cached.get("latency", 0.0),
        tenant_id=tenant.tenant_id,
    )


@app.get("/v1/goals/{request_id}", response_model=GoalResponse)
async def get_goal_status(request_id: str):
    cached = _result_cache.get(request_id)
    if not cached:
        raise HTTPException(status_code=404, detail="Request not found")
    return GoalResponse(
        request_id=request_id,
        status=cached["status"],
        result=cached.get("result"),
        cost=cached.get("cost", 0.0),
        latency=cached.get("latency", 0.0),
        tenant_id=cached.get("tenant_id"),
    )


@app.get("/v1/metrics")
async def get_metrics():
    agent = get_agent()
    return {
        **agent.get_metrics(),
        "memory": agent.get_memory_stats(),
        "max_concurrent_goals": get_config().max_concurrent_goals,
    }


class InteractiveMessageRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(None, description="Resume an existing interactive session")
    max_time: int = Field(300, ge=5, le=600)
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None


class InteractiveMessageResponse(BaseModel):
    session_id: str
    status: str
    needs_input: bool
    message: str
    request: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    chat_messages: list = Field(default_factory=list)
    tenant_id: str = "default"


@app.post("/v1/interactive/message", response_model=InteractiveMessageResponse)
async def interactive_message(
    req: InteractiveMessageRequest,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
):
    tenant = TenantContext.from_headers(
        req.tenant_id or x_tenant_id,
        req.user_id or x_user_id,
        default_tenant=get_config().default_tenant_id,
    )
    store = get_session_store()
    session_data = store.get(req.session_id or "", tenant.tenant_id) if req.session_id else None
    session = OmegaChatSession.from_state_dict(session_data) if session_data else OmegaChatSession()
    if req.session_id:
        session.session_id = req.session_id
    session.metadata["tenant_id"] = tenant.tenant_id
    if tenant.user_id:
        session.metadata["user_id"] = tenant.user_id

    runner = get_interactive_runner()
    async with get_goal_semaphore():
        outcome = await runner.handle_message(req.message, session=session, max_time=req.max_time)

    store.set(session.session_id, session.to_state_dict(), tenant.tenant_id)

    return InteractiveMessageResponse(
        session_id=session.session_id,
        status=outcome.status.value,
        needs_input=outcome.needs_input,
        message=outcome.message,
        request=outcome.request.to_dict() if outcome.request else None,
        result=outcome.agent_result.to_dict() if outcome.agent_result else None,
        chat_messages=outcome.chat_messages,
        tenant_id=tenant.tenant_id,
    )


@app.get("/v1/interactive/sessions/{session_id}")
async def get_interactive_session(
    session_id: str,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    tenant_id = sanitize_tenant_id(x_tenant_id or get_config().default_tenant_id)
    data = get_session_store().get(session_id, tenant_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    return data


@app.get("/v1/domains")
async def list_domains():
    agent = get_agent()
    return {
        "mode": "dynamic",
        "description": "Domains discovered per-goal via web search + LLM",
        "tools": agent.list_tools(),
    }
