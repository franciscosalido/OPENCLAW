"""Offline tests for Q18-05 Qdrant tuning profile contracts."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, cast

import pytest

from backend.rag.qdrant_tuning import (
    BenchmarkReadiness,
    IndexTuningConfig,
    QdrantTuningProfile,
    QuantizationConfig,
    QuantizationKind,
    QueryTuningConfig,
    TuningProfileName,
    balanced_local_profile,
    baseline_ram_profile,
    build_benchmark_summary,
    build_qdrant_collection_params,
    build_qdrant_search_params,
    default_tuning_profile,
    get_all_profiles,
    get_profile,
    high_precision_disk_profile,
    low_memory_profile,
    profile_registry,
    qdrant_monitoring_probe_config,
    turboquant_experimental_profile,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "backend/rag/qdrant_tuning.py"
DOC_PATH = ROOT / "docs/specs/qdrant-1-18-upgrade/tuning_profiles.md"


def test_all_profiles_are_defined_and_unique() -> None:
    profiles = get_all_profiles()

    assert len(profiles) == 5
    assert {profile.name for profile in profiles} == set(TuningProfileName)


def test_profile_order_is_deterministic() -> None:
    assert tuple(profile.name for profile in get_all_profiles()) == (
        TuningProfileName.BASELINE_RAM,
        TuningProfileName.BALANCED_LOCAL,
        TuningProfileName.LOW_MEMORY,
        TuningProfileName.TURBOQUANT_EXPERIMENTAL,
        TuningProfileName.HIGH_PRECISION_DISK,
    )


def test_default_profile_is_balanced_local_not_turboquant() -> None:
    profile = default_tuning_profile()

    assert profile.name is TuningProfileName.BALANCED_LOCAL
    assert profile.index_config.quantization is None
    assert profile.experimental is False
    assert profile.is_default_safe() is True


def test_baseline_ram_has_no_quantization_no_on_disk() -> None:
    profile = baseline_ram_profile()

    assert profile.index_config.dense_on_disk is False
    assert profile.index_config.hnsw_on_disk is False
    assert profile.index_config.quantization is None
    assert profile.benchmark_readiness is BenchmarkReadiness.BASELINE


def test_balanced_local_is_conservative() -> None:
    profile = balanced_local_profile()

    assert profile.index_config.dense_on_disk is False
    assert profile.index_config.hnsw_on_disk is False
    assert profile.index_config.quantization is None
    assert profile.requires_benchmark is False


def test_low_memory_uses_on_disk() -> None:
    profile = low_memory_profile()

    assert profile.index_config.dense_on_disk is True
    assert profile.index_config.hnsw_on_disk is True
    assert profile.index_config.quantization is None
    assert profile.requires_benchmark is True


def test_turboquant_is_experimental_and_requires_benchmark() -> None:
    profile = turboquant_experimental_profile()

    assert profile.experimental is True
    assert profile.requires_benchmark is True
    assert (
        profile.benchmark_readiness
        is BenchmarkReadiness.EXPERIMENTAL_REQUIRES_BENCHMARK
    )
    assert profile.index_config.quantization is not None
    assert profile.index_config.quantization.kind is QuantizationKind.TURBOQUANT


def test_high_precision_disk_uses_on_disk_without_turboquant() -> None:
    profile = high_precision_disk_profile()

    assert profile.index_config.dense_on_disk is True
    assert profile.index_config.hnsw_on_disk is True
    assert profile.index_config.quantization is None
    assert profile.recall_risk == "low"


def test_profiles_are_json_serializable() -> None:
    payload = [profile.to_safe_dict() for profile in get_all_profiles()]

    assert json.loads(json.dumps(payload))[1]["name"] == "balanced_local"


def test_profile_safe_dict_roundtrip_via_json() -> None:
    profile = turboquant_experimental_profile()
    loaded = json.loads(json.dumps(profile.to_safe_dict()))

    assert loaded["name"] == "turboquant_experimental"
    assert loaded["index_config"]["quantization"]["turbo_bits"] == "bits4"


def test_to_safe_dict_has_no_forbidden_fields() -> None:
    serialized = json.dumps([profile.to_safe_dict() for profile in get_all_profiles()])

    for forbidden in (
        "payload",
        "dense_vector",
        "sparse_vector",
        "embedding",
        "prompt",
    ):
        assert forbidden not in serialized


def test_summary_to_safe_dict_contains_profile_and_metrics() -> None:
    summary = build_benchmark_summary(
        profile=balanced_local_profile(),
        qdrant_server_version="1.18.0",
        qdrant_client_version="1.18.0",
        memory_report_available=True,
        latency_p50_ms=10.0,
        latency_p95_ms=20.0,
        recall_at_10=0.8,
        ndcg_at_5=0.7,
        peak_ram_mb=512.0,
    )
    payload = summary.to_safe_dict()

    assert payload["profile_name"] == "balanced_local"
    assert payload["latency_p95_ms"] == 20.0
    assert payload["recall_at_10"] == 0.8
    assert payload["peak_ram_mb"] == 512.0


def test_build_qdrant_collection_params_baseline() -> None:
    params = build_qdrant_collection_params(baseline_ram_profile())

    assert params == {
        "vectors_on_disk": False,
        "hnsw_config": {"on_disk": False},
        "tuning_profile": "baseline_ram",
    }


def test_build_qdrant_collection_params_low_memory() -> None:
    params = build_qdrant_collection_params(low_memory_profile())

    assert params["vectors_on_disk"] is True
    assert params["hnsw_config"] == {"on_disk": True}
    assert params["tuning_profile"] == "low_memory"


def test_build_qdrant_collection_params_turboquant() -> None:
    params = build_qdrant_collection_params(turboquant_experimental_profile())

    assert params["quantization_config"] == {
        "type": "turboquant",
        "bits": "bits4",
        "always_ram": True,
        "rescore": True,
    }


def test_build_qdrant_search_params_rescore() -> None:
    params = build_qdrant_search_params(turboquant_experimental_profile())

    assert params["quantization"] == {"rescore": True}
    assert params["oversampling_factor"] == 2.0


def test_to_qdrant_config_is_pure() -> None:
    profile = turboquant_experimental_profile()

    assert build_qdrant_collection_params(profile) == build_qdrant_collection_params(
        profile
    )
    assert build_qdrant_search_params(profile) == build_qdrant_search_params(profile)


def test_profiles_cover_search_params_space() -> None:
    profiles = get_all_profiles()

    assert any(
        profile.query_config.quantization_rescore is True for profile in profiles
    )
    assert any(profile.query_config.oversampling_factor == 2.0 for profile in profiles)
    assert all(profile.query_config.exact is False for profile in profiles)


def test_hnsw_ef_validation() -> None:
    with pytest.raises(ValueError, match="hnsw_ef"):
        QueryTuningConfig(hnsw_ef=0)
    with pytest.raises(TypeError, match="hnsw_ef"):
        QueryTuningConfig(hnsw_ef=True)


def test_oversampling_factor_validation() -> None:
    with pytest.raises(ValueError, match="oversampling_factor"):
        QueryTuningConfig(oversampling_factor=0.0)
    with pytest.raises(TypeError, match="oversampling_factor"):
        QueryTuningConfig(oversampling_factor=True)


def test_exact_flag_serializes() -> None:
    config = QueryTuningConfig(exact=True)

    assert config.to_safe_dict()["exact"] is True
    assert config.to_qdrant_search_params_dict()["exact"] is True


def test_get_profile_accepts_enum_and_string() -> None:
    assert get_profile(TuningProfileName.BALANCED_LOCAL) == balanced_local_profile()
    assert get_profile("balanced_local") == balanced_local_profile()


def test_get_profile_rejects_unknown() -> None:
    with pytest.raises(KeyError, match="unknown"):
        get_profile("unknown")


def test_get_profile_rejects_empty_name_as_malformed_input() -> None:
    with pytest.raises(ValueError, match="name cannot be empty"):
        get_profile("")


def test_registry_is_immutable() -> None:
    registry = profile_registry()

    with pytest.raises(TypeError):
        cast(Any, registry)["new"] = balanced_local_profile()


def test_profile_can_be_exposed_as_otel_attributes() -> None:
    attrs = turboquant_experimental_profile().to_otel_attributes()

    assert attrs["qdrant.profile"] == "turboquant_experimental"
    assert attrs["qdrant.quantization"] == "turboquant"
    assert attrs["qdrant.experimental"] is True


def test_monitoring_probe_config_has_metrics_and_telemetry_endpoints() -> None:
    config = qdrant_monitoring_probe_config(
        balanced_local_profile(),
        "quimera_benchmark_hybrid_118",
    )

    assert config["metrics_endpoint"] == "/metrics?per_collection=true"
    assert config["telemetry_endpoint"] == "/telemetry"
    assert config["purpose"] == "future_q18_benchmark_monitoring"


def test_monitoring_probe_config_does_not_call_network() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    target = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "qdrant_monitoring_probe_config"
    )
    forbidden = {"get", "post", "request", "connect", "send"}

    for node in ast.walk(target):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden


def test_otel_attribute_keys_are_stable() -> None:
    assert set(balanced_local_profile().to_otel_attributes()) == {
        "qdrant.profile",
        "qdrant.quantization",
        "qdrant.dense_on_disk",
        "qdrant.hnsw_on_disk",
        "qdrant.hnsw_ef",
        "qdrant.exact",
        "qdrant.quantization_rescore",
        "qdrant.oversampling_factor",
        "qdrant.experimental",
    }


def test_benchmark_summary_includes_memory_latency_quality_fields() -> None:
    payload = build_benchmark_summary(profile=low_memory_profile()).to_safe_dict()

    assert "memory_report_available" in payload
    assert "latency_p50_ms" in payload
    assert "latency_p95_ms" in payload
    assert "recall_at_10" in payload
    assert "ndcg_at_5" in payload
    assert "peak_ram_mb" in payload


def test_tuning_profiles_doc_exists() -> None:
    assert DOC_PATH.exists()


def test_docs_list_all_profile_names() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")

    for profile in TuningProfileName:
        assert profile.value in text


def test_docs_say_turboquant_not_default() -> None:
    text = DOC_PATH.read_text(encoding="utf-8").casefold()

    assert "turboquant nunca e default" in text or "turboquant is never default" in text


def test_docs_reference_monitoring_handoff() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "/metrics?per_collection=true" in text
    assert "/telemetry" in text
    assert "qdrant.profile" in text


def test_qdrant_tuning_does_not_import_qdrant_client() -> None:
    assert _imported_roots().isdisjoint({"qdrant_client"})


def test_qdrant_tuning_does_not_import_opentelemetry() -> None:
    assert _imported_roots().isdisjoint({"opentelemetry"})


def test_qdrant_tuning_does_not_import_requests_httpx() -> None:
    assert _imported_roots().isdisjoint({"requests", "httpx"})


def test_qdrant_tuning_has_no_network_calls() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden = {"get", "post", "request", "connect", "send"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden


def test_qdrant_tuning_has_no_collection_mutation_calls() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden = {
        "create_collection",
        "update_collection",
        "delete_collection",
        "recreate_collection",
        "upsert",
        "query_points",
        "search",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden


def test_profiles_do_not_hardcode_qdrant_version_except_docs_or_summary() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "1.18.0" not in source


def test_future_profile_addition_requires_registry_update() -> None:
    registry = profile_registry()

    assert set(registry) == {profile.value for profile in TuningProfileName}
    assert len(get_all_profiles()) == len(TuningProfileName)


def test_quantization_validation_contract() -> None:
    with pytest.raises(ValueError, match="none"):
        QuantizationConfig(kind=QuantizationKind.NONE, bits=8)
    with pytest.raises(ValueError, match="scalar"):
        QuantizationConfig(kind=QuantizationKind.SCALAR, bits=4)
    with pytest.raises(ValueError, match="turboquant"):
        QuantizationConfig(kind=QuantizationKind.TURBOQUANT, bits=8)


def test_summary_rejects_negative_or_non_finite_metrics() -> None:
    with pytest.raises(ValueError, match="latency_p95_ms"):
        build_benchmark_summary(
            profile=balanced_local_profile(),
            latency_p95_ms=-1.0,
        )
    with pytest.raises(ValueError, match="peak_ram_mb"):
        build_benchmark_summary(
            profile=balanced_local_profile(),
            peak_ram_mb=float("nan"),
        )


def test_index_config_rejects_non_bool_flags() -> None:
    with pytest.raises(TypeError, match="dense_on_disk"):
        IndexTuningConfig(dense_on_disk=cast(Any, "yes"), hnsw_on_disk=False)


def test_turboquant_profile_cannot_be_non_experimental() -> None:
    with pytest.raises(ValueError, match="turboquant"):
        QdrantTuningProfile(
            name=TuningProfileName.TURBOQUANT_EXPERIMENTAL,
            description="bad turbo profile",
            memory_goal="low",
            latency_risk="medium",
            recall_risk="unknown",
            index_config=IndexTuningConfig(
                dense_on_disk=False,
                hnsw_on_disk=False,
                quantization=QuantizationConfig(kind=QuantizationKind.TURBOQUANT),
            ),
            query_config=QueryTuningConfig(),
            experimental=False,
            requires_benchmark=True,
            benchmark_readiness=BenchmarkReadiness.EXPERIMENTAL_REQUIRES_BENCHMARK,
            intended_use="negative test",
        )


def _imported_roots() -> set[str]:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".")[0])
    return roots
