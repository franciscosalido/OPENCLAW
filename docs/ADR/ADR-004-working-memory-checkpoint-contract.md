# ADR-004 - Working Memory Fast Layer Deferred; pgvector as Durable Checkpoint

Status: Accepted

## Decision

The fast working memory backend is deferred. QUIMERA will choose the hot,
ultrafast working memory layer in a future benchmark-driven PR.

Backend fast layer deferred.

pgvector is accepted as the durable checkpoint for working memory. It is not
the hot working memory backend.

No RAM layer is allowed to become the only source of truth. Every working
memory state must be reconstructible from checkpoint + canonical memory.

The checkpoint must not contain prompt, response, chunk, document text, DSN or
secrets. The checkpoint may contain vectors, safe IDs, topic labels, hashes,
TTL, schema version, checksums and operational metadata.

## Consequences

- Redis remains only a candidate.
- Python in-process vector memory remains only a candidate.
- Qdrant ephemeral memory remains only a candidate.
- Qdrant remains persistent HybridRAG knowledge memory.
- PostgreSQL/Timescale remains canonical relational-temporal memory.
- pgvector provides restart recovery for future fast working memory.

## Contract

The checkpoint preserves:

- `agent_id`
- `session_id`
- `topic`
- `embedding_model`
- `vector_dim`
- optional `memory_vector`
- `ttl_seconds`
- `expires_at`
- `checksum`
- `schema_version`
- timestamps

The fast backend decision belongs to PR-10+.
