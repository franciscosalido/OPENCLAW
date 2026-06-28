"""Executable memory-boundary policy for QUIMERA.

This module is intentionally pure: no filesystem access, no environment reads,
no database client imports and no network clients. It exists so architecture
tests can import the memory boundary as code.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MemoryBackend(StrEnum):
    """Storage and handoff backends recognized by the memory boundary."""

    POSTGRES = "postgres"
    TIMESCALEDB = "timescaledb"
    QDRANT = "qdrant"
    PGVECTOR = "pgvector"
    MARKDOWN = "markdown"


class MemoryRole(StrEnum):
    """Architectural roles assigned to memory backends."""

    TEMPORAL_SERIES = "temporal_series"
    RELATIONAL_STATE = "relational_state"
    OPERATIONAL_STATE = "operational_state"
    AUDIT_TRAIL = "audit_trail"
    FINANCIAL_METADATA = "financial_metadata"
    EPISODIC_LONG_TERM_MEMORY = "episodic_long_term_memory"
    CONCEPTUAL_LONG_TERM_MEMORY = "conceptual_long_term_memory"
    DECISION_PROVENANCE = "decision_provenance"
    PRIMARY_SEMANTIC_RETRIEVER = "primary_semantic_retriever"
    HYBRID_RAG = "hybrid_rag"
    DENSE_RETRIEVAL = "dense_retrieval"
    SPARSE_RETRIEVAL = "sparse_retrieval"
    MULTIVECTOR_RETRIEVAL = "multivector_retrieval"
    RRF_DBSF = "rrf_dbsf"
    SEMANTIC_CACHE = "semantic_cache"
    AUXILIARY_VECTOR_CHECKPOINT = "auxiliary_vector_checkpoint"
    EXPERIMENTAL_EMBEDDING_STORE = "experimental_embedding_store"
    CONTROLLED_FALLBACK = "controlled_fallback"
    HUMAN_HANDOFF = "human_handoff"
    HUMAN_REPORTING = "human_reporting"


@dataclass(frozen=True, slots=True)
class MemoryBoundaryRule:
    """Allowed and forbidden roles for one backend."""

    backend: MemoryBackend
    allowed_roles: frozenset[MemoryRole]
    forbidden_roles: frozenset[MemoryRole]


PRIMARY_SEMANTIC_RETRIEVER: MemoryBackend = MemoryBackend.QDRANT

PGVECTOR_AUTHORIZED_USES = frozenset(
    {
        "embedding_checkpoint",
        "ab_model_comparison",
        "controlled_fallback",
    }
)

FINLIB_FORBIDDEN_IMPORT_PREFIXES = frozenset(
    {
        "anthropic",
        "backend.memory.qdrant",
        "backend.rag",
        "httpx",
        "langchain",
        "litellm",
        "ollama",
        "openai",
        "qdrant_client",
        "requests",
    }
)

RAG_FORBIDDEN_IMPORT_PREFIXES = frozenset(
    {
        "asyncpg",
        "backend.finlib",
        "psycopg",
        "psycopg2",
        "sqlalchemy",
    }
)

_PRIMARY_RETRIEVER_ROLES = frozenset(
    {
        MemoryRole.PRIMARY_SEMANTIC_RETRIEVER,
        MemoryRole.HYBRID_RAG,
    }
)

MEMORY_BOUNDARY_RULES = {
    MemoryBackend.POSTGRES: MemoryBoundaryRule(
        backend=MemoryBackend.POSTGRES,
        allowed_roles=frozenset(
            {
                MemoryRole.TEMPORAL_SERIES,
                MemoryRole.RELATIONAL_STATE,
                MemoryRole.OPERATIONAL_STATE,
                MemoryRole.AUDIT_TRAIL,
                MemoryRole.FINANCIAL_METADATA,
                MemoryRole.EPISODIC_LONG_TERM_MEMORY,
                MemoryRole.CONCEPTUAL_LONG_TERM_MEMORY,
                MemoryRole.DECISION_PROVENANCE,
            }
        ),
        forbidden_roles=_PRIMARY_RETRIEVER_ROLES,
    ),
    MemoryBackend.TIMESCALEDB: MemoryBoundaryRule(
        backend=MemoryBackend.TIMESCALEDB,
        allowed_roles=frozenset(
            {
                MemoryRole.TEMPORAL_SERIES,
                MemoryRole.FINANCIAL_METADATA,
            }
        ),
        forbidden_roles=_PRIMARY_RETRIEVER_ROLES,
    ),
    MemoryBackend.QDRANT: MemoryBoundaryRule(
        backend=MemoryBackend.QDRANT,
        allowed_roles=frozenset(
            {
                MemoryRole.PRIMARY_SEMANTIC_RETRIEVER,
                MemoryRole.HYBRID_RAG,
                MemoryRole.DENSE_RETRIEVAL,
                MemoryRole.SPARSE_RETRIEVAL,
                MemoryRole.MULTIVECTOR_RETRIEVAL,
                MemoryRole.RRF_DBSF,
                MemoryRole.SEMANTIC_CACHE,
            }
        ),
        forbidden_roles=frozenset(),
    ),
    MemoryBackend.PGVECTOR: MemoryBoundaryRule(
        backend=MemoryBackend.PGVECTOR,
        allowed_roles=frozenset(
            {
                MemoryRole.AUXILIARY_VECTOR_CHECKPOINT,
                MemoryRole.EXPERIMENTAL_EMBEDDING_STORE,
                MemoryRole.CONTROLLED_FALLBACK,
            }
        ),
        forbidden_roles=_PRIMARY_RETRIEVER_ROLES,
    ),
    MemoryBackend.MARKDOWN: MemoryBoundaryRule(
        backend=MemoryBackend.MARKDOWN,
        allowed_roles=frozenset(
            {
                MemoryRole.HUMAN_HANDOFF,
                MemoryRole.HUMAN_REPORTING,
            }
        ),
        forbidden_roles=_PRIMARY_RETRIEVER_ROLES,
    ),
}


def assert_role_allowed(
    backend: MemoryBackend | str,
    role: MemoryRole | str,
) -> None:
    """Raise ValueError when a backend is not allowed to perform a role."""

    resolved_backend = MemoryBackend(backend)
    resolved_role = MemoryRole(role)
    rule = MEMORY_BOUNDARY_RULES[resolved_backend]
    if resolved_role in rule.forbidden_roles or resolved_role not in rule.allowed_roles:
        raise ValueError(
            f"{resolved_backend.value} is not authorized for role {resolved_role.value}"
        )


def validate_pgvector_use(use_case: str) -> None:
    """Validate a pgvector use case against the explicit allow-list."""

    normalized = use_case.strip().lower()
    if normalized not in PGVECTOR_AUTHORIZED_USES:
        allowed = ", ".join(sorted(PGVECTOR_AUTHORIZED_USES))
        raise ValueError(
            f"pgvector use case {use_case!r} is not authorized. "
            f"Authorized use cases: {allowed}. "
            "Add an ADR and sprint authorization before expanding this list."
        )


def is_primary_semantic_retriever(backend: MemoryBackend | str) -> bool:
    """Return True only for the canonical semantic/hybrid retriever backend."""

    return MemoryBackend(backend) is PRIMARY_SEMANTIC_RETRIEVER
