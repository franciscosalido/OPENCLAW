# FINLIB-0 Handoff To Data Agents

Status: Gate document for the next sprint

## Entry Gate

Data agents may start only after:

```bash
python scripts/check_finlib_readiness.py --json
```

returns:

- `status == "READY"`;
- `ready_for_data_agents == true`;
- `failed_checks == []`.

If readiness is `BLOCKED`, the agent must not start.

## Authorized Repositories

Future agents write only through:

- `OpsRepository`;
- `MacroRepository`;
- `TreasuryRepository`;
- `FundRepository`;
- `FixedIncomeRepository`;
- `FundamentalsRepository`.

## Authorized Write Tables

Agents may write through repositories to:

- `ops_data_sources`;
- `ops_ingestion_runs`;
- `ops_ingestion_watermarks`;
- `ops_data_quality_checks`;
- `ops_outbox_events`;
- `macro_series_catalog`;
- `macro_observations`;
- `treasury_bonds`;
- `treasury_prices`;
- `fund_registry`;
- `fund_daily_info`;
- `fi_instruments`;
- `debenture_market_data`;
- `company_registry`;
- `company_listings`;
- `fundamentals_statements`;
- `fundamentals_indicators`;
- `audit_agent_writes` only through repository audit helper.

## Prohibited Direct Writes

Agents must not write directly to PostgreSQL with ad hoc SQL. Agents must not
write Qdrant, pgvector, `model_runs`, `kronos_forecasts` or Qlib projection
files in the FINLIB-0 handoff.

## Transaction Rule

Every non-empty domain write must commit the domain rows and exactly one
`audit_agent_writes` row in the same transaction. Rollback cancels both.

## Outbox Rule

Use `OpsRepository.enqueue_event()` and `OpsRepository.poll_events()`. The
`FOR UPDATE SKIP LOCKED` polling contract is encapsulated in the repository.

## Watermark Rule

Use `OpsRepository.get_watermark()` and `OpsRepository.set_watermark()`.
Watermarks are monotonic where the schema enforces monotonic timestamps.

## Level 0 Boundary

Do not expose CPF, account numbers, brokerage identifiers, positions,
quantities, acquisition prices, cost basis, private statements or portfolio
payloads to remote APIs or logs. Level 0 data remains local.

## Future TimescaleDB To Kronos Integration

TimescaleDB is the future canonical source of OHLCVA/K-line frames. Future
Kronos adapters consume:

- `instrument_id`;
- `ts`;
- `open`;
- `high`;
- `low`;
- `close`;
- `volume`;
- `amount`.

Kronos does not run in FINLIB-0. Kronos must not treat Qlib files as QUIMERA's
source of truth. Future `model_runs` and `kronos_forecasts` must be append-only,
audited and linked to source query hashes, transform hashes, input window hash,
lookback, prediction length and deterministic config.

FINLIB readiness does not require Kronos input readiness unless explicitly
requested with `--require-kronos-input-ready`.

## Failure Protocol

Do not start a data agent if:

- readiness is `BLOCKED`;
- memory boundary tests fail;
- audit layer is missing;
- repository imports fail;
- destructive retention is detected;
- migration head is not `029_create_finlib_aggregates_readiness`.
