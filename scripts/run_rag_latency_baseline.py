#!/usr/bin/env python
"""RAG per-segment latency baseline — cold/warm/degraded collector.

Produces a structured report plus three compatibility trace JSONs:
  cold_start     — first pipeline call after service startup
  warm_model     — immediate repeat call (model already loaded)
  degraded_qdrant — retrieval forced to fail via fake store

Usage (opt-in only):
  RUN_RAG_LATENCY_BASELINE=1 uv run python scripts/run_rag_latency_baseline.py
  uv run python scripts/run_rag_latency_baseline.py --verify-only report.json

Output files are written to --output-dir (default: reports/g2_latency_baseline/).
Files are gitignored. No prompt, answer, chunks, vectors or secrets are written.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import sys
import time
from datetime import UTC, datetime
from dataclasses import dataclass
from uuid import uuid4
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

import httpx
import yaml
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
DEFAULT_LITELLM_CONFIG_PATH = Path("config/litellm_config.yaml")
DEFAULT_OLLAMA_API_BASE = "http://127.0.0.1:11434"
REPORT_SCHEMA_VERSION = "g2_pr04_rag_latency_baseline_v1"
LOAD_DURATION_THRESHOLD_MS = 500.0
LOCAL_URL_PREFIXES = ("http://127.0.0.1:", "http://localhost:")
RUN_TYPES = frozenset({"cold_start", "warm_model", "degraded_qdrant"})
OLLAMA_METRICS_UNAVAILABLE_REASONS = frozenset(
    {
        "not_forwarded_by_gateway",
        "not_present_in_response",
        "not_applicable_degraded",
        "unknown",
    }
)
RESIDENT_CHECK_UNAVAILABLE_REASONS = frozenset(
    {
        "non_local_url",
        "timeout",
        "connection",
        "invalid_response",
        "unknown",
    }
)

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
        "raw_user_input", "model_weights_path", "weights_path",
    }
)

OllamaMetricsUnavailableReason = Literal[
    "not_forwarded_by_gateway",
    "not_present_in_response",
    "not_applicable_degraded",
    "unknown",
]
ResidentCheckUnavailableReason = Literal[
    "non_local_url",
    "timeout",
    "connection",
    "invalid_response",
    "unknown",
]


@dataclass(frozen=True)
class ModelResidencyCheck:
    model_was_resident_before_run: bool | None
    resident_check_unavailable_reason: ResidentCheckUnavailableReason | None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "model_was_resident_before_run": self.model_was_resident_before_run,
            "resident_check_unavailable_reason": (
                self.resident_check_unavailable_reason
            ),
        }


@dataclass(frozen=True)
class BaselineRunResult:
    run_type: RagRunContext
    alias: str
    model: str
    question_hash_8: str
    question_length_chars: int
    segment_ms: dict[str, float | None]
    ollama_metrics_available: bool
    ollama_metrics_unavailable_reason: OllamaMetricsUnavailableReason | None
    ollama_total_duration_ms: float | None
    ollama_load_duration_ms: float | None
    ollama_eval_count: int | None
    ollama_eval_duration_ms: float | None
    ollama_prompt_eval_count: int | None
    ollama_prompt_eval_duration_ms: float | None
    model_load_observed: bool | None
    run_type_verified: bool | None
    model_was_resident_before_run: bool | None
    resident_check_unavailable_reason: ResidentCheckUnavailableReason | None
    tokens_per_second: float | None
    wall_ms: float
    ok: bool
    error_category: str | None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "run_type": self.run_type,
            "alias": self.alias,
            "model": self.model,
            "question_hash_8": self.question_hash_8,
            "question_length_chars": self.question_length_chars,
            "segments": {k: v for k, v in self.segment_ms.items() if v is not None},
            "ollama_metrics_available": self.ollama_metrics_available,
            "ollama_metrics_unavailable_reason": (
                self.ollama_metrics_unavailable_reason
            ),
            "ollama_total_duration_ms": self.ollama_total_duration_ms,
            "ollama_load_duration_ms": self.ollama_load_duration_ms,
            "ollama_eval_count": self.ollama_eval_count,
            "ollama_eval_duration_ms": self.ollama_eval_duration_ms,
            "ollama_prompt_eval_count": self.ollama_prompt_eval_count,
            "ollama_prompt_eval_duration_ms": self.ollama_prompt_eval_duration_ms,
            "model_load_observed": self.model_load_observed,
            "run_type_verified": self.run_type_verified,
            "model_was_resident_before_run": self.model_was_resident_before_run,
            "resident_check_unavailable_reason": (
                self.resident_check_unavailable_reason
            ),
            "tokens_per_second": self.tokens_per_second,
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
    run_type: RagRunContext,
    *,
    alias: str,
    model: str,
    residency_check: ModelResidencyCheck,
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
        await pipeline.ask(_SYNTHETIC_QUESTION, run_context=run_type)
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
    ollama_metrics_available = bool(trace.get("ollama_metrics_available", False))
    ollama_load_duration_ms = _float_or_none(trace.get("ollama_load_duration_ms"))
    ollama_eval_count = _int_or_none(trace.get("ollama_eval_count"))
    ollama_eval_duration_ms = _float_or_none(trace.get("ollama_eval_duration_ms"))

    return BaselineRunResult(
        run_type=run_type,
        alias=alias,
        model=model,
        question_hash_8=_QUESTION_HASH_8,
        question_length_chars=len(_SYNTHETIC_QUESTION),
        segment_ms=segments,
        ollama_metrics_available=ollama_metrics_available,
        ollama_metrics_unavailable_reason=_ollama_metrics_unavailable_reason(
            run_type=run_type,
            trace_present=bool(trace),
            metrics_available=ollama_metrics_available,
        ),
        ollama_total_duration_ms=_float_or_none(trace.get("ollama_total_duration_ms")),
        ollama_load_duration_ms=ollama_load_duration_ms,
        ollama_eval_count=ollama_eval_count,
        ollama_eval_duration_ms=ollama_eval_duration_ms,
        ollama_prompt_eval_count=_int_or_none(trace.get("ollama_prompt_eval_count")),
        ollama_prompt_eval_duration_ms=_float_or_none(
            trace.get("ollama_prompt_eval_duration_ms")
        ),
        model_load_observed=_model_load_observed(ollama_load_duration_ms),
        run_type_verified=_run_type_verified(
            run_type=run_type,
            model_load_observed=_model_load_observed(ollama_load_duration_ms),
            error_category=error_category,
        ),
        model_was_resident_before_run=(
            residency_check.model_was_resident_before_run
        ),
        resident_check_unavailable_reason=(
            residency_check.resident_check_unavailable_reason
        ),
        tokens_per_second=_tokens_per_second(
            eval_count=ollama_eval_count,
            eval_duration_ms=ollama_eval_duration_ms,
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


def _validate_run_type(value: str) -> RagRunContext:
    if value not in RUN_TYPES:
        raise ValueError(f"run_type must be one of {sorted(RUN_TYPES)}")
    return cast(RagRunContext, value)


def _ollama_metrics_unavailable_reason(
    *,
    run_type: RagRunContext,
    trace_present: bool,
    metrics_available: bool,
) -> OllamaMetricsUnavailableReason | None:
    if metrics_available:
        return None
    if run_type == "degraded_qdrant":
        return "not_applicable_degraded"
    if trace_present:
        return "not_forwarded_by_gateway"
    return "not_present_in_response"


def _model_load_observed(load_duration_ms: float | None) -> bool | None:
    if load_duration_ms is None:
        return None
    return load_duration_ms > LOAD_DURATION_THRESHOLD_MS


def _run_type_verified(
    *,
    run_type: RagRunContext,
    model_load_observed: bool | None,
    error_category: str | None,
) -> bool | None:
    if run_type == "degraded_qdrant":
        return error_category is not None
    if model_load_observed is None:
        return None
    if run_type == "cold_start":
        return model_load_observed is True
    if run_type == "warm_model":
        return model_load_observed is False
    return None


def _tokens_per_second(
    *,
    eval_count: int | None,
    eval_duration_ms: float | None,
) -> float | None:
    if eval_count is None or eval_duration_ms is None or eval_duration_ms <= 0:
        return None
    return float(eval_count) / (eval_duration_ms / 1000.0)


def _is_local_url(url: str) -> bool:
    return any(url.startswith(prefix) for prefix in LOCAL_URL_PREFIXES)


def _ollama_model_name(litellm_model: str) -> str:
    if "/" in litellm_model:
        return litellm_model.rsplit("/", 1)[-1]
    return litellm_model


def _model_for_alias(
    alias: str = "local_rag",
    config_path: Path = DEFAULT_LITELLM_CONFIG_PATH,
) -> str:
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError:
        return alias
    if not isinstance(raw, Mapping):
        return alias
    model_list = raw.get("model_list")
    if not isinstance(model_list, Sequence) or isinstance(model_list, (str, bytes)):
        return alias
    for item in model_list:
        if not isinstance(item, Mapping):
            continue
        if item.get("model_name") != alias:
            continue
        params = item.get("litellm_params")
        if not isinstance(params, Mapping):
            return alias
        model = params.get("model")
        if isinstance(model, str) and model.strip():
            return _ollama_model_name(model.strip())
    return alias


def _parse_ollama_ps_residency(
    payload: object,
    *,
    model: str,
) -> bool | None:
    if not isinstance(payload, Mapping):
        return None
    models = payload.get("models")
    if not isinstance(models, Sequence) or isinstance(models, (str, bytes)):
        return None
    candidates = {model, _ollama_model_name(model)}
    for item in models:
        if not isinstance(item, Mapping):
            continue
        for key in ("name", "model"):
            value = item.get(key)
            if isinstance(value, str) and value in candidates:
                return True
    return False


async def check_ollama_model_residency(
    *,
    model: str,
    base_url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> ModelResidencyCheck:
    """Check Ollama ``/api/ps`` without logging raw responses or local paths."""
    effective_base_url = (base_url or os.environ.get(
        "OLLAMA_API_BASE",
        DEFAULT_OLLAMA_API_BASE,
    )).rstrip("/")
    if not _is_local_url(effective_base_url):
        return ModelResidencyCheck(
            model_was_resident_before_run=None,
            resident_check_unavailable_reason="non_local_url",
        )
    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        base_url=effective_base_url,
        timeout=httpx.Timeout(5.0),
    )
    try:
        response = await active_client.get("/api/ps")
        response.raise_for_status()
        resident = _parse_ollama_ps_residency(response.json(), model=model)
        if resident is None:
            return ModelResidencyCheck(
                model_was_resident_before_run=None,
                resident_check_unavailable_reason="invalid_response",
            )
        return ModelResidencyCheck(
            model_was_resident_before_run=resident,
            resident_check_unavailable_reason=None,
        )
    except httpx.TimeoutException:
        return ModelResidencyCheck(
            model_was_resident_before_run=None,
            resident_check_unavailable_reason="timeout",
        )
    except httpx.ConnectError:
        return ModelResidencyCheck(
            model_was_resident_before_run=None,
            resident_check_unavailable_reason="connection",
        )
    except httpx.HTTPError:
        return ModelResidencyCheck(
            model_was_resident_before_run=None,
            resident_check_unavailable_reason="unknown",
        )
    except ValueError:
        return ModelResidencyCheck(
            model_was_resident_before_run=None,
            resident_check_unavailable_reason="invalid_response",
        )
    finally:
        if owns_client:
            await active_client.aclose()


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
    fname = f"baseline_{result.run_type}_{result.question_hash_8}.json"
    path = output_dir / fname
    data = result.to_json_dict()
    _assert_no_forbidden_keys(data)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _hardware_snapshot() -> dict[str, object]:
    return {
        "platform_system": platform.system(),
        "platform_machine": platform.machine(),
        "python_version": platform.python_version(),
        "processor": platform.processor() or None,
        "ram_total_bytes": _ram_total_bytes(),
    }


def _ram_total_bytes() -> int | None:
    if not hasattr(os, "sysconf"):
        return None
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
    except (OSError, ValueError):
        return None
    if not isinstance(page_size, int) or not isinstance(page_count, int):
        return None
    if page_size <= 0 or page_count <= 0:
        return None
    return page_size * page_count


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _safe_float_values(values: Sequence[float | None]) -> list[float]:
    return [value for value in values if value is not None]


def _summary_by_alias_and_run_type(
    results: Sequence[BaselineRunResult],
) -> dict[str, dict[str, dict[str, object]]]:
    grouped: dict[tuple[str, str], list[BaselineRunResult]] = {}
    for result in results:
        grouped.setdefault((result.alias, result.run_type), []).append(result)

    summary: dict[str, dict[str, dict[str, object]]] = {}
    for (alias, run_type), items in sorted(grouped.items()):
        total_values = _safe_float_values(
            [item.segment_ms.get("total_ms") for item in items]
        )
        generation_values = _safe_float_values(
            [item.segment_ms.get("generation_ms") for item in items]
        )
        tps_values = _safe_float_values([item.tokens_per_second for item in items])
        summary.setdefault(alias, {})[run_type] = {
            "count": len(items),
            "ok_count": sum(1 for item in items if item.ok),
            "mean_total_ms": _mean(total_values),
            "p50_total_ms": _percentile(total_values, 0.50),
            "p95_total_ms": _percentile(total_values, 0.95),
            "mean_generation_ms": _mean(generation_values),
            "mean_tokens_per_second": _mean(tps_values),
            "model_load_observed_count": sum(
                1 for item in items if item.model_load_observed is True
            ),
            "run_type_verified_count": sum(
                1 for item in items if item.run_type_verified is True
            ),
        }
    return summary


def build_report(results: Sequence[BaselineRunResult]) -> dict[str, object]:
    records = [result.to_json_dict() for result in results]
    report: dict[str, object] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "run_id": uuid4().hex,
        "timestamp_utc": _utc_now_iso(),
        "hardware_snapshot": _hardware_snapshot(),
        "records": records,
        "summary_by_alias_and_run_type": _summary_by_alias_and_run_type(results),
        "record_count": len(records),
        "run_types": sorted({result.run_type for result in results}),
        "aliases": sorted({result.alias for result in results}),
    }
    validate_report(report)
    return report


def _write_report(output_dir: Path, results: Sequence[BaselineRunResult]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(results)
    run_id = str(report["run_id"])
    path = output_dir / f"rag_latency_baseline_report_{run_id}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def validate_report(data: Mapping[str, object]) -> None:
    """Validate a G2-PR04 baseline report without requiring live services."""
    _assert_no_forbidden_keys(dict(data))
    if "mean_total_ms" in data:
        raise ValueError("Report must not contain a mixed top-level mean_total_ms")
    if data.get("report_schema_version") != REPORT_SCHEMA_VERSION:
        raise ValueError("Unsupported baseline report schema version")
    records = data.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("Baseline report must contain records")
    for item in records:
        if not isinstance(item, Mapping):
            raise ValueError("Baseline report records must be mappings")
        _validate_record(item)
    summary = data.get("summary_by_alias_and_run_type")
    if not isinstance(summary, Mapping) or not summary:
        raise ValueError("Baseline report must group summary by alias and run_type")
    hardware = data.get("hardware_snapshot")
    if not isinstance(hardware, Mapping):
        raise ValueError("Baseline report must include hardware_snapshot")


def _validate_record(record: Mapping[str, object]) -> None:
    run_type = record.get("run_type")
    if run_type not in RUN_TYPES:
        raise ValueError("Baseline record must include a valid run_type")
    for key in ("alias", "model", "question_hash_8"):
        value = record.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Baseline record must include {key}")
    reason = record.get("ollama_metrics_unavailable_reason")
    if reason is not None and reason not in OLLAMA_METRICS_UNAVAILABLE_REASONS:
        raise ValueError("Invalid ollama_metrics_unavailable_reason")
    resident_reason = record.get("resident_check_unavailable_reason")
    if (
        resident_reason is not None
        and resident_reason not in RESIDENT_CHECK_UNAVAILABLE_REASONS
    ):
        raise ValueError("Invalid resident_check_unavailable_reason")
    segments = record.get("segments")
    if not isinstance(segments, Mapping):
        raise ValueError("Baseline record must include segments mapping")


def verify_report_file(path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("Baseline report must be a JSON object")
    validate_report(raw)


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
        print(f"\n[{r.run_type}]  ok={r.ok}  wall={r.wall_ms:.0f}ms")
        print(f"  alias/model    : {r.alias} / {r.model}")
        print(f"  resident_before: {r.model_was_resident_before_run}")
        print(f"  embedding_ms   : {emb}")
        print(f"  retrieval_ms   : {ret}")
        print(f"  context_pack_ms: {segs.get('context_pack_ms')}")
        print(f"  prompt_build_ms: {segs.get('prompt_build_ms')}")
        print(f"  generation_ms  : {gen}")
        print(f"  total_ms       : {total}")
        print(f"  generation %   : {pct}")
        if r.ollama_metrics_available:
            print(f"  ollama_load_ms       : {r.ollama_load_duration_ms}")
            print(f"  ollama_eval_count     : {r.ollama_eval_count}")
            print(f"  ollama_eval_ms        : {r.ollama_eval_duration_ms}")
            print(f"  ollama_prompt_eval_ms : {r.ollama_prompt_eval_duration_ms}")
            print(f"  tokens_per_second    : {r.tokens_per_second}")
        else:
            print(
                "  ollama_metrics_available: False "
                f"({r.ollama_metrics_unavailable_reason})"
            )

    # Answer the 4 merge-criterion questions
    contexts = {r.run_type for r in results}
    all_ok_or_degraded = all(
        r.ok or r.run_type == "degraded_qdrant" for r in results
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
    alias = "local_rag"
    model = _model_for_alias(alias)

    print("Building live pipeline (cold_start run)…")
    pipeline = _build_pipeline()
    cold_residency = await check_ollama_model_residency(model=model)
    r1 = await _run_once(
        pipeline,
        "cold_start",
        alias=alias,
        model=model,
        residency_check=cold_residency,
    )
    results.append(r1)
    path1 = _write_result(output_dir, r1)
    print(f"  cold_start  → {path1}  ({r1.wall_ms:.0f} ms)")

    print("Running warm_model…")
    warm_residency = await check_ollama_model_residency(model=model)
    r2 = await _run_once(
        pipeline,
        "warm_model",
        alias=alias,
        model=model,
        residency_check=warm_residency,
    )
    results.append(r2)
    path2 = _write_result(output_dir, r2)
    print(f"  warm_model  → {path2}  ({r2.wall_ms:.0f} ms)")

    print("Building degraded pipeline (fake Qdrant unavailable)…")
    deg_pipeline = _build_degraded_pipeline()
    degraded_residency = await check_ollama_model_residency(model=model)
    r3 = await _run_once(
        deg_pipeline,
        "degraded_qdrant",
        alias=alias,
        model=model,
        residency_check=degraded_residency,
    )
    results.append(r3)
    path3 = _write_result(output_dir, r3)
    print(f"  degraded    → {path3}  ({r3.wall_ms:.0f} ms)")

    report_path = _write_report(output_dir, results)
    print(f"  report      → {report_path}")
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
    parser.add_argument(
        "--verify-only",
        type=Path,
        help="Validate an existing baseline report without live service calls.",
    )
    args = parser.parse_args()
    if args.verify_only is not None:
        try:
            verify_report_file(args.verify_only)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"Invalid baseline report: {type(exc).__name__}", file=sys.stderr)
            return 1
        print("Baseline report OK")
        return 0
    return asyncio.run(main_async(args.output_dir))


if __name__ == "__main__":
    sys.exit(main())
