"""Sanitized Agent-0 domain routing report contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from statistics import median
from typing import Any
from uuid import uuid4

from backend.agent0.domain_routing import (
    RouteDecision,
    reason_code_counts,
    route_counts,
)
from backend.agent0.golden_questions import assert_golden_report_sanitized


ROUTING_FORBIDDEN_KEYS = frozenset(
    {
        "query",
        "text",
        "raw_text",
        "answer",
        "prompt",
        "chunk",
        "chunks",
        "chunk_text",
        "vector",
        "vectors",
        "embedding",
        "embeddings",
        "payload",
        "headers",
        "api_key",
        "authorization",
        "secret",
        "raw_exception",
        "exception_message",
        "traceback",
        "absolute_path",
        "absolute_paths",
        "local_absolute_path",
        "username",
    }
)


def build_routing_report(
    *,
    decisions: Sequence[RouteDecision],
    passed: int,
    failed: int,
    golden_accuracy: float,
) -> dict[str, Any]:
    """Build a sanitized routing report with allowlisted metadata."""

    if passed < 0 or failed < 0:
        raise ValueError("passed and failed cannot be negative")
    total_decisions = len(decisions)
    latencies = [decision.latency_ms for decision in decisions]
    report: dict[str, Any] = {
        "run_id": uuid4().hex,
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "total_decisions": total_decisions,
        "passed": passed,
        "failed": failed,
        "coverage": _ratio(passed + failed, total_decisions),
        "p50_routing_ms": round(median(latencies), 3) if latencies else 0.0,
        "p95_routing_ms": _percentile(latencies, 95),
        "route_counts": route_counts(decisions),
        "reason_code_counts": reason_code_counts(decisions),
        "golden_accuracy": round(golden_accuracy, 3),
        "per_decision": [decision.to_dict() for decision in decisions],
    }
    assert_routing_report_sanitized(report)
    return report


def assert_routing_report_sanitized(report: Mapping[str, Any]) -> None:
    """Reject forbidden content-bearing keys anywhere in the report."""

    assert_golden_report_sanitized(report)
    hits = _forbidden_key_hits(report)
    if hits:
        raise ValueError(f"routing report contains forbidden keys: {hits}")


def _forbidden_key_hits(value: object, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            next_path = f"{path}.{key_text}"
            if key_text in ROUTING_FORBIDDEN_KEYS:
                hits.append(next_path)
            hits.extend(_forbidden_key_hits(nested, next_path))
    elif isinstance(value, list | tuple):
        for index, nested in enumerate(value):
            hits.extend(_forbidden_key_hits(nested, f"{path}[{index}]"))
    return hits


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 3)


def _percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((percentile / 100) * (len(ordered) - 1))))
    return round(ordered[index], 3)
