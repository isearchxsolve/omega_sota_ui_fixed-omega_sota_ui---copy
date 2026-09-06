# OMEGA SOTA UI

Dynamic automation agent: web research → plan (DAG) → materialize deliverables → **verify / learn / fix** → zip.

## Quick start

```powershell
pip install -r requirements.txt
$env:GROQ_API_KEY = "your-key"
python -m omega_agent.ui.gradio_app
```

Mock mode (no API key, fast, skips npm verify):

```powershell
python -c "import asyncio; from omega_agent import OmegaAgent, Config; asyncio.run(OmegaAgent(Config(use_mock_llm=True)).run('Build a React app'))"
```

## Deliverable verification loop

For build / workspace goals with LLM credentials enabled:

1. Materialize files (`llm_generate_files`, scaffolds, etc.)
2. DAG task **`verify_deliverable`**: `run_shell` with install + build + test
3. **Finalize convergence**: on failure, LLM reads stderr → patches files → re-runs verify (up to N times)
4. Zip only when verify passes (unless `OMEGA_DELIVERABLE_ZIP_ON_FAILURE=true`)

See [docs/CONVERGENCE.md](docs/CONVERGENCE.md) for architecture and notebook parity.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | — | Groq LLM (recommended) |
| `OMEGA_DELIVERABLE_VERIFY_ENABLED` | `true` | Enable verify/fix loop |
| `OMEGA_DELIVERABLE_VERIFY_MAX_RETRIES` | `5` | Max verify→fix cycles |
| `OMEGA_DELIVERABLE_VERIFY_TIMEOUT` | `300` | Shell timeout per verify (seconds) |
| `OMEGA_DELIVERABLE_ZIP_ON_FAILURE` | `false` | Zip project even if verify failed |
| `OMEGA_DEFAULT_TENANT_ID` | `default` | Tenant namespace for workspaces |
| `OMEGA_MAX_CONCURRENT_GOALS` | `8` | Max parallel goal executions (API) |
| `OMEGA_GRADIO_CONCURRENCY` | `4` | Gradio queue workers |
| `OMEGA_REDIS_URL` | — | Shared session store (required for multi-replica) |

See [docs/SCALING.md](docs/SCALING.md) for multitenancy and production deployment.

### Smoke test (real LLM + npm)

```powershell
$env:GROQ_API_KEY = "your-key"
python scripts/run_deliverable_verify_smoke.py
```

## Tests

```powershell
python -m pytest test_deliverable_convergence.py test_build_actions.py test_interactive_ui.py -q
```

## API

```powershell
uvicorn omega_agent.api:app --reload
```
