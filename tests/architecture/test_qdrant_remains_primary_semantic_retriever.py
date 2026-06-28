from __future__ import annotations

import ast
from pathlib import Path

from backend.memory.policy import MemoryBackend, PRIMARY_SEMANTIC_RETRIEVER


RAG = Path("backend/rag")
QDRANT_STORE = RAG / "qdrant_store.py"


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


def test_policy_declares_qdrant_as_primary_semantic_retriever() -> None:
    assert PRIMARY_SEMANTIC_RETRIEVER is MemoryBackend.QDRANT


def test_rag_path_exists_and_qdrant_store_imports_qdrant_client() -> None:
    assert RAG.exists(), "backend/rag must exist; update this boundary test if moved"
    imports = _imports(QDRANT_STORE)

    assert "qdrant_client" in imports


def test_rag_modules_do_not_import_finlib_directly() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _python_files(RAG):
        bad = [
            imported
            for imported in _imports(path)
            if imported == "backend.finlib" or imported.startswith("backend.finlib.")
        ]
        if bad:
            offenders[str(path)] = sorted(bad)

    assert offenders == {}


def test_rag_does_not_use_pgvector_as_primary_retriever() -> None:
    forbidden_phrases = (
        "pgvector_primary",
        'primary_semantic_retriever = "pgvector"',
        'primary_semantic_backend = "pgvector"',
        "pgvector is the primary semantic retriever",
        "pgvector as primary rag",
    )
    offenders: dict[str, list[str]] = {}
    for path in _python_files(RAG):
        text = path.read_text(encoding="utf-8").lower()
        matches = [phrase for phrase in forbidden_phrases if phrase in text]
        if matches:
            offenders[str(path)] = matches

    assert offenders == {}


def test_qdrant_implementation_does_not_import_finlib_or_asyncpg() -> None:
    imports = _imports(QDRANT_STORE)

    assert "asyncpg" not in imports
    assert not any(imported.startswith("backend.finlib") for imported in imports)
