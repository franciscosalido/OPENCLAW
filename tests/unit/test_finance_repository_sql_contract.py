from __future__ import annotations

from pathlib import Path


REPOSITORY = Path("backend/temporal/finance_repository.py")


def _source() -> str:
    return REPOSITORY.read_text(encoding="utf-8")


def test_finance_repository_uses_asyncpg_and_no_heavy_orm() -> None:
    source = _source().lower()
    assert "asyncpg" in source
    for forbidden in ("sqlalchemy", "django", "peewee", "tortoise", "pony"):
        assert forbidden not in source


def test_finance_repository_uses_parameterized_sql() -> None:
    source = _source()
    for token in ("$1", "$2"):
        assert token in source
    assert "DROP TABLE" not in source
    assert 'f"SELECT' not in source
    assert "f'SELECT" not in source
    assert 'f"INSERT' not in source
    assert "f'INSERT" not in source
    assert ".format(" not in source


def test_order_by_direction_is_branch_controlled() -> None:
    source = _source()
    assert "query = ascending_query if ascending else descending_query" in source
    assert "ORDER BY ts ASC" in source
    assert "ORDER BY ts DESC" in source
    assert "{direction}" not in source
    assert ".replace(" not in source
