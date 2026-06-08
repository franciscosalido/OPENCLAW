from __future__ import annotations

import ast
from pathlib import Path


PACKAGE = Path("backend/memory/postgres")
FORBIDDEN_IMPORTS = {
    "sqlalchemy",
    "django",
    "peewee",
    "tortoise",
    "pony",
    "py2neo",
    "neo4j",
}


def _python_files() -> list[Path]:
    return sorted(PACKAGE.glob("*.py"))


def test_postgres_package_does_not_import_orms() -> None:
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
        assert imported_roots.isdisjoint(FORBIDDEN_IMPORTS), path


def test_no_model_inherits_from_orm_base() -> None:
    for path in _python_files():
        source = path.read_text(encoding="utf-8")
        assert "(Base)" not in source
        assert "declarative_base" not in source
        assert "models.Model" not in source


def test_client_uses_asyncpg_directly() -> None:
    source = (PACKAGE / "client.py").read_text(encoding="utf-8")
    assert "asyncpg" in source
    assert "create_pool" in source
