# FINLIB-0 — Financial Libraries on PostgreSQL/TimescaleDB

> **Sprint master spec (SDD).** Item 1 of the pre-agent infrastructure phase:
> "PostgreSQL/TimescaleDB readiness + migrations + schemas".
> Authored by Claude (Fable) on 2026-06-10 after live repository inspection.
> Executors: Claude Code / Codex (implement) · Claude Cowork (adversarial review)
> · Francisco (final approval gate).
> Each PR below gets its own SDD file under `docs/specs/finlib-0/` before
> implementation starts.

---

## 0. Reality Audit — what ALREADY EXISTS (do not recreate)

Verified against the live repo on 2026-06-10:

| Capability | Status | Evidence |
|---|---|---|
| PostgreSQL 18.4 + TimescaleDB 2.23.0 + pgvector 0.8.2 Docker image | DONE | `infra/postgres/Dockerfile`, compose files |
| Extensions bootstrap (pgcrypto, timescaledb, vector, pg_stat_statements) + FINLIB read-only role | DONE | `infra/postgres/initdb/` |
| Migration runner: sha256 checksums, idempotency, transactional rollback, isolated `quimera_test_` DBs | DONE | `backend/memory/postgres/migrations.py` + tests |
| Migrations 000–017 applied: schema_migrations, memory extensions, sessions, turns, agent_states, entity_mentions, market_instruments, market_calendars, market_bars (hypertable), market_features (hypertable), model_runs, kronos_forecasts, qlib_projection_manifests, vector ext | DONE | `backend/memory/postgres/migrations/` |
| Memory repository (asyncpg, no ORM) + finance repository roundtrip tests | DONE | `backend/memory/postgres/repository.py` |
| Backup/restore + timescaledb pre/post restore protocol + pg_stat diagnostics | DONE | `infra/postgres/backup.sh`, `restore_verify.sh` |
| OTel base layer with safe attributes (no query/prompt/payload leak) | DONE | `backend/observability/` |
| Working-memory pgvector checkpoints | DONE | RAG-01B PR-10 |
| Qdrant 1.18.x Hybrid RAG, LiteLLM host gateway, Ollama | DONE | RAG-01A/01B, GW/G2 sprints |

**Gaps this sprint closes:**

1. No dedicated `check_postgres_readiness.py` (only `quimera_status.py` service-level check).
2. No ops layer: data sources registry, ingestion runs, watermarks, data-quality checks, outbox events.
3. No audit table for agent writes.
4. No macro/inflation/FX library (IPCA, IGP-M, Selic, CDI, USD/BRL PTAX).
5. No Tesouro Direto mark-to-market library.
6. No CVM fund registry / informe diário library.
7. No bank fixed-income (CDB/LCA/LCI/CRI/CRA) or debênture reference library.
8. No company fundamentals library (for PETR4/VALE3-style fundamental data).
9. No continuous aggregates / retention policies on hypertables.
10. `pg_trgm` / `btree_gin` extensions not yet enabled (needed for alias fuzzy matching and composite indexes).

**Explicitly NOT in scope (consistent with prior sprints / ADRs):** data agents themselves (next sprint), FastAPI, Redis, Neo4j/Graphiti, remote providers, COE instruments, Qdrant changes, decision/rebalance logic.

---

## 1. Standing decisions (record as ADRs in FL-PR00)

**ADR-A — Table namespace convention.** Existing applied migrations live in
schema `public` with domain prefixes (`market_*`, `kronos_*`, `qlib_*`).
Checksum immutability forbids rewriting them. Decision: **continue the prefix
convention in `public`** (`macro_*`, `treasury_*`, `fund_*`, `fi_*`,
`fundamentals_*`, `ops_*`, `audit_*`). Dedicated PostgreSQL schemas are
deferred to a future major version; a rename now buys cosmetics at the price of
breaking checksum history and the finance repository.

**ADR-B — Two SQL namespaces, one source of truth.**
`backend/memory/postgres/migrations/*.sql` (runner-managed, checksummed) is the
only schema source of truth. `infra/postgres/sql/*.sql` is operational SQL
(diagnostics, contracts) and may reuse numbers (e.g. `020_` exists in both) —
document this to prevent confusion; new schema objects go ONLY through the
runner.

**ADR-C — Library scope and source policy.** Asset classes covered: ações,
FIIs, ETFs, BDRs (already representable via `market_instruments.asset_class` +
`market_bars`), Tesouro Direto, fundos de investimento (CVM), CDB/LCA/LCI,
CRI/CRA, debêntures, séries macro (inflação, juros) e câmbio USD/BRL. COE is
permanently out of scope. Primary sources are official/semi-official: BCB
SGS, CVM Dados Abertos, Tesouro Transparente, B3 COTAHIST, ANBIMA (where
publicly accessible). Every source row carries `source_id`, every ingested
batch carries `run_id` + `lineage_hash` (pattern already used in
`market_bars`).

**ADR-D — Derived indicators are features, not tables.** OBV (On-Balance
Volume — "BOV"), moving averages, volatility, drawdown etc. are computed
deterministically in Python and stored in the existing `market_features`
hypertable (`feature_name='obv'`, versioned). No new table per indicator,
ever.

**ADR-E — FX representation.** USD/BRL PTAX (compra/venda) is stored once as
macro observations. BRL/USD is a derived view (`1/x`), never stored, to avoid
dual-write drift.

---

## 2. PR ladder (small, atomic, ≤400 production lines each)

Standard merge gate for EVERY PR (inherits CLAUDE.md):
`uv run pytest` (unit + integration where applicable) · `uv run mypy --strict .`
· `uv run pyright` · `uvx sqlfluff lint backend/memory/postgres/migrations --dialect postgres`
· `git diff --check` · no `DROP TABLE` · idempotency test green · isolated
`quimera_test_` DB for live tests · loguru only · no hardcoded endpoints ·
asyncpg only (no ORM) · OTel-safe logging (no payload/DSN leak).

### FL-PR00 — `docs/finlib0-adrs-and-specs`
- **Scope:** commit this master spec; ADR-A..E as `docs/adr/ADR-0xx-*.md`
  (Accepted); per-PR SDD stubs; `docs/data/DATA_DICTIONARY.md` skeleton.
- **Tests:** existing docs contract tests only. Docs-only PR.
- **Acceptance:** Cowork confirms ADRs do not conflict with ADR-001..022.

### FL-PR01 — `feat/finlib-postgres-readiness`
- **Migration `018_enable_library_extensions.sql`:** `CREATE EXTENSION IF NOT
  EXISTS pg_trgm;` `CREATE EXTENSION IF NOT EXISTS btree_gin;` (ltree
  deferred — no taxonomy consumer yet).
- **Script `scripts/check_postgres_readiness.py`:** JSON output validating
  postgres/timescaledb/vector/pgcrypto/pg_trgm/btree_gin/pg_stat_statements,
  database name, write test in a temp table, migration head version, and
  readonly role presence. Exit code 0/1. `--json` default-safe (no DSN echo).
- **Wire into `scripts/quimera_status.py`** as a `migrations`/`extensions` field.
- **Infra bootstrap:** `infra/postgres/initdb/002_readonly_role.sql` creates
  `quimera_readonly NOLOGIN` for fresh local volumes; old volumes must apply
  the same file once.
- **Tests:** `tests/unit/test_postgres_readiness_script.py` (offline contract)
  + `tests/integration/test_postgres_readiness_live.py` (isolated DB).
- **Acceptance:** readiness JSON green on live local stack; agents-gate rule
  documented: *no data agent starts unless this script exits 0*.

### FL-PR02 — `feat/finlib-ops-core`
- **Migration `019_create_ops_sources_runs.sql`:**
  - `ops_data_sources(source_id text pk, kind, base_url, license_note,
    methodology_limitations text, enabled bool, metadata jsonb, created_at)` —
    B3 "no inflation/proventos adjustment" limitation is recorded HERE as data,
    not tribal knowledge.
  - `ops_ingestion_runs(run_id uuid pk default uuidv7(), source_id fk,
    agent_id text, mode text check (mode in ('dry_run','execute')), status,
    started_at, finished_at, records_seen int, records_inserted int,
    records_updated int, records_rejected int, source_snapshot_hash text,
    error_summary text, trace_id uuid, metadata jsonb)`.
- **Migration `020_create_ops_watermarks_quality_outbox.sql`:**
  - `ops_ingestion_watermarks(source_id, dataset text, watermark_ts
    timestamptz, watermark_key text, updated_at, pk(source_id, dataset))`.
  - `ops_data_quality_checks(check_id uuid pk, run_id fk, check_name,
    target_table, severity check in ('info','warning','error','critical'),
    passed bool, observed jsonb, expected jsonb, created_at)`.
  - `ops_outbox_events(event_id uuid pk default uuidv7(), event_type,
    aggregate_type, aggregate_id, payload jsonb, status default 'pending',
    attempts int default 0, next_attempt_at, created_at, locked_by,
    locked_at)` + partial index on `(status, next_attempt_at)` for
    `FOR UPDATE SKIP LOCKED` polling.
- **Tests:** schema contract tests + idempotency + a live SKIP LOCKED
  double-consumer test proving no double-dispatch.
- **Acceptance:** outbox poll query under 5ms on empty table; zero double
  dispatch in concurrent test.

### FL-PR03 — `feat/finlib-audit-agent-writes`
- **Migration `021_create_audit_agent_writes.sql`:**
  `audit_agent_writes(audit_id uuid pk default uuidv7(), trace_id, run_id,
  agent_id, target_table, operation check in ('insert','update','upsert'),
  row_count int, batch_hash text, created_at)` — **append-only**: REVOKE
  UPDATE/DELETE from the application role; enforced also by a guard trigger.
- **Tests:** contract + live test proving UPDATE/DELETE raise; repository can
  only append.
- **Acceptance:** Cowork verifies append-only at both role and trigger level.

### FL-PR04 — `feat/finlib-macro-library`
- **Migration `022_create_macro_catalog_observations.sql`:**
  - `macro_series_catalog(series_code text pk, source_id fk, provider_code
    text, name, unit, periodicity check in
    ('daily','monthly','quarterly','annual'), seasonally_adjusted bool,
    methodology_note, metadata jsonb)`.
  - `macro_observations(series_code fk, ref_ts timestamptz not null,
    value numeric not null, source_id, run_id, ingested_at,
    revision int default 0, lineage_hash,
    pk(series_code, ref_ts, revision))` → hypertable on `ref_ts`.
  - View `vw_fx_brlusd` = `1/value` of the USD/BRL PTAX series (ADR-E).
- **Seed file `config/macro_series_seed.yaml`** with initial BCB SGS codes —
  IPCA (433), IGP-M (189), Selic meta (432), Selic diária, CDI, PTAX USD/BRL
  compra/venda. *Each code MUST be verified against the live SGS catalog
  during implementation; codes in this spec are planning references, not
  ground truth.*
- **Tests:** unit (seed parsing, revision semantics: re-released IPCA creates
  revision+1, never overwrites) + integration (hypertable, idempotent upsert
  by natural key `series_code+ref_ts+revision`).
- **Acceptance:** double ingest of identical batch → 0 new rows; revised value
  → new revision row, old row intact.

### FL-PR05 — `feat/finlib-treasury-library`
- **Migration `023_create_treasury_bonds_prices.sql`:**
  - `treasury_bonds(bond_id uuid pk, bond_type text /* LFT, LTN, NTN-B,
    NTN-B Principal, NTN-F */, maturity_date date, isin text, index_kind
    check in ('selic','ipca','prefixado'), metadata jsonb,
    unique(bond_type, maturity_date))`.
  - `treasury_prices(ts timestamptz not null, bond_id fk, buy_rate numeric,
    sell_rate numeric, buy_price numeric, sell_price numeric /* marcação a
    mercado diária */, base_value numeric, source_id, run_id, ingested_at,
    lineage_hash, pk(bond_id, ts))` → hypertable.
- **Tests:** contract + idempotency + DQ rules (no negative prices, sell/buy
  spread sanity, no future `ts`).
- **Acceptance:** Tesouro Transparente CSV sample round-trips with stable
  `lineage_hash`.

### FL-PR06 — `feat/finlib-fund-library`
- **Migration `024_create_fund_registry_daily_info.sql`:**
  - `fund_registry(fund_cnpj text pk, name, cvm_class, anbima_class,
    target_audience, condominio, status, registered_at, metadata jsonb)`.
  - `fund_daily_info(ts timestamptz, fund_cnpj fk, quota_value numeric,
    net_worth numeric, total_portfolio_value numeric, inflow numeric,
    outflow numeric, shareholders int, source_id, run_id, ingested_at,
    lineage_hash, pk(fund_cnpj, ts))` → hypertable. Mirrors CVM Informe
    Diário fields (CSV-in-ZIP since 2022).
- **Tests:** contract + idempotency + DQ (`quota_value`/`net_worth` not null,
  no negative shareholders).
- **Acceptance:** sample CVM informe parses to rows with natural key
  `fund_cnpj+competence_ts` and re-ingest is a no-op.

### FL-PR07 — `feat/finlib-fixed-income-debentures` *(split into 07a/07b if >400 lines)*
- **Migration `025_create_fi_instruments.sql`:**
  `fi_instruments(fi_id uuid pk, kind check in
  ('cdb','lca','lci','cri','cra','debenture'), issuer_name, issuer_cnpj,
  indexer check in ('cdi','ipca','prefixado','selic','igpm'),
  rate_spec jsonb /* e.g. {"pct_cdi":110} or {"ipca_plus":6.1} */,
  issue_date, maturity_date, liquidity text, fgc_covered bool,
  isin text, ticker text, metadata jsonb)`. CDB/LCA/LCI rows usually
  originate from the user's own positions/extracts (Level 0 — local only).
- **Migration `026_create_debenture_market_data.sql`:**
  `debenture_market_data(ts timestamptz, fi_id fk, indicative_rate numeric,
  pu numeric, duration numeric, source_id, run_id, ingested_at,
  lineage_hash, pk(fi_id, ts))` → hypertable. ANBIMA public-data access
  limitations must be recorded in `ops_data_sources.methodology_limitations`.
- **Tests:** contract + idempotency + rate_spec JSON schema validation in
  Pydantic.
- **Acceptance:** all six `kind`s representable; Level 0 boundary documented.

### FL-PR08 — `feat/finlib-fundamentals`
- **Migration `027_create_company_fundamentals.sql`:**
  - `company_registry(company_id uuid pk, cvm_code text unique, cnpj text
    unique, name, sector, metadata jsonb)` + `company_listings(company_id fk,
    instrument_id fk -> market_instruments, pk(company_id, instrument_id))`
    linking PETR4/PETR3 etc. to one issuer.
  - `fundamentals_statements(company_id, period_end date, period_kind check
    in ('annual','quarterly','ttm'), statement check in
    ('bp','dre','dfc'), line_code text, value numeric, currency,
    consolidated bool, version int default 0, source_id, run_id,
    lineage_hash, pk(company_id, period_end, period_kind, statement,
    line_code, version))`.
  - `fundamentals_indicators(ts timestamptz, company_id, indicator_name,
    indicator_value numeric, indicator_version text, source_id, run_id,
    lineage_hash, pk(company_id, indicator_name, indicator_version, ts))`
    → hypertable (P/L, ROE, dívida líquida/EBITDA etc. — derived in Python,
    same philosophy as ADR-D).
- **Tests:** contract + restatement semantics (version+1) + idempotency.
- **Acceptance:** CVM DFP/ITR sample for one company round-trips; restated
  statement preserves history.

### FL-PR09 — `feat/finlib-repositories` *(split 09a ops/macro, 09b treasury/fund/fi/fundamentals if needed)*
- `backend/finlib/__init__.py` + repositories over asyncpg pool (reuse
  existing pool/client from `backend/memory/postgres`):
  `OpsRepository` (register_source, start_run/finish_run, get/set_watermark,
  record_quality_check, outbox enqueue/poll with SKIP LOCKED),
  `MacroRepository`, `TreasuryRepository`, `FundRepository`,
  `FixedIncomeRepository`, `FundamentalsRepository` — each with batch upsert
  by natural key, `lineage_hash` requirement, and automatic
  `audit_agent_writes` append inside the same transaction.
- **Import Linter contract:** Agent0/RAG modules must NOT import
  `backend.finlib` directly (extends the existing `.importlinter` boundary).
- **Tests:** unit with fake pool + live roundtrips in isolated DBs; concurrency
  test on watermarks; transaction atomicity test (write + audit commit or
  rollback together).
- **Acceptance:** zero raw SQL outside repositories (grep gate in test);
  every write produces exactly one `audit_agent_writes` row.

### FL-PR10 — `feat/finlib-aggregates-retention-closeout`
- **Migration `028_continuous_aggregates_retention.sql`:** continuous
  aggregates (e.g. `market_bars_1d` from intraday when present;
  `macro_observations` latest-revision view; monthly fund quota return) +
  conservative retention/compression policies (compression only, NO data
  drops in V1).
- **Data dictionary final:** `docs/data/DATA_DICTIONARY.md` — every table,
  column, natural key, source, limitation.
- **Readiness integration:** `check_postgres_readiness.py` validates head
  migration `028` and presence of aggregates.
- **Final gate script:** `scripts/check_finlib_readiness.py` → the formal
  Go/No-Go that the NEXT sprint (data agents) consumes.
- **Acceptance (sprint close):** fresh machine: `./start_quimera.sh --start`
  → migrate → readiness 0 exit → `pytest` full green → tag `finlib-0`.

---

## 3. SDD workflow (how each PR is executed)

1. **Spec first:** copy `docs/specs/finlib-0/_TEMPLATE.md` →
   `pr-XX-<slug>.md`; fill Objective / Schema diff / Natural keys / DQ rules /
   Tests / Out-of-scope / Rollback. Spec is reviewed by Cowork BEFORE code.
2. **Issue + branch:** one GitHub issue per PR, branch from updated `main`
   (`git pull --ff-only`).
3. **Red:** write contract tests against the spec (they fail).
4. **Green:** write the migration + minimal code.
5. **Mutate/Refactor:** targeted `mutmut` via `scripts/vibe_deep_run.sh` on
   new repository code (TDD+M methodology already in
   `docs/testing/tdd_m_professional_methodology.md`).
6. **Gate:** full merge-criteria block; Cowork adversarial review classifies
   findings Funcional / Contrato Operacional / Cosmético.
7. **Merge on GitHub only** (ADR-011), then update `docs/04_MEM/current_state.md`
   and `/compact`.

**On automation ("GitHub Spec SDD"):** the repo's existing
`docs/specs/<sprint>/pr-XX-*.md` convention IS spec-driven development and is
already wired into the Codex/Cowork loop — keep it. Optionally adopt
GitHub **spec-kit** (`/specify → /plan → /tasks`) inside Claude Code to
generate the per-PR SDD stubs from this master spec; treat its output as a
draft that must still pass Cowork review. Do not introduce a new framework
dependency into `pyproject.toml` for this.

---

## 4. Source registry (initial; verify live during FL-PR04+)

| source_id | Provider | Datasets | Notes/limitations |
|---|---|---|---|
| `bcb_sgs` | Banco Central BCData/SGS | IPCA, IGP-M, Selic, CDI, PTAX USD/BRL | JSON API by series code |
| `cvm_fundos_inf_diario` | CVM Dados Abertos | fund_daily_info | CSV inside ZIP since 2022 |
| `tesouro_transparente` | Tesouro Nacional | treasury_bonds, treasury_prices | daily CSV, MtM prices/rates |
| `b3_cotahist` | B3 série histórica | market_bars (EOD) | NO inflation/proventos adjustment — record in methodology_limitations; `factor` column reserved for future adjusted series |
| `brapi_dev` | brapi.dev (semi-official) | market_bars convenience, fundamentals snapshots | rate limits; secondary source |
| `anbima_debentures` | ANBIMA | debenture_market_data | public access restrictions — verify before committing scope |

---

## 5. Go/No-Go checklist consumed by the next sprint (data agents)

- [ ] `check_postgres_readiness.py` exit 0 (extensions, head migration, write test)
- [ ] Migrations 018–028 idempotent; no DROP TABLE; checksums recorded
- [ ] `ops_*` and `audit_agent_writes` exist and are exercised by tests
- [ ] All library tables have natural keys + `source_id` + `run_id` + `lineage_hash`
- [ ] Repositories are the only write path (grep/import-linter gates green)
- [ ] Data dictionary published
- [ ] Qdrant remains primary vector store; pgvector untouched as auxiliary
- [ ] No agent code merged in this sprint
