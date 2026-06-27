# FINLIB-0 FL-PR09 — Debenture Market Data

Branch: `feat/finlib-debenture-market-data`
Status: Initial SDD
Issue: https://github.com/franciscosalido/OPENCLAW/issues/119

## Objective

FL-PR09 adds temporal market observations for debentures already represented
in `fi_instruments`. The PR creates a TimescaleDB-backed table for secondary
market observations while preserving the FL-PR08 boundary:

- `fi_instruments` remains the stable reference catalog.
- `debenture_market_data` stores temporal market data.
- future `fi_positions` remains out of scope and local-only.

## Context And Preconditions

- Current migration head before this PR is `025_create_fi_instruments`.
- PostgreSQL target is 18.x.
- TimescaleDB is required for hypertables.
- `fi_instruments.instrument_id` is the internal primary key.
- FL-PR08 accepts `kind = 'debenture'`.
- FL-PR08 already seeds `anbima_debentures` in `ops_data_sources`.
- `ops_ingestion_runs`, `ops_data_quality_checks` and `audit_agent_writes`
  already exist from earlier FINLIB migrations.
- The official sandbox is Python 3.12 with PostgreSQL client 18.x.

## Scope

This PR creates exactly one schema object family:

- table `debenture_market_data`
- trigger function `enforce_debenture_market_data_instrument_kind()`
- trigger `trg_debenture_market_data_instrument_kind`
- focused indexes for latest-observation and run lineage access

It also adds static and live tests for the schema contract.

## Non-Scope

This PR does not create:

- another debenture catalog
- CRI/CRA market data tables
- `fi_positions`
- user positions or balances
- valuation, duration analytics or credit curves
- ratings
- repositories
- data agents
- downloader or HTTP client
- ANBIMA authentication
- MCP write tools
- A2A runtime
- Qdrant or pgvector changes
- recommendation, rebalance or portfolio logic

## Architecture Decisions

### FK Uses `instrument_id`, Not ISIN

`debenture_market_data.fi_id` references `fi_instruments(instrument_id)`.
ISIN remains an external identifier in the reference catalog. Future ingestion
must resolve an external ISIN to `instrument_id` before inserting an
observation. A missing lookup means the observation must not be inserted.

### Debenture Kind Guard

A plain foreign key cannot ensure that `fi_id` points to a row with
`kind = 'debenture'`. The migration therefore adds a small database trigger:

- `BEFORE INSERT OR UPDATE OF fi_id`
- reads `fi_instruments.kind`
- accepts only `debenture`
- lets the foreign key reject unknown IDs
- raises a generic safe error without leaking issuer, ISIN or payload data

The semantic invariant is bidirectional. Once a debenture instrument has rows
in `debenture_market_data`, `fi_instruments.kind` must not be changed away from
`debenture`. RC-01 adds migration `027_guard_debenture_kind_drift.sql` instead
of editing the already reviewed migration 026, preserving migration checksum
stability. The new migration guards `BEFORE UPDATE OF kind ON fi_instruments`
and rejects kind drift when temporal debenture market data already exists.

### Revision Semantics

ANBIMA market data can be corrected or republished. This PR deliberately uses
revisioned temporal identity:

- `revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0)`
- `PRIMARY KEY (fi_id, ts, revision)`
- `UNIQUE (lineage_hash, ts)`

Identical reingestion uses `ON CONFLICT (lineage_hash, ts) DO NOTHING`.
Corrections produce a new `lineage_hash` and `revision + 1`; previous
revisions remain immutable. Future repository code must use an advisory lock
keyed by `(fi_id, ts)` or an equivalent transaction-safe mechanism before
computing the next revision.

### TimescaleDB

`debenture_market_data` is a hypertable partitioned by `ts` with monthly
chunks:

```sql
SELECT create_hypertable(
    'debenture_market_data',
    'ts',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);
```

Every primary key and unique constraint on the hypertable includes `ts`.

### Source Handling

FL-PR08 already seeds `anbima_debentures`. FL-PR09 should not blindly reseed or
overwrite unrelated source metadata. If the existing methodology text is
insufficient, migration 026 may perform a narrow idempotent
`INSERT ... ON CONFLICT DO UPDATE` for `anbima_debentures` only, documenting
why the additional limitations are required.

The methodology limitations must communicate:

- indicative rates and PUs are secondary-market reference data
- coverage depends on eligible sampled assets
- absence of an observation is not absence of economic value
- access, license, authentication and history may be limited
- public/free windows may be limited
- no operational secrets are stored in schema
- observations can be corrected

### Data Classification

`debenture_market_data` is market data, classified as Level 1/Level 2. It is
not Level 0. It must never include user holding amounts, held face-value
economics, acquisition economics, personal tax identifiers, account or holder
identifiers, brokerage identifiers, custody identifiers, or portfolio
identifiers. Those belong to future local-only position scopes and remain
outside this market-data table.

## Lineage Hash Contract

`lineage_hash` is a SHA-256 hex digest of canonical observation content.
Canonical fields:

- `fi_id`
- `ts`
- `indicative_rate`
- `pu`
- `duration`
- `source_id`
- `schema_version`

`run_id` is intentionally excluded so the same content ingested by two runs
produces the same idempotency hash.

Canonicalization rules:

- `fi_id`: UUID canonical text
- `ts`: ISO-8601 UTC
- numeric values: deterministic decimal strings
- nulls: one documented JSON null representation
- sorted JSON keys

## Field Semantics

- `ts` is the reference date normalized to `00:00:00+00`.
- `ingested_at` is the real insertion time.
- `indicative_rate` can be null; do not impose universal positivity.
- `pu`, when present, must be strictly positive.
- `duration` is measured in business days and can be zero.
- at least one of `indicative_rate`, `pu` or `duration` must be present.
- `quality_flags` and `metadata` must be JSON objects.

## Future Repository Transaction Contract

Future ingestion/repository code must use one transaction:

```sql
BEGIN;
  -- resolve fi_id from external identifier
  -- insert idempotent or revisioned debenture_market_data rows
  -- insert ops_data_quality_checks rows when necessary
  -- append exactly one audit_agent_writes row for the logical batch
COMMIT;
```

If audit append fails, the domain write must roll back. If the domain write
fails, no orphan audit row may exist. Data agents must not use destructive
`UPDATE` or `DELETE` for historical correction.

## Rollback

This PR is additive. In development, rollback is dropping the isolated test
database. In a persistent environment, rollback must be a future migration, not
manual edits to applied migrations.

## Test Plan

Static unit tests:

- migration 026 exists and creates exactly one table
- no forbidden Level 0 or secret-like fields
- FK uses `fi_instruments(instrument_id)`
- no ISIN column
- PK/unique include `ts`
- hypertable contract uses `ts`, one-month chunks and `if_not_exists`
- trigger function and trigger exist
- SDD documents duration, source limits, revision semantics, Level 1/2 and
  exclusion of `run_id` from `lineage_hash`

Live integration tests:

- use isolated `quimera_test_*` database
- apply migrations 000-026
- prove `debenture_market_data` is a real hypertable
- prove idempotent migration runner behavior
- insert valid debenture observations
- reject non-debenture `fi_id`
- reject missing FK rows
- reject invalid DQ cases
- preserve revision 0 while inserting revision 1 corrections
- verify source methodology limitations and cross-sprint tables

Authoritative validation should run in code-sandbox-mcp / Vibe sandbox. Host
validation is useful but not the final certification.

## External References

- TimescaleDB/Tiger Data documentation: unique indexes on hypertables must
  include all partitioning columns.
- PostgreSQL 18 documentation: `CREATE OR REPLACE TRIGGER` and `BEFORE INSERT
  OR UPDATE OF` trigger behavior.
- ANBIMA Developers: Corporate Bonds (Debentures) pricing API discloses bid,
  ask and indicative rates, unit prices and indicative ranges for corporate
  bonds.
- ANBIMA Developers: CRI/CRA pricing API has related source limitations but is
  explicitly out of this PR's table scope.
