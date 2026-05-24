"""Offline tests for Q18-07 Qdrant 1.18 benchmark decisions."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import cast

import pytest

from evaluation import compare_qdrant_113_vs_118 as compare
from evaluation.compare_qdrant_113_vs_118 import (
    COMPARISONS,
    CSV_COLUMNS,
    BenchmarkDecision,
    BenchmarkScenarioResult,
    LatencyMetrics,
    QdrantBenchmarkRun,
    QualityMetrics,
    ResourceSnapshot,
    build_benchmark_span_attributes,
    build_comparison_span_attributes,
    build_summary,
    compute_deltas,
    latency_p95_multiplier,
    load_historical_baseline,
    machine_readable_decision,
    memory_reduction_pct,
    render_adr,
    render_markdown_report,
    render_svg_dashboard,
    write_csv,
    write_json,
    write_markdown_report,
    write_svg,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "evaluation/compare_qdrant_113_vs_118.py"
DOC_REPORT = ROOT / "docs/rag/qdrant_118_upgrade_results.md"
ADR_PATH = ROOT / "docs/ADR/ADR-0XX-qdrant-118-upgrade.md"


def _run(
    profile_name: str = "qdrant_118_baseline_ram",
    *,
    recall: float | None = 0.9,
    ndcg: float | None = 0.8,
    p95: float | None = 100.0,
    ram: float | None = 1000.0,
    fusion_backend: compare.FusionBackend = "python_rrf",
    retrieval_mode: compare.RetrievalMode = "hybrid",
    quantization: str = "none",
    metadata: dict[str, object] | None = None,
) -> QdrantBenchmarkRun:
    return QdrantBenchmarkRun(
        run_id=f"run-{profile_name}",
        scenario="fixture",
        qdrant_version="1.18.0",
        profile_name=profile_name,
        fusion_backend=fusion_backend,
        retrieval_mode=retrieval_mode,
        quantization=quantization,
        corpus_hash="corpus123",
        query_set_hash="queries123",
        quality=QualityMetrics(
            precision_at_5=0.7,
            recall_at_10=recall,
            mrr=0.75,
            ndcg_at_5=ndcg,
        ),
        latency=LatencyMetrics(
            p50_ms=50.0,
            p95_ms=p95,
            total_ms_p50=50.0,
            total_ms_p95=p95,
        ),
        resources=ResourceSnapshot(
            memory_report_available=True,
            peak_ram_mb=ram,
            collection_size_bytes=2048,
            vector_storage={"dense": "ram"},
            quantization=quantization,
            qdrant_server_version="1.18.0",
            qdrant_client_version="1.18.0",
        ),
        profile_config={"profile": profile_name},
        metadata=metadata or {},
    )


def _complete_runs() -> tuple[QdrantBenchmarkRun, ...]:
    return (
        _run("qdrant_113_historical_baseline", p95=120.0),
        _run("qdrant_118_baseline_ram", p95=100.0),
        _run("qdrant_118_balanced_local", p95=90.0),
        _run("qdrant_118_python_rrf", p95=100.0),
        _run(
            "qdrant_118_native_rrf",
            p95=95.0,
            fusion_backend="qdrant_rrf",
            metadata={"overlap_at_10": 0.96, "tie_break_regression_count": 0},
        ),
        _run("qdrant_118_no_quantization", p95=100.0, ram=1000.0),
        _run(
            "qdrant_118_turboquant_experimental",
            p95=80.0,
            ram=650.0,
            quantization="turboquant",
        ),
        _run("qdrant_118_dense_only", p95=80.0, retrieval_mode="dense_only"),
        _run("qdrant_118_hybrid", p95=100.0, retrieval_mode="hybrid"),
    )


def test_quality_metrics_to_safe_dict() -> None:
    assert QualityMetrics(precision_at_5=0.1).to_safe_dict()["precision_at_5"] == 0.1


def test_latency_metrics_to_safe_dict() -> None:
    assert LatencyMetrics(total_ms_p95=12.5).to_safe_dict()["total_ms_p95"] == 12.5


def test_resource_snapshot_missing_memory_report_is_valid() -> None:
    snapshot = ResourceSnapshot(memory_report_available=False)

    assert snapshot.to_safe_dict()["memory_report_available"] is False


def test_benchmark_run_safe_dict_has_no_sensitive_fields() -> None:
    payload = json.dumps(_run().to_safe_dict())

    assert "payload" not in payload
    assert "dense_vector" not in payload
    assert "embedding" not in payload


def test_summary_safety_flags_false() -> None:
    summary = build_summary(runs=())

    assert summary.to_safe_dict()["safety"] == {
        "includes_query_text": False,
        "includes_document_text": False,
        "includes_payload": False,
        "includes_vectors": False,
        "includes_embeddings": False,
    }


def test_compute_deltas_simple_quality_case() -> None:
    deltas = compute_deltas(_run(recall=0.5), _run(recall=0.7))
    recall_delta = cast(dict[str, object], deltas["recall_at_10"])

    assert recall_delta["absolute_delta"] == pytest.approx(0.2)
    assert recall_delta["winner"] == "profile_b"


def test_compute_deltas_latency_lower_is_better() -> None:
    deltas = compute_deltas(_run(p95=100.0), _run(p95=80.0))
    p95_delta = cast(dict[str, object], deltas["total_ms_p95"])

    assert p95_delta["winner"] == "profile_b"


def test_delta_pct_handles_zero_baseline() -> None:
    deltas = compute_deltas(_run(recall=0.0), _run(recall=0.2))
    recall_delta = cast(dict[str, object], deltas["recall_at_10"])

    assert recall_delta["relative_delta_pct"] is None


def test_missing_metric_yields_none_delta() -> None:
    deltas = compute_deltas(_run(recall=None), _run(recall=0.2))
    recall_delta = cast(dict[str, object], deltas["recall_at_10"])

    assert recall_delta["absolute_delta"] is None


def test_accept_qdrant_118_baseline_when_no_regression() -> None:
    summary = build_summary(runs=_complete_runs(), historical_baseline=None)

    assert summary.final_decision in {
        BenchmarkDecision.ACCEPT_QDRANT_118_BALANCED_PROFILE.value,
        BenchmarkDecision.ACCEPT_QDRANT_118_BASELINE.value,
    }


def test_defer_due_to_quality_regression() -> None:
    runs = tuple(
        _run("qdrant_113_historical_baseline", recall=0.9)
        if run.profile_name == "qdrant_113_historical_baseline"
        else _run(run.profile_name, recall=0.5)
        for run in _complete_runs()
    )

    assert build_summary(runs=runs).final_decision == BenchmarkDecision.DEFER_DUE_TO_REGRESSION.value


def test_turboquant_experimental_only_even_when_memory_improves() -> None:
    summary = build_summary(runs=_complete_runs())

    assert summary.turboquant_decision == BenchmarkDecision.ACCEPT_TURBOQUANT_EXPERIMENTAL_ONLY.value


def test_keep_python_rrf_default_without_native_clear_win() -> None:
    runs = tuple(
        _run("qdrant_118_native_rrf", metadata={"overlap_at_10": 0.5})
        if run.profile_name == "qdrant_118_native_rrf"
        else run
        for run in _complete_runs()
    )
    summary = build_summary(runs=runs)

    assert summary.native_rrf_decision == BenchmarkDecision.KEEP_PYTHON_RRF_DEFAULT.value
    assert summary.python_rrf_default is True


def test_promote_native_rrf_only_with_strong_evidence() -> None:
    summary = build_summary(runs=_complete_runs())

    assert summary.native_rrf_decision == BenchmarkDecision.PROMOTE_QDRANT_NATIVE_RRF.value


def test_inconclusive_when_baseline_missing() -> None:
    summary = build_summary(runs=(_run("qdrant_118_baseline_ram"),))

    assert summary.final_decision == BenchmarkDecision.INCONCLUSIVE_MISSING_EVIDENCE.value


def test_all_five_scenarios_are_declared() -> None:
    assert len(COMPARISONS) == 5


def test_scenario_ids_are_stable() -> None:
    assert tuple(item.scenario.value for item in COMPARISONS) == (
        "qdrant_113_vs_118_baseline",
        "qdrant_118_baseline_vs_balanced",
        "qdrant_118_python_rrf_vs_native_rrf",
        "qdrant_118_no_quant_vs_turboquant",
        "qdrant_118_dense_only_vs_hybrid",
    )


def test_scenario_summary_has_profile_a_and_b() -> None:
    summary = build_summary(runs=())

    assert all(scenario.profile_a and scenario.profile_b for scenario in summary.scenarios)


def test_postgresql_is_out_of_scope() -> None:
    assert build_summary(runs=()).postgresql_scope == "out_of_scope_for_q18"


def test_benchmark_span_attributes_are_otel_compatible() -> None:
    attrs = build_benchmark_span_attributes(scenario="s1", run=_run())

    assert attrs["benchmark.scenario"] == "s1"
    assert attrs["rag.qdrant.profile"] == "qdrant_118_baseline_ram"


def test_comparison_span_attributes_are_otel_compatible() -> None:
    result = BenchmarkScenarioResult(
        scenario="s1",
        profile_a="a",
        profile_b="b",
        run_a=None,
        run_b=None,
        deltas={},
        decision_hint="inconclusive_missing_evidence",
        evidence_complete=False,
    )

    assert build_comparison_span_attributes(result)["benchmark.evidence_complete"] is False


def test_attrs_do_not_include_query_text_payload_vectors() -> None:
    attrs = json.dumps(build_benchmark_span_attributes(scenario="s1", run=_run()))

    assert "query_text" not in attrs
    assert "payload" not in attrs
    assert "dense_vector" not in attrs


def test_svg_dashboard_renders() -> None:
    svg = render_svg_dashboard(build_summary(runs=()))

    assert "<svg" in svg


def test_svg_contains_quality_latency_resources_decision() -> None:
    svg = render_svg_dashboard(build_summary(runs=_complete_runs()))

    for label in ("Quality", "Latency", "Resources", "Decision", "Fusion"):
        assert label in svg


def test_svg_decision_matrix_contains_winner_confidence_decision() -> None:
    svg = render_svg_dashboard(build_summary(runs=()))

    for label in ("Winner", "Confidence", "Decision"):
        assert label in svg


def test_svg_handles_missing_values() -> None:
    assert "TBD" in render_svg_dashboard(build_summary(runs=()))


def test_svg_does_not_leak_sensitive_fields() -> None:
    svg = render_svg_dashboard(build_summary(runs=()))

    assert "payload" not in svg
    assert "embedding" not in svg
    assert "dense_vector" not in svg


def test_csv_header_exact(tmp_path: Path) -> None:
    csv_path = tmp_path / "rows.csv"
    write_csv(build_summary(runs=_complete_runs()), csv_path)
    header = csv_path.read_text(encoding="utf-8").splitlines()[0].split(",")

    assert tuple(header) == CSV_COLUMNS


def test_json_summary_parseable(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    write_json(build_summary(runs=()), path)

    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"]


def test_machine_readable_decision_block_parseable() -> None:
    block = machine_readable_decision(build_summary(runs=()))

    assert block["schema_version"] == "qdrant-118-decision-v1"


def test_report_contains_hypothesis_experiment_decision() -> None:
    report = render_markdown_report(build_summary(runs=()))

    assert "Hypotheses" in report
    assert "Decision" in report


def test_load_historical_baseline_none_marks_absent() -> None:
    assert load_historical_baseline(None) is None
    assert build_summary(runs=()).baseline_113_present is False


def test_artifact_only_does_not_call_qdrant() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))

    assert not any(isinstance(node, ast.Import) and "qdrant" in ast.dump(node) for node in ast.walk(tree))


def test_live_benchmark_requires_env_and_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUN_QDRANT_118_BENCHMARK", raising=False)

    assert compare.main(["--execute-live-benchmark"]) == 2


def test_script_does_not_import_qdrant_client_in_unit_path_unless_live_guarded() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "qdrant_client" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module != "qdrant_client"


def test_script_does_not_create_delete_collections() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden = {"create_collection", "delete_collection", "recreate_collection", "upsert"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden


def test_script_does_not_import_postgres_drivers() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "psycopg" not in source
    assert "asyncpg" not in source


def test_outputs_do_not_contain_forbidden_terms() -> None:
    output = json.dumps(build_summary(runs=()).to_safe_dict())

    for forbidden in ('"query_text"', "chunk_text", '"payload"', '"vector"', '"embedding"', '"prompt"', '"answer"'):
        assert forbidden not in output


def test_run_id_or_summary_deterministic_with_fixed_inputs() -> None:
    first = build_summary(runs=(), generated_at_utc="2026-05-24T00:00:00+00:00").to_safe_dict()
    second = build_summary(runs=(), generated_at_utc="2026-05-24T00:00:00+00:00").to_safe_dict()

    assert first == second


def test_seed_recorded_if_any_randomness_exists() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "random" not in source


def test_no_random_global_without_seed() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))

    assert not any(isinstance(node, ast.Import) and "random" in ast.dump(node) for node in ast.walk(tree))


def test_latency_and_memory_helpers() -> None:
    before = _run(p95=100.0, ram=1000.0)
    after = _run(p95=50.0, ram=700.0)

    assert latency_p95_multiplier(before, after) == 0.5
    assert memory_reduction_pct(before, after) == 30.0


def test_docs_exist() -> None:
    assert DOC_REPORT.exists()
    assert ADR_PATH.exists()


def test_writers_create_safe_artifacts(tmp_path: Path) -> None:
    summary = build_summary(runs=())
    write_markdown_report(summary, tmp_path / "report.md")
    write_svg(summary, tmp_path / "charts.svg")

    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "charts.svg").exists()


def test_render_adr_status_is_proposed_when_missing_evidence() -> None:
    adr = render_adr(build_summary(runs=()))

    assert "Status: Proposed" in adr


def test_results_gitkeep_documents_header_only_csv() -> None:
    text = (ROOT / "evaluation/results/.gitkeep").read_text(encoding="utf-8")

    assert "only a header" in text
    assert "artifact-only mode" in text


def test_report_and_adr_document_canonical_adr_directory() -> None:
    report = render_markdown_report(build_summary(runs=()))
    adr = render_adr(build_summary(runs=()))

    assert "canonical ADR directory" in report
    assert "docs/ADR" in report
    assert "p95_multiplier <= 1.0" in adr
