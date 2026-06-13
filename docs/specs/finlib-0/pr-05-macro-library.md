# FL-PR05 — Macro Library

Status: Draft implementation SDD

Branch: `feat/finlib-macro-library`

## Scope

FL-PR05 creates the minimal Brazilian macroeconomic and FX library for
FINLIB-0. It adds only:

- `macro_series_catalog`
- `macro_observations`
- `vw_fx_brlusd`
- `config/macro_series_seed.yaml`

It does not implement ingestion, repositories, agents, MCP tools, Qdrant,
pgvector, Kronos adapters or any FL-PR06+ library.

## Source Policy

The canonical initial provider is `bcb_sgs`. The migration seeds it into
`ops_data_sources` so every catalog row can reference an operational source.

BCB/SGS provider codes in `config/macro_series_seed.yaml` are planning
references. They must not be treated as ground truth until a future ingestion
PR verifies them against the live BCB/SGS catalog/API with bounded date
filters. The BCData URL contract is:

```text
https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_serie}/dados?formato=json&dataInicial={dataInicial}&dataFinal={dataFinal}
```

Every seeded series uses `provider_code_status = 'planning_reference'` and
`requires_live_verification = true`.

### RC-01 PTAX Code Evidence

The FL-PR05 seed keeps PTAX codes as planning references, but RC-01 records the
current evidence used to avoid a misleading pair assumption:

- BCB Dados Abertos identifies SGS `10813` as
  `Taxa de câmbio - Livre - Dólar americano (compra)`.
- BCB Dados Abertos identifies SGS `1` as
  `Taxa de câmbio - Livre - Dólar americano (venda) - diário`.
- The official BCData/SGS endpoint pattern is
  `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_serie}/dados`.
- Direct bounded API sanity checks for 2023-01-02 through 2023-01-05 returned
  plausible USD/BRL values for `10813` and `1`.
- The same bounded sanity check for `10814` returned a non-FX value in the
  checked window, so `10814` must not replace `1` without future live catalog
  evidence.

Therefore `ptax_usdbrl_venda` remains `provider_code: "1"` in this PR, still
with `provider_code_status = 'planning_reference'` and
`requires_live_verification = true`.

## Series

The initial seed contains exactly seven stored series:

- `ipca`
- `igpm`
- `selic_meta`
- `selic_diaria`
- `cdi`
- `ptax_usdbrl_compra`
- `ptax_usdbrl_venda`

BRL/USD is not a stored macro series. It is derived by `vw_fx_brlusd`.

## Observation Model

`macro_observations` is a TimescaleDB hypertable partitioned by `ref_ts` with
`chunk_time_interval => INTERVAL '3 months'`. Three months is a practical
baseline for mixed daily/business-daily and monthly macro series: it avoids
over-fragmenting low-frequency IPCA/IGP-M while keeping PTAX/Selic/CDI chunks
small enough for time-window scans.

Required provenance fields:

- `source_id`
- `run_id`
- `lineage_hash`

`source_id` references `ops_data_sources`; `run_id` references
`ops_ingestion_runs`.

## Revision Semantics

Revisions are append-only rows identified by:

```text
PRIMARY KEY (series_code, ref_ts, revision)
```

Revision `0` is the first accepted value for a series/date. A revised value is
inserted as `revision + 1`; the old value remains intact. This PR intentionally
does not implement Python revision allocation. A future repository must allocate
`revision + 1` inside a transaction and use an advisory lock keyed by
`(series_code, ref_ts)` or an equivalent serializable operation.

## Idempotency

Identical reingestion is guarded by a lineage constraint:

```text
UNIQUE (lineage_hash, ref_ts)
```

TimescaleDB requires unique constraints on hypertables to include every
partitioning column, so `ref_ts` is included with `lineage_hash`. The canonical
lineage hash contract includes `ref_ts`, making this equivalent to unique
lineage identity for FINLIB-0:

- `series_code`
- `ref_ts`
- `value`
- `source_id`
- `provider_code`
- `schema_version`

Callers should use `INSERT ... ON CONFLICT (lineage_hash, ref_ts) DO NOTHING`
for duplicate identical batches.

## FX View

`vw_fx_brlusd` derives BRL/USD from the latest revision of PTAX USD/BRL compra
and venda for the same `ref_ts`. It is a normal PostgreSQL view, not a
materialized view and not a stored series.

Outputs:

- `ref_ts`
- `usdbrl_bid`
- `usdbrl_ask`
- `usdbrl_mid`
- `brlusd_bid`
- `brlusd_ask`
- `brlusd_mid`
- provenance fields from the paired PTAX rows

The view uses an inner join so dates missing either compra or venda are absent.
Zero-valued PTAX observations are also excluded from `vw_fx_brlusd`; this
protects the `1 / value` derived BRL/USD columns and should not occur for valid
PTAX data.

## Future Repository And Audit Contract

A future `MacroRepository` must write domain rows and exactly one
`audit_agent_writes` row per logical batch in the same transaction. If the audit
insert fails, the domain write must roll back. This PR only creates the schema
needed for that future transaction contract.
