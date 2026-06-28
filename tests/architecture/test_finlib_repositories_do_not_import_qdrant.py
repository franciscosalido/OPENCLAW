from __future__ import annotations

import ast
from pathlib import Path

from backend.memory.policy import FINLIB_FORBIDDEN_IMPORT_PREFIXES


FINLIB = Path("backend/finlib")
REPOSITORIES = FINLIB / "repositories"
POLICY_PATH = Path("backend/memory/policy.py")


def _python_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.py") if ".venv" not in path.parts)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _is_forbidden(imported: str) -> bool:
    return any(
        imported == prefix or imported.startswith(f"{prefix}.")
        for prefix in FINLIB_FORBIDDEN_IMPORT_PREFIXES
    )


def test_finlib_does_not_import_qdrant_rag_llm_or_http_clients() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _python_files(FINLIB):
        bad = [imported for imported in _imports(path) if _is_forbidden(imported)]
        if bad:
            offenders[str(path)] = sorted(bad)

    assert offenders == {}


def test_finlib_repositories_do_not_import_qdrant_or_rag() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _python_files(REPOSITORIES):
        bad = [
            imported
            for imported in _imports(path)
            if imported == "qdrant_client"
            or imported.startswith("qdrant_client.")
            or imported == "backend.rag"
            or imported.startswith("backend.rag.")
        ]
        if bad:
            offenders[str(path)] = sorted(bad)

    assert offenders == {}


def test_memory_policy_module_is_self_contained() -> None:
    forbidden = {
        "anthropic",
        "asyncpg",
        "httpx",
        "litellm",
        "ollama",
        "openai",
        "psycopg",
        "psycopg2",
        "qdrant_client",
        "requests",
        "sqlalchemy",
    }
    imports = _imports(POLICY_PATH)

    assert imports.isdisjoint(forbidden)
