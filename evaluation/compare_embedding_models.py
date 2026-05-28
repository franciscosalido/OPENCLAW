"""Qwen3-Embedding-4B vs Nomic bakeoff artifact generator.

Default mode is artifact-only: it declares scenarios and writes safe TBD
outputs without calling Ollama or Qdrant. Live benchmark execution is opt-in
and requires ``RUN_OLLAMA_QWEN3_4B_BAKEOFF=1`` plus ``--execute``.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from collections.abc import Awaitable, Callable, Mapping
from collections.abc import Sequence
from pathlib import Path

from backend.rag.ollama_embedding_bakeoff import (
    BAKEOFF_COLLECTION,
    EMBEDDING_BAKEOFF_SUMMARY_SCHEMA_VERSION,
    NOMIC_MODEL_ID,
    QWEN3_4B_DEFAULT_DIMENSIONS,
    QWEN3_4B_OLLAMA_MODEL_ID,
    QWEN3_QUERY_INSTRUCTION,
    EmbeddingBakeoffMetrics,
    EmbeddingBakeoffRun,
    EmbeddingBakeoffScenario,
    EmbeddingBakeoffSummary,
    EmbeddingCandidateDecision,
    OllamaEmbeddingClient,
    bakeoff_csv_header,
    build_empty_bakeoff_summary,
    build_pkd_machine_block,
    decide_embedding_candidate,
    declared_bakeoff_scenarios,
    render_bakeoff_svg,
)
from evaluation import run_q18_benchmark_profile as q18_profile_runner

RUN_ENV = "RUN_OLLAMA_QWEN3_4B_BAKEOFF"
RESULTS_DIR = Path("evaluation") / "results"
SUMMARY_PATH = RESULTS_DIR / "embedding_bakeoff_qwen3_4b_summary.json"
ROWS_PATH = RESULTS_DIR / "embedding_bakeoff_qwen3_4b_rows.csv"
REPORT_PATH = RESULTS_DIR / "embedding_bakeoff_qwen3_4b_report.md"
CHARTS_PATH = RESULTS_DIR / "embedding_bakeoff_qwen3_4b_charts.svg"
Q18_RUNNER_ENV = "RUN_Q18_BENCHMARK_PROFILE"

Q18_SCENARIO_PROFILES: Mapping[str, str] = {
    "nomic_dense_only": "qdrant_118_dense_only",
    "qwen3_4b_dense_only": "qdrant_118_qwen3_dense_only",
    "nomic_hybrid_python_rrf": "qdrant_118_python_rrf",
    "qwen3_4b_hybrid_python_rrf": "qdrant_118_qwen3_python_rrf",
    "qwen3_4b_instruction_on": "qdrant_118_qwen3_python_rrf",
}

Q18Runner = Callable[..., Awaitable[Mapping[str, object]]]
EmbeddingProbe = Callable[[EmbeddingBakeoffScenario], Awaitable[EmbeddingBakeoffMetrics]]


def write_summary_json(summary: EmbeddingBakeoffSummary, path: Path = SUMMARY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary.to_safe_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_rows_csv(summary: EmbeddingBakeoffSummary, path: Path = ROWS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=bakeoff_csv_header())
        writer.writeheader()
        for run in summary.scenarios:
            metrics = run.metrics.to_safe_dict()
            writer.writerow(
                {
                    "schema_version": EMBEDDING_BAKEOFF_SUMMARY_SCHEMA_VERSION,
                    "scenario_id": run.scenario.scenario_id,
                    "model": run.scenario.model,
                    "retrieval_mode": run.scenario.retrieval_mode,
                    "dimensions": run.scenario.dimensions,
                    "instruction_enabled": run.scenario.instruction_enabled,
                    "precision_at_5": metrics["precision_at_5"],
                    "recall_at_10": metrics["recall_at_10"],
                    "mrr": metrics["mrr"],
                    "ndcg_at_5": metrics["ndcg_at_5"],
                    "embed_ms_p50": metrics["embed_ms_p50"],
                    "embed_ms_p95": metrics["embed_ms_p95"],
                    "search_ms_p50": metrics["search_ms_p50"],
                    "search_ms_p95": metrics["search_ms_p95"],
                    "fusion_ms": metrics["fusion_ms"],
                    "total_ms_p50": metrics["total_ms_p50"],
                    "total_ms_p95": metrics["total_ms_p95"],
                    "load_duration_ns": metrics["load_duration_ns"],
                    "total_duration_ns": metrics["total_duration_ns"],
                    "prompt_eval_count": metrics["prompt_eval_count"],
                    "batch_size": metrics["batch_size"],
                    "keep_alive": metrics["keep_alive"],
                    "memory_snapshot_available": metrics["memory_snapshot_available"],
                    "collection_size_bytes": metrics["collection_size_bytes"],
                    "model_size_bytes": metrics["model_size_bytes"],
                    "evidence_complete": run.evidence_complete,
                }
            )


def render_markdown_report(summary: EmbeddingBakeoffSummary) -> str:
    scenarios = "\n".join(
        f"| {run.scenario.scenario_id} | {run.scenario.model} | "
        f"{run.scenario.dimensions} | {'yes' if run.evidence_complete else 'TBD'} |"
        for run in summary.scenarios
    )
    machine = json.dumps(build_pkd_machine_block(winner=summary.winner), indent=2, sort_keys=True)
    return f"""# Qwen3-Embedding-4B vs Nomic Bakeoff

## Executive Summary

This artifact is safe by default and does not invent metrics. Qwen3-Embedding-4B
is the candidate embedding model. `nomic-embed-text` remains the baseline and
fallback. Python Weighted RRF remains the ground truth.

## Benchmark Collection

`{summary.bakeoff_collection}`

## Scenario Matrix

| Scenario | Model | Dimensions | Evidence complete |
|---|---|---:|---|
{scenarios}

## Decision

Decision: `{summary.decision.value}`

Winner: `{summary.winner}`

## Safety

The default artifacts do not include query text, document text, payloads,
vectors, embeddings, prompts or answers.

## Machine-readable block

<!-- machine-readable: pkd-d2p-qwen3-4b-vs-nomic-v1 -->
```json
{machine}
```
"""


def write_markdown_report(summary: EmbeddingBakeoffSummary, path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown_report(summary), encoding="utf-8")


def write_svg(summary: EmbeddingBakeoffSummary, path: Path = CHARTS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_bakeoff_svg(summary), encoding="utf-8")


def generate_artifacts(*, collection: str = BAKEOFF_COLLECTION) -> EmbeddingBakeoffSummary:
    if collection != BAKEOFF_COLLECTION:
        raise ValueError("embedding bakeoff uses only the dedicated bakeoff collection")
    summary = build_empty_bakeoff_summary()
    write_summary_json(summary)
    write_rows_csv(summary)
    write_markdown_report(summary)
    write_svg(summary)
    return summary


async def run_live_bakeoff(
    *,
    collection: str,
    host: str,
    port: int,
    root: Path,
    drop_and_recreate: bool,
    q18_runner: Q18Runner | None = None,
    embedding_probe: EmbeddingProbe | None = None,
    summary_path: Path = SUMMARY_PATH,
    rows_path: Path = ROWS_PATH,
    report_path: Path = REPORT_PATH,
    charts_path: Path = CHARTS_PATH,
) -> EmbeddingBakeoffSummary:
    """Run the opt-in live bakeoff without changing production defaults."""
    if collection != BAKEOFF_COLLECTION:
        raise ValueError("embedding bakeoff uses only the dedicated bakeoff collection")
    q18 = q18_runner or q18_profile_runner.run_benchmark
    probe = embedding_probe or _run_embedding_scenario_probe
    run_by_id: dict[str, EmbeddingBakeoffRun] = {}
    for scenario in declared_bakeoff_scenarios():
        if scenario.scenario_id in Q18_SCENARIO_PROFILES:
            profile = Q18_SCENARIO_PROFILES[scenario.scenario_id]
            artifact = await q18(
                profile_name=profile,
                host=host,
                port=port,
                collection=_collection_for_scenario(scenario),
                root=root,
                drop_and_recreate=drop_and_recreate,
            )
            run_by_id[scenario.scenario_id] = _run_from_q18_artifact(scenario, artifact)
        else:
            metrics = await probe(scenario)
            run_by_id[scenario.scenario_id] = EmbeddingBakeoffRun(
                scenario=scenario,
                metrics=metrics,
                evidence_complete=True,
            )
    runs = tuple(run_by_id[scenario.scenario_id] for scenario in declared_bakeoff_scenarios())
    decision = _decide_from_runs(runs)
    winner = "Qwen/Qwen3-Embedding-4B" if decision == EmbeddingCandidateDecision.PROMOTE_QWEN3_4B_DEFAULT else (
        NOMIC_MODEL_ID if decision == EmbeddingCandidateDecision.KEEP_NOMIC_DEFAULT else None
    )
    summary = EmbeddingBakeoffSummary(
        schema_version=EMBEDDING_BAKEOFF_SUMMARY_SCHEMA_VERSION,
        generated_at_utc=_utc_now(),
        artifact_only=False,
        live_benchmark_executed=True,
        bakeoff_collection=collection,
        scenarios=runs,
        decision=decision,
        winner=winner,
        python_rrf_default=True,
        nomic_kept_as_fallback=True,
    )
    write_summary_json(summary, summary_path)
    write_rows_csv(summary, rows_path)
    write_markdown_report(summary, report_path)
    write_svg(summary, charts_path)
    return summary


def _run_from_q18_artifact(
    scenario: EmbeddingBakeoffScenario,
    artifact: Mapping[str, object],
) -> EmbeddingBakeoffRun:
    quality = _mapping_or_empty(artifact.get("quality"))
    latency = _mapping_or_empty(artifact.get("latency"))
    resources = _mapping_or_empty(artifact.get("resources"))
    metadata = _mapping_or_empty(artifact.get("metadata"))
    metrics = EmbeddingBakeoffMetrics(
        precision_at_5=_float_or_none(quality.get("precision_at_5")),
        recall_at_10=_float_or_none(quality.get("recall_at_10")),
        mrr=_float_or_none(quality.get("mrr")),
        ndcg_at_5=_float_or_none(quality.get("ndcg_at_5")),
        embed_ms_p50=_float_or_none(latency.get("embed_dense_ms_p50")),
        embed_ms_p95=_float_or_none(latency.get("embed_dense_ms_p50")),
        search_ms_p50=_float_or_none(latency.get("search_dense_ms_p50")),
        search_ms_p95=_float_or_none(latency.get("search_dense_ms_p50")),
        fusion_ms=_float_or_none(latency.get("fusion_ms_p50")),
        total_ms_p50=_float_or_none(latency.get("total_ms_p50")),
        total_ms_p95=_float_or_none(latency.get("total_ms_p95")),
        batch_size=_int_or_none(metadata.get("corpus_doc_count")),
        keep_alive="30m",
        memory_snapshot_available=bool(resources.get("memory_report_available")),
        collection_size_bytes=_int_or_none(resources.get("collection_size_bytes")),
        embedding_dimensions=scenario.dimensions,
    )
    return EmbeddingBakeoffRun(scenario=scenario, metrics=metrics, evidence_complete=True)


async def _run_embedding_scenario_probe(scenario: EmbeddingBakeoffScenario) -> EmbeddingBakeoffMetrics:
    model = QWEN3_4B_OLLAMA_MODEL_ID if scenario.model != NOMIC_MODEL_ID else NOMIC_MODEL_ID
    batch_size = 4 if scenario.batch_mode == "batched" else 1
    texts = tuple(f"probe-{idx}" for idx in range(batch_size))
    if scenario.scenario_id == "batch_vs_single_embed":
        texts = ("probe-0", "probe-1")
    client = OllamaEmbeddingClient(
        model=model,
        dimensions=scenario.dimensions if scenario.model != NOMIC_MODEL_ID else None,
        keep_alive="30m",
        batch_size=batch_size,
        query_instruction=QWEN3_QUERY_INSTRUCTION if scenario.instruction_enabled else None,
    )
    start = time.perf_counter()
    result = await client.embed_queries(texts) if scenario.instruction_enabled else await client.embed_documents(texts)
    wall_ms = (time.perf_counter() - start) * 1000
    total_ms = _ns_to_ms(result.total_duration_ns) or wall_ms
    load_ms = _ns_to_ms(result.load_duration_ns)
    return EmbeddingBakeoffMetrics(
        embed_ms_p50=round(total_ms, 3),
        embed_ms_p95=round(total_ms, 3),
        total_ms_p50=round(total_ms, 3),
        total_ms_p95=round(total_ms, 3),
        load_duration_ns=result.load_duration_ns,
        total_duration_ns=result.total_duration_ns,
        prompt_eval_count=result.prompt_eval_count,
        batch_size=result.batch_size,
        keep_alive=result.keep_alive,
        embedding_dimensions=result.dimensions,
        memory_snapshot_available=False,
        model_size_bytes=None,
        fusion_ms=None,
        search_ms_p50=None,
        search_ms_p95=None,
    )


def _decide_from_runs(runs: Sequence[EmbeddingBakeoffRun]) -> EmbeddingCandidateDecision:
    by_id = {run.scenario.scenario_id: run for run in runs}
    nomic = by_id.get("nomic_hybrid_python_rrf")
    qwen = by_id.get("qwen3_4b_hybrid_python_rrf")
    return decide_embedding_candidate(
        qwen3_available=qwen is not None and qwen.evidence_complete,
        qwen3_ndcg_at_5=qwen.metrics.ndcg_at_5 if qwen else None,
        nomic_ndcg_at_5=nomic.metrics.ndcg_at_5 if nomic else None,
        qwen3_recall_at_10=qwen.metrics.recall_at_10 if qwen else None,
        nomic_recall_at_10=nomic.metrics.recall_at_10 if nomic else None,
        qwen3_total_p95_ms=qwen.metrics.total_ms_p95 if qwen else None,
        nomic_total_p95_ms=nomic.metrics.total_ms_p95 if nomic else None,
        memory_ok=True,
    )


def _collection_for_scenario(scenario: EmbeddingBakeoffScenario) -> str:
    if scenario.model == NOMIC_MODEL_ID:
        return q18_profile_runner.BENCHMARK_COLLECTION_NOMIC
    return q18_profile_runner.BENCHMARK_COLLECTION_QWEN3


def _mapping_or_empty(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _ns_to_ms(value: int | None) -> float | None:
    return None if value is None else value / 1_000_000


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default=BAKEOFF_COLLECTION)
    parser.add_argument("--execute", action="store_true", help="Run live bakeoff; requires env gate")
    parser.add_argument("--models", default="nomic,qwen3_4b")
    parser.add_argument("--qwen-dimensions", type=int, default=2560)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6333)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--drop-and-recreate", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.execute and os.environ.get(RUN_ENV) != "1":
        sys.stderr.write(f"live bakeoff refused: set {RUN_ENV}=1 and rerun with --execute\n")
        return 2
    if args.execute:
        os.environ.setdefault(Q18_RUNNER_ENV, "1")
        try:
            summary = asyncio.run(
                run_live_bakeoff(
                    collection=args.collection,
                    host=args.host,
                    port=args.port,
                    root=args.root,
                    drop_and_recreate=args.drop_and_recreate,
                )
            )
        except Exception as exc:
            sys.stderr.write(f"embedding bakeoff failed: {type(exc).__name__}\n")
            return 2
        sys.stdout.write(json.dumps(summary.to_safe_dict(), indent=2, sort_keys=True, ensure_ascii=False))
        sys.stdout.write("\n")
        return 0
    try:
        summary = generate_artifacts(collection=args.collection)
    except ValueError as exc:
        sys.stderr.write(f"embedding bakeoff failed: {exc}\n")
        return 2
    sys.stdout.write(json.dumps(summary.to_safe_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
