# current_state.md — OPENCLAW Operational Memory

> Volatile project state for Codex, Claude Code, ChatGPT Thinking, and human
> review. Read after `docs/04_MEM/AGENT_CONTEXT.md`. Update at the end of
> meaningful sessions.

**Last updated:** 2026-06-28
**Updated by:** Codex — FL-PR13 RC-01 Ready For Local Merge

---

## READY FOR LOCAL MERGE — FINLIB-0 FL-PR13 Memory Boundary

**Adversarial review verdict:** `APPROVE_WITH_NITS`
**Report:** `docs/04_MEM/FL_PR13_ADVERSARIAL_REVIEW.md`
**Sandbox:** container `f205ddd50d99` (openclaw-sandbox:latest)
**Tests in sandbox:** 23/23 boundary unit + 16/16 architecture + 89/89 FINLIB unit = 128 targeted PASSED
**import-linter:** 6/6 contracts KEPT
**mypy --strict (scope):** 0 errors
**ruff:** all clean

**NITs (non-blocking):**
- FND-01 [MAJOR]: FL-PR12 not merged into main — BLK-02 fix present and
  correct (Caminho B, commit `09a00c8`). Local merge should merge FL-PR12 and
  FL-PR13 together because this branch is intentionally stacked.
- FND-02 [NIT]: policy.py env-read gap was resolved by RC-01 commit `e0b473c`
  (`test: block memory policy environment reads`).
- FND-03 [NIT]: Pre-existing gateway timing test failure (unrelated).
- FND-04 [NIT]: Pre-existing SQLFluff violations in migrations 012-016.
  FL-PR13 adds zero SQL files.
- FND-05 [NIT]: Synthetic CPF "00000000000" in test fixtures (harmless).

**Merge condition:** merge FL-PR12 and FL-PR13 simultaneously via
`feat/finlib-memory-boundary`, preserving the stacked order:
FL-PR12 SDD -> FL-PR12 implementation -> FL-PR12 RC -> FL-PR13 SDD ->
FL-PR13 implementation -> FL-PR13 RC-01.

Current branch: `feat/finlib-memory-boundary`

GitHub:

- Issue created: `https://github.com/franciscosalido/OPENCLAW/issues/122`.
- Draft PR remote creation deferred because the local FINLIB stack is ahead of
  `origin/main` and FL-PR12 has not been published/merged remotely from this
  workspace.

Scope:

- Added SDD `docs/specs/finlib-0/pr-13-memory-boundary.md`.
- Added ADR `docs/ADR/ADR-006-qdrant-postgres-pgvector-boundary.md`.
- Added active policy doc `docs/specs/memory_policy.md`.
- Added LongRAG planning reference
  `docs/references/long-rag-postgres-memory-reference.md`.
- Added pure policy module `backend/memory/policy.py`.
- Added unit and architecture tests that make the boundary executable:
  Qdrant remains primary semantic/hybrid retriever, PostgreSQL/TimescaleDB
  remains structured long-term memory, pgvector remains auxiliary only, and
  FINLIB repositories do not import Qdrant/RAG/LLM/HTTP clients.
- Extended `.importlinter` with FINLIB/RAG/memory-policy boundary contracts.

Scope intentionally unchanged:

- No LongRAG runtime, migrations, tables, retrievers, agents, Qdrant
  collection mutation, pgvector retriever, FINLIB repository mutation, LLM
  calls, HTTP clients, secrets, DSNs, portfolio data or runtime data mutation.

---

## IN PROGRESS — FINLIB-0 FL-PR12 Repositories Assets

Adversarial RC-01 verdict was `REQUEST_CHANGES`; Codex applied the advisory
lock fix locally.

Current branch: `feat/finlib-repositories-assets`

GitHub:

- Issue created: `https://github.com/franciscosalido/OPENCLAW/issues/121`.
- Draft PR remote creation deferred because local `main` is ahead of
  `origin/main` by 35 commits.

RC-01 fix:

- Replaced advisory-lock placeholder casts that coerced Python `datetime`,
  `date` or `UUID` values through PostgreSQL `text` OID.
- Adopted typed SQL casts instead of Python pre-stringification:
  - `fund_repository.py`: `$2::timestamptz::text`
  - `fixed_income_repository.py`: `$1::uuid::text`,
    `$2::timestamptz::text`
  - `fundamentals_repository.py`: `$1::uuid::text`, `$5::date::text`
  - `macro_repository.py`: `$2::timestamptz::text`
- Added unit assertions that lock SQLs use typed casts and do not regress to
  bare temporal `$N::text` casts.

Cowork sandbox before fix (container 8b973cab9fec):

- Unit: 20/20 + 67/67 FINLIB + 123 cross-sprint PASSED
- Architecture: 4/4 PASSED
- Integration FL-PR12: 0/1 FAILED (BLK-02 live)
- Integration cross-sprint: test_finlib_repositories_core_live 1/2 FAILED (BLK-02b)
- mypy strict 0 errors | pyright 0 | ruff clean | bandit clean | BLK-01 fixed ✅

Local RC-01 validation after fix:

- `uv run pytest tests/unit/test_finlib_fund_repository.py tests/unit/test_finlib_fixed_income_repository.py tests/unit/test_finlib_fundamentals_repository.py tests/unit/test_finlib_macro_repository.py -q`
  passed: 26 passed.
- `uv run pytest tests/integration/test_finlib_repositories_assets_live.py tests/integration/test_finlib_repositories_core_live.py -q`
  skipped safely without host DSN: 3 skipped.
- `uv run pytest tests/architecture -q` passed: 4 passed.
- `uv run mypy backend/finlib/repositories tests/unit/test_finlib_fund_repository.py tests/unit/test_finlib_fixed_income_repository.py tests/unit/test_finlib_fundamentals_repository.py tests/unit/test_finlib_macro_repository.py --strict`
  passed: no issues in 14 source files.
- `uv run pyright backend/finlib/repositories tests/unit/test_finlib_fund_repository.py tests/unit/test_finlib_fixed_income_repository.py tests/unit/test_finlib_fundamentals_repository.py tests/unit/test_finlib_macro_repository.py`
  passed with only the known cosmetic Pyright update notice.
- `uvx ruff check ...` passed.
- `uvx ruff format --check ...` passed.

Scope:

- Added SDD `docs/specs/finlib-0/pr-12-repositories-assets.md`.
- Added asset DTOs in `backend/finlib/repositories/models_assets.py`.
- Added `FundRepository` for `fund_registry` and `fund_daily_info`.
- Added `FixedIncomeRepository` for `fi_instruments` and `debenture_market_data`.
- Added `FundamentalsRepository` for `company_registry`, `company_listings`,
  `fundamentals_statements` and `fundamentals_indicators`.
- Reused FL-PR11 `BaseRepository`, audited transaction helper, `AuditContext`,
  `BatchWriteResult`, canonical JSON serialization and Level 0 recursive validation.
- Added architecture tests for FINLIB import boundaries and raw SQL placement.

Scope intentionally unchanged:

- No migrations, agents, ingesters, parsers, HTTP clients, ORM, SQLAlchemy,
  FastAPI, MCP, A2A runtime, Qdrant mutation, LLM call, pgvector policy,
  private portfolio data or secrets.

---

## IN PROGRESS — FINLIB-0 FL-PR11 Repositories Core

Current branch: `feat/finlib-repositories-core`

GitHub:

- Issue created: `https://github.com/franciscosalido/OPENCLAW/issues/120`.
- Draft PR remote creation deferred because local `main` is ahead of
  `origin/main` by 31 commits. Opening a Draft PR now would include unrelated
  prior local sprint commits.

Scope:

- Added SDD `docs/specs/finlib-0/pr-11-repositories-core.md`.
- Added asyncpg-only repository package under `backend/finlib/repositories/`.
- Added typed DTOs for audit context, ops, macro and treasury writes.
- Added shared audited transaction helper that writes domain data and exactly
  one `audit_agent_writes` row in one transaction.
- Added `OpsRepository` for sources, runs, watermarks, quality checks and
  outbox polling.
- Added `MacroRepository` for macro catalog and append-only observations with
  advisory-lock revision allocation.
- Added `TreasuryRepository` for treasury bond catalog and idempotent temporal
  prices.
- Added unit boundary tests and live integration test for repository flow,
  audit counts, rollback and outbox concurrency.

Schema reality:

- Migration head at PR start: `028_create_company_fundamentals.sql`.
- Watermark backing table already exists: `ops_ingestion_watermarks`.
- No new migration is planned for FL-PR11.
- `audit_agent_writes.batch_hash` is the audit hash column used by
  `AuditContext.batch_hash`.

Validation so far:

- `uv run pytest tests/unit/test_finlib_ops_repository.py tests/unit/test_finlib_macro_repository.py tests/unit/test_finlib_treasury_repository.py tests/unit/test_finlib_repository_boundaries.py -q`
  passed: 25 passed.
- `uv run pytest tests/integration/test_finlib_repositories_core_live.py -q`
  skipped safely without host DSN: 2 skipped.
- `uvx ruff check backend/finlib/repositories backend/finlib/__init__.py tests/unit/test_finlib_ops_repository.py tests/unit/test_finlib_macro_repository.py tests/unit/test_finlib_treasury_repository.py tests/unit/test_finlib_repository_boundaries.py tests/integration/test_finlib_repositories_core_live.py`
  passed.
- `uvx ruff format --check backend/finlib/repositories backend/finlib/__init__.py tests/unit/test_finlib_ops_repository.py tests/unit/test_finlib_macro_repository.py tests/unit/test_finlib_treasury_repository.py tests/unit/test_finlib_repository_boundaries.py tests/integration/test_finlib_repositories_core_live.py`
  passed.
- `uv run mypy backend/finlib/repositories --strict` passed.
- `uv run pyright backend/finlib/repositories` passed with only the known
  cosmetic Pyright update notice.

RC-01 adversarial review fix:

- Cowork found a live PostgreSQL BLOCKER: repository SQL used `$N::jsonb` while
  the repositories pass canonical JSON strings produced by
  `_json_dumps_canonical()`.
- The project pool configures asyncpg JSON/JSONB codecs, so `$N::jsonb` caused
  asyncpg to encode the already-serialized string again. PostgreSQL then saw a
  JSONB string instead of a JSONB object, tripping `jsonb_typeof(...) = 'object'`
  checks such as `ops_data_sources_metadata_check`.
- Fixed repository SQL to cast all pre-serialized repository payloads through
  `::text::jsonb`.
- Added a unit boundary test that rejects bare `::jsonb` casts inside
  `backend/finlib/repositories/` and requires the `::text::jsonb` contract.

RC-01 validation:

- `uv run pytest tests/unit/test_finlib_ops_repository.py tests/unit/test_finlib_macro_repository.py tests/unit/test_finlib_treasury_repository.py tests/unit/test_finlib_repository_boundaries.py -q`
  passed: 26 passed.
- `uv run pytest tests/integration/test_finlib_repositories_core_live.py -q`
  skipped safely without host DSN: 2 skipped.
- `uvx ruff check backend/finlib/repositories backend/finlib/__init__.py tests/unit/test_finlib_ops_repository.py tests/unit/test_finlib_macro_repository.py tests/unit/test_finlib_treasury_repository.py tests/unit/test_finlib_repository_boundaries.py tests/integration/test_finlib_repositories_core_live.py`
  passed.
- `uvx ruff format --check backend/finlib/repositories backend/finlib/__init__.py tests/unit/test_finlib_ops_repository.py tests/unit/test_finlib_macro_repository.py tests/unit/test_finlib_treasury_repository.py tests/unit/test_finlib_repository_boundaries.py tests/integration/test_finlib_repositories_core_live.py`
  passed.
- `uv run mypy backend/finlib/repositories --strict` passed.
- `uv run pyright backend/finlib/repositories` passed with only the known
  cosmetic Pyright update notice.

Scope intentionally unchanged:

- No agents, ingesters, parsers, HTTP clients, ORM, SQLAlchemy, FastAPI, MCP,
  A2A runtime, Qdrant mutation, pgvector policy, private portfolio data or
  secrets.

---

## IN PROGRESS — FINLIB-0 FL-PR10 Company Fundamentals

Current branch: `feat/finlib-fundamentals`

RC-01 adversarial review fixes:

- Fixed `test_fundamentals_statement_constraints` argument ordering so `$9`
  receives `run_id` and `$10` receives `lineage_hash`. Before this fix,
  `asyncpg` raised `DataError` during UUID binding and the live PostgreSQL
  CHECK constraints were not exercised.
- Narrowed migration 028 `ops_data_sources ON CONFLICT` behavior so existing
  `kind`, `base_url`, and `enabled` values are not silently overwritten.
- Added static coverage asserting migration 028 does not overwrite those
  source identity/operational fields while still merging metadata.

RC-02 adversarial review follow-up:

- Cowork RC-01 verdict was `APPROVE` after sandbox confirmed 7/7 live
  `CheckViolationError` cases for `test_fundamentals_statement_constraints`.
- Resolved the remaining source-conflict nit explicitly in the SDD: migration
  028 may refresh documentation fields and merge metadata, but must not
  overwrite source identity or operational fields such as `kind`, `base_url`
  or `enabled`.
- The remaining timing flap in `test_gateway1_proof_of_life.py` is
  pre-existing and outside FL-PR10 scope.

Scope:

- Adds migration `028_create_company_fundamentals.sql`.
- Adds four tables: `company_registry`, `company_listings`,
  `fundamentals_statements`, and `fundamentals_indicators`.
- Seeds public source contracts for CVM company registry, CVM DFP, CVM ITR,
  and B3 listings through `ops_data_sources`.
- Keeps company identity separate from listings, so PETR3/PETR4 may point to
  one canonical `company_id`.
- Stores DFP/ITR restatements as immutable `version + 1` statement rows.
- Stores only statement-derived indicators; market-dependent valuation
  indicators remain out of scope.
- Makes `fundamentals_indicators` a TimescaleDB hypertable partitioned by
  `ts`, with all primary/unique constraints including the partition column.
- Adds `backend/finlib/fundamentals.py` with strict Pydantic indicator model
  and deterministic statement-only derivation/hash helpers.

Validation:

- `uv run pytest tests/unit/test_company_fundamentals_schema_contract.py tests/unit/test_fundamentals_python_indicators.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 28 passed.
- `uv run pytest tests/integration/test_fundamentals_restatement_live.py::test_fundamentals_statement_constraints -q`
  skipped safely without host DSN: 1 skipped. Cowork should rerun this inside
  code-sandbox-mcp with `TEST_POSTGRES_DSN` set to confirm 7 live
  `CheckViolationError` cases.
- `uv run pytest tests/integration/test_company_listing_link_live.py tests/integration/test_fundamentals_restatement_live.py -q`
  collected cleanly and skipped safely without host DSN: 7 skipped.
- `uvx ruff check backend/finlib/fundamentals.py backend/finlib/__init__.py tests/unit/test_company_fundamentals_schema_contract.py tests/unit/test_fundamentals_python_indicators.py tests/unit/test_postgres_migrations_static.py tests/integration/test_company_listing_link_live.py tests/integration/test_fundamentals_restatement_live.py`
  passed.
- `uvx ruff format --check backend/finlib/fundamentals.py backend/finlib/__init__.py tests/unit/test_company_fundamentals_schema_contract.py tests/unit/test_fundamentals_python_indicators.py tests/unit/test_postgres_migrations_static.py tests/integration/test_company_listing_link_live.py tests/integration/test_fundamentals_restatement_live.py`
  passed.
- `uvx sqlfluff lint backend/memory/postgres/migrations/028_create_company_fundamentals.sql --dialect postgres`
  passed.
- `uv run mypy backend/finlib/fundamentals.py --strict` passed.
- `uv run pyright backend/finlib/fundamentals.py` passed with only the known
  cosmetic Pyright update notice.

Scope intentionally unchanged:

- No repository, ingestion agent, downloader, HTTP client, MCP/A2A runtime,
  Qdrant mutation, pgvector policy, user position, portfolio, brokerage or
  secret handling changes.

---

## FIXED LOCALLY — FINLIB-0 FL-PR09 RC-01 Adversarial Nits

Current branch: `feat/finlib-debenture-market-data`

Context:

- Cowork approved FL-PR09 with nits.
- NIT-01: `debenture_market_data` insert/update trigger guarded `fi_id`, but
  `fi_instruments.kind` could still drift from `debenture` to another kind
  after market data rows existed.
- NIT-02: `evaluation/results/` artifacts were dirty in the worktree and could
  be accidentally staged.

Resolution:

- Added migration `027_guard_debenture_kind_drift.sql` instead of editing the
  already reviewed migration `026`, preserving checksum stability.
- Added `prevent_debenture_market_data_kind_drift()`.
- Added trigger `trg_fi_instruments_debenture_market_data_kind_guard` on
  `fi_instruments BEFORE UPDATE OF kind`.
- The trigger rejects changing an instrument away from `debenture` when rows
  already exist in `debenture_market_data`.
- Added static schema assertions for the new bidirectional kind guard.
- Added live integration coverage for attempted `debenture -> cdb` drift after
  inserting temporal market data.
- Added explicit `evaluation/results/*` ignore rule while preserving
  `evaluation/results/.gitkeep`.
- Documented the bidirectional invariant in the FL-PR09 SDD.

Validation:

- `uv run pytest tests/unit/test_debenture_market_data_schema_contract.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 16 passed.
- `uv run pytest tests/integration/test_debenture_market_data_hypertable_live.py -q`
  skipped safely without host DSN: 14 skipped.
- `uvx ruff check tests/unit/test_debenture_market_data_schema_contract.py tests/integration/test_debenture_market_data_hypertable_live.py`
  passed.
- `uvx ruff format --check tests/unit/test_debenture_market_data_schema_contract.py tests/integration/test_debenture_market_data_hypertable_live.py`
  passed.
- `uv run mypy --strict tests/unit/test_debenture_market_data_schema_contract.py tests/integration/test_debenture_market_data_hypertable_live.py`
  passed.
- `uv run pyright tests/unit/test_debenture_market_data_schema_contract.py tests/integration/test_debenture_market_data_hypertable_live.py`
  passed with only the known cosmetic Pyright update notice.
- `uvx sqlfluff lint backend/memory/postgres/migrations/026_create_debenture_market_data.sql backend/memory/postgres/migrations/027_guard_debenture_kind_drift.sql --dialect postgres`
  passed.
- `git diff --check` passed.

Scope intentionally unchanged:

- No repository, ingestion agent, live downloader, MCP/A2A runtime, Qdrant,
  pgvector, user-position, brokerage, portfolio or secret handling changes.
- Pre-existing dirty tracked result artifacts were not reverted or staged.

---

## CONTEXT UPDATE — Cowork Reviewer Pack

Current branch: `feat/finlib-debenture-market-data`

What changed:

- Added `docs/04_MEM/COWORK_REVIEWER_CONTEXT.md`.
- Added a compact pointer in `CLAUDE.md`.
- Kept `docs/04_MEM/current_state.md` as live state and
  `docs/04_MEM/decisions.md` as durable decision log.

Purpose:

- Give Claude Cowork a token-cheap A2A reviewer pack.
- Keep adversarial review structured, compact and evidence-first.
- Reduce repeated context expansion in reviewer prompts.
- Preserve settled runtime truths such as Qdrant `1.18.x` family parity.

Scope intentionally unchanged:

- No MCP connector, desktop extension or remote connector was added.
- No secrets, `.env`, service runtime state, DB state or generated reports were
  touched for this context update.

---

## CONTEXT UPDATE — Qdrant/UV Lock Integrity

Current branch: `feat/finlib-debenture-market-data`

Decision treated as settled:

- Qdrant server/client parity is by `1.18.x` family, not exact patch parity.
- Active server target remains `qdrant/qdrant:v1.18.2`.
- Accepted Python client target remains `qdrant-client 1.18.0`.
- Do not reopen the Qdrant 1.18 family decision unless a future explicit
  upgrade sprint requests it.

What changed:

- `pyproject.toml` now bounds the Python SDK to `qdrant-client>=1.18,<1.19`.
- `uv.lock` was regenerated and resolves `qdrant-client==1.18.0`.
- `infra/qdrant/version_contract.yaml`, ADR-018, PKD-D2P-00Y and active Qdrant
  result docs now document the bounded `1.18.x` dependency contract.
- `CLAUDE.md` now reports Qdrant v1.18.2 via Docker and a Python SDK bounded to
  the `qdrant-client 1.18.x` family.
- `backend/rag/qdrant_store.py` was inspected and did not require edits; it
  already uses the modern `query_points` API instead of legacy `search`.

Validation:

- Static search confirms no active dependency on `qdrant-client==1.13.2`.
- `uv.lock` contains `qdrant-client` version `1.18.0` under the project
  specifier `>=1.18,<1.19`.
- Runtime `uv run` verification was intentionally not repeated after the human
  decision to accept server `1.18.x` and client `1.18.0` as the project truth.

Scope intentionally unchanged:

- No Qdrant container restart, rebuild, volume reset or collection mutation.
- No dependency family upgrade to `1.19+`.
- No changes to unrelated PR-08/PR-09 generated result artifacts already dirty
  in the worktree.

---

## IN PROGRESS — FINLIB-0 FL-PR09 Debenture Market Data

Current branch: `feat/finlib-debenture-market-data`

GitHub workflow:

- Issue created: https://github.com/franciscosalido/OPENCLAW/issues/119
- Initial SDD committed locally:
  `afc1506 docs: define finlib debenture market data SDD`.
- Draft PR creation was attempted after the SDD commit, but GitHub rejected it
  because the stacked local branch is not published and the remote could not
  resolve a head SHA. No push, force-push or merge to `main` was performed.

Goal:

- Add temporal market data for debentures already represented in
  `fi_instruments`, without repositories, agents, live downloaders, external
  clients, user-position tables, Qdrant or pgvector changes.

Implemented in this branch:

- Added migration `026_create_debenture_market_data.sql`.
- Added exactly one table: `debenture_market_data`.
- Modeled `debenture_market_data` as a TimescaleDB hypertable on `ts` with
  one-month chunks.
- Used `fi_id UUID REFERENCES fi_instruments(instrument_id)` instead of ISIN
  as database identity.
- Enforced that market rows point only to `fi_instruments.kind = 'debenture'`
  with trigger `trg_debenture_market_data_instrument_kind`.
- Added revisioned temporal identity with `PRIMARY KEY (fi_id, ts, revision)`
  and idempotent content lineage via `UNIQUE (lineage_hash, ts)`.
- Required provenance through `source_id`, `run_id`, `lineage_hash`,
  `schema_version`, object-only `quality_flags` and object-only `metadata`.
- Added data-quality checks for at least one measurement, positive PU when
  present, non-negative duration and non-whitespace lineage.
- Narrowly hardened the existing `anbima_debentures` source limitations for
  secondary-market observations without creating a second debenture catalog.
- Added static schema-contract tests and live isolated PostgreSQL tests for
  hypertable, constraints, trigger, revision history and cross-sprint tables.

Validation so far:

- `uv run pytest tests/unit/test_debenture_market_data_schema_contract.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 16 passed.
- `uv run pytest tests/unit -q` passed: 2029 passed, 261 subtests passed.
- `uv run pytest tests/integration/test_debenture_market_data_hypertable_live.py -q`
  skipped safely: 13 skipped because no test DSN was present in the current
  host environment.
- `scripts/vibe_deep_run.sh 'uv run pytest tests/unit/test_debenture_market_data_schema_contract.py tests/integration/test_debenture_market_data_hypertable_live.py -q'`
  passed in the Python 3.12 Vibe sandbox with live services: 22 passed.
- `uv run mypy --strict tests/unit/test_debenture_market_data_schema_contract.py tests/integration/test_debenture_market_data_hypertable_live.py`
  passed.
- `uv run pyright tests/unit/test_debenture_market_data_schema_contract.py tests/integration/test_debenture_market_data_hypertable_live.py`
  passed with the known cosmetic Pyright version notice.
- `uvx ruff check` and `uvx ruff format --check` on changed Python tests
  passed.
- `uvx sqlfluff lint backend/memory/postgres/migrations/026_create_debenture_market_data.sql --dialect postgres`
  passed.
- `git diff --check` passed.

Scope intentionally unchanged:

- No CRI/CRA market data table.
- No `fi_positions`.
- No user holdings, account identifiers, personal identifiers, brokerage or
  portfolio fields.
- No repository, ingestion agent, HTTP client, MCP/A2A runtime, Qdrant or
  pgvector mutation.

---

## FIXED LOCALLY — FINLIB-0 FL-PR08 RC-01 Hardening

Current branch: `feat/finlib-private-fixed-income`

Context:

- Adversarial review approved FL-PR08 with two nits: Python did not expose a
  pre-DB `issuer_cnpj` validator, and `compute_quality_flags()` did not warn
  for uncommon `cdb + igpm` combinations.

Resolution:

- Added `validate_issuer_cnpj()` to `backend.finlib.rate_spec` and exported it
  from `backend.finlib`.
- Extended `validate_rate_spec_for_instrument()` with an optional
  `issuer_cnpj` parameter so future repositories can validate CNPJ shape
  before attempting a database write.
- Added unit coverage for valid, masked, short, long and non-numeric CNPJ
  values.
- Added an advisory `uncommon_cdb_igpm` quality flag while keeping warnings
  non-blocking and outside database constraints.
- Updated FL-PR08 SDD with the Python CNPJ validator and quality-flag behavior.

Scope intentionally unchanged:

- No migration edits after `025`.
- No database checksum churn.
- No repository, live ingestion, external client, user-position table or
  runtime service changes.

---

## IN PROGRESS — FINLIB-0 FL-PR08 Private Fixed Income

Current branch: `feat/finlib-private-fixed-income`

GitHub workflow:

- Issue created: https://github.com/franciscosalido/OPENCLAW/issues/118
- Draft PR creation was attempted before implementation, but GitHub rejected it
  because the branch had no commits and local `main` is ahead of
  `origin/main` by the stacked FINLIB commits. The branch remains local until
  the stacked base is published or coordinated.

Goal:

- Add the minimal private fixed-income reference catalog for CDB, LCA, LCI,
  CRI, CRA and debenture without repositories, agents, ingesters, external
  clients, user positions, valuation, Qdrant or pgvector changes.

Implemented in this branch:

- Added migration `025_create_fi_instruments.sql`.
- Added exactly one table: `fi_instruments`.
- Seeded `local_fixed_income_input` and `anbima_debentures` in
  `ops_data_sources` using existing allowed source kinds.
- Modeled `issuer_cnpj` as 14 canonical digits and optional ISO-like `isin`.
- Constrained `kind`, `indexer`, `rate_spec` JSONB shape, source provenance,
  JSONB object fields, non-whitespace text and unique `lineage_hash`.
- Enforced fail-safe FGC semantics: CRI, CRA and debenture cannot be
  `fgc_covered = true`.
- Enforced `maturity_date` for CRI, CRA and debenture, and `maturity_date >=
  issue_date` when both are present.
- Added `backend.finlib.rate_spec.RateSpec` as a strict Pydantic v2 model with
  semantic validation for prefixado, percent-of-indexer, indexer-plus-spread
  and inflation-plus-coupon contracts.
- Added canonical `compute_fi_lineage_hash()` and explicit rejection of Level
  0 position fields.
- Documented the Level 0 boundary in the FL-PR08 SDD.

Validation:

- `uv run pytest tests/unit/test_fi_instruments_schema_contract.py tests/unit/test_fi_rate_spec_validation.py -q`
  passed: 34 passed.
- `uv run pytest tests/unit/test_fi_instruments_schema_contract.py tests/unit/test_fi_rate_spec_validation.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 41 passed.
- `uv run pytest tests/unit -q` passed: 2013 passed, 261 subtests passed.
- `uv run mypy --strict .` passed: no issues in 441 source files.
- `uv run pyright backend/finlib tests/unit/test_fi_instruments_schema_contract.py tests/unit/test_fi_rate_spec_validation.py`
  passed: 0 errors, 0 warnings.
- `uvx ruff check .`, `uvx ruff format --check .`, and `git diff --check`
  passed.
- `uvx sqlfluff lint backend/memory/postgres/migrations/025_create_fi_instruments.sql --dialect postgres`
  passed.
- Full SQLFluff over historical migrations still fails on pre-existing
  migrations 000-016; migration 025 is clean.
- `scripts/vibe_deep_run.sh 'uv run pytest tests/unit/test_fi_instruments_schema_contract.py tests/unit/test_fi_rate_spec_validation.py -q'`
  was attempted, but Docker failed before tests with `DeadlineExceeded` while
  resolving `docker/dockerfile:1`.

Scope intentionally unchanged:

- No `fi_positions`.
- No user holdings, accounts, CPF, broker/custodian or portfolio fields.
- No live data access.
- No repository, agent, MCP, A2A runtime, Qdrant or pgvector mutation.

---

## FIXED LOCALLY — FINLIB-0 FL-PR07 RC-02 Fund Whitespace Coverage

Current branch: `codex/fl-pr07-rc02-fund-whitespace-tests`

Context:

- The adversarial V2 review confirmed the FL-PR07 schema was correct, but
  flagged a permanent coverage gap: live whitespace tests covered
  `legal_name` but not nullable registry descriptors `cvm_class` and
  `fund_type`.

Resolution:

- Expanded the live integration parametrization to cover whitespace-only
  `cvm_class` and `fund_type` values.
- Fixed the test statement builder so the parametrized field is actually
  inserted for nullable fields instead of only changing `legal_name`.
- Documented the registry text contract in the FL-PR07 SDD: optional
  descriptors may be absent, but cannot be semantic whitespace when present.

Scope intentionally unchanged:

- No migration edits.
- No schema checksum changes.
- No runtime ingestion, repository or agent code.

---

## IN PROGRESS — FINLIB-0 FL-PR07 Fund Library

Current branch: `feat/finlib-fund-library`

RC-01 migration checksum hardening:

- Fixed pre-existing checksum drift for
  `022_create_macro_catalog_observations.sql`.
- Root cause: a documentation-only SQL comment about `value <> 0` was added
  after migration 022 had already been applied to the local PostgreSQL
  database. The live `schema_migrations` checksum was
  `1b2a45c168d3e6ce0b26f606a3dd437b25e19974db9b2da035959279ff741d76`.
- Resolution: restored migration 022 to the already-applied canonical content
  by removing the post-apply inline comment; the explanation remains in the
  FL-PR05 SDD.
- Added a unit guard pinning the canonical migration 022 checksum so future
  cosmetic edits fail before runtime.
- Fixed two Vibe integration false positives where offline LiteLLM MCP config
  tests inherited `host.docker.internal` from the sandbox environment. The
  tests now pass explicit loopback-only offline env maps and the runtime
  validator remains strict.

RC-01 validation:

- `uv run pytest tests/unit/test_macro_series_seed.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 25 passed.
- `uv run pytest tests/integration/test_pr07_litellm_mcp_registration_smoke.py tests/integration/test_pr08_litellm_mcp_tools_live.py tests/unit/test_macro_series_seed.py -q`
  passed: 20 passed.
- Vibe targeted checksum-regression suite passed:
  `test_postgres_repository.py`, `test_pr01_concurrency_gaps.py`,
  `test_pr02_market_bars_concurrency.py` -> 19 passed.
- Vibe full integration suite passed: 192 passed, 14 skipped,
  3 subtests passed.
- `uv run mypy --strict` on changed test files passed.
- `uvx ruff check` and format check on changed test files passed.

Workflow note:

- `git pull --ff-only` on local `main` reported "Already up to date".
- Branch `feat/finlib-fund-library` was created from local `main`.
- Draft PR creation was attempted before implementation, but `gh pr create`
  could not proceed because the branch had not been pushed. No push or merge
  was performed.

Goal:

- Add the minimal CVM fund registry and Informe Diario library for FINLIB-0
  without implementing repositories, agents, MCP tools, runtime ingestion,
  live CVM clients, Qdrant changes, pgvector changes or FL-PR08+ tables.

Implemented in this branch:

- Added migration `024_create_fund_registry_daily_info.sql`.
- Added exactly two tables: `fund_registry` and `fund_daily_info`.
- Seeded canonical source `cvm_informes_diarios` in `ops_data_sources` with
  `kind='regulator'`.
- Modeled `fund_cnpj` as the canonical 14-digit natural key in
  `fund_registry`.
- Modeled `fund_daily_info` as a TimescaleDB hypertable on `ts` with
  `chunk_time_interval => INTERVAL '1 month'`.
- Enforced revisioned history with
  `PRIMARY KEY (fund_cnpj, ts, revision)` and idempotency with
  `UNIQUE (lineage_hash, ts)`.
- Added data-quality constraints for mandatory positive `quota_value`,
  mandatory `net_worth`, non-negative `shareholders`, non-negative flows when
  present, mandatory provenance, object-only JSONB fields and semantic text
  guards using `~ '\S'`.
- Documented CVM CSV semantics, CNPJ normalization, DT_COMPTC timestamp
  semantics, future reapresentacao by `revision+1`, advisory-lock mitigation
  and future repository/audit transaction contract.
- Added static schema tests, CSV sample normalization/lineage tests and live
  isolated PostgreSQL integration tests for hypertable, idempotency,
  reapresentacao and DQ constraints.

Validation so far:

- `uv run pytest tests/unit/test_fund_schema_contract.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 17 passed.
- Local integration without DSN skipped safely: 27 skipped.
- Vibe sandbox focused unit suite passed: 17 passed.
- Vibe sandbox live integration suite passed: 27 passed.
- `uv run mypy --strict tests/unit/test_fund_schema_contract.py tests/integration/test_fund_daily_info_hypertable_live.py tests/integration/test_fund_daily_info_idempotency_live.py`
  passed.
- `uvx ruff check` on new tests passed.
- `uvx sqlfluff lint backend/memory/postgres/migrations/024_create_fund_registry_daily_info.sql --dialect postgres`
  passed.

---

## IN PROGRESS — FINLIB-0 FL-PR06 Treasury Library

Current branch: `feat/finlib-treasury-library`

RC-01 reviewer hardening:

- Documented the explicit price-correction policy in
  `docs/specs/finlib-0/pr-06-treasury-library.md`: FL-PR06 has no
  `revision` column, so a corrected `(bond_id, ts)` observation is rejected by
  the primary key and must become a future repository-level audited policy or a
  future revisioned migration.
- Added live integration coverage proving negative rates are accepted when the
  rate spread remains sane.
- Expanded the test-local Tesouro CSV bond-type normalizer to cover all
  treasury bond labels accepted by the schema.

Goal:

- Add the minimal Tesouro Direto mark-to-market library for FINLIB-0 without
  implementing repositories, agents, MCP tools, runtime ingestion, Qdrant
  changes, pgvector changes or FL-PR07+ financial tables.

Implemented in this branch:

- Added migration `023_create_treasury_bonds_prices.sql`.
- Added exactly two tables: `treasury_bonds` and `treasury_prices`.
- Seeded canonical source `tesouro_transparente` in `ops_data_sources` with
  `kind='treasury'`, matching the enum introduced by FL-PR02.
- Modeled `treasury_prices` as a TimescaleDB hypertable on `ts` with
  `chunk_time_interval => INTERVAL '1 month'`.
- Enforced `PRIMARY KEY (bond_id, ts)` and
  `UNIQUE (lineage_hash, ts)` so all unique constraints on the hypertable
  include the partitioning column.
- Added data-quality constraints for non-negative prices/base value, spread
  sanity, no all-null observation rows, mandatory provenance, object-only JSONB
  fields and no operationally future-dated `ts`.
- Documented the Tesouro CSV contract, normalized reference-date semantics,
  source-kind choice and future repository/audit transaction contract.
- Added static contract tests, CSV sample round-trip tests and live isolated
  PostgreSQL integration tests for hypertable/idempotency/DQ semantics.

Workflow note:

- Draft PR creation was attempted before implementation, but `gh pr create`
  could not proceed because the branch had not been pushed. No push or merge
  was performed.

---

## FIXED LOCALLY — FINLIB-0 FL-PR05 RC-01 PTAX Evidence Notes

Context:

- Adversarial review flagged two minor findings before commit:
  `vw_fx_brlusd` used `value <> 0` without an inline explanation, and
  `ptax_usdbrl_venda` used provider code `1` while the review expected
  `10814`.

Resolution:

- Added an inline SQL comment documenting that `value <> 0` prevents division
  by zero in derived BRL/USD columns.
- Researched BCB Dados Abertos and bounded BCData/SGS API responses.
- Kept `ptax_usdbrl_venda.provider_code = "1"` because BCB Dados Abertos
  identifies SGS `1` as daily USD/BRL venda, while a bounded API sanity check
  for `10814` returned a non-FX value in the checked window.
- Documented the evidence in `docs/specs/finlib-0/pr-05-macro-library.md`.
- Added a unit contract locking the current planning-reference decision:
  compra `10813`, venda `1`, venda not `10814`, still requiring live
  verification before operational ingestion.

Validation:

- `uv run pytest tests/unit/test_macro_series_seed.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 24 passed.
- `uvx sqlfluff lint backend/memory/postgres/migrations/022_create_macro_catalog_observations.sql --dialect postgres`
  passed.
- `uvx ruff check tests/unit/test_macro_series_seed.py` and
  `uvx ruff format --check tests/unit/test_macro_series_seed.py` passed.
- `uv run mypy --strict tests/unit/test_macro_series_seed.py` passed.

---

## IN PROGRESS — FINLIB-0 FL-PR05 Macro Library

Current branch: `feat/finlib-macro-library`

Goal:

- Add the minimal Brazilian macroeconomic and FX library for FINLIB-0 without
  implementing repositories, ingestion agents, MCP tools or FL-PR06+ tables.

Implemented in this branch:

- Added migration `022_create_macro_catalog_observations.sql`.
- Added exactly two tables: `macro_series_catalog` and `macro_observations`.
- Added exactly one view: `vw_fx_brlusd`.
- Seeded canonical source `bcb_sgs` in `ops_data_sources` with explicit
  methodology limitations and live-verification warning.
- Seeded seven catalog series: IPCA, IGP-M, Selic meta, Selic diaria, CDI,
  PTAX USD/BRL compra and PTAX USD/BRL venda.
- Marked all SGS provider codes as `planning_reference` with
  `requires_live_verification = true`; no provider code is treated as ground
  truth in this PR.
- Made `macro_observations` a TimescaleDB hypertable on `ref_ts` with
  `chunk_time_interval => INTERVAL '3 months'`.
- Enforced provenance with mandatory `source_id`, `run_id` and
  `lineage_hash`; `source_id` references `ops_data_sources`, and `run_id`
  references `ops_ingestion_runs`.
- Modeled revisions as append-only rows via
  `PRIMARY KEY (series_code, ref_ts, revision)`.
- Modeled identical reingestion idempotency with
  `UNIQUE (lineage_hash, ref_ts)`, because TimescaleDB unique constraints on
  hypertables must include the partition column.
- Kept BRL/USD out of storage; `vw_fx_brlusd` derives BRL/USD from latest
  PTAX USD/BRL compra/venda revisions.
- Documented the future repository contract: domain writes and exactly one
  `audit_agent_writes` row per logical batch in the same transaction.

Validation:

- `uv run pytest tests/unit/test_macro_series_seed.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 23 passed.
- `uv run pytest tests/unit -q` passed: 1955 passed, 261 subtests passed.
- Local integration without DSN skipped safely: 19 skipped.
- Vibe sandbox focused suite passed: 35 passed.
- Vibe sandbox live hypertable suite passed: 14 passed.
- Vibe sandbox live revision/view suite passed: 5 passed.
- `uv run mypy --strict .` passed: no issues in 431 source files.
- `uv run pyright backend/` passed: 0 errors, 0 warnings.
- `uvx ruff check .`, `uvx ruff format --check .`,
  `uvx sqlfluff lint backend/memory/postgres/migrations/022_create_macro_catalog_observations.sql --dialect postgres`,
  and `git diff --check` passed.

Workflow limitation:

- Draft PR creation was attempted before implementation, but `gh pr create`
  could not proceed because the branch was local/unpushed and the worktree had
  local changes. No push or merge was performed.
- Full SQLFluff over all historical migrations still reports pre-existing
  style violations in migrations 000-016; migration 022 is SQLFluff-clean.

---

## IN PROGRESS — FINLIB-0 FL-PR04 Audit Agent Writes

Current branch: `feat/finlib-audit-agent-writes`

Goal:

- Add append-only audit storage for future FINLIB data-agent/repository writes,
  without implementing repositories, agents, MCP write tools or FL-PR05+
  financial library tables.

Implemented in this branch:

- Added migration `021_create_audit_agent_writes.sql`.
- Added exactly one table: `audit_agent_writes`.
- Added mandatory `trace_id`, optional `run_id` FK to `ops_ingestion_runs`,
  semantic non-whitespace guards for `agent_id`, `repository`, `target_table`
  and `batch_hash`, safe JSONB-object `metadata`, `row_count >= 0`, and
  operation domain `insert/update/upsert/bulk_insert/bulk_upsert`.
- Explicitly excluded `delete` as an audit operation for this PR.
- Added focused indexes on `trace_id`, partial `run_id`, `(agent_id,
  created_at DESC)` and `(repository, target_table, created_at DESC)`.
- Added `prevent_audit_agent_writes_mutation()` and
  `trg_audit_agent_writes_append_only` to reject UPDATE/DELETE with an
  append-only error.
- Added `REVOKE UPDATE, DELETE ... FROM PUBLIC` as defense-in-depth and
  documented that PostgreSQL owner capability means the trigger is the
  authoritative guard in the current single-role setup.
- Added SDD documentation for future repository transaction atomicity: domain
  write and exactly one audit row per logical batch in the same transaction.
- Added static unit tests and live isolated PostgreSQL tests for insert,
  trigger append-only behavior, constraints, FK, metadata safety, ACL catalog
  inspection and optional non-owner role enforcement when CREATE ROLE is
  available.

Workflow limitation:

- GitHub Issue/Draft PR creation was attempted but blocked locally by GitHub
  CLI keyring/API timeout. Branch remains local and unmerged into `main`.

---

## FIXED LOCALLY — FINLIB-0 Migration 020 Checksum Drift

Context:

- Adversarial review for FL-PR04 found a pre-existing checksum drift on
  `020_create_ops_watermarks_quality_outbox.sql`.
- The drift was caused by comments added after the migration had already been
  applied to local PostgreSQL environments.

Resolution:

- Restored migration `020_create_ops_watermarks_quality_outbox.sql` to the
  original applied content with SHA-256
  `bb63d55faede65436f58e4b44c5d0ab6e5d3c352d6b150e81fcbcf03b7cbe99e`.
- Moved the explanatory text about `CREATE OR REPLACE`, `watermark_value` and
  non-concurrent indexes into
  `docs/specs/finlib-0/pr-03-watermarks-quality-outbox.md`.
- Updated unit tests so documentation assertions read the SDD, not the
  immutable migration text.

---

## IN PROGRESS — FINLIB-0 FL-PR03 RC-01 Review Hardening

Current branch: `feat/finlib-watermarks-quality-outbox-rc01`

Goal:

- Close non-blocking reviewer findings for FL-PR03 without expanding scope
  beyond watermarks, data-quality checks and outbox tables.

Implemented in this branch:

- Documented in the SDD that `watermark_ts` is the canonical monotonic
  comparator and `watermark_value` is a descriptive label only.
- Documented in the SDD why FL-PR03 uses `CREATE OR REPLACE` for
  function/trigger idempotency and why indexes deliberately avoid
  `CONCURRENTLY` under the transactional migration runner.
- Added live adversarial PostgreSQL coverage for missing
  `aggregate_type`/`aggregate_id` in outbox events.
- Added live adversarial PostgreSQL coverage for `attempts > max_attempts`.

---

## IN PROGRESS — Qdrant 1.18.x test warning hardening

Current branch: `feat/finlib-watermarks-quality-outbox`

Goal:

- Keep Vibe/pytest output clean without changing the accepted Qdrant 1.18.x
  compatibility policy.

Implemented in this branch:

- Accepted Cowork's root-cause finding: `qdrant-client >=1.17.1` runs
  server-version probing in a daemon thread; in Docker, `localhost:6333` can
  point to the container loopback, so the background probe warns even when
  client `1.18.0` and server `1.18.2` are compatible by major/minor family.
- Added pytest warning filtering in `pyproject.toml` and global Python warning
  filtering in `tests/conftest.py` for only
  `Failed to obtain server version` `UserWarning`.
- Set `asyncio_default_fixture_loop_scope = "function"` to remove the pytest
  asyncio deprecation warning.
- Documented the temporary filter and removal rule in
  `docs/testing/vibe_deep_testing.md`.

Future cleanup:

- When PyPI publishes `qdrant-client >=1.18.2`, run
  `uv lock --upgrade-package qdrant-client`, remove both warning filters, and
  rerun Vibe tests with `-W always`.

---

## IN PROGRESS — FINLIB-0 FL-PR03 Watermarks, Quality and Outbox

Current branch: `feat/finlib-watermarks-quality-outbox`

Goal:

- Add operational idempotency, data-quality recording and a minimal Postgres
  outbox for FINLIB-0 without data agents, repositories, audit tables or MCP
  tools.

Implemented in this branch:

- Added migration `020_create_ops_watermarks_quality_outbox.sql`.
- Added `ops_ingestion_watermarks` with `(source_id, dataset)` primary key,
  JSONB object metadata, source/run FKs and direct-update trigger protection
  against timestamp regression.
- Added `ops_data_quality_checks` with severity limited to `info`, `warning`,
  `error` and `critical`, JSONB object contracts and run FK.
- Added `ops_outbox_events` with explicit status lifecycle, retry counters,
  lock metadata constraints and partial pending poll index.
- Documented and tested the official outbox poll contract using
  `FOR UPDATE SKIP LOCKED`.
- Added static schema tests and live isolated PostgreSQL tests for outbox
  double-dispatch prevention, empty poll latency and watermark concurrency.

Known workflow limitation:

- Draft PR/Issue creation was not completed because `gh auth status` timed out
  in the local keyring and local `main` is ahead of `origin/main`. Branch work
  remains local until the GitHub base is published/ratified.

---

## IN PROGRESS — Vibe pytest report/timeout plugin hardening

Current branch: `feat/vibe-pytest-report-timeout`

Goal:

- Ensure Vibe runners can pass pytest `--json-report` and `--timeout`
  arguments inside the official Python 3.12 venv.

Implemented in this branch:

- Added `pytest-json-report` and `pytest-timeout` to the `dev` dependency
  group and `uv.lock`, which is the dependency source consumed by
  `Dockerfile.openclaw-sandbox`.
- Added `requirements-vibe.txt` for external Vibe runners that install extra
  pytest plugins from a requirements file.
- Added unit contracts proving the Vibe requirements file, `pyproject.toml`
  and `uv.lock` keep both plugins declared.

---

## IN PROGRESS — FINLIB-0 FL-PR02 Whitespace Integrity RC

Current branch: `feat/finlib-ops-whitespace-rc01`

Goal:

- Fix semantic-empty text bypasses in migration `019_create_ops_sources_runs.sql`
  before publishing FL-PR02 remotely.

Implemented in this branch:

- Replaced `length(btrim(...)) > 0` guards with PostgreSQL regex checks using
  `~ '\S'` for `methodology_limitations`, `agent_id`,
  `source_snapshot_hash` and `error_summary`.
- Updated the `execute + completed` compound snapshot rule to require
  `source_snapshot_hash IS NOT NULL AND source_snapshot_hash ~ '\S'`.
- Added an operational maximum of 128 characters for `source_id`.
- Added static and live integration coverage for tab, newline and carriage
  return whitespace-only bypasses.

---

## IN PROGRESS — FINLIB-0 FL-PR02 Ops Sources and Runs

Current branch: `feat/finlib-ops-sources-runs`

Goal:

- Add the first FINLIB operational tables for financial source registry and
  ingestion run bookkeeping, without agents, repositories, watermarks, data
  quality, outbox or audit tables.

Implemented in this branch:

- Added migration `019_create_ops_sources_runs.sql`.
- Added `ops_data_sources` with required methodology limitations, JSONB object
  metadata constraint and B3 historical quotes seed.
- Added `ops_ingestion_runs` with `uuidv7()` run IDs, source FK, explicit
  `dry_run`/`execute` modes, explicit statuses, non-negative counters,
  mandatory trace id and completed execute snapshot-hash rule.
- Added focused indexes on `(source_id, started_at DESC)`, `trace_id`, and
  `(status, started_at DESC)`.
- Added unit schema contract tests and isolated live integration tests.
- Added `docs/specs/finlib-0/pr-02-ops-sources-runs.md`.

Out of scope by design:

- No `ops_ingestion_watermarks`, `ops_data_quality_checks`,
  `ops_outbox_events`, `audit_agent_writes`, repositories or data agents.

---

## IN PROGRESS — FINLIB-0 FL-PR01 PostgreSQL Readiness

Current branch: `feat/finlib-postgres-readiness`

Goal:

- Implement the first FINLIB gate for "PostgreSQL/TimescaleDB readiness +
  migrations + schemas".

Implemented in this branch:

- Added migration `018_enable_library_extensions.sql` for `pg_trgm` and
  `btree_gin`.
- Added `scripts/check_postgres_readiness.py`, a JSON-only readiness gate for
  PostgreSQL, required extensions, migration head, temp write probe and
  read-only role presence.
- Added `infra/postgres/initdb/002_readonly_role.sql` to provision
  `quimera_readonly NOLOGIN` for fresh local volumes and documented the
  one-time bootstrap for existing volumes.
- RC-02 hardened existing-volume operations: documented one-time
  `pg_stat_statements` extension creation, made default privileges explicit for
  `FOR ROLE quimera`, added Bandit `nosec` annotations for intentional safe
  exception/subprocess patterns, and improved the live readiness assertion
  message.
- Integrated safe Postgres readiness summary into `scripts/quimera_status.py`.
- Added unit and live integration tests for the readiness contract.
- Added `docs/specs/finlib-0/pr-01-postgres-readiness.md`.

Gate rule:

- FINLIB data agents remain blocked until the PostgreSQL/FINLIB readiness gate
  exits `0`. The later consolidated `scripts/check_finlib_readiness.py` will
  wrap this gate; FL-PR01 owns only the PostgreSQL readiness layer.

---

## PLANNING — FINLIB-0 Sprint Master Spec (no code changed)

Authored by Claude (Fable) on 2026-06-10 after live repo inspection. This is
the pre-agent phase item 1: "PostgreSQL/TimescaleDB readiness + migrations +
schemas" for Brazilian financial asset libraries.

- New spec: `docs/specs/finlib-0/SPRINT_FINLIB0_MASTER_SPEC.md`.
- PR ladder FL-PR00..FL-PR10 (≤400 production lines each, SDD-first,
  Red/Green/Mutate, Cowork adversarial review, GitHub-only merge per ADR-011).
- Scope: readiness script `check_postgres_readiness.py`; migrations 018–028:
  pg_trgm/btree_gin, ops layer (data_sources, ingestion_runs, watermarks,
  data_quality_checks, outbox_events SKIP LOCKED), audit_agent_writes
  (append-only), macro library (IPCA/IGP-M/Selic/CDI/PTAX USD-BRL),
  Tesouro Direto MtM, CVM fund registry + informe diário, fixed income
  (CDB/LCA/LCI/CRI/CRA) + debêntures, company fundamentals, continuous
  aggregates + compression; `backend/finlib/` repositories with mandatory
  audit append in-transaction.
- Standing decisions to ratify in FL-PR00 (ADR-A..E): keep `public` schema
  prefix convention (no namespaced schemas in V1); runner migrations dir is
  the only schema source of truth vs `infra/postgres/sql`; derived indicators
  (incl. OBV) go to `market_features`, never new tables; BRL/USD is a derived
  view of PTAX, never stored; COE permanently out of scope.
- Data agents (MarketLibrarySeeder, ResearchLibraryCurator, TreasuryMtM) are
  the NEXT sprint and are gated on `check_finlib_readiness.py` exit 0.
- No code, migration, config or runtime state was modified in this session.

---

## codex/code-sandbox-mcp-python312 — code-sandbox-mcp Python 3.12 Runtime

Current branch: `codex/code-sandbox-mcp-python312`
Base branch: local `main` at `4a8141f`.

Implemented:

- Accepted `openclaw-sandbox:latest` as the local truth for the
  code-sandbox-mcp runtime used by Claude Desktop.
- Hardened `Dockerfile.openclaw-sandbox` so the sandbox image is pinned to
  `python:3.12-slim` by digest and fails the build if Python drifts off the
  3.12 series.
- Kept project dependencies resolved from `uv.lock` into `/opt/openclaw-venv`,
  outside `/workspace`, so the runtime survives repository volume mounts.
- Kept PostgreSQL 18 client tools, Node.js/Pyright, `QUIMERA_E2E=true`, and
  `PYTHONPATH=/workspace` in the sandbox runtime.
- Added `docker/docker-compose.sandbox.yml` as the reproducible local build
  recipe for `openclaw-sandbox:latest`.
- Added `docs/04_MEM/CODE_SANDBOX_MCP_RUNBOOK.md` documenting the
  code-sandbox-mcp `-no-update` fix, the stale Python 3.14 regression, and
  post-build verification commands.
- Removed Claude's stray `test_demo.py` scratch file from the local PR scope.

Validation:

- `docker compose -f docker/docker-compose.sandbox.yml config`: passed.
- `docker compose -f docker/docker-compose.sandbox.yml build`: passed,
  produced `openclaw-sandbox:latest`.
- `docker run --rm openclaw-sandbox:latest python --version`:
  `Python 3.12.13`.
- `docker run --rm openclaw-sandbox:latest pg_dump --version`:
  `pg_dump (PostgreSQL) 18.4`.
- `docker run --rm openclaw-sandbox:latest node --version`: `v20.19.2`.
- `docker run --rm openclaw-sandbox:latest pyright --version`: `pyright
  1.1.409` with only the expected upstream notice that 1.1.410 exists.
- `docker run --rm -v "$PWD:/workspace" openclaw-sandbox:latest python -c
  "import backend; print(backend.__file__)"`: `/workspace/backend/__init__.py`.
- `uv run pytest tests/unit/test_vibe_sandbox_operational_contract.py
  tests/unit/test_pr09_backup_scripts_static.py -q`: 11 passed.
- `uvx ruff check tests/unit/test_vibe_sandbox_operational_contract.py`:
  passed.
- `uvx ruff format --check tests/unit/test_vibe_sandbox_operational_contract.py`:
  passed.
- `git diff --check`: clean.

Known residual:

- Per ADR-011, this local merge is not official integration. GitHub remains the
  source of truth after PR, CI, review, and GitHub merge.

---

## codex/tdd-m-real-mutation-hardening — TDD+M Real Mutation Hardening

Current branch: `codex/tdd-m-real-mutation-hardening`
Base branch: local `main` at `901463c`.

Implemented:

- Added real OpenTelemetry span tests for `backend.observability.decorators`
  using `TracerProvider`, `SimpleSpanProcessor`, and `InMemorySpanExporter`
  instead of relying only on fake spans.
- Hardened exception telemetry so decorators disable OpenTelemetry automatic
  exception recording and emit a sanitized exception event controlled by
  QUIMERA.
- Expanded DSN redaction so PostgreSQL DSNs are fully redacted in sanitized
  error messages.
- Hardened `backend.rag.collection_guard` so `bool` is not accepted as an
  embedding dimension and metadata completeness checks validate value types,
  not only key presence.
- Hardened gateway health checks so invalid JSON responses from Ollama or
  LiteLLM fail with controlled `SystemExit(1)` rather than uncaught parser
  exceptions.
- Updated `pyproject.toml` mutation config from deprecated
  `paths_to_mutate` to `source_paths` and kept
  `mutate_only_covered_lines = false` as an explicit anti-Goodhart policy.
- Excluded generated `.mutmut-cache/` and `mutants/` directories from mypy and
  pyright so generated mutation artifacts do not poison static analysis.
- Added `docs/testing/tdd_m_professional_methodology.md` documenting the
  QUIMERA Red/Green/Mutate/Refactor loop, survivor triage, and reviewer output.

Validation:

- `uv run pytest tests/unit/test_otel_decorators.py tests/unit/test_collection_guard.py tests/unit/test_gateway_health.py tests/unit/test_otel_safety.py tests/unit/test_vibe_sandbox_operational_contract.py -q`:
  66 passed, 2 subtests passed.
- `uv run pytest tests/unit -q`: 1895 passed, 259 subtests passed.
- `uvx ruff check .`: all checks passed.
- `uvx ruff format --check .`: 417 files already formatted.
- `uv run mypy --strict .`: success, 417 source files checked.
- `PYRIGHT_PYTHON_FORCE_VERSION=latest .venv/bin/pyright <changed python files>`:
  0 errors / 0 warnings.

Known residual:

- A host `uvx mutmut run ...` attempt used an isolated Python 3.14 environment
  and failed during pytest collection. Use `scripts/vibe_deep_run.sh
  'mutmut run'` for authoritative mutation runs because the official Vibe
  sandbox is Python 3.12 and joins the QUIMERA network.

---

## codex/vibe-deep-sandbox-hardening — Vibe Deep Sandbox and Dynamic Test Hardening

Current branch: `codex/vibe-deep-sandbox-hardening`
Base branch: local `main` after local adversarial contract merge
(`351fe5b`).

Implemented:

- Standardized the official Vibe sandbox Dockerfile on Python `3.12.13-slim`
  while keeping `/opt/openclaw-venv` as the image-owned dependency runtime.
- Added `scripts/vibe_deep_run.sh`, which rebuilds `vibe-sandbox:py312`,
  mounts the current checkout at `/workspace`, installs OpenClaw editable, and
  attaches to `QUIMERA_VIBE_DOCKER_NETWORK`, `quimera_network`, or
  `quimera-local_default` so dynamic tests can reach the live QUIMERA stack.
- Added `scripts/quarantine_venv_to_patio.sh`, a reversible virtualenv
  quarantine helper. It moves only `.venv` paths into
  `/Users/fas/projetos/_patio_venvs` and never deletes them.
- Created `/Users/fas/projetos/_patio_venvs` and moved
  `/Users/fas/projetos/vibe_code_sandbox/.venv` to
  `/Users/fas/projetos/_patio_venvs/vibe_code_sandbox.venv.20260609T012125Z`.
- Updated LiteLLM host startup to prefer the project root `.venv` and then
  `uv run litellm`; the old `infra/litellm/.venv` fallback is no longer part
  of the startup path. The directory was intentionally left on disk pending
  operator smoke confirmation.
- Added safe `mutmut` configuration in `pyproject.toml`: mutate `backend/`,
  copy required project context, avoid symlinked `mutants/`, and keep
  `mutate_only_covered_lines = false` so no-test regions remain visible.
- Added `.gitignore` coverage for `.mutmut-cache/` and `mutants/`.
- Updated `uv.lock`: `urllib3 2.6.3 -> 2.7.0` and `idna 3.13 -> 3.18`.
  `PyJWT` was already locked at `2.13.0`.
- Cleaned SQLFluff findings in `infra/postgres/sql/*.sql` while keeping
  non-concurrent index creation explicitly documented for migration/init
  context.
- Added `docs/testing/vibe_deep_testing.md` documenting official sandbox,
  dynamic stack access, mutation testing, venv patio and dependency audit
  policy.
- Added unit contracts for sandbox Python version, Vibe runner network/venv
  behavior, mutmut safe copy config, venv patio behavior and dependency locks.

Validation:

- `uv run pytest tests/unit -q`: 1884 passed, 259 subtests passed.
- `uvx ruff check .`: all checks passed.
- `uvx ruff format --check .`: 417 files already formatted.
- `uvx sqlfluff lint infra/postgres --dialect postgres`: all finished, no
  violations.
- `uv run mypy --strict .`: success, 417 source files checked.
- `uv run pyright`: 0 errors / 0 warnings.
- `uvx pip-audit --path .venv/lib/python3.12/site-packages`: no known
  vulnerabilities found; only local `openclaw` is skipped as non-PyPI.
- `docker build -f Dockerfile.openclaw-sandbox -t vibe-sandbox:py312 .`:
  passed; image contains Python 3.12.13, PyJWT 2.13.0, urllib3 2.7.0,
  idna 3.18 and qdrant-client 1.18.0.
- `QUIMERA_VIBE_BUILD_IMAGE=0 scripts/vibe_deep_run.sh 'scripts/vibe_sandbox_bootstrap.sh /workspace && python -m pytest tests/integration/test_agentic0_e2e.py tests/e2e/test_agent0_e2e.py -q'`:
  passed with 1 passed / 2 skipped. The skips are due to live Agent0 gateway
  preconditions, not sandbox Python/venv/network failure.
- `./run_smoke.sh --quick --json --allow-degraded`: completed with services
  online but returned degraded due to existing latency baseline warning and
  LiteLLM model introspection warning.

Known residual:

- Full `mutmut run` was not re-executed in this Codex turn because the previous
  Deep run took about 75 minutes. The runner and config now support a dynamic
  networked rerun without symlinked `mutants/`.
- Direct `python -m infra.litellm.smoke_test` reported readiness/liveliness,
  Ollama and Qdrant OK but `/v1/models` false when no LiteLLM key was exported
  in the current shell. The runner passes `QUIMERA_LLM_API_KEY` and
  `LITELLM_MASTER_KEY` through when the operator has them exported.

Scope intentionally not changed:

- No `.env`, `.env.*`, secrets, real data, Postgres/Qdrant volumes or
  `infra/litellm/.venv` directory content was read, deleted or committed.
- Generated PR-08/PR-09 smoke artifacts were restored and kept out of the diff.

---

## codex/rc-adversarial-report-contract-sync — Adversarial Report Contract Sync

Current branch: `codex/rc-adversarial-report-contract-sync`
Base branch: local `main` at `da758ee`.

Implemented:

- Added a unit contract proving `LocalGenerator(gateway_client=fake)` does not
  read gateway environment settings and does not require
  `QUIMERA_LLM_API_KEY`.
- Updated `LocalGenerator.__post_init__` so an explicitly injected
  `GatewayChatClient` is honored before calling `GatewayRuntimeConfig.from_env`.
  Primitive local validations still run.
- Resolved the current Ruff lint findings across evaluation, infra and scripts.
- Applied the mechanical Ruff formatting required by `ruff format --check .`.
  This touched the non-test files that were already outside the repository-wide
  formatting contract; it did not intentionally refactor behavior.
- Updated active LiteLLM/infra/recovery docs to use the current root wrapper:
  `./start_quimera.sh --start`, `./start_quimera.sh --status` and
  `./start_quimera.sh --stop`.
- Marked historical RAG-01B specs that mention removed `start_quimera.sh`
  subcommands as superseded, without reintroducing those subcommands.

Scope intentionally not changed:

- No `.env`, `.env.*`, secrets, service runtime data, Docker state, Qdrant,
  Postgres or LiteLLM process state touched.
- Generated `evaluation/results` output from the unit run was restored and not
  kept in the diff.
- Historical specs retain their original body for traceability; they only gain
  superseded notes.

Validation:

- `uv run pytest tests/unit -q`: 1877 passed, 259 subtests passed.
- `uvx ruff check .`: all checks passed.
- `uvx ruff format --check .`: 416 files already formatted.
- `uv run mypy --strict .`: success, 416 source files checked.
- `uv run pyright`: 0 errors / 0 warnings.
- `git diff --check`: clean.

Known residual:

- `pyright` reports that a newer Pyright release is available. This is an
  environment notice only; the configured gate passed with zero findings.

---

## codex/rc-quality-report-hardening — Standard Quality Report RC

Current branch: `codex/rc-quality-report-hardening`
Base branch: local `main` at `08e524f`.

Implemented:

- Hardened the standard quality report findings from 2026-06-08:
  - `asyncpg` imports now use `# type: ignore[import-untyped, unused-ignore]`
    so mypy passes both when asyncpg is untyped and when an analyzer no longer
    needs the ignore.
  - Replaced Bandit B101 production asserts in
    `backend/rag/hybrid_retriever.py` and
    `backend/rag/ollama_embedding_bakeoff.py` with explicit runtime guards.
  - Made `test_pr09_pg_dump_restore_verify_live` skip only when PostgreSQL is
    genuinely unreachable from a sandbox, while still failing on pg_dump/server
    version mismatch and script bugs.
  - Added Vulture config in `pyproject.toml` for Protocol/API keyword names
    that must remain stable (`vectors_config`, `with_payload`, Qwen3 encoder
    keyword args).
  - Added `.importlinter` with a first kept architecture contract:
    Agent0 must not import Postgres/working-memory/temporal memory backends
    directly.
  - Reduced complexity in `backend/ingestion/report.py`,
    `backend/rag/run_trace.py` and `backend/rag/qdrant_tuning.py`. The prior
    rank-D blocks reported by Xenon/Radon are no longer present.
  - `SnapshotService.create_delta_snapshot` now validates
    `since_checkpoint_id` instead of accepting and ignoring a blank value.

Research notes:

- Mypy `warn-unused-ignores` reports ignores that no longer suppress an error;
  combining `import-untyped` with `unused-ignore` is the portable compromise
  for environments where `asyncpg` typing visibility differs.
- Bandit B101 documents that `assert` statements are removed under optimized
  Python bytecode; production guards now raise explicit exceptions instead.
- Vulture supports `tool.vulture` configuration in `pyproject.toml`; this RC
  keeps the report aligned with `min_confidence = 80`.
- Import Linter forbidden contracts are suitable for enforcing the Agent0
  memory-access boundary without introducing a broad unreviewed layer model.

Validation:

- `uv run pytest tests/unit/test_quality_tool_contracts.py tests/unit/test_pr09_pg_dump_live_contract.py tests/unit/test_wm_snapshot_service.py tests/unit/test_hybrid_retriever.py tests/unit/test_qwen3_4b_embedding_bakeoff.py tests/unit/test_rag_run_trace.py tests/unit/test_qdrant_tuning_profiles.py tests/unit/test_ingestion_pipeline.py -q`:
  172 passed.
- `uv run pytest tests/integration/test_pr09_pg_dump_restore_verify_live.py -q`:
  passed in the local host environment.
- `uv run mypy --strict .`: success, 416 files checked.
- `uv run pyright`: 0 errors / 0 warnings.
- `uvx bandit -q -r backend`: success, no findings.
- `uvx vulture --config pyproject.toml`: success.
- `uvx --from import-linter lint-imports`: Agent0 memory boundary contract
  kept.
- `uvx xenon --max-absolute D --max-modules B --max-average B backend`:
  success, confirming no rank-D blocks remain.
- `git diff --check`: clean.

Known residual:

- `uvx xenon --max-absolute B --max-modules B --max-average B backend` still
  reports rank-C blocks across the historical backend. This RC removes the
  rank-D offenders from the report and reduces targeted complexity, but does
  not convert the entire backend to a strict B threshold in one broad refactor.

---

## codex/rc-vibe-sandbox-bootstrap — Vibe Sandbox Operational Bootstrap RC-02

Current branch: `codex/rc-vibe-sandbox-bootstrap`
Base branch: local `main` at `6823c02`.

Implemented:

- Added `scripts/vibe_sandbox_bootstrap.sh`, an idempotent runtime bootstrap
  for Vibe containers. It runs after the repository is mounted and installs
  OpenClaw editable with `uv pip install --no-deps --editable .`, falling back
  to `python -m pip install --no-deps --editable .`, then verifies
  `backend` imports.
- Added `scripts/vibe_semgrep_scan.sh`, which runs Semgrep outside the project
  virtualenv. Docker `semgrep/semgrep:latest` is preferred; `uvx semgrep` is
  the fallback. This avoids downgrading or constraining the project's
  OpenTelemetry dependencies.
- Added `scripts/vibe_pyright_json.sh`, which warms Pyright with
  `pyright --version >/dev/null` before running `pyright --outputjson`, so
  first-run bootstrap/progress text does not pollute stdout JSON.
- Updated `Dockerfile.openclaw-sandbox` to install `nodejs`, create the
  virtualenv directly at `/opt/openclaw-venv`, and warm Pyright during image
  build with `/opt/openclaw-venv/bin/pyright --version >/dev/null`.
- Added unit contracts covering the editable install bootstrap, isolated
  Semgrep policy, Pyright JSON warmup and sandbox Dockerfile Node/Pyright
  prewarm.

Research notes:

- Current Semgrep documentation recommends the latest Semgrep for current
  features/fixes and supports running Semgrep via Docker, `pipx` or `uv` for
  isolated versions. This RC uses Docker/`uvx` instead of adding Semgrep to the
  project dependency graph.
- Current Semgrep CI examples use the official `semgrep/semgrep` image and
  `semgrep scan --config auto`.
- Pyright JSON output should be produced only by the JSON command; the wrapper
  performs any first-run warmup before `--outputjson`.

Scope intentionally not changed:

- No OpenTelemetry dependency changed.
- No Semgrep dependency added to `pyproject.toml` or `uv.lock`.
- No `.env`, `.env.*`, secrets, service runtime state or data touched.
- Existing generated PR-08/PR-09 artifacts remain unstaged.

Validation:

- `bash -n scripts/vibe_sandbox_bootstrap.sh scripts/vibe_semgrep_scan.sh scripts/vibe_pyright_json.sh`
  passed.
- `uv run pytest tests/unit/test_vibe_sandbox_operational_contract.py tests/unit/test_pr09_backup_scripts_static.py tests/unit/test_gateway_final_baseline.py`
  passed: 16 tests.
- `uv run mypy --strict tests/unit/test_vibe_sandbox_operational_contract.py`
  passed.
- `uv run pyright tests/unit/test_vibe_sandbox_operational_contract.py`
  passed: 0 errors.
- `VIRTUAL_ENV="$PWD/.venv" scripts/vibe_sandbox_bootstrap.sh "$PWD"`
  passed and installed `openclaw` editable from the mounted checkout.
- `QUIMERA_SEMGREP_USE_DOCKER=0 scripts/vibe_semgrep_scan.sh --version`
  passed with isolated Semgrep `1.165.0`.
- `scripts/vibe_pyright_json.sh tests/unit/test_vibe_sandbox_operational_contract.py`
  emitted parseable JSON with zero errors.
- `docker build -f Dockerfile.openclaw-sandbox -t openclaw-sandbox-vibe-bootstrap-check .`
  passed.
- Container smoke passed: `pg_dump` reports PostgreSQL 18.4, Node.js is
  present, `npm` is absent, Pyright runs from `/opt/openclaw-venv`, editable
  bootstrap succeeds after `/workspace` mount, and Pyright JSON output parses
  cleanly.

---

## codex/rc-vibe-test-style-only — Dedicated Test Style and Lint RC

Current branch: `codex/rc-vibe-test-style-only`
Base branch: local `main` at `1f19862`.

Purpose:

- Split the mass `ruff format tests` cleanup out of the mixed Vibe Smoke RC so
  reviewers can inspect the style-only churn independently.
- Keep the required golden baseline gate contract fix in this branch because
  unit tests must pass before local merge.

Implemented:

- Renamed the golden baseline ignore test to
  `test_generated_report_dirs_are_ignored_and_baseline_files_are_tracked`,
  making the behavior under test explicit.
- Reworked that test to validate effective Git ignore behavior via
  `git check-ignore --no-index` instead of asserting stale literal
  `.gitignore` strings. `reports/` is accepted as covering generated
  `reports/golden/`, `reports/gateway2/` and `reports/ci/` outputs, while
  official files under `tests/golden/baseline/` remain tracked.
- Ran `uvx ruff check tests --fix`, removing the 14 unused imports reported by
  Vibe Smoke.
- Replaced the ambiguous variable name `l` in
  `tests/unit/test_litellm_infra_scripts.py`.
- Ran `uvx ruff format tests`, applying the dedicated test-formatting pass.

Research notes:

- Git's current `gitignore` documentation confirms a directory pattern matches
  the directory and paths underneath it, so `reports/` covers generated report
  subdirectories.
- Ruff's current linter documentation distinguishes safe fixes from unsafe
  ones; unused-import cleanup is handled by Ruff's safe fix path in ordinary
  test modules.
- Ruff's formatter documentation defines `ruff format --check` as the
  non-writing verification mode for the same formatting contract.

Validation:

- `uvx ruff check tests`: all checks passed.
- `uvx ruff format --check tests`: 234 files already formatted.
- `uv run pyright tests`: 0 errors / 0 warnings.
- `uv run pytest tests/unit`: 1867 passed.
- `uv run pytest tests/integration`: 34 passed / 48 skipped in this local
  host environment.
- `uv run pytest tests/smoke`: 5 passed / 13 skipped.
- `git diff --check`: clean.

Scope intentionally not changed:

- No backend runtime code.
- No `.env`, `.env.*`, secrets, service runtime state or data.
- Existing generated PR-08/PR-09 artifacts remain unstaged.

---

## codex/rc-vibe-minor-recommendations — Vibe Minor Recommendations RC

Current branch: `codex/rc-vibe-minor-recommendations`
Base branch: local `main` at `14e8491`.

Implemented:

- Added `QUIMERA_E2E=true` to `Dockerfile.openclaw-sandbox` as the Vibe
  sandbox umbrella flag for real e2e collection. The project still does not
  commit `.env.sandbox`; all `.env.*` files remain ignored and untouched.
- Updated `tests/e2e/test_agent0_e2e.py` so Agent0 e2e accepts either the
  legacy explicit flag `RUN_AGENT0_E2E=1` or the sandbox umbrella
  `QUIMERA_E2E=true`.
- Added a unit contract guarding that the sandbox Dockerfile and Agent0 e2e
  test both keep the `QUIMERA_E2E` contract.
- Added explicit `TRUNCATE TABLE qlib_projection_manifests CASCADE` to the
  finance roundtrip fixture after migrations. The truncate is scoped to a
  per-test isolated database, preserving production repository create/insert
  semantics while making repeated live test attempts deterministic.
- Hardened the PR-07 JSON status live-shape test to assert stable service
  shape for Postgres, Qdrant, LiteLLM and Ollama while allowing either
  `overall=ok` or `overall=fail`, depending on host/sandbox reachability.

Research notes:

- PostgreSQL 18 documents `TRUNCATE ... CASCADE` as a fast way to empty tables
  and dependent tables, with explicit caution around unintended data loss.
  This RC uses it only in disposable isolated test databases.
- PostgreSQL 18 `INSERT ... ON CONFLICT DO UPDATE` remains available, but was
  not used because it would change repository semantics from create/insert to
  upsert for `qlib_projection_manifests`.
- Python 3.12 subprocess guidance still favors explicit argument sequences and
  `sys.executable` for relaunching the current interpreter; the status test
  keeps that path instead of reviving removed shell JSON subcommands.

Validation:

- `uv run mypy --strict tests/e2e/test_agent0_e2e.py
  tests/integration/test_finance_repository_roundtrip.py
  tests/integration/test_pr07_start_quimera_status_json_live.py
  tests/unit/test_gateway_final_baseline.py`: success.
- `uv run pyright` on the same files: 0 errors.
- `uv run pytest tests/unit/test_gateway_final_baseline.py
  tests/e2e/test_agent0_e2e.py
  tests/integration/test_pr07_start_quimera_status_json_live.py`:
  9 passed / 2 skipped.
- `QUIMERA_E2E=true uv run pytest tests/e2e/test_agent0_e2e.py -q`:
  2 skipped through controlled runtime/corpus guards.
- Live Postgres targeted block with temporary superuser test role:
  `tests/integration/test_finance_repository_roundtrip.py
  tests/integration/test_pr07_start_quimera_status_json_live.py`: 2 passed.
- `git diff --check`: clean.

---

## codex/rc-vibe-integration-roundtrip-status — Vibe Integration Residual RC

Current branch: `codex/rc-vibe-integration-roundtrip-status`
Base branch: local `main` at `df37f51`.

Implemented:

- Made `test_finance_repository_full_roundtrip` use a per-test isolated
  PostgreSQL database via the existing `isolated_postgres_client` helper.
  This preserves insert-only repository semantics while eliminating residual
  `qlib_projection_manifests` unique-key collisions between live test runs.
- Updated the PR-07 live JSON status integration test to call
  `scripts/quimera_status.py status --json` through `sys.executable` with an
  explicit `PYTHONPATH`, instead of invoking the removed
  `scripts/start_quimera.sh status --json` contract.
- Updated the local runtime integration checks to use the canonical wrapper
  contract: `./start_quimera.sh --status`.

Research notes:

- PostgreSQL 18 `INSERT ... ON CONFLICT` could handle duplicate unique keys,
  but was intentionally not used here because the failure is test-state
  leakage and the repository method models create/insert semantics.
- Python 3.12 documents `sys.executable` as the recommended way to relaunch
  the current Python interpreter, which is more portable than shelling through
  a wrapper that has no JSON mode.

Validation:

- `uv run mypy --strict tests/integration/test_finance_repository_roundtrip.py
  tests/integration/test_pr07_start_quimera_status_json_live.py
  tests/integration/test_quimera_local_runtime.py`: success.
- `uv run pyright tests/integration/test_finance_repository_roundtrip.py
  tests/integration/test_pr07_start_quimera_status_json_live.py
  tests/integration/test_quimera_local_runtime.py`: 0 errors.
- Live targeted integration block with temporary superuser test role:
  `tests/integration/test_finance_repository_roundtrip.py
  tests/integration/test_pr07_start_quimera_status_json_live.py
  tests/integration/test_quimera_local_runtime.py`: 3 passed / 1 skipped.
- `uv run pytest tests/unit/test_start_quimera_status_json.py`: 3 passed.
- `git diff --check`: clean.

Scope intentionally not changed:

- No repository method was converted from insert/create to upsert.
- No Docker, Postgres, Qdrant, LiteLLM or Ollama runtime configuration was
  changed.
- No generated PR-08/PR-09 artifacts were staged.

---

## Testes-01 — Qdrant Client Dependency Contract

Current branch: `Testes-01`
Base branch: `main` at `68f5716d37f6f1c421f73db08d7708f8d4709aa7`.

Implemented:

- Relaxed project dependency from `qdrant-client==1.18.0` to the then-current
  open 1.18 floor; this was superseded on 2026-06-25 by the active
  bounded contract `qdrant-client>=1.18,<1.19`.
- Reconciled `uv.lock` metadata offline; the locked package version remains
  `qdrant-client 1.18.0`.
- Updated Qdrant 1.18 version contract, ADR-018 and active Qdrant handoff docs
  to distinguish dependency boundary (`>=1.18,<1.19`) from current lockfile
  resolution (`1.18.0`).
- Updated Qdrant 1.18 unit contracts to reject legacy `qdrant-client==1.13.2`
  while accepting the new `>=1.18,<1.19` dependency boundary.
- Applied Ruff cleanup to `backend/`: `uvx ruff format backend/` reformatted
  65 files and `uvx ruff check --fix backend/` removed 13 unused imports.
- Updated LiteLLM MCP server identifiers from hyphenated names to
  LiteLLM-safe `snake_case` names:
  `quimera_postgres_memory`, `quimera_qdrant_memory` and
  `quimera_working_memory`.
- Updated the LiteLLM MCP transport contract from `streamable_http` to `http`,
  matching the currently installed LiteLLM gateway runtime.
- Started LiteLLM as a host-only local LaunchAgent
  `com.quimera.litellm.local`, bound to `127.0.0.1:4000`, using the rendered
  runtime config from `infra/litellm/generated/litellm_config.runtime.yaml`
  and explicit development placeholder keys. No `.env` or `.env.*` file was
  read.

Validation:

- `.venv/bin/python -m pytest tests/unit/test_qdrant_118_config.py`:
  43 passed.
- `uv lock --check`: success.
- Host import/version check: installed `qdrant-client` is `1.18.0` and
  satisfies the active `>=1.18,<1.19` boundary.
- `uvx ruff check backend/`: success.
- `uvx ruff format --check backend/`: success.
- `uv run mypy --strict backend`: success.
- `uv run pyright backend`: 0 errors / 0 warnings.
- Full host Python 3.12 regression with `.venv/bin/python -m pytest`:
  1891 passed / 65 skipped.
- `git diff --check`: clean.
- `python -m infra.litellm.config_validator infra/litellm/litellm_config.yaml`:
  success; one expected qdrant-semantic fallback warning.
- `.venv/bin/python -m pytest tests/unit/test_litellm_mcp_config_validator.py
  tests/integration/test_pr07_litellm_mcp_registration_smoke.py
  tests/integration/test_pr08_litellm_mcp_tools_live.py
  tests/unit/test_pr08_litellm_mcp_allowed_tools.py
  tests/unit/test_pr08_healthcheck_contract.py`:
  9 passed.
- `bash infra/litellm/test_models.sh`: success.
- LiteLLM readiness: `http://127.0.0.1:4000/health/readiness` returned
  `status=healthy`, `cache=local`, `litellm_version=1.83.14`.
- Gateway chat smoke through `local_chat`: returned `QUIMERA_OK`.
- Gateway embedding smoke through `quimera_embed`: returned a 768-dimension
  float vector.
- `./scripts/start_quimera.sh status --json`: `overall=ok`; LiteLLM host-only,
  Ollama, Postgres 18.4 and Qdrant reported OK.

Qdrant version finding:

- Official Qdrant server release page shows `v1.18.2` as the newest server
  release.
- Official `qdrant-client` PyPI/GitHub release page shows `1.18.0` as the
  newest Python client release.
- PKD-D2P-00Y now accepts Qdrant server/client parity by `1.18.x` family:
  active server target is `qdrant/qdrant:v1.18.2`, Python dependency boundary is
  `qdrant-client>=1.18,<1.19`, and the current lockfile resolution is
  `qdrant-client 1.18.0`.
- Exact server/client patch parity remains diagnostic only
  (`version_exact_parity_ok=false`) while official PyPI client release remains
  `1.18.0`.
- Local runtime observed before container recreation may still report Qdrant
  server `1.18.1`; compose and version contract now point to `1.18.2`.

Scope intentionally not changed:

- No live Qdrant container restart or volume reset.
- No destructive Qdrant operation.
- No project dependency installation. Ruff was executed through `uvx`, not
  added to `pyproject.toml`.
- No generated PR-09 smoke artifact staged.

---

## vibe_code_sandbox — Postgres Extension Runtime Hardening

Current worktree: `/Users/fas/projetos/vibe_code_sandbox`
Branch: `vibe_code_sandbox`
Base: local `main` at `cb0ba17` after merging `Testes-01` runtime contracts.

Implemented:

- Added `infra/postgres/Dockerfile`, a local runtime image derived from
  `postgres:18.4-trixie`.
- The image installs TimescaleDB `2.23.0` and pgvector `0.8.2` from source so
  RAG-01B integration tests can create `timescaledb` hypertables and
  `vector(768)` checkpoint columns without changing PostgreSQL major/minor.
- Updated `docker/docker-compose.postgres.yml` and
  `infra/docker/compose.quimera.local.yml` to build
  `quimera/postgres-memory:18.4-trixie-timescaledb-pgvector`.
- Updated Postgres startup to preload `timescaledb,pg_stat_statements`.
- Updated initdb extension bootstrap to create `pgcrypto`, `timescaledb`,
  `vector` and `pg_stat_statements`.
- Updated working-memory checkpoint SQL to create `vector` before using the
  `vector(768)` type, so existing databases with the extension package
  available can self-heal on schema application.

Scope intentionally not changed:

- No PostgreSQL version change.
- No switch to PostgreSQL 17/15.
- No `postgres:latest`.
- No live volume reset.
- No pg_dump/restore behavior change yet.

### vibe_code_sandbox RC — start_quimera Postgres rebuild hardening

Implemented:

- Refactored `scripts/start_quimera.sh` as the canonical operational entrypoint
  behind the root `./start_quimera.sh` wrapper.
- The script now accepts exactly `--start`, `--stop` and `--status`.
- Postgres image/config drift is detected before start and requires explicit
  human confirmation before rebuild.
- Rebuild preserves data volumes: it uses compose build-or-pull, stop, rm -f
  and up -d for the Postgres service only; no volume removal, compose down -v
  or Docker prune command is present.
- Ollama warmup uses numeric `keep_alive: -1`, matching the official Ollama API
  preload examples and the existing numeric unload `keep_alive: 0` contract.
- `--status` now degrades to a partial host-only table when Docker is not
  available instead of aborting before rendering any status.
- Postgres rebuild now calls `docker compose build` only when the service has a
  Compose `build:` section; external image services use `docker compose pull`.

Validation:

- `bash -n ./start_quimera.sh scripts/start_quimera.sh scripts/star_quimera.sh`:
  success.
- `uv run pytest tests/unit/test_start_quimera_script.py`:
  19 passed.
- `git diff --check`:
  clean.
- `shellcheck` and `ruff` were not executed in this worktree because the tools
  were unavailable and no dependency installation was requested.

### vibe_code_sandbox RC — Vibe integration residual failures

Implemented:

- Updated `Dockerfile.openclaw-sandbox` to install PostgreSQL 18 client tools
  from the official PGDG apt repository and prepend
  `/usr/lib/postgresql/18/bin` to `PATH`, so sandbox `pg_dump` is not older
  than the canonical PostgreSQL 18.4 server.
- Hardened `infra/postgres/backup.sh` and `restore_verify.sh` to prefer
  PostgreSQL tools from the running `quimera-postgres-memory` container when
  available, avoiding host/sandbox client drift.
- Added TimescaleDB logical restore protocol to `restore_verify.sh`:
  `CREATE EXTENSION IF NOT EXISTS timescaledb`,
  `timescaledb_pre_restore()` before `pg_restore`, and
  `timescaledb_post_restore()` after restore.
- Added migration `017_enable_vector_extension.sql` instead of editing older
  applied migrations, preserving checksum immutability while enabling pgvector
  through the migration runner.
- Added isolated live PostgreSQL test database helper for migration tests.
  `test_postgres_migrations.py` and `test_finance_schema_migrations.py` now run
  against per-test temporary databases and clean them up with a guarded
  `quimera_test_` prefix.
- Fixed the finance checksum assertion to compare only finance migrations when
  querying `schema_migrations WHERE version >= '010'`.

Validation:

- Live reproduction block for the four reported failures:
  4 passed.
- Full affected integration files:
  9 passed.
- Static/unit block:
  39 passed.
- `bash -n infra/postgres/backup.sh infra/postgres/restore_verify.sh
  ./start_quimera.sh scripts/start_quimera.sh scripts/star_quimera.sh`:
  success.
- `uv run mypy --strict` on touched test/helper files:
  success.
- `uv run pyright` on touched test/helper files:
  0 errors.
- `git diff --check`:
  clean.

### main RC — Vibe sandbox contract and pg_dump 18.4 verification

Implemented:

- Updated stale tests that still expected removed `scripts/start_quimera.sh`
  subcommands. The canonical wrapper contract is now exactly
  `./start_quimera.sh --start`, `./start_quimera.sh --status` and
  `./start_quimera.sh --stop`.
- Updated `docs/04_MEM/AGENT_CONTEXT.md` to advertise the new wrapper commands
  instead of obsolete JSON subcommands.
- Hardened unit tests that execute gateway/LiteLLM scripts so sandbox
  integration env such as `host.docker.internal` cannot leak into local-only
  unit contracts.
- Updated `infra/litellm/audit.py` so RC-21/RC-23 audit the actual host
  modules (`infra/litellm/audit.py` and `overhead_benchmark.py`) instead of
  requiring removed `start_quimera.sh` subcommands.
- Rebuilt `Dockerfile.openclaw-sandbox` locally as
  `openclaw-sandbox-pg18-check` and verified the sandbox image has
  `pg_dump (PostgreSQL) 18.4 (Debian 18.4-1.pgdg13+1)` and matching
  `psql 18.4`.

Validation:

- `uv run pytest tests/unit`:
  1866 passed.
- Vibe-reported Postgres integration block:
  9 passed.
- `docker build -f Dockerfile.openclaw-sandbox -t openclaw-sandbox-pg18-check .`:
  success.
- `docker run --rm openclaw-sandbox-pg18-check pg_dump --version`:
  PostgreSQL 18.4.
- `docker run --rm openclaw-sandbox-pg18-check psql --version`:
  PostgreSQL 18.4.
- `bash -n` on touched shell scripts:
  success.
- `uv run mypy --strict` on touched Python files:
  success.
- `uv run pyright` on touched Python files:
  0 errors.

---

## RAG-01B PR-10 — Working Memory Qdrant + pgvector Checkpoints

Current branch: `rag-01b/pr-10-working-memory-qdrant-pgvector`
Base branch: `rag-01b/pr-08-integration-smoke` after PR-09 merge commit
`a0870b14d441de9731c84cb3e027ae76fdbb787c`.

Implemented:

- Added accepted ADR-005 in both ADR trees:
  `docs/adr/ADR-005-qdrant-working-memory-pgvector-checkpoints.md` and
  `docs/ADR/ADR-005-qdrant-working-memory-pgvector-checkpoints.md`.
- Added PR-10 SDD and memory handoff:
  `docs/specs/rag-01b/pr-10-working-memory-qdrant-pgvector.md` and
  `docs/04_MEM/WORKING_MEMORY_QDRANT.md`.
- Added `backend/working_memory/` with settings, immutable models, safety
  gates, Qdrant hot store, pgvector checkpoint repository, snapshot service,
  restore service, cleanup and safe metric names.
- Added pgvector checkpoint SQL:
  `infra/postgres/sql/020_working_memory_checkpoints.sql`.
- Added working-memory MCP tools/server on loopback Streamable HTTP
  `127.0.0.1:8813/mcp`.
- Registered `quimera_working_memory` in host LiteLLM config and allowed only
  safe Agentic0 health/query tools by default. Upsert/snapshot are optional
  write tools; restore/cleanup remain disabled by default.
- Added degraded-safe working-memory smoke report:
  `integration/working_memory_smoke.py` and
  `evaluation/results/rag_01b_pr10_working_memory_smoke.json`.

Scope explicitly not changed:

- No Redis, Dragonfly or Python/RAM backend decision.
- No HybridRAG collection mutation.
- No `quimera_query_cache` or `quimera_llm_cache` mutation.
- No pgvector ANN index as hot path.
- No daemon/scheduler/dashboard/provider remoto/real data.
- No `delete_collection` flow for working memory.

Validation:

- PR-10 unit/integration block: 67 passed / 4 skipped.
- PR-10 + LiteLLM/MCP registration block: 75 passed / 4 skipped.
- `uv run mypy --strict` on PR-10 working-memory, MCP, LiteLLM config and
  tests: success.
- `uv run pyright` on the same scope: 0 errors.
- `uv run python -m infra.litellm.config_validator`: success with one expected
  qdrant-semantic fallback warning.
- `uv run python -m integration.working_memory_smoke`: generated skipped safe
  smoke artifact because live stack was not requested.
- `git diff --check`: clean.

Operational note:

- Live Qdrant/Postgres restore tests are opt-in and skip cleanly unless the
  human operator exports the explicit `QUIMERA_TEST_WM_*` variables and a
  test DSN.

### RAG-01B PR-10 RC-01 — Restore Integrity and Host Python 3.12 Gate

Implemented:

- Added `abort_on_checksum_fail` to `RestoreService`. Default remains
  availability-first warn-and-restore; strict operators can now abort restore
  before any point is written when checksum validation fails.
- Replaced module-level `count(1)` snapshot epochs in the real snapshot flow
  with PostgreSQL `MAX(snapshot_epoch) + 1` allocation under an advisory lock
  scoped to `(agent_id, session_id)`, avoiding restart-to-1 behavior and
  cross-process epoch races.
- Documented that `integration/hybrid_fixture.py` uses `delete_collection` only
  for synthetic HybridRAG fixture teardown and not in working-memory runtime.

Validation:

- `.venv/bin/python --version`: Python 3.12.13.
- Required host Python 3.12 unit block:
  68 passed.
- PR-10 focused unit/integration block:
  70 passed / 4 skipped.
- Full host Python 3.12 regression with `.venv/bin/python -m pytest`:
  1891 passed / 65 skipped.
- `uv run mypy --strict` on PR-10 working-memory/MCP/tests:
  success.
- `uv run pyright` on PR-10 working-memory/MCP/tests:
  0 errors / 0 warnings.

---

## RAG-01B PR-09 — Operational Hardening + Smoke CLI

Current branch: `rag-01b/pr-09-operational-hardening-smoke`
Base branch: `rag-01b/pr-08-integration-smoke`

Implemented:

- Added accepted working memory checkpoint ADR:
  `docs/ADR/ADR-004-working-memory-checkpoint-contract.md`.
- Added `docs/04_MEM/WORKING_MEMORY_CONTRACT.md`, explicitly deferring the
  fast working memory backend and accepting pgvector only as durable checkpoint.
- Added PR-09 SDD, recovery runbooks, PostgreSQL backup/restore runbook and
  15-minute agent onboarding doc.
- Added local PostgreSQL backup helpers:
  `infra/postgres/backup.sh`, `restore_verify.sh`, `backup_manifest.py` and
  `backup_config.env.example`.
- Added pg_stat_statements operational config and diagnostics:
  Postgres compose command settings, initdb extension bootstrap,
  `infra/postgres/sql/010_pg_stat_statements_diagnostics.sql` and
  `infra/postgres/pg_stat_report.py`.
- Added working memory checkpoint SQL contract:
  `infra/postgres/sql/011_working_memory_checkpoint_contract.sql`.
- Added PR-09 smoke CLI:
  `./run_smoke.sh` plus `scripts/start_quimera.sh smoke`.
- Added PR-09 smoke summary and manual health report:
  `integration/smoke_summary.py` and `integration/health_report.py`.
- Added conservative latency baseline:
  `baseline/rag01b_latency_baseline.json`.
- Generated PR-09 artifacts:
  `evaluation/results/rag_01b_pr09_smoke_summary.json`,
  `evaluation/results/rag_01b_pr09_health_report.json` and
  `evaluation/results/rag_01b_pr09_pg_stat_report.json`.

Scope explicitly not changed:

- No final fast working memory backend selected.
- No Redis implementation.
- No Qdrant in-memory implementation.
- No Python vector memory implementation.
- No cloud/offsite backup, PITR, replication or dashboard.
- No provider remoto.
- No `down -v`, `docker system prune` or volume deletion.
- No destructive schema migration.

Validation:

- PR-09 unit block: 21 passed.
- PR-09 integration block: 3 passed / 2 skipped.
- PR-08 + PR-09 focused block: 51 passed / 3 skipped.
- Full regression: 1816 passed / 60 skipped.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `bash -n run_smoke.sh infra/postgres/backup.sh infra/postgres/restore_verify.sh scripts/start_quimera.sh`: clean.
- `./run_smoke.sh --quick --json --no-build --timeout 5 --allow-degraded`:
  generated PR-09 smoke summary with `overall=degraded` because LiteLLM was
  unavailable while local Postgres/Qdrant/Ollama healthchecks were OK.

Operational note:

- Live backup/restore and live pg_stat integration tests skipped because no
  Postgres DSN was exported in the shell. The static contract, scripts,
  manifest logic and degraded reports are covered locally.

### RAG-01B PR-09 RC-01 — Integration + Diagnostic Final Closure

Implemented:

- Hardened `integration/smoke_summary.py::render_summary_table` so service
  values can be either strings (`"ok"`, `"fail"`) or dictionaries with
  `status`.
- Added `status` as a compatibility alias for the canonical smoke-summary
  `overall` field, and documented that contract in the PR-09 SDD.
- Refactored PR-09 live subprocess tests to invoke modules with
  `sys.executable` and explicit `PYTHONPATH`, avoiding `uv run` inside
  mounted review sandboxes.
- Added a PR-09 GitHub Actions workflow that runs the required unit contracts
  on Python 3.12 inside `.venv`.
- Added an explicit irreversible-data-loss warning around manual
  `docker volume rm` reset instructions in `infra/README.md`.
- Regenerated PR-09 health and smoke summary artifacts with the new
  `status == overall` contract.

Validation:

- PR-09 focused block: 28 passed / 2 skipped.
- Full regression: 1819 passed / 61 skipped.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `bash -n run_smoke.sh infra/postgres/backup.sh infra/postgres/restore_verify.sh scripts/start_quimera.sh`: clean.
- `git diff --check`: clean.

---

## RAG-01B PR-08 — Agentic0 End-to-End System Integration Smoke

Current branch: `rag-01b/pr-08-integration-smoke`

Implemented:

- Added deterministic PR-08 integration package under `integration/` with:
  Agentic0 smoke contracts, LiteLLM-only Agentic0 client, integration health
  report, synthetic HybridRAG fixture, safe report writer and CLI smoke runner.
- Added PR-08 documentation:
  `docs/specs/rag-01b/pr-08-agentic0-integration-smoke.md`,
  `docs/rag/rag_01b_pr08_integration_report.md`, and
  `docs/references/llm_harness_original_papers.md`.
- Updated `docs/04_MEM/AGENT_CONTEXT.md` with final RAG-01B integration state,
  service responsibility map, Level 0/local-only policy and PR-08 commands.
- Added Agentic0 virtual-key/tool policy to host LiteLLM config and validator.
  Allowed tools are explicit; wildcard and destructive tools are rejected.
- Extended `scripts/start_quimera.sh` with:
  `integration-health`, `mcp-status`, `agentic0-smoke`, `pr08-report`, and
  `rag01b-final-gate`.
- Added PR-08 unit and integration tests for Agentic0 contracts, health,
  HybridRAG, MCP registration, no direct backend shortcuts, safe artifacts,
  OTel trace safety, degraded-service behavior, latency reporting and final
  closeout docs.
- Generated PR-08 artifacts:
  `evaluation/results/rag_01b_pr08_agentic0_smoke_summary.json`,
  `evaluation/results/rag_01b_pr08_integration_health.json`, and
  `evaluation/results/rag_01b_pr08_latency_summary.json`.

Scope explicitly not changed:

- No LiteLLM Docker service.
- No remote provider fallback.
- No Agentic0 direct Qdrant/Postgres/Ollama access.
- No destructive Qdrant/Postgres operations outside guarded test-prefix
  cleanup helpers.
- No raw prompt, answer, chunk, document text, vector, embedding, secret or DSN
  stored in PR-08 artifacts.

Validation:

- `bash -n scripts/start_quimera.sh`: clean.
- `uv run python -m infra.litellm.config_validator`: success with one expected
  qdrant-semantic policy warning.
- PR-08 focused block: 23 passed / 1 skipped.
- Full regression: 1787 passed / 59 skipped.
- `uv run mypy --strict` on PR-08 modules/tests and LiteLLM validator:
  success.
- `uv run pyright` on PR-08 modules/tests and LiteLLM validator: 0 errors.
- `uv run python -m integration.run_agentic0_smoke_test --json --allow-degraded`:
  generated safe artifacts with status `skipped` because the local stack had
  LiteLLM/Qdrant/Postgres down while Ollama was OK.

Operational note:

- Live end-to-end Agentic0 synthesis should be rerun after starting the full
  local stack with LiteLLM host gateway, Qdrant and Postgres. The degraded
  result is intentional and safe; it verifies no shortcut path bypasses LiteLLM.

### RAG-01B PR-08 RC-01 — Reviewer Risk Closure

Implemented:

- HybridRAG artifacts now explicitly mark Recall@5 as
  `offline_synthetic_fixture`, require live local validation, and distinguish
  deterministic RRF fixture evidence from real `nomic-embed-text` quality.
- `json_has_no_forbidden_fields` now delegates to the AST-aware field scanner,
  so audit flags such as `secrets_seen` do not trigger false positives while
  unsafe field names remain blocked.
- `rag01b-final-gate` no longer interpolates JSON into a Python heredoc. It
  writes status, integration-health and smoke JSON to temporary files and loads
  them by path.
- Latency artifacts now include `measurement_mode`, `sample_count` and
  `p95_warning`. Offline/degraded runs set `p95_ms=null` with
  `not_measured_stack_unavailable`; live p95 over 500ms emits
  `p95_exceeds_500ms`.
- `scripts/quimera_status.py` now captures LiteLLM and Ollama healthcheck
  latency, and integration health includes safe per-service latency metadata.

Validation:

- PR-08 focused RC block: 27 passed / 1 skipped.
- Full regression: 1791 passed / 59 skipped.
- `uv run mypy --strict` on PR-08 modules/tests and status script: success.
- `uv run pyright` on PR-08 modules/tests and status script: 0 errors.
- `bash -n scripts/start_quimera.sh`: clean.
- `git diff --check`: clean.

---

## RAG-01B PR-07 — Benchmark + ADR + MCP Memory Gate

Current branch: `rag-01b/pr-07-benchmark-adr-mcp-memory`

Implemented:

- Added deterministic benchmark harness and artifacts:
  `evaluation/results/rag_01b_session_benchmark_summary.json` and
  `evaluation/results/rag_01b_session_benchmark_rows.csv`.
- Added accepted backend decision ADR:
  `docs/ADR/ADR-003-memory-backend-decision.md`.
- Added PR-07 SDD and benchmark result documentation.
- Added FastMCP-based local memory servers:
  `backend/mcp/postgres_memory_server.py` and
  `backend/mcp/qdrant_memory_server.py`, with loopback-only ports 8811/8812
  and guarded tool inputs.
- Registered MCP servers in host LiteLLM config and hardened the config
  validator for loopback URL, port and transport policy.
- Wired OTel decorators into embedding, retrieval, RRF, cache and selected
  Postgres repository paths, and added benchmark probes for embed, retrieval,
  RRF, rerank, cache, pg_read and pg_write spans.
- Added `scripts/quimera_status.py` plus `start_quimera.sh status --json` and
  `rag01b-acceptance --json`.
- Hardened LiteLLM host-only policy: `start_litellm.sh` refuses to reuse a
  running `quimera-litellm` Docker container, and status JSON reports that
  violation explicitly.
- Closed PR-01/PR-02 reviewer gaps with opt-in integration tests for
  concurrent agent-state/turn writes, market-bar concurrency, and real
  pg_indexes checks.
- Added `fastmcp` dependency for the local MCP memory layer.

Validation:

- PR-07 focused unit block: 35 passed.
- PR-07 focused integration block: 5 passed / 7 skipped.
- Full unit suite: 1739 passed.
- Full regression: 1763 passed / 58 skipped.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `uv run python -m infra.litellm.config_validator`: success with one expected
  qdrant-semantic policy warning.
- `./scripts/start_quimera.sh rag01b-acceptance --json`: `overall=ok`.
- `git diff --check`: clean.

Operational note:

- Local status currently reports `overall=fail` because Postgres and Qdrant are
  not running and a legacy `quimera-litellm` Docker container is active. This is
  now detected as a host-only violation instead of being silently reused.

---

## RAG-01B PR-07 RC-01 — Review Sandbox and Decision Hardening

Current branch: `rag-01b/pr-07-benchmark-adr-mcp-memory`

Implemented:

- Refactored `test_start_quimera_status_json.py` subprocess checks to invoke
  `scripts/quimera_status.py` with `sys.executable` and explicit `PYTHONPATH`,
  avoiding `uv run` in sandbox-mounted review environments.
- Added `degraded` to MCP `ToolResponse`; Postgres MCP read tools now mark
  responses as degraded when no DSN/backend is configured, and write-enabled
  calls fail explicitly with `postgres backend unavailable`.
- Added `sprint: RAG-01B` to benchmark summary JSON and regenerated benchmark
  JSON/CSV artifacts.
- Clarified `llm_response_cache` decision as `qdrant` in benchmark decisions,
  ADR-003 and benchmark docs. LiteLLM remains gateway/manager, not the
  canonical storage backend.
- Updated PR-07 SDD OTel notes to reflect real retrieval/RRF instrumentation.

Validation:

- RC focused tests: 15 passed.
- Full unit suite: 1740 passed.
- Full regression: 1764 passed / 58 skipped.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `./scripts/start_quimera.sh rag01b-acceptance --json`: `overall=ok`.

---

## RAG-01B PR-06 — OpenTelemetry Base Layer

Current branch: `rag-01b/pr-06-otel-base-layer`
Base branch: `rag-01b/pr-05b-litellm-host-audit` while PR-05B remains open.
Draft PR: <https://github.com/franciscosalido/OPENCLAW/pull/113>

Implemented:

- Added `backend/observability/` base package with OTel tracing setup,
  idempotent asyncpg instrumentation, safe attributes, PII/content guards,
  contextvars, events, metrics and async-only decorators.
- Added LiteLLM OTel callback guard and source YAML callback settings:
  `litellm_settings.callbacks: ["otel"]` plus
  `callback_settings.otel.message_logging: false`.
- Added `scripts/start_quimera.sh otel-doctor` and `otel-doctor --json`.
- Added `.env.observability.example` and PR-06 SDD.
- Added OTel dependencies:
  `opentelemetry-api`, `opentelemetry-sdk`,
  `opentelemetry-exporter-otlp-proto-http`,
  `opentelemetry-instrumentation-asyncpg`.

Scope explicitly not changed:

- No full RAG runtime instrumentation.
- No dashboard, collector, Grafana, Tempo, Jaeger or Prometheus service.
- No MCP server, FastAPI, REST API or gRPC.
- No PostgreSQL/Timescale schema change.
- No Qdrant collection change.
- No LiteLLM Docker service.

Validation:

- PR-06 focused OTel tests: 39 passed.
- LiteLLM/start-script compatibility block: 58 passed.
- Full unit suite: 1707 passed.
- Full regression: 1726 passed / 51 skipped.
- Focused post-typing block: 52 passed / 2 skipped.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `bash -n scripts/start_quimera.sh`: clean.
- `uv run python -m infra.litellm.config_validator`: success with one expected
  qdrant-semantic policy warning.
- `./scripts/start_quimera.sh otel-doctor --json`: status `ok`.
- `git diff --check`: clean.

Handoff to PR-07:

- Wire decorators into selected RAG/Gateway execution paths.
- Decide optional collector/profile strategy.
- Keep content capture disabled unless a future ADR explicitly changes the
  privacy boundary.

---

## RAG-01B PR-06 RC-01 — OTel SemConv and Test Marker Cleanup

Current branch: `rag-01b/pr-06-otel-base-layer`
Draft PR: <https://github.com/franciscosalido/OPENCLAW/pull/113>

Implemented:

- `traced_pg` now emits current OTel DB semconv attributes for PostgreSQL:
  `db.system.name=postgresql`, `db.operation.name` and `db.collection.name`,
  while preserving `quimera.pg_table`, `quimera.pg_operation` and
  `latency.pg_ms`.
- Added public metric name constants for the GenAI and retrieval histograms.
- Added `pytest.mark.integration` to all PR-06 OTel integration tests, so
  `pytest -m integration` includes them.
- Hardened `traced_mcp_tool`: validates low-cardinality tool/method names,
  stores tool name as `gen_ai.tool.name`, and keeps span name based on
  `mcp.method.name` rather than raw tool name.

Validation:

- RC focused block: 17 passed.
- `pytest -m integration` on OTel integration tests: 3 passed.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `uv run pytest`: 1730 passed / 51 skipped.
- `git diff --check`: clean.

---

## RAG-01B PR-05B — LiteLLM Host Audit and Hardening

Current branch: `rag-01b/pr-05b-litellm-host-audit`
Issue: <https://github.com/franciscosalido/OPENCLAW/issues/110>

Implemented:

- LiteLLM source config normalized to `os.environ/OLLAMA_BASE_URL`.
- Added canonical aliases `qwen3-local`, `qwen3:14b` and `nomic-embed-text`
  while preserving legacy Gateway/Agentic aliases.
- Embedding aliases now use timeout/stream timeout `5/5`; chat remains
  `120/45`; global request timeout remains `165`.
- Added `infra/litellm/audit.py` for safe JSON/Markdown audit reports.
- Added `infra/litellm/version_fingerprint.py` for best-effort local version
  collection with sanitized DSNs and structured warnings.
- Added `infra/litellm/overhead_benchmark.py`; live benchmark is opt-in via
  `QUIMERA_LITELLM_BENCHMARK=1`.
- Reworked `infra/litellm/start_litellm.sh` to start one host process,
  reuse readiness, write `.runtime/litellm.pid`, use `--num_workers 1`, and
  wait on `/health/readiness`.
- Added `scripts/start_quimera.sh` subcommands: `litellm-audit`,
  `litellm-fingerprint`, `litellm-benchmark`.
- Added PR-05B SDD at
  `docs/specs/rag-01b/pr-05b-litellm-host-audit.md`.

Scope explicitly not changed:

- No LiteLLM Docker service.
- No MCP server, FastAPI or gRPC.
- No HybridRAG mutation.
- No PostgreSQL/Timescale migrations or schema changes.
- No Qdrant collection deletion/recreate.
- No remote providers or model downloads.

Validation so far:

- PR-05B focused unit block: 58 passed.
- LiteLLM/Gateway/Agentic focused block: 160 passed / 95 subtests passed.
- All `tests/unit/test_litellm*.py` + start script tests: 78 passed /
  8 subtests passed.
- Full unit suite: 1669 passed / 256 subtests passed.
- Full regression: 1685 passed / 51 skipped / 259 subtests passed.
- `uv run mypy --strict` on `infra/litellm/*` PR-05B modules: success.
- `uv run pyright` on `infra/litellm/*` PR-05B modules: 0 errors.
- `bash -n` on `scripts/start_quimera.sh` and
  `infra/litellm/start_litellm.sh`: clean.
- `uv run python -m infra.litellm.config_validator`: success with one expected
  qdrant-semantic policy warning.
- `uv run python -m infra.litellm.render_config`: success, fallback local.
- `uv run python -m infra.litellm.audit`: generated JSON/Markdown, status
  `warn` due expected local-service/experimental warnings.
- `uv run python -m infra.litellm.overhead_benchmark`: `SKIPPED_VALID` without
  opt-in.

---

## RAG-01B PR-05B RC-01 — Residual Risk Cleanup

Current branch: `rag-01b/pr-05b-litellm-host-audit`
PR: <https://github.com/franciscosalido/OPENCLAW/pull/111>

Implemented RC-01 fixes:

- RC-09 audit `warn` remains intentional when source YAML declares
  `qdrant-semantic` and the experimental flag is not set; SDD/README now state
  that fallback local is valid runtime behavior.
- `local_json` keeps `timeout=60` and `stream_timeout=45`; SDD/README now
  document the first-chunk tradeoff and recommend concise JSON contexts.
- `version_fingerprint` now exposes `python_version` and `python_executable`
  directly from the running interpreter, independent of command probe failures.
- `overhead_benchmark` keeps `status=SKIPPED_VALID` and now also emits
  `skipped=true` for compatibility with reviewer expectations.

Validation:

- RC-01 focused tests: 19 passed.
- LiteLLM/start-script block: 80 passed / 8 subtests passed.
- Gateway/Agentic focused block: 92 passed / 87 subtests passed.
- PR-05B opt-in integrations without env flags: 5 skipped.
- Full unit suite: 1671 passed / 256 subtests passed.
- `uv run mypy --strict` on RC-01 touched LiteLLM modules: success.
- `uv run pyright` on RC-01 touched LiteLLM modules: 0 errors.
- `uv run python -m infra.litellm.version_fingerprint`: success; includes
  `python_version` and `python_executable`.
- `uv run python -m infra.litellm.overhead_benchmark`: `SKIPPED_VALID` with
  `skipped=true`.
- `uv run python -m infra.litellm.audit`: generated JSON/Markdown, status
  `warn` by design.

---

## RAG-01B PR-05 RC-01 — LiteLLM Host Hardening

Current branch: `rag-01b/pr-05-litellm-host-cache-timeout`
PR: <https://github.com/franciscosalido/OPENCLAW/pull/109>

Implemented RC-01 fixes:

- Raised chat alias `stream_timeout` from 15s to 45s for local Qwen slow-start
  safety.
- Raised global `request_timeout` to 165s so it covers 120s model timeout plus
  45s stream slow-start budget.
- Centralized embedding dimension in `CANONICAL_EMBED_DIM = 768` and validates
  the semantic-cache vector size against it.
- `start_quimera.sh` now warns when the local placeholder
  `LITELLM_MASTER_KEY=quimera-dev-key-change-me` is still used.
- `litellm-stop` sends SIGTERM to only the owned PID and escalates to SIGKILL
  only for that same PID after a grace loop.
- Runtime YAML render now uses `allow_unicode=True`.

Validation:

- RC focused tests: 33 passed.
- PR-05/Gateway focused block: 110 passed / 3 skipped / 65 subtests passed.
- Full unit suite: 1649 passed / 253 subtests passed.
- Full regression: 1666 passed / 47 skipped / 256 subtests passed.
- `bash -n` on changed shell scripts: clean.
- `./scripts/start_quimera.sh litellm-validate`: success.
- `uv run python -m infra.litellm.render_config`: success with
  `cache_backend=local`.
- Production scan: no LiteLLM Docker image/service, no Qdrant container URL,
  no `pkill litellm`, no `killall litellm`, no `down -v`.
- `git diff --check`: clean.

---

## RAG-01B PR-05 — LiteLLM Host Cache + Timeout Hardening

Current branch: `rag-01b/pr-05-litellm-host-cache-timeout`

Architectural correction:

- LiteLLM is a host Python process, not a Docker Compose service.
- Docker Compose manages only Postgres and Qdrant.
- `scripts/start_quimera.sh` reuses a ready host LiteLLM at
  `http://127.0.0.1:4000` or starts exactly one host process tracked by
  `.runtime/litellm.pid`.
- The PR-04 memory line saying Compose managed `quimera-litellm` is superseded
  by this PR-05 correction.

Implemented:

- Removed `litellm`/`quimera-litellm` from
  `infra/docker/compose.quimera.local.yml`.
- Added host LiteLLM commands to `scripts/start_quimera.sh`:
  `litellm-validate`, `litellm-render`, `litellm-start`, `litellm-stop`,
  `litellm-restart`, `litellm-smoke`.
- Added `infra/litellm/config_validator.py`,
  `infra/litellm/render_config.py` and `infra/litellm/smoke_test.py`.
- Added Qdrant semantic-cache source config with safe local fallback in the
  generated runtime config.
- Added tests guarding against LiteLLM returning to Compose.

Validation:

- Focused PR-05/Gateway block: 103 passed / 3 skipped / 65 subtests passed.
- Full unit suite: 1642 passed / 253 subtests passed.
- Full regression: 1659 passed / 47 skipped / 256 subtests passed.
- `docker compose -f infra/docker/compose.quimera.local.yml config --services`:
  `postgres-memory`, `qdrant`.
- `bash -n` on changed shell scripts: clean.
- `git diff --check`: clean.

---

## RAG-01B PR-04 RC-01 — Compose Env Guard + Volume Reset Docs

Current branch: `rag-01b/pr-04-ollama-tuning`
Draft PR: <https://github.com/franciscosalido/OPENCLAW/pull/108>

Implemented RC-01 fixes:

- `infra/docker/compose.quimera.local.yml` now requires `LITELLM_MASTER_KEY`
  through Docker Compose required interpolation and fails fast when missing.
- Added `.env.local.example` with a local placeholder key and Ollama defaults.
- Added `infra/README.md` documenting the local env contract and manual volume
  reset procedure.
- SDD now states that `restart` preserves volumes and corrupted-volume reset is
  manual/operator-owned via `docker volume rm`.

Validation:

- PR-04 unit tests: 28 passed.
- Compose config with placeholder key: success.
- Compose config without `LITELLM_MASTER_KEY`: fails as expected with an
  actionable message.
- Full unit suite: 1618 passed / 253 subtests passed.
- PR-04 optional integration: 1 passed / 2 skipped cleanly.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `git diff --check`: clean.

---

## RAG-01B PR-04 — Ollama Tuning + Keep-Alive Hardening

Current branch: `rag-01b/pr-04-ollama-tuning`
Base: `main` after PR-03 merge.

PR-03 was merged through GitHub:

- PR: <https://github.com/franciscosalido/OPENCLAW/pull/106>
- Merge commit: `3fe71d53460e00f68fbeb1df9821f4b8599a9ad6`
- `main...origin/main`: `0 0` after pull/prune.
- Local Git inconsistency fixed: `branch.main.rebase=false` and
  `pull.rebase=false` so `git pull --ff-only` no longer attempts rebase.

PR-04 implemented locally:

- `scripts/start_quimera.sh` controller with start/stop/restart/status/logs/
  doctor/test/warmup/release.
- Root `start_quimera.sh` and `scripts/star_quimera.sh` compatibility wrappers.
- `infra/ollama` config, warmup and shutdown/release hooks.
- `infra/docker/compose.quimera.local.yml` for `quimera-postgres-memory`,
  `quimera-qdrant` and `quimera-litellm`.
- `docs/specs/rag-01b/pr-04-ollama-tuning-keepalive.md`.

Validation:

- PR-04 unit tests: 25 passed.
- Controller self-test: 25 passed.
- Full unit suite: 1615 passed / 253 subtests passed.
- PR-04 optional integration: 1 passed / 2 skipped cleanly.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `bash -n` on shell wrappers: clean.
- YAML parse check: clean.
- `git diff --check`: clean.

Explicitly not implemented: schema SQL, HybridRAG changes, MCP/API/gRPC,
Kronos, Qlib, pgvector logic, model auto-pull or performance tests.

---

## RAG-01B PR-03 RC-02 — Corrupted Cache Payload Handling

Current branch: `rag-01b/pr-03-hybridrag-cache-qdrant`
PR: <https://github.com/franciscosalido/OPENCLAW/pull/106>

Implemented RC-02 fixes:

- `CacheLayer.lookup` now treats corrupted Qdrant cache payload as a safe cache
  miss, logs `cache_lookup_bad_payload_skipped` at DEBUG, and returns `None`.
- Added unit coverage proving corrupted cache payload does not raise
  `CachePayloadError` to callers.
- `hmac_query_hash` docstring now explicitly warns never to log `query_text`
  alongside the returned hash.

Validation:

- `test_cache_layer.py`: 9 passed.
- `test_cache_fingerprint.py`: 8 passed.
- PR-03 + observability focused tests: 52 passed.
- Full unit suite: 1590 passed / 253 subtests passed.
- Live Qdrant integration with `TEST_QDRANT_URL=http://127.0.0.1:6333`: 3 passed.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `git diff --check`: clean.
- Cache module scope scans: no forbidden imports or destructive collection calls.

---

## RAG-01B PR-03 Review Gate

Current branch: `rag-01b/pr-03-hybridrag-cache-qdrant`
PR: <https://github.com/franciscosalido/OPENCLAW/pull/106>
Status: ready for review, not merged.

Rito status:

- Local branch pulled with `--ff-only`: already up to date.
- Local Qdrant checked healthy at `http://127.0.0.1:6333`.
- Live Qdrant integration now executed with
  `TEST_QDRANT_URL=http://127.0.0.1:6333`: 3 passed.
- PR was converted from draft to ready for review.
- Merge/prune are blocked until COWORK/human approval.

---

## RAG-01B PR-03 RC-01 — Semantic Cache Hardening

Current branch: `rag-01b/pr-03-hybridrag-cache-qdrant`
Draft PR: <https://github.com/franciscosalido/OPENCLAW/pull/106>

Implemented RC-01 fixes:

- `CacheSettings` now rejects `collection_name == source_collection`.
- `invalidate_by_schema_version` rejects empty/blank version values.
- `invalidate_by_corpus_epoch` rejects empty/blank corpus epoch values.
- `test_rag_observability_config` no longer writes to a fixed file under
  `tests/`; it uses an isolated temporary directory, resolving the pre-existing
  PermissionError/carry-over artifact risk.
- `hmac_query_hash` is documented as a caller-side helper whose raw query input
  must never be persisted; only the returned hash may be stored.
- `record_hit` remains best-effort but now emits a safe DEBUG log on failure.

Validation:

- RC focused tests: 37 passed.
- PR-03 + observability focused tests: 51 passed.
- Full unit suite: 1589 passed / 253 subtests passed.
- Optional Qdrant integration tests: 3 skipped cleanly when live integration env
  is not set.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `git diff --check`: clean.

---

## RAG-01B PR-03 — HybridRAG Semantic Cache Layer (Qdrant)

Current branch: `rag-01b/pr-03-hybridrag-cache-qdrant`
Draft PR: <https://github.com/franciscosalido/OPENCLAW/pull/106>
Implementation series: `414bf28..HEAD` on the draft PR branch.

Local and remote branch are aligned (`HEAD...origin/rag-01b/pr-03-hybridrag-cache-qdrant`
is `0 0`).

Implemented:

- SDD for PR-03 semantic retrieval cache.
- `backend/rag/cache/*` settings, models, fingerprint helpers, Qdrant collection
  manager, async `CacheLayer`, errors and shared types.
- Unit tests with fake Qdrant clients.
- Optional live Qdrant integration tests guarded by environment configuration.

Validation:

- PR-03 focused unit tests: 44 passed.
- Optional Qdrant integration tests: 3 skipped cleanly when live integration env
  is not set.
- Full unit suite: 1587 passed / 253 subtests passed.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `git diff --check`: clean.

Explicitly not implemented in PR-03: response cache, raw query/prompt/final
answer/full chunk storage, LLM calls, embedding generation, MCP/API/gRPC,
PostgreSQL/TimescaleDB changes, Qdrant knowledge collection mutation or ORM.

---

## RAG-01B PR-01 RC-02 — PostgreSQL 18.4 Canonical Memory Base

Current branch: `rag-01b/pr-01-postgres-session-schema`

Local-only review state:

- ADR-0021 accepts PostgreSQL 18.4 as the canonical relational-temporal memory
  version.
- Docker Compose pins `postgres:18.4-trixie`.
- PostgreSQL local auth uses `POSTGRES_PASSWORD_FILE` with a non-versioned
  password file under `infra/postgres/secrets/`.
- PostgreSQL 18+ storage layout is explicit: volume mount
  `/var/lib/postgresql`, internal `PGDATA=/var/lib/postgresql/18/docker`.
- PKD-00X documents the QUIMERA MCP Memory Fabric over LiteLLM as the future
  memory access architecture. No MCP runtime was implemented in RC-02.
- PostgreSQL 16 was the previous blueprint reference and is superseded by
  ADR-0021.

No benchmark, migration, SQL schema change or version-selection test was added
for this decision.

## RAG-01B PR-01 RC-03 — Janus Temporal Memory Fabric

Current branch: `rag-01b/pr-01-postgres-session-schema`

Local-only review state:

- ADR-0021 now includes a TimescaleDB addendum.
- ADR-0022 accepts PostgreSQL 18.4 + TimescaleDB as the single temporal memory
  source of truth for agentic memory, financial time series, Qlib projections
  and Kronos forecasts.
- Qlib is a derived compatibility projection, not canonical storage.
- Kronos has no separate persistent memory.
- Blueprint V3.0 now includes the QUIMERA Janus Temporal Memory Fabric section.

No TimescaleDB runtime, Docker image change, SQL extension, hypertable, schema,
Qlib adapter, Kronos adapter or MCP tool was implemented in RC-03.

---

## Stack State — 2026-05-27

Stack local completamente verificado e funcional. Ver `docs/04_MEM/QUIMERA_STACK_RUNBOOK.md`.

| Serviço  | Status | Versão / Detalhe                              |
|----------|--------|-----------------------------------------------|
| Qdrant   | ✅ UP  | v1.18.1, 4 collections presentes              |
| Ollama   | ✅ UP  | nomic-embed-text:latest (0.27GB) + qwen3:14b (9.28GB) |
| LiteLLM  | ✅ UP  | 4 aliases chat saudáveis, embedding falso-positivo no health check (ver BUG 1) |

**Fixes aplicados em `start_quimera.sh`:**
1. `/health` → `/health/liveliness` em todas as verificações LiteLLM (3 ocorrências + modo `--status`)
2. Adicionado export de `LITELLM_LOCAL_CHAT_MODEL` e `LITELLM_LOCAL_EMBED_MODEL` no fallback sem iTerm2
3. iTerm2 path: variáveis derivadas incluídas no `LITELLM_TAB_CMD`

**Problema residual conhecido (não-bloqueante):** LiteLLM reporta `unhealthy_count: 2` para `quimera_embed`/`local_embed` porque o health check interno usa `/api/generate` mas `nomic-embed-text` só aceita `/api/embed`. Os embeddings reais funcionam perfeitamente (768d verificado). Ver BUG 1 no runbook.

---

---

## Active Sprint: Agent-0 / CLI and Readiness

**Goal:** expose the first stable public Agent-0 interface,
`OpenClaw.ask(question) -> Answer`, plus a local CLI, readiness checks,
opt-in E2E SLO gates, sanitized reports and rollback docs.

Current branch: `feat/agent0-cli-and-readiness`
Current issue: <https://github.com/franciscosalido/OPENCLAW/issues/82>

A0-PR05 starts after A0-PR04 and closes the Agent-0 MVP sprint surface. It
does not add multi-agent orchestration, FastAPI, MCP, UI, remote providers,
remote fallback, new ingestion, reindexing or Qdrant mutation in readiness.

```text
question
  -> OpenClaw.ask
  -> deterministic domain routing
  -> existing local RAG path when route == local_rag
  -> frozen Answer with metadata-only citations
  -> CLI / sanitized E2E report
```

Current runtime path:

```text
OpenClaw / runtime generation
  -> LiteLLM at http://127.0.0.1:4000/v1
  -> Ollama / Qwen local
```

Current controlled embedding path:

```text
RagEmbedder factory
  -> gateway_litellm
  -> GatewayEmbedClient
  -> LiteLLM at http://127.0.0.1:4000/v1/embeddings
  -> quimera_embed
  -> Ollama / nomic-embed-text local
```

Rollback embedding path:

```text
RagEmbedder factory
  -> direct_ollama
  -> OllamaEmbedder
  -> Ollama direct at http://127.0.0.1:11434/api/embed
```

GW-07 proves the current RAG E2E path without migrating embeddings:

```text
synthetic docs
  -> chunking
  -> OllamaEmbedder direct at http://127.0.0.1:11434/api/embed
  -> Qdrant temporary collection gw07_synthetic_rag_<short_uuid>
  -> Retriever / ContextPacker / PromptBuilder
  -> LocalGenerator / GatewayChatClient
  -> LiteLLM at http://127.0.0.1:4000/v1/chat/completions
  -> Ollama / Qwen local
```

Hard constraints remain:

- Local only.
- No remote providers.
- No FastAPI.
- No MCP.
- No quant tools.
- No secrets or real portfolio data.
- No `openclaw_knowledge` mutation in verify-only.
- No Qdrant mutation unless `--commit` is explicit and a future writer is wired.
- No arbitrary collection override for dual corpus bootstrap.
- No answer generation in A0-PR03 golden question harness or A0-PR04 routing.
- No LLM-as-judge.
- No Qdrant mutation or live Qdrant requirement in A0-PR03 unit tests.
- No LLM classifier, embeddings, rerankers, remote providers or live Qdrant
  dependency in A0-PR04 classifier/routing unit tests.
- No Qdrant mutation, reindexing or bootstrap in A0-PR05 readiness checks.
- A0-PR05 E2E is opt-in only via `RUN_AGENT0_E2E=1`; unit tests remain offline.
- A0-PR05 reports must not serialize prompt, question text, answer text, chunks,
  vectors, embeddings, payloads, headers, secrets, raw exceptions or tracebacks.
- No final local merge into `main`; GitHub PR approval is the integration path.

## A0-PR05 Current Work

A0-PR05 adds the final Agent-0 MVP public/readiness surface:

- `backend/agent0/openclaw.py` with `OpenClaw.ask(...)` and frozen `Answer`.
- `scripts/openclaw.py` with `ask` command and safe JSON/human output.
- `scripts/check_agent0_readiness.py` with idempotent local readiness checks.
- `backend/agent0/e2e_report.py` with sanitized E2E SLO report builder.
- `tests/e2e/test_agent0_e2e.py`, guarded by `RUN_AGENT0_E2E=1`.
- `docs/AGENT0_RUNBOOK.md` and `docs/AGENT0_ROLLBACK.md`.

Rules:

- `OpenClaw.ask` must reuse existing routing, citation and RAG components; do
  not duplicate the pipeline in the public API wrapper.
- CLI must call `OpenClaw.ask`, support `--json`, avoid tracebacks by default
  and never print prompt/chunks/vectors/payloads/secrets.
- Readiness checks verify Qdrant reachability/collections, local LiteLLM,
  Ollama models, aliases, remote routing disabled, corpus manifests and golden
  questions. They do not mutate Qdrant or bootstrap collections.
- E2E SLO gate is opt-in and expects already-bootstrapped
  `openclaw_internal` / `openclaw_financial`.
- Final SLOs: E2E p95 < 15s and citation hit rate >= 5/6 on the six golden
  questions when local services and corpora are available.
- Rollback deletes only `openclaw_internal` and `openclaw_financial`; never
  delete `openclaw_knowledge`.
- Validation on Python 3.12.13:
  `pytest -v` 561 passed / 9 skipped / 217 subtests passed,
  `mypy --strict .` 0 errors, `pyright` 0 errors, smoke 5 passed / 7 skipped.
- Optional live check status: CLI returns a sanitized local auth failure when
  local gateway credentials are absent; readiness reported 7/9 with only
  Agent-0 Qdrant collections missing in this local environment.

---

## Mandatory GitHub Workflow

For every tracked task:

1. Sync local `main` with GitHub.
2. Open or update a GitHub Issue before implementation.
3. Create a feature branch from updated `main`.
4. Implement locally.
5. Run validation locally.
6. Commit atomic changes.
7. Push the feature branch.
8. Open a GitHub PR to `main`.
9. Link the PR to the issue.
10. Address review on the same branch.
11. Merge only in GitHub after approval.
12. After merge, pull `main` with `--ff-only` and delete branches only when safe.

Do not push directly to `main`. Do not use `git push --force`; if a rebase is
unavoidable, use `git push --force-with-lease`.

---

## Gateway PR Tracking

| PR | Branch | Scope | Status |
|---|---|---|---|
| GW-01 | `feat/gateway-prep-contracts` | ADR, Blueprint V3.0, semantic aliases, config contracts | Done / merged |
| GW-02 | `feat/gateway-install-health` | Local-only LiteLLM operational setup | Done / merged |
| GW-03 | `feat/gateway-route-opencraw-litellm` | Runtime chat/generation through LiteLLM | Done / merged |
| GW-04 | `feat/gateway-runtime-smoke` | Shared message validation, optional smoke, observability | Done / merged |
| GW-05a | `feat/gateway-per-alias-timeouts` | Per-alias timeout configuration | Done / merged |
| GW-05b | `feat/gateway-live-smoke-timeouts` | Live smoke with effective timeout observability | Done / merged |
| GW-06 | `feat/gateway-local-embed-evaluation` | Evaluate embeddings via `local_embed` | Done / merged |
| GW06C | `feat/adr-openai-compatible-embeddings-contract` | OpenAI-compatible embeddings ADR and `quimera_embed` | Done / merged |
| GW-07 | `feat/gateway-rag-e2e-synthetic` | Synthetic RAG E2E through gateway path | Done / merged |
| GW-08 | `feat/rag-controlled-embedding-migration` | Controlled RAG embedding migration to `quimera_embed` | Done / merged |
| GW-09 | `feat/rag-collection-metadata-guard` | Collection metadata drift guard for embedding traceability | Done / merged |
| GW-10 | `feat/rag-run-trace-provenance` | Safe per-query RAG provenance trace | Done / merged |
| GW-11 | `feat/rag-observability-events` | Safe structured RAG lifecycle observability events | Done / merged |
| GW-12 | `feat/gateway-operational-readiness` | Final runbook, readiness checks, ADR boundary, handoff | Done / merged |
| GW-13 | `feat/gateway1-routing-policy-prelude` | Gateway-1 local-first routing policy and token economy prelude | Done / merged |
| GW-14 | `feat/gateway1-routing-audit-token-economy` | Config-driven routing audit and token economy calibration | Done / merged |
| GW-15 | `feat/agent0-local-runner` | Agent-0 local CLI runner MVP | Done / merged |
| GW-16 | `feat/agent0-runner-contract-hardening` | Agent-0 runner contract hardening | Done / merged |
| GW-17 | `feat/agent0-local-failsafe-degradation` | Explicit local fail-safe degradation for Agent-0 | Done / merged |
| GW-18 | `feat/agent0-golden-question-harness` | Golden question benchmark harness for Agent-0 | Done / merged |
| GW-19 | `feat/agent0-observability-signal-contract` | Agent-0 observability signal contract and sanitization tests | Done / merged |
| GW-20 | `feat/gateway1-proof-of-life-smoke` | Gateway-1 operational proof-of-life smoke | Done / merged |
| G2-PR01 | `feat/g2-rag-segment-timing-baseline` | Per-segment RAG latency baseline | Done / merged |
| G2-PR02 | `feat/g2-local-rag-context-budget-cap` | Configurable whole-chunk context budget cap | Done / merged |
| G2-PR03 | `feat/g2-local-rag-generation-budget` | Configurable local_rag generation budget | Done / merged |
| G2-PR04 | `feat/g2-warm-model-cold-start-separation` | Cold/warm/degraded latency separation and model residency measurement | Done / merged |
| G2-PR05 | `feat/g2-keep-alive-model-residency` | Configurable local_rag Ollama keep_alive model residency | Done / merged |
| G2-PR06 | `feat/g2-local-rag-alias-comparison` | Local-only local_rag candidate alias comparison harness | Current |

GW-05a issue: <https://github.com/franciscosalido/OPENCLAW/issues/25>
GW-05b issue: <https://github.com/franciscosalido/OPENCLAW/issues/28>
GW-06 issue: <https://github.com/franciscosalido/OPENCLAW/issues/30>
GW-07 issue: <https://github.com/franciscosalido/OPENCLAW/issues/38>
GW-08 issue: <https://github.com/franciscosalido/OPENCLAW/issues/40>
GW-09 issue: <https://github.com/franciscosalido/OPENCLAW/issues/42>
GW-10 issue: <https://github.com/franciscosalido/OPENCLAW/issues/44>
GW-11 issue: <https://github.com/franciscosalido/OPENCLAW/issues/46>
GW-12 issue: <https://github.com/franciscosalido/OPENCLAW/issues/48>
GW-13 issue: <https://github.com/franciscosalido/OPENCLAW/issues/51>
GW-15 issue: <https://github.com/franciscosalido/OPENCLAW/issues/55>
GW-16 issue: <https://github.com/franciscosalido/OPENCLAW/issues/57>
GW-17 issue: <https://github.com/franciscosalido/OPENCLAW/issues/59>
GW-18 issue: <https://github.com/franciscosalido/OPENCLAW/issues/61>
GW-19 issue: <https://github.com/franciscosalido/OPENCLAW/issues/63>

Gateway-0 sprint complete. GW-01 through GW-12 merged on `main`.
The next sprint must start from a new explicit issue, ADR if architecture
changes, and `git pull --ff-only origin main`.

## G2-PR06 Current Work

G2-PR06 adds an opt-in alias comparison harness for `local_rag` candidates.

Deliverables:

- `scripts/run_rag_alias_comparison.py`.
- `tests/unit/test_rag_alias_comparison.py`.
- `docs/RAG_ALIAS_COMPARISON.md`.

Rules:

- `local_rag` remains the default and comparison baseline.
- Candidate aliases must be semantic local LiteLLM aliases, never concrete
  model names.
- Candidate aliases must resolve to local Ollama config only.
- Remote provider prefixes are rejected.
- The same synthetic golden question fixture is used for baseline and
  candidates.
- Reports store `question_id`, fixture hash, alias metrics and citation flags,
  never question text, answer text, prompt text, chunks, vectors, payloads,
  headers, API keys or tracebacks.
- Warmup runs are discarded and marked only in summary metadata.
- No prompt, retrieval, Qdrant, context budget, generation budget, keep_alive,
  alias default or provider config is changed.
- Candidate promotion requires a separate future PR.

## GW-15 Current Work

GW-15 creates Agent-0, the first local MVP runner:

```text
question
  -> decide_route(...)
  -> local_chat | local_json | explicit local_rag
  -> safe answer metadata
```

Deliverables:

- `scripts/run_local_agent.py`.
- `scripts/test_agent0_local_runner.sh` optional smoke guarded by
  `RUN_AGENT0_LOCAL_SMOKE=1`.
- `docs/AGENT0_LOCAL_RUNNER.md`.
- `tests/unit/test_run_local_agent.py`.

Rules:

- Default execution uses `local_chat`.
- `--json` uses `local_json`.
- `--rag` explicitly opts into the existing local RAG path and `local_rag`.
- `--dry-run` works without live services.
- No remote providers, no remote calls, no API keys, no FastAPI, no MCP.
- No Qdrant mutation, no reindexing, no ingestion, no real data.
- Progressive fallback is handled by GW-17.
- Golden questions harness is handled by GW-18.

## GW-16 Current Work

GW-16 hardens the Agent-0 runner contract without adding new execution
features.

Rules:

- Alias matrix is frozen: default `local_chat`, `--json` `local_json`,
  `--rag` `local_rag`.
- Output schema remains stable across success, dry-run, blocked and failure
  states.
- Blocked and dry-run paths return `latency_ms=0.0`.
- Chat, JSON and RAG failures return safe error categories only.
- No fallback is added. RAG/JSON/chat failures do not silently try another
  alias.
- No remote providers, no remote calls, no Qdrant mutation, no live services
  required for tests.

## GW-17 Current Work

GW-17 adds the first explicit local fail-safe degradation layer.

Rules:

- Fallback reasons are enum-derived, not free-form strings.
- RAG/Qdrant unavailable can fallback once from `local_rag` to `local_chat`.
- Successful RAG fallback returns the chat answer, `alias=local_chat`, and
  `used_rag=false`.
- Policy blocks such as `budget_exceeded` and `unsupported_task` never
  fallback, call no model, and return `error_category=blocked`.
- If the fallback alias also fails, the runner returns a safe failure with no
  second fallback.
- Fallback emits a sanitized local `agent_fallback` loguru event only when
  fallback occurs.
- `local_think` timeout fallback is deferred because Agent-0 has no public
  think path yet.
- No remote providers, no remote calls, no Qdrant mutation, no real data, and
  no live services required for unit tests.

## GW-18 Current Work

GW-18 adds the reproducible Agent-0 golden question harness.

Deliverables:

- `tests/golden/questions.yaml` with 8 synthetic financial-domain questions.
- `scripts/run_golden_harness.py` opt-in harness guarded by
  `RUN_GOLDEN_HARNESS=1`.
- Offline `--dry-run` mode that emits JSONL and summary JSON without live
  services.
- `scripts/compare_golden_runs.py` for summary-to-summary regression checks.
- `docs/AGENT0_GOLDEN_HARNESS.md` and `tests/golden/README.md`.

Rules:

- No answer text is stored in JSONL by default; only `answer_length_chars`.
- Reports exclude prompt/question/chunks/vectors/payloads/secrets and raw
  exceptions.
- Reports are written under `tests/golden/reports/`, which is ignored by Git.
- Quality scoring is human-readable only; no LLM-as-judge and no external API.
- Optional human scoring helper is deferred to a future issue.
- No remote providers, no remote calls, no Qdrant mutation, no real data, and
  no live services required for unit tests.

## GW-19 Current Work

GW-19 adds the Agent-0 observability signal contract.

Deliverables:

- `backend/gateway/observability_contract.py` with canonical allowlists and
  prohibited signal keys.
- `tests/unit/test_observability_signal_contract.py` for RouterDecision,
  TokenEconomyRecord, RagRunTrace, fallback events, decision logs, Agent-0
  output and golden harness dry-run reports.
- `docs/AGENT0_OBSERVABILITY.md`.
- GW-18 NB fixes:
  - golden harness uses `estimate_prompt_tokens` directly from
    `backend.gateway.routing_policy`;
  - `GoldenResult` rejects `skipped=True` with `error_category`.

Rules:

- Sanitization is enforced with allowlists, not blocklist-only checks.
- Fallback event `decision_id` must correlate with Agent-0 output.
- `estimated_remote_tokens_avoided` is checked across success, dry-run,
  blocked, fallback success and fallback failure paths.
- No prompt, raw user input, chunks, vectors, payloads, headers, API keys, raw
  exceptions or model weight paths may appear in observability keys.
- No runtime routing behavior, fallback behavior or remote provider behavior is
  changed.
- No live LiteLLM/Ollama/Qdrant services are required for tests.

## GW-13 Completed Work

GW-13 opens Gateway-1 with safe routing policy records only.

Deliverables:

- `backend/gateway/routing_policy.py` with frozen decision and token economy
  dataclasses.
- `config/rag_config.yaml` `gateway.routing` defaults with
  `remote_enabled: false` and no allowed remote providers.
- `docs/GATEWAY1_ROUTING_POLICY.md`.
- `docs/ADR/0020-controlled-remote-escalation-policy.md` with status Proposed.
- `docs/sprints/GATEWAY1_SPRINT_HANDOFF.md`.
- `tests/unit/test_gateway_routing_policy.py`.

Rules:

- No remote providers.
- No remote calls.
- No API keys.
- No runtime model routing change.
- No Qdrant mutation, reindexing, ingestion, or `openclaw_knowledge` access.
- Token economy is estimated only, not billed.
- Remote escalation requires future sanitization and an explicit Accepted ADR.

---

## GW-05a Timeout Contract

Runtime gateway calls now reserve different timeout budgets per semantic alias:

| Alias | Timeout | Notes |
|---|---:|---|
| `local_chat` | 30.0s | Default chat calls |
| `local_think` | 120.0s | Longer local reasoning calls |
| `local_rag` | 60.0s | RAG answer synthesis |
| `local_json` | 30.0s | Structured local responses |
| `local_embed` | 30.0s | Placeholder only; embeddings are not routed through LiteLLM in GW-05a |

Unknown aliases and `None` fall back to the global `timeout_seconds`.

---

## GW-12 Completed Work

GW-12 closed Gateway-0 as an operational readiness PR, not a feature PR.

Deliverables:

- `docs/GATEWAY_FINAL_RUNBOOK.md`.
- `scripts/check_gateway_readiness.sh` with static default mode and explicit
  `--live`.
- `tests/unit/test_gateway_readiness_script.py`.
- `tests/unit/test_gateway_final_baseline.py`.
- `docs/ADR/0019-gateway-0-sprint-boundary.md`.
- Final updates to shared context, setup, runtime and handoff docs.

Rules respected:

- No runtime architecture change.
- No remote providers.
- No FastAPI, MCP, quant tools, OpenTelemetry, Prometheus, Grafana,
  dashboards, profiling, or mandatory soak tests.
- No Qdrant mutation, no reindexing, no `openclaw_knowledge` access.
- Live proof remains opt-in and must not become CI.
- Memory/resource baseline: not implemented in GW-12. Deferred to a future sprint. See ADR-0019 Future Work section.

## Historical Work

GW-05b:

- Add `timeout_s` to gateway call debug logs.
- Run expanded live smoke with LiteLLM and Ollama actually running when
  `RUN_LITELLM_SMOKE=1` is explicitly set.
- Validate `local_chat`, `local_think`, `local_rag`, and `local_json` against
  their effective timeout budgets.
- Keep smoke synthetic-only and local-only.
- Do not introduce remote providers, real data, RAG E2E, or embeddings through
  LiteLLM.

Live smoke status for GW-05b:

- **2026-04-28: PASSED** — Cenário A completo.
- 128/128 unit+integration tests passed. mypy 0. pyright 0.
- `RUN_LITELLM_SMOKE=1 pytest tests/smoke/` — 7/7 passed.
- `RUN_LITELLM_SMOKE=1 RUN_LITELLM_SMOKE_REPEAT=3 pytest tests/smoke/` — 7/7 passed (54s).

Observed latencies (macOS, qwen3:14b Q4_K_M):

| Alias | elapsed_s | timeout_s |
|---|---:|---:|
| `local_chat` | 2.20 | 30.0 |
| `local_think` | 12.44 | 120.0 |
| `local_rag` | 2.23 | 60.0 |
| `local_json` | 1.72 | 30.0 |

GW-06:

- Evaluate whether embeddings should route through `local_embed`.
- Add an experimental `GatewayEmbedClient` for OpenAI-compatible
  `/embeddings` calls through LiteLLM.
- Keep existing direct/local embedding behavior as the default RAG path.
- Do not reindex Qdrant or touch real documents.
- Use only synthetic smoke inputs.
- Live evaluation on 2026-04-28 passed against local LiteLLM + Ollama.
- Decision status: **Approved for future migration**.
- Migration is still not performed in GW-06; a future PR must preserve or
  replace the current Ollama embedder's retry/backoff/concurrency behavior.

Observed local_embed results (2026-04-28):

| Check | Result |
|---|---|
| LiteLLM single embedding | 768 dimensions, 0.08s |
| LiteLLM batch embedding | 2 vectors, 768 dimensions each, 0.05s |
| Direct Ollama parity | 768 dimensions |
| Cosine similarity | 1.000000 |
| Script smoke | 768 dimensions, 0.70s |

GW-07:

- Prove a synthetic RAG end-to-end flow against the gateway path.
- Keep Qdrant data synthetic and local.
- Use a unique temporary collection named `gw07_synthetic_rag_<short_uuid>`.
- Attempt prefix-guarded cleanup and delete only temporary collections with the
  `gw07_synthetic_rag_` prefix.
- Never touch `openclaw_knowledge`.
- Keep embeddings direct through `OllamaEmbedder`; `quimera_embed` appears only
  as embedding contract metadata in this PR.
- Generate the final answer through LiteLLM using `local_rag`.
- Run only when explicitly enabled with `RUN_RAG_E2E_SMOKE=1`.

Manual live command:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/test_rag_e2e_gateway.sh
```

Direct pytest command:

```bash
RUN_RAG_E2E_SMOKE=1 uv run pytest tests/smoke/test_rag_e2e_gateway_smoke.py -v
```

Cleanup is attempted in teardown. If cleanup is interrupted, manually delete
only Qdrant collections whose names start with `gw07_synthetic_rag_`.

Live status:

- **2026-04-30: PASSED** — Cenário A completo for GW-07.
- Command: `RUN_RAG_E2E_SMOKE=1 uv run pytest tests/smoke/test_rag_e2e_gateway_smoke.py -v -s`.
- Corpus: 3 PT-BR synthetic documents, 14 chunks, 5 chunks retrieved/used.
- Temporary collection: `gw07_synthetic_rag_<short_uuid>` with prefix-guarded
  cleanup for the recorded run; interrupted runs may require manual cleanup by
  prefix.
- Embedding path: direct `OllamaEmbedder` to Ollama `/api/embed`.
- Generation path: `LocalGenerator` / `GatewayChatClient` through LiteLLM
  `local_rag`.

Observed GW-07 latencies (2026-04-30):

| Stage | Latency |
|---|---:|
| embedding/indexing | 178.1 ms |
| retrieval | 18.4 ms |
| generation | 3621.2 ms |
| total pipeline | 3639.6 ms |

---

## Validation Expectations For GW-07

Before opening PR:

```bash
git diff --check
uv run pytest -v
uv run mypy --strict .
uv run pyright
uv run python -m compileall backend tests scripts infra
uv run pytest tests/unit/test_gateway_embed_client.py -v
uv run pytest tests/smoke/ -v
```

## GW-10 Completed Work

GW-10 adds `RagRunTrace`, a safe frozen dataclass for per-query provenance:

```text
LocalRagPipeline.ask(...)
  -> retrieval/prompt/generation timings
  -> RagRunTrace safe metadata only
  -> logger.bind(trace=...).log(...)
```

Trace scope:

- Records collection name, embedding backend/model/alias/dimensions, chunk
  count, gateway alias, and latency metadata.
- Does not record query text, chunk text, prompts, answer text, vectors,
  payloads, real portfolio data, private documents, API keys, Authorization
  headers, or secrets.
- Uses `rag.tracing.enabled` and `rag.tracing.log_level` from
  `config/rag_config.yaml`.
- Raises `EmbeddingDimensionMismatchError` if trace dimensions diverge from
  active expected dimensions.
- Does not mutate Qdrant, reindex collections, or touch `openclaw_knowledge`.

GW-11 current work remains separate from `RagRunTrace`: lifecycle events are
local structured loguru records around embedding, retrieval, and generation.
Memory/resource baseline: not implemented in GW-12. Deferred to a future sprint. See ADR-0019 Future Work section.

Live smoke tests should skip by default unless their explicit guards are set.
GW-07 requires `RUN_RAG_E2E_SMOKE=1`.

Optional live validation when local services are already running:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
RUN_LITELLM_EMBED_SMOKE=1 uv run pytest tests/smoke/test_gateway_embed_smoke.py -v
scripts/test_local_embed_litellm.sh
```

Optional GW-07 live validation when Qdrant, Ollama, LiteLLM, and credentials are
already running locally:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/test_rag_e2e_gateway.sh
```

## GW-08 Completed Work

GW-08 aligns new controlled RAG embedding generation with the accepted
OpenAI-compatible embeddings contract:

```text
RagEmbedder factory
  -> gateway_litellm
  -> GatewayEmbedClient
  -> LiteLLM /v1/embeddings
  -> quimera_embed
  -> Ollama / nomic-embed-text
```

Rollback remains explicit:

```bash
export QUIMERA_RAG_EMBEDDING_BACKEND="direct_ollama"
```

Key rules:

- `OllamaEmbedder` remains available.
- `direct_ollama` remains the rollback backend.
- Existing collections are not reindexed automatically.
- `openclaw_knowledge` is not touched.
- Vectors from different embedding backends, models, providers, or dimensions
  must not be mixed silently in one collection.
- GW-08 smoke uses temporary collections with prefix
  `gw08_embedding_migration_`.

Validation expectations:

```bash
git diff --check
uv run pytest -v
uv run mypy --strict .
uv run pyright
uv run pytest tests/smoke/ -v
```

Optional live validation:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/test_gw08_embedding_migration.sh
```

Live status:

- **2026-04-30: PASSED** — controlled migration smoke and parity smoke passed.
- Required operational note: restart LiteLLM after adding `quimera_embed`; an
  old LiteLLM process may still expose only `local_embed`.
- Command: `QUIMERA_LLM_API_KEY=<local-placeholder> scripts/test_gw08_embedding_migration.sh`.
- Temporary collection prefix: `gw08_embedding_migration_`.
- Synthetic chunks: 4 indexed, 4 retrieved/used.
- Embedding path: `RagEmbedder factory -> gateway_litellm -> GatewayEmbedClient -> LiteLLM /v1/embeddings -> quimera_embed`.
- Generation path: `LocalGenerator / GatewayChatClient -> LiteLLM local_rag`.
- Rollback path remains: `QUIMERA_RAG_EMBEDDING_BACKEND=direct_ollama`.
- `openclaw_knowledge` was not touched.

Observed GW-08 latencies and parity (2026-04-30):

| Check | Result |
|---|---:|
| embedding/indexing | 314.7 ms |
| retrieval | 27.4 ms |
| generation | 4951.7 ms |
| total pipeline | 4979.1 ms |
| cosine similarity vs direct Ollama | 1.000000 |
| vector dimensions | 768 |

## GW-09 Completed Work

GW-09 adds a traceability guard for Qdrant collection embedding metadata:

```text
Qdrant payload sample
  -> embedding_backend/model/dimensions/contract/alias check
  -> structured warning on drift
  -> hard error only for dimension mismatch by default
```

Key rules:

- The guard samples payloads with `with_payload=True` and `with_vectors=False`.
- It does not mutate, delete, recreate, or reindex collections.
- It does not touch `openclaw_knowledge`.
- Backend, model, contract, alias, and missing metadata drift warn by default.
- Dimension mismatch always raises `EmbeddingDimensionMismatchError`.
- `strict=True` can raise on backend/model/contract/alias mismatch.
- No chunk text, vectors, prompts, secrets, or Authorization headers are logged.
- GW-10 remains the place for `RagRunTrace`.
- GW-11 adds structured RAG observability lifecycle events separately.

Validation expectations:

```bash
git diff --check
uv run pytest -v
uv run mypy --strict .
uv run pyright
uv run pytest tests/smoke/ -v
```

## GW-11 Completed Work

GW-11 adds local structured RAG lifecycle observability events:

```text
embedding/retrieval/generation stage
  -> RagObservabilityEvent safe metadata only
  -> logger.bind(event=...).log(...)
```

Scope:

- `backend/rag/observability.py` defines event kinds, error categories, config,
  safe serialization, emission, and exception categorization.
- `GatewayEmbedClient` emits embedding started/finished/failed events for
  `gateway_litellm`.
- `OllamaEmbedder` emits embedding started/finished/failed events for
  `direct_ollama`.
- `LocalRagPipeline` emits retrieval and generation lifecycle events.
- `config/rag_config.yaml` has `rag.observability` flags and log level.

Safety rules:

- Events contain only safe scalar metadata.
- Events never include query text, prompt text, answer text, chunk text,
  document text, vectors, Qdrant payloads, portfolio data, API keys,
  Authorization headers, tokens, passwords, or secrets.
- No return values change.
- Retry/backoff/concurrency semantics are unchanged.
- Qdrant is not mutated and `openclaw_knowledge` is not touched.

Out of scope:

- OpenTelemetry, Prometheus, Grafana, dashboards, distributed tracing,
  profiling, soak tests, and memory/resource baselines.
- Memory/resource baseline: not implemented in GW-12. Deferred to a future sprint. See ADR-0019 Future Work section.

## GW-20 Completed Work

GW-20 adds the Gateway-1 operational proof-of-life smoke and closes the
Gateway-1 readiness loop before Gateway-2:

```text
dry-run Agent-0
  -> local URL guard
  -> Ollama/Qdrant/LiteLLM probes
  -> live local_chat
  -> live local_rag or explicit fallback
  -> forced Qdrant degradation
  -> policy block no-model-call check
  -> sanitized summary JSON
```

Key files:

- `docs/sprints/GATEWAY1_DONE_CRITERIA.md`
- `scripts/test_gateway1_proof_of_life.py`
- `docs/AGENT0_SMOKE.md`
- `tests/unit/test_gateway1_proof_of_life.py`

Rules:

- The smoke is opt-in with `RUN_GATEWAY1_PROOF_OF_LIFE=1`.
- Live probes refuse non-local service URLs.
- Summary reports do not store answer text, prompts, questions, chunks,
  vectors, payloads, secrets, Authorization headers, raw exceptions or
  tracebacks.
- Forced degradation is injected through Agent-0 hooks; it does not stop Docker,
  mutate Qdrant, reindex, or touch `openclaw_knowledge`.
- Gateway-2 should not begin until GW-20 passes locally.

Live proof result on 2026-05-02:

- Command:
  `QUIMERA_LLM_API_KEY=dev-local-key-change-me RUN_GATEWAY1_PROOF_OF_LIFE=1 uv run python scripts/test_gateway1_proof_of_life.py --output-dir /tmp/openclaw_gateway1_smoke`
- Result: **PASSED** — G1-01 through G1-11 all true.
- Summary: `/tmp/openclaw_gateway1_smoke/gateway1_proof_of_life_9f23ce3df3f2.json`.
- Probes: Ollama OK, Qdrant OK, LiteLLM OK.
- Live runner: `local_chat` OK, `local_rag` OK.
- Forced Qdrant degradation: fallback to `local_chat` with
  `qdrant_unavailable`.
- Policy block: blocked before model call.

Observed live latencies:

| Check | Latency |
|---|---:|
| Ollama probe | 28.6 ms |
| Qdrant probe | 9.4 ms |
| LiteLLM probe | 26.1 ms |
| Agent-0 `local_chat` | 8790.5 ms |
| Agent-0 `local_rag` | 32162.8 ms |
| forced degradation | 0.03 ms |

## G2-01 Current Work

G2-01 starts Gateway-2 with a measurement-only RAG latency baseline:

```text
LocalRagPipeline
  -> RagRunTrace optional segment fields
  -> embed/search/pack/prompt/generation/total timings
  -> safe trace serialization only
```

Scope:

- Extend `RagRunTrace` with optional per-segment fields:
  `routing_ms`, `embedding_ms`, `retrieval_ms`, `context_pack_ms`,
  `prompt_build_ms`, `generation_ms`, `total_ms`, and `run_context`.
- Preserve old trace fields such as `retrieval_latency_ms`,
  `generation_latency_ms`, `prompt_latency_ms`, and `total_latency_ms`.
- Populate pipeline traces from existing `time.perf_counter()` wrappers and
  `Retriever.last_timings`.
- Keep `total_ms` as a directly measured outer timer, not a segment sum.
- Add optional Ollama metric fields, but only when already available in
  metadata. Current LiteLLM path does not expose native Ollama metrics, so
  normal traces record `ollama_metrics_available=false`.

Safety:

- No optimization.
- No prompt/top-k/model/timeout/alias/routing/fallback behavior change.
- No Qdrant mutation, no reindex, no `openclaw_knowledge` access.
- No prompt, question, chunks, answer, vectors, payloads, API keys,
  Authorization headers, raw exceptions or tracebacks in trace serialization.

Deferred from G2-01:

- First optimization experiment: configurable local RAG context budget cap.

## G2-02 Current Work

G2-02 adds a rollback-safe, config-controlled context budget cap for
`local_rag`:

```text
retrieved chunks
  -> existing ContextPacker dedup/token-limit/document ordering
  -> optional whole-chunk max_context_chunks cap
  -> PromptBuilder
  -> LocalGenerator/local_rag
```

Scope:

- Add `rag.context_budget` to `config/rag_config.yaml`:
  `enabled: false`, `max_context_chunks: 3`, `mode: whole_chunks`,
  `apply_to_aliases: [local_rag]`.
- Add typed `ContextBudgetConfig` and `ContextBudgetResult`.
- Apply the cap in `ContextPacker` only, after existing packing logic.
- Preserve whole chunks, citation ids, `doc_id`, `chunk_index`, and payload
  metadata.
- Expose safe trace metadata on `RagRunTrace`:
  `context_budget_enabled`, `context_budget_applied`,
  `context_chunks_retrieved`, `context_chunks_used`,
  `context_chunks_dropped`, `context_budget_max_chunks`, and
  `context_estimated_tokens_used`.

Safety:

- Default `enabled: false` preserves existing behavior.
- Rollback is a single config change.
- No retrieval/top-k/Qdrant/model alias/prompt template/timeout change.
- No Qdrant mutation, no reindex, no `openclaw_knowledge` access.
- No prompt, chunks, answer, vectors, payloads, secrets, Authorization headers,
  raw exceptions or tracebacks in trace serialization.

Deferred:

- Token-based context budgeting.
- Full recalibration of `estimated_remote_tokens_avoided` against the final
  capped prompt.
- Mandatory live Golden Harness before/after gate.

## G2-07 Current Work

G2-07 closes Gateway-2 with an offline baseline freeze and regression gate.
This is not an optimization PR.

Delivered scope:

- Official tracked baseline artifacts under `tests/golden/baseline/`:
  `gateway2_baseline_summary.json`, `gateway2_baseline_results.jsonl`,
  `gateway2_baseline_scores.jsonl`, and
  `gateway2_regression_thresholds.yaml`.
- `scripts/compare_golden_runs.py` now supports:
  `--verify-only <summary.json>` and
  `--baseline <summary.json> --candidate <summary.json> --thresholds <yaml>`.
- Regression gate exit codes:
  `0` pass, `2` schema/sanitization, `3` citation/quality,
  `4` latency, `5` fixture/config mismatch, `6` incompatibility.
- Baseline summaries stay grouped by alias and run type:
  `cold_start`, `warm_model`, and `degraded_qdrant`.
- Generated report directories are ignored while official baseline artifacts
  remain explicitly allowed.

Safety:

- No prompt, question text, answer text, chunks, vectors, payloads, headers,
  API keys, raw exceptions, tracebacks, usernames, local paths or model weight
  paths are allowed in baseline artifacts.
- No remote providers, no live services, no Qdrant mutation, no reindexing and
  no `openclaw_knowledge` access are required for the gate.

Gateway-2 handoff:

- See `docs/GATEWAY2_BASELINE.md`.
- See `docs/sprints/GATEWAY2_SPRINT_HANDOFF.md`.
- Gateway-3 should start from the frozen Gateway-2 baseline and use the offline
  gate before accepting performance or quality regressions.
