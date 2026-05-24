"""Offline tests for Q18-06 native RRF comparison contracts."""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

from backend.rag import qdrant_native_fusion as native
from backend.rag.qdrant_native_fusion import (
    BENCHMARK_COLLECTION,
    CANDIDATE_COLLECTION,
    DENSE_VECTOR_NAME,
    LEXICAL_HYBRID_PROFILE,
    LEGACY_COLLECTION,
    NEUTRAL_PROFILE,
    SEMANTIC_HYBRID_PROFILE,
    SPARSE_VECTOR_NAME,
    FusionCandidate,
    FusionComparisonEvent,
    NativeFusionConfig,
    NativeFusionDisabled,
    NativeFusionError,
    QdrantNativeFusionRetriever,
    SparseVectorLike,
    build_prefetch_plan,
    build_rrf_monitoring_attributes,
    build_rrf_query_config,
    classify_query_profile,
    compare_fusion_for_query,
    compute_fusion_divergence,
    compute_jaccard_at_k,
    compute_overlap_at_k,
    compute_rank_delta_stats,
    default_retrieval_profile,
    fusion_comparison_otel_attributes,
    get_retrieval_profile,
    make_query_hash,
    profile_to_python_rrf_weights,
    profile_to_qdrant_prefetch_weights,
    retrieval_profile_registry,
    retrieve_native_with_python_fallback,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "backend/rag/qdrant_native_fusion.py"
DOC_PATH = ROOT / "docs/specs/qdrant-1-18-upgrade/native_rrf_adapter.md"
NETWORK_METHOD_NAMES = frozenset(
    {"get", "post", "put", "patch", "delete", "request", "send", "connect"}
)
NETWORK_RECEIVER_ROOTS = frozenset({"aiohttp", "httpx", "requests", "urllib"})
NETWORK_RECEIVER_NAMES = frozenset(
    {
        "api_client",
        "async_client",
        "client",
        "connection",
        "conn",
        "http_client",
        "session",
        "_client",
    }
)


def _ast_root_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _ast_root_name(node.value)
    if isinstance(node, ast.Call):
        return _ast_root_name(node.func)
    return None


def _ast_leaf_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _ast_leaf_name(node.func)
    return None


def _looks_like_http_receiver(node: ast.AST) -> bool:
    root = _ast_root_name(node)
    leaf = _ast_leaf_name(node)
    return (
        root in NETWORK_RECEIVER_ROOTS
        or root in NETWORK_RECEIVER_NAMES
        or leaf in NETWORK_RECEIVER_ROOTS
        or leaf in NETWORK_RECEIVER_NAMES
    )


def _network_call_violations(tree: ast.AST) -> tuple[str, ...]:
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in NETWORK_METHOD_NAMES:
            violations.append(node.func.id)
        elif (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in NETWORK_METHOD_NAMES
            and _looks_like_http_receiver(node.func.value)
        ):
            violations.append(node.func.attr)
    return tuple(violations)


@dataclass(frozen=True, slots=True)
class FakeSparseVector:
    indices: tuple[int, ...] = (1, 2)
    values: tuple[float, ...] = (0.5, 1.0)


class FakeNativeClient:
    def __init__(
        self,
        points: Sequence[Mapping[str, object]] | None = None,
        *,
        fail: bool = False,
    ) -> None:
        self.points = list(points or [])
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    async def query_points(
        self,
        *,
        collection_name: str,
        prefetch: Sequence[object],
        query: object,
        limit: int,
        with_payload: bool = True,
    ) -> object:
        self.calls.append(
            {
                "collection_name": collection_name,
                "prefetch": prefetch,
                "query": query,
                "limit": limit,
                "with_payload": with_payload,
            }
        )
        if self.fail:
            raise RuntimeError("raw native error with details")
        return {"points": self.points[:limit]}


class FakeRunner:
    def __init__(
        self,
        results: Sequence[FusionCandidate],
        *,
        fail: bool = False,
    ) -> None:
        self.results = tuple(results)
        self.fail = fail
        self.calls: list[str] = []

    async def retrieve(
        self,
        *,
        query_id: str,
        dense_vector: Sequence[float],
        sparse_vector: SparseVectorLike,
        top_k: int,
    ) -> Sequence[FusionCandidate]:
        self.calls.append(query_id)
        if self.fail:
            raise RuntimeError("raw runner failure")
        return self.results[:top_k]


def candidate(
    result_id: str,
    rank: int,
    *,
    doc_id: str | None = None,
    backend: native.FusionBackend = "python_rrf",
) -> FusionCandidate:
    return FusionCandidate(
        result_id=result_id,
        doc_id=doc_id or f"doc-{result_id}",
        rank=rank,
        score=1.0 / rank,
        backend=backend,
    )


def test_retrieval_profiles_contract() -> None:
    registry = retrieval_profile_registry()

    assert set(registry) == {"neutral", "semantic_hybrid", "lexical_hybrid"}
    assert profile_to_python_rrf_weights(NEUTRAL_PROFILE) == {
        "dense": 1.0,
        "sparse": 1.0,
        "k": 60.0,
    }


def test_default_profile_is_neutral() -> None:
    assert default_retrieval_profile() is NEUTRAL_PROFILE


def test_semantic_profile_dense_heavy() -> None:
    assert SEMANTIC_HYBRID_PROFILE.dense_weight > SEMANTIC_HYBRID_PROFILE.sparse_weight


def test_lexical_profile_sparse_heavy() -> None:
    assert LEXICAL_HYBRID_PROFILE.sparse_weight > LEXICAL_HYBRID_PROFILE.dense_weight


def test_profile_to_qdrant_weights_respects_prefetch_order_sparse_dense() -> None:
    assert profile_to_qdrant_prefetch_weights(
        SEMANTIC_HYBRID_PROFILE,
        (SPARSE_VECTOR_NAME, DENSE_VECTOR_NAME),
    ) == [1.0, 1.3]
    assert profile_to_qdrant_prefetch_weights(
        LEXICAL_HYBRID_PROFILE,
        (SPARSE_VECTOR_NAME, DENSE_VECTOR_NAME),
    ) == [1.4, 1.0]


def test_profile_registry_immutable() -> None:
    with pytest.raises(TypeError):
        cast(Any, retrieval_profile_registry())["new"] = NEUTRAL_PROFILE


def test_unknown_profile_rejected() -> None:
    with pytest.raises(KeyError, match="unknown"):
        get_retrieval_profile("not-a-profile")


def test_query_classifier_ticker_goes_lexical() -> None:
    assert classify_query_profile("MXRF11 DY CDI") is LEXICAL_HYBRID_PROFILE


def test_query_classifier_acronyms_go_lexical() -> None:
    assert classify_query_profile("CRI CDI IPCA") is LEXICAL_HYBRID_PROFILE


def test_query_classifier_long_natural_question_goes_semantic() -> None:
    query = "qual fundo imobiliario parece adequado para renda mensal recorrente?"

    assert classify_query_profile(query) is SEMANTIC_HYBRID_PROFILE


def test_query_classifier_ambiguous_goes_neutral() -> None:
    assert classify_query_profile("renda fixa") is NEUTRAL_PROFILE


def test_query_classifier_rejects_null_byte_or_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        classify_query_profile(" ")
    with pytest.raises(ValueError, match="null bytes"):
        classify_query_profile("abc\x00def")


def test_native_config_disabled_by_default() -> None:
    config = NativeFusionConfig()

    assert config.enabled is False
    assert config.collection_name == BENCHMARK_COLLECTION


def test_native_config_rejects_candidate_and_legacy_collections() -> None:
    with pytest.raises(ValueError, match="protected"):
        NativeFusionConfig(collection_name=CANDIDATE_COLLECTION)
    with pytest.raises(ValueError, match="protected"):
        NativeFusionConfig(collection_name=LEGACY_COLLECTION)


def test_build_prefetch_plan_sparse_dense() -> None:
    config = NativeFusionConfig(enabled=True)

    plan = build_prefetch_plan(
        dense_vector=[0.1, 0.2],
        sparse_vector=FakeSparseVector(),
        config=config,
    )

    assert tuple(item["using"] for item in plan) == ("sparse", "dense")
    assert tuple(item["query_kind"] for item in plan) == ("sparse", "dense")


def test_build_rrf_query_config_neutral() -> None:
    query = build_rrf_query_config(NativeFusionConfig())

    assert query["rrf"] == {"k": 60.0}


def test_build_weighted_rrf_query_config_semantic() -> None:
    config = NativeFusionConfig(
        fusion_mode="weighted_rrf",
        profile=SEMANTIC_HYBRID_PROFILE,
    )
    query = build_rrf_query_config(config)

    assert query["rrf"] == {"k": 60.0, "weights": [1.0, 1.3]}


def test_build_weighted_rrf_query_config_lexical() -> None:
    config = NativeFusionConfig(
        fusion_mode="weighted_rrf",
        profile=LEXICAL_HYBRID_PROFILE,
    )
    query = build_rrf_query_config(config)

    assert query["rrf"] == {"k": 60.0, "weights": [1.4, 1.0]}


def test_search_top_k_must_be_greater_or_equal_return_top_k() -> None:
    with pytest.raises(ValueError, match="search_top_k"):
        NativeFusionConfig(search_top_k=5, return_top_k=10)


@pytest.mark.asyncio
async def test_native_adapter_refuses_when_disabled() -> None:
    adapter = QdrantNativeFusionRetriever(
        client=FakeNativeClient(),
        config=NativeFusionConfig(enabled=False),
    )

    with pytest.raises(NativeFusionDisabled):
        await adapter.retrieve(
            dense_vector=[0.1],
            sparse_vector=FakeSparseVector(),
            query_id="q1",
        )


@pytest.mark.asyncio
async def test_native_adapter_calls_query_points_with_prefetch() -> None:
    client = FakeNativeClient([{"id": "r1", "score": 0.9, "payload": {"doc_id": "d1"}}])
    adapter = QdrantNativeFusionRetriever(
        client=client,
        config=NativeFusionConfig(enabled=True),
    )

    await adapter.retrieve(
        dense_vector=[0.1],
        sparse_vector=FakeSparseVector(),
        query_id="q1",
    )

    assert len(client.calls) == 1
    assert client.calls[0]["collection_name"] == BENCHMARK_COLLECTION
    assert client.calls[0]["limit"] == 10
    assert client.calls[0]["with_payload"] is True


@pytest.mark.asyncio
async def test_native_adapter_normalizes_points_to_candidates() -> None:
    adapter = QdrantNativeFusionRetriever(
        client=FakeNativeClient(
            [
                {"id": "r1", "score": 0.9, "payload": {"doc_id": "d1"}},
                {"id": "r2", "score": 0.8, "payload": {"doc_id": "d2"}},
            ]
        ),
        config=NativeFusionConfig(enabled=True, fusion_mode="weighted_rrf"),
    )

    results = await adapter.retrieve(
        dense_vector=[0.1],
        sparse_vector=FakeSparseVector(),
        query_id="q1",
    )

    assert tuple(item.result_id for item in results) == ("r1", "r2")
    assert tuple(item.rank for item in results) == (1, 2)
    assert {item.backend for item in results} == {"qdrant_weighted_rrf"}


@pytest.mark.asyncio
async def test_native_adapter_requires_doc_id_in_payload() -> None:
    adapter = QdrantNativeFusionRetriever(
        client=FakeNativeClient([{"id": "r1", "score": 0.9, "payload": {}}]),
        config=NativeFusionConfig(enabled=True),
    )

    with pytest.raises(NativeFusionError, match="doc_id"):
        await adapter.retrieve(
            dense_vector=[0.1],
            sparse_vector=FakeSparseVector(),
            query_id="q1",
        )


@pytest.mark.asyncio
async def test_native_adapter_has_no_payload_leak() -> None:
    adapter = QdrantNativeFusionRetriever(
        client=FakeNativeClient(
            [{"id": "r1", "score": 0.9, "payload": {"doc_id": "d1", "text": "secret"}}]
        ),
        config=NativeFusionConfig(enabled=True),
    )

    results = await adapter.retrieve(
        dense_vector=[0.1],
        sparse_vector=FakeSparseVector(),
        query_id="q1",
    )

    assert "payload" not in results[0].to_safe_dict()
    assert "secret" not in json.dumps(results[0].to_safe_dict())


@pytest.mark.asyncio
async def test_native_adapter_weight_order_matches_prefetch_order() -> None:
    client = FakeNativeClient([{"id": "r1", "score": 0.9, "payload": {"doc_id": "d1"}}])
    adapter = QdrantNativeFusionRetriever(
        client=client,
        config=NativeFusionConfig(
            enabled=True,
            fusion_mode="weighted_rrf",
            profile=LEXICAL_HYBRID_PROFILE,
        ),
    )

    await adapter.retrieve(
        dense_vector=[0.1],
        sparse_vector=FakeSparseVector(),
        query_id="q1",
    )

    assert client.calls[0]["query"] == {"rrf": {"k": 60.0, "weights": [1.4, 1.0]}}


def test_overlap_at_k() -> None:
    assert compute_overlap_at_k(("a", "b", "c"), ("b", "c", "d"), 3) == pytest.approx(2 / 3)


def test_jaccard_at_k() -> None:
    assert compute_jaccard_at_k(("a", "b", "c"), ("b", "c", "d"), 3) == pytest.approx(0.5)


def test_order_equal_true() -> None:
    divergence = compute_fusion_divergence(
        query_id="q1",
        profile=NEUTRAL_PROFILE,
        python_results=[candidate("a", 1), candidate("b", 2)],
        native_results=[
            candidate("a", 1, backend="qdrant_rrf"),
            candidate("b", 2, backend="qdrant_rrf"),
        ],
        top_k=2,
    )

    assert divergence.order_equal is True
    assert divergence.set_equal is True


def test_same_set_different_order_records_tie_break_note() -> None:
    divergence = compute_fusion_divergence(
        query_id="q1",
        profile=NEUTRAL_PROFILE,
        python_results=[candidate("a", 1), candidate("b", 2)],
        native_results=[
            candidate("b", 1, backend="qdrant_rrf"),
            candidate("a", 2, backend="qdrant_rrf"),
        ],
        top_k=2,
    )

    assert divergence.set_equal is True
    assert divergence.order_equal is False
    assert divergence.tie_break_notes == ("same_set_different_order",)


def test_rank_delta_stats() -> None:
    mean_delta, max_delta = compute_rank_delta_stats(("a", "b", "c"), ("b", "a", "c"), 3)

    assert mean_delta == pytest.approx(2 / 3)
    assert max_delta == 1


def test_compute_fusion_divergence_safe_dict_no_query_payload_vectors() -> None:
    divergence = compute_fusion_divergence(
        query_id="q-safe-id",
        profile=NEUTRAL_PROFILE,
        python_results=[candidate("a", 1)],
        native_results=[candidate("b", 1, backend="qdrant_rrf")],
        top_k=1,
    )
    payload = json.dumps(divergence.to_safe_dict())

    assert "payload" not in payload
    assert "vector" not in payload
    assert "embedding" not in payload
    assert "literal query" not in payload


@pytest.mark.asyncio
async def test_fallback_to_python_on_native_error() -> None:
    python_runner = FakeRunner([candidate("py", 1)])
    native_runner = FakeRunner([], fail=True)

    backend, results = await retrieve_native_with_python_fallback(
        native_runner=native_runner,
        python_runner=python_runner,
        query_id="q1",
        dense_vector=[0.1],
        sparse_vector=FakeSparseVector(),
        top_k=10,
    )

    assert backend == "python_rrf"
    assert tuple(item.result_id for item in results) == ("py",)


@pytest.mark.asyncio
async def test_native_error_is_sanitized() -> None:
    adapter = QdrantNativeFusionRetriever(
        client=FakeNativeClient(fail=True),
        config=NativeFusionConfig(enabled=True),
    )

    with pytest.raises(NativeFusionError) as exc_info:
        await adapter.retrieve(
            dense_vector=[0.1],
            sparse_vector=FakeSparseVector(),
            query_id="q1",
        )

    assert "raw native error" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_python_result_unchanged_when_native_fails() -> None:
    expected = [candidate("py", 1)]
    python_runner = FakeRunner(expected)

    _, results = await retrieve_native_with_python_fallback(
        native_runner=FakeRunner([], fail=True),
        python_runner=python_runner,
        query_id="q1",
        dense_vector=[0.1],
        sparse_vector=FakeSparseVector(),
        top_k=10,
    )

    assert tuple(results) == tuple(expected)


def test_monitoring_attributes_are_otel_friendly() -> None:
    attrs = build_rrf_monitoring_attributes(
        backend="python_rrf",
        fusion_mode="rrf",
        profile=SEMANTIC_HYBRID_PROFILE,
        native_enabled=False,
    )

    assert attrs["rag.fusion.python_source_of_truth"] is True
    assert attrs["rag.fusion.profile"] == "semantic_hybrid"


def test_fusion_comparison_event_safe_dict() -> None:
    event = FusionComparisonEvent(
        query_hash=make_query_hash("safe synthetic query"),
        query_id="q1",
        profile_name="neutral",
        overlap_at_k=1.0,
        order_equal=True,
    )

    assert event.to_safe_dict()["schema_version"] == "fusion-comparison-v1"


def test_comparison_event_has_no_query_literal_payload_vectors_embeddings() -> None:
    event = FusionComparisonEvent(
        query_hash=make_query_hash("do not leak this query"),
        query_id="q1",
        profile_name="neutral",
        overlap_at_k=0.5,
        order_equal=False,
    )
    payload = json.dumps(event.to_safe_dict())

    assert "do not leak this query" not in payload
    for forbidden in ("payload", "vector", "embedding", "chunk_text"):
        assert forbidden not in payload


def test_python_rrf_remains_default_source_of_truth_in_docs() -> None:
    assert "Python RRFFusion continua fonte de verdade" in DOC_PATH.read_text(
        encoding="utf-8"
    )


def test_module_does_not_import_mcp_sdk() -> None:
    assert _imported_roots().isdisjoint({"mcp"})


def test_module_does_not_import_opentelemetry() -> None:
    assert _imported_roots().isdisjoint({"opentelemetry"})


def test_network_call_detector_allows_mapping_get_but_flags_http_clients() -> None:
    tree = ast.parse(
        """
payload.get("doc_id")
response.get("points")
http_client.get("/health")
requests.post("/events")
self._client.request("GET", "/collections")
"""
    )

    assert _network_call_violations(tree) == ("get", "post", "request")


def test_module_has_no_http_network_calls() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))

    assert _network_call_violations(tree) == ()


def test_module_does_not_call_create_delete_upsert_collection() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden = {
        "create_collection",
        "delete_collection",
        "recreate_collection",
        "upsert",
        "set_payload",
        "delete_payload",
        "update_collection",
        "upload_collection",
        "delete_vectors",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden


def test_module_does_not_touch_reset_or_schema_scripts() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "qdrant_reset_local_collections" not in source
    assert "qdrant_create_hybrid_schema_118" not in source


def test_docs_mention_python_rrf_source_of_truth() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "Python RRFFusion continua fonte de verdade" in text


def test_docs_mention_mcp_future_only_not_implemented() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "No MCP server in Q18-06" in text
    assert "one MCP server and two retrieval tools" in text


@pytest.mark.asyncio
async def test_compare_fusion_for_query_uses_same_query_id() -> None:
    python_runner = FakeRunner([candidate("a", 1)])
    native_runner = FakeRunner([candidate("a", 1, backend="qdrant_rrf")])

    await compare_fusion_for_query(
        query_id="q-shared",
        dense_vector=[0.1],
        sparse_vector=FakeSparseVector(),
        python_runner=python_runner,
        native_runner=native_runner,
        profile=NEUTRAL_PROFILE,
        top_k=10,
    )

    assert python_runner.calls == ["q-shared"]
    assert native_runner.calls == ["q-shared"]


@pytest.mark.asyncio
async def test_compare_fusion_for_query_pairwise_outputs_divergence() -> None:
    divergence = await compare_fusion_for_query(
        query_id="q1",
        dense_vector=[0.1],
        sparse_vector=FakeSparseVector(),
        python_runner=FakeRunner([candidate("a", 1), candidate("b", 2)]),
        native_runner=FakeRunner(
            [
                candidate("b", 1, backend="qdrant_rrf"),
                candidate("a", 2, backend="qdrant_rrf"),
            ]
        ),
        profile=NEUTRAL_PROFILE,
        top_k=2,
    )

    assert divergence.overlap_at_k == 1.0
    assert divergence.order_equal is False


def test_query_id_not_query_text_in_logs() -> None:
    divergence = compute_fusion_divergence(
        query_id="q-id-only",
        profile=NEUTRAL_PROFILE,
        python_results=[candidate("a", 1)],
        native_results=[candidate("a", 1, backend="qdrant_rrf")],
        top_k=1,
    )

    assert "literal" not in json.dumps(divergence.to_safe_dict())


def _imported_roots() -> set[str]:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".")[0])
    return roots
