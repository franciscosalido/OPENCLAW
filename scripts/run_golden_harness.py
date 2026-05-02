#!/usr/bin/env python
"""Run the Agent-0 golden question harness.

The harness is opt-in and local-only. Dry-run mode is fully offline and never
calls LiteLLM, Ollama or Qdrant.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from uuid import uuid4

import yaml

from scripts import run_local_agent


DEFAULT_QUESTIONS_PATH = Path("tests/golden/questions.yaml")
DEFAULT_OUTPUT_DIR = Path("tests/golden/reports")
HARNESS_GUARD_ENV = "RUN_GOLDEN_HARNESS"


@dataclass(frozen=True)
class GoldenQuestion:
    """Synthetic golden benchmark question."""

    question_id: str
    domain: str
    mode: str
    question: str
    rationale: str


@dataclass(frozen=True)
class GoldenResult:
    """Safe per-question benchmark result without answer text."""

    question_id: str
    domain: str
    mode: str
    route: str
    alias: str | None
    used_rag: bool
    latency_ms: float
    decision_id: str
    estimated_remote_tokens_avoided: int | float
    answer_length_chars: int
    error_category: str | None
    fallback_applied: bool | None
    fallback_reason: str | None
    quality_score: None
    skipped: bool = False
    skipped_reason: str | None = None

    def to_json_dict(self) -> dict[str, object]:
        """Return allowlisted JSONL-safe result metadata."""
        data: dict[str, object] = {
            "question_id": self.question_id,
            "domain": self.domain,
            "mode": self.mode,
            "route": self.route,
            "used_rag": self.used_rag,
            "latency_ms": self.latency_ms,
            "decision_id": self.decision_id,
            "estimated_remote_tokens_avoided": (
                self.estimated_remote_tokens_avoided
            ),
            "answer_length_chars": self.answer_length_chars,
            "quality_score": self.quality_score,
            "skipped": self.skipped,
        }
        optional_values: dict[str, object | None] = {
            "alias": self.alias,
            "error_category": self.error_category,
            "fallback_applied": self.fallback_applied,
            "fallback_reason": self.fallback_reason,
            "skipped_reason": self.skipped_reason,
        }
        for key, value in optional_values.items():
            if value is not None:
                data[key] = value
        return data


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse harness CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run the opt-in Agent-0 golden question harness.",
    )
    parser.add_argument(
        "--questions",
        default=str(DEFAULT_QUESTIONS_PATH),
        help="Path to the golden question registry.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for JSONL and summary reports.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run offline with deterministic fake runner results.",
    )
    return parser.parse_args(argv)


def load_questions(path: Path | str = DEFAULT_QUESTIONS_PATH) -> list[GoldenQuestion]:
    """Load synthetic golden questions from YAML."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("golden questions root must be a mapping")
    items = raw.get("questions")
    if not isinstance(items, list):
        raise ValueError("golden questions file must contain a questions list")
    questions: list[GoldenQuestion] = []
    seen_ids: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("each golden question must be a mapping")
        question = GoldenQuestion(
            question_id=_read_str(item, "id"),
            domain=_read_str(item, "domain"),
            mode=_read_mode(item),
            question=_read_str(item, "question"),
            rationale=_read_str(item, "rationale"),
        )
        if question.question_id in seen_ids:
            raise ValueError(f"duplicate golden question id: {question.question_id}")
        seen_ids.add(question.question_id)
        questions.append(question)
    return questions


async def run_harness(
    *,
    questions_path: Path | str = DEFAULT_QUESTIONS_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    dry_run: bool,
) -> tuple[Path, Path]:
    """Run all golden questions and write JSONL plus summary reports."""
    questions = load_questions(questions_path)
    run_id = uuid4().hex[:12]
    timestamp = _utc_now()
    results: list[GoldenResult] = []
    for question in questions:
        if dry_run:
            result = _dry_run_result(question)
        else:
            result = await _live_result(question)
        results.append(result)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / f"golden_results_{run_id}.jsonl"
    summary_path = out_dir / f"golden_summary_{run_id}.json"
    _write_jsonl(jsonl_path, results)
    _write_summary(
        summary_path,
        run_id=run_id,
        timestamp_utc=timestamp,
        results=results,
    )
    return jsonl_path, summary_path


async def main_async(argv: Sequence[str] | None = None) -> int:
    """Async harness entrypoint."""
    args = parse_args(argv)
    if os.environ.get(HARNESS_GUARD_ENV) != "1":
        sys.stdout.write(
            "Golden harness is opt-in. Set RUN_GOLDEN_HARNESS=1 to run.\n",
        )
        return 2
    jsonl_path, summary_path = await run_harness(
        questions_path=args.questions,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )
    sys.stdout.write(f"OK golden_jsonl={jsonl_path} summary_json={summary_path}\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    return asyncio.run(main_async(argv))


def _dry_run_result(question: GoldenQuestion) -> GoldenResult:
    alias = _alias_for_mode(question.mode)
    answer = "Dry run: no model call executed."
    estimated = run_local_agent._estimate_prompt_token_count(question.question)
    return GoldenResult(
        question_id=question.question_id,
        domain=question.domain,
        mode=question.mode,
        route="local",
        alias=alias,
        used_rag=question.mode == "rag",
        latency_ms=0.0,
        decision_id=f"dryrun-{question.question_id}",
        estimated_remote_tokens_avoided=estimated,
        answer_length_chars=len(answer),
        error_category=None,
        fallback_applied=None,
        fallback_reason=None,
        quality_score=None,
    )


async def _live_result(question: GoldenQuestion) -> GoldenResult:
    result = await run_local_agent.run_agent(
        question=question.question,
        use_rag=question.mode == "rag",
        use_json=question.mode == "json",
    )
    return GoldenResult(
        question_id=question.question_id,
        domain=question.domain,
        mode=question.mode,
        route=result.route,
        alias=result.alias,
        used_rag=result.used_rag,
        latency_ms=result.latency_ms,
        decision_id=result.decision_id,
        estimated_remote_tokens_avoided=result.estimated_remote_tokens_avoided,
        answer_length_chars=len(result.answer),
        error_category=result.error_category,
        fallback_applied=result.fallback_applied,
        fallback_reason=(
            result.fallback_reason.value
            if result.fallback_reason is not None
            else None
        ),
        quality_score=None,
    )


def _write_jsonl(path: Path, results: Sequence[GoldenResult]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result.to_json_dict(), sort_keys=True) + "\n")


def _write_summary(
    path: Path,
    *,
    run_id: str,
    timestamp_utc: str,
    results: Sequence[GoldenResult],
) -> None:
    summary = build_summary(
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
    run_id: str,
    timestamp_utc: str,
    results: Sequence[GoldenResult],
) -> dict[str, object]:
    """Build a safe aggregate benchmark summary."""
    failed = sum(1 for result in results if result.error_category is not None)
    skipped = sum(1 for result in results if result.skipped)
    passed = len(results) - failed - skipped
    aliases = sorted(
        {result.alias for result in results if result.alias is not None}
    )
    return {
        "run_id": run_id,
        "timestamp_utc": timestamp_utc,
        "total_questions": len(results),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "fallback_count": sum(1 for result in results if result.fallback_applied),
        "mean_latency_ms_by_alias": _latency_by_alias(results, percentile=False),
        "p95_latency_ms_by_alias": _latency_by_alias(results, percentile=True),
        "total_estimated_remote_tokens_avoided": sum(
            result.estimated_remote_tokens_avoided for result in results
        ),
        "quality_score_present": False,
        "model_under_test_aliases": aliases,
    }


def _latency_by_alias(
    results: Sequence[GoldenResult],
    *,
    percentile: bool,
) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for result in results:
        if result.alias is None:
            continue
        values.setdefault(result.alias, []).append(result.latency_ms)
    output: dict[str, float] = {}
    for alias, latencies in values.items():
        output[alias] = _p95(latencies) if percentile else mean(latencies)
    return output


def _p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = max(0, min(len(sorted_values) - 1, int(len(sorted_values) * 0.95) - 1))
    return sorted_values[index]


def _alias_for_mode(mode: str) -> str:
    if mode == "rag":
        return run_local_agent.LOCAL_RAG_ALIAS
    if mode == "json":
        return run_local_agent.LOCAL_JSON_ALIAS
    return run_local_agent.LOCAL_CHAT_ALIAS


def _read_str(item: Mapping[object, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"golden question {key} must be a non-empty string")
    return value.strip()


def _read_mode(item: Mapping[object, object]) -> str:
    mode = _read_str(item, "mode")
    if mode not in {"chat", "rag", "json"}:
        raise ValueError(f"unsupported golden question mode: {mode}")
    return mode


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
