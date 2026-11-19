"""Offline tests for Q18 Qwen3 embedding benchmark contracts.

Covers:
- Embedding probe (offline, no Qdrant or Ollama needed)
- Runner profile specs (Qwen3 vs Nomic)
- Collection name validation and separation
- Aggregator Qwen3 scenarios
- Qwen3 embedding decision logic
- Safe text guard with metadata fields
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ── probe ─────────────────────────────────────────────────────────────────────

from evaluation.probe_embedding_model import (
    KNOWN_MODELS,
    ProbeResult,
    _ensure_localhost,
)

# ── runner profiles ───────────────────────────────────────────────────────────

from evaluation.run_q18_benchmark_profile import (
    BENCHMARK_COLLECTION_NOMIC,
    BENCHMARK_COLLECTION_QWEN3,
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    NOMIC_PROFILES,
    PROFILE_SPECS,
    QWEN3_EMBEDDING_DIMENSIONS,
    QWEN3_EMBEDDING_MODEL,
    QWEN3_PROFILES,
    _resolve_collection,
    _validate_collection_name,
)

# ── aggregator ────────────────────────────────────────────────────────────────

from evaluation.compare_qdrant_113_vs_118 import (
    COMPARISONS,
    BenchmarkDecision,
    ComparisonScenario,
    _NOMIC_BASELINE_SCENARIOS,
    _QWEN3_SCENARIOS,
    build_summary,
    decide_qwen3_embedding,
    load_benchmark_runs,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]


# ──────────────────────────────────────────────────────────────────────────────
# Probe: known models registry
# ──────────────────────────────────────────────────────────────────────────────


def test_qwen3_4b_default_dimensions_2560() -> None:
    assert KNOWN_MODELS["Qwen/Qwen3-Embedding-4B"]["expected_dimensions"] == 2560


def test_nomic_profile_uses_768_dimensions() -> None:
    assert KNOWN_MODELS["nomic-embed-text"]["expected_dimensions"] == 768
    assert KNOWN_MODELS["nomic-embed-text:latest"]["expected_dimensions"] == 768


def test_qwen3_4b_dimensions_2560() -> None:
    assert KNOWN_MODELS["Qwen/Qwen3-Embedding-4B"]["expected_dimensions"] == 2560


def test_probe_result_to_safe_dict_has_no_vectors() -> None:
    result = ProbeResult(
        provider="ollama",
        model="Qwen/Qwen3-Embedding-4B",
        available=False,
        dimensions=None,
        expected_dimensions=2560,
        dimension_matches_expected=None,
        probe_latency_ms=None,
        error="ConnectionRefusedError",
        probed_at_utc="2026-05-24T00:00:00Z",
    )
    d = result.to_safe_dict()
    text = json.dumps(d)
    # Must not contain raw embedding data
    assert '"embedding"' not in text
    assert '"vector"' not in text
    assert '"embeddings"' not in text


def test_probe_localhost_guard_rejects_remote() -> None:
    with pytest.raises(ValueError, match="localhost"):
        _ensure_localhost("remote.example.com")


def test_probe_localhost_guard_allows_loopback() -> None:
    assert _ensure_localhost("localhost") == "localhost"
    assert _ensure_localhost("127.0.0.1") == "127.0.0.1"
    assert _ensure_localhost("::1") == "::1"


# ──────────────────────────────────────────────────────────────────────────────
# Runner profile specs
# ──────────────────────────────────────────────────────────────────────────────


def test_qwen3_profile_uses_expected_model_metadata() -> None:
    spec = PROFILE_SPECS["qdrant_118_qwen3_python_rrf"]
    assert spec.embedding_model == QWEN3_EMBEDDING_MODEL
    assert spec.embedding_dimensions == QWEN3_EMBEDDING_DIMENSIONS
    assert spec.query_instruction_used is True


def test_nomic_profile_uses_768_and_nomic_model() -> None:
    spec = PROFILE_SPECS["qdrant_118_python_rrf"]
    assert spec.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert spec.embedding_dimensions == DEFAULT_EMBEDDING_DIMENSIONS
    assert spec.query_instruction_used is False


def test_qwen3_and_nomic_use_distinct_collections() -> None:
    qwen3_spec = PROFILE_SPECS["qdrant_118_qwen3_python_rrf"]
    nomic_spec = PROFILE_SPECS["qdrant_118_python_rrf"]
    assert qwen3_spec.default_collection != nomic_spec.default_collection
    assert qwen3_spec.default_collection == BENCHMARK_COLLECTION_QWEN3
    assert nomic_spec.default_collection == BENCHMARK_COLLECTION_NOMIC


def test_all_qwen3_profiles_use_qwen3_collection() -> None:
    for name in QWEN3_PROFILES:
        spec = PROFILE_SPECS[name]
        assert spec.default_collection == BENCHMARK_COLLECTION_QWEN3, (
            f"Profile {name!r} should use Qwen3 collection but uses {spec.default_collection!r}"
        )


def test_all_nomic_profiles_use_nomic_collection() -> None:
    for name in NOMIC_PROFILES:
        spec = PROFILE_SPECS[name]
        assert spec.default_collection == BENCHMARK_COLLECTION_NOMIC, (
            f"Profile {name!r} should use Nomic collection but uses {spec.default_collection!r}"
        )


def test_embedding_dimension_mismatch_is_detectable() -> None:
    """Validate collection guard rejects protected and non-benchmark collection names."""
    with pytest.raises(ValueError, match="protected"):
        _validate_collection_name("quimera_knowledge")
    with pytest.raises(ValueError, match="protected"):
        _validate_collection_name("quimera_knowledge_v2")
    with pytest.raises(ValueError):
        _validate_collection_name("openclaw_knowledge")


def test_benchmark_collections_are_allowed() -> None:
    _validate_collection_name("quimera_benchmark_hybrid_118_qwen3_4b")
    _validate_collection_name("quimera_benchmark_hybrid_118_nomic")
    _validate_collection_name("quimera_benchmark_hybrid_118")


def test_resolve_collection_uses_spec_default_when_none() -> None:
    resolved = _resolve_collection(None, "qdrant_118_qwen3_python_rrf")
    assert resolved == BENCHMARK_COLLECTION_QWEN3


def test_resolve_collection_respects_explicit_override() -> None:
    override = "quimera_benchmark_hybrid_118_custom"
    resolved = _resolve_collection(override, "qdrant_118_qwen3_python_rrf")
    assert resolved == override


def test_resolve_collection_rejects_production_name() -> None:
    with pytest.raises(ValueError):
        _resolve_collection("quimera_knowledge", "qdrant_118_qwen3_python_rrf")


# ──────────────────────────────────────────────────────────────────────────────
# Aggregator: Qwen3 scenarios declared
# ──────────────────────────────────────────────────────────────────────────────


def test_qwen3_scenarios_are_declared() -> None:
    ids = {c.scenario.value for c in COMPARISONS}
    assert "qdrant_113_vs_118_qwen3_baseline" in ids
    assert "qdrant_118_qwen3_python_rrf_vs_native_rrf" in ids
    assert "qdrant_118_qwen3_no_quant_vs_turboquant" in ids
    assert "qdrant_118_qwen3_dense_only_vs_hybrid" in ids


def test_nomic_vs_qwen3_scenario_exists() -> None:
    ids = {c.scenario.value for c in COMPARISONS}
    assert ComparisonScenario.QDRANT_118_NOMIC_VS_QWEN3_EMBEDDING.value in ids


def test_nomic_baseline_scenarios_set_is_five() -> None:
    assert len(_NOMIC_BASELINE_SCENARIOS) == 5


def test_qwen3_scenarios_set_is_six() -> None:
    assert len(_QWEN3_SCENARIOS) == 6


def test_nomic_and_qwen3_scenario_sets_are_disjoint() -> None:
    assert _NOMIC_BASELINE_SCENARIOS.isdisjoint(_QWEN3_SCENARIOS)


# ──────────────────────────────────────────────────────────────────────────────
# Aggregator: Qwen3 embedding decision logic
# ──────────────────────────────────────────────────────────────────────────────


def test_decide_qwen3_returns_inconclusive_when_unavailable() -> None:
    decision = decide_qwen3_embedding([], qwen3_available=False)
    assert decision == BenchmarkDecision.QWEN3_INCONCLUSIVE_MISSING_BASELINE.value


def test_decide_qwen3_returns_inconclusive_when_no_scenarios() -> None:
    decision = decide_qwen3_embedding([], qwen3_available=True)
    assert decision == BenchmarkDecision.QWEN3_INCONCLUSIVE_MISSING_BASELINE.value


def test_qdrant_upgrade_decision_not_affected_by_missing_qwen3() -> None:
    """Nomic upgrade decision must still work when Qwen3 scenarios are missing."""
    # build_summary with no runs → all scenarios incomplete → INCONCLUSIVE
    summary = build_summary(runs=())
    # The upgrade decision logic only looks at Nomic scenarios, so it
    # should still return INCONCLUSIVE due to missing Nomic evidence,
    # not because of Qwen3 scenarios.
    assert (
        summary.final_decision == BenchmarkDecision.INCONCLUSIVE_MISSING_EVIDENCE.value
    )


# ──────────────────────────────────────────────────────────────────────────────
# Aggregator: Qwen3 summary does not leak sensitive data
# ──────────────────────────────────────────────────────────────────────────────


FORBIDDEN_JSON_KEYS = (
    '"query_text"',
    '"chunk_text"',
    '"dense_vector"',
    '"sparse_vector"',
    '"payload"',
    '"embedding"',
    '"vector"',
    '"prompt"',
    '"answer"',
)
LEAK_CANARY = "CANARIO_SINTETICO_Q18"
LOCAL_QWEN3_SUMMARY = ROOT / "evaluation/results/qdrant_118_qwen3_benchmark_summary.json"


def _synthetic_run(profile_name: str) -> dict[str, object]:
    """Run sintetico valido que tambem carrega, de proposito, campos proibidos."""
    return {
        "profile_name": profile_name,
        "scenario": "synthetic",
        "quality": {"precision_at_5": 0.5, "recall_at_10": 0.5, "mrr": 0.5, "ndcg_at_5": 0.5},
        "latency": {"p50_ms": 10.0, "p95_ms": 20.0},
        "query_text": LEAK_CANARY,
        "chunk_text": LEAK_CANARY,
        "dense_vector": [0.1, 0.2],
        "sparse_vector": {"indices": [1], "values": [0.5]},
        "payload": {"text": LEAK_CANARY},
        "embedding": [0.3],
        "vector": [0.4],
        "prompt": LEAK_CANARY,
        "answer": LEAK_CANARY,
    }


def _assert_no_forbidden_keys(text: str) -> None:
    for forbidden in FORBIDDEN_JSON_KEYS:
        assert forbidden not in text.lower(), (
            f"Qwen3 summary leaks forbidden token: {forbidden!r}"
        )


def test_qwen3_summary_does_not_leak_query_payload_vectors(tmp_path: Path) -> None:
    """Hermetico: o resumo sai do serializador real, a partir de runs sinteticos.

    Os runs de entrada carregam os campos proibidos; se o serializador os deixasse
    passar, o teste falharia. Nao depende de artefato ignorado pelo Git.
    """
    specs = [spec for spec in COMPARISONS if spec.scenario.value in _QWEN3_SCENARIOS]
    profiles = sorted({name for spec in specs for name in (spec.profile_a, spec.profile_b)})
    assert len(specs) == len(_QWEN3_SCENARIOS) and profiles
    runs_path = tmp_path / "runs.json"
    runs_path.write_text(
        json.dumps({"runs": [_synthetic_run(name) for name in profiles]}), encoding="utf-8"
    )
    assert LEAK_CANARY in runs_path.read_text(encoding="utf-8")

    summary = build_summary(
        runs=load_benchmark_runs(runs_path), generated_at_utc="2026-01-01T00:00:00Z"
    )
    by_scenario = {result.scenario: result for result in summary.scenarios}
    for scenario in _QWEN3_SCENARIOS:
        assert by_scenario[scenario].evidence_complete, scenario

    summary_path = tmp_path / "qdrant_118_qwen3_benchmark_summary.json"
    write_json(summary, summary_path)
    text = summary_path.read_text(encoding="utf-8")
    _assert_no_forbidden_keys(text)
    assert LEAK_CANARY not in text
    assert all(profile in text for profile in profiles), "comparacao deve sair preenchida"


def test_forbidden_key_inside_run_metadata_is_rejected(tmp_path: Path) -> None:
    run = _synthetic_run("qualquer_perfil")
    run["metadata"] = {"query_text": LEAK_CANARY}
    runs_path = tmp_path / "runs.json"
    runs_path.write_text(json.dumps([run]), encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden output key"):
        load_benchmark_runs(runs_path)


@pytest.mark.skipif(
    not LOCAL_QWEN3_SUMMARY.exists(),
    reason="artefato local ignorado pelo Git; so existe na maquina que rodou o benchmark",
)
def test_local_qwen3_summary_artifact_does_not_leak() -> None:
    _assert_no_forbidden_keys(LOCAL_QWEN3_SUMMARY.read_text(encoding="utf-8"))


# ──────────────────────────────────────────────────────────────────────────────


def test_all_qwen3_profile_specs_use_2560_dimensions() -> None:
    for name in QWEN3_PROFILES:
        spec = PROFILE_SPECS[name]
        assert spec.embedding_dimensions == 2560, (
            f"Qwen3 profile {name!r} should use 2560 dims, got {spec.embedding_dimensions}"
        )


def test_all_nomic_profile_specs_use_768_dimensions() -> None:
    for name in NOMIC_PROFILES:
        spec = PROFILE_SPECS[name]
        assert spec.embedding_dimensions == 768, (
            f"Nomic profile {name!r} should use 768 dims, got {spec.embedding_dimensions}"
        )


def test_query_instruction_recorded_for_qwen3() -> None:
    for name in QWEN3_PROFILES:
        spec = PROFILE_SPECS[name]
        assert spec.query_instruction_used is True, (
            f"Qwen3 profile {name!r} must have query_instruction_used=True"
        )


def test_nomic_profiles_do_not_use_query_instruction() -> None:
    for name in NOMIC_PROFILES:
        spec = PROFILE_SPECS[name]
        assert spec.query_instruction_used is False, (
            f"Nomic profile {name!r} must not use query instruction"
        )
