from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from backend.memory import policy


POLICY_PATH = Path("backend/memory/policy.py")
MEMORY_POLICY_DOC = Path("docs/specs/memory_policy.md")
ADR_PATH = Path("docs/ADR/ADR-006-qdrant-postgres-pgvector-boundary.md")


def test_policy_module_imports_without_runtime_clients() -> None:
    module = importlib.import_module("backend.memory.policy")

    assert module.PRIMARY_SEMANTIC_RETRIEVER is policy.MemoryBackend.QDRANT


def test_primary_semantic_retriever_is_qdrant() -> None:
    assert policy.PRIMARY_SEMANTIC_RETRIEVER is policy.MemoryBackend.QDRANT
    assert policy.is_primary_semantic_retriever(policy.MemoryBackend.QDRANT)
    assert policy.is_primary_semantic_retriever("qdrant")


@pytest.mark.parametrize(
    "role",
    [
        policy.MemoryRole.PRIMARY_SEMANTIC_RETRIEVER,
        policy.MemoryRole.HYBRID_RAG,
        policy.MemoryRole.DENSE_RETRIEVAL,
        policy.MemoryRole.SPARSE_RETRIEVAL,
    ],
)
def test_qdrant_allows_semantic_retrieval_roles(role: policy.MemoryRole) -> None:
    policy.assert_role_allowed(policy.MemoryBackend.QDRANT, role)


@pytest.mark.parametrize(
    "backend",
    [
        policy.MemoryBackend.POSTGRES,
        policy.MemoryBackend.TIMESCALEDB,
        policy.MemoryBackend.PGVECTOR,
        policy.MemoryBackend.MARKDOWN,
    ],
)
def test_non_qdrant_backends_reject_primary_semantic_retrieval(
    backend: policy.MemoryBackend,
) -> None:
    with pytest.raises(ValueError, match="primary_semantic_retriever"):
        policy.assert_role_allowed(
            backend,
            policy.MemoryRole.PRIMARY_SEMANTIC_RETRIEVER,
        )


def test_pgvector_rejects_hybrid_rag() -> None:
    with pytest.raises(ValueError, match="hybrid_rag"):
        policy.assert_role_allowed(policy.MemoryBackend.PGVECTOR, "hybrid_rag")


def test_pgvector_authorized_uses_are_limited() -> None:
    assert policy.PGVECTOR_AUTHORIZED_USES == frozenset(
        {
            "embedding_checkpoint",
            "ab_model_comparison",
            "controlled_fallback",
        }
    )


@pytest.mark.parametrize(
    "use_case",
    [
        "primary_retriever",
        "primary_semantic_retriever",
        "hybrid_rag_primary",
        "semantic_cache_primary",
    ],
)
def test_validate_pgvector_use_rejects_primary_roles(use_case: str) -> None:
    with pytest.raises(ValueError, match="not authorized"):
        policy.validate_pgvector_use(use_case)


@pytest.mark.parametrize("use_case", sorted(policy.PGVECTOR_AUTHORIZED_USES))
def test_validate_pgvector_use_accepts_authorized_uses(use_case: str) -> None:
    policy.validate_pgvector_use(use_case)


def test_finlib_forbidden_import_prefixes_include_qdrant_and_llm_clients() -> None:
    assert "qdrant_client" in policy.FINLIB_FORBIDDEN_IMPORT_PREFIXES
    assert "backend.rag" in policy.FINLIB_FORBIDDEN_IMPORT_PREFIXES
    assert "openai" in policy.FINLIB_FORBIDDEN_IMPORT_PREFIXES
    assert "anthropic" in policy.FINLIB_FORBIDDEN_IMPORT_PREFIXES
    assert "litellm" in policy.FINLIB_FORBIDDEN_IMPORT_PREFIXES
    assert "ollama" in policy.FINLIB_FORBIDDEN_IMPORT_PREFIXES


def test_policy_module_has_no_runtime_client_imports() -> None:
    forbidden = {
        "anthropic",
        "asyncpg",
        "httpx",
        "litellm",
        "ollama",
        "openai",
        "psycopg",
        "qdrant_client",
        "requests",
        "sqlalchemy",
    }
    tree = ast.parse(POLICY_PATH.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert imports.isdisjoint(forbidden)


def test_memory_policy_doc_mentions_all_authorized_pgvector_uses() -> None:
    text = MEMORY_POLICY_DOC.read_text(encoding="utf-8")

    for use_case in policy.PGVECTOR_AUTHORIZED_USES:
        assert use_case in text


def test_adr_exists_and_records_boundary_decision() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")

    assert "Status: Accepted" in text
    assert "Qdrant is the primary semantic and hybrid RAG retriever" in text
    assert "pgvector is auxiliary only" in text
    assert "PostgreSQL/TimescaleDB" in text
