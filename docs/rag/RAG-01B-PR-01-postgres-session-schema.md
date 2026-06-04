# RAG-01B PR-01 — PostgreSQL Session Memory Schema

## Objective

PR-01 adds the local PostgreSQL foundation for Quimera relational-temporal
memory. PostgreSQL stores sessions, turns, agent state and entity mentions.
Qdrant remains the vector memory layer and is not changed by this PR.

## Tables

- `schema_migrations`: version and SHA-256 checksum for every SQL migration.
- `sessions`: agent/user session metadata with `created_at` and `updated_at`.
- `turns`: ordered conversational turns linked to a session.
- `agent_states`: JSONB agent working state keyed by `(agent_id, session_id, state_key)`.
- `entity_mentions`: light entity mention metadata linked to one turn.

## Invariants

- SQL schema is versioned through immutable migration files.
- Runtime database I/O is async and uses `asyncpg` directly.
- No SQLAlchemy, Django ORM, Peewee, Tortoise, Pony or generated ORM migrations.
- Migrations are applied lexicographically, record checksums and fail on drift.
- All user values are passed as asyncpg parameters, never string-interpolated SQL.
- Settings are loaded with `pydantic-settings`; DSNs are sanitized before display.
- Integration tests skip unless `TEST_POSTGRES_DSN` or `QUIMERA_POSTGRES_DSN` is set.

## Indexes

The schema includes lookup indexes for `agent_id`, `session_id`, `created_at`,
`state_key` ownership, entity text and entity type. The `sessions.updated_at`
field is maintained by a small trigger. `agent_states.updated_at` is updated
explicitly by the repository upsert.

## Repository Ordering Decision

`get_recent_turns(session_id, limit)` queries newest turns first for efficient
bounded retrieval, then returns them in chronological order. That shape is more
useful for prompt/context construction while keeping the SQL limit efficient.

## Test Plan

- Unit model tests validate immutability, timezone awareness, role constraints,
  non-negative counters and entity mention bounds.
- Static schema tests validate tables, keys, FKs, `ON DELETE CASCADE`, JSONB,
  TIMESTAMPTZ and required indexes.
- Migration static tests validate ordering, non-empty files, checksums,
  idempotent planning and checksum drift detection.
- No-ORM tests scan the new package for forbidden ORM imports and require
  `asyncpg` usage.
- Settings tests validate env loading, local defaults and DSN sanitization.
- Integration tests apply migrations, run repository round-trips, verify
  database constraints, cascade deletes, JSONB/unicode round-trips and
  concurrent agent-state upserts.

## Out Of Scope

This PR does not implement entity nodes, entity edges, GraphRAG, Qdrant cache,
TimescaleDB, pgvector, MCP, REST, gRPC, OpenTelemetry spans, Ollama changes,
LiteLLM changes or HybridRAG pipeline changes.
