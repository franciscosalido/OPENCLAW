# ADR-005 - Qdrant Working Memory with pgvector Checkpoints

Status: Accepted

## Decision

Qdrant is the initial backend for QUIMERA Working Memory.

- Default collection: `quimera_working_memory`
- Vector name: `work-dense`
- Vector size: `768`
- Distance: `Cosine`
- Qdrant vector storage: `on_disk=false`
- Postgres/pgvector checkpoint tables:
  - `working_memory_snapshots`
  - `working_memory_snapshot_points`

pgvector is a checkpoint and restore layer, not the hot path. The fast backend
remains pluggable.

## Consequences

- Qdrant working memory can be erased and rebuilt from checkpoint.
- Restore after Qdrant loss is a required behavior.
- Every checkpoint needs a checksum.
- TTL is mandatory for working-memory points.
- Payloads must be sanitized.
- Logs and reports must not include raw prompt, response, chunk, vector, DSN or
  secrets.

## Non-Goals

- Choosing Redis definitively.
- Replacing HybridRAG.
- Replacing Qdrant knowledge collections.
- Replacing Postgres/Timescale canonical memory.
