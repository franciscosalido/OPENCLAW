# FINLIB-0 Data Dictionary

Status: Active
Sprint: FINLIB-0

Each FINLIB object must preserve source, run and lineage metadata where the
schema requires it. Data agents must write through repositories only.

## Ops

### ops_data_sources
- Type: table
- Domain: ops
- Description: registry of external and internal data sources.
- Primary key: `source_id`
- Natural key: `source_id`
- Provenance: source metadata and methodology limitations.
- Revision/version semantics: not revisioned.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: OpsRepository
- Future data agent: all agents register source dependencies here.
- Level 0 risk: low; do not store private credentials.
- Kronos relevance: source registry for future market/Kronos projections.

### ops_ingestion_runs
- Type: table
- Domain: ops
- Description: execution log for ingestion or dry-run batches.
- Primary key: `run_id`
- Natural key: `run_id`
- Provenance: `source_id`, `agent_id`, `trace_id`, counters and metadata.
- Revision/version semantics: terminal status only, no history overwrite.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: OpsRepository
- Future data agent: every batch starts and finishes a run.
- Level 0 risk: medium; metadata must not contain private positions.
- Kronos relevance: future Kronos projections should link to run lineage.

### ops_ingestion_watermarks
- Type: table
- Domain: ops
- Description: canonical per-source dataset watermark.
- Primary key: `(source_id, dataset)`
- Natural key: `(source_id, dataset)`
- Provenance: `run_id`, `source_snapshot_hash`, metadata.
- Revision/version semantics: monotonic timestamp guard.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: OpsRepository
- Future data agent: checkpoint for incremental ingestion.
- Level 0 risk: low.
- Kronos relevance: protects future K-line projections from replay drift.

### ops_data_quality_checks
- Type: table
- Domain: ops
- Description: results of data-quality checks.
- Primary key: `check_id`
- Natural key: `check_id`
- Provenance: `run_id`, observed JSON, expected JSON.
- Revision/version semantics: append-only check records.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: OpsRepository
- Future data agent: record validation before commit/handoff.
- Level 0 risk: medium; observed payloads must stay sanitized.
- Kronos relevance: K-line quality gates before model input.

### ops_outbox_events
- Type: table
- Domain: ops
- Description: reliable local outbox for future async dispatch.
- Primary key: `event_id`
- Natural key: `event_id`
- Provenance: `aggregate_type`, `aggregate_id`, `payload`, `run_id`.
- Revision/version semantics: attempts and status transitions.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: OpsRepository
- Future data agent: enqueue and poll via SKIP LOCKED only in repository.
- Level 0 risk: medium; payload must not contain private account data.
- Kronos relevance: future forecast events may be queued here.

## Audit

### audit_agent_writes
- Type: table
- Domain: audit
- Description: append-only audit record for repository writes.
- Primary key: `audit_id`
- Natural key: `audit_id`
- Provenance: `trace_id`, `run_id`, `agent_id`, `target_table`, `batch_hash`.
- Revision/version semantics: append-only.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: BaseRepository audited transaction helper.
- Future data agent: every non-empty repository write creates one row.
- Level 0 risk: medium; metadata must stay sanitized.
- Kronos relevance: future model inputs and forecasts must be auditable.

## Macro

### macro_series_catalog
- Type: table
- Domain: macro
- Description: macroeconomic and FX series catalog.
- Primary key: `series_code`
- Natural key: `series_code`
- Provenance: `source_id`, provider code and methodology note.
- Revision/version semantics: catalog upsert by series.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: MacroRepository
- Future data agent: macro and FX ingestion.
- Level 0 risk: low.
- Kronos relevance: macro features may enrich future model context.

### macro_observations
- Type: table
- Domain: macro
- Description: temporal macro observations.
- Primary key: `(series_code, ref_ts, revision)`
- Natural key: `(series_code, ref_ts, revision)`
- Unique constraints: `(lineage_hash, ref_ts)`
- Provenance: `source_id`, `run_id`, `lineage_hash`, quality flags.
- Revision/version semantics: changed observation creates `revision + 1`.
- Hypertable: yes, `ref_ts`
- Continuous aggregate: no
- Compression: no automatic policy in V1
- Retention: none
- Repository: MacroRepository
- Future data agent: macro series agent.
- Level 0 risk: low.
- Kronos relevance: optional exogenous context, not K-line source.

### macro_observations_latest_revision
- Type: view
- Domain: macro
- Description: latest revision per macro series and timestamp.
- Primary key: derived `(series_code, ref_ts)` not enforced.
- Natural key: `(series_code, ref_ts)`
- Provenance: inherited from `macro_observations`.
- Revision/version semantics: selects highest `revision`.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: read-only
- Future data agent: read model for macro consumers.
- Level 0 risk: low.
- Kronos relevance: optional feature source.

## Treasury

### treasury_bonds
- Type: table
- Domain: treasury
- Description: Tesouro Direto bond registry.
- Primary key: `bond_id`
- Natural key: `(bond_type, maturity_date)`
- Unique constraints: `(bond_type, maturity_date)`
- Provenance: `source_id`, metadata.
- Revision/version semantics: catalog upsert.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: TreasuryRepository
- Future data agent: Tesouro agent.
- Level 0 risk: low.
- Kronos relevance: none.

### treasury_prices
- Type: table
- Domain: treasury
- Description: daily mark-to-market treasury prices and rates.
- Primary key: `(bond_id, ts)`
- Natural key: `(bond_id, ts)`
- Unique constraints: `(lineage_hash, ts)`
- Provenance: `source_id`, `run_id`, `lineage_hash`.
- Revision/version semantics: idempotent by lineage, no revision column.
- Hypertable: yes, `ts`
- Continuous aggregate: no
- Compression: no automatic policy in V1
- Retention: none
- Repository: TreasuryRepository
- Future data agent: Tesouro agent.
- Level 0 risk: low.
- Kronos relevance: none.

### treasury_latest_prices_view
- Type: view
- Domain: treasury
- Description: latest price row per bond.
- Primary key: derived `bond_id` not enforced.
- Natural key: `bond_id`
- Provenance: inherited from `treasury_prices`.
- Revision/version semantics: latest `ts`.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: read-only
- Future data agent: read model for treasury consumers.
- Level 0 risk: low.
- Kronos relevance: none.

## Funds

### fund_registry
- Type: table
- Domain: funds
- Description: CVM fund registry.
- Primary key: `fund_cnpj`
- Natural key: `fund_cnpj`
- Provenance: `source_id`, metadata.
- Revision/version semantics: catalog upsert.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: FundRepository
- Future data agent: CVM fund agent.
- Level 0 risk: medium; CNPJ is public, never store investor position.
- Kronos relevance: none.

### fund_daily_info
- Type: table
- Domain: funds
- Description: CVM Informe Diario observations.
- Primary key: `(fund_cnpj, ts, revision)`
- Natural key: `(fund_cnpj, ts, revision)`
- Unique constraints: `(lineage_hash, ts)`
- Provenance: `source_id`, `run_id`, `lineage_hash`.
- Revision/version semantics: changed daily row creates `revision + 1`.
- Hypertable: yes, `ts`
- Continuous aggregate: no
- Compression: no automatic policy in V1
- Retention: none
- Repository: FundRepository
- Future data agent: CVM fund agent.
- Level 0 risk: medium; never combine with private holdings in this table.
- Kronos relevance: none.

### fund_daily_info_latest_revision
- Type: view
- Domain: funds
- Description: latest revision per fund and timestamp.
- Primary key: derived `(fund_cnpj, ts)` not enforced.
- Natural key: `(fund_cnpj, ts)`
- Provenance: inherited from `fund_daily_info`.
- Revision/version semantics: selects highest `revision`.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: read-only
- Future data agent: read model for fund consumers.
- Level 0 risk: medium.
- Kronos relevance: none.

### fund_monthly_quota_returns
- Type: view
- Domain: funds
- Description: monthly quota return from latest daily revisions.
- Primary key: derived `(fund_cnpj, month_ts)` not enforced.
- Natural key: `(fund_cnpj, month_ts)`
- Provenance: inherited from latest fund daily info.
- Revision/version semantics: latest revisions only.
- Hypertable: no
- Continuous aggregate: no in V1.
- Compression: no
- Retention: none
- Repository: read-only
- Future data agent: read model for fund analytics.
- Level 0 risk: medium.
- Kronos relevance: none.

## Fixed Income

### fi_instruments
- Type: table
- Domain: fixed_income
- Description: private fixed-income instrument registry.
- Primary key: `instrument_id`
- Natural key: `lineage_hash`
- Unique constraints: `lineage_hash`
- Provenance: `source_id`, optional `run_id`, `lineage_hash`.
- Revision/version semantics: idempotent by lineage.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: FixedIncomeRepository
- Future data agent: private fixed income agent.
- Level 0 risk: high when sourced from user statements; stay local.
- Kronos relevance: none.

### debenture_market_data
- Type: table
- Domain: fixed_income
- Description: temporal public/semi-public debenture market data.
- Primary key: `(fi_id, ts, revision)`
- Natural key: `(fi_id, ts, revision)`
- Unique constraints: `(lineage_hash, ts)`
- Provenance: `source_id`, `run_id`, `lineage_hash`.
- Revision/version semantics: changed row creates `revision + 1`.
- Hypertable: yes, `ts`
- Continuous aggregate: no
- Compression: no automatic policy in V1
- Retention: none
- Repository: FixedIncomeRepository
- Future data agent: debenture data agent.
- Level 0 risk: low for public data, high if mixed with private positions.
- Kronos relevance: none.

## Fundamentals

### company_registry
- Type: table
- Domain: fundamentals
- Description: canonical company identity.
- Primary key: `company_id`
- Natural key: `cnpj`
- Unique constraints: `cnpj`, `lineage_hash`
- Provenance: `source_id`, `lineage_hash`.
- Revision/version semantics: identity upsert.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: FundamentalsRepository
- Future data agent: fundamentals agent.
- Level 0 risk: low.
- Kronos relevance: optional context only.

### company_listings
- Type: table
- Domain: fundamentals
- Description: exchange ticker/listing linked to company identity.
- Primary key: `listing_id`
- Natural key: `(exchange, ticker)`
- Unique constraints: `(exchange, ticker)`, `lineage_hash`
- Provenance: `source_id`, `lineage_hash`.
- Revision/version semantics: listing upsert.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: FundamentalsRepository
- Future data agent: fundamentals/listing agent.
- Level 0 risk: low.
- Kronos relevance: ticker to company context.

### fundamentals_statements
- Type: table
- Domain: fundamentals
- Description: versioned financial statement payloads.
- Primary key: `statement_id`
- Natural key: `(company_id, period_type, period_kind, statement_scope, period_end, version)`
- Unique constraints: natural statement version tuple, `lineage_hash`
- Provenance: `source_id`, `run_id`, `lineage_hash`.
- Revision/version semantics: restatement creates `version + 1`.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: FundamentalsRepository
- Future data agent: fundamentals agent.
- Level 0 risk: low.
- Kronos relevance: optional explanatory context.

### fundamentals_indicators
- Type: table
- Domain: fundamentals
- Description: deterministic Python-derived indicators.
- Primary key: `(company_id, ts, indicator_set, source_statement_id)`
- Natural key: `(company_id, ts, indicator_set, source_statement_id)`
- Unique constraints: `(lineage_hash, ts)`
- Provenance: `run_id`, `lineage_hash`, `computation_hash`.
- Revision/version semantics: derived from statement versions.
- Hypertable: yes, `ts`
- Continuous aggregate: no in V1.
- Compression: no automatic policy in V1
- Retention: none
- Repository: FundamentalsRepository
- Future data agent: fundamentals agent.
- Level 0 risk: low.
- Kronos relevance: optional exogenous context.

## Aggregates And Kronos Readiness

### market_bars
- Type: table
- Domain: market
- Description: canonical OHLCVA market bars.
- Primary key: `(instrument_id, timeframe, ts)`
- Natural key: `(instrument_id, timeframe, ts)`
- Provenance: `source_id`, `lineage_hash`, metadata.
- Revision/version semantics: no revision column; schema_version tracks contract.
- Hypertable: yes, `ts`
- Continuous aggregate: no
- Compression: existing base table, no new policy in FL-PR14.
- Retention: none
- Repository: legacy finance repository.
- Future data agent: market bars agent.
- Level 0 risk: low for public data.
- Kronos relevance: canonical future OHLCVA source.

### market_bars_1d_cagg
- Type: continuous aggregate
- Domain: market
- Description: daily OHLCVA aggregation over `market_bars`.
- Primary key: derived `(instrument_id, timeframe, ts)` not enforced.
- Natural key: `(instrument_id, timeframe, ts)`
- Provenance: inherited source_id summary, schema_version `market-bar-1d-v1`.
- Revision/version semantics: aggregate refresh, not revisioned.
- Hypertable: continuous aggregate over hypertable.
- Continuous aggregate: yes
- Compression: compression-ready; no automatic policy in V1.
- Retention: none
- Repository: read-only
- Future data agent: market data / Kronos preparation.
- Level 0 risk: low for public data.
- Kronos relevance: preferred future K-line frame.

### market_bars_1d
- Type: view
- Domain: market
- Description: stable read alias over `market_bars_1d_cagg`.
- Primary key: derived `(instrument_id, timeframe, ts)` not enforced.
- Natural key: `(instrument_id, timeframe, ts)`
- Provenance: inherited from CAGG.
- Revision/version semantics: aggregate refresh.
- Hypertable: no
- Continuous aggregate: no, alias view.
- Compression: no
- Retention: none
- Repository: read-only
- Future data agent: market data / Kronos preparation.
- Level 0 risk: low.
- Kronos relevance: stable future Kronos OHLCVA input.

### vw_kronos_ohlcva_input
- Type: view
- Domain: market/Kronos readiness
- Description: read-only projection of OHLCVA fields for future Kronos adapters.
- Primary key: derived `(instrument_id, ts)` not enforced.
- Natural key: `(instrument_id, timeframe, ts)`
- Provenance: inherited from `market_bars_1d`.
- Revision/version semantics: projection only.
- Hypertable: no
- Continuous aggregate: no
- Compression: no
- Retention: none
- Repository: read-only
- Future data agent: future Kronos adapter, not implemented in FINLIB-0.
- Level 0 risk: low for public data.
- Kronos relevance: direct planning contract.

## Future Objects

The following are FUTURE and do not exist in FINLIB-0:

- FUTURE `model_runs` writes for Kronos execution metadata.
- FUTURE `kronos_forecasts` writes for append-only forecasts.
- FUTURE `qlib_projection_manifests` generated from canonical TimescaleDB data.
- FUTURE data agents for macro, treasury, funds, fixed income and fundamentals.
