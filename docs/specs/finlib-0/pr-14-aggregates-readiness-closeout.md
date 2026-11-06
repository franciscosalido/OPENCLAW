# FINLIB-0 FL-PR14 - Aggregates Readiness Closeout

Branch: `feat/finlib-aggregates-readiness-closeout`
GitHub Issue: `#123`
Status: Initial SDD

## Objective

FL-PR14 closes FINLIB-0 with read-optimized aggregate/view objects,
conservative TimescaleDB compression readiness, a deterministic FINLIB
readiness gate, a data dictionary, Go/No-Go criteria and handoff guidance for
future data agents.

This PR does not implement data agents, ingesters, Kronos execution, model
loading, forecasts, Qdrant mutation, pgvector mutation, new repositories or
destructive retention.

The sprint is ready for data agents only when:

```bash
python scripts/check_finlib_readiness.py --json
```

returns exit code `0`, `status == "READY"` and
`ready_for_data_agents == true` against a live isolated database.

## Real Repository State

- Local `main` contains FL-PR13 through merge commit
  `52af8f9 Merge local FINLIB FL-PR12 and FL-PR13 stack`.
- Local `main` is ahead of `origin/main`; remote Draft PR creation is deferred
  until the local stack is authorized for publication.
- Current migration head: `028_create_company_fundamentals.sql`.
- FL-PR14 migration number: `029_create_finlib_aggregates_readiness.sql`.
- `market_bars` exists in migration `012_create_market_bars.sql`.
- `market_bars` is a hypertable on `ts`.
- `market_bars` has `amount`, `volume`, `timeframe`, `instrument_id` and OHLC
  columns.
- `macro_observations` exists, is a hypertable on `ref_ts`, and uses
  `revision`.
- `fund_daily_info` exists, is a hypertable on `ts`, and uses `revision`.
- `treasury_prices` exists, is a hypertable on `ts`.
- `fundamentals_indicators` exists and is a hypertable on `ts`, but no new
  aggregate is planned for it in FL-PR14.
- Existing view: `vw_fx_brlusd`.
- No FINLIB continuous aggregate exists in the repository before this PR.

## Migration Plan

File:

`backend/memory/postgres/migrations/029_create_finlib_aggregates_readiness.sql`

Required sections:

- Section A: read-only views.
- Section B: continuous aggregates where the schema supports true temporal
  aggregation.
- Section C: refresh policies for created continuous aggregates, only when safe
  and idempotent.
- Section D: compression readiness/conservative compression.
- Section E: retention policies intentionally absent in V1.

Planned read objects:

- `macro_observations_latest_revision` regular view.
- `treasury_latest_prices_view` regular view.
- `fund_daily_info_latest_revision` regular view.
- `fund_monthly_quota_returns` regular view or CAGG depending on safe SQL
  semantics.
- `market_bars_1d_cagg` continuous aggregate if TimescaleDB accepts it in the
  migration runner.
- `market_bars_1d` regular alias view over the CAGG when created.

The implementation must not use `DROP`, `TRUNCATE`, `DELETE`, `drop_chunks`,
`add_retention_policy` or any destructive retention policy.

## Readiness Script Plan

File:

`scripts/check_finlib_readiness.py`

Requirements:

- asyncpg only;
- JSON stdout;
- exit `0` only when FINLIB is ready;
- sanitized output, no DSN, password, raw traceback or secret;
- read-only and idempotent;
- no schema writes;
- no Qdrant, Kronos, LLM, HTTP or download calls.

The JSON contract must include:

- `status`;
- `checked_at`;
- `migration_head`;
- `postgres`;
- `timescaledb`;
- `extensions`;
- `schemas`;
- `repositories`;
- `memory_boundary`;
- `aggregates`;
- `compression`;
- `kronos_input_ready`;
- `ready_for_data_agents`;
- `failed_checks`.

FINLIB readiness must not be blocked only because Kronos input is degraded.
Kronos readiness is reported separately.

## Documentation Plan

Required docs:

- `docs/data/DATA_DICTIONARY.md`;
- `docs/sprints/FINLIB0_DONE_CRITERIA.md`;
- `docs/sprints/FINLIB0_HANDOFF_TO_DATA_AGENTS.md`.

The data dictionary is a contract, not decoration. It must list FINLIB objects
from migrations `018` through `029`, including source/run/lineage requirements,
revision semantics, hypertable status, compression/retention posture,
repository owner, future data-agent owner, Level 0 risk and Kronos relevance.

## Future TimescaleDB To Kronos Integration

TimescaleDB is the future canonical source of OHLCVA/K-line frames for Kronos.
Kronos must not treat Qlib files as the source of truth inside QUIMERA. Future
Qlib/Kronos manifests are disposable projections from PostgreSQL/TimescaleDB.

FL-PR14 does not run Kronos, create `model_runs`, create `kronos_forecasts` or
load models. It only reports whether `market_bars`/`market_bars_1d` are ready
enough for future Kronos input planning.

## Test Plan

Focused:

```bash
uv run pytest \
  tests/unit/test_finlib_readiness_script_contract.py \
  tests/unit/test_finlib_data_dictionary_contract.py \
  tests/unit/test_finlib_closeout_docs_contract.py \
  tests/architecture/test_finlib_no_destructive_retention.py \
  -q
```

Live:

```bash
uv run pytest \
  tests/integration/test_finlib_continuous_aggregates_live.py \
  tests/integration/test_check_finlib_readiness_live.py \
  -q
```

Static:

```bash
uvx ruff check scripts/check_finlib_readiness.py tests/unit/test_finlib_readiness_script_contract.py tests/unit/test_finlib_data_dictionary_contract.py tests/unit/test_finlib_closeout_docs_contract.py tests/architecture/test_finlib_no_destructive_retention.py
uvx ruff format --check scripts/check_finlib_readiness.py tests/unit/test_finlib_readiness_script_contract.py tests/unit/test_finlib_data_dictionary_contract.py tests/unit/test_finlib_closeout_docs_contract.py tests/architecture/test_finlib_no_destructive_retention.py
uv run mypy scripts/check_finlib_readiness.py --strict
uv run pyright scripts/check_finlib_readiness.py
uvx sqlfluff lint backend/memory/postgres/migrations/029_create_finlib_aggregates_readiness.sql --dialect postgres
git diff --check
```

## Out Of Scope

- Data agents;
- Kronos runner;
- Kronos model loading;
- HuggingFace downloads;
- `model_runs` writes;
- `kronos_forecasts` writes;
- forecast quality;
- new repositories;
- new ingestion scripts;
- Qdrant mutation;
- pgvector mutation;
- destructive retention;
- modifying prior migrations.

