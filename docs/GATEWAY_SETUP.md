# Gateway Setup

Gateway-0 prepares LiteLLM as the future single gateway for Quimera/OpenClaw
model calls. PR 2 makes the local gateway installable and testable, but still
does not route OpenClaw runtime calls through LiteLLM.

Gateway work must follow the repository GitHub workflow: issue first, branch
from updated `main`, local validation, pushed branch, GitHub PR, linked issue,
and merge only in GitHub after approval.

## Local Services

Required local services:

- Ollama at `http://127.0.0.1:11434`
- Qwen local chat model available in Ollama
- `nomic-embed-text` available in Ollama
- Qdrant for RAG vectors

Useful checks:

```bash
ollama --version
ollama pull qwen3:14b
ollama pull nomic-embed-text
ollama list
curl -fsS http://127.0.0.1:11434/api/tags
curl -fsS http://localhost:6333/healthz
```

## Config Locations

Contract config:

```text
config/litellm_config.yaml
```

Operational local gateway config:

```text
infra/litellm/litellm_config.yaml
```

Both configs define these semantic aliases:

- `local_chat`
- `local_think`
- `local_rag`
- `local_json`
- `quimera_embed`
- `local_embed`

The operational aliases point only to local Ollama models. No remote provider is
enabled.

## Install LiteLLM Locally

Use an isolated environment under `infra/litellm`:

```bash
cd infra/litellm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Security note: LiteLLM versions `1.82.7` and `1.82.8` were compromised on PyPI
in March 2026. The local requirements exclude those versions and require the
post-incident `1.83.x` line.

## Environment

Use shell exports. Do not commit real secrets.

```bash
export LITELLM_MASTER_KEY="dev-local-key-change-me"
export OLLAMA_API_BASE="http://127.0.0.1:11434"
export QWEN_MODEL="qwen3:14b"
export EMBED_MODEL="nomic-embed-text"
export LITELLM_HOST="127.0.0.1"
export LITELLM_PORT="4000"
```

LiteLLM supports `os.environ/VAR_NAME` when the whole YAML value is loaded from
the environment. Because model names need an `ollama/` prefix,
`start_litellm.sh` derives the full LiteLLM model strings from `QWEN_MODEL` and
`EMBED_MODEL` before startup.

## Start LiteLLM

```bash
cd infra/litellm
source .venv/bin/activate
./start_litellm.sh
```

The script defaults to `127.0.0.1:4000` and refuses any non-local bind address.

## Validate

`healthcheck.sh` requires `LITELLM_MASTER_KEY` to be exported in the current
shell. `QUIMERA_LLM_API_KEY` must equal `LITELLM_MASTER_KEY` — it is the Bearer
token the runtime uses to authenticate against the gateway.

```bash
export LITELLM_MASTER_KEY="dev-local-key-change-me"
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
export QUIMERA_LLM_BASE_URL="http://127.0.0.1:4000/v1"
```

Then in the same shell:

```bash
cd infra/litellm
source .venv/bin/activate
./test_models.sh
./test_local_chat.sh
./healthcheck.sh
```

Or from the repository root:

```bash
scripts/check_litellm_gateway.sh
scripts/test_opencraw_litellm_runtime.sh
```

The checks validate:

- `/v1/models` responds;
- all five aliases are exposed;
- `local_chat` answers a short synthetic Portuguese prompt;
- PR4 smoke additionally checks `local_chat`, `local_think`, `local_rag`, and
  `local_json`;
- Ollama is reachable;
- no active remote provider marker appears in the LiteLLM config.

Pytest smoke is opt-in:

```bash
RUN_LITELLM_SMOKE=1 uv run pytest tests/smoke -v
```

It is skipped by default because normal unit tests must not require local
services.

## Stop LiteLLM

If LiteLLM runs in the foreground, stop it with `Ctrl-C`.

If it runs in another shell:

```bash
ps aux | grep '[l]itellm'
kill <pid>
```

## RAG Boundary

Qdrant remains the RAG vector database. LiteLLM is not the vector store and does
not own chunking, retrieval, context packing, or citation logic.

The intended future path is:

```text
Python RAG modules -> Qdrant retrieval -> prompt/context -> LiteLLM alias -> Ollama
```

RAG is not routed directly through LiteLLM in PR 2. Only the standalone gateway
operation is proven there. PR 3 routes OpenClaw runtime chat generation through
LiteLLM while preserving Qdrant retrieval and existing embedding behavior.
PR 4 proves the live route with optional smoke tests and minimal gateway
observability.
GW-05a adds runtime request timeout budgets per semantic alias without changing
RAG, Qdrant, embeddings, or prompt construction.
GW-05b adds live smoke timing validation and `timeout_s` gateway observability
without changing RAG, Qdrant, embeddings, or prompt construction.
GW-12 closes the Gateway-0 sprint with `docs/GATEWAY_FINAL_RUNBOOK.md`,
`scripts/check_gateway_readiness.sh`, static baseline tests and ADR-0019.

Application runtime environment:

```bash
export QUIMERA_LLM_BASE_URL="http://127.0.0.1:4000/v1"
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
export QUIMERA_LLM_MODEL="local_chat"
export QUIMERA_LLM_REASONING_MODEL="local_think"
export QUIMERA_LLM_RAG_MODEL="local_rag"
export QUIMERA_LLM_JSON_MODEL="local_json"
```

Runtime timeout contract:

| Alias | Timeout | Notes |
|---|---:|---|
| `local_chat` | 30.0s | Default chat calls |
| `local_think` | 120.0s | Longer local reasoning calls |
| `local_rag` | 60.0s | RAG answer synthesis |
| `local_json` | 30.0s | Structured local responses |
| `quimera_embed` | 30.0s | Canonical local embedding alias |
| `local_embed` | 30.0s | Compatibility embedding alias |

## Final Readiness

Static readiness is CI-safe and requires no live services:

```bash
scripts/check_gateway_readiness.sh
```

Live readiness is explicit and local-only:

```bash
export LITELLM_MASTER_KEY="dev-local-key-change-me"
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/check_gateway_readiness.sh --live
```

The final runbook is:

```text
docs/GATEWAY_FINAL_RUNBOOK.md
```

Gateway-0 remains local-only. Remote providers require a future ADR. FastAPI,
MCP, quant tools, OpenTelemetry/profiling and production
`openclaw_knowledge` ingestion are out of scope for Gateway-0.

Live smoke repeat is opt-in:

```bash
RUN_LITELLM_SMOKE=1 RUN_LITELLM_SMOKE_REPEAT=3 uv run pytest tests/smoke -v
```

See `docs/guides/OPENCLAW_LITELLM_RUNTIME.md` for runtime troubleshooting.

## MVP Exclusions

FastAPI is intentionally out of the MVP path. Gateway-0 focuses on local config,
contracts, and reviewable boundaries before any service layer is introduced.

Also excluded:

- remote AI fallback;
- Redis;
- quant tools;
- MCP;
- embeddings-through-gateway;
- real portfolio data;
- secrets in repository files.

## Security Notes

Do not commit `.env`, API keys, tokens, passwords, private endpoints, broker
exports, real portfolio data, or private documents.

Do not put private financial data in prompts or logs. Remote providers must be
introduced only in a later approved sprint with sanitization, audit logging, and
budget controls.
