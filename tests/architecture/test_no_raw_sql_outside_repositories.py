from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path("backend")
ALLOWED_SQL_ROOTS = (
    Path("backend/finlib/repositories"),
    Path("backend/memory/postgres"),
)
LEGACY_SQL_MODULES = {
    Path("backend/temporal/finance_repository.py"),
    Path("backend/temporal/timescale.py"),
    Path("backend/working_memory/checkpoint_repository.py"),
}
SQL_TOKENS = (
    "CREATE TABLE",
    "DELETE FROM",
    "FOR UPDATE",
    "INSERT INTO",
    "ON CONFLICT",
    "SELECT ",
    "SKIP LOCKED",
    "UPDATE ",
)
SQL_START_TOKENS = tuple(token.strip() for token in SQL_TOKENS)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if ".venv" not in path.parts)


def _string_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value.upper())
    return values


def _is_allowed(path: Path) -> bool:
    return any(path.is_relative_to(root) for root in ALLOWED_SQL_ROOTS)


def _looks_like_sql(literal: str) -> bool:
    stripped = literal.strip().upper()
    if not stripped:
        return False
    return "\n" in literal and stripped.startswith(SQL_START_TOKENS)


def test_raw_sql_is_confined_to_repositories_migrations_or_known_legacy_modules() -> (
    None
):
    offenders: list[str] = []
    for path in _python_files(BACKEND):
        if _is_allowed(path) or path in LEGACY_SQL_MODULES:
            continue
        if any(_looks_like_sql(literal) for literal in _string_literals(path)):
            offenders.append(str(path))

    assert offenders == []


def test_known_legacy_sql_modules_are_explicitly_documented() -> None:
    for path in LEGACY_SQL_MODULES:
        assert path.exists(), path
