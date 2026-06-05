from __future__ import annotations

import pytest

from integration.hybrid_fixture import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    assert_safe_cleanup_collection,
    collection_name,
    compute_recall_at_k,
    hybrid_contract_summary,
    synthetic_dense_scores,
    synthetic_hybrid_rrf,
    synthetic_sparse_scores,
)


def test_hybrid_fixture_contract_is_safe_and_deterministic() -> None:
    name = collection_name("ABC")
    summary = hybrid_contract_summary("ABC")

    assert name.startswith("quimera_pr08_hybrid_smoke_")
    assert DENSE_VECTOR_NAME == "text-dense"
    assert SPARSE_VECTOR_NAME == "text-sparse"
    assert summary["dense_ok"] is True
    assert summary["sparse_ok"] is True
    assert summary["hybrid_ok"] is True
    assert summary["result_count"] > 0


def test_cleanup_rejects_real_collections() -> None:
    for name in ("quimera_knowledge", "quimera_query_cache", "quimera_llm_cache", "other"):
        with pytest.raises(ValueError):
            assert_safe_cleanup_collection(name)


def test_recall_at_5_calculates_expected_ratio() -> None:
    dense = synthetic_dense_scores("postgres qdrant")
    sparse = synthetic_sparse_scores("postgres qdrant")
    hybrid = synthetic_hybrid_rrf("postgres qdrant")

    assert dense
    assert sparse
    assert hybrid
    assert compute_recall_at_k(hybrid, {"doc-memory", "doc-qdrant"}) >= 0.5
