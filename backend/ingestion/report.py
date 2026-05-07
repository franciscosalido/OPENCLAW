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


def build_report(
    *,
    mode: IngestionMode,
    manifest_path_relative: str,
    manifest_path: Path,
    document_reports: list[DocumentReport],
) -> dict[str, Any]:
    """Build an allowlisted report with no document text or payloads."""

    enabled_reports = [
        report for report in document_reports if report.rejection_reason != "disabled"
    ]
    approved_documents = [
        report
        for report in enabled_reports
        if report.rejection_reason not in {"curation_status_not_approved"}
    ]
    latencies = [report.latency_ms for report in document_reports if report.status == "chunked"]
    chunked_documents = sum(1 for report in document_reports if report.status == "chunked")
    total_approved = len(approved_documents)
    coverage = round(chunked_documents / total_approved, 6) if total_approved else 0.0

    report: dict[str, Any] = {
        "run_id": str(uuid4()),
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "mode": mode,
        "manifest_path_relative": manifest_path_relative,
        "manifest_sha256": file_sha256(manifest_path),
        "total_documents": len(document_reports),
        "enabled_documents": len(enabled_reports),
        "approved_documents": total_approved,
        "rejected_documents": sum(
            1 for result in document_reports if result.status == "rejected"
        ),
        "skipped_documents": sum(1 for result in document_reports if result.status == "skipped"),
        "duplicate_documents": sum(
            1 for result in document_reports if result.status == "duplicate"
        ),
        "parsed_documents": sum(
            1 for result in document_reports if result.status in {"parsed", "chunked"}
        ),
        "chunked_documents": chunked_documents,
        "coverage": coverage,
        "p50_ingestion_ms": round(float(median(latencies)), 3) if latencies else 0.0,
        "p95_ingestion_ms": round(_percentile(latencies, 95), 3) if latencies else 0.0,
        "per_document": [result.to_dict() for result in document_reports],
    }
    assert_report_is_sanitized(report)
    return report


def assert_report_is_sanitized(report: dict[str, Any]) -> None:
    """Reject reports containing forbidden key names anywhere in the structure."""

    forbidden = _find_forbidden_keys(report)
    if forbidden:
        keys = ", ".join(sorted(forbidden))
        raise ValueError(f"report contains forbidden keys: {keys}")


def write_report(path: Path, report: dict[str, Any]) -> None:
    """Write sanitized report JSON."""

    assert_report_is_sanitized(report)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
