from __future__ import annotations

from pathlib import Path

import pytest

from backend.memory.postgres.migrations import (
    MigrationFile,
    check_applied_checksum,
    compute_checksum,
    list_migration_files,
    plan_pending_migrations,
)


MIGRATIONS_DIR = Path("backend/memory/postgres/migrations")


def test_migration_files_exist_and_are_ordered() -> None:
    migrations = list_migration_files(MIGRATIONS_DIR)
    names = [migration.version for migration in migrations]

    assert names == sorted(names)
    assert names == [
        "000_create_schema_migrations",
        "001_enable_memory_extensions",
        "002_create_sessions",
        "003_create_turns",
        "004_create_agent_states",
        "005_create_entity_mentions",
    ]


def test_no_migration_file_is_empty() -> None:
    for migration in list_migration_files(MIGRATIONS_DIR):
        assert migration.sql.strip()


def test_migrations_use_if_not_exists_where_applicable() -> None:
    for migration in list_migration_files(MIGRATIONS_DIR):
        sql = migration.sql.upper()
        assert "IF NOT EXISTS" in sql or migration.version.startswith("005_")


def test_schema_migrations_migration_exists() -> None:
    sql = (MIGRATIONS_DIR / "000_create_schema_migrations.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in sql
    assert "checksum" in sql


def test_compute_checksum_is_sha256_hex() -> None:
    checksum = compute_checksum("SELECT 1;\n")

    assert len(checksum) == 64
    assert all(char in "0123456789abcdef" for char in checksum)


def test_checksum_drift_is_rejected() -> None:
    migration = MigrationFile(
        version="001_example",
        path=Path("001_example.sql"),
        sql="SELECT 1;",
        checksum=compute_checksum("SELECT 1;"),
    )

    with pytest.raises(RuntimeError, match="checksum drift"):
        check_applied_checksum(migration, applied_checksum="different")


def test_migration_planning_is_idempotent_for_fake_state() -> None:
    migrations = (
        MigrationFile("001_a", Path("001_a.sql"), "SELECT 1;", "aaa"),
        MigrationFile("002_b", Path("002_b.sql"), "SELECT 2;", "bbb"),
    )
    first_plan = plan_pending_migrations(migrations, applied_checksums={})
    second_plan = plan_pending_migrations(
        migrations,
        applied_checksums={"001_a": "aaa", "002_b": "bbb"},
    )

    assert [migration.version for migration in first_plan] == ["001_a", "002_b"]
    assert second_plan == ()
