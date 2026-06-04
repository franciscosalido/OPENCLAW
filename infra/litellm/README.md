# LiteLLM Local Gateway

This directory contains the operational Gateway-0 layer for Quimera/OpenClaw.
It starts LiteLLM as a local-only proxy in front of Ollama. OpenClaw runtime
calls are not routed through LiteLLM yet.

## Security Contract

- Bind only to `127.0.0.1`.
- Do not commit real secrets.
- Do not enable OpenAI, Anthropic, Gemini, or any remote provider.
- Do not use real portfolio data, private financial data, or private documents
  in test prompts.
- Do not print `LITELLM_MASTER_KEY`.
- Keep RAG data in Qdrant. LiteLLM handles model calls only.

## Install

```bash
cd infra/litellm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Supply-chain note: LiteLLM versions `1.82.7` and `1.82.8` were compromised on
PyPI in March 2026. This directory excludes those versions and requires a
post-incident `1.83.x` release line.

## Prepare Ollama

```bash
ollama --version
ollama pull qwen3:14b
ollama pull nomic-embed-text
ollama list
```

## Configure Environment

Use shell exports. Do not copy real secrets into Git.

```bash
export LITELLM_MASTER_KEY="dev-local-key-change-me"
export OLLAMA_BASE_URL="http://127.0.0.1:11434"
export QWEN_MODEL="qwen3:14b"
export EMBED_MODEL="nomic-embed-text:latest"
export LITELLM_HOST="127.0.0.1"
export LITELLM_PORT="4000"
```

LiteLLM supports `os.environ/VAR_NAME` when the whole YAML value comes from the
environment. Because model names need an `ollama/` prefix, `start_litellm.sh`
derives `LITELLM_LOCAL_CHAT_MODEL` and `LITELLM_LOCAL_EMBED_MODEL` from
`QWEN_MODEL` and `EMBED_MODEL`.

## Start

Recommended through the stack controller:

```bash
./scripts/start_quimera.sh litellm-validate
./scripts/start_quimera.sh litellm-render
./scripts/start_quimera.sh litellm-start
./scripts/start_quimera.sh litellm-smoke
./scripts/start_quimera.sh litellm-audit
./scripts/start_quimera.sh litellm-benchmark
```

`scripts/start_quimera.sh start` also starts or reuses host LiteLLM after
Postgres and Qdrant are ready.

Docker Compose does not manage LiteLLM in Quimera. Compose owns Postgres and
Qdrant only; LiteLLM remains a host Python process on `127.0.0.1:4000`.

The source config is `infra/litellm/litellm_config.yaml`. The generated runtime
config is `infra/litellm/generated/litellm_config.runtime.yaml`; it is local and
not versioned.

```bash
./start_litellm.sh
```

The script refuses to bind to anything other than `127.0.0.1`.
If the placeholder key from `.env.local.example` is still in use, the stack
controller prints a warning. Rotate it for any shared runtime.

`litellm-audit` writes safe local reports to `.runtime/reports/`. The audit
includes config contracts, endpoint probes, cache policy and version
fingerprints. `litellm-benchmark` is opt-in; without
`QUIMERA_LITELLM_BENCHMARK=1`, it returns `SKIPPED_VALID` and does not call a
model.

## Validate

`healthcheck.sh` requires `LITELLM_MASTER_KEY` to be exported. The runtime
client uses `QUIMERA_LLM_API_KEY` as the Bearer token; it must match
`LITELLM_MASTER_KEY`.

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

Expected checks:

- `/v1/models` responds.
- `/health/readiness` and `/health/liveliness` respond.
- All five local aliases are visible.
- `local_chat` returns a compact answer through LiteLLM.
- Ollama is reachable.
- No active remote provider appears in the LiteLLM config.

Avoid using `/health` as the default probe because LiteLLM uses it for model
health checks.

## Semantic Cache

The source config declares Qdrant semantic cache for the LLM gateway with
collection `quimera_llm_cache`. The retrieval cache collection remains
`quimera_query_cache`; these collections must never be merged.

The renderer keeps Qdrant semantic cache only when
`QUIMERA_LITELLM_QDRANT_SEMANTIC_EXPERIMENTAL=1` and Qdrant is reachable at
`QDRANT_API_BASE`. Otherwise it writes a runtime config with local cache.

## Stop

```bash
./scripts/start_quimera.sh litellm-stop
```

The stop path reads only `.runtime/litellm.pid`, sends SIGTERM to that PID, and
uses SIGKILL only for the same PID after the grace loop. It does not use
`pkill` or `killall`.

## MVP Boundary

FastAPI is intentionally not used in this PR. Gateway-0 should prove the local
LiteLLM operational path before adding any service layer.

RAG is not routed directly through LiteLLM yet. Qdrant remains the vector store,
and the Python RAG modules still own chunking, retrieval, context packing, and
prompt construction.

## Future Directions

Multi-agent and MCP integration will be introduced only after the local gateway
path is validated end-to-end. The intended sequence is:

1. Route OpenClaw runtime model calls through the LiteLLM gateway (PR3).
2. Validate the full RAG → LiteLLM → Ollama path in a smoke test.
3. Introduce multi-agent coordination contracts once the single-agent path is stable.
4. Add MCP tool bindings as an explicit sprint after agent contracts are defined.

Remote providers and external API access remain out of scope until a dedicated
sanitisation and audit sprint is approved.

MCP and broader tooling integration remain explicitly out of scope until the
local LiteLLM runtime path is stable and reviewed.
