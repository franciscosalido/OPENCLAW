# QUIMERA Memory Policy

Status: Active
Owner: FINLIB-0 / RAG architecture
Executable mapping: `backend/memory/policy.py`

## Summary

QUIMERA uses separate memory backends for separate jobs.

| Backend | Canonical role | Must not do |
|---|---|---|
| PostgreSQL/TimescaleDB | structured, temporal, relational and auditable memory | primary semantic/hybrid RAG |
| Qdrant | primary semantic/hybrid retriever | relational source of truth |
| pgvector | auxiliary checkpoint, experiment and controlled fallback | primary semantic/hybrid RAG |
| Markdown | human/multi-agent handoff and reports | canonical data, audit or retrieval |

## PostgreSQL/TimescaleDB

PostgreSQL and TimescaleDB MUST store structured long-term memory:

- time series;
- relational state;
- data sources;
- ingestion runs;
- watermarks;
- data-quality checks;
- outbox events;
- audit rows;
- financial metadata;
- future structured episodic memory;
- future structured conceptual memory;
- future decision provenance.

PostgreSQL MAY support retrieval by exposing structured filters, temporal
windows and provenance. It MUST NOT become the primary semantic/hybrid
retriever.

## Qdrant

Qdrant MUST remain the primary semantic/hybrid retriever:

- dense retrieval;
- sparse retrieval;
- multivector retrieval when applicable;
- RRF/DBSF fusion when applicable;
- semantic documents and chunks;
- semantic cache when applicable.

Qdrant MUST NOT become the relational source of truth for FINLIB data.

## pgvector

pgvector is authorized only for:

- `embedding_checkpoint`;
- `ab_model_comparison`;
- `controlled_fallback`.

pgvector MUST NOT be used as:

- `primary_retriever`;
- `primary_semantic_retriever`;
- `hybrid_rag_primary`;
- `semantic_cache_primary`;
- `document_chunk_primary_store`.

Any new pgvector role requires an ADR and explicit sprint authorization.

## Markdown

Markdown SHOULD be used for:

- human handoff;
- reviewer reports;
- status;
- runbooks;
- readable artifacts.

Markdown MUST NOT be treated as the canonical source of time-series data, audit
truth or primary semantic retrieval.

## Policy Mapping

`backend/memory/policy.py` exposes:

- `MemoryBackend`;
- `MemoryRole`;
- `MemoryBoundaryRule`;
- `PRIMARY_SEMANTIC_RETRIEVER`;
- `PGVECTOR_AUTHORIZED_USES`;
- `FINLIB_FORBIDDEN_IMPORT_PREFIXES`;
- `RAG_FORBIDDEN_IMPORT_PREFIXES`;
- `assert_role_allowed()`;
- `validate_pgvector_use()`;
- `is_primary_semantic_retriever()`.

## Test Gates

The architecture suite MUST verify:

- Qdrant is the only primary semantic retriever in the policy;
- pgvector rejects primary semantic and hybrid RAG roles;
- FINLIB does not import Qdrant, RAG, LLM or HTTP clients;
- RAG does not import FINLIB repositories directly;
- migrations `018` through `028` do not create primary embedding tables;
- policy docs and Python policy agree on authorized pgvector uses.

## Future LongRAG Over PostgreSQL Long-Term Memory

Future sprints MAY add structured long-term memory such as:

- `investment_episodes`;
- `investment_thesis`;
- `concept_nodes`;
- `decision_rationales`;
- `entity_relations`;
- `context_bundles`.

These structures would make PostgreSQL the canonical structured memory for
financial reasoning. They would not make PostgreSQL or pgvector the semantic
retriever. Qdrant remains the semantic/hybrid retrieval layer and PostgreSQL
provides temporal, relational and audit context.

## No Runtime Mutation In FL-PR13

FL-PR13 does not mutate Qdrant, pgvector, PostgreSQL schemas, migrations,
FINLIB repositories or RAG pipelines. It adds documentation, a pure policy
module and architecture tests.

## Bibliography

- Lewis et al., Retrieval-Augmented Generation for Knowledge-Intensive NLP
  Tasks.
- Jiang et al., LongRAG.
- Sarthi et al., RAPTOR.
- Packer et al., MemGPT.
- Gutierrez et al., HippoRAG.
- Liu et al., Lost in the Middle.
- Qdrant Hybrid Queries documentation.
- pgvector documentation.
- PostgreSQL Full Text Search documentation.
