# OPENCLAW — Development Setup

## Environment variables

All local secrets live in a `.env` file at the project root.
`.env` is gitignored and must never be committed.
Use `.env.example` as the reference template:

```bash
cp .env.example .env
# Edit .env — set LITELLM_MASTER_KEY and QUIMERA_LLM_API_KEY to the same value
```

`QUIMERA_LLM_API_KEY` must match the `LITELLM_MASTER_KEY` used to start the
LiteLLM gateway (`infra/litellm/start_litellm.sh`).

---

## Running commands with environment variables

`uv run` does **not** auto-load `.env`. Always pass `--env-file .env`:

```bash
# Run tests
uv run --env-file .env pytest tests/unit/ -v

# Run type checks (no env needed — pure static analysis)
uv run mypy backend/ --strict
uv run pyright backend/

# Run any script
uv run --env-file .env python scripts/<script>.py
```

### Key scripts

```bash
# Start LiteLLM gateway (must have LITELLM_MASTER_KEY exported first)
set -a && source .env && set +a
cd infra/litellm && source .venv/bin/activate && ./start_litellm.sh

# RAG queries
uv run --env-file .env python scripts/rag_ask_local.py "Qual a projeção da Selic?"

# RAG latency baseline (opt-in — requires all services running)
RUN_RAG_LATENCY_BASELINE=1 uv run --env-file .env python \
  scripts/run_rag_latency_baseline.py --output-dir reports/g2_latency_baseline

# GW-20 proof-of-life smoke
RUN_GATEWAY1_PROOF_OF_LIFE=1 uv run --env-file .env python \
  scripts/test_gateway1_proof_of_life.py
```

---

## Services required for integration / smoke tests

| Service | Start command | Health check |
|---|---|---|
| Qdrant | `docker compose -f docker/docker-compose.qdrant.yml up -d` | `curl http://localhost:6333/healthz` |
| Ollama | `ollama serve` | `curl http://localhost:11434/api/tags` |
| LiteLLM | `set -a && source .env && set +a && cd infra/litellm && source .venv/bin/activate && ./start_litellm.sh` | `curl -H "Authorization: Bearer $QUIMERA_LLM_API_KEY" http://localhost:4000/health` |

---

## Security levels

| Level | Description | Rule |
|---|---|---|
| 0 | Portfolio data, credentials, CPF, tokens | Never leave the machine |
| 1 | Macro analysis, sector analysis (sanitized) | Remote only after stripping asset names and values |
| 2 | Public research, editorial review | Remote OK |
