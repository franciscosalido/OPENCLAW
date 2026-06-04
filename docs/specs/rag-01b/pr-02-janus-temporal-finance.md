# RAG-01B PR-02 - Janus Temporal Finance Memory

## Objective

PR-02 adds the finance/Kronos/Qlib face of the QUIMERA Janus Temporal Memory
Fabric. PostgreSQL 18.4 + TimescaleDB 2.23+ is the single canonical temporal
store for structured financial memory. Qlib and Kronos surfaces are contracts
and projections only.

This PR does not execute Kronos, generate Qlib `.bin`, create MCP, expose an
API, touch Qdrant, or implement trading.

## Decisions

- PostgreSQL 18.4 is the target database.
- TimescaleDB 2.23+ is the target temporal extension.
- SQL migrations 010-016 reuse the PR-01 migration runner and
  `schema_migrations`.
- `market_bars`, `market_features`, and `kronos_forecasts` are TimescaleDB
  hypertables.
- Entity/execution tables use PostgreSQL 18 `uuidv7()`.
- Qlib artifacts are disposable projections, never canonical memory.
- Kronos outputs return to PostgreSQL/TimescaleDB in model run and forecast
  tables.
- Repository I/O is async and uses asyncpg directly.
- Heavy ORMs and runtime ML dependencies are forbidden.

## Schema

Finance memory adds:

- `market_instruments`
- `market_calendars`
- `market_bars`
- `market_features`
- `model_runs`
- `kronos_forecasts`
- `qlib_projection_manifests`
- `qlib_ohlcv_v1`

The temporal envelope uses `TIMESTAMPTZ`, `ingested_at`, `source_id`,
`schema_version`, `lineage_hash`, JSONB metadata/quality fields and typed
financial tables rather than a generic EAV store.

## Repository

`FinanceRepository` accepts an injected asyncpg pool or PR-01 `PostgresClient`.
It creates/upserts instruments, bars, features, model runs, forecasts and Qlib
projection manifests. SQL is parameterized. `ORDER BY` direction is controlled
by an internal boolean branch, not user-provided SQL.

## Tests

- Unit tests cover dataclass validation, schema SQL, Timescale hypertable
  declarations, Qlib manifest contracts, Kronos frame contracts and repository
  SQL safety.
- Integration tests apply PR-01 + PR-02 migrations when a PostgreSQL DSN is
  available and skip cleanly when DSN or TimescaleDB is unavailable.

## Risks

- TimescaleDB availability depends on the local PostgreSQL image used by the
  developer or CI environment.
- PostgreSQL 18 `uuidv7()` is required by the new entity tables.
- Real Qlib/Kronos adapters remain future work and must preserve the canonical
  memory boundary.
- RC-01 corrected the `get_market_bars_window` ordering query to use explicit
  ASC/DESC SQL branches instead of templated direction replacement.
- Bulk writes currently loop through async repository methods one row at a
  time. Before real ingestion, a performance PR should evaluate
  `copy_records_to_table` or `executemany` for large market bar and forecast
  batches.
- `KronosForecastResult.predictions` remains intentionally shape-agnostic in
  this contract PR. A future Kronos adapter PR should define a concrete
  `TypeAlias` or `Protocol` for prediction payloads.
- The pre-existing `test_rag_observability_config` temporary-file permission
  issue is unrelated to PR-02 and should be handled in a separate maintenance
  PR if it reproduces.

## Out Of Scope

No real Kronos execution, Qlib export, pyqlib dependency, torch, transformers,
GPU, model downloads, trading strategy, REST, gRPC, MCP server, scheduler,
dashboard, Qdrant writes, pgvector storage or heavy ORM.
