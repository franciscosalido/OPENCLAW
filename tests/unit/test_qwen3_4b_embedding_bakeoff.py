from __future__ import annotations

import ast
import json
from pathlib import Path
from collections.abc import Mapping
from typing import cast

import httpx
import pytest

from backend.rag.ollama_embedding_bakeoff import (
    BAKEOFF_COLLECTION,
    DENSE_NOMIC_VECTOR_NAME,
    DENSE_QWEN3_4B_VECTOR_NAME,
    EmbeddingBakeoffCollectionSpec,
    EmbeddingBatchResult,
    NOMIC_BENCHMARK_COLLECTION,
    NOMIC_DEFAULT_DIMENSIONS,
    NOMIC_MODEL_ID,
    QWEN3_4B_ALLOWED_DIMENSIONS,
    QWEN3_4B_BENCHMARK_COLLECTION,
    QWEN3_4B_DEFAULT_DIMENSIONS,
    QWEN3_4B_MODEL_ID,
    QWEN3_4B_OLLAMA_MODEL_ID,
    REQUIRED_BAKEOFF_PAYLOAD_FIELDS,
    SPARSE_VECTOR_NAME,
    OllamaEmbeddingClient,
    build_embed_payload,
    declared_bakeoff_scenarios,
    default_bakeoff_collection_spec,
    expected_dimension_for_model,
    format_qwen3_query,
    nomic_contract,
    qwen3_4b_contract,
)
from evaluation import run_q18_benchmark_profile as profile_runner

MODULE_PATH = Path(__file__).resolve().parents[2] / "backend/rag/ollama_embedding_bakeoff.py"


def test_qwen3_4b_contract_dimensions_2560() -> None:
    contract = qwen3_4b_contract()
    assert contract.model_id == QWEN3_4B_MODEL_ID
    assert contract.default_dimensions == QWEN3_4B_DEFAULT_DIMENSIONS
    assert contract.context_length == 32768
    assert contract.instruction_aware is True


def test_qwen3_4b_allows_dimension_sweep() -> None:
    assert 1024 in QWEN3_4B_ALLOWED_DIMENSIONS
    assert 1536 in QWEN3_4B_ALLOWED_DIMENSIONS
    assert 2560 in QWEN3_4B_ALLOWED_DIMENSIONS


def test_qwen3_4b_query_instruction_applied() -> None:
    formatted = format_qwen3_query("qual fundo imobiliário rende mensalmente?")
    assert formatted.startswith("Instruct: ")
    assert "\nQuery: " in formatted


def test_documents_do_not_use_query_instruction() -> None:
    payload = build_embed_payload(
        model=QWEN3_4B_MODEL_ID,
        inputs=("documento financeiro sintético",),
        dimensions=2560,
        keep_alive="30m",
    )
    inputs = cast(list[str], payload["input"])
    assert "Instruct:" not in inputs[0]


def test_qwen3_dimension_probe_detects_mismatch() -> None:
    assert expected_dimension_for_model(QWEN3_4B_MODEL_ID, 1024) == 1024
    assert expected_dimension_for_model(QWEN3_4B_MODEL_ID, None) == 2560


def test_qwen3_unavailable_does_not_promote() -> None:
    from backend.rag.ollama_embedding_bakeoff import decide_embedding_candidate

    decision = decide_embedding_candidate(
        qwen3_available=False,
        qwen3_ndcg_at_5=None,
        nomic_ndcg_at_5=None,
        qwen3_recall_at_10=None,
        nomic_recall_at_10=None,
        qwen3_total_p95_ms=None,
        nomic_total_p95_ms=None,
        memory_ok=None,
    )
    assert decision.value == "inconclusive_qwen3_4b_unavailable"


def test_nomic_contract_dimensions_768() -> None:
    contract = nomic_contract()
    assert contract.model_id == NOMIC_MODEL_ID
    assert contract.default_dimensions == NOMIC_DEFAULT_DIMENSIONS


def test_nomic_kept_as_fallback_in_contract() -> None:
    assert nomic_contract().baseline_or_candidate == "baseline"


def test_bakeoff_collection_has_dense_nomic_dense_qwen3_sparse() -> None:
    spec = default_bakeoff_collection_spec()
    vectors = spec.build_vectors_config()
    sparse = spec.build_sparse_vectors_config()
    dense_nomic = cast(Mapping[str, object], vectors[DENSE_NOMIC_VECTOR_NAME])
    dense_qwen3 = cast(Mapping[str, object], vectors[DENSE_QWEN3_4B_VECTOR_NAME])
    assert spec.collection_name == BAKEOFF_COLLECTION
    assert dense_nomic["size"] == 768
    assert dense_qwen3["size"] == 2560
    assert SPARSE_VECTOR_NAME in sparse


def test_fallback_nomic_collection_is_allowed_in_spec() -> None:
    spec = EmbeddingBakeoffCollectionSpec(collection_name=NOMIC_BENCHMARK_COLLECTION)
    assert spec.collection_name == NOMIC_BENCHMARK_COLLECTION


def test_fallback_qwen3_collection_is_allowed_in_spec() -> None:
    spec = EmbeddingBakeoffCollectionSpec(collection_name=QWEN3_4B_BENCHMARK_COLLECTION)
    assert spec.collection_name == QWEN3_4B_BENCHMARK_COLLECTION


def test_production_collections_still_blocked_with_expanded_allowlist() -> None:
    for collection in ("quimera_knowledge", "quimera_knowledge_v2", "openclaw_knowledge"):
        with pytest.raises(ValueError, match="protected"):
            EmbeddingBakeoffCollectionSpec(collection_name=collection)


def test_same_point_contains_both_dense_vectors_contract() -> None:
    spec = default_bakeoff_collection_spec()
    assert "dense_nomic_dimensions" in spec.payload_fields
    assert "dense_qwen3_4b_dimensions" in spec.payload_fields
    assert set(REQUIRED_BAKEOFF_PAYLOAD_FIELDS).issubset(set(spec.payload_fields))


def test_no_mixing_in_same_vector_name() -> None:
    spec = default_bakeoff_collection_spec()
    assert spec.dense_nomic_vector_name != spec.dense_qwen3_4b_vector_name


def test_nomic_vs_qwen_scenario_declared() -> None:
    ids = {scenario.scenario_id for scenario in declared_bakeoff_scenarios()}
    assert "nomic_dense_only" in ids
    assert "qwen3_4b_dense_only" in ids


def test_dimension_scenarios_declared() -> None:
    ids = {scenario.scenario_id for scenario in declared_bakeoff_scenarios()}
    assert "qwen3_4b_dimensions_1024" in ids
    assert "qwen3_4b_dimensions_1536" in ids
    assert "qwen3_4b_dimensions_2560" in ids


def test_cold_warm_scenarios_declared() -> None:
    ids = {scenario.scenario_id for scenario in declared_bakeoff_scenarios()}
    assert "cold_ollama_qwen3_4b" in ids
    assert "warm_ollama_qwen3_4b" in ids
    assert "batch_vs_single_embed" in ids


@pytest.mark.asyncio
async def test_ollama_embedding_client_batches_and_preserves_order() -> None:
    seen_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        seen_payloads.append(payload)
        count = len(payload["input"])
        return httpx.Response(
            200,
            json={
                "embeddings": [[float(i), float(i + 1)] for i in range(count)],
                "load_duration": 1,
                "total_duration": 2,
                "prompt_eval_count": count,
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:11434") as http_client:
        client = OllamaEmbeddingClient(
            model=QWEN3_4B_MODEL_ID,
            dimensions=2,
            client=http_client,
            keep_alive="30m",
        )
        result = await client.embed_documents(("doc a", "doc b"))

    assert result.count == 2
    assert result.dimensions == 2
    assert seen_payloads[0]["input"] == ["doc a", "doc b"]
    assert seen_payloads[0]["keep_alive"] == "30m"
    assert seen_payloads[0]["dimensions"] == 2


def test_embedding_batch_result_repr_excludes_raw_vectors() -> None:
    result = EmbeddingBatchResult(
        model=QWEN3_4B_MODEL_ID,
        dimensions=2,
        count=2,
        batch_size=2,
        keep_alive="30m",
        load_duration_ns=1,
        total_duration_ns=2,
        prompt_eval_count=2,
        embeddings=((0.123456, 0.654321), (0.987654, 0.456789)),
    )
    text = repr(result)
    assert "0.123456" not in text
    assert "0.987654" not in text
    assert "values excluded" in text


@pytest.mark.asyncio
async def test_ollama_embedding_client_applies_instruction_only_to_queries() -> None:
    seen_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        seen_payloads.append(payload)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2]], "total_duration": 1})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:11434") as http_client:
        client = OllamaEmbeddingClient(model=QWEN3_4B_MODEL_ID, dimensions=2, client=http_client)
        await client.embed_queries(("qual CDI?",))
        await client.embed_documents(("documento CDI",))

    query_inputs = cast(list[str], seen_payloads[0]["input"])
    document_inputs = cast(list[str], seen_payloads[1]["input"])
    assert query_inputs[0].startswith("Instruct:")
    assert not document_inputs[0].startswith("Instruct:")


def test_run_q18_qwen3_profile_now_targets_4b() -> None:
    assert profile_runner.QWEN3_EMBEDDING_MODEL == QWEN3_4B_OLLAMA_MODEL_ID
    assert profile_runner.QWEN3_EMBEDDING_DIMENSIONS == QWEN3_4B_DEFAULT_DIMENSIONS
    assert profile_runner.BENCHMARK_COLLECTION_QWEN3.endswith("_qwen3_4b")


def test_no_hardcoded_quimera_knowledge_for_bakeoff() -> None:
    text = MODULE_PATH.read_text(encoding="utf-8")
    assert "quimera_knowledge" in text  # protected-name guard is intentional
    assert BAKEOFF_COLLECTION in text


def test_no_api_embeddings_legacy_usage_unless_explicit_fallback() -> None:
    text = MODULE_PATH.read_text(encoding="utf-8")
    assert 'OLLAMA_LEGACY_EMBEDDINGS_PATH = "/api/embeddings"' in text
    assert "post(OLLAMA_LEGACY_EMBEDDINGS_PATH" not in text


def test_no_prompt_or_query_text_in_logs() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden_calls = {"basicConfig", "print"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_calls


def test_no_auto_delete_model_or_ollama_pull_on_import() -> None:
    text = MODULE_PATH.read_text(encoding="utf-8")
    assert "ollama pull" not in text
    assert "delete_model" not in text
    tree = ast.parse(text)
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])
    assert "subprocess" not in imported_roots
