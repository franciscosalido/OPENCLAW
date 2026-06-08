"""Synthetic HybridRAG fixture for PR-08."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

DENSE_VECTOR_NAME = "text-dense"
SPARSE_VECTOR_NAME = "text-sparse"
COLLECTION_PREFIX = "quimera_pr08_hybrid_smoke_"
PROTECTED_COLLECTIONS = frozenset(
    {"quimera_knowledge", "quimera_query_cache", "quimera_llm_cache"}
)


@dataclass(frozen=True, slots=True)
class SyntheticHybridDocument:
    doc_id: str
    title: str
    safe_summary: str
    expected_keywords: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HybridSearchResult:
    doc_id: str
    score: float
    source: str


class HybridContractSummary(TypedDict):
    collection: str
    quality_mode: str
    quality_evidence: str
    retrieval_backend: str
    live_quality_checked: bool
    live_quality_required: bool
    quality_warning: str | None
    dense_ok: bool
    sparse_ok: bool
    hybrid_ok: bool
    hybrid_recall_at_5: float
    dense_recall_at_5: float
    result_count: int


SYNTHETIC_DOCS: tuple[SyntheticHybridDocument, ...] = (
    SyntheticHybridDocument(
        "doc-solar",
        "Alpha Solar",
        "solar panels and battery storage",
        ("solar", "battery"),
    ),
    SyntheticHybridDocument(
        "doc-steel",
        "Alpha Steel",
        "steel production and industrial alloys",
        ("steel", "alloy"),
    ),
    SyntheticHybridDocument(
        "doc-memory",
        "Quimera Memory",
        "Postgres sessions and agent state",
        ("postgres", "session"),
    ),
    SyntheticHybridDocument(
        "doc-qdrant",
        "Quimera Vectors",
        "Qdrant hybrid dense sparse retrieval",
        ("qdrant", "hybrid"),
    ),
    SyntheticHybridDocument(
        "doc-mcp", "MCP Tools", "local MCP tools over Streamable HTTP", ("mcp", "tool")
    ),
    SyntheticHybridDocument(
        "doc-otel",
        "OTel Safety",
        "safe trace identifiers and metadata",
        ("otel", "trace"),
    ),
    SyntheticHybridDocument(
        "doc-litellm",
        "LiteLLM Gateway",
        "host gateway for OpenAI compatible model calls",
        ("litellm", "gateway"),
    ),
    SyntheticHybridDocument(
        "doc-ollama", "Ollama Runtime", "local qwen model runtime", ("ollama", "qwen")
    ),
    SyntheticHybridDocument(
        "doc-timescale",
        "Temporal Memory",
        "Timescale temporal events",
        ("timescale", "temporal"),
    ),
    SyntheticHybridDocument(
        "doc-agentic0", "Agentic0", "deterministic smoke agent", ("agentic0", "smoke")
    ),
)


def collection_name(run_id: str) -> str:
    clean = "".join(ch for ch in run_id.lower() if ch.isalnum() or ch in {"_", "-"})
    return f"{COLLECTION_PREFIX}{clean}"


def assert_safe_cleanup_collection(name: str) -> None:
    if name in PROTECTED_COLLECTIONS or not name.startswith(COLLECTION_PREFIX):
        raise ValueError("refusing to cleanup non-PR08 smoke collection")


def synthetic_dense_scores(query: str) -> list[HybridSearchResult]:
    return _rank(query, source="dense", lexical_weight=0.35)


def synthetic_sparse_scores(query: str) -> list[HybridSearchResult]:
    return _rank(query, source="sparse", lexical_weight=0.85)


def synthetic_hybrid_rrf(query: str) -> list[HybridSearchResult]:
    dense = synthetic_dense_scores(query)
    sparse = synthetic_sparse_scores(query)
    scores: dict[str, float] = {}
    for ranked in (dense, sparse):
        for index, result in enumerate(ranked):
            scores[result.doc_id] = scores.get(result.doc_id, 0.0) + 1.0 / (
                60.0 + index + 1
            )
    return [
        HybridSearchResult(doc_id=doc_id, score=score, source="hybrid")
        for doc_id, score in sorted(
            scores.items(), key=lambda item: item[1], reverse=True
        )
    ]


def compute_recall_at_k(
    results: list[HybridSearchResult], expected_doc_ids: set[str], *, k: int = 5
) -> float:
    if not expected_doc_ids:
        return 0.0
    seen = {result.doc_id for result in results[:k]}
    return len(seen & expected_doc_ids) / len(expected_doc_ids)


def hybrid_contract_summary(run_id: str = "unit") -> HybridContractSummary:
    query = "postgres qdrant hybrid smoke"
    dense = synthetic_dense_scores(query)
    sparse = synthetic_sparse_scores(query)
    hybrid = synthetic_hybrid_rrf(query)
    expected = {"doc-memory", "doc-qdrant", "doc-agentic0"}
    return {
        "collection": collection_name(run_id),
        "quality_mode": "offline_synthetic_fixture",
        "quality_evidence": "deterministic_rrf_fixture",
        "retrieval_backend": "qdrant_query_api_rrf_contract",
        "live_quality_checked": False,
        "live_quality_required": True,
        "quality_warning": "live_nomic_hybrid_validation_required",
        "dense_ok": bool(dense),
        "sparse_ok": bool(sparse),
        "hybrid_ok": bool(hybrid),
        "hybrid_recall_at_5": compute_recall_at_k(hybrid, expected),
        "dense_recall_at_5": compute_recall_at_k(dense, expected),
        "result_count": len(hybrid),
    }


async def ensure_hybrid_collection(client: Any, name: str) -> None:
    assert_safe_cleanup_collection(name)
    from qdrant_client import models

    await client.create_collection(
        collection_name=name,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(
                size=4, distance=models.Distance.COSINE
            )
        },
        sparse_vectors_config={SPARSE_VECTOR_NAME: models.SparseVectorParams()},
    )


async def cleanup_test_collection(client: Any, name: str) -> None:
    assert_safe_cleanup_collection(name)
    await client.delete_collection(collection_name=name)


def _rank(
    query: str, *, source: str, lexical_weight: float
) -> list[HybridSearchResult]:
    query_terms = set(query.lower().split())
    results: list[HybridSearchResult] = []
    for doc in SYNTHETIC_DOCS:
        overlap = len(query_terms & set(doc.expected_keywords))
        semantic_bonus = (
            0.2
            if "quimera" in doc.title.lower() or "agentic0" in doc.title.lower()
            else 0.0
        )
        score = overlap * lexical_weight + semantic_bonus
        if score > 0:
            results.append(HybridSearchResult(doc.doc_id, round(score, 6), source))
    return sorted(results, key=lambda item: item.score, reverse=True)
