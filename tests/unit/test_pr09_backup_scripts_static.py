from __future__ import annotations

from pathlib import Path


BACKUP = Path("infra/postgres/backup.sh")
RESTORE = Path("infra/postgres/restore_verify.sh")
SANDBOX_DOCKERFILE = Path("Dockerfile.openclaw-sandbox")


def test_backup_script_uses_custom_pg_dump_and_safe_manifest() -> None:
    text = BACKUP.read_text(encoding="utf-8")

    assert "set -euo pipefail" in text
    assert "pg_dump" in text
    assert "-Fc" in text
    assert "container_pg_tools_available" in text
    assert "docker exec -i" in text
    assert "backup_manifest.py" in text
    assert "chmod 600" in text
    assert "QUIMERA_POSTGRES_DSN" in text
    assert "postgresql://" not in text
    assert "echo ${QUIMERA_POSTGRES_DSN}" not in text


def test_restore_script_uses_temp_database_and_prefix_guard() -> None:
    text = RESTORE.read_text(encoding="utf-8")

    assert "set -euo pipefail" in text
    assert "pg_restore" in text
    assert "container_pg_tools_available" in text
    assert "docker exec -i" in text
    assert "timescaledb_pre_restore()" in text
    assert "timescaledb_post_restore()" in text
    assert "quimera_restore_verify_" in text
    assert "DROP DATABASE" in text
    assert "quimera_restore_verify_" in text.split("DROP DATABASE", 1)[1]
    assert "--clean" not in text
    assert "QUIMERA_BACKUP_KEEP_RESTORE_DB" in text
    assert "postgresql://" not in text


def test_backup_restore_scripts_do_not_use_destructive_volume_commands() -> None:
    combined = BACKUP.read_text(encoding="utf-8") + RESTORE.read_text(encoding="utf-8")

    for forbidden in ("down -v", "docker system prune", "docker volume rm"):
        assert forbidden not in combined


def test_openclaw_sandbox_uses_postgresql_18_client_tools() -> None:
    text = SANDBOX_DOCKERFILE.read_text(encoding="utf-8")

    assert "apt.postgresql.org/pub/repos/apt" in text
    assert "postgresql-client-18" in text
    assert "/usr/lib/postgresql/18/bin" in text
