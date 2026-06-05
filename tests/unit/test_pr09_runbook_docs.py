from __future__ import annotations

from pathlib import Path


def test_postgres_backup_restore_runbook_contains_safe_commands() -> None:
    text = Path("docs/runbooks/postgres_backup_restore.md").read_text(encoding="utf-8")

    for token in ("./infra/postgres/backup.sh", "./infra/postgres/restore_verify.sh", "manifest", "nunca usar down -v"):
        assert token in text


def test_quimera_recovery_runbook_contains_operational_steps() -> None:
    text = Path("docs/runbooks/quimera_recovery_runbook.md").read_text(encoding="utf-8")

    for token in ("./run_smoke.sh --quick", "pg_stat_report", "Agentic0", "working memory", "restore"):
        assert token in text
