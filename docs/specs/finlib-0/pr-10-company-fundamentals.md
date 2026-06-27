# FINLIB-0 FL-PR10 — Company Fundamentals

Branch: `feat/finlib-fundamentals`
Status: Initial implementation SDD

## Objective

FL-PR10 adds the company fundamentals library for QUIMERA. It models public
company identity, exchange listings, versioned DFP/ITR statements and
statement-only indicators derived by deterministic Python.

## Context And Preconditions

- Current migration head before this PR is `027_guard_debenture_kind_drift`.
- The next migration is `028_create_company_fundamentals`.
- PostgreSQL target is 18.x.
- TimescaleDB is required for the indicators hypertable.
- `uuidv7()` is available.
- `ops_data_sources`, `ops_ingestion_runs` and `audit_agent_writes` already
  exist.
- `fi_instruments` and `debenture_market_data` already exist.
- The official sandbox is Python 3.12 with PostgreSQL client 18.x.

## Research Notes

- CVM Dados Abertos publishes DFP and ITR datasets for public companies.
- DFP/ITR include statement families such as BPA, BPP, DFC, DMPL, DRA, DRE and
  DVA.
- CVM open datasets can be updated and may contain reapresentations.
- CVM company registration datasets include cadastral fields such as CNPJ,
  registration date and registration status.
- B3 ticker and ISIN identify listings/instruments; they are not the canonical
  company identity.
- TimescaleDB requires primary keys and unique constraints on hypertables to
  include every partitioning column.

No test in this PR downloads live CVM or B3 data.

## Scope

This PR creates exactly four tables:

- `company_registry`
- `company_listings`
- `fundamentals_statements`
- `fundamentals_indicators`

It also creates a pure Python module:

- `backend/finlib/fundamentals.py`

## Non-Scope

This PR does not create repositories, agents, ingesters, CVM clients, B3
clients, downloaders, HTTP fetches, scraping, recommendations, rebalancing,
portfolio tables, Qdrant mutations or pgvector policy changes.

## Architecture Decisions

### Migration 028

FL-PR09 RC already created `027_guard_debenture_kind_drift.sql`. Reusing `027`
would create migration ambiguity and checksum drift, so FL-PR10 uses
`028_create_company_fundamentals.sql`.

### Registry Versus Listings

`company_registry` is the canonical company entity. It is not a ticker table.
`company_listings` stores exchange, ticker, share class and ISIN. PETR3 and
PETR4 are two listings that may point to the same `company_id`.

### Versioned Statements

`fundamentals_statements` stores normalized public DFP/ITR payloads. A
restatement creates `version + 1`, requires `prior_version_id` and requires
`restatement_reason`. Previous versions remain queryable.

### Python-Only Indicators

`fundamentals_indicators` stores indicators derived in Python. SQL stores the
result; SQL does not calculate financial ratios.

Persisted MVP indicators are statement-only:

- `lpa`
- `vpa`
- `ebitda`
- `net_revenue`
- `net_income`
- `total_assets`
- `total_equity`
- `net_debt`
- `roe`
- `roa`

Market-dependent indicators such as `pe_ratio`, `pb_ratio`, `ev_ebitda`,
`dividend_yield`, `market_cap` and `market_price` are prohibited in this PR.

### Indicators Hypertable

`fundamentals_indicators` is a TimescaleDB hypertable partitioned by `ts` with
three-month chunks. Its primary key and unique constraint include `ts`.

## Source Handling

Migration 028 seeds these sources idempotently:

- `cvm_cia_aberta_cadastro`
- `cvm_dfp`
- `cvm_itr`
- `b3_listings`

Source metadata is merged rather than blindly replacing unrelated metadata.
The `ON CONFLICT` path must not overwrite source identity or operational
fields such as `kind`, `base_url` or `enabled`; it may refresh documentation
fields and merge metadata only.

## Level Boundary

All four tables are Level 1/Level 2 public or semipublic company/fundamentals
data. This PR must never include Level 0 position fields such as quantity,
position size, acquisition price, cost basis, custodian, account number,
broker, CPF, holder ID, portfolio ID, user ID, personal notes, recommendation
or target weight.

## Future Repository Transaction Contract

Future repository code must use one transaction:

```sql
BEGIN;
  -- resolve company/listing;
  -- insert/update registry and listing idempotently;
  -- insert fundamentals_statements versioned;
  -- compute statement-only indicators in Python;
  -- insert fundamentals_indicators;
  -- append exactly one audit_agent_writes row for the logical batch;
COMMIT;
```

Audit failure rolls back the batch. Domain-write failure must not create an
orphan audit row. Statements must not be corrected with destructive UPDATE.
Concurrent `version + 1` calculation will require an advisory lock keyed by the
statement natural identity.

## Rollback

This PR is additive. Test rollback is dropping the isolated `quimera_test_*`
database. Persistent rollback must be a future migration, not manual edits to
applied migrations.

## Test Plan

Static unit tests:

- migration 028 exists and creates exactly four tables
- migration 027 remains separate
- no forbidden Level 0, credentials, downloader or agent scope
- registry/listing contracts preserve company-vs-ticker separation
- statements are versioned and restatement-aware
- indicators hypertable is Timescale-safe
- SDD documents Level 0 boundary and Python-only indicators

Python unit tests:

- strict Pydantic model rejects extras
- statement-only indicators are derived deterministically
- missing fields produce `None`
- market-dependent indicators are rejected
- lineage/computation hashes are stable and Level 0-safe

Live integration tests:

- isolated `quimera_test_*` database
- migrations 000-028 apply idempotently
- PETR3/PETR4 point to one `company_id`
- DFP/ITR restatement preserves history
- indicators from v1 and v2 coexist
- `fundamentals_indicators` is a real hypertable
- no write to `audit_agent_writes`

## Security Checklist

- No `.env`, secrets, tokens, DSNs or credentials.
- No real private portfolio data.
- No downloader or remote client.
- No repository or agent.
- No market-dependent stored indicators.
- No Level 0 fields in schema or Python model; docs may name them only to
  define the forbidden boundary.
