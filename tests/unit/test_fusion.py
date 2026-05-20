"""Unit tests for deterministic Weighted RRF fusion."""

from __future__ import annotations

import ast
import inspect
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from typing import cast

import pytest

import backend.rag.fusion as fusion_module
from backend.rag.fusion import (
    DEFAULT_DENSE_WEIGHT,
    DEFAULT_PROFILE,
    DEFAULT_RRF_K,
    DEFAULT_SPARSE_WEIGHT,
    FusedResult,
    RRFFusion,
    RRFWeightProfile,
    RankedResult,
    SOURCE_DENSE,
    SOURCE_SPARSE,
    fuse,
    ranked_result_from_position,
)


def rr(
    result_id: str,
    doc_id: str | None = None,
    rank: int = 1,
    raw_score: float | None = None,
    payload: Mapping[str, object] | None = None,
) -> RankedResult:
    return RankedResult(
        result_id=result_id,
        doc_id=result_id if doc_id is None else doc_id,
        rank=rank,
        raw_score=raw_score,
        payload={} if payload is None else payload,
    )


def ids(results: list[FusedResult]) -> list[str]:
    return [result.result_id for result in results]


def test_fusion_module_is_pure_stdlib_without_io_or_print() -> None:
    tree = ast.parse(inspect.getsource(fusion_module))
    allowed_roots = {
        "__future__",
        "collections",
        "dataclasses",
        "math",
        "types",
        "typing",
    }
    forbidden_calls = {"open", "print"}
    forbidden_attrs = {"read", "write"}

    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_attrs

    assert imported_roots <= allowed_roots


def test_ranked_result_validates_rank_and_ids() -> None:
    with pytest.raises(ValueError, match="rank must be >= 1"):
        rr("A", rank=0)
    with pytest.raises(ValueError, match="result_id cannot be blank"):
        rr(" ")
    with pytest.raises(ValueError, match="doc_id cannot be blank"):
        rr("A", doc_id=" ")
    with pytest.raises(ValueError, match="result_id cannot contain null bytes"):
        rr("A\x00B")
    with pytest.raises(ValueError, match="doc_id cannot contain null bytes"):
        rr("A", doc_id="doc\x00A")


def test_ranked_result_rank_boundary_values() -> None:
    valid = rr("A", rank=1)
    assert valid.rank == 1

    with pytest.raises(ValueError, match="rank must be >= 1"):
        rr("A", rank=0)

    with pytest.raises(ValueError, match="rank must be >= 1"):
        rr("A", rank=-1)


def test_ranked_result_is_frozen_and_payload_is_defensive_mapping() -> None:
    payload = {"source": "dense"}
    result = rr("A", payload=payload)
    payload["source"] = "mutated"

    assert dict(result.payload) == {"source": "dense"}
    with pytest.raises(TypeError):
        result.payload["source"] = "mutated"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        result.rank = 2  # type: ignore[misc]


def test_rrf_weight_profile_defaults_and_validation() -> None:
    assert DEFAULT_PROFILE.dense_weight == DEFAULT_DENSE_WEIGHT
    assert DEFAULT_PROFILE.sparse_weight == DEFAULT_SPARSE_WEIGHT
    assert DEFAULT_PROFILE.k == DEFAULT_RRF_K

    with pytest.raises(ValueError, match="RRF weights must be non-negative"):
        RRFWeightProfile(dense_weight=-0.1)
    with pytest.raises(ValueError, match="at least one RRF weight must be positive"):
        RRFWeightProfile(dense_weight=0.0, sparse_weight=0.0)
    with pytest.raises(ValueError, match="RRF k must be > 0"):
        RRFWeightProfile(k=0)
    with pytest.raises(ValueError, match="RRF profile name cannot contain null bytes"):
        RRFWeightProfile(name="bad\x00name")

    assert RRFWeightProfile(dense_weight=0.0).dense_weight == 0.0
    assert RRFWeightProfile(sparse_weight=0.0).sparse_weight == 0.0
    assert RRFWeightProfile(k=60.5).k == 60.5


def test_rrf_weight_profile_bva_symmetric_and_k_boundary() -> None:
    with pytest.raises(ValueError, match="RRF weights must be non-negative"):
        RRFWeightProfile(sparse_weight=-0.1)

    profile = RRFWeightProfile(k=1.0)
    assert profile.k == 1.0

    result = fuse(
        dense_results=[rr("A", rank=1)],
        sparse_results=[],
        profile=profile,
    )
    assert result[0].rrf_score == pytest.approx(1.0 / 2.0)

    with pytest.raises(ValueError, match="RRF k must be > 0"):
        RRFWeightProfile(k=-1.0)


def test_fuse_empty_and_single_channel_cases() -> None:
    assert fuse(dense_results=[], sparse_results=[]) == []

    dense_only = fuse(dense_results=[rr("D", rank=2)], sparse_results=[])
    assert ids(dense_only) == ["D"]
    assert dense_only[0].dense_rank == 2
    assert dense_only[0].sparse_rank is None
    assert dense_only[0].sources == frozenset({SOURCE_DENSE})

    sparse_only = fuse(dense_results=[], sparse_results=[rr("S", rank=3)])
    assert ids(sparse_only) == ["S"]
    assert sparse_only[0].dense_rank is None
    assert sparse_only[0].sparse_rank == 3
    assert sparse_only[0].sources == frozenset({SOURCE_SPARSE})


def test_fuse_limit_validation_and_truncation() -> None:
    with pytest.raises(ValueError, match="limit must be >= 1"):
        fuse(dense_results=[rr("A")], sparse_results=[], limit=0)

    fused = fuse(
        dense_results=[rr("A", rank=1), rr("B", rank=2), rr("C", rank=3)],
        sparse_results=[],
        limit=2,
    )

    assert ids(fused) == ["A", "B"]


def test_document_present_in_both_rankings_receives_two_contributions() -> None:
    fused = RRFFusion().fuse(
        dense_results=[rr("A", rank=1), rr("B", rank=2)],
        sparse_results=[rr("B", rank=1), rr("C", rank=2)],
    )

    assert ids(fused)[0] == "B"
    assert fused[0].dense_rank == 2
    assert fused[0].sparse_rank == 1
    assert fused[0].dense_contribution == pytest.approx(1.0 / 62.0)
    assert fused[0].sparse_contribution == pytest.approx(1.0 / 61.0)
    assert fused[0].rrf_score == pytest.approx((1.0 / 62.0) + (1.0 / 61.0))
    assert fused[0].best_rank == 1
    assert fused[0].sources == frozenset({SOURCE_DENSE, SOURCE_SPARSE})
    assert fused[0].rrf_score == pytest.approx(
        fused[0].dense_contribution + fused[0].sparse_contribution
    )


def test_raw_score_is_diagnostic_and_does_not_affect_ordering() -> None:
    first = fuse(
        dense_results=[
            rr("A", rank=1, raw_score=0.01),
            rr("B", rank=2, raw_score=999.0),
        ],
        sparse_results=[],
    )
    second = fuse(
        dense_results=[
            rr("A", rank=1, raw_score=999.0),
            rr("B", rank=2, raw_score=0.01),
        ],
        sparse_results=[],
    )

    assert ids(first) == ["A", "B"]
    assert ids(second) == ["A", "B"]
    assert first[0].dense_raw_score == 0.01
    assert second[0].dense_raw_score == 999.0
    assert [result.result_id for result in first] == [
        result.result_id for result in second
    ]
    assert [result.rrf_score for result in first] == [
        result.rrf_score for result in second
    ]


def test_duplicate_in_dense_or_sparse_counts_only_first_occurrence() -> None:
    dense_duplicate = fuse(
        dense_results=[rr("A", rank=3), rr("A", rank=1)],
        sparse_results=[],
    )
    sparse_duplicate = fuse(
        dense_results=[],
        sparse_results=[rr("B", rank=4), rr("B", rank=1)],
    )

    assert len(dense_duplicate) == 1
    assert dense_duplicate[0].dense_rank == 3
    assert dense_duplicate[0].rrf_score == pytest.approx(1.0 / 63.0)
    assert len(sparse_duplicate) == 1
    assert sparse_duplicate[0].sparse_rank == 4
    assert sparse_duplicate[0].rrf_score == pytest.approx(1.0 / 64.0)


def test_conflicting_doc_id_for_same_result_id_fails() -> None:
    with pytest.raises(ValueError, match="conflicting doc_id for the same result_id"):
        fuse(
            dense_results=[rr("chunk-1", doc_id="doc-a", rank=1)],
            sparse_results=[rr("chunk-1", doc_id="doc-b", rank=1)],
        )


def test_two_chunks_same_doc_id_different_result_id_do_not_collapse() -> None:
    """Checklist 2: result_id is the dedup key, not doc_id."""

    fused = fuse(
        dense_results=[
            rr("chunk-1", doc_id="doc-a", rank=1),
            rr("chunk-2", doc_id="doc-a", rank=2),
        ],
        sparse_results=[],
    )

    assert len(fused) == 2
    assert {result.result_id for result in fused} == {"chunk-1", "chunk-2"}
    assert {result.doc_id for result in fused} == {"doc-a"}


def test_first_seen_order_uses_concatenated_input_position_even_with_duplicates() -> None:
    fused = fuse(
        dense_results=[rr("A", rank=1), rr("A", rank=2), rr("B", rank=3)],
        sparse_results=[rr("C", rank=1)],
    )
    by_id = {result.result_id: result for result in fused}

    assert by_id["A"].first_seen_order == 0
    assert by_id["B"].first_seen_order == 2
    assert by_id["C"].first_seen_order == 3


def test_first_seen_order_respects_dense_sparse_boundary() -> None:
    fused = fuse(
        dense_results=[rr("a", rank=10), rr("x", rank=10), rr("y", rank=10)],
        sparse_results=[rr("b", rank=1), rr("c", rank=2)],
    )
    by_id = {result.result_id: result for result in fused}

    assert by_id["b"].first_seen_order == 3
    assert by_id["c"].first_seen_order == 4
    assert ids(fused).index("b") < ids(fused).index("c")


def test_ablation_with_zero_weights_behaves_as_single_channel() -> None:
    sparse_only = fuse(
        dense_results=[rr("dense_only", rank=1)],
        sparse_results=[rr("sparse_only", rank=1)],
        profile=RRFWeightProfile(dense_weight=0.0, sparse_weight=1.0),
    )
    dense_only = fuse(
        dense_results=[rr("dense_only", rank=1)],
        sparse_results=[rr("sparse_only", rank=1)],
        profile=RRFWeightProfile(dense_weight=1.0, sparse_weight=0.0),
    )

    assert ids(sparse_only) == ["sparse_only"]
    assert sparse_only[0].sources == frozenset({SOURCE_SPARSE})
    assert ids(dense_only) == ["dense_only"]
    assert dense_only[0].sources == frozenset({SOURCE_DENSE})


def test_rrf_score_equals_sum_of_contributions_and_rank1_spot_check() -> None:
    result = fuse(
        dense_results=[rr("a", rank=1)],
        sparse_results=[rr("a", rank=2)],
        profile=DEFAULT_PROFILE,
    )[0]

    assert result.rrf_score == pytest.approx(
        result.dense_contribution + result.sparse_contribution
    )
    assert result.dense_contribution == pytest.approx(1.0 / 61.0, abs=1e-15)
    assert result.sparse_contribution == pytest.approx(1.0 / 62.0, abs=1e-15)


def test_rank1_k60_weight1_contribution_is_correct() -> None:
    result = fuse(
        dense_results=[rr("x", rank=1, raw_score=1.0)],
        sparse_results=[],
        profile=DEFAULT_PROFILE,
    )[0]

    assert result.rrf_score == pytest.approx(1.0 / 61.0, abs=1e-15)


def test_ranked_result_from_position_assigns_one_based_rank() -> None:
    result = ranked_result_from_position(
        result_id="chunk-1",
        doc_id="doc-1",
        zero_based_position=2,
        raw_score=0.42,
        payload={"kind": "dense"},
    )

    assert result == rr(
        "chunk-1",
        doc_id="doc-1",
        rank=3,
        raw_score=0.42,
        payload={"kind": "dense"},
    )


def test_ranked_result_from_position_rejects_negative_position() -> None:
    with pytest.raises(ValueError, match="zero_based_position must be non-negative"):
        ranked_result_from_position(
            result_id="chunk-1",
            doc_id="doc-1",
            zero_based_position=-1,
        )


def test_determinism_across_repeated_calls() -> None:
    dense = [rr("A", rank=1), rr("B", rank=2), rr("C", rank=3)]
    sparse = [rr("C", rank=1), rr("B", rank=2), rr("D", rank=3)]

    first = RRFFusion().fuse(dense_results=dense, sparse_results=sparse)
    second = RRFFusion().fuse(dense_results=dense, sparse_results=sparse)

    assert first == second


def test_inputs_are_not_mutated() -> None:
    dense = [rr("A", rank=1), rr("B", rank=2)]
    sparse = [rr("B", rank=1), rr("C", rank=2)]
    dense_before = list(dense)
    sparse_before = list(sparse)

    RRFFusion().fuse(dense_results=dense, sparse_results=sparse)

    assert dense == dense_before
    assert sparse == sparse_before


def test_tie_breaks_by_best_rank_then_first_seen_then_result_id() -> None:
    k = 60
    best_rank_tie = fuse(
        dense_results=[rr("A", rank=1)],
        sparse_results=[rr("placeholder", rank=99), rr("B", rank=2)],
        profile=RRFWeightProfile(
            dense_weight=1.0,
            sparse_weight=(k + 2) / (k + 1),
            k=k,
            name="best-rank-tie",
        ),
    )
    assert ids(best_rank_tie).index("A") < ids(best_rank_tie).index("B")
    assert best_rank_tie[0].rrf_score == pytest.approx(best_rank_tie[1].rrf_score)

    first_seen_tie = fuse(
        dense_results=[rr("A", rank=1)],
        sparse_results=[rr("B", rank=1)],
    )
    assert ids(first_seen_tie) == ["A", "B"]
    assert first_seen_tie[0].rrf_score == pytest.approx(first_seen_tie[1].rrf_score)
    assert first_seen_tie[0].best_rank == first_seen_tie[1].best_rank

    result_id_tie = sorted(
        [
            FusedResult(
                result_id="b",
                doc_id="doc-b",
                rrf_score=1.0,
                dense_rank=1,
                sparse_rank=None,
                dense_contribution=1.0,
                sparse_contribution=0.0,
                best_rank=1,
                first_seen_order=0,
                sources=frozenset({SOURCE_DENSE}),
            ),
            FusedResult(
                result_id="a",
                doc_id="doc-a",
                rrf_score=1.0,
                dense_rank=1,
                sparse_rank=None,
                dense_contribution=1.0,
                sparse_contribution=0.0,
                best_rank=1,
                first_seen_order=0,
                sources=frozenset({SOURCE_DENSE}),
            ),
        ],
        key=fusion_module._fused_sort_key,  # noqa: SLF001
    )
    assert ids(result_id_tie) == ["a", "b"]


def test_fused_result_requires_sources_to_match_present_ranks() -> None:
    with pytest.raises(ValueError, match="sources must match present source ranks"):
        FusedResult(
            result_id="a",
            doc_id="doc-a",
            rrf_score=1.0,
            dense_rank=1,
            sparse_rank=None,
            dense_contribution=1.0,
            sparse_contribution=0.0,
            best_rank=1,
            first_seen_order=0,
            sources=frozenset({SOURCE_SPARSE}),
        )


def test_fused_result_requires_rrf_score_to_equal_contributions() -> None:
    with pytest.raises(
        ValueError,
        match="rrf_score must equal dense_contribution",
    ):
        FusedResult(
            result_id="a",
            doc_id="doc-a",
            rrf_score=0.5,
            dense_rank=1,
            sparse_rank=None,
            dense_contribution=1.0,
            sparse_contribution=0.0,
            best_rank=1,
            first_seen_order=0,
            sources=frozenset({SOURCE_DENSE}),
        )


def test_payload_selection_uses_best_rank_and_dense_wins_rank_tie() -> None:
    dense_best = fuse(
        dense_results=[rr("A", doc_id="doc-1", rank=1, payload={"source": "dense"})],
        sparse_results=[
            rr("x", rank=1),
            rr("A", doc_id="doc-1", rank=2, payload={"source": "sparse"}),
        ],
    )
    sparse_best = fuse(
        dense_results=[rr("A", doc_id="doc-1", rank=3, payload={"source": "dense"})],
        sparse_results=[rr("A", doc_id="doc-1", rank=1, payload={"source": "sparse"})],
    )
    dense_tie = fuse(
        dense_results=[rr("A", doc_id="doc-1", rank=1, payload={"source": "dense"})],
        sparse_results=[rr("A", doc_id="doc-1", rank=1, payload={"source": "sparse"})],
    )

    assert dict(dense_best[0].payload) == {"source": "dense"}
    assert dict(sparse_best[0].payload) == {"source": "sparse"}
    assert dict(dense_tie[0].payload) == {"source": "dense"}


def test_payload_allows_schema_content_because_fusion_is_schema_agnostic() -> None:
    result = rr(
        "A",
        payload={
            "text": "chunk text belongs to retriever/schema layers",
            "vector": [1.0, 2.0],
        },
    )

    assert dict(result.payload) == {
        "text": "chunk text belongs to retriever/schema layers",
        "vector": [1.0, 2.0],
    }


def test_payload_rejects_non_string_keys() -> None:
    payload = cast(Mapping[str, object], {1: "not-json-friendly"})

    with pytest.raises(TypeError, match="payload keys must be strings"):
        rr("A", payload=payload)


def test_to_dict_is_stable_and_json_friendly() -> None:
    result = fuse(
        dense_results=[
            rr(
                "A",
                doc_id="doc-1",
                rank=1,
                raw_score=0.99,
                payload={"kind": "dense"},
            )
        ],
        sparse_results=[],
    )[0]

    assert result.to_dict() == {
        "result_id": "A",
        "doc_id": "doc-1",
        "rrf_score": pytest.approx(1.0 / 61.0),
        "dense_rank": 1,
        "sparse_rank": None,
        "dense_contribution": pytest.approx(1.0 / 61.0),
        "sparse_contribution": 0.0,
        "best_rank": 1,
        "first_seen_order": 0,
        "dense_raw_score": 0.99,
        "sparse_raw_score": None,
        "sources": ["dense"],
        "payload": {"kind": "dense"},
    }


def test_function_matches_wrapper_class() -> None:
    profile = RRFWeightProfile(name="function-test")
    dense = [rr("A", rank=1), rr("B", rank=2)]
    sparse = [rr("B", rank=1), rr("C", rank=2)]

    assert RRFFusion(profile=profile).fuse(
        dense_results=dense,
        sparse_results=sparse,
    ) == fuse(
        dense_results=dense,
        sparse_results=sparse,
        profile=profile,
    )


def test_public_exports_include_benchmark_constants_and_helper() -> None:
    assert {
        "DEFAULT_RRF_K",
        "DEFAULT_DENSE_WEIGHT",
        "DEFAULT_SPARSE_WEIGHT",
        "SOURCE_DENSE",
        "SOURCE_SPARSE",
        "ranked_result_from_position",
    } <= set(fusion_module.__all__)
    assert "DENSE_SOURCE" not in fusion_module.__all__
    assert "SPARSE_SOURCE" not in fusion_module.__all__


def test_snapshot_fixed_weighted_rrf_output() -> None:
    fused = fuse(
        dense_results=[
            rr("chunk-a", doc_id="doc-a", rank=1),
            rr("chunk-b", doc_id="doc-b", rank=2),
            rr("chunk-c", doc_id="doc-c", rank=3),
        ],
        sparse_results=[
            rr("chunk-b", doc_id="doc-b", rank=1),
            rr("chunk-d", doc_id="doc-d", rank=2),
            rr("chunk-a", doc_id="doc-a", rank=3),
        ],
    )

    assert [result.to_dict() for result in fused] == [
        {
            "result_id": "chunk-b",
            "doc_id": "doc-b",
            "rrf_score": pytest.approx((1.0 / 62.0) + (1.0 / 61.0)),
            "dense_rank": 2,
            "sparse_rank": 1,
            "dense_contribution": pytest.approx(1.0 / 62.0),
            "sparse_contribution": pytest.approx(1.0 / 61.0),
            "best_rank": 1,
            "first_seen_order": 1,
            "dense_raw_score": None,
            "sparse_raw_score": None,
            "sources": ["dense", "sparse"],
            "payload": {},
        },
        {
            "result_id": "chunk-a",
            "doc_id": "doc-a",
            "rrf_score": pytest.approx((1.0 / 61.0) + (1.0 / 63.0)),
            "dense_rank": 1,
            "sparse_rank": 3,
            "dense_contribution": pytest.approx(1.0 / 61.0),
            "sparse_contribution": pytest.approx(1.0 / 63.0),
            "best_rank": 1,
            "first_seen_order": 0,
            "dense_raw_score": None,
            "sparse_raw_score": None,
            "sources": ["dense", "sparse"],
            "payload": {},
        },
        {
            "result_id": "chunk-d",
            "doc_id": "doc-d",
            "rrf_score": pytest.approx(1.0 / 62.0),
            "dense_rank": None,
            "sparse_rank": 2,
            "dense_contribution": 0.0,
            "sparse_contribution": pytest.approx(1.0 / 62.0),
            "best_rank": 2,
            "first_seen_order": 4,
            "dense_raw_score": None,
            "sparse_raw_score": None,
            "sources": ["sparse"],
            "payload": {},
        },
        {
            "result_id": "chunk-c",
            "doc_id": "doc-c",
            "rrf_score": pytest.approx(1.0 / 63.0),
            "dense_rank": 3,
            "sparse_rank": None,
            "dense_contribution": pytest.approx(1.0 / 63.0),
            "sparse_contribution": 0.0,
            "best_rank": 3,
            "first_seen_order": 2,
            "dense_raw_score": None,
            "sparse_raw_score": None,
            "sources": ["dense"],
            "payload": {},
        },
    ]
