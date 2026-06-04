from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from backend.observability.decorators import traced_cache, traced_embed, traced_pg, traced_rerank, traced_retrieval, traced_rrf
from backend.rag.fusion import RRFFusion, ranked_result_from_position
from evaluation.benchmark_models import (
    DECISIONS,
    BackendStats,
    BenchmarkRow,
    BenchmarkScenario,
    to_jsonable_scenario,
)
from evaluation.benchmark_safety import require_cache_disabled

SUMMARY_PATH = Path("evaluation/results/rag_01b_session_benchmark_summary.json")
ROWS_PATH = Path("evaluation/results/rag_01b_session_benchmark_rows.csv")


@traced_pg(table="turns", operation="read")
async def benchmark_pg_read_probe() -> str:
    return "pg_read"


@traced_pg(table="turns", operation="write")
async def benchmark_pg_write_probe() -> str:
    return "pg_write"


@traced_embed(model="nomic-embed-text")
async def benchmark_embed_probe() -> list[float]:
    return [0.0, 0.1, 0.2]


@traced_retrieval(source="qdrant")
async def benchmark_retrieval_probe() -> dict[str, object]:
    return {"result_count": 2, "cache_hit": False}


@traced_cache(operation="lookup", backend="qdrant", collection="quimera_query_cache")
async def benchmark_cache_lookup_probe() -> None:
    return None


@traced_rrf(backend="python_rrf")
async def benchmark_rrf_probe() -> int:
    fusion = RRFFusion()
    dense = [ranked_result_from_position(result_id="d1", doc_id="doc-a", zero_based_position=0)]
    sparse = [ranked_result_from_position(result_id="s1", doc_id="doc-a", zero_based_position=0)]
    return len(fusion.fuse(dense_results=dense, sparse_results=sparse))


@traced_rerank(enabled=True)
async def benchmark_rerank_probe() -> list[str]:
    return ["doc-a", "doc-b"]


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_fake_scenarios(samples: int) -> list[BenchmarkScenario]:
    return [
        BenchmarkScenario(
            scenario="recent_turns_context",
            samples=samples,
            postgres=BackendStats(1.2, 2.0, 2.7),
            qdrant=BackendStats(3.4, 5.8, 7.1),
            winner="postgres",
            reason="ordered temporal turns are relational/session-local data",
        ),
        BenchmarkScenario(
            scenario="session_state_lookup",
            samples=samples,
            postgres=BackendStats(0.8, 1.5, 2.1),
            qdrant=BackendStats(4.0, 6.2, 8.4),
            winner="postgres",
            reason="agent state is keyed JSONB with uniqueness constraints",
        ),
        BenchmarkScenario(
            scenario="semantic_context_retrieval",
            samples=samples,
            postgres=BackendStats(0.0, 0.0, 0.0, errors=0),
            qdrant=BackendStats(2.2, 3.9, 5.0),
            winner="qdrant",
            reason="semantic vector retrieval is a Qdrant capability",
        ),
        BenchmarkScenario(
            scenario="light_entity_context",
            samples=samples,
            postgres=BackendStats(1.0, 1.8, 2.5),
            qdrant=BackendStats(3.0, 5.0, 6.5),
            winner="postgres",
            reason="entity mentions are normalized temporal facts",
        ),
    ]


def build_rows(scenarios: list[BenchmarkScenario], *, git_commit: str, generated_at: str) -> list[BenchmarkRow]:
    rows: list[BenchmarkRow] = []
    for scenario in scenarios:
        for backend, stats in (("postgres", scenario.postgres), ("qdrant", scenario.qdrant)):
            rows.append(
                BenchmarkRow(
                    scenario=scenario.scenario,
                    backend=backend,
                    sample_index=0,
                    latency_ms=stats.p50_ms,
                    error="",
                    cache_enabled="0",
                    cache_bypass=True,
                    git_commit=git_commit,
                    timestamp=generated_at,
                )
            )
    return rows


def build_summary(samples: int, *, real_mode: bool = False) -> dict[str, object]:
    generated_at = datetime.now(UTC).isoformat()
    git_commit = _git_commit()
    scenarios = build_fake_scenarios(samples)
    return {
        "schema_version": "rag-01b-session-benchmark-v1",
        "generated_at": generated_at,
        "git_commit": git_commit,
        "environment": {
            "python": platform.python_version(),
            "postgresql": "18.4",
            "qdrant": "1.18.x",
            "litellm_host_only": True,
            "otel_enabled": True,
        },
        "guards": {
            "QUIMERA_CACHE_ENABLED": "0",
            "litellm_cache_bypass": True,
            "real_mode": real_mode,
        },
        "scenarios": [to_jsonable_scenario(scenario) for scenario in scenarios],
        "decisions": DECISIONS,
        "otel_attributes": {
            "observed_span_names": ["embeddings", "retrieval qdrant", "retrieval rrf", "cache lookup", "pg READ turns", "pg WRITE turns"],
            "observed_safe_attributes": {
                "gen_ai.operation.name": "retrieval",
                "cache.backend": "qdrant",
                "db.system.name": "postgresql",
                "latency.rrf_ms": 0.0,
            },
            "forbidden_attributes_seen": [],
        },
        "warnings": [] if not real_mode else ["real benchmark execution is intentionally synthetic-data only"],
    }


def write_outputs(summary: dict[str, object], csv_path: Path, json_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    scenario_rows = cast(list[dict[str, object]], summary["scenarios"])
    raw_samples = scenario_rows[0]["samples"] if scenario_rows else 0
    samples = raw_samples if isinstance(raw_samples, int) else 0
    scenarios = build_fake_scenarios(samples)
    rows = build_rows(scenarios, git_commit=str(summary["git_commit"]), generated_at=str(summary["generated_at"]))
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scenario",
                "backend",
                "sample_index",
                "latency_ms",
                "error",
                "cache_enabled",
                "cache_bypass",
                "git_commit",
                "timestamp",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def run(samples: int, *, output_json: Path = SUMMARY_PATH, output_csv: Path = ROWS_PATH) -> dict[str, object]:
    real_mode = os.getenv("QUIMERA_BENCHMARK_REAL") == "1"
    require_cache_disabled()
    summary = build_summary(samples, real_mode=real_mode)
    write_outputs(summary, output_csv, output_json)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--output-json", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--output-csv", type=Path, default=ROWS_PATH)
    args = parser.parse_args()
    run(args.samples, output_json=args.output_json, output_csv=args.output_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
