from __future__ import annotations

from pathlib import Path


MIGRATION = Path(
    "backend/memory/postgres/migrations/029_create_finlib_aggregates_readiness.sql"
)
DOCS = (
    Path("docs/specs/finlib-0/pr-14-aggregates-readiness-closeout.md"),
    Path("docs/sprints/FINLIB0_DONE_CRITERIA.md"),
    Path("docs/sprints/FINLIB0_HANDOFF_TO_DATA_AGENTS.md"),
)

DESTRUCTIVE_SQL = (
    "add_retention_policy",
    "drop_chunks",
    "delete from",
    "truncate",
    "drop table",
)


def test_closeout_migration_has_no_destructive_retention_or_deletion() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    for token in DESTRUCTIVE_SQL:
        assert token not in sql
    assert "retention policies" in sql
    assert "intentionally absent in v1" in sql


def test_closeout_docs_state_no_destructive_retention() -> None:
    for path in DOCS:
        text = path.read_text(encoding="utf-8").lower()
        assert "destructive retention" in text
        assert "no" in text or "prohibited" in text
