# OpenClaw LiteLLM Runtime

PR 3 routes OpenClaw runtime chat generation through the local LiteLLM gateway.
PR 4 adds optional live smoke tests for that route.
GW-05a adds per-alias request timeout budgets for semantic local aliases.
GW-05b adds live smoke timing validation and logs the effective timeout budget
used by each gateway call.
GW-06 evaluates `local_embed` embeddings through LiteLLM without changing the
default RAG embedding path.
GW-07 adds optional synthetic RAG E2E smoke for the current production-safe path:
direct Ollama embeddings, temporary Qdrant collection, and LiteLLM generation.
The default runtime path is:

```text
OpenClaw -> http://127.0.0.1:4000/v1 -> LiteLLM -> Ollama/Qwen local
```

## Environment Variables

```bash
export QUIMERA_LLM_BASE_URL="http://127.0.0.1:4000/v1"
export QUIMERA_LLM_API_KEY="dev-local-key-change-me"
export QUIMERA_LLM_MODEL="local_chat"
export QUIMERA_LLM_REASONING_MODEL="local_think"
export QUIMERA_LLM_RAG_MODEL="local_rag"
export QUIMERA_LLM_JSON_MODEL="local_json"
export QUIMERA_LLM_EMBED_MODEL="local_embed"
```

`QUIMERA_LLM_API_KEY` should match the local `LITELLM_MASTER_KEY` used to start
LiteLLM. Do not commit either value.

## Start Ollama

Ensure Ollama is running and the local models are available:

```bash
ollama serve
ollama pull qwen3:14b
ollama pull nomic-embed-text
ollama list
```

## Start LiteLLM

Use the local-only operational scripts from PR 2:

```bash
cd infra/litellm
source .venv/bin/activate
export LITELLM_MASTER_KEY="dev-local-key-change-me"
export OLLAMA_API_BASE="http://127.0.0.1:11434"
export QWEN_MODEL="qwen3:14b"
export EMBED_MODEL="nomic-embed-text"
./start_litellm.sh
```

In another shell:

```bash
export QUIMERA_LLM_API_KEY="dev-local-key-change-me"
scripts/test_opencraw_litellm_runtime.sh
```

## Optional Live Smoke Tests

Smoke tests are skipped by default so normal CI and local unit runs do not
require LiteLLM or Ollama.

Run the script smoke:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/test_opencraw_litellm_runtime.sh
```

Run the pytest smoke:

```bash
RUN_LITELLM_SMOKE=1 uv run pytest tests/smoke -v
```

Repeat each live alias probe up to a small capped count:

```bash
RUN_LITELLM_SMOKE=1 RUN_LITELLM_SMOKE_REPEAT=3 uv run pytest tests/smoke -v
```

The live smoke tests exercise only synthetic prompts and these local aliases:

- `local_chat`
- `local_think`
- `local_rag`
- `local_json`

They do not require Qdrant, embeddings, real portfolio data, or remote
providers.

Smoke is skipped by default. `RUN_LITELLM_SMOKE=1` is required so normal unit
test runs do not depend on local services.

## Optional Embedding Evaluation

GW-06 evaluates the reserved `local_embed` alias through LiteLLM. This is an
evaluation path only:

```text
GatewayEmbedClient -> LiteLLM /v1/embeddings -> Ollama/nomic-embed-text
```

The current RAG embedding path remains unchanged:

```text
RAG / OllamaEmbedder -> Ollama direct /api/embed
```

Run the guarded pytest smoke when LiteLLM and Ollama are already running:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
RUN_LITELLM_EMBED_SMOKE=1 uv run pytest tests/smoke/test_gateway_embed_smoke.py -v
```

Run the compact script smoke:

```bash
scripts/test_local_embed_litellm.sh
```

The embedding evaluation uses synthetic text only. It does not require Qdrant,
does not reindex any collection, does not read real documents, and does not use
real portfolio data.

Interpretation:

- `dims=768` means the expected `nomic-embed-text` vector shape is present.
- Batch success means LiteLLM accepts a small list of synthetic inputs.
- Direct Ollama parity checks compare dimensions and log cosine similarity as
  evidence; they do not require byte-identical vectors.
- Latency should be recorded before any future migration decision.
- GW-06 live evidence recorded 768-dimensional vectors, batch support, and
  cosine similarity `1.000000` against direct Ollama for the synthetic probe.
- Decision status is **Approved for future migration**, but the default RAG
  embedder remains direct Ollama until a future migration PR preserves or
  replaces retry/backoff/concurrency behavior.

## Optional Synthetic RAG E2E Smoke

GW-07 proves the current RAG path end to end with synthetic data only:

```text
synthetic docs
  -> chunking
  -> OllamaEmbedder direct /api/embed
  -> Qdrant temporary collection
  -> Retriever / ContextPacker / PromptBuilder
  -> LocalGenerator / GatewayChatClient
  -> LiteLLM /v1/chat/completions
  -> Ollama / Qwen local
```

Embeddings remain direct through `OllamaEmbedder` in GW-07. The test records
the GW06C embedding metadata contract in the temporary chunks, including
`quimera_embed`, but it does not route production embeddings through LiteLLM.

Run the compact script when Qdrant, Ollama, LiteLLM, and the local gateway key
are already available:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/test_rag_e2e_gateway.sh
```

Run pytest directly:

```bash
RUN_RAG_E2E_SMOKE=1 uv run pytest tests/smoke/test_rag_e2e_gateway_smoke.py -v
```

GW-07 smoke is skipped by default. It uses a unique temporary Qdrant collection
named `gw07_synthetic_rag_<short_uuid>` and attempts prefix-guarded deletion
during teardown. It never uses or deletes `openclaw_knowledge`.

If a run is interrupted, teardown may not complete. Clean up manually only by
deleting collections whose names start with `gw07_synthetic_rag_`.

The synthetic corpus is PT-BR and fictitious. It contains no real portfolio
data, no real tickers, no private documents, no patient data, and no remote
provider calls.

Qdrant creates the temporary collection with vector size `768` and cosine
distance, matching the local `nomic-embed-text` embedding metadata. Collection
payloads include provider, model, dimensions, version, contract, alias, and
backend so future reindexing decisions can be audited.

GW-07 live result recorded on 2026-04-30:

| Stage | Latency |
|---|---:|
| embedding/indexing | 178.1 ms |
| retrieval | 18.4 ms |
| generation through `local_rag` | 3621.2 ms |
| total pipeline | 3639.6 ms |

The run used 3 synthetic PT-BR documents, generated 14 chunks, used 5 retrieved
chunks, and completed cleanup of the temporary collection without reported
errors. Future interrupted runs may still require manual prefix-only cleanup.

## What Changed

- `backend.rag.generator.LocalGenerator` now sends OpenAI-compatible
  `/chat/completions` requests to LiteLLM.
- The default base URL is `http://127.0.0.1:4000/v1`.
- The default chat alias is `local_chat`.
- RAG CLI calls use `local_rag` by default and `local_think` when `--thinking`
  is selected.
- Gateway calls emit minimal debug observability: alias, base URL host, latency,
  effective timeout budget, success/failure status, and error category. API
  keys and prompt text are not logged.
- GW-05a resolves request timeouts per alias: `local_chat` 30s, `local_think`
  120s, `local_rag` 60s, `local_json` 30s, and `local_embed` 30s placeholder.
  Unknown aliases and `None` still fall back to the global `timeout_seconds`.

## What Did Not Change

- Qdrant remains the vector store.
- RAG chunking, embeddings, retrieval, context packing, and citation logic are
  unchanged.
- Embeddings still use the existing local Ollama embedder until a separate,
  tested embedding-gateway PR is approved.
- `local_embed` has a reserved timeout value only. GW-05a does not route
  embeddings through LiteLLM.
- GW-06 evaluates `local_embed` but does not wire it into default RAG behavior.
- GW-07 does not migrate embeddings; it keeps direct Ollama embeddings and uses
  LiteLLM only for answer generation.
- GW-07 does not touch production Qdrant collections or `openclaw_knowledge`.
- Remote providers remain disabled.
- FastAPI remains postponed.
- MCP and tooling integration remain future direction, not implemented in
  Gateway-0.
- Live smoke expansion belongs to GW-05b (PR 6). GW-05a does not modify smoke
  test scope or activation behavior.

## Timeout Failures

A live smoke timeout failure means the alias exceeded its effective timeout
budget plus a small test harness overhead margin. Check:

- LiteLLM is running on `127.0.0.1:4000`.
- Ollama is running on `127.0.0.1:11434`.
- Qwen is pulled and not still loading.
- The machine has enough memory for the local model.
- `local_think` may legitimately need more wall time on slower hardware.

Do not hide a `local_think` overrun by weakening assertions silently. Record the
observed latency and decide in review whether to keep the contract, use a
smaller local model, or adjust the timeout in a follow-up.

## Troubleshooting

LiteLLM is not running:

```bash
cd infra/litellm
./start_litellm.sh
```

Ollama is not running:

```bash
ollama serve
curl -fsS http://127.0.0.1:11434/api/tags
```

Wrong API key:

- Ensure `QUIMERA_LLM_API_KEY` matches `LITELLM_MASTER_KEY`.
- Do not print either value in logs or terminal captures.

Missing model alias:

```bash
cd infra/litellm
./test_models.sh
```

Model not pulled:

```bash
ollama pull qwen3:14b
ollama pull nomic-embed-text
ollama list
```

Direct Ollama call accidentally configured:

- Runtime chat defaults should use semantic aliases only.
- Vendor model names such as Qwen, GPT, Claude, Gemini, or Ollama provider
  strings belong in LiteLLM configuration, not application-facing defaults.
