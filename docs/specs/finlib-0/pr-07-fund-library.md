# FINLIB-0 FL-PR07 — Fund Library

Branch: `feat/finlib-fund-library`
Status: Implementation PR

## Scope

FL-PR07 creates the minimal CVM fund registry and daily fund report library
for FINLIB-0. The PR adds exactly two durable tables:

- `fund_registry`
- `fund_daily_info`

It does not add repositories, agents, MCP tools, runtime ingestion, live CVM
clients, Qdrant objects, pgvector objects, portfolio logic, recommendation
logic or FL-PR08+ tables.

## Source

The canonical source row is `ops_data_sources.source_id =
'cvm_informes_diarios'`.

The sprint master spec listed `cvm_fundos_inf_diario` as an early planning
label. FL-PR07 standardizes on `cvm_informes_diarios` because this PR models
the CVM daily report dataset, not a broader fund source family.

CVM Dados Abertos describes Informe Diario as a demonstrative report by
competence date containing total portfolio value, net worth, quota value,
daily subscriptions, daily redemptions and shareholders. CVM also states that
since May 2022 the daily report files are published as compressed CSV files.
The CSV is a future ingestion contract. This PR stores normalized temporal
memory, not the raw file.

## Registry Semantics

`fund_registry.fund_cnpj` is the canonical natural key and is stored as 14
digits without punctuation. Future ingestion code must normalize masked CNPJ
values before writing. The table intentionally keeps the registry minimal:
legal name, optional CVM class/type, status, registration date, source and
metadata.

## Time And Revision Semantics

`fund_daily_info.ts` is the CVM `DT_COMPTC` reference date normalized to
`YYYY-MM-DD 00:00:00+00`. `ingested_at` is the real insertion timestamp.

Reapresentacao or correction of the same fund/date is represented by a new row
with `revision = max(revision) + 1`. The original row remains preserved.
Identical reingestion uses `ON CONFLICT (lineage_hash, ts) DO NOTHING` and
creates no new row. Future concurrent ingestion must use an advisory lock keyed
by `(fund_cnpj, ts)` or an equivalent transaction-safe mechanism to avoid races
while computing the next revision. Historical corrections must not use
destructive `UPDATE` or `DELETE`.

## TimescaleDB Contract

`fund_daily_info` is a TimescaleDB hypertable partitioned by `ts` with
`chunk_time_interval => INTERVAL '1 month'`.

TimescaleDB unique constraints on hypertables must include the partitioning
column. For that reason:

- Logical row identity is `PRIMARY KEY (fund_cnpj, ts, revision)`.
- Identical reingestion idempotency is expressed as
  `UNIQUE (lineage_hash, ts)`.

`fund_registry` is not a hypertable.

## Data Quality Contract

Schema constraints cover baseline data quality:

- `quota_value` is mandatory and must be greater than zero.
- `net_worth` is mandatory. It is not constrained to be positive because
  negative net worth can exist in special fund situations and should be a
  quality signal, not a schema impossibility.
- `total_portfolio_value`, `inflow` and `outflow` are nullable, but cannot be
  negative when present.
- `shareholders` is mandatory and cannot be negative.
- `source_id`, `run_id` and `lineage_hash` are mandatory.
- JSON metadata fields must be JSON objects.

## Lineage Hash Contract

Future ingestion/repository code must compute the stable SHA-256 lineage hash
from the canonical JSON serialization of:

- `fund_cnpj`
- `ts`
- `total_portfolio_value`
- `quota_value`
- `net_worth`
- `inflow`
- `outflow`
- `shareholders`
- `source_id`
- `schema_version`

The hash is revision-independent: a corrected economic payload for the same
fund/date receives a new `revision` and a new `lineage_hash`, while identical
reingestion remains a no-op.

## Future Repository And Audit Contract

Future fund batches must use one database transaction:

```sql
BEGIN;
  -- upsert fund_registry
  -- insert idempotent fund_daily_info rows
  -- insert ops_data_quality_checks rows when violations are detected
  -- insert exactly one audit_agent_writes row for the logical batch
COMMIT;
```

If the audit insert fails, the domain write must roll back. If the domain write
fails, no orphan audit row may be created. No data agent may issue `DELETE`.

## CSV Sample Contract

The PR test suite keeps a small in-file CSV sample with headers compatible
with the CVM Informe Diario family:

- `CNPJ_FUNDO`
- `DT_COMPTC`
- `VL_TOTAL`
- `VL_QUOTA`
- `VL_PATRIM_LIQ`
- `CAPTC_DIA`
- `RESG_DIA`
- `NR_COTST`

The sample parser is test-local only. Runtime CSV ingestion and layout-alias
handling belong to future repository/ingestion PRs.
