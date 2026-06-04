# ADR-003 - Memory Backend Decision for RAG-01B

Status: Accepted

Date: 2026-06-04

## Evidence

This decision is derived from:

- `evaluation/results/rag_01b_session_benchmark_summary.json`
- `evaluation/results/rag_01b_session_benchmark_rows.csv`

The ADR follows the `decisions` object in the benchmark summary.

## Decision

Postgres/Timescale is the canonical backend for:

- sessions;
- turns;
- agent_states;
- entity_mentions;
- lightweight entity graph records;
- temporal memory events;
- market_bars;
- market_features;
- qlib_projection_manifests;
- kronos_forecasts;
- model_runs.

Qdrant is the canonical vector backend for:

- knowledge vectors;
- dense, sparse and hybrid retrieval;
- semantic query cache;
- optional LiteLLM semantic cache when the LiteLLM backend is stable.

Python Weighted RRF remains the ground truth for fusion. Native Qdrant RRF
remains experimental.

Qlib and Kronos use derived projections. They are not sources of truth.

MCP is an agent interface over the canonical memory backends. MCP is not a
source of truth.

## Benchmark Decisions

- sessions: postgres
- turns: postgres
- agent_states: postgres
- entity_mentions: postgres
- vectors: qdrant
- semantic_cache: qdrant
- llm_response_cache: qdrant_or_litellm_cache
- qlib_projection: postgres_timescale_manifest
- kronos_forecasts: postgres_timescale

## Consequences

- Session-local temporal context is read from Postgres/Timescale.
- Semantic retrieval and vector cache remain Qdrant responsibilities.
- Agents access memory through repository/API/MCP layers, not direct storage
  coupling.
- Benchmark artifacts must be updated before reopening this decision.

