# FINLIB-0 FL-PR06 — Treasury Library

Branch: `feat/finlib-treasury-library`
Status: Implementation PR

## Scope

FL-PR06 creates the minimal Tesouro Direto mark-to-market library for
FINLIB-0. The PR adds exactly two durable tables:

- `treasury_bonds`
- `treasury_prices`

It does not add repositories, agents, MCP tools, runtime ingestion, Qdrant
objects, pgvector objects, portfolio logic, broker access or FL-PR07+ tables.

## Source

The canonical source row is `ops_data_sources.source_id =
'tesouro_transparente'`.

The existing `ops_data_sources.kind` domain from FL-PR02 includes `treasury`
and does not include `government_treasury`. Therefore this PR uses
`kind = 'treasury'` and documents `government_treasury` as a rejected planning
label, not a schema value.

Tesouro Transparente publishes the "Taxas dos Titulos Ofertados pelo Tesouro
Direto" dataset as a daily CSV. The CSV is a future ingestion contract. This
PR stores the normalized temporal memory, not the raw file.

## Time Semantics

`treasury_prices.ts` is the reference date normalized to
`YYYY-MM-DD 00:00:00+00`. `ingested_at` is the real insertion timestamp.

The schema rejects timestamps beyond the current UTC day plus one day. This
small margin avoids false rejects around timezone boundaries while still
blocking operationally future-dated market observations.

## Price And Rate Semantics

`price_bid` is the Tesouro buy price from the investor point of view: the
investor sells the title back to the Treasury.

`price_ask` is the Tesouro sell price from the investor point of view: the
investor buys the title from the Treasury.

Sanity constraints:

- `price_ask >= price_bid` when both are present.
- `rate_bid >= rate_ask` when both are present.
- `price_bid`, `price_ask` and `base_value` cannot be negative.
- Rates are not constrained to be non-negative because real-world yield
  regimes can include negative rates.

At least one of `price_bid`, `price_ask`, `rate_bid`, `rate_ask` or
`base_value` must be present.

## TimescaleDB Contract

`treasury_prices` is a TimescaleDB hypertable partitioned by `ts` with
`chunk_time_interval => INTERVAL '1 month'`.

TimescaleDB unique constraints on hypertables must include the partitioning
column. For that reason:

- Logical row identity is `PRIMARY KEY (bond_id, ts)`.
- Identical reingestion idempotency is expressed as
  `UNIQUE (lineage_hash, ts)`.

## Lineage Hash Contract

Future ingestion/repository code must compute the stable SHA-256 lineage hash
from the canonical JSON serialization of:

- `bond_type`
- `maturity_date`
- `ts`
- `price_bid`
- `price_ask`
- `rate_bid`
- `rate_ask`
- `base_value`
- `source_id`
- `schema_version`

The hash is mandatory for every `treasury_prices` row. Identical reingestion
must use `ON CONFLICT (lineage_hash, ts) DO NOTHING` and create no new row.

## Price Corrections

`treasury_prices` deliberately has no `revision` column in FL-PR06. A
corrected observation for an existing `(bond_id, ts)` cannot be inserted as a
second row; the primary key rejects it. Future treasury repository code must
treat corrections as an explicit policy decision: either perform an audited
`UPDATE` with a new `lineage_hash`, or introduce a revisioned table shape in a
future migration. FL-PR06 therefore preserves one canonical daily observation
per title/date and defers correction history to a later repository PR.

## Future Repository And Audit Contract

The future treasury repository must write `treasury_bonds`,
`treasury_prices`, and exactly one `audit_agent_writes` row for each logical
batch in the same database transaction. This PR validates that
`audit_agent_writes` exists but intentionally does not write to it.

## CSV Sample Contract

The PR test suite keeps a small in-file CSV sample with headers compatible
with the Tesouro Transparente CSV family:

- `Tipo Titulo`
- `Data Vencimento`
- `Data Base`
- `Taxa Compra Manha`
- `Taxa Venda Manha`
- `PU Compra Manha`
- `PU Venda Manha`
- `PU Base Manha`

The sample parser is test-local only. Runtime CSV ingestion belongs to a
future PR.
