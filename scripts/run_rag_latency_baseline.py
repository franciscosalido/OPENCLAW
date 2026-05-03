#!/usr/bin/env python
"""RAG per-segment latency baseline — 3-run collector.

Produces three labelled trace JSONs:
  cold_start     — first pipeline call after service startup
  warm_model     — immediate repeat call (model already loaded)
  degraded_qdrant — retrieval forced to fail via fake store

Usage (opt-in only):
  RUN_RAG_LATENCY_BASELINE=1 uv run python scripts/run_rag_latency_baseline.py

Output files are written to --output-dir (default: reports/g2_latency_baseline/).
Files are gitignored. No prompt, answer, chunks, vectors or secrets are written.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any

from loguru import logger

from backend.rag.pipeline import LocalRagPipeline
from backend.rag.generator import LocalGenerator
from backend.rag.prompt_builder import PromptBuilder
from backend.rag.retriever import Retriever
from backend.rag.run_trace import RagRunContext, load_rag_tracing_config

GUARD_ENV = "RUN_RAG_LATENCY_BASELINE"
# Synthetic question — text never written to any output.
_SYNTHETIC_QUESTION = (
    "Qual é o impacto do aumento da taxa Selic sobre a rentabilidade "
    "de títulos prefixados em carteiras de renda fixa?"
)
_QUESTION_HASH_8 = hashlib.sha256(
    _SYNTHETIC_QUESTION.encode("utf-8")
).hexdigest()[:8]

DEFAULT_OUTPUT_DIR = Path("reports/g2_latency_baseline")

SEGMENT_KEYS = (
    "embedding_ms",
    "retrieval_ms",
    "context_pack_ms",
    "prompt_build_ms",
    "generation_ms",
    "total_ms",
)
FORBIDDEN_KEYS = frozenset(
    {
        "prompt", "question", "answer", "chunks", "chunk_text",
        "vectors", "embeddings", "payload", "qdrant_payload",
        "api_key", "authorization", "headers", "secret", "password",
        "raw_response", "raw_exception", "exception_message", "traceback",
        "raw_user_input",
    }
)


@dataclass(frozen=True)
class BaselineRunResult:
    run_context: RagRunContext
    question_hash_8: str
    segment_ms: dict[str, float | None]
    ollama_metrics_available: bool
    ollama_eval_count: int | None
    ollama_eval_duration_ms: float | None
    ollama_prompt_eval_count: int | None
    ollama_prompt_eval_duration_ms: float | None
    wall_ms: float
    ok: bool
    error_category: str | None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "run_context": self.run_context,
            "question_hash_8": self.question_hash_8,
            "segments": {k: v for k, v in self.segment_ms.items() if v is not None},
            "ollama_metrics_available": self.ollama_metrics_available,
            "ollama_eval_count": self.ollama_eval_count,
            "ollama_eval_duration_ms": self.ollama_eval_duration_ms,
            "ollama_prompt_eval_count": self.ollama_prompt_eval_count,
            "ollama_prompt_eval_duration_ms": self.ollama_prompt_eval_duration_ms,
            "wall_ms": self.wall_ms,
            "ok": self.ok,
            "error_category": self.error_category,
        }


def _build_pipeline() -> LocalRagPipeline:
    """Build a LocalRagPipeline from environment and config."""
    from backend.gateway.embed_client import GatewayEmbedClient
    from backend.rag.qdrant_store import QdrantVectorStore
    from backend.rag.retriever import Retriever

    embed_client = GatewayEmbedClient()
    store = QdrantVectorStore()
    retriever = Retriever(embedder=embed_client, store=store)
    generator = LocalGenerator(model="local_rag")
    tracing_config = load_rag_tracing_config().validated()

    return LocalRagPipeline(
        retriever=retriever,
        generator=generator,
        prompt_builder=PromptBuilder(),
        tracing_config=tracing_config,
    )


def _build_degraded_pipeline() -> LocalRagPipeline:
    """Build a pipeline with a fake store that raises on search."""
    from backend.gateway.embed_client import GatewayEmbedClient
    from backend.rag.retriever import Retriever

    class _FakeUnavailableStore:
        async def search(
            self,
            vector: Sequence[float],
            top_k: int = 5,
            score_threshold: float | None = 0.3,
            filters: Mapping[str, Any] | None = None,
        ) -> list[dict[str, object]]:
            del vector, top_k, score_threshold, filters
            raise RuntimeError("FakeQdrantUnavailableError: store unreachable")

    embed_client = GatewayEmbedClient()
    retriever = Retriever(embedder=embed_client, store=_FakeUnavailableStore())
    generator = LocalGenerator(model="local_rag")
    tracing_config = load_rag_tracing_config().validated()

    return LocalRagPipeline(
        retriever=retriever,
        generator=generator,
        prompt_builder=PromptBuilder(),
        tracing_config=tracing_config,
    )


def _capture_trace(pipeline: LocalRagPipeline) -> tuple[list[dict[str, object]], int]:
    """Install a loguru sink and collect all rag_run_trace dicts."""
    captured: list[dict[str, object]] = []

    def sink(message: Any) -> None:
        record = message.record
        if record["message"] == "rag_run_trace":
            trace = record["extra"].get("trace")
            if isinstance(trace, dict):
                captured.append(dict(trace))

    sink_id = logger.add(sink, level="DEBUG")
    return captured, sink_id


async def _run_once(
    pipeline: LocalRagPipeline,
    run_context: RagRunContext,
) -> BaselineRunResult:
    captured: list[dict[str, object]] = []
    sink_id: int | None = None

    def _sink(message: Any) -> None:
        record = message.record
        if record["message"] == "rag_run_trace":
            trace = record["extra"].get("trace")
            if isinstance(trace, dict):
                captured.append(dict(trace))

    sink_id = logger.add(_sink, level="DEBUG")
    wall_start = time.perf_counter()
    error_category: str | None = None
    ok = False
    try:
        await pipeline.ask(_SYNTHETIC_QUESTION, run_context=run_context)
        ok = True
    except Exception as exc:
        error_category = type(exc).__name__
        logger.debug("baseline run raised: {}", type(exc).__name__)
    finally:
        wall_ms = (time.perf_counter() - wall_start) * 1000.0
        if sink_id is not None:
            logger.remove(sink_id)

    trace = captured[0] if captured else {}
    segments: dict[str, float | None] = {
        key: _float_or_none(trace.get(key)) for key in SEGMENT_KEYS
    }

    return BaselineRunResult(
        run_context=run_context,
        question_hash_8=_QUESTION_HASH_8,
        segment_ms=segments,
        ollama_metrics_available=bool(trace.get("ollama_metrics_available", False)),
        ollama_eval_count=_int_or_none(trace.get("ollama_eval_count")),
        ollama_eval_duration_ms=_float_or_none(trace.get("ollama_eval_duration_ms")),
        ollama_prompt_eval_count=_int_or_none(trace.get("ollama_prompt_eval_count")),
        ollama_prompt_eval_duration_ms=_float_or_none(
            trace.get("ollama_prompt_eval_duration_ms")
        ),
        wall_ms=wall_ms,
        ok=ok,
        error_category=error_category,
    )


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _assert_no_forbidden_keys(data: dict[str, object]) -> None:
    lowered = {str(k).lower() for k in _flatten_keys(data)}
    leaked = lowered & FORBIDDEN_KEYS
    if leaked:
        raise ValueError(f"Forbidden keys in baseline output: {leaked}")


def _flatten_keys(obj: object) -> list[str]:
    keys: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(str(k))
            keys.extend(_flatten_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_flatten_keys(item))
    return keys


def _write_result(output_dir: Path, result: BaselineRunResult) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    fname = f"baseline_{result.run_context}_{result.question_hash_8}.json"
    path = output_dir / fname
    data = result.to_json_dict()
    _assert_no_forbidden_keys(data)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _print_summary(results: list[BaselineRunResult]) -> None:
    print("\n" + "=" * 60)
    print("RAG LATENCY BASELINE — SUMMARY")
    print("=" * 60)
    for r in results:
        segs = r.segment_ms
        total = segs.get("total_ms")
        gen = segs.get("generation_ms")
        emb = segs.get("embedding_ms")
        ret = segs.get("retrieval_ms")
        pct = f"{gen / total * 100:.1f}%" if (total and gen) else "n/a"
        print(f"\n[{r.run_context}]  ok={r.ok}  wall={r.wall_ms:.0f}ms")
        print(f"  embedding_ms   : {emb}")
        print(f"  retrieval_ms   : {ret}")
        print(f"  context_pack_ms: {segs.get('context_pack_ms')}")
        print(f"  prompt_build_ms: {segs.get('prompt_build_ms')}")
        print(f"  generation_ms  : {gen}")
        print(f"  total_ms       : {total}")
        print(f"  generation %   : {pct}")
        if r.ollama_metrics_available:
            print(f"  ollama_eval_count     : {r.ollama_eval_count}")
            print(f"  ollama_eval_ms        : {r.ollama_eval_duration_ms}")
            print(f"  ollama_prompt_eval_ms : {r.ollama_prompt_eval_duration_ms}")
        else:
            print("  ollama_metrics_available: False (LiteLLM normalizes response)")

    # Answer the 4 merge-criterion questions
    contexts = {r.run_context for r in results}
    all_ok_or_degraded = all(
        r.ok or r.run_context == "degraded_qdrant" for r in results
    )
    segments_present = all(
        r.segment_ms.get("generation_ms") is not None
        and r.segment_ms.get("retrieval_ms") is not None
        for r in results
        if r.ok
    )
    distinguishable = len(contexts) == len(results)

    print("\n" + "-" * 60)
    print("MERGE CRITERION ANSWERS:")
    print(f"  1. 3 runs successful?          {'YES' if all_ok_or_degraded else 'NO'}")
    print(f"  2. generation_ms visible?      {'YES' if segments_present else 'NO'}")
    print(f"  3. retrieval_ms visible?       {'YES' if segments_present else 'NO'}")
    print(f"  4. cold/warm/degraded distinct?{'YES' if distinguishable else 'NO'}")
    print(f"  5. no forbidden keys?          YES (validated before write)")
    print("-" * 60)


async def main_async(output_dir: Path) -> int:
    if os.environ.get(GUARD_ENV) != "1":
        print(
            f"Opt-in required: set {GUARD_ENV}=1 to run the baseline.",
            file=sys.stderr,
        )
        return 2

    logger.remove()  # suppress loguru noise to stdout during baseline
    results: list[BaselineRunResult] = []

    print("Building live pipeline (cold_start run)…")
    pipeline = _build_pipeline()
    r1 = await _run_once(pipeline, "cold_start")
    results.append(r1)
    path1 = _write_result(output_dir, r1)
    print(f"  cold_start  → {path1}  ({r1.wall_ms:.0f} ms)")

    print("Running warm_model…")
    r2 = await _run_once(pipeline, "warm_model")
    results.append(r2)
    path2 = _write_result(output_dir, r2)
    print(f"  warm_model  → {path2}  ({r2.wall_ms:.0f} ms)")

    print("Building degraded pipeline (fake Qdrant unavailable)…")
    deg_pipeline = _build_degraded_pipeline()
    r3 = await _run_once(deg_pipeline, "degraded_qdrant")
    results.append(r3)
    path3 = _write_result(output_dir, r3)
    print(f"  degraded    → {path3}  ({r3.wall_ms:.0f} ms)")

    _print_summary(results)
    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for baseline JSON files (default: reports/g2_latency_baseline/)",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args.output_dir))


if __name__ == "__main__":
    sys.exit(main())
