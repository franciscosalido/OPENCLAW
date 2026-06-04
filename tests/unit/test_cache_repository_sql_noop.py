from __future__ import annotations

import ast
from pathlib import Path


CACHE_ROOT = Path("backend/rag/cache")


def _imported_roots() -> set[str]:
    roots: set[str] = set()
    for path in CACHE_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_cache_module_has_no_sql_or_runtime_service_imports() -> None:
    forbidden = {
        "sqlalchemy",
        "django",
        "peewee",
        "tortoise",
        "pony",
        "asyncpg",
        "fastapi",
        "grpc",
        "mcp",
        "torch",
        "transformers",
        "langchain",
        "llama_index",
        "openai",
    }

    assert _imported_roots().isdisjoint(forbidden)


def test_cache_layer_uses_qdrant_async_client_contract() -> None:
    source = (CACHE_ROOT / "cache_layer.py").read_text(encoding="utf-8")

    assert "AsyncQdrantClient" in source
    assert "query_points" in source
