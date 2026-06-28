# ADR-006 - Qdrant/Postgres/pgvector Memory Boundary

Status: Accepted
Date: 2026-06-27

## Context

QUIMERA has two memory families that must cooperate without collapsing into a
single ambiguous backend.

FINLIB uses PostgreSQL 18.4 and TimescaleDB for structured financial memory:
time series, sources, ingestion runs, watermarks, data-quality checks, outbox
events, audit rows and relational metadata. Gateway/RAG uses Qdrant 1.18.x as
the semantic and hybrid retriever. pgvector exists in the local PostgreSQL image
for auxiliary checkpoint and experiment workflows, especially working-memory
restart recovery.

Future LongRAG work will need long-term structured memory for investment
episodes, theses, concept nodes, decision rationales and context bundles. That
future work must not silently promote PostgreSQL or pgvector into the primary
semantic/hybrid retriever.

## Decision

Qdrant is the primary semantic and hybrid RAG retriever for QUIMERA. It owns
dense, sparse and multivector retrieval, plus RRF/DBSF fusion where applicable.

PostgreSQL/TimescaleDB is the relational, temporal, operational, audit and
future structured long-term memory layer. It may provide structured context,
provenance and temporal constraints to a RAG pipeline, but it is not the primary
semantic retriever.

pgvector is auxiliary only. Authorized uses are durable checkpoints, small or
experimental embeddings, controlled A/B comparison and explicitly authorized
fallback. pgvector must not become the primary semantic retriever or the primary
hybrid RAG backend without a future ADR and sprint authorization.

Markdown is for human and multi-agent handoff: status, review reports, runbooks
and readable artifacts. Markdown is not the source of truth for time series,
audit trails or semantic retrieval.

## Consequences

- `backend/memory/policy.py` is the executable source for the memory boundary.
- Architecture tests must fail if pgvector is promoted to primary RAG.
- FINLIB repositories must not import Qdrant, RAG, HTTP clients or LLM clients.
- RAG modules must not import FINLIB repositories directly.
- Migrations must not create primary embedding tables without an explicit ADR.
- Exceptions require a new ADR or explicit sprint authorization.

## References

- Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP
  Tasks" (2020).
- Jiang et al., "LongRAG: Enhancing Retrieval-Augmented Generation with Long
  Context LLMs" (2024).
- Sarthi et al., "RAPTOR: Recursive Abstractive Processing for Tree-Organized
  Retrieval" (2024).
- Packer et al., "MemGPT: Towards LLMs as Operating Systems" (2023).
- Gutierrez et al., "HippoRAG: Neurobiologically Inspired Long-Term Memory for
  Large Language Models" (2024).
- Liu et al., "Lost in the Middle: How Language Models Use Long Contexts"
  (2023).
- Qdrant documentation: Hybrid Queries and Query API.
- pgvector project documentation.
- PostgreSQL documentation: Full Text Search.
