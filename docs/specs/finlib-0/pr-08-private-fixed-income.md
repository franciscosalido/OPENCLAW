# FINLIB-0 FL-PR08 — Private Fixed Income

Branch: `feat/finlib-private-fixed-income`
Status: Implementation PR

## Scope

FL-PR08 creates a local Brazilian private fixed-income REFERENCE CATALOG for:

- CDB
- LCA
- LCI
- CRI
- CRA
- debenture

The PR adds exactly one durable table:

- `fi_instruments`

It does not add repositories, agents, MCP tools, runtime ingestion, live ANBIMA,
B3, bank or broker clients, Qdrant objects, pgvector objects, valuation,
duration, credit-risk scoring, suitability, recommendation logic or FL-PR09+
tables.

## Source Policy

The migration seeds two canonical source rows:

- `local_fixed_income_input`: local user-supplied input for CDB/LCA/LCI-style
  instruments. This row exists because these instruments frequently originate
  from extracts, statements or local positions.
- `anbima_debentures`: declarative future source for debenture, CRI and CRA
  public or semipublic metadata. ANBIMA exposes pricing and index packages for
  corporate bonds and CRI/CRA in future scopes, but this PR does not download
  or query those services.

Both rows are source metadata only. This PR does not fetch private,
brokerage, banking, ANBIMA, B3 or CVM data.

## Level 0 Boundary

`fi_instruments` is a REFERENCE CATALOG. It is not a user-position table.

The following fields are permanently outside this table:

- quantity
- face_value_held
- acquisition_price
- yield_at_purchase
- custodian
- account_number
- cpf
- holder_id
- portfolio_id
- broker_id

Those fields are Level 0 personal or portfolio data. They may only appear in a
future local-only table such as `fi_positions`, outside FINLIB-0 and behind an
explicit human-approved privacy design. Level 0 data must not be sent to remote providers. Level 0 fields must not be sent to remote providers.

## Instrument Contract

`fi_instruments.kind` is limited to:

- `cdb`
- `lca`
- `lci`
- `cri`
- `cra`
- `debenture`

`issuer_cnpj` is canonical: 14 digits without punctuation.

`isin` is optional. When present it must follow an ISO-like shape:
two uppercase country letters, nine uppercase alphanumeric characters and one
check digit.

`indexer` is limited to:

- `cdi`
- `ipca`
- `prefixado`
- `selic`
- `igpm`

CRI, CRA and debenture must have `fgc_covered = false` and a non-null
`maturity_date`. `maturity_date`, when present together with `issue_date`, must
not be earlier than `issue_date`.

`fgc_covered` defaults to false as a fail-safe. Future importers should still
write it explicitly because coverage is a financial-product semantic, not a
database guess.

## Rate Spec Contract

`rate_spec` is stored as JSONB and the database enforces only the minimum
shape:

- object JSON
- `indexer`
- `rate_model`
- `day_count`
- `payment_frequency`

Semantic validation is performed before writes by `backend.finlib.rate_spec`.
The Pydantic model is strict, forbids extra fields and supports:

- `prefixado`: `indexer = prefixado`, `rate` required.
- `percent_of_indexer`: `indexer in (cdi, selic)`, `rate` required.
- `indexer_plus_spread`: `indexer in (cdi, selic)`, `spread` required.
- `inflation_plus_coupon`: `indexer in (ipca, igpm)`, `coupon` required.

The helper rejects divergence between the table `indexer` and the JSON
`rate_spec.indexer`.

## Lineage Hash Contract

`lineage_hash` is mandatory and unique for catalog idempotency.

Future ingestion/repository code must compute the stable SHA-256 lineage hash
from the canonical JSON serialization of:

- `isin`
- `kind`
- `issuer_cnpj`
- `indexer`
- `rate_spec_canonical`
- `maturity_date`
- `issue_date`
- `source_id`
- `schema_version`

Fields from user positions are intentionally absent from the hash because they
do not exist in this catalog.

## Quality Flags

The Python helper `compute_quality_flags()` may emit warnings for unusual but
possible combinations, such as LCI or LCA with `prefixado`. Those warnings are
advisory metadata, not hard database constraints.

## Future Work

Future PRs may add repositories, local-only position tables, market data for
debentures/CRI/CRA, valuation and audit-bound ingestion. They must not mutate
this PR's migration after it has been applied; new behavior must arrive through
new migrations.
