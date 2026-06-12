# FL-PR03 — Watermarks, Data Quality and Outbox

Status: Implementation branch

Branch: `feat/finlib-watermarks-quality-outbox`

## Objetivo

Adicionar idempotência operacional, qualidade de dados e barramento assíncrono
mínimo para FINLIB-0 sem criar agents, repositories, MCP tools ou runtime A2A.

Este PR adiciona somente a migration
`020_create_ops_watermarks_quality_outbox.sql`.

## Schema Diff

### `ops_ingestion_watermarks`

- `source_id TEXT NOT NULL REFERENCES ops_data_sources(source_id)`
- `dataset TEXT NOT NULL`
- `watermark_value TEXT NOT NULL`
- `watermark_ts TIMESTAMPTZ`
- `source_snapshot_hash TEXT`
- `run_id UUID REFERENCES ops_ingestion_runs(run_id)`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`
- `PRIMARY KEY (source_id, dataset)`

`dataset`, `watermark_value` and optional `source_snapshot_hash` must contain at
least one non-whitespace character. `metadata` must be a JSON object.

Watermark monotonicity is enforced in two layers:

- direct `UPDATE` cannot move `watermark_ts` backwards or from non-null to null;
- the official upsert used by tests advances only when the incoming
  `watermark_ts` is greater than or equal to the stored value, or the stored
  value is null.

If `watermark_ts` is null, ordering is intentionally conservative: null does
not replace an existing timestamp through the official upsert.

### `ops_data_quality_checks`

- `check_id UUID PRIMARY KEY DEFAULT uuidv7()`
- `run_id UUID NOT NULL REFERENCES ops_ingestion_runs(run_id)`
- `check_name TEXT NOT NULL`
- `target_table TEXT NOT NULL`
- `severity TEXT NOT NULL CHECK IN ('info', 'warning', 'error', 'critical')`
- `passed BOOLEAN NOT NULL`
- `observed JSONB NOT NULL DEFAULT '{}'::jsonb`
- `expected JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`

Text fields must contain non-whitespace content. JSONB fields must be objects.

### `ops_outbox_events`

- `event_id UUID PRIMARY KEY DEFAULT uuidv7()`
- `event_type TEXT NOT NULL`
- `aggregate_type TEXT NOT NULL`
- `aggregate_id TEXT NOT NULL`
- `payload JSONB NOT NULL DEFAULT '{}'::jsonb`
- `status TEXT NOT NULL DEFAULT 'pending'`
- `attempts INTEGER NOT NULL DEFAULT 0`
- `max_attempts INTEGER NOT NULL DEFAULT 3`
- `next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `locked_by TEXT`
- `locked_at TIMESTAMPTZ`
- `trace_id UUID`
- `run_id UUID REFERENCES ops_ingestion_runs(run_id)`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`

Status values are exactly `pending`, `processing`, `completed`, `failed` and
`cancelled`. Payload and metadata must be JSON objects.

## Outbox Poll Contract

Official polling uses PostgreSQL row locks:

```sql
SELECT *
FROM ops_outbox_events
WHERE status = 'pending'
  AND next_attempt_at <= now()
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT $1;
```

The migration creates the partial index:

```sql
CREATE INDEX IF NOT EXISTS idx_ops_outbox_pending
ON ops_outbox_events (next_attempt_at, created_at)
WHERE status = 'pending';
```

Empty outbox poll target: under 5ms on isolated local PostgreSQL, measured as
the best sample after warmup to avoid turning noise into a flaky benchmark.

## Fora de Escopo

- `audit_agent_writes`
- repositories
- data agents
- MCP tools
- runtime A2A
- FL-PR04+ financial library tables

## Validação Esperada

```bash
uv run pytest tests/unit/test_finlib_watermarks_quality_outbox_schema.py -q
uv run pytest tests/integration/test_finlib_outbox_skip_locked_live.py -q
uv run pytest tests/integration/test_finlib_watermark_concurrency_live.py -q
```
