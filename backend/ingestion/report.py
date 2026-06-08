"""Sanitized ingestion report contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any, Literal
from uuid import uuid4

from backend.ingestion.fingerprint import file_sha256


IngestionMode = Literal["verify_only", "commit"]
DocumentStatus = Literal["parsed", "chunked", "rejected", "skipped", "duplicate"]

FORBIDDEN_REPORT_KEYS = {
    "text",
    "raw_text",
    "normalized_text",
    "chunk",
    "chunks",
    "chunk_text",
    "vector",
    "vectors",
    "embedding",
    "embeddings",
    "payload",
    "prompt",
    "answer",
    "api_key",
    "authorization",
    "headers",
    "secret",
    "raw_exception",
    "exception_message",
    "traceback",
    "local_absolute_path",
    "username",
}


@dataclass(frozen=True)
class DocumentReport:
    """Sanitized per-document ingestion result."""

    doc_id: str
    source_id: str
    source_type: str
    domain: str
    ingestion_policy: str
    status: DocumentStatus
    rejection_reason: str | None
    file_sha256: str | None
    normalized_text_sha256: str | None
    chunk_count: int
    latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "domain": self.domain,
            "ingestion_policy": self.ingestion_policy,
            "status": self.status,
            "rejection_reason": self.rejection_reason,
            "file_sha256": self.file_sha256,
            "normalized_text_sha256": self.normalized_text_sha256,
            "chunk_count": self.chunk_count,
            "latency_ms": round(self.latency_ms, 3),
        }


@dataclass(frozen=True)
class ReportStats:
    enabled_documents: int
    approved_documents: int
    chunked_documents: int
    coverage: float
    p50_ingestion_ms: float
    p95_ingestion_ms: float


def build_report(
    *,
    mode: IngestionMode,
    manifest_path_relative: str,
    manifest_path: Path,
    document_reports: list[DocumentReport],
) -> dict[str, Any]:
    """Build an allowlisted report with no document text or payloads."""

    stats = _build_report_stats(document_reports)

    report: dict[str, Any] = {
        "run_id": str(uuid4()),
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "mode": mode,
        "manifest_path_relative": manifest_path_relative,
        "manifest_sha256": file_sha256(manifest_path),
        "total_documents": len(document_reports),
        "enabled_documents": stats.enabled_documents,
        "approved_documents": stats.approved_documents,
        "rejected_documents": _count_status(document_reports, "rejected"),
        "skipped_documents": _count_status(document_reports, "skipped"),
        "duplicate_documents": _count_status(document_reports, "duplicate"),
        "parsed_documents": _count_parsed_documents(document_reports),
        "chunked_documents": stats.chunked_documents,
        "coverage": stats.coverage,
        "p50_ingestion_ms": stats.p50_ingestion_ms,
        "p95_ingestion_ms": stats.p95_ingestion_ms,
        "per_document": [result.to_dict() for result in document_reports],
    }
    assert_report_is_sanitized(report)
    return report


def _build_report_stats(reports: list[DocumentReport]) -> ReportStats:
    enabled_reports = _enabled_reports(reports)
    approved_count = len(_approved_reports(enabled_reports))
    latencies = _chunked_latencies(reports)
    chunked_count = _count_status(reports, "chunked")
    return ReportStats(
        enabled_documents=len(enabled_reports),
        approved_documents=approved_count,
        chunked_documents=chunked_count,
        coverage=_coverage(chunked_count, approved_count),
        p50_ingestion_ms=_median_latency(latencies),
        p95_ingestion_ms=_p95_latency(latencies),
    )


def _enabled_reports(reports: list[DocumentReport]) -> list[DocumentReport]:
    return [report for report in reports if report.rejection_reason != "disabled"]


def _approved_reports(reports: list[DocumentReport]) -> list[DocumentReport]:
    return [
        report
        for report in reports
        if report.rejection_reason not in {"curation_status_not_approved"}
    ]


def _chunked_latencies(reports: list[DocumentReport]) -> list[float]:
    return [report.latency_ms for report in reports if report.status == "chunked"]


def _coverage(chunked_documents: int, approved_documents: int) -> float:
    if approved_documents == 0:
        return 0.0
    return round(chunked_documents / approved_documents, 6)


def _median_latency(latencies: list[float]) -> float:
    if not latencies:
        return 0.0
    return round(float(median(latencies)), 3)


def _p95_latency(latencies: list[float]) -> float:
    if not latencies:
        return 0.0
    return round(_percentile(latencies, 95), 3)


def _count_status(
    reports: list[DocumentReport],
    status: DocumentStatus,
) -> int:
    return sum(1 for report in reports if report.status == status)


def _count_parsed_documents(reports: list[DocumentReport]) -> int:
    parsed_statuses = {"parsed", "chunked"}
    return sum(1 for report in reports if report.status in parsed_statuses)


def assert_report_is_sanitized(report: dict[str, Any]) -> None:
    """Reject reports containing forbidden key names anywhere in the structure."""

    forbidden = _find_forbidden_keys(report)
    if forbidden:
        keys = ", ".join(sorted(forbidden))
        raise ValueError(f"report contains forbidden keys: {keys}")


def write_report(path: Path, report: dict[str, Any]) -> None:
    """Write sanitized report JSON."""

    assert_report_is_sanitized(report)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _find_forbidden_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        found = {key for key in value if key in FORBIDDEN_REPORT_KEYS}
        for nested in value.values():
            found.update(_find_forbidden_keys(nested))
        return found
    if isinstance(value, list):
        nested_found: set[str] = set()
        for item in value:
            nested_found.update(_find_forbidden_keys(item))
        return nested_found
    return set()


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (percentile / 100) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight
