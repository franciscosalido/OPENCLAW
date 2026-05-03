#!/usr/bin/env python
"""Compare two Agent-0 golden harness summary files."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse comparison CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Compare two Agent-0 golden harness summary JSON files.",
    )
    parser.add_argument("--baseline", required=True, help="Baseline summary JSON.")
    parser.add_argument("--candidate", required=True, help="Candidate summary JSON.")
    parser.add_argument(
        "--latency-threshold-pct",
        type=float,
        default=20.0,
        help="Mean latency regression threshold by alias.",
    )
    return parser.parse_args(argv)


def compare_summaries(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    latency_threshold_pct: float,
) -> tuple[str, int]:
    """Return a human-readable comparison table and exit code."""
    if latency_threshold_pct < 0:
        raise ValueError("latency_threshold_pct cannot be negative")
    baseline_rate = _pass_rate(baseline)
    candidate_rate = _pass_rate(candidate)
    pass_rate_delta = candidate_rate - baseline_rate
    baseline_latency = _read_float_mapping(baseline, "mean_latency_ms_by_alias")
    candidate_latency = _read_float_mapping(candidate, "mean_latency_ms_by_alias")
    aliases = sorted(set(baseline_latency) | set(candidate_latency))
    latency_rows: list[tuple[str, float, float, float]] = []
    latency_regression = False
    for alias in aliases:
        base = baseline_latency.get(alias, 0.0)
        cand = candidate_latency.get(alias, 0.0)
        delta_pct = _percent_delta(base, cand)
        latency_rows.append((alias, base, cand, delta_pct))
        if base > 0 and delta_pct > latency_threshold_pct:
            latency_regression = True

    fallback_delta = _read_int(candidate, "fallback_count") - _read_int(
        baseline,
        "fallback_count",
    )
    token_delta = _read_float(
        candidate,
        "total_estimated_remote_tokens_avoided",
    ) - _read_float(baseline, "total_estimated_remote_tokens_avoided")

    lines = [
        "golden_run_comparison",
        f"pass_rate_delta={pass_rate_delta:.4f}",
        f"fallback_count_delta={fallback_delta}",
        f"total_estimated_remote_tokens_avoided_delta={token_delta:.1f}",
        "alias | baseline_mean_ms | candidate_mean_ms | delta_pct",
    ]
    for alias, base, cand, delta_pct in latency_rows:
        lines.append(f"{alias} | {base:.1f} | {cand:.1f} | {delta_pct:.1f}")

    exit_code = 1 if pass_rate_delta < 0 or latency_regression else 0
    return "\n".join(lines) + "\n", exit_code


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    baseline = _load_summary(args.baseline)
    candidate = _load_summary(args.candidate)
    output, exit_code = compare_summaries(
        baseline,
        candidate,
        latency_threshold_pct=args.latency_threshold_pct,
    )
    sys.stdout.write(output)
    return exit_code


def _load_summary(path: Path | str) -> Mapping[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("summary JSON must be an object")
    return raw


def _pass_rate(summary: Mapping[str, Any]) -> float:
    total = _read_int(summary, "total_questions")
    if total <= 0:
        return 0.0
    return _read_int(summary, "passed") / total


def _read_int(summary: Mapping[str, Any], key: str) -> int:
    value = summary.get(key)
    if not isinstance(value, int):
        raise ValueError(f"summary {key} must be an integer")
    return value


def _read_float(summary: Mapping[str, Any], key: str) -> float:
    value = summary.get(key)
    if not isinstance(value, int | float):
        raise ValueError(f"summary {key} must be numeric")
    return float(value)


def _read_float_mapping(summary: Mapping[str, Any], key: str) -> dict[str, float]:
    value = summary.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"summary {key} must be an object")
    output: dict[str, float] = {}
    for alias, latency in value.items():
        if not isinstance(alias, str):
            raise ValueError(f"summary {key} keys must be strings")
        if not isinstance(latency, int | float):
            raise ValueError(f"summary {key}.{alias} must be numeric")
        output[alias] = float(latency)
    return output


def _percent_delta(baseline: float, candidate: float) -> float:
    if baseline <= 0:
        return 0.0 if candidate <= 0 else 100.0
    return ((candidate - baseline) / baseline) * 100.0


if __name__ == "__main__":
    raise SystemExit(main())
