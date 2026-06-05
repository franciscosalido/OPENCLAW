from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_pr09_working_memory_checkpoint_sql_is_non_destructive_contract() -> None:
    sql = Path("infra/postgres/sql/011_working_memory_checkpoint_contract.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS working_memory_checkpoints" in sql
    assert "DROP TABLE" not in sql
    assert "redis" not in sql.lower()
    assert "fast backend" not in sql.lower()
