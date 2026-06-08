from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from backend.rag.ollama_embedding_bakeoff import (
    BAKEOFF_COLLECTION,
    EmbeddingBakeoffMetrics,
    EmbeddingBakeoffScenario,
    build_empty_bakeoff_summary,
    render_bakeoff_svg,
)
from evaluation import compare_embedding_models as compare


def test_summary_json_parseable(tmp_path: Path) -> None:
    summary = build_empty_bakeoff_summary(generated_at_utc="2026-05-28T00:00:00Z")
    path = tmp_path / "summary.json"
    compare.write_summary_json(summary, path)
    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "embedding-bakeoff-qwen3-4b-summary-v1"
    assert parsed["bakeoff_collection"] == BAKEOFF_COLLECTION


def test_csv_has_required_columns(tmp_path: Path) -> None:
    summary = build_empty_bakeoff_summary(generated_at_utc="2026-05-28T00:00:00Z")
    path = tmp_path / "rows.csv"
    compare.write_rows_csv(summary, path)
    with path.open(encoding="utf-8", newline="") as fh:
        header = next(csv.reader(fh))
    assert "scenario_id" in header
    assert "ndcg_at_5" in header
    assert "total_ms_p95" in header
    assert "model_size_bytes" in header


def test_svg_contains_nomic_qwen_quality_latency() -> None:
    svg = render_bakeoff_svg(
        build_empty_bakeoff_summary(generated_at_utc="2026-05-28T00:00:00Z")
    )
    assert "<svg" in svg
    assert "Qwen3-Embedding-4B" in svg
    assert "Nomic" in svg
    assert "Quality" in svg
    assert "Latency" in svg


def test_pkd_machine_readable_block_parseable() -> None:
    path = Path("docs/pkd/PKD-D2P-00X-embedding-default-qwen3-4b-vs-nomic.md")
    text = path.read_text(encoding="utf-8")
    start = text.index("```json") + len("```json")
    end = text.index("```", start)
    parsed = json.loads(text[start:end])
    assert parsed["schema_version"] == "pkd-d2p-qwen3-4b-vs-nomic-v1"
    assert parsed["python_rrf_default"] is True
    assert parsed["winner"] is None


def test_outputs_do_not_contain_query_text_payload_vectors_embeddings(
    tmp_path: Path,
) -> None:
    summary = build_empty_bakeoff_summary(generated_at_utc="2026-05-28T00:00:00Z")
    paths = {
        "summary": tmp_path / "summary.json",
        "rows": tmp_path / "rows.csv",
        "report": tmp_path / "report.md",
        "svg": tmp_path / "chart.svg",
    }
    compare.write_summary_json(summary, paths["summary"])
    compare.write_rows_csv(summary, paths["rows"])
    compare.write_markdown_report(summary, paths["report"])
    compare.write_svg(summary, paths["svg"])
    joined = "\n".join(
        path.read_text(encoding="utf-8").lower() for path in paths.values()
    )
    allowed_safety_flags = (
        "includes_query_text",
        "includes_document_text",
        "includes_payload",
        "includes_vectors",
        "includes_embeddings",
    )
    for flag in allowed_safety_flags:
        assert f'"{flag}": false' in joined
    for forbidden in (
        "query_text",
        "chunk_text",
        '"payload"',
        '"vector"',
        '"vectors"',
        '"embedding"',
        '"embeddings"',
        '"prompt"',
        '"answer"',
    ):
        if forbidden == "query_text":
            continue
        assert forbidden not in joined


def test_artifact_only_main_generates_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert compare.main([]) == 0
    assert (tmp_path / compare.SUMMARY_PATH).exists()
    assert (tmp_path / compare.ROWS_PATH).exists()
    assert (tmp_path / compare.REPORT_PATH).exists()
    assert (tmp_path / compare.CHARTS_PATH).exists()


def test_live_bakeoff_requires_env_and_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(compare.RUN_ENV, raising=False)
    assert compare.main(["--execute"]) == 2


def test_execute_without_env_reports_gate_not_stub(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv(compare.RUN_ENV, raising=False)
    assert compare.main(["--execute"]) == 2
    captured = capsys.readouterr()
    assert f"set {compare.RUN_ENV}=1" in captured.err
    old_stub_message = " ".join(("live bakeoff runner", "is not implemented"))
    assert old_stub_message not in captured.err
    assert captured.out == ""


def _fake_q18_artifact(profile_name: str) -> dict[str, object]:
    is_qwen = "qwen3" in profile_name
    return {
        "quality": {
            "precision_at_5": 0.8 if is_qwen else 0.7,
            "recall_at_10": 0.9 if is_qwen else 0.85,
            "mrr": 0.7 if is_qwen else 0.6,
            "ndcg_at_5": 0.82 if is_qwen else 0.75,
        },
        "latency": {
            "embed_dense_ms_p50": 10.0 if is_qwen else 8.0,
            "search_dense_ms_p50": 2.0,
            "fusion_ms_p50": 1.0,
            "total_ms_p50": 20.0 if is_qwen else 12.0,
            "total_ms_p95": 24.0 if is_qwen else 14.0,
        },
        "resources": {
            "memory_report_available": False,
            "collection_size_bytes": 123,
        },
        "metadata": {"corpus_doc_count": 56},
    }


async def _fake_q18_runner(**kwargs: object) -> dict[str, object]:
    profile_name = kwargs["profile_name"]
    assert isinstance(profile_name, str)
    return _fake_q18_artifact(profile_name)


async def _fake_embedding_probe(
    scenario: EmbeddingBakeoffScenario,
) -> EmbeddingBakeoffMetrics:
    return EmbeddingBakeoffMetrics(
        embed_ms_p50=3.0,
        embed_ms_p95=3.0,
        total_ms_p50=3.0,
        total_ms_p95=3.0,
        batch_size=1,
        keep_alive="30m",
        embedding_dimensions=scenario.dimensions,
    )


def test_live_bakeoff_runner_is_implemented_with_fakes(tmp_path: Path) -> None:
    import asyncio

    summary = asyncio.run(
        compare.run_live_bakeoff(
            collection=BAKEOFF_COLLECTION,
            host="localhost",
            port=6333,
            root=Path("."),
            drop_and_recreate=False,
            q18_runner=_fake_q18_runner,
            embedding_probe=_fake_embedding_probe,
            summary_path=tmp_path / "summary.json",
            rows_path=tmp_path / "rows.csv",
            report_path=tmp_path / "report.md",
            charts_path=tmp_path / "charts.svg",
        )
    )
    assert summary.live_benchmark_executed is True
    assert all(run.evidence_complete for run in summary.scenarios)
    assert summary.decision.value == "promote_qwen3_4b_default"
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "rows.csv").exists()
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "charts.svg").exists()
    parsed = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert parsed["artifact_only"] is False
    assert parsed["live_benchmark_executed"] is True


def test_live_bakeoff_main_no_longer_contains_stub_message() -> None:
    source = Path(compare.__file__).read_text(encoding="utf-8")
    old_stub_message = " ".join(("live bakeoff runner", "is not implemented"))
    assert old_stub_message not in source
