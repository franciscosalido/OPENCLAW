"""Controlled Agent-0 ingestion pipeline."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from backend.ingestion.fingerprint import file_sha256, normalized_text_sha256
from backend.ingestion.manifest import CorpusDocument, load_manifest, resolve_corpus_path
from backend.ingestion.parsers import (
    ParserRejectedError,
    ParserUnavailableError,
    parse_document,
)
from backend.ingestion.report import DocumentReport, DocumentStatus, IngestionMode, build_report
from backend.ingestion.sanitizer import reject_manifest_pii, sanitize_parsed_text
from backend.rag.chunking import DEFAULT_MAX_TOKENS, DEFAULT_OVERLAP_TOKENS, chunk_text
from backend.rag.qdrant_store import VectorStoreChunk


@dataclass(frozen=True)
class IngestionOptions:
    """Runtime options for controlled ingestion."""

    manifest_path: Path
    mode: IngestionMode = "verify_only"
    fail_on_pending: bool = True
    collection: str | None = None
    max_tokens: int = DEFAULT_MAX_TOKENS
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS


class IngestionCommitStore(Protocol):
    """Optional commit abstraction used by tests or future Qdrant wiring."""

    def commit(self, chunks: Sequence[VectorStoreChunk], *, collection: str | None) -> None:
        """Persist chunks behind an explicit commit mode."""


@dataclass(frozen=True)
class IngestionRunResult:
    """Pipeline result with sanitized report and Qdrant-ready chunks."""

    report: dict[str, Any]
    chunks: tuple[VectorStoreChunk, ...]


def run_ingestion(
    options: IngestionOptions,
    *,
    commit_store: IngestionCommitStore | None = None,
) -> IngestionRunResult:
    """Run manifest validation, parsing, sanitization, fingerprinting and chunking."""

    manifest = load_manifest(options.manifest_path)
    document_reports: list[DocumentReport] = []
    chunks_to_commit: list[VectorStoreChunk] = []
    seen_file_hashes: set[str] = set()

    for document in manifest.documents:
        document_path = resolve_corpus_path(options.manifest_path, document)
        document_result, document_chunks = _process_document(
            document=document,
            document_path=document_path,
            options=options,
            seen_file_hashes=seen_file_hashes,
        )
        document_reports.append(document_result)
        chunks_to_commit.extend(document_chunks)

    if options.mode == "commit":
        _validate_commit_allowed(document_reports, options.fail_on_pending)
        if commit_store is not None:
            commit_store.commit(tuple(chunks_to_commit), collection=options.collection)

    report = build_report(
        mode=options.mode,
        manifest_path_relative=_relative_manifest_path(options.manifest_path),
        manifest_path=options.manifest_path,
        document_reports=document_reports,
    )
    return IngestionRunResult(report=report, chunks=tuple(chunks_to_commit))


def _process_document(
    *,
    document: CorpusDocument,
    document_path: Path,
    options: IngestionOptions,
    seen_file_hashes: set[str],
) -> tuple[DocumentReport, tuple[VectorStoreChunk, ...]]:
    started_at = time.perf_counter()

    if not document.enabled:
        return _document_report(
            document=document,
            status="skipped",
            rejection_reason="disabled",
            started_at=started_at,
        ), ()

    manifest_guard = reject_manifest_pii(document)
    if not manifest_guard.accepted:
        return _document_report(
            document=document,
            status="rejected",
            rejection_reason=manifest_guard.status,
            started_at=started_at,
        ), ()

    if document.curation_status != "approved":
        return _document_report(
            document=document,
            status="skipped",
            rejection_reason="curation_status_not_approved",
            started_at=started_at,
        ), ()

    try:
        digest = file_sha256(document_path)
    except OSError:
        return _document_report(
            document=document,
            status="rejected",
            rejection_reason="file_unavailable",
            started_at=started_at,
        ), ()

    if document.expected_hash is not None and digest != document.expected_hash:
        return _document_report(
            document=document,
            status="rejected",
            rejection_reason="expected_hash_mismatch",
            file_digest=digest,
            started_at=started_at,
        ), ()

    if digest in seen_file_hashes:
        return _document_report(
            document=document,
            status="duplicate",
            rejection_reason="duplicate_file_sha256",
            file_digest=digest,
            started_at=started_at,
        ), ()
    seen_file_hashes.add(digest)

    try:
        parsed_text = parse_document(document_path, document.source_type)
    except ParserUnavailableError:
        return _document_report(
            document=document,
            status="rejected",
            rejection_reason="parser_unavailable",
            file_digest=digest,
            started_at=started_at,
        ), ()
    except ParserRejectedError:
        return _document_report(
            document=document,
            status="rejected",
            rejection_reason="parser_error",
            file_digest=digest,
            started_at=started_at,
        ), ()

    text_guard = sanitize_parsed_text(parsed_text)
    if not text_guard.accepted:
        reason = str(text_guard.status)
        if text_guard.pii_pattern_category is not None:
            reason = f"{reason}:{text_guard.pii_pattern_category}"
        return _document_report(
            document=document,
            status="rejected",
            rejection_reason=reason,
            file_digest=digest,
            started_at=started_at,
        ), ()

    normalized_digest = normalized_text_sha256(parsed_text)
    if (
        document.expected_normalized_text_hash is not None
        and normalized_digest != document.expected_normalized_text_hash
    ):
        return _document_report(
            document=document,
            status="rejected",
            rejection_reason="expected_normalized_text_hash_mismatch",
            file_digest=digest,
            normalized_digest=normalized_digest,
            started_at=started_at,
        ), ()

    chunks = _vector_chunks_for_document(
        document=document,
        text=parsed_text,
        max_tokens=options.max_tokens,
        overlap_tokens=options.overlap_tokens,
    )
    return _document_report(
        document=document,
        status="chunked",
        rejection_reason=None,
        file_digest=digest,
        normalized_digest=normalized_digest,
        chunk_count=len(chunks),
        started_at=started_at,
    ), tuple(chunks)


def _vector_chunks_for_document(
    *,
    document: CorpusDocument,
    text: str,
    max_tokens: int,
    overlap_tokens: int,
) -> list[VectorStoreChunk]:
    chunks = chunk_text(text, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    return [
        VectorStoreChunk(
            doc_id=document.doc_id,
            chunk_index=chunk.index,
            text=chunk.text,
            security_level="Level 1",
            metadata={
                "source_id": document.source_id,
                "domain": document.domain,
                "source_type": document.source_type,
                "ingestion_policy": document.ingestion_policy,
                "language": document.language,
                "license": document.license,
                "chunk_id": f"{document.doc_id}#{chunk.index}",
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
            },
        )
        for chunk in chunks
    ]


def _document_report(
    *,
    document: CorpusDocument,
    status: str,
    rejection_reason: str | None,
    started_at: float,
    file_digest: str | None = None,
    normalized_digest: str | None = None,
    chunk_count: int = 0,
) -> DocumentReport:
    return DocumentReport(
        doc_id=document.doc_id,
        source_id=document.source_id,
        source_type=document.source_type,
        domain=document.domain,
        ingestion_policy=document.ingestion_policy,
        status=cast(DocumentStatus, status),
        rejection_reason=rejection_reason,
        file_sha256=file_digest,
        normalized_text_sha256=normalized_digest,
        chunk_count=chunk_count,
        latency_ms=(time.perf_counter() - started_at) * 1000,
    )


def _validate_commit_allowed(
    document_reports: list[DocumentReport],
    fail_on_pending: bool,
) -> None:
    blocking_reasons: set[str] = {
        report.rejection_reason
        for report in document_reports
        if report.status in {"rejected", "duplicate"} and report.rejection_reason is not None
    }
    if fail_on_pending:
        blocking_reasons.update(
            report.rejection_reason
            for report in document_reports
            if report.rejection_reason == "curation_status_not_approved"
        )
    if blocking_reasons:
        reasons = ", ".join(sorted(blocking_reasons))
        raise ValueError(f"commit blocked by manifest verification: {reasons}")


def _relative_manifest_path(path: Path) -> str:
    resolved = path.resolve()
    cwd = Path.cwd().resolve()
    try:
        return resolved.relative_to(cwd).as_posix()
    except ValueError:
        return resolved.name
