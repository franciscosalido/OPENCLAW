# FINLIB-0 FL-PR12 — Repositories Assets

Branch: `feat/finlib-repositories-assets`
GitHub Issue: `#121`
Status: Initial SDD

## Objective

FL-PR12 completes the asyncpg-only repository layer for the FINLIB asset
libraries created by FL-PR07 through FL-PR10:

- funds: `fund_registry`, `fund_daily_info`;
- private fixed income: `fi_instruments`, `debenture_market_data`;
- fundamentals: `company_registry`, `company_listings`,
  `fundamentals_statements`, `fundamentals_indicators`.

This PR complements FL-PR11 and must not create schemas, migrations, ingesters,
downloaders, parsers, agents, MCP tools, Qdrant clients, LLM clients or
application services.

## Access And Git Preconditions

- Local branch before PR creation: `main`.
- FL-PR11 is merged locally into `main`.
- Migration head at PR start: `028_create_company_fundamentals.sql`.
- Local `main` is ahead of `origin/main` by 35 commits. Remote Draft PR
  creation is deferred until the human authorizes publishing the stacked local
  sprint history or origin is synchronized.
- GitHub Issue created:
  `https://github.com/franciscosalido/OPENCLAW/issues/121`.
- Existing dirty files outside FL-PR12 scope are preserved and must not be
  staged by this PR.

## Real Schema Inventory

### `fund_registry`

- `fund_cnpj TEXT PRIMARY KEY`
- `legal_name TEXT NOT NULL`
- `cvm_class TEXT`
- `fund_type TEXT`
- `status TEXT NOT NULL`
- `registered_at DATE`
- `source_id TEXT NOT NULL`
- `is_active BOOLEAN NOT NULL`
- `metadata JSONB NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`

### `fund_daily_info`

- `fund_cnpj TEXT NOT NULL`
- `ts TIMESTAMPTZ NOT NULL`
- `revision INTEGER NOT NULL DEFAULT 0`
- numeric fund daily fields
- `source_id TEXT NOT NULL`
- `run_id UUID NOT NULL`
- `lineage_hash TEXT NOT NULL`
- `schema_version INTEGER NOT NULL DEFAULT 1`
- `quality_flags JSONB NOT NULL`
- `ingested_at TIMESTAMPTZ NOT NULL`
- `metadata JSONB NOT NULL`
- `PRIMARY KEY (fund_cnpj, ts, revision)`
- `UNIQUE (lineage_hash, ts)`
- TimescaleDB hypertable on `ts`

### `fi_instruments`

- `instrument_id UUID PRIMARY KEY`
- `kind TEXT NOT NULL`
- issuer identity and instrument descriptors
- `indexer TEXT NOT NULL`
- `rate_spec JSONB NOT NULL`
- `fgc_covered BOOLEAN NOT NULL`
- `issue_date DATE`
- `maturity_date DATE`
- `source_id TEXT NOT NULL`
- `run_id UUID`
- `lineage_hash TEXT NOT NULL UNIQUE`
- `schema_version INTEGER NOT NULL DEFAULT 1`
- `quality_flags JSONB NOT NULL`
- `metadata JSONB NOT NULL`

### `debenture_market_data`

- `fi_id UUID NOT NULL`
- `ts TIMESTAMPTZ NOT NULL`
- `revision INTEGER NOT NULL DEFAULT 0`
- `indicative_rate NUMERIC`
- `pu NUMERIC`
- `duration INTEGER`
- `source_id TEXT NOT NULL`
- `run_id UUID NOT NULL`
- `lineage_hash TEXT NOT NULL`
- `schema_version INTEGER NOT NULL DEFAULT 1`
- `quality_flags JSONB NOT NULL`
- `metadata JSONB NOT NULL`
- `PRIMARY KEY (fi_id, ts, revision)`
- `UNIQUE (lineage_hash, ts)`
- TimescaleDB hypertable on `ts`
- trigger requires referenced `fi_instruments.kind = 'debenture'`

### `company_registry`

- `company_id UUID PRIMARY KEY`
- `cnpj TEXT NOT NULL UNIQUE`
- `cnpj_base TEXT NOT NULL`
- identity and classification fields
- `source_id TEXT NOT NULL`
- `lineage_hash TEXT NOT NULL UNIQUE`
- `schema_version INTEGER NOT NULL DEFAULT 1`
- `metadata JSONB NOT NULL`

### `company_listings`

- `listing_id UUID PRIMARY KEY`
- `company_id UUID NOT NULL`
- `exchange TEXT NOT NULL`
- `ticker TEXT NOT NULL`
- share class and listing fields
- `source_id TEXT NOT NULL`
- `lineage_hash TEXT NOT NULL UNIQUE`
- `schema_version INTEGER NOT NULL DEFAULT 1`
- `metadata JSONB NOT NULL`
- `UNIQUE (exchange, ticker)`

### `fundamentals_statements`

- `statement_id UUID PRIMARY KEY`
- `company_id UUID NOT NULL`
- period identity fields
- `version INTEGER NOT NULL DEFAULT 1`
- `restatement_reason TEXT`
- `prior_version_id UUID`
- `statements_json JSONB NOT NULL`
- `currency TEXT NOT NULL`
- `unit_multiplier INTEGER NOT NULL`
- `source_id TEXT NOT NULL`
- `run_id UUID NOT NULL`
- `lineage_hash TEXT NOT NULL UNIQUE`
- `schema_version INTEGER NOT NULL DEFAULT 1`
- `quality_flags JSONB NOT NULL`
- `metadata JSONB NOT NULL`
- `UNIQUE (company_id, period_type, period_kind, statement_scope, period_end, version)`

### `fundamentals_indicators`

- `company_id UUID NOT NULL`
- `ts TIMESTAMPTZ NOT NULL`
- `indicator_set TEXT NOT NULL`
- `source_statement_id UUID NOT NULL`
- `indicators_json JSONB NOT NULL`
- `computation_hash TEXT NOT NULL`
- `run_id UUID NOT NULL`
- `lineage_hash TEXT NOT NULL`
- `schema_version INTEGER NOT NULL DEFAULT 1`
- `quality_flags JSONB NOT NULL`
- `metadata JSONB NOT NULL`
- `PRIMARY KEY (company_id, ts, indicator_set, source_statement_id)`
- `UNIQUE (lineage_hash, ts)`
- TimescaleDB hypertable on `ts`

## Architecture Decisions

### Reuse FL-PR11

Repositories inherit `BaseRepository` and reuse:

- `AuditContext`;
- `BatchWriteResult`;
- `_audited_transaction`;
- `_append_audit_agent_write`;
- `_json_dumps_canonical`;
- `_validate_no_level0_payload`.

### asyncpg Only

Repositories accept an injected asyncpg pool-compatible object. They never
create pools, read DSNs or shell out to database tools.

### DTOs

All public writes accept typed frozen dataclasses with named fields. Tuple
batches and anonymous dict domain inputs are forbidden.

### Audited Batch Writes

Every non-empty batch write:

1. opens one transaction;
2. writes domain rows;
3. appends exactly one `audit_agent_writes` row;
4. commits both or rolls both back.

Empty batches return `BatchWriteResult.empty()` without touching the database
or creating audit rows.

### JSONB Contract

Repository payloads are serialized with `_json_dumps_canonical()`. Because the
project pool configures asyncpg JSON/JSONB codecs, repository SQL must cast
pre-serialized JSON strings as `::text::jsonb`, never bare `::jsonb`.

### Advisory Lock Parameter Contract

Revision/version allocation uses transaction-scoped `pg_advisory_xact_lock`
inside the same audited transaction. Advisory lock keys are built as textual
strings, but SQL placeholders must first declare the real PostgreSQL type
expected from Python/asyncpg and only then cast to text:

- `datetime` parameters: `$N::timestamptz::text`;
- `date` parameters: `$N::date::text`;
- `UUID` parameters: `$N::uuid::text`.

Do not cast non-string asyncpg parameters directly as `$N::text`; doing so makes
asyncpg select the TEXT encoder and raises client-side `DataError` before the
query reaches PostgreSQL.

### Idempotency And Revision Policies

- `fund_registry`: natural key `fund_cnpj`.
- `fund_daily_info`: existing `lineage_hash + ts` is skipped; changed content
  for the same `fund_cnpj + ts` creates `revision + 1`.
- `fi_instruments`: natural idempotency key `lineage_hash`.
- `debenture_market_data`: existing `lineage_hash + ts` is skipped; changed
  content for the same `fi_id + ts` creates `revision + 1`.
- `company_registry`: natural key `cnpj`.
- `company_listings`: natural key `exchange + ticker`; `company_id` must not be
  overwritten on conflict.
- `fundamentals_statements`: existing `lineage_hash` is skipped; changed
  content for the same company/period/scope creates `version + 1` with
  `prior_version_id` and `restatement_reason`.
- `fundamentals_indicators`: idempotency key `lineage_hash + ts`; no indicator
  calculation occurs in the repository.

### Level 0 Rejection

Repositories reject Level 0 keys in metadata, quality flags, payloads,
statements, indicators and rate specs before any database write.

### Boundary Rules

- `backend.finlib` must not import Qdrant, RAG, Agent0, HTTP clients or LLM
  clients.
- Agent0/RAG must not import `backend.finlib` directly.
- Raw SQL outside tests/docs is confined to `backend/finlib/repositories/` and
  `backend/memory/postgres/`.

## Test Plan

- Unit tests for each repository class and DTO contract.
- Architecture tests for raw SQL placement and import boundaries.
- Live integration test with isolated PostgreSQL test database and full
  migrations.
- Static checks: ruff, mypy strict, pyright and `git diff --check`.
