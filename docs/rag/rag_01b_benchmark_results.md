# RAG-01B Session Context Benchmark Results

The PR-07 benchmark compares Postgres and Qdrant for session-context memory
roles using deterministic synthetic data by default.

Artifacts:

- `evaluation/results/rag_01b_session_benchmark_summary.json`
- `evaluation/results/rag_01b_session_benchmark_rows.csv`

## Method

The default benchmark mode is local, deterministic and cache-safe:

- `QUIMERA_CACHE_ENABLED=0` is required.
- LiteLLM cache bypass is represented as `x-litellm-cache: no-cache`.
- Real service execution is opt-in with `QUIMERA_BENCHMARK_REAL=1`.
- No real portfolio, brokerage or private document data is used.

## Results

The benchmark summary chooses Postgres for temporal/session facts and Qdrant for
semantic vector retrieval. It also makes `llm_response_cache` explicit:
Qdrant is the canonical storage backend for the LLM response semantic cache,
while LiteLLM remains the gateway/manager.

## Decision

See `docs/ADR/ADR-003-memory-backend-decision.md`.
