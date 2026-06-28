# FINLIB-0 FL-PR13 - Memory Boundary

Branch: `feat/finlib-memory-boundary`
GitHub Issue: `#122`
Status: Initial SDD

## Objective

FL-PR13 turns the Qdrant/PostgreSQL/TimescaleDB/pgvector/Markdown boundary
into an executable architectural contract.

This PR does not implement LongRAG. It does not create migrations, tables,
retrievers, agents, ingestion jobs, Qdrant mutations, pgvector retrieval paths
or FINLIB repository changes. Its job is to make the current boundary explicit
in docs, Python policy and tests so future drift fails in CI.

## Real Repository Paths

- Active ADR path: `docs/adr/`.
- Active specs path: `docs/specs/`.
- Memory policy path selected for this PR: `docs/specs/memory_policy.md`.
- FINLIB path: `backend/finlib/`.
- RAG path: `backend/rag/`.
- Memory path: `backend/memory/`.
- PostgreSQL migrations path: `backend/memory/postgres/migrations/`.
- Architecture tests path: `tests/architecture/`.
- Import-linter config path: `.importlinter`.

`docs/specs/memorypolicy.md` did not exist before this PR, so the snake-case
name `docs/specs/memory_policy.md` is used to avoid duplicate conventions.

## Current Boundary Facts

- `backend/rag/qdrant_store.py`, `backend/rag/collection_guard.py`,
  `backend/rag/cache/cache_layer.py` and related RAG modules already reference
  Qdrant clients.
- `backend/finlib/` already has architecture tests preventing imports of
  Qdrant, RAG, HTTP clients and LLM clients.
- Migrations `018` through `028` do not define primary embedding tables or
  `vector(...)` columns. Existing pgvector usage is documented as working-memory
  checkpoint infrastructure outside the FINLIB schema ladder.
- `.importlinter` already exists and must be extended, not replaced.
- Code-sandbox-mcp is the reviewer runtime. Local validation should also run
  through `uv` and, when possible, through the Docker sandbox image.

## Formal Boundary

### PostgreSQL/TimescaleDB

PostgreSQL/TimescaleDB is the structured long-term memory layer:

- time series;
- relational state;
- sources;
- runs;
- watermarks;
- data quality;
- outbox;
- audit;
- financial metadata;
- future structured episodic/conceptual memory;
- future long-term decision provenance.

It is not the primary semantic or hybrid RAG retriever.

### Qdrant

Qdrant is the primary semantic/hybrid retrieval layer:

- dense retrieval;
- sparse retrieval;
- multivector retrieval when applicable;
- RRF/DBSF fusion when applicable;
- semantic documents/chunks;
- semantic cache when applicable.

### pgvector

pgvector is auxiliary only:

- durable checkpoints;
- small or experimental embeddings;
- controlled model comparison;
- explicitly authorized fallback.

pgvector must not become the primary QUIMERA semantic retriever or primary
hybrid RAG backend without a future ADR and sprint authorization.

### Markdown

Markdown is for human and multi-agent handoff:

- project status;
- review reports;
- runbooks;
- readable artifacts.

Markdown is not the source of truth for time series, audit trails or primary
semantic retrieval.

## Required Deliverables

- ADR: `docs/adr/ADR-006-qdrant-postgres-pgvector-boundary.md`.
- Memory policy doc: `docs/specs/memory_policy.md`.
- LongRAG reference doc:
  `docs/references/long-rag-postgres-memory-reference.md`.
- Pure policy module: `backend/memory/policy.py`.
- Unit tests: `tests/unit/test_qdrant_pgvector_boundary.py`.
- Architecture tests:
  - `tests/architecture/test_finlib_does_not_promote_pgvector_to_primary_rag.py`;
  - `tests/architecture/test_qdrant_remains_primary_semantic_retriever.py`;
  - `tests/architecture/test_finlib_repositories_do_not_import_qdrant.py`.
- Import-linter updates in `.importlinter`.
- Final factual state update in `docs/04_MEM/current_state.md`.

## Test Plan

Focused:

```bash
uv run pytest \
  tests/unit/test_qdrant_pgvector_boundary.py \
  tests/architecture/test_finlib_does_not_promote_pgvector_to_primary_rag.py \
  tests/architecture/test_qdrant_remains_primary_semantic_retriever.py \
  tests/architecture/test_finlib_repositories_do_not_import_qdrant.py \
  -q
```

Regression:

```bash
uv run pytest tests/unit -q
uv run pytest tests/architecture -q
uv run mypy --strict backend/memory/policy.py
uv run pyright backend/memory/policy.py
uvx ruff check backend/memory/policy.py tests/unit/test_qdrant_pgvector_boundary.py tests/architecture
uvx ruff format --check backend/memory/policy.py tests/unit/test_qdrant_pgvector_boundary.py tests/architecture
uvx --from import-linter lint-imports
uvx sqlfluff lint backend/memory/postgres/migrations --dialect postgres
git diff --check
```

Sandbox, when available:

```bash
docker run --rm \
  -v "$PWD:/workspace" \
  -w /workspace \
  openclaw-sandbox:latest \
  sh -lc 'python --version && pytest tests/unit/test_qdrant_pgvector_boundary.py tests/architecture -q'
```

## Out Of Scope

- LongRAG runtime;
- migrations;
- tables;
- Qdrant collection changes;
- pgvector retrievers;
- FINLIB repository changes;
- RAG production pipeline mutation;
- agents;
- LLM calls;
- HTTP clients;
- secrets, DSNs, private portfolio data or real financial account data.

