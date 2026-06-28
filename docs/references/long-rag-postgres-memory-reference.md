# LongRAG And PostgreSQL Long-Term Memory Reference

Status: Planning reference
Sprint: FINLIB-0 FL-PR13

## Problem

QUIMERA needs long-term memory for investment reasoning that is too durable and
structured to live only in a model context window. Buy-and-hold decisions,
investment theses, macroeconomic assumptions and concept explanations should be
recoverable months later with provenance, timestamps and revision history.

Long context does not remove the need for retrieval. It changes how retrieval
and context packing should be designed.

## Boundary Summary

- PostgreSQL/TimescaleDB stores structured, temporal, relational and auditable
  memory.
- Qdrant stores semantic/hybrid retrieval memory.
- pgvector is auxiliary only.
- Markdown is human and multi-agent handoff.

## RAG And LongRAG

RAG adds a non-parametric retrieval layer to generation. For QUIMERA, that
means cited financial evidence must be retrieved from explicit memory stores
instead of relying on model weights.

LongRAG extends this idea by retrieving longer units and using long-context
readers. For QUIMERA, this is relevant to multi-page theses, long investment
histories and complex macroeconomic narratives. It does not imply dumping all
memory into the prompt.

## RAPTOR Mapping

RAPTOR-style hierarchical summarization can be modeled with PostgreSQL tables
for hierarchy, provenance and versioning, while Qdrant indexes the semantic
representations used for retrieval. PostgreSQL manages the tree; Qdrant answers
semantic nearest-neighbor and hybrid retrieval.

## MemGPT Mapping

MemGPT separates memory tiers. In QUIMERA terms:

- PostgreSQL is structured recall memory.
- Qdrant is semantic archival retrieval.
- Markdown is the human-readable handoff layer.
- pgvector is a checkpoint/experiment layer, not the operating memory manager.

## HippoRAG Mapping

HippoRAG motivates associative long-term retrieval. QUIMERA maps associative
semantic lookup to Qdrant and structured relational/audit storage to
PostgreSQL. The two layers should cooperate rather than compete.

## Lost In The Middle

Long context models can underuse evidence placed in the middle of a large
context. QUIMERA should prefer deliberate context packing: retrieve, rank,
deduplicate, cite and budget evidence instead of blindly expanding context.

## PostgreSQL Long-Term Memory Direction

Future PostgreSQL memory tables may include:

- investment episodes;
- investment theses;
- decision rationales;
- concept nodes;
- entity relations;
- context bundles;
- source watermarks;
- memory consolidation records.

Those tables should be append-friendly, auditable and queryable by time,
source, entity and lineage hash.

## Ten Future LongRAG Suggestions

S-01: Episodic Memory Store. Store investment episodes with event time,
entities, source ids, summary, evidence links and lineage hash.

S-02: Investment Thesis Append-Only Log. Preserve the original thesis and later
revisions without overwriting the decision context.

S-03: Hierarchical Summarization. Model RAPTOR-like parent/child summaries in
PostgreSQL while indexing semantic nodes in Qdrant.

S-04: Temporal Memory Queries. Use TimescaleDB windows to recover what was
known at decision time.

S-05: Staleness Guard. Attach validity windows and source watermarks to memory
records so old evidence is marked stale before generation.

S-06: Draft Memory Query Pattern. Let agents draft structured memory queries
before retrieving, then audit the query and result ids.

S-07: Entity Relations In SQL. Keep durable entity relations in PostgreSQL so
semantic retrieval can be filtered by issuer, ticker, sector or source.

S-08: Memory Audit Layer. Record which memory records affected an answer,
without logging raw prompts or private Level 0 payloads.

S-09: Context Budget Manager. Allocate prompt budget across facts, episodes,
concepts and citations instead of blindly appending retrieved chunks.

S-10: Memory Consolidation. Use continuous or scheduled consolidation to
produce durable summaries with lineage back to raw observations.

## References

- Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP
  Tasks", 2020.
- Jiang et al., "LongRAG: Enhancing Retrieval-Augmented Generation with Long
  Context LLMs", 2024.
- Sarthi et al., "RAPTOR: Recursive Abstractive Processing for Tree-Organized
  Retrieval", 2024.
- Packer et al., "MemGPT: Towards LLMs as Operating Systems", 2023.
- Gutierrez et al., "HippoRAG: Neurobiologically Inspired Long-Term Memory for
  Large Language Models", 2024.
- Liu et al., "Lost in the Middle: How Language Models Use Long Contexts",
  2023.
- Qdrant documentation, Hybrid Queries and Query API.
- pgvector project documentation.
- PostgreSQL documentation, Full Text Search.

## Non-Goal

FL-PR13 is a gate condition before LongRAG implementation. It does not create
the memory tables above and does not change runtime retrieval.
