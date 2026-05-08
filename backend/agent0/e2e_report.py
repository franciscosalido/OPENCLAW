"""Sanitized Agent-0 E2E SLO report."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from statistics import median
from typing import Any
from uuid import uuid4

from backend.agent0.golden_questions import Citation, assert_golden_report_sanitized
from backend.agent0.openclaw import Answer


E2E_FORBIDDEN_KEYS = frozenset(
    {
        "question",
        "query",
        "text",
        "raw_text",
        "prompt",
        "chunks",
        "chunk",
        "chunk_text",
        "vectors",
        "vector",
        "embeddings",
        "embedding",
        "payload",
        "headers",
        "api_key",
        "authorization",
        "secret",
        "raw_exception",
        "traceback",
        "answer",
    }
)


def build_e2e_report(results: Sequence[tuple[str, Answer]]) -> dict[str, Any]:
    """Build a sanitized E2E report without question or answer text."""

    total = len(results)
    passed = sum(1 for _, answer in results if answer.citation_present)
    failed_question_ids = tuple(
        question_id for question_id, answer in results if not answer.citation_present
    )
    latencies = [answer.latency_ms for _, answer in results]
    answers = [answer for _, answer in results]
    report: dict[str, Any] = {
        "run_id": uuid4().hex,
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "total_questions": total,
        "passed": passed,
        "failed": total - passed,
        "citation_hit_rate": _ratio(passed, total),
        "p50_latency_ms": round(median(latencies), 3) if latencies else 0.0,
        "p95_latency_ms": _percentile(latencies, 95),
        "route_counts": dict(Counter(answer.route for answer in answers)),
        "corpus_counts": dict(Counter(answer.corpus for answer in answers)),
        "failed_question_ids": list(failed_question_ids),
        "safe_citations": [
            _safe_citation_dict(citation)
            for answer in answers
            for citation in answer.citations
        ],
    }
    assert_e2e_report_sanitized(report)
    return report


def assert_e2e_report_sanitized(report: Mapping[str, Any]) -> None:
    """Reject report keys that could leak content or secrets."""

    assert_golden_report_sanitized(report)
    hits = _forbidden_key_hits(report)
    if hits:
        raise ValueError(f"e2e report contains forbidden keys: {hits}")


def _safe_citation_dict(citation: Citation) -> dict[str, object]:
    return {
        "question_id": citation.question_id,
        "source_id": citation.source_id,
        "doc_id": citation.doc_id,
        "chunk_id": citation.chunk_id,
        "corpus": citation.corpus,
        "collection_name": citation.collection_name,
        "origin_path": citation.origin_path,
        "score": citation.score,
        "rank": citation.rank,
        "retrieval_mode": citation.retrieval_mode,
        "chunk_index": citation.chunk_index,
    }


def _forbidden_key_hits(value: object, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            next_path = f"{path}.{key_text}"
            if key_text in E2E_FORBIDDEN_KEYS:
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
