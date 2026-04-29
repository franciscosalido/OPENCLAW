# LiteLLM Local Gateway

This directory contains the operational Gateway-0 layer for Quimera/OpenClaw.
It starts LiteLLM as a local-only proxy in front of Ollama. OpenClaw runtime
chat/generation calls route through LiteLLM; production RAG embeddings remain
direct Ollama until an explicit migration PR.

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
export OLLAMA_API_BASE="http://127.0.0.1:11434"
export QWEN_MODEL="qwen3:14b"
export EMBED_MODEL="nomic-embed-text"
export LITELLM_HOST="127.0.0.1"
export LITELLM_PORT="4000"
```

LiteLLM supports `os.environ/VAR_NAME` when the whole YAML value comes from the
environment. Because model names need an `ollama/` prefix, `start_litellm.sh`
derives `LITELLM_LOCAL_CHAT_MODEL` and `LITELLM_LOCAL_EMBED_MODEL` from
`QWEN_MODEL` and `EMBED_MODEL`.

## Start

```bash
./start_litellm.sh
```

The script refuses to bind to anything other than `127.0.0.1`.

## Validate

In another shell with the same environment variables:

```bash
cd infra/litellm
source .venv/bin/activate
./test_models.sh
./test_local_chat.sh
./healthcheck.sh
```

Expected checks:

- `/v1/models` responds.
- All local aliases are visible, including `quimera_embed` and compatibility
  alias `local_embed`.
- `local_chat` returns a compact answer through LiteLLM.
- Ollama is reachable.
- No active remote provider appears in the LiteLLM config.

## Stop

If LiteLLM runs in the foreground, stop it with `Ctrl-C`.

If you started it in a background shell, find and stop that process manually:

```bash
ps aux | grep '[l]itellm'
kill <pid>
```

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
