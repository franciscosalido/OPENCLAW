# RAG Runbook — Quimera/OpenClaw

This runbook operates RAG-0 locally. It uses synthetic data only.

## Safety

- Do not use real portfolio, brokerage, credential, or private document data.
- Do not read `.env` or `.env.*`.
- Do not call remote AI providers.
- Do not add LiteLLM, Redis, FastAPI, LangChain, or sentence-transformers in RAG-0.

## Prerequisites

```bash
uv sync
ollama pull qwen3:14b
ollama pull nomic-embed-text
docker compose -f docker/docker-compose.qdrant.yml up -d
```

Check services:

```bash
curl -fsS http://localhost:11434/api/tags
curl -fsS http://localhost:6333/healthz
```

## Ingest Synthetic Documents

Dry run without Ollama or Qdrant:

```bash
uv run python scripts/rag_ingest_synthetic.py --dry-run
```

Real local ingest:

```bash
uv run python scripts/rag_ingest_synthetic.py
```

Expected output per document:

- document id
- chunk count
- embedding latency
- upsert confirmation

## Ask Local RAG

Default factual mode uses `/no_think`:

```bash
uv run python scripts/rag_ask_local.py "Qual o impacto sintetico da Selic?" --verbose
```

Thinking mode is opt-in:

```bash
uv run python scripts/rag_ask_local.py "Riscos de concentracao" --thinking --top-k 3
```

MVP policy:

- RAG/Qdrant factual calls prefer `/no_think`.
- `thinking_mode=True` is reserved for explicit CLI use and future Gateway-0 routing.
- Future OpenCraw or selected agent calls may set `thinking_mode=True` through LiteLLM/Gateway-0.

## Validation

```bash
uv run pytest -v
uv run mypy --explicit-package-bases --strict backend/rag scripts tests/unit tests/integration tests/smoke
uv run pyright backend/rag scripts tests/unit tests/integration tests/smoke
uv run python -m py_compile backend/rag/*.py scripts/*.py tests/unit/*.py tests/integration/*.py tests/smoke/*.py
```

Forbidden import scan:

```bash
rg -n "LangChain|sentence_transformers|from openai|import openai|anthropic|LiteLLM|Redis|FastAPI|remote" backend scripts tests || true
```

Duplicated validation check (looks for the old private function definition, not test method names):

```bash
rg -n "^def _validate_question" backend/ tests/ || echo "OK — no duplicates"
```

## Troubleshooting

Qdrant unavailable:

```bash
docker compose -f docker/docker-compose.qdrant.yml ps
docker compose -f docker/docker-compose.qdrant.yml logs qdrant
docker compose -f docker/docker-compose.qdrant.yml up -d
```

Ollama unavailable:

```bash
ollama list
ollama ps
curl -fsS http://localhost:11434/api/tags
```

Missing embedding model:

```bash
ollama pull nomic-embed-text
```

Qdrant version warning:

- Docker server is pinned in `docker/docker-compose.qdrant.yml`.
- Python client is pinned in `pyproject.toml`.
- Recreate or sync the virtual environment after version changes.
