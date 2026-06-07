# RAG-01B PR-10 - Working Memory Qdrant + pgvector Checkpoints

## Objective

O PR-10 introduz uma working memory vetorial quente em Qdrant e usa
Postgres/pgvector como checkpoint durável. A coleção working memory é pequena,
ativa e restaurável; ela não substitui Qdrant HybridRAG nem Postgres/Timescale
como memória canônica.

## Decision

Qdrant is the first hot working-memory backend. The backend remains pluggable
for future Redis, Python/RAM or Dragonfly benchmarks. Postgres/pgvector stores
durable checkpoints only.

## Memory Boundaries

Working memory: short-lived active agent/session state for current reasoning.
HybridRAG: dense/sparse retrieval over knowledge collections.
Long-term memory: Postgres/Timescale canonical relational-temporal memory.
Semantic cache: Qdrant/LiteLLM response/retrieval cache collections.

## Qdrant Collection Design

- Collection: `quimera_working_memory`
- Vector name: `work-dense`
- Vector size: `768`
- Distance: `Cosine`
- Storage: `on_disk=false`
- Required filters: `agent_id` and `session_id`
- Default limit: `10`; maximum limit: `50`
- No vector returned by default

Payload contains only safe operational fields: IDs, memory kind, source refs,
topic, importance, recency, TTL, checksum, safe summary and sanitized metadata.

## pgvector Checkpoint Design

Checkpoint tables:

- `working_memory_snapshots`
- `working_memory_snapshot_points`

The point table stores `memory_vector vector(768)` for restore. No HNSW/IVFFlat
index is created in this PR because pgvector is not the hot path.

## Snapshot/Restore Lifecycle

Snapshots are explicit by CLI/MCP or by caller-controlled autosnapshot policy.
Restore upserts points back into Qdrant. Replace mode is disabled unless
explicitly enabled and may only delete points for the same `agent_id` and
`session_id`.

Checksum mismatch defaults to availability-first behavior: restore continues
with `status=warn`, `checksum_ok=false` and an explicit warning. Operators that
prefer integrity over availability can construct `RestoreService` with
`abort_on_checksum_fail=true`; in that mode no point is restored after checksum
mismatch.

`snapshot_epoch` is a wall-clock millisecond epoch with a local monotonic guard.
It does not reset to `1` after process restart and remains sortable across
process lifetimes. PostgreSQL still enforces uniqueness by
`(agent_id, session_id, snapshot_epoch)`.

## TTL And Cleanup

Every point has `expires_at` and `ttl_seconds`. Cleanup only removes expired
points from `quimera_working_memory` or test-prefixed collections.

## Safety/PII

Forbidden fields include prompt, response, answer, chunk text, document text,
raw payloads, vectors, secrets, tokens, passwords, DSNs and connection strings.
Reports and logs expose counts, IDs, checksums and safe summaries only.

## MCP Tools

The working-memory MCP server uses Streamable HTTP on `127.0.0.1:8813/mcp`.
Tools: health, upsert, query, snapshot, restore and cleanup. Restore and cleanup
are gated by settings.

## OTel/Metrics

Safe spans cover working-memory upsert, query, snapshot, restore and cleanup.
Attributes are limited to agent/session IDs, collection name, counts, snapshot
ID and latency.

## Test Plan

Unit tests cover settings, models, safety, Qdrant collection contract, SQL
schema, snapshot/restore, cleanup and MCP tools. Integration tests are marked
`integration` and skip cleanly when Qdrant/Postgres are unavailable.

## Negative Scope

No Redis, Dragonfly, final Python/RAM backend decision, new knowledge
collection, HybridRAG mutation, cache collection mutation, pgvector ANN hot
path, scheduler daemon, dashboard, remote provider, real data or real
collection deletion.

`integration/hybrid_fixture.py` uses `delete_collection` only as teardown for
synthetic HybridRAG test collections. PR-10 does not add `delete_collection` to
`backend/working_memory` or the working-memory MCP path.

## Future Handoff

- Redis/Python/RAM alternatives benchmark.
- Compacting/reflection policy for active memory.
- Multi-agent memory arbitration.
