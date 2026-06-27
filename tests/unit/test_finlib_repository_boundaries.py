from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path("backend/finlib")
REPOSITORIES = Path("backend/finlib/repositories")
ALLOWED_SQL_ROOTS = (
    Path("backend/finlib/repositories"),
    Path("backend/memory/postgres/migrations"),
)
FORBIDDEN_IMPORTS = {"sqlalchemy", "sqlmodel", "alembic"}
SQL_TOKENS = (
    "SELECT ",
    "INSERT INTO ",
    "UPDATE ",
    "DELETE FROM ",
    "FOR UPDATE",
    "ON CONFLICT",
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if ".venv" not in path.parts)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports


def test_repository_package_exists_and_exports_core_types() -> None:
    package = (REPOSITORIES / "__init__.py").read_text(encoding="utf-8")

    for expected in (
        "AuditContext",
        "BatchWriteResult",
        "OpsRepository",
        "MacroRepository",
        "TreasuryRepository",
    ):
        assert expected in package


def test_backend_does_not_import_orms() -> None:
    for path in _python_files(BACKEND):
        assert _imports(path).isdisjoint(FORBIDDEN_IMPORTS), path


def test_raw_sql_is_confined_to_repositories_and_migrations() -> None:
    offenders: list[Path] = []
    for path in _python_files(BACKEND):
        if any(path.is_relative_to(root) for root in ALLOWED_SQL_ROOTS):
            continue
        text = path.read_text(encoding="utf-8").upper()
        if any(token in text for token in SQL_TOKENS):
            offenders.append(path)

    assert offenders == []


def test_skip_locked_only_exists_in_ops_repository_and_tests() -> None:
    production_hits = [
        path
        for path in _python_files(BACKEND)
        if "SKIP LOCKED" in path.read_text(encoding="utf-8").upper()
    ]

    assert production_hits == [REPOSITORIES / "ops_repository.py"]


def test_no_agent_ingester_or_remote_client_added_to_finlib_repositories() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in _python_files(REPOSITORIES)
    ).lower()

    for forbidden in ("httpx", "requests", "fastapi", "qdrant", "pgvector"):
        assert forbidden not in combined
