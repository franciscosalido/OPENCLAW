# Gateway Sprint Handoff

> Start each Gateway cycle by reading this file before touching Git.

**Last updated:** 2026-04-28
**Repository:** OpenClaw
**Product:** Quimera
**Sprint:** Gateway-0 / LiteLLM

---

## Mandatory GitHub Workflow

GitHub is the source of truth for issues, branches, pull requests, review state,
and merge state. The local checkout is a work area, not the final integration
point.

For every tracked PR:

1. Sync local `main`.
2. Open or update a GitHub Issue before implementation.
3. Create the feature branch from updated `main`.
4. Implement locally.
5. Run relevant validations locally.
6. Commit with clear atomic messages.
7. Push the feature branch.
8. Open a GitHub PR from the feature branch to `main`.
9. Link the PR to the issue.
10. Address review comments on the same branch.
11. Merge only in GitHub after approval.
12. After GitHub merge, sync local `main` with `--ff-only`.

Canonical start:

```bash
cd /Users/fas/projetos/OPENCLAW
git checkout main
git pull --ff-only origin main
```

Never push directly to `main`. Never use `git push --force`; if a rebase is
unavoidable, use `git push --force-with-lease`.

---

## Current Status

Current active branch:

```text
feat/gateway-local-embed-evaluation
```

Current issue:

```text
https://github.com/franciscosalido/OPENCLAW/issues/30
```

Gateway baseline already merged:

```text
GW-01 through GW-04 are merged in 92c0ec5.
GW-05a is merged in 96278f6.
GW-05b live smoke fixes are merged through 5c42547.
GW-06 branches from the post-GW-05b baseline.
```

Gateway PR state:

| PR | Branch | Scope | Status |
|---|---|---|---|
| GW-01 | `feat/gateway-prep-contracts` | Gateway contracts, ADR, Blueprint, semantic aliases | Merged in `92c0ec5` |
| GW-02 | `feat/gateway-install-health` | Local-only LiteLLM install and health scripts | Merged in `92c0ec5` |
| GW-03 | `feat/gateway-route-opencraw-litellm` | OpenClaw runtime chat through LiteLLM | Merged in `92c0ec5` |
| GW-04 | `feat/gateway-runtime-smoke` | Shared validation, optional smoke, observability | Merged in `92c0ec5` |
| GW-05a | `feat/gateway-per-alias-timeouts` | Per-alias timeout configuration | Merged in `96278f6` |
| GW-05b | `feat/gateway-live-smoke-timeouts` | Live smoke with effective timeout observability | Merged through `5c42547` |
| GW-06 | `feat/gateway-local-embed-evaluation` | Evaluate embeddings via `local_embed` | Current |
| GW-07 | TBD | Synthetic RAG E2E through gateway path | Planned |

---

## GW-05a Contract

Objective:

Add per-alias timeout configuration for semantic LiteLLM aliases without
changing the runtime architecture.

Timeout contract:

| Alias | Timeout | Notes |
|---|---:|---|
| `local_chat` | 30.0s | Default chat |
| `local_think` | 120.0s | Longer reasoning/planning calls |
| `local_rag` | 60.0s | RAG answer synthesis |
| `local_json` | 30.0s | Structured responses |
| `local_embed` | 30.0s | Placeholder only; not used for embeddings yet |

Resolution rules:

- If the request alias exists in `per_alias_timeouts`, use that timeout.
- If the alias is unknown, use global `timeout_seconds`.
- If the alias is `None`, use global `timeout_seconds`.
- Reject zero, negative, infinite, or NaN timeout values.

Out of scope:

- Live smoke expansion.
- FastAPI.
- MCP.
- Remote providers.
- Quant tools.
- Embeddings through LiteLLM.
- Qdrant/retrieval/chunking changes.
- Prompt builder changes.
- Autoprogramming.

---

## GW-06 Current Work

Objective:

Evaluate whether the `local_embed` semantic alias can safely return embeddings
through LiteLLM without changing the default RAG embedding path.

Scope:

- Add an experimental `GatewayEmbedClient` for OpenAI-compatible
  `/embeddings` calls.
- Validate single and small-batch synthetic inputs.
- Validate 768-dimensional numeric vectors.
- Add optional live smoke guarded by `RUN_LITELLM_EMBED_SMOKE=1`.
- Add a local script for one synthetic `local_embed` call.
- Compare direct Ollama and LiteLLM dimensions when live services are available.

Out of scope:

- Replacing `backend.rag.embeddings.OllamaEmbedder`.
- Routing production RAG embeddings through LiteLLM.
- Reindexing Qdrant.
- Real documents, real portfolio data, or private files.
- FastAPI, MCP, remote providers, quant tools, and autoprogramming.

Decision status:

- **Approved for future migration** after live local evaluation on 2026-04-28.
- Current RAG remains direct via Ollama in GW-06.
- A future migration PR must preserve or replace the current direct embedder's
  retry/backoff/concurrency behavior before switching defaults.

Live evaluation results:

| Check | Result |
|---|---|
| `RUN_LITELLM_EMBED_SMOKE=1 uv run pytest tests/smoke/test_gateway_embed_smoke.py -v` | 2/2 passed |
| `scripts/test_local_embed_litellm.sh` | passed |
| Single embedding | 768 dimensions, 0.08s pytest / 0.70s script |
| Batch embedding | 2 vectors, 768 dimensions each, 0.05s |
| Direct Ollama parity | 768 dimensions |
| Cosine similarity | 1.000000 |

Environment:

- macOS local development machine.
- LiteLLM: `127.0.0.1:4000`.
- Ollama: `127.0.0.1:11434`.
- Embed alias: `local_embed`.
- Direct model: `nomic-embed-text`.

## Previous Work

GW-05b:

- Add `timeout_s` to gateway debug logs for diagnosis of overruns.
- Run expanded live smoke with LiteLLM and Ollama already running.
- Keep smoke opt-in with `RUN_LITELLM_SMOKE=1`.
- Use only synthetic prompts and local aliases.
- Validate each alias against `GatewayRuntimeConfig.resolve_timeout(alias)`.
- Support `RUN_LITELLM_SMOKE_REPEAT`, capped at 5, for repeated local probes.
- Do not claim live smoke has passed until it has actually run with services.
- If local services are unavailable, document that live smoke was not run.

Current live smoke status:

- **2026-04-28: PASSED** — all 4 aliases responded within budget.
- Ollama: `127.0.0.1:11434` — qwen3:14b (9.3 GB Q4_K_M), nomic-embed-text.
- LiteLLM: `127.0.0.1:4000` — provider `ollama_chat/qwen3:14b`.

Observed latencies (2026-04-28, macOS, qwen3:14b Q4_K_M):

| Alias | elapsed_s | timeout_s | margin |
|---|---:|---:|---|
| `local_chat` | 2.20 | 30.0 | 27.8s |
| `local_think` | 12.44 | 120.0 | 107.6s |
| `local_rag` | 2.23 | 60.0 | 57.8s |
| `local_json` | 1.72 | 30.0 | 28.3s |

`RUN_LITELLM_SMOKE_REPEAT=3` passed (7/7 tests, 54s wall time).

Config fixes applied in GW-05b to make smoke pass:

- `start_litellm.sh`: default provider changed from `ollama/` to `ollama_chat/`
  (uses `/api/chat` endpoint — required for Qwen3 chat format).
- `litellm_config.yaml`: `extra_body: {think: false}` added to `local_chat`,
  `local_rag`, `local_json` to prevent thinking tokens exhausting max_tokens
  before visible content is produced. `local_think` keeps thinking active.
- Smoke scripts: `max_tokens=2048` for `local_think`; 96 for other aliases.

GW-07:

- Run synthetic RAG E2E over the approved gateway path.
- Keep all data fictitious and local.

---

## Validation Checklist

Before opening GW-06 PR:

```bash
git status --short --branch
git diff --stat
git diff --check
uv run pytest -v
uv run mypy --strict .
uv run pyright
uv run python -m compileall backend tests scripts infra
uv run pytest tests/unit/test_gateway_embed_client.py -v
uv run pytest tests/smoke/ -v
```

Expected embedding smoke behavior without `RUN_LITELLM_EMBED_SMOKE=1`: smoke
tests skip, not fail.

Optional live checks when local services and credentials are already available:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
RUN_LITELLM_EMBED_SMOKE=1 uv run pytest tests/smoke/test_gateway_embed_smoke.py -v
scripts/test_local_embed_litellm.sh
```
