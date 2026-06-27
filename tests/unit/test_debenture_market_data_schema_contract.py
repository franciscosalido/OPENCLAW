from __future__ import annotations

from pathlib import Path


MIGRATION = Path(
    "backend/memory/postgres/migrations/026_create_debenture_market_data.sql"
)
KIND_DRIFT_MIGRATION = Path(
    "backend/memory/postgres/migrations/027_guard_debenture_kind_drift.sql"
)
SDD = Path("docs/specs/finlib-0/pr-09-debenture-market-data.md")

LEVEL0_FORBIDDEN_FIELDS = (
    "quantity",
    "face_value_held",
    "acquisition_price",
    "yield_at_purchase",
    "cpf",
    "holder_id",
    "account_number",
    "broker_id",
    "custodian",
    "portfolio_id",
)
SECRET_FORBIDDEN_FIELDS = (
    "client_id",
    "client_secret",
    "api_key",
    "bearer_token",
    "credentials",
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _compact_sql() -> str:
    return " ".join(_sql().split())


def _kind_drift_sql() -> str:
    return KIND_DRIFT_MIGRATION.read_text(encoding="utf-8")


def _compact_kind_drift_sql() -> str:
    return " ".join(_kind_drift_sql().split())


def _sdd() -> str:
    return SDD.read_text(encoding="utf-8")


def test_migration_026_exists_and_is_non_destructive() -> None:
    sql = _sql().lower()

    assert MIGRATION.exists()
    assert "drop table" not in sql
    assert "truncate" not in sql
    assert "create schema" not in sql
    assert "fi." not in sql
    assert "market." not in sql
    assert "ops." not in sql
    assert "audit." not in sql


def test_scope_is_limited_to_debenture_market_data() -> None:
    lower_sql = _sql().lower()

    assert lower_sql.count("create table if not exists") == 1
    assert "create table if not exists debenture_market_data" in lower_sql
    for forbidden in (
        "cri_market",
        "cra_market",
        "fi_positions",
        "repository",
        "agent",
        "qdrant",
        "vector",
        "httpx",
        "requests",
        "fetch",
        "download",
    ):
        assert forbidden not in lower_sql


def test_migration_and_sdd_exclude_level0_and_secret_fields() -> None:
    lower_sql = _sql().lower()
    lower_sdd = _sdd().lower()

    for field in LEVEL0_FORBIDDEN_FIELDS + SECRET_FORBIDDEN_FIELDS:
        assert field not in lower_sql
        assert field not in lower_sdd


def test_identity_foreign_key_and_revision_contract() -> None:
    compact = _compact_sql()

    assert "fi_id UUID NOT NULL REFERENCES fi_instruments (instrument_id)" in compact
    assert "ts TIMESTAMPTZ NOT NULL" in compact
    assert "revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0)" in compact
    assert "PRIMARY KEY (fi_id, ts, revision)" in compact
    assert "UNIQUE (lineage_hash, ts)" in compact
    assert "UNIQUE (lineage_hash)" not in compact
    assert "isin" not in compact.lower()


def test_measurement_columns_and_dq_contracts() -> None:
    compact = _compact_sql()

    assert "indicative_rate NUMERIC" in compact
    assert "pu NUMERIC CHECK (pu IS NULL OR pu > 0)" in compact
    assert "duration INTEGER CHECK (duration IS NULL OR duration >= 0)" in compact
    assert (
        "indicative_rate IS NOT NULL OR pu IS NOT NULL OR duration IS NOT NULL"
        in compact
    )
    assert "lineage_hash TEXT NOT NULL CHECK (lineage_hash ~ '\\S')" in compact
    assert (
        "schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0)"
        in compact
    )
    assert "CHECK (jsonb_typeof(quality_flags) = 'object')" in compact
    assert "CHECK (jsonb_typeof(metadata) = 'object')" in compact
    assert "btrim(" not in compact.lower()


def test_timescale_hypertable_contract_and_indexes() -> None:
    compact = _compact_sql()
    raw = _sql()

    assert "SELECT create_hypertable(" in compact
    assert "'debenture_market_data'" in compact
    assert "'ts'" in compact
    assert "chunk_time_interval => INTERVAL '1 month'" in compact
    assert "if_not_exists => TRUE" in compact
    assert "idx_debenture_market_data_fi_ts_revision" in compact
    assert "ON debenture_market_data (fi_id, ts DESC, revision DESC)" in compact
    assert "idx_debenture_market_data_run_id" in compact
    assert "CONCURRENTLY is prohibited inside the transactional migration runner" in raw


def test_debenture_kind_trigger_contract() -> None:
    compact = _compact_sql()
    drift_compact = _compact_kind_drift_sql()

    assert "enforce_debenture_market_data_instrument_kind" in compact
    assert (
        "CREATE OR REPLACE TRIGGER trg_debenture_market_data_instrument_kind" in compact
    )
    assert "BEFORE INSERT OR UPDATE OF fi_id ON debenture_market_data" in compact
    assert "kind <> 'debenture'" in compact
    assert "debenture_market_data requires a debenture instrument" in compact
    assert KIND_DRIFT_MIGRATION.exists()
    assert "prevent_debenture_market_data_kind_drift" in drift_compact
    assert (
        "CREATE OR REPLACE TRIGGER "
        "trg_fi_instruments_debenture_market_data_kind_guard" in drift_compact
    )
    assert "BEFORE UPDATE OF kind ON fi_instruments" in drift_compact
    assert "WHEN (old.kind IS DISTINCT FROM new.kind)" in drift_compact
    assert "WHERE fi_id = OLD.instrument_id" in drift_compact
    assert (
        "cannot change fi_instruments.kind while debenture_market_data rows exist"
        in drift_compact
    )


def test_anbima_source_is_narrowly_hardened_for_market_data() -> None:
    compact = _compact_sql()

    assert compact.count("INSERT INTO ops_data_sources") == 1
    assert "'anbima_debentures'" in compact
    assert "ON CONFLICT (source_id) DO UPDATE SET" in compact
    assert "methodology_limitations = excluded.methodology_limitations" in compact
    assert "metadata = ops_data_sources.metadata || jsonb_build_object" in compact
    for term in ("secundario", "amostra", "acesso", "historico", "retificacao"):
        assert term in compact.lower()


def test_sdd_documents_revision_lineage_and_cross_sprint_boundary() -> None:
    sdd = _sdd()

    assert "Revision Semantics" in sdd
    assert "`run_id` is intentionally excluded" in sdd
    assert "Level 1/Level 2" in sdd
    assert "`duration` is measured in business days" in sdd
    assert "append exactly one audit_agent_writes row" in sdd
    assert "Future Repository Transaction Contract" in sdd
