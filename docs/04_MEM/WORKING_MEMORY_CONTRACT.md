# Working Memory Contract

Fast layer backend is deferred.

QUIMERA will use a future hot, ultrafast working memory layer for active
multi-agent context. The backend is not selected in PR-09.

Candidate technologies remain candidates only:

- Redis or RedisSearch.
- Python in-process vector memory.
- Qdrant in-memory or ephemeral collection.
- Another ultrafast vector backend.

pgvector checkpoint is accepted as the durable checkpoint for that future hot
layer.

No RAM layer is a source of truth.

no RAM layer is a source of truth. Working memory must be restorable from
checkpoint + canonical memory.

## Checkpoint Fields

- agent_id
- session_id
- topic
- embedding_model
- vector_dim
- memory_vector, optional
- metadata, safe operational metadata only
- checksum
- ttl_seconds
- created_at
- expires_at
- schema_version

## Restore Semantics

On restart, a future fast layer may read unexpired checkpoints, validate
checksum and schema version, and rebuild working context. Expired checkpoints
are ignored by the fast layer but are not automatically deleted in PR-09.

## Safety

Checkpoints must not contain prompt, response, raw prompt, answer, chunk,
chunk text, document text, DSN, Authorization, api key, token, password or
secret material.

## Future ADR

The final backend for hot working memory requires a future ADR and benchmark.
