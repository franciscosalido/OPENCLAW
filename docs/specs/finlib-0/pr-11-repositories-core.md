# FINLIB-0 FL-PR11 — Repositories Core

Branch: `feat/finlib-repositories-core`
GitHub Issue: `#120`
Status: Initial SDD

## Objective

FL-PR11 creates the asyncpg-only repository layer for the FINLIB operational
core and the first two temporal libraries: macro series and Tesouro Direto.

The repository layer is the future data-agent write boundary:

```text
future data agent
  -> repository method
    -> asyncpg transaction
      -> domain SQL
      -> audit_agent_writes
    -> commit or rollback
```

Every logical write batch must persist the domain write and exactly one
`audit_agent_writes` row in the same PostgreSQL transaction. If the domain
write fails, no audit row is inserted. If the audit write fails, the domain
write rolls back.

## Preconditions Confirmed

- Current local branch before PR creation was `main`.
- Local `main` contains FL-PR10 and migration head
  `028_create_company_fundamentals.sql`.
- Local `main` is ahead of `origin/main` by 31 commits; therefore the remote
  Draft PR must not be opened until the local stack is synchronized or the
  human explicitly authorizes publishing the stacked branch.
- Python target is 3.12.
- PostgreSQL target is 18.x.
- The code-sandbox-mcp Docker environment is the authoritative reviewer
  runtime.

## Real Schema Inventory

### Operational Core

`ops_data_sources`:

- `source_id TEXT PRIMARY KEY`
- `kind TEXT NOT NULL`
- `base_url TEXT`
- `license_note TEXT`
- `methodology_limitations TEXT NOT NULL`
- `enabled BOOLEAN NOT NULL DEFAULT TRUE`
- `metadata JSONB NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`

`ops_ingestion_runs`:

- `run_id UUID PRIMARY KEY`
- `source_id TEXT NOT NULL`
- `agent_id TEXT NOT NULL`
- `mode TEXT NOT NULL`
- `status TEXT NOT NULL`
- `started_at TIMESTAMPTZ NOT NULL`
- `finished_at TIMESTAMPTZ`
- non-negative counters
- `source_snapshot_hash TEXT`
- `error_summary TEXT`
- `trace_id UUID NOT NULL`
- `metadata JSONB NOT NULL`

### Watermarks

The dedicated watermark table already exists and is canonical:

`ops_ingestion_watermarks`:

- `source_id TEXT NOT NULL`
- `dataset TEXT NOT NULL`
- `watermark_value TEXT NOT NULL`
- `watermark_ts TIMESTAMPTZ`
- `source_snapshot_hash TEXT`
- `run_id UUID`
- `updated_at TIMESTAMPTZ NOT NULL`
- `metadata JSONB NOT NULL`
- `PRIMARY KEY (source_id, dataset)`

No FL-PR11 migration should create `ops_watermarks`; doing so would create two
watermark sources of truth. `set_watermark` must use the existing table and
preserve monotonic `watermark_ts` semantics.

### Quality And Outbox

`ops_data_quality_checks`:

- `check_id UUID PRIMARY KEY`
- `run_id UUID NOT NULL`
- `check_name TEXT NOT NULL`
- `target_table TEXT NOT NULL`
- `severity TEXT NOT NULL`
- `passed BOOLEAN NOT NULL`
- `observed JSONB NOT NULL`
- `expected JSONB NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`
- `metadata JSONB NOT NULL`

`ops_outbox_events`:

- `event_id UUID PRIMARY KEY`
- `event_type TEXT NOT NULL`
- `aggregate_type TEXT NOT NULL`
- `aggregate_id TEXT NOT NULL`
- `payload JSONB NOT NULL`
- `status TEXT NOT NULL DEFAULT 'pending'`
- `attempts INTEGER NOT NULL DEFAULT 0`
- `max_attempts INTEGER NOT NULL DEFAULT 3`
- `next_attempt_at TIMESTAMPTZ NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`
- `locked_by TEXT`
- `locked_at TIMESTAMPTZ`
- `trace_id UUID`
- `run_id UUID`
- `metadata JSONB NOT NULL`

`OpsRepository.poll_events()` is the only production code path allowed to use
`FOR UPDATE SKIP LOCKED`.

### Audit

`audit_agent_writes`:

- `audit_id UUID PRIMARY KEY`
- `trace_id UUID NOT NULL`
- `run_id UUID`
- `agent_id TEXT NOT NULL`
- `repository TEXT NOT NULL`
- `target_table TEXT NOT NULL`
- `operation TEXT NOT NULL`
- `row_count INTEGER NOT NULL`
- `batch_hash TEXT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`
- `metadata JSONB NOT NULL`

`AuditContext.batch_hash` maps to the real `audit_agent_writes.batch_hash`
column.

### Macro Library

`macro_series_catalog` is keyed by `series_code`.

`macro_observations`:

- `series_code TEXT NOT NULL`
- `ref_ts TIMESTAMPTZ NOT NULL`
- `revision INTEGER NOT NULL DEFAULT 0`
- `value NUMERIC NOT NULL`
- `source_id TEXT NOT NULL`
- `run_id UUID NOT NULL`
- `lineage_hash TEXT NOT NULL`
- `schema_version INTEGER NOT NULL DEFAULT 1`
- `quality_flags JSONB NOT NULL`
- `ingested_at TIMESTAMPTZ NOT NULL`
- `metadata JSONB NOT NULL`
- `PRIMARY KEY (series_code, ref_ts, revision)`
- `UNIQUE (lineage_hash, ref_ts)`

`macro_observations` is a TimescaleDB hypertable on `ref_ts`.

### Treasury Library

`treasury_bonds`:

- `bond_id UUID PRIMARY KEY`
- `bond_type TEXT NOT NULL`
- `security_family TEXT`
- `maturity_date DATE NOT NULL`
- `display_name TEXT NOT NULL`
- `source_id TEXT NOT NULL`
- `is_active BOOLEAN NOT NULL DEFAULT TRUE`
- `metadata JSONB NOT NULL`
- `UNIQUE (bond_type, maturity_date)`

`treasury_prices`:

- `bond_id UUID NOT NULL`
- `ts TIMESTAMPTZ NOT NULL`
- price/rate/base value columns
- `source_id TEXT NOT NULL`
- `run_id UUID NOT NULL`
- `lineage_hash TEXT NOT NULL`
- `schema_version INTEGER NOT NULL DEFAULT 1`
- `quality_flags JSONB NOT NULL`
- `ingested_at TIMESTAMPTZ NOT NULL`
- `metadata JSONB NOT NULL`
- `PRIMARY KEY (bond_id, ts)`
- `UNIQUE (lineage_hash, ts)`

`treasury_prices` is a TimescaleDB hypertable on `ts`.

## Architecture Decisions

### asyncpg Only

Repositories accept an injected asyncpg pool or connection-compatible object.
They never accept a DSN, never create a pool internally and never read
environment variables.

### No ORM

SQLAlchemy, SQLModel, Alembic and other ORM layers are forbidden in FL-PR11.
SQL must live inside `backend/finlib/repositories/`, migrations or tests.

### DTOs

Repository methods must use typed dataclasses or Pydantic models with named
fields. Heterogeneous tuple batches and positional `*args` spreads are
forbidden for domain payloads.

Required DTO families:

- `AuditContext`
- `BatchWriteResult`
- `DataSourceInput`
- `IngestionRunInput`
- `WatermarkInput`
- `DataQualityCheckInput`
- `OutboxEventInput`
- `QueuedEvent`
- `MacroSeriesInput`
- `MacroObservationInput`
- `TreasuryBondInput`
- `TreasuryPriceInput`

### Audited Transactions

The base repository must provide a shared audited-transaction helper:

1. acquire connection;
2. open transaction;
3. execute domain write;
4. insert exactly one `audit_agent_writes` row;
5. commit;
6. rollback both writes on any exception.

Empty batches should be deterministic no-ops returning
`BatchWriteResult(attempted=0, inserted=0, updated=0, skipped=0,
audit_id=None)` and must not create audit rows.

### Macro Revision Policy

`MacroRepository.upsert_observations_batch()` must allocate
`revision + 1` under a transaction-scoped advisory lock keyed by
`series_code + ref_ts`.

Identical `lineage_hash + ref_ts` is skipped. Changed values for the same
`series_code + ref_ts` create a new revision row.

### Treasury Idempotency Policy

`TreasuryRepository.upsert_bonds_batch()` uses the natural key
`bond_type + maturity_date` and preserves existing `bond_id`.

`TreasuryRepository.upsert_prices_batch()` uses
`ON CONFLICT (lineage_hash, ts) DO NOTHING` for identical reingestion and must
not rewrite an existing `(bond_id, ts)` row with a different `lineage_hash`.

### Outbox Polling

`OpsRepository.poll_events()` owns the only production `SKIP LOCKED` query.
It claims pending, due events by changing them to `processing`, filling
`locked_by`, `locked_at`, and incrementing `attempts` inside one transaction.

## Planned Files

- `backend/finlib/repositories/__init__.py`
- `backend/finlib/repositories/base.py`
- `backend/finlib/repositories/models.py`
- `backend/finlib/repositories/ops_repository.py`
- `backend/finlib/repositories/macro_repository.py`
- `backend/finlib/repositories/treasury_repository.py`
- `tests/unit/test_finlib_ops_repository.py`
- `tests/unit/test_finlib_macro_repository.py`
- `tests/unit/test_finlib_treasury_repository.py`
- `tests/unit/test_finlib_repository_boundaries.py`
- `tests/integration/test_finlib_repositories_core_live.py`

No migration is planned because `ops_ingestion_watermarks` already exists.

## Test Plan

Unit tests:

- DTO and async method contracts.
- No ORM imports.
- No SQL outside repositories/migrations/tests.
- `SKIP LOCKED` only in `ops_repository.py` and tests.
- Empty batch no-op behavior.
- Level 0 payload rejection for outbox payloads.
- Static SQL contract for advisory locks, conflict handling and audit writes.

Live integration:

- isolated `quimera_test_*` database;
- migrations through head `028`;
- source registration, run lifecycle, macro catalog/observations, treasury
  bonds/prices, quality checks, watermarks and outbox;
- exactly one audit row per logical batch;
- rollback cancels domain write and audit write;
- concurrent outbox polling does not double-claim an event.

## Security And Privacy

FL-PR11 must not touch `.env`, secrets, DSNs, Qdrant, pgvector, runtime
volumes, real portfolio data, brokerage data, CPF, account numbers, positions,
quantities, acquisition prices, cost basis or private payloads.

Level 0 fields in outbox payloads must be rejected before writing to the
database.

## Rollback

This PR should be code-only plus tests and docs. Rollback is deleting the
repository package and tests. If a future review discovers that a migration is
needed, it must be additive and use the next migration number after `028`.

## Remote PR State

GitHub Issue: `#120`.

Draft PR remote creation is deferred because local `main` is currently ahead
of `origin/main` by 31 commits. Opening a Draft PR before synchronizing that
stack would publish unrelated prior sprint commits in this PR.
