#!/usr/bin/env python
"""Compare local RAG candidate aliases without changing defaults.

The comparison is opt-in, local-only and report-oriented. It does not promote
aliases, mutate Qdrant, or store prompt/question/answer/chunk/vector content in
reports.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any
from uuid import uuid4

import yaml
from loguru import logger

from backend.gateway.routing_policy import estimate_prompt_tokens
from scripts import run_golden_harness, run_local_agent
from scripts.rag_ask_local import ask_local


GUARD_ENV = "RUN_RAG_ALIAS_COMPARISON"
DEFAULT_BASELINE_ALIAS = run_local_agent.LOCAL_RAG_ALIAS
DEFAULT_LITELLM_CONFIG_PATH = Path("config/litellm_config.yaml")
DEFAULT_QUESTIONS_PATH = run_golden_harness.DEFAULT_QUESTIONS_PATH
DEFAULT_OUTPUT_DIR = Path("reports/g2_alias_comparison")
REMOTE_PROVIDER_PREFIXES = (
    "openai/",
    "anthropic/",
    "gemini/",
    "azure/",
    "openrouter/",
    "xai/",
)
SAFE_RUN_TYPE = "warm_model"


@dataclass(frozen=True)
class AliasMetadata:
    """Safe LiteLLM alias metadata for comparison validation."""

    alias: str
    provider: str
    api_base: str
    experimental: bool | None


@dataclass(frozen=True)
class AliasComparisonResult:
    """Safe per-question/per-alias comparison result."""

    question_id: str
    alias: str
    alias_role: str
    experimental: bool
    run_type: str
    total_ms: float | None
    generation_ms: float | None
    prompt_eval_duration_ms: float | None
    eval_duration_ms: float | None
    eval_count: int | None
    tokens_per_second: float | None
    answer_length_chars: int
    citation_present: bool
    fallback_applied: bool
    estimated_remote_tokens_avoided: int
    error_category: str | None = None

    def to_json_dict(self) -> dict[str, object]:
        """Return an allowlisted report row without answer/question text."""
        data: dict[str, object] = {
            "question_id": self.question_id,
            "alias": self.alias,
            "alias_role": self.alias_role,
            "experimental": self.experimental,
            "run_type": self.run_type,
            "answer_length_chars": self.answer_length_chars,
            "citation_present": self.citation_present,
            "fallback_applied": self.fallback_applied,
            "estimated_remote_tokens_avoided": self.estimated_remote_tokens_avoided,
        }
        optional: dict[str, object | None] = {
            "total_ms": self.total_ms,
            "generation_ms": self.generation_ms,
            "prompt_eval_duration_ms": self.prompt_eval_duration_ms,
            "eval_duration_ms": self.eval_duration_ms,
            "eval_count": self.eval_count,
            "tokens_per_second": self.tokens_per_second,
            "error_category": self.error_category,
        }
        for key, value in optional.items():
            if value is not None:
                data[key] = value
        return data


AliasRunner = Callable[
    [run_golden_harness.GoldenQuestion, str, str],
    Awaitable[AliasComparisonResult],
]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Compare local_rag against local-only candidate aliases.",
    )
    parser.add_argument("--baseline-alias", default=DEFAULT_BASELINE_ALIAS)
    parser.add_argument(
        "--candidate-alias",
        action="append",
        required=True,
        help="Local semantic candidate alias. Repeat for multiple candidates.",
    )
    parser.add_argument(
        "--questions",
        default=str(DEFAULT_QUESTIONS_PATH),
        help="Path to the golden question registry.",
    )
    parser.add_argument(
        "--litellm-config",
        default=str(DEFAULT_LITELLM_CONFIG_PATH),
        help="Path to a local LiteLLM config containing candidate aliases.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for JSONL and summary reports.",
    )
    parser.add_argument(
        "--run-type",
        choices=("warm_model",),
        default=SAFE_RUN_TYPE,
        help="Comparison run type. G2-PR06 compares warm_model only.",
    )
    return parser.parse_args(argv)


async def run_comparison(
    *,
    baseline_alias: str,
    candidate_aliases: Sequence[str],
    questions_path: Path | str = DEFAULT_QUESTIONS_PATH,
    litellm_config_path: Path | str = DEFAULT_LITELLM_CONFIG_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_type: str = SAFE_RUN_TYPE,
    runner: AliasRunner | None = None,
) -> tuple[Path, Path]:
    """Run alias comparison and write JSONL plus summary reports."""
    if run_type != SAFE_RUN_TYPE:
        raise ValueError("G2-PR06 alias comparison supports warm_model only")
    alias_metadata = load_alias_metadata(litellm_config_path)
    validated_candidates = validate_aliases(
        baseline_alias=baseline_alias,
        candidate_aliases=candidate_aliases,
        alias_metadata=alias_metadata,
    )
    questions = run_golden_harness.load_questions(questions_path)
    fixture_hash = question_fixture_hash(questions_path)
    active_runner = _live_alias_result if runner is None else runner
    aliases = [baseline_alias, *validated_candidates]

    for alias in aliases:
        await active_runner(questions[0], alias, run_type)

    results: list[AliasComparisonResult] = []
    for question in questions:
        for alias in aliases:
            results.append(await active_runner(question, alias, run_type))

    run_id = uuid4().hex[:12]
    timestamp = _utc_now()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / f"rag_alias_comparison_{run_id}.jsonl"
    summary_path = out_dir / f"rag_alias_comparison_summary_{run_id}.json"
    write_jsonl(jsonl_path, results)
    write_summary(
        summary_path,
        baseline_alias=baseline_alias,
        candidate_aliases=validated_candidates,
        fixture_hash=fixture_hash,
        run_id=run_id,
        timestamp_utc=timestamp,
        results=results,
    )
    return jsonl_path, summary_path


async def main_async(argv: Sequence[str] | None = None) -> int:
    """Async CLI entrypoint."""
    args = parse_args(argv)
    if os.environ.get(GUARD_ENV) != "1":
        sys.stdout.write(
            "RAG alias comparison is opt-in. "
            "Set RUN_RAG_ALIAS_COMPARISON=1 to run.\n",
        )
        return 2
    jsonl_path, summary_path = await run_comparison(
        baseline_alias=args.baseline_alias,
        candidate_aliases=tuple(args.candidate_alias),
        questions_path=args.questions,
        litellm_config_path=args.litellm_config,
        output_dir=args.output_dir,
        run_type=args.run_type,
    )
    sys.stdout.write(
        f"OK alias_comparison_jsonl={jsonl_path} summary_json={summary_path}\n",
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    return asyncio.run(main_async(argv))


def load_alias_metadata(config_path: Path | str) -> dict[str, AliasMetadata]:
    """Load safe alias metadata from a LiteLLM YAML config."""
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("LiteLLM config must be a mapping")
    model_list = raw.get("model_list")
    if not isinstance(model_list, list):
        raise ValueError("LiteLLM config must contain model_list")
    aliases: dict[str, AliasMetadata] = {}
    for item in model_list:
        if not isinstance(item, Mapping):
            raise ValueError("LiteLLM model_list entries must be mappings")
        alias = _read_required_str(item, "model_name")
        params = item.get("litellm_params")
        info = item.get("model_info")
        if not isinstance(params, Mapping):
            raise ValueError(f"Alias {alias} missing litellm_params")
        if not isinstance(info, Mapping):
            raise ValueError(f"Alias {alias} missing model_info")
        aliases[alias] = AliasMetadata(
            alias=alias,
            provider=_read_required_str(info, "provider"),
            api_base=_read_required_str(params, "api_base"),
            experimental=_optional_bool(info.get("experimental")),
        )
    return aliases


def validate_aliases(
    *,
    baseline_alias: str,
    candidate_aliases: Sequence[str],
    alias_metadata: Mapping[str, AliasMetadata],
) -> tuple[str, ...]:
    """Validate baseline and candidate aliases for local-only comparison."""
    baseline = _validate_semantic_alias(baseline_alias)
    if baseline != DEFAULT_BASELINE_ALIAS:
        raise ValueError("baseline_alias must remain local_rag in G2-PR06")
    if baseline not in alias_metadata:
        raise ValueError("baseline alias is not defined in LiteLLM config")
    _validate_local_alias(alias_metadata[baseline], require_experimental=False)

    candidates: list[str] = []
    seen: set[str] = set()
    for candidate_alias in candidate_aliases:
        candidate = _validate_semantic_alias(candidate_alias)
        if candidate == baseline:
            raise ValueError("candidate alias cannot equal baseline alias")
        if candidate in seen:
            raise ValueError(f"duplicate candidate alias: {candidate}")
        if candidate not in alias_metadata:
            raise ValueError(f"candidate alias is not defined: {candidate}")
        _validate_local_alias(alias_metadata[candidate], require_experimental=True)
        candidates.append(candidate)
        seen.add(candidate)
    if not candidates:
        raise ValueError("at least one candidate alias is required")
    return tuple(candidates)


def question_fixture_hash(path: Path | str) -> str:
    """Return a stable hash for the golden fixture without storing text."""
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return digest[:16]


def write_jsonl(path: Path, results: Sequence[AliasComparisonResult]) -> None:
    """Write one sanitized JSON object per result line."""
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result.to_json_dict(), sort_keys=True) + "\n")


def write_summary(
    path: Path,
    *,
    baseline_alias: str,
    candidate_aliases: Sequence[str],
    fixture_hash: str,
    run_id: str,
    timestamp_utc: str,
    results: Sequence[AliasComparisonResult],
) -> None:
    """Write a safe aggregate comparison summary."""
    summary = build_summary(
        baseline_alias=baseline_alias,
        candidate_aliases=candidate_aliases,
        fixture_hash=fixture_hash,
        run_id=run_id,
        timestamp_utc=timestamp_utc,
        results=results,
    )
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_summary(
    *,
    baseline_alias: str,
    candidate_aliases: Sequence[str],
    fixture_hash: str,
    run_id: str,
    timestamp_utc: str,
    results: Sequence[AliasComparisonResult],
) -> dict[str, object]:
    """Build a safe alias comparison summary."""
    results_by_alias = _results_by_alias(results)
    delta_by_candidate = _delta_by_candidate(
        baseline_alias=baseline_alias,
        candidate_aliases=candidate_aliases,
        results=results,
    )
    citation_regression = {
        alias: _citation_regression(
            baseline_alias=baseline_alias,
            candidate_alias=alias,
            results=results,
        )
        for alias in candidate_aliases
    }
    hypothesis_supported = {
        alias: (
            _material_latency_improvement(delta_by_candidate.get(alias, {}))
            and citation_regression.get(alias) is False
        )
        for alias in candidate_aliases
    }
    return {
        "run_id": run_id,
        "timestamp_utc": timestamp_utc,
        "question_fixture_hash": fixture_hash,
        "baseline_alias": baseline_alias,
        "candidate_aliases": list(candidate_aliases),
        "warmup_discarded": True,
        "default_unchanged": baseline_alias == DEFAULT_BASELINE_ALIAS,
        "results_by_alias": results_by_alias,
        "delta_by_candidate": delta_by_candidate,
        "citation_regression": citation_regression,
        "quality_regression": None,
        "hypothesis_supported": hypothesis_supported,
    }


async def _live_alias_result(
    question: run_golden_harness.GoldenQuestion,
    alias: str,
    run_type: str,
) -> AliasComparisonResult:
    """Run one live local RAG question for an alias and return safe metrics."""
    traces: list[dict[str, object]] = []

    def sink(message: Any) -> None:
        trace = message.record["extra"].get("trace")
        if isinstance(trace, dict):
            traces.append(trace)

    sink_id = logger.add(sink, level="INFO")
    start = time.perf_counter()
    try:
        result = await ask_local(question=question.question, model=alias)
    except Exception as exc:
        return AliasComparisonResult(
            question_id=question.question_id,
            alias=alias,
            alias_role=_alias_role(alias),
            experimental=alias != DEFAULT_BASELINE_ALIAS,
            run_type=run_type,
            total_ms=(time.perf_counter() - start) * 1000.0,
            generation_ms=None,
            prompt_eval_duration_ms=None,
            eval_duration_ms=None,
            eval_count=None,
            tokens_per_second=None,
            answer_length_chars=0,
            citation_present=False,
            fallback_applied=False,
            estimated_remote_tokens_avoided=estimate_prompt_tokens(question.question),
            error_category=exc.__class__.__name__,
        )
    finally:
        logger.remove(sink_id)
    trace = traces[0] if traces else {}
    return AliasComparisonResult(
        question_id=question.question_id,
        alias=alias,
        alias_role=_alias_role(alias),
        experimental=alias != DEFAULT_BASELINE_ALIAS,
        run_type=run_type,
        total_ms=_float_or_none(trace.get("total_ms")) or result.latency_ms["total_ms"],
        generation_ms=(
            _float_or_none(trace.get("generation_ms"))
            or result.latency_ms["generation_ms"]
        ),
        prompt_eval_duration_ms=_float_or_none(
            trace.get("ollama_prompt_eval_duration_ms")
        ),
        eval_duration_ms=_float_or_none(trace.get("ollama_eval_duration_ms")),
        eval_count=_int_or_none(trace.get("ollama_eval_count")),
        tokens_per_second=_tokens_per_second(
            eval_count=_int_or_none(trace.get("ollama_eval_count")),
            eval_duration_ms=_float_or_none(trace.get("ollama_eval_duration_ms")),
        ),
        answer_length_chars=len(result.answer),
        citation_present=_citation_present(result.answer, result.citations),
        fallback_applied=False,
        estimated_remote_tokens_avoided=estimate_prompt_tokens(question.question),
        error_category=None,
    )


def _results_by_alias(
    results: Sequence[AliasComparisonResult],
) -> dict[str, dict[str, dict[str, object]]]:
    grouped: dict[str, dict[str, list[AliasComparisonResult]]] = {}
    for result in results:
        grouped.setdefault(result.alias, {}).setdefault(result.run_type, []).append(result)
    output: dict[str, dict[str, dict[str, object]]] = {}
    for alias, by_run_type in grouped.items():
        output[alias] = {}
        for run_type, items in by_run_type.items():
            output[alias][run_type] = {
                "count": len(items),
                "mean_total_ms": _mean_metric(items, "total_ms"),
                "mean_generation_ms": _mean_metric(items, "generation_ms"),
                "mean_eval_duration_ms": _mean_metric(items, "eval_duration_ms"),
                "mean_eval_count": _mean_metric(items, "eval_count"),
                "mean_tokens_per_second": _mean_metric(items, "tokens_per_second"),
                "mean_answer_length_chars": mean(
                    item.answer_length_chars for item in items
                ),
                "citation_present_count": sum(
                    1 for item in items if item.citation_present
                ),
                "fallback_count": sum(1 for item in items if item.fallback_applied),
            }
    return output


def _delta_by_candidate(
    *,
    baseline_alias: str,
    candidate_aliases: Sequence[str],
    results: Sequence[AliasComparisonResult],
) -> dict[str, dict[str, float | None]]:
    baseline_total = _mean_for_alias(results, baseline_alias, "total_ms")
    baseline_generation = _mean_for_alias(results, baseline_alias, "generation_ms")
    deltas: dict[str, dict[str, float | None]] = {}
    for alias in candidate_aliases:
        candidate_total = _mean_for_alias(results, alias, "total_ms")
        candidate_generation = _mean_for_alias(results, alias, "generation_ms")
        deltas[alias] = {
            "total_ms_delta_pct": _improvement_pct(baseline_total, candidate_total),
            "generation_ms_delta_pct": _improvement_pct(
                baseline_generation,
                candidate_generation,
            ),
        }
    return deltas


def _citation_regression(
    *,
    baseline_alias: str,
    candidate_alias: str,
    results: Sequence[AliasComparisonResult],
) -> bool:
    baseline_by_question = {
        result.question_id: result.citation_present
        for result in results
        if result.alias == baseline_alias
    }
    for result in results:
        if result.alias != candidate_alias:
            continue
        if baseline_by_question.get(result.question_id) and not result.citation_present:
            return True
    return False


def _material_latency_improvement(delta: Mapping[str, object]) -> bool:
    total = delta.get("total_ms_delta_pct")
    generation = delta.get("generation_ms_delta_pct")
    return (
        (isinstance(total, (int, float)) and total >= 30.0)
        or (isinstance(generation, (int, float)) and generation >= 30.0)
    )


def _mean_for_alias(
    results: Sequence[AliasComparisonResult],
    alias: str,
    field_name: str,
) -> float | None:
    return _mean_metric([result for result in results if result.alias == alias], field_name)


def _mean_metric(
    results: Sequence[AliasComparisonResult],
    field_name: str,
) -> float | None:
    values: list[float] = []
    for result in results:
        raw = getattr(result, field_name)
        if isinstance(raw, bool) or raw is None:
            continue
        if isinstance(raw, (int, float)):
            values.append(float(raw))
    if not values:
        return None
    return mean(values)


def _improvement_pct(
    baseline_value: float | None,
    candidate_value: float | None,
) -> float | None:
    if baseline_value is None or candidate_value is None or baseline_value <= 0:
        return None
    return ((baseline_value - candidate_value) / baseline_value) * 100.0


def _validate_local_alias(
    metadata: AliasMetadata,
    *,
    require_experimental: bool,
) -> None:
    provider = metadata.provider.strip().lower()
    if provider != "ollama":
        raise ValueError(f"Alias {metadata.alias} is not a local Ollama alias")
    if not _is_local_api_base(metadata.api_base):
        raise ValueError(f"Alias {metadata.alias} does not use a local api_base")
    if require_experimental and metadata.experimental is False:
        raise ValueError(f"Candidate alias {metadata.alias} is not experimental")


def _validate_semantic_alias(alias: str) -> str:
    value = alias.strip()
    if not value:
        raise ValueError("alias cannot be empty")
    lower = value.lower()
    if any(lower.startswith(prefix) for prefix in REMOTE_PROVIDER_PREFIXES):
        raise ValueError("remote provider aliases are not allowed")
    if "/" in value or ":" in value:
        raise ValueError("concrete model names are not allowed")
    if not value.replace("_", "").isalnum() or not value[0].isalpha():
        raise ValueError("alias must be a semantic local identifier")
    return value


def _is_local_api_base(api_base: str) -> bool:
    return (
        api_base.startswith("http://localhost:")
        or api_base.startswith("http://127.0.0.1:")
    )


def _alias_role(alias: str) -> str:
    return "baseline" if alias == DEFAULT_BASELINE_ALIAS else "candidate"


def _citation_present(answer: str, citations: Sequence[str]) -> bool:
    return any(citation in answer for citation in citations)


def _tokens_per_second(
    *,
    eval_count: int | None,
    eval_duration_ms: float | None,
) -> float | None:
    if eval_count is None or eval_duration_ms is None or eval_duration_ms <= 0:
        return None
    return float(eval_count) / (eval_duration_ms / 1000.0)


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None


def _read_required_str(data: Mapping[object, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError("experimental must be boolean when present")
    return value


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
