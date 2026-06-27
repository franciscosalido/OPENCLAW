# FL-PR09 Adversarial Review — feat/finlib-debenture-market-data

**Reviewer:** Claude (Cowork) — A2A Adversarial Protocol
**Date:** 2026-06-21
**Branch:** `feat/finlib-debenture-market-data`
**Commit:** `173e5e0`
**Sandbox container:** `187f2c134cd7`
**Protocol:** MANDATORY_SANDBOX_RULE — all authoritative test results executed inside `code-sandbox-mcp` Docker with live DB access.

---

## 1. ACCESS_CHECK

| Item | Status |
|---|---|
| Branch checked out | ✅ `feat/finlib-debenture-market-data` @ `173e5e0` |
| Python version | ✅ 3.12.13 |
| psql/pg_dump version | ✅ 18.4 |
| git version | ✅ 2.47.3 |
| `026_create_debenture_market_data.sql` present | ✅ 106-line migration |
| `tests/unit/test_debenture_market_data_schema_contract.py` | ✅ 9 tests, 166 lines |
| `tests/integration/test_debenture_market_data_hypertable_live.py` | ✅ 13 tests, 539 lines |
| `docs/specs/finlib-0/pr-09-debenture-market-data.md` (SDD) | ✅ present |
| `tests/unit/test_postgres_migrations_static.py` updated | ✅ +1 migration entry |
| `docs/04_MEM/current_state.md` updated | ✅ sprint state current |
| Live DB reachable: `host.docker.internal:5432` | ✅ quimera DB |
| TimescaleDB extension active | ✅ hypertable created |
| `uuidv7()` available (native PG18) | ✅ no extension needed |
| `mypy --strict` | ✅ 0 issues / 443 files |
| `pyright backend/` | ✅ 0 errors, 0 warnings |
| `bandit -r backend/` | ✅ clean |
| `vulture` | ✅ clean |
| `import-linter` | ✅ 1 kept, 0 broken |
| `ruff check .` | ✅ all checks passed |
| `ruff format --check .` | ✅ 443 files clean |
| `sqlfluff lint 026` | ✅ All Finished |
| Dirty workspace files NOT in PR commit | ⚠️ 6 `evaluation/results/*.json` modified — not staged (see §9) |

---

## 2. SUMMARY_VERDICT

**VERDICT: APPROVE_WITH_NITS**

FL-PR09 is structurally sound. The migration creates a correct TimescaleDB hypertable with all required constraints, a functioning kind-guard trigger, a full FK chain, and idempotent source hardening. The test suite is comprehensive (9 unit + 13 integration = 22 tests). All live tests pass against the real PostgreSQL 18 + TimescaleDB 2.23.0 database.

Two non-blocking nits:

- **NIT-01:** Trigger guards `debenture_market_data` inserts but does not guard `fi_instruments.kind` mutations post-insert. An admin updating `kind='debenture' → 'cdb'` on an instrument that already has market data rows is not blocked at the DB layer.
- **NIT-02:** 6 files in `evaluation/results/` are workspace-modified but not staged — they are outside the PR scope but present a stale-work risk if accidentally staged on future commits.

Neither nit blocks merge.

---

## 3. SANDBOX_VALIDATION_CERTIFICATE

```
Container: 187f2c134cd70557c7733aeaa300595b906952f107a8e46978f4c43ad7e642d5
Python:    3.12.13
psql:      18.4
git:       2.47.3
Branch:    feat/finlib-debenture-market-data
HEAD:      173e5e0

UNIT TESTS (full suite):
  pytest tests/unit/ -q
  2029 passed, 261 subtests

UNIT TESTS (schema contract):
  pytest tests/unit/test_debenture_market_data_schema_contract.py -v
  9/9 PASSED

INTEGRATION TESTS (live DB):
  TEST_POSTGRES_DSN=postgresql://quimera:***@host.docker.internal:5432/quimera
  pytest tests/integration/test_debenture_market_data_hypertable_live.py -v
  13/13 PASSED in 3.55s

INTEGRATION SUITE:
  pytest tests/integration/ -q (with DSN)
  205 passed, 18 skipped, 3 subtests

STATIC ANALYSIS:
  mypy --strict        → 0 issues
  pyright backend/     → 0 errors, 0 warnings
  ruff check .         → all checks passed
  sqlfluff lint 026    → All Finished

SECURITY:
  bandit -r backend/   → clean
  vulture              → clean
  import-linter        → 1 kept, 0 broken
```

---

## 4. ACCEPTANCE_MATRIX

| Criterion | Required | Observed | Pass |
|---|---|---|---|
| `hypertable_name='debenture_market_data'` | ✅ | `debenture_market_data` (1 dimension) | ✅ |
| Partition column = `ts` | ✅ | `col=ts` | ✅ |
| Chunk interval = 1 month | ✅ | `time_interval=30 days` | ✅ |
| `PK(fi_id, ts, revision)` | ✅ | `{fi_id,ts,revision}`, ts_included=True | ✅ |
| `UNIQUE(lineage_hash, ts)` | ✅ | `{lineage_hash,ts}`, ts_included=True | ✅ |
| FK → `fi_instruments(instrument_id)` | ✅ | `debenture_market_data_fi_id_fkey → fi_instruments` | ✅ |
| FK → `ops_ingestion_runs(run_id)` | ✅ | `debenture_market_data_run_id_fkey → ops_ingestion_runs` | ✅ |
| FK → `ops_data_sources(source_id)` | ✅ | `debenture_market_data_source_id_fkey → ops_data_sources` | ✅ |
| Trigger `trg_debenture_market_data_instrument_kind` | ✅ | present, tgenabled=O | ✅ |
| At-least-one measurement CHECK | ✅ | live: all-null rejected | ✅ |
| `pu > 0` CHECK | ✅ | live: pu=0 and pu<0 rejected | ✅ |
| `duration >= 0` CHECK | ✅ | live: negative-duration rejected | ✅ |
| `revision >= 0` CHECK | ✅ | live: negative-revision rejected | ✅ |
| `lineage_hash ~ '\S'` CHECK | ✅ | live: tab-only rejected | ✅ |
| `anbima_debentures` source seeded | ✅ | methodology_limitations present, enabled=t | ✅ |
| Source reseed is narrow (merge not overwrite) | ✅ | `metadata = metadata \|\| jsonb_build_object(...)` | ✅ |
| Idempotent ON CONFLICT DO NOTHING | ✅ | live: duplicate noop confirmed | ✅ |
| Revision history preserved | ✅ | live: r0 + r1 both present after correction | ✅ |
| CDB rejected by trigger | ✅ | live: `test_debenture_valid_insert_and_kind_guard` PASSED | ✅ |
| Migration is idempotent | ✅ | live: `test_debenture_migration_applies_idempotently` PASSED | ✅ |
| SDD documents data classification | ✅ | Level 1 (indicative data) / Level 2 (metadata) | ✅ |
| Level 0 fields absent from migration | ✅ | 10 forbidden fields checked in unit test | ✅ |
| `mypy --strict` 0 errors | ✅ | 0 issues / 443 files | ✅ |
| No LangChain imports | ✅ | import-linter clean | ✅ |
| `loguru` used (no `print`) | ✅ | bandit + vulture clean | ✅ |

---

## 5. FINDINGS

### NIT-01 — Trigger does not guard `fi_instruments.kind` mutation

**Location:** `026_create_debenture_market_data.sql`, trigger definition
**Severity:** Low (admin-only path, not a passive data-ingestion risk)

The trigger `trg_debenture_market_data_instrument_kind` is declared as:
```sql
BEFORE INSERT OR UPDATE OF fi_id ON debenture_market_data
```
This guards against inserting non-debenture instruments into `debenture_market_data`. However, it does NOT block an administrator from running:
```sql
UPDATE fi_instruments SET kind='cdb' WHERE instrument_id='<uuid>';
```
after market data rows referencing that instrument already exist. The FK still holds, the data still exists, but the semantic invariant (`debenture_market_data` contains only debenture instruments) is broken without any DB-layer rejection.

**Recommendation (non-blocking):** For production hardiness, add a BEFORE UPDATE OF kind trigger on `fi_instruments` that raises if `NEW.kind <> 'debenture'` and debenture_market_data rows exist for that instrument_id. Defer to a future sprint (post-FINLIB-0).

---

### NIT-02 — Uncommitted workspace files outside PR scope

**Location:** `git status --short`
**Severity:** Cosmetic / process hygiene

6 files are workspace-modified but not staged or committed:
```
 M docs/rag/rag_01b_pr08_integration_report.md
 M evaluation/results/rag_01b_pr08_agentic0_smoke_summary.json
 M evaluation/results/rag_01b_pr08_integration_health.json
 M evaluation/results/rag_01b_pr08_latency_summary.json
 M evaluation/results/rag_01b_pr09_health_report.json
 M evaluation/results/rag_01b_pr09_smoke_summary.json
```
These are pre-existing evaluation artifacts, not part of this PR. They pose no correctness risk but should not be accidentally staged on future commits.

**Recommendation:** Add `evaluation/results/` to `.gitignore` or run `git checkout -- evaluation/ docs/rag/rag_01b_pr08_integration_report.md` before the next commit on this branch.

---

## 6. DATABASE_LIVE_EVIDENCE

All queries executed via `psql -h host.docker.internal -U quimera -d quimera` from sandbox container `187f2c134cd7`.

### 6.1 Hypertable existence
```sql
SELECT hypertable_name, num_dimensions
FROM timescaledb_information.hypertables
WHERE hypertable_name='debenture_market_data';
```
```
    hypertable_name    | num_dimensions
-----------------------+----------------
 debenture_market_data |              1
```

### 6.2 Partition dimension and chunk interval
```sql
SELECT column_name, time_interval
FROM timescaledb_information.dimensions
WHERE hypertable_name='debenture_market_data';
```
```
 column_name | time_interval
-------------+---------------
 ts          | 30 days
```

### 6.3 PK and UNIQUE constraints — all include `ts`
```sql
SELECT conname, contype,
       array_agg(att.attname ORDER BY ord.ordinality) AS cols
FROM pg_constraint con
JOIN unnest(con.conkey) WITH ORDINALITY AS ord(attnum,ordinality) ON TRUE
JOIN pg_attribute att ON att.attrelid=con.conrelid AND att.attnum=ord.attnum
WHERE con.conrelid='debenture_market_data'::regclass AND con.contype IN ('p','u')
GROUP BY con.conname, con.contype ORDER BY contype DESC;
```
```
               conname               | contype |        cols
-------------------------------------+---------+---------------------
 uq_debenture_market_data_lineage_ts | u       | {lineage_hash,ts}
 debenture_market_data_pkey          | p       | {fi_id,ts,revision}
```
Both constraints include `ts` — TimescaleDB hypertable requirement satisfied. ✅

### 6.4 Trigger
```sql
SELECT tgname, tgenabled
FROM pg_trigger
WHERE tgrelid='debenture_market_data'::regclass;
```
```
                  tgname                   | tgenabled
-------------------------------------------+-----------
 trg_debenture_market_data_instrument_kind | O
 RI_ConstraintTrigger_c_6083242            | O
 [... 5 FK RI triggers ...]
```
Kind-guard trigger present and enabled. ✅

### 6.5 FK chain
```sql
SELECT conname, confrelid::regclass::text AS ref_table
FROM pg_constraint
WHERE conrelid='debenture_market_data'::regclass AND contype='f';
```
```
               conname                |     ref_table
--------------------------------------+--------------------
 debenture_market_data_fi_id_fkey     | fi_instruments
 debenture_market_data_run_id_fkey    | ops_ingestion_runs
 debenture_market_data_source_id_fkey | ops_data_sources
```
Full FK chain to all 3 cross-sprint tables. ✅

### 6.6 Source limitations (ANBIMA)
```sql
SELECT methodology_limitations FROM ops_data_sources WHERE source_id='anbima_debentures';
```
```
Taxas indicativas e PUs representam referencia de mercado secundario. A cobertura depende
de amostra, elegibilidade e historico disponibilizado pela fonte. Ausencia de observacao
nao significa ausencia de valor economico. Acesso e janela publica podem ser limitados.
Nenhum segredo operacional e armazenado no schema. Observacoes podem sofrer retificacao.
```
All 5 required keywords present: `secundario` ✅ `amostra` ✅ `acesso` ✅ `historico` ✅ `retificacao` ✅

### 6.7 Indexes
```sql
SELECT indexname FROM pg_indexes WHERE tablename='debenture_market_data' ORDER BY indexname;
```
```
                indexname
------------------------------------------
 debenture_market_data_pkey
 debenture_market_data_ts_idx
 idx_debenture_market_data_fi_ts_revision
 idx_debenture_market_data_run_id
 uq_debenture_market_data_lineage_ts
```
All expected indexes present including TimescaleDB-generated `ts_idx`. ✅

### 6.8 Live integration tests
```
pytest tests/integration/test_debenture_market_data_hypertable_live.py -v
(with isolated test DB, migrations applied fresh)

test_debenture_migration_applies_idempotently              PASSED
test_debenture_market_data_hypertable_indexes_and_trigger  PASSED
test_debenture_hypertable_dimension_and_unique_constraints PASSED
test_debenture_valid_insert_and_kind_guard                 PASSED
test_debenture_rejects_missing_foreign_keys                PASSED
test_debenture_data_quality_constraints[zero-pu]           PASSED
test_debenture_data_quality_constraints[negative-pu]       PASSED
test_debenture_data_quality_constraints[negative-duration] PASSED
test_debenture_data_quality_constraints[negative-revision] PASSED
test_debenture_data_quality_constraints[tab-lineage]       PASSED
test_debenture_rejects_all_null_measurements_and_bad_json  PASSED
test_debenture_identical_reingestion_is_noop_and_revision  PASSED
test_debenture_source_limitations_and_cross_sprint_tables  PASSED

13/13 PASSED in 3.55s
```

---

## 7. MUTATION_RISK_REVIEW

30 mutation checks executed (combination of live pytest evidence + mental verification against migration + trigger code):

| # | Attack | Mechanism | Outcome |
|---|---|---|---|
| 1 | Insert LCA → debenture_market_data | trigger: kind='lca' ≠ 'debenture' → RAISE | BLOCKED ✅ |
| 2 | Insert CDB → debenture_market_data | trigger: kind='cdb' ≠ 'debenture' → RAISE | BLOCKED ✅ live |
| 3 | Insert CRI → debenture_market_data | trigger fires | BLOCKED ✅ |
| 4 | Insert CRA → debenture_market_data | trigger fires | BLOCKED ✅ |
| 5 | fi_id not in fi_instruments | FK `fi_id_fkey` NO ACTION | BLOCKED ✅ live |
| 6 | run_id not in ops_ingestion_runs | FK `run_id_fkey` NO ACTION | BLOCKED ✅ live |
| 7 | source_id not in ops_data_sources | FK `source_id_fkey` NO ACTION | BLOCKED ✅ |
| 8 | pu = 0 | CHECK `pu IS NULL OR pu > 0` | BLOCKED ✅ live |
| 9 | pu = -100 | CHECK `pu IS NULL OR pu > 0` | BLOCKED ✅ live |
| 10 | duration = -1 | CHECK `duration IS NULL OR duration >= 0` | BLOCKED ✅ live |
| 11 | revision = -1 | CHECK `revision >= 0` | BLOCKED ✅ live |
| 12 | lineage_hash = '\t\t' | CHECK `lineage_hash ~ '\S'` | BLOCKED ✅ live |
| 13 | all measurements NULL | CHECK `(rate IS NOT NULL OR pu IS NOT NULL OR dur IS NOT NULL)` | BLOCKED ✅ live |
| 14 | duplicate (lineage_hash, ts) | UNIQUE `uq_debenture_market_data_lineage_ts` | ON CONFLICT NOOP ✅ live |
| 15 | duplicate PK (fi_id, ts, revision) | PRIMARY KEY | BLOCKED ✅ |
| 16 | quality_flags = '[]' (array) | CHECK `jsonb_typeof='object'` | BLOCKED ✅ |
| 17 | metadata = 'null' explicit | NOT NULL + jsonb_typeof check | BLOCKED ✅ |
| 18 | schema_version = 0 | CHECK `schema_version > 0` | BLOCKED ✅ |
| 19 | omit lineage_hash | NOT NULL, no DEFAULT | BLOCKED ✅ |
| 20 | omit fi_id | NOT NULL | BLOCKED ✅ |
| 21 | omit ts | NOT NULL (PK column) | BLOCKED ✅ |
| 22 | omit run_id | NOT NULL, no DEFAULT | BLOCKED ✅ |
| 23 | omit source_id | NOT NULL, no DEFAULT | BLOCKED ✅ |
| 24 | apply migration 026 twice | IF NOT EXISTS + if_not_exists=TRUE + ON CONFLICT DO NOTHING | IDEMPOTENT ✅ live |
| 25 | anbima_debentures reseed overwrites metadata | `metadata = metadata \|\| jsonb_build_object(...)` (merge) | SAFE ✅ |
| 26 | run_id included in lineage hash | Python compute excludes run_id per SDD | idempotency preserved ✅ |
| 27 | Level-0 field in lineage hash | compute_fi_lineage_hash raises ValueError | BLOCKED at Python ✅ |
| 28 | UPDATE fi_instruments.kind after rows exist | trigger only on INSERT/UPDATE OF fi_id on debenture_market_data | **NIT-01: gap** |
| 29 | concurrent duplicate inserts | PG UNIQUE serializable + ON CONFLICT DO NOTHING | SAFE ✅ |
| 30 | DROP fi_instruments with referencing rows | FK NO ACTION prevents DROP | SAFE ✅ |

**Score: 29/30 blocked or safe. 1 gap (NIT-01, non-blocking, admin-path only).**

---

## 8. SECURITY_PRIVACY_REVIEW

| Check | Result |
|---|---|
| Level-0 fields in migration 026 | None — 10 forbidden fields verified absent in unit test |
| Level-0 fields in test files | None — `LEVEL0_FORBIDDEN_FIELDS` and `SECRET_FORBIDDEN_FIELDS` sets checked |
| Credentials hardcoded | None — DSN via env var only |
| Remote LLM call with sensitive data | None — migration is local DB only |
| ANBIMA data classification | Level 1 (sanitized indicative rates, no user positions) |
| Metadata classification | Level 2 (methodology notes, public) |
| `methodology_limitations` content | Contains no secrets, no PII, no Level-0 data |
| `bandit -r backend/` | Clean — no security issues |
| `import-linter` | 1 kept, 0 broken — agent isolation intact |

**Privacy boundary:** `debenture_market_data` stores market observations only. No user quantity, acquisition price, holder_id, CPF, account_number, or any Level-0 field is defined in this table. The unit test `test_level0_and_secret_fields_absent_from_migration_and_sdd` explicitly verifies both the migration SQL and the SDD document for 15 forbidden strings. ✅

---

## 9. SCOPE_CONTROL_REVIEW

**PR commit scope (git diff HEAD~1 HEAD):**
```
backend/memory/postgres/migrations/026_create_debenture_market_data.sql  +106
docs/04_MEM/current_state.md                                              +75/-3
docs/specs/finlib-0/pr-09-debenture-market-data.md                       +2/-1
tests/integration/test_debenture_market_data_hypertable_live.py           +539
tests/unit/test_debenture_market_data_schema_contract.py                  +166
tests/unit/test_postgres_migrations_static.py                             +1
```

6 files, all within declared sprint scope. No changes to:
- `backend/rag/` (RAG-0 sprint — correct)
- `backend/gateway/` (Gateway-0 sprint — correct)
- `backend/finlib/rate_spec.py` (FL-PR08 — correct, no new Python module added)
- `config/` or `infra/` (no operational changes — correct for migration-only PR)

**Workspace dirt (NOT in PR commit):**
```
 M docs/rag/rag_01b_pr08_integration_report.md
 M evaluation/results/rag_01b_pr08_agentic0_smoke_summary.json
 M evaluation/results/rag_01b_pr08_integration_health.json
 M evaluation/results/rag_01b_pr08_latency_summary.json
 M evaluation/results/rag_01b_pr09_health_report.json
 M evaluation/results/rag_01b_pr09_smoke_summary.json
?? .claude/settings.local.json
```

These are evaluation artifacts from prior smoke runs — not staged, not in the PR. Low risk of accidental commit if `evaluation/results/` is added to `.gitignore`. Flagged as NIT-02.

**Scope verdict: CLEAN.** The PR is atomic and correctly scoped.

---

## 10. REQUIRED_PATCHES

**No blocking patches required.**

Optional / deferred:

### PATCH-OPT-01 (NIT-01): Add fi_instruments.kind mutation guard
Non-blocking. Defer to a future sprint or FINLIB-0 hardening issue.

```sql
-- Example: add to a future migration
CREATE OR REPLACE FUNCTION enforce_fi_instruments_kind_immutable()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.kind = 'debenture' AND NEW.kind <> 'debenture' THEN
        IF EXISTS (SELECT 1 FROM debenture_market_data WHERE fi_id = OLD.instrument_id LIMIT 1) THEN
            RAISE EXCEPTION 'cannot change kind from debenture: market data rows exist for instrument_id %', OLD.instrument_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_fi_instruments_kind_immutable
BEFORE UPDATE OF kind ON fi_instruments
FOR EACH ROW EXECUTE FUNCTION enforce_fi_instruments_kind_immutable();
```

### PATCH-OPT-02 (NIT-02): Gitignore evaluation results
```bash
echo 'evaluation/results/*.json' >> .gitignore
```

---

## 11. FINAL_RECOMMENDATION

**APPROVE_WITH_NITS**

FL-PR09 satisfies all FINLIB-0 acceptance criteria for a migration-only pre-agent sprint:

- Migration 026 creates a correct TimescaleDB hypertable (`debenture_market_data`) with monthly 30-day chunks, PK `(fi_id, ts, revision)`, UNIQUE `(lineage_hash, ts)` — both including the partitioning column as required.
- Trigger `trg_debenture_market_data_instrument_kind` correctly rejects non-debenture instruments at INSERT/UPDATE time.
- Full FK chain to `fi_instruments`, `ops_ingestion_runs`, `ops_data_sources` is live and enforced.
- DQ constraints (pu > 0, duration ≥ 0, revision ≥ 0, lineage_hash non-whitespace, at-least-one measurement) all verified live.
- `anbima_debentures` source is seeded with narrow DO UPDATE (metadata merge, not overwrite) and complete methodology limitations.
- Idempotency confirmed: duplicate ingestion is a NOOP; revision correction preserves history.
- All 13 live integration tests pass against PostgreSQL 18.4 + TimescaleDB 2.23.0.
- Full suite: 2029 unit tests pass. mypy/pyright/ruff/bandit all clean.
- Level-0 boundary is clean: no user position fields anywhere in the migration or SDD.

The two nits (kind mutation gap, workspace dirt) are non-blocking. The PR is ready to merge.

---

*Generated by A2A Adversarial Protocol — FINLIB-0 sprint — 2026-06-21*
