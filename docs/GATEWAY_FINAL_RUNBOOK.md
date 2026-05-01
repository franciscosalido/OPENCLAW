# Gateway-0 Final Runbook

Gateway-0 is the local-only Quimera/OpenClaw model gateway baseline.

It closes the implementation/configuration/observability sprint with a
repeatable operational path for local chat, RAG generation, embeddings,
readiness checks, rollback and troubleshooting.

## Architecture Summary

```text
OpenClaw runtime generation
  -> GatewayChatClient
  -> LiteLLM http://127.0.0.1:4000/v1
  -> Ollama / Qwen local

RAG embeddings for new controlled paths
  -> RagEmbedder factory
  -> gateway_litellm
  -> GatewayEmbedClient
  -> LiteLLM /v1/embeddings
  -> quimera_embed
  -> Ollama / nomic-embed-text local

RAG vectors
  -> Qdrant http://127.0.0.1:6333
```

Gateway-0 is local only. Remote providers are disabled and require a future ADR
before activation.

## Official Boot Order

1. Ollama
2. Qdrant
3. LiteLLM
4. Healthcheck
5. Gateway smoke
6. Optional RAG smoke

## Expected Local Endpoints

| Service | Endpoint |
|---|---|
| Ollama | `http://127.0.0.1:11434` |
| LiteLLM | `http://127.0.0.1:4000/v1` |
| Qdrant | `http://127.0.0.1:6333` |

## Required Aliases

- `local_chat`
- `local_think`
- `local_rag`
- `local_json`
- `quimera_embed`
- `local_embed`

`quimera_embed` is the canonical application-facing embedding alias.
`local_embed` remains a compatibility alias.

## Required Environment Variables

```bash
export LITELLM_MASTER_KEY="dev-local-key-change-me"
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
export QUIMERA_LLM_BASE_URL="http://127.0.0.1:4000/v1"
export OLLAMA_API_BASE="http://127.0.0.1:11434"
export QDRANT_URL="http://127.0.0.1:6333"
```

Do not commit real secrets. `.env` is not required and must not be modified by
Gateway-0 readiness scripts.

## Start And Stop Ollama

Start:

```bash
ollama serve
```

Pull required models:

```bash
ollama pull qwen3:14b
ollama pull nomic-embed-text
ollama list
```

Check:

```bash
curl -fsS http://127.0.0.1:11434/api/tags
```

Stop:

```bash
pkill -f "ollama serve"
```

If Ollama is managed by a desktop/service manager, stop it through that
manager instead.

## Start And Stop Qdrant

Start:

```bash
docker compose -f docker/docker-compose.qdrant.yml up -d
```

Check:

```bash
curl -fsS http://127.0.0.1:6333/healthz
```

Stop:

```bash
docker compose -f docker/docker-compose.qdrant.yml down
```

Do not delete, recreate, or reindex `openclaw_knowledge` without an explicit
future sprint.

## Start And Stop LiteLLM

Install once:

```bash
cd infra/litellm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start:

```bash
cd infra/litellm
source .venv/bin/activate
export LITELLM_MASTER_KEY="dev-local-key-change-me"
export OLLAMA_API_BASE="http://127.0.0.1:11434"
export QWEN_MODEL="qwen3:14b"
export EMBED_MODEL="nomic-embed-text"
./start_litellm.sh
```

Stop:

```bash
ps aux | grep '[l]itellm'
kill <pid>
```

If LiteLLM is running in the foreground, use `Ctrl-C`.

## Readiness Commands

Static, CI-safe readiness:

```bash
scripts/check_gateway_readiness.sh
```

Live local readiness:

```bash
export LITELLM_MASTER_KEY="dev-local-key-change-me"
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/check_gateway_readiness.sh --live
```

Default mode is static and does not require network, secrets, live services,
Qdrant mutation, or access to `openclaw_knowledge`.

## Smoke Commands

Gateway runtime smoke:

```bash
scripts/test_opencraw_litellm_runtime.sh
RUN_LITELLM_SMOKE=1 uv run pytest tests/smoke/test_gateway_runtime_smoke.py -v
```

Embedding smoke:

```bash
scripts/test_local_embed_litellm.sh
RUN_LITELLM_EMBED_SMOKE=1 uv run pytest tests/smoke/test_gateway_embed_smoke.py -v
```

Synthetic RAG E2E smoke:

```bash
scripts/test_rag_e2e_gateway.sh
RUN_RAG_E2E_SMOKE=1 uv run pytest tests/smoke/test_rag_e2e_gateway_smoke.py -v
```

GW-08 controlled embedding migration smoke:

```bash
scripts/test_gw08_embedding_migration.sh
RUN_GW08_EMBEDDING_MIGRATION_SMOKE=1 \
RUN_GW08_EMBEDDING_PARITY_SMOKE=1 \
uv run pytest tests/smoke/test_rag_gateway_embedding_migration_smoke.py -v -s
```

Smoke tests are skipped by default. Live proof is explicit and must not become
a normal CI requirement.

## Rollback Commands

Rollback controlled embeddings to direct Ollama:

```bash
export QUIMERA_RAG_EMBEDDING_BACKEND="direct_ollama"
```

Return to gateway embeddings:

```bash
unset QUIMERA_RAG_EMBEDDING_BACKEND
```

Restart LiteLLM after alias/config changes:

```bash
cd infra/litellm
source .venv/bin/activate
./start_litellm.sh
```

No automatic reindexing is performed. Existing collections must not mix vectors
from different embedding models, dimensions, providers, or backends.

## Interpreting RagRunTrace

`RagRunTrace` is emitted once per completed RAG query as:

```text
logger.bind(trace=trace.to_log_dict()).log(log_level, "rag_run_trace")
```

It records safe provenance metadata: query id, timestamp, collection,
embedding backend/model/alias/dimensions, chunk count, gateway alias, and
latencies. It never records query text, prompts, answers, chunks, vectors,
payloads, portfolio data, API keys, Authorization headers, tokens, passwords
or secrets.

## Interpreting RagObservabilityEvent

`RagObservabilityEvent` is emitted for lifecycle stages as:

```text
logger.bind(event=event.to_log_dict()).log(log_level, "rag_lifecycle_event")
```

It records safe scalar metadata for embedding, retrieval, generation and
guard-related lifecycle stages. It is not OpenTelemetry, distributed tracing,
remote telemetry, profiling or a dashboard.

## Security Checklist

- `.env` untouched.
- No secrets committed.
- No Authorization headers printed.
- No real portfolio data or private documents in prompts or logs.
- Remote provider aliases disabled.
- URLs must be loopback: `127.0.0.1` or `localhost`.
- Qdrant production collections are not mutated by readiness checks.
- `openclaw_knowledge` is not ingested, reindexed, deleted or recreated by
  Gateway-0 readiness.
- Live smoke uses synthetic data only.

## No Remote Provider Policy

Gateway-0 is local only. Active configs must not contain OpenAI, Anthropic,
Gemini, Google, OpenRouter, xAI or Azure provider model prefixes or remote API
key environment markers.

Future remote providers require:

- explicit ADR;
- sanitization policy;
- budget controls;
- audit logging;
- Level 0 data exclusion.

## Troubleshooting Matrix

| Symptom | Likely cause | Check / Fix |
|---|---|---|
| LiteLLM down | Proxy not started | `cd infra/litellm && ./start_litellm.sh` |
| Ollama down | Ollama service stopped | `ollama serve`; `curl -fsS http://127.0.0.1:11434/api/tags` |
| Qdrant down | Docker service stopped | `docker compose -f docker/docker-compose.qdrant.yml up -d` |
| Missing Qwen model | `qwen3:14b` not pulled | `ollama pull qwen3:14b`; `ollama list` |
| Missing nomic embed model | `nomic-embed-text` not pulled | `ollama pull nomic-embed-text`; `ollama list` |
| Wrong key | `QUIMERA_LLM_API_KEY` differs from `LITELLM_MASTER_KEY` | Re-export both in the same shell; do not print them |
| Missing alias | LiteLLM did not reload config | restart LiteLLM and run `infra/litellm/test_models.sh` |
| Remote URL rejected | URL is not loopback | use `http://127.0.0.1:<port>` or `http://localhost:<port>` |
| Embedding dimension mismatch | collection/model/config drift | stop ingest, inspect metadata, reindex only in explicit future sprint |
| Qdrant metadata drift | existing collection predates migration or backend changed | collection guard warns; do not mix vectors silently |
| Smoke skipped by default | guard env var not set | set the explicit `RUN_*_SMOKE=1` guard |
| Healthcheck remote marker failure | active config contains remote provider marker | remove active remote provider; comments alone are allowed |

## Housekeeping Commands

Inspect stale GitHub work manually:

```bash
gh pr list --state open
gh issue list --state open
```

Close obsolete PRs or issues only after human confirmation:

```bash
gh pr close <number>
gh issue close <number>
```

Readiness scripts must never close PRs or issues automatically.

## Supply Chain Note

`infra/litellm/requirements.txt` excludes LiteLLM `1.82.7` and `1.82.8` and
requires the post-incident `1.83.x` line or newer compatible `1.x` release.
GW-12 does not introduce new dependencies or provider SDK changes.
