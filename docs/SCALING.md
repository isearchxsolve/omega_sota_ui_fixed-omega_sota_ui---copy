# OMEGA scaling and multitenancy

## Current capabilities (v1.2)

| Feature | Status |
|---------|--------|
| Tenant-isolated workspaces (`outputs/workspaces/{tenant_id}/{workspace_id}`) | Yes |
| API headers `X-Tenant-ID`, `X-User-ID` | Yes |
| Pluggable session store (memory / Redis) | Yes |
| Concurrent goal limit (`OMEGA_MAX_CONCURRENT_GOALS`) | Yes |
| Gradio queue concurrency (`OMEGA_GRADIO_CONCURRENCY`) | Yes |
| Per-request agent instance (API) | Yes |
| Horizontal auto-scale / K8s manifests | Not included |
| Strong auth (OAuth, API keys per tenant) | Not included |
| Dedicated DB per tenant | No (shared SQLite memory) |

OMEGA is **multi-tenant ready** for development and moderate production load. It is **not** yet a fully elastic hyperscale platform without external infrastructure (Redis, load balancer, worker pool).

## Architecture

```
                    ┌─────────────┐
  Clients ─────────►│ Load balancer│
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
      API replica 1   API replica 2   Gradio UI
           │               │               │
           └───────────────┼───────────────┘
                           ▼
                    Redis (sessions)
                           │
              workspaces/{tenant}/{project}
```

## Environment

```bash
OMEGA_DEFAULT_TENANT_ID=acme-corp
OMEGA_MAX_CONCURRENT_GOALS=16
OMEGA_GRADIO_CONCURRENCY=8
OMEGA_REDIS_URL=redis://localhost:6379/0
OMEGA_SESSION_TTL_SECONDS=86400
```

## API usage

```http
POST /v1/goals
X-Tenant-ID: acme-corp
X-User-ID: user-42
Content-Type: application/json

{"goal": "Build a Vite dashboard", "max_time": 300}
```

Or in the JSON body: `"tenant_id": "acme-corp", "user_id": "user-42"`.

## Production checklist

1. Run **multiple uvicorn workers** or replicas behind a load balancer.
2. Set **`OMEGA_REDIS_URL`** so interactive sessions survive replica changes.
3. Mount **shared storage** (NFS / S3 sync) for `outputs/workspaces` if workers are not single-node.
4. Add **API authentication** at the gateway (not built into OMEGA yet).
5. Rate-limit per tenant at the gateway.

## What is not multitenant yet

- Shared episodic memory SQLite (`omega_memory.db`) — all tenants share learning store unless you split by `memory_db_path` per tenant in a custom deployment.
- Single global metrics collector per process.
- No per-tenant LLM budget enforcement.
