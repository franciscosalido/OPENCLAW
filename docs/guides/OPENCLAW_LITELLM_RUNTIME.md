# OpenClaw LiteLLM Runtime

PR 3 routes OpenClaw runtime chat generation through the local LiteLLM gateway.
PR 4 adds optional live smoke tests for that route.
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
```

`QUIMERA_LLM_API_KEY` should match the local `LITELLM_MASTER_KEY` used to start
LiteLLM. Do not commit either value.

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

The live smoke tests exercise only synthetic prompts and these local aliases:

- `local_chat`
- `local_think`
- `local_rag`
- `local_json`

They do not require Qdrant, embeddings, real portfolio data, or remote
providers.

## What Changed

- `backend.rag.generator.LocalGenerator` now sends OpenAI-compatible
  `/chat/completions` requests to LiteLLM.
- The default base URL is `http://127.0.0.1:4000/v1`.
- The default chat alias is `local_chat`.
- RAG CLI calls use `local_rag` by default and `local_think` when `--thinking`
  is selected.
- Gateway calls emit minimal debug observability: alias, base URL host, latency,
  success/failure status, and error category. API keys and prompt text are not
  logged.

## What Did Not Change

- Qdrant remains the vector store.
- RAG chunking, embeddings, retrieval, context packing, and citation logic are
  unchanged.
- Embeddings still use the existing local Ollama embedder until a separate,
  tested embedding-gateway PR is approved.
- Remote providers remain disabled.
- FastAPI remains postponed.
- MCP and tooling integration are not implemented in PR 3 or PR 4.

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
