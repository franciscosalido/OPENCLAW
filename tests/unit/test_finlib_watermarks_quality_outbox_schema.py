from __future__ import annotations

from pathlib import Path


MIGRATIONS_DIR = Path("backend/memory/postgres/migrations")
MIGRATION = MIGRATIONS_DIR / "020_create_ops_watermarks_quality_outbox.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _compact_sql() -> str:
    return " ".join(_sql().split())


def test_migration_020_exists() -> None:
    assert MIGRATION.exists()


def test_migration_is_scoped_non_destructive_and_public_prefix_only() -> None:
    sql = _sql().lower()

    assert "drop table" not in sql
    assert "create schema" not in sql
    assert "ops." not in sql
    assert "audit_agent_writes" not in sql
    for forbidden in (
        "macro_series_catalog",
        "macro_observations",
        "tesouro",
        "cvm",
        "debenture",
        "fundamental",
        "marketlibraryseederagent",
        "researchlibrarycuratoragent",
        "treasurymtagent",
        "pydanticai",
        "langgraph",
        "crewai",
        "fastapi",
        "redis",
        "celery",
        "kafka",
    ):
        assert forbidden not in sql


def test_migration_creates_exact_ops_tables_for_pr03() -> None:
    sql = _sql()

    assert "CREATE TABLE IF NOT EXISTS ops_ingestion_watermarks" in sql
    assert "CREATE TABLE IF NOT EXISTS ops_data_quality_checks" in sql
    assert "CREATE TABLE IF NOT EXISTS ops_outbox_events" in sql
    assert sql.count("CREATE TABLE IF NOT EXISTS ops_") == 3


def test_watermarks_contract() -> None:
    sql = _compact_sql()

    assert "PRIMARY KEY (source_id, dataset)" in sql
    assert "source_id TEXT NOT NULL REFERENCES ops_data_sources (source_id)" in sql
    assert "dataset TEXT NOT NULL CHECK (dataset ~ '\\S')" in sql
    assert "watermark_value TEXT NOT NULL CHECK (watermark_value ~ '\\S')" in sql
    assert "watermark_ts TIMESTAMPTZ" in sql
    assert "source_snapshot_hash TEXT CHECK" in sql
    assert "source_snapshot_hash IS NULL OR source_snapshot_hash ~ '\\S'" in sql
    assert "run_id UUID REFERENCES ops_ingestion_runs (run_id)" in sql
    assert "metadata JSONB NOT NULL DEFAULT '{}'::JSONB" in sql
    assert "jsonb_typeof(metadata) = 'object'" in sql.lower()


def test_watermark_direct_update_regression_guard_exists() -> None:
    sql = _sql()

    assert "prevent_ops_watermark_regression" in sql
    assert "CREATE OR REPLACE TRIGGER trg_ops_watermark_no_regression" in sql
    assert "NEW.watermark_ts < OLD.watermark_ts" in sql
    assert "OLD.watermark_ts IS NOT NULL AND NEW.watermark_ts IS NULL" in sql


def test_data_quality_checks_contract() -> None:
    sql = _compact_sql()

    assert "check_id UUID PRIMARY KEY DEFAULT uuidv7()" in sql
    assert "run_id UUID NOT NULL REFERENCES ops_ingestion_runs (run_id)" in sql
    assert "check_name TEXT NOT NULL CHECK (check_name ~ '\\S')" in sql
    assert "target_table TEXT NOT NULL CHECK (target_table ~ '\\S')" in sql
    assert "severity TEXT NOT NULL" in sql
    assert "severity IN ('info', 'warning', 'error', 'critical')" in sql
    for field in ("observed", "expected", "metadata"):
        assert f"{field} JSONB NOT NULL DEFAULT '{{}}'::JSONB" in sql
        assert f"jsonb_typeof({field}) = 'object'" in sql.lower()


def test_outbox_contract() -> None:
    sql = _compact_sql()

    assert "event_id UUID PRIMARY KEY DEFAULT uuidv7()" in sql
    assert "event_type TEXT NOT NULL CHECK (event_type ~ '\\S')" in sql
    assert "aggregate_type TEXT NOT NULL CHECK (aggregate_type ~ '\\S')" in sql
    assert "aggregate_id TEXT NOT NULL CHECK (aggregate_id ~ '\\S')" in sql
    assert "payload JSONB NOT NULL DEFAULT '{}'::JSONB" in sql
    assert "status TEXT NOT NULL DEFAULT 'pending'" in sql
    assert (
        "status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')" in sql
    )
    assert "attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0)" in sql
    assert "max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts > 0)" in sql
    assert "CHECK (attempts <= max_attempts)" in sql
    assert "locked_by TEXT CHECK (locked_by IS NULL OR locked_by ~ '\\S')" in sql
    assert "run_id UUID REFERENCES ops_ingestion_runs (run_id)" in sql
    assert "metadata JSONB NOT NULL DEFAULT '{}'::JSONB" in sql


def test_outbox_partial_index_and_poll_contract() -> None:
    sql = _compact_sql()

    assert "idx_ops_outbox_pending" in sql
    assert "ON ops_outbox_events (next_attempt_at, created_at)" in sql
    assert "WHERE status = 'pending'" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "next_attempt_at <= now()" in sql
    assert "ORDER BY created_at" in sql
