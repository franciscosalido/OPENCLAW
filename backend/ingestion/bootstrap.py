"""Dual corpus bootstrap orchestration for Agent-0."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Literal, Protocol, cast

from backend.ingestion.commit_store import DUAL_CORPUS_COLLECTIONS
from backend.ingestion.manifest import CorpusManifest, load_manifest
from backend.ingestion.pipeline import IngestionOptions, run_ingestion
from backend.ingestion.report import IngestionMode, assert_report_is_sanitized
from backend.rag.collection_guard import assert_collection_namespace
from backend.rag.qdrant_store import VectorStoreChunk


CorpusName = Literal["internal", "financial"]
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_CORPUS_ROOT = REPO_ROOT / "data" / "corpus"
BOOTSTRAP_FORBIDDEN_KEYS = {
    "text",
    "raw_text",
    "normalized_text",
    "chunks",
    "chunk_text",
    "vectors",
    "embeddings",
    "payload",
    "prompt",
    "answer",
    "api_key",
    "authorization",
    "headers",
    "raw_exception",
    "exception_message",
    "traceback",
    "absolute_paths",
    "username",
}


class BootstrapCommitStore(Protocol):
    """Commit store interface used by bootstrap orchestration."""

    def commit(self, chunks: Sequence[VectorStoreChunk], *, collection: str | None) -> None:
        """Persist vector chunks into the mapped collection."""


class ExistingHashIndex(Protocol):
    """Existing document hash lookup used for idempotence."""

    def unchanged_doc_ids(
        self,
        documents: Sequence[Mapping[str, Any]],
        *,
        corpus: CorpusName,
        collection_name: str,
    ) -> set[str]:
        """Return document ids that are unchanged in the target collection."""
        ...


@dataclass(frozen=True)
class MappingExistingHashIndex:
    """In-memory existing hash index for tests and dry local orchestration."""

    hashes_by_doc_id: Mapping[str, tuple[str | None, str | None]]

    def unchanged_doc_ids(
        self,
        documents: Sequence[Mapping[str, Any]],
        *,
        corpus: CorpusName,
        collection_name: str,
    ) -> set[str]:
        """Return docs whose raw or normalized hash matches existing metadata."""

        assert_collection_namespace(collection_name, DUAL_CORPUS_COLLECTIONS)
        unchanged: set[str] = set()
        for document in documents:
            doc_id = str(document.get("doc_id", ""))
            existing = self.hashes_by_doc_id.get(doc_id)
            if existing is None:
                continue
            existing_file_hash, existing_normalized_hash = existing
            file_hash = _optional_string(document.get("file_sha256"))
            normalized_hash = _optional_string(document.get("normalized_text_sha256"))
            if existing_file_hash is not None and existing_file_hash == file_hash:
                unchanged.add(doc_id)
                continue
            if (
                existing_normalized_hash is not None
                and existing_normalized_hash == normalized_hash
            ):
                unchanged.add(doc_id)
        return unchanged


@dataclass(frozen=True)
class BootstrapOptions:
    """Runtime options for dual-corpus bootstrap."""

    corpus: CorpusName
    mode: IngestionMode = "verify_only"
    report_out: Path | None = None


@dataclass(frozen=True)
class BootstrapResult:
    """Sanitized bootstrap result."""

    report: dict[str, Any]
    chunks: tuple[VectorStoreChunk, ...]


def manifest_path_for_corpus(corpus: CorpusName) -> Path:
    """Return the closed manifest path for one corpus."""

    return DATA_CORPUS_ROOT / corpus / "manifest.yaml"


def collection_for_corpus(corpus: CorpusName) -> str:
    """Return the closed Qdrant collection name for one corpus."""

    return DUAL_CORPUS_COLLECTIONS[corpus]


def run_bootstrap(
    options: BootstrapOptions,
    *,
    commit_store: BootstrapCommitStore | None = None,
    existing_hash_index: ExistingHashIndex | None = None,
) -> BootstrapResult:
    """Run controlled bootstrap for one mapped corpus."""

    collection_name = assert_collection_namespace(
        collection_for_corpus(options.corpus),
        DUAL_CORPUS_COLLECTIONS,
    )
    manifest_path = manifest_path_for_corpus(options.corpus)
    manifest = load_manifest(manifest_path)
    _validate_manifest_for_corpus(manifest, corpus=options.corpus)

    ingestion_result = run_ingestion(
        IngestionOptions(
            manifest_path=manifest_path,
            mode="verify_only",
            collection=collection_name,
        )
    )
    per_document = cast(list[dict[str, Any]], ingestion_result.report["per_document"])
    unchanged_doc_ids = (
        existing_hash_index.unchanged_doc_ids(
            per_document,
            corpus=options.corpus,
            collection_name=collection_name,
        )
        if existing_hash_index is not None
        else set()
    )
    hashes_by_doc_id = _hashes_by_doc_id(per_document)
    chunks_to_commit = tuple(
        _with_bootstrap_metadata(
            chunk,
            corpus=options.corpus,
            collection_name=collection_name,
            hashes_by_doc_id=hashes_by_doc_id,
        )
        for chunk in ingestion_result.chunks
        if chunk.doc_id not in unchanged_doc_ids
    )

    if options.mode == "commit":
        if commit_store is None:
            raise ValueError("commit mode requires a commit store")
        commit_store.commit(chunks_to_commit, collection=collection_name)

    query_p95_by_corpus = {
        name: measure_query_dry_run_p95(cast(CorpusName, name), mapped_collection)
        for name, mapped_collection in DUAL_CORPUS_COLLECTIONS.items()
        if name in {"internal", "financial"}
    }
    query_p95 = query_p95_by_corpus[options.corpus]
    report = _build_bootstrap_report(
        ingestion_report=ingestion_result.report,
        corpus=options.corpus,
        collection_name=collection_name,
        mode=options.mode,
        unchanged_doc_ids=unchanged_doc_ids,
        upserted_chunks=len(chunks_to_commit) if options.mode == "commit" else 0,
        embedded_chunks=len(chunks_to_commit) if options.mode == "commit" else 0,
        query_dry_run_p95_ms=query_p95,
        internal_query_p95_ms=query_p95_by_corpus["internal"],
        financial_query_p95_ms=query_p95_by_corpus["financial"],
    )
    return BootstrapResult(report=report, chunks=chunks_to_commit)


def measure_query_dry_run_p95(corpus: CorpusName, collection_name: str) -> float:
    """Measure offline query planning latency without Qdrant or LLM calls."""

    assert_collection_namespace(collection_name, DUAL_CORPUS_COLLECTIONS)
    durations: list[float] = []
    for query_index in range(10):
        started_at = time.perf_counter()
        _fake_embed_query(corpus=corpus, query_index=query_index)
        _fake_vector_search(collection_name=collection_name, query_index=query_index)
        durations.append((time.perf_counter() - started_at) * 1000)
    return round(_percentile(durations, 95), 3)


def _validate_manifest_for_corpus(
    manifest: CorpusManifest,
    *,
    corpus: CorpusName,
) -> None:
    expected_policy = "internal" if corpus == "internal" else "financial"
    for document in manifest.documents:
        if document.ingestion_policy != expected_policy:
            raise ValueError("document ingestion_policy does not match corpus")
        if corpus == "financial" and document.financial_domain is None:
            raise ValueError("financial documents must declare financial_domain")
        if corpus == "internal" and document.financial_domain is not None:
            raise ValueError("internal documents cannot declare financial_domain")


def _with_bootstrap_metadata(
    chunk: VectorStoreChunk,
    *,
    corpus: CorpusName,
    collection_name: str,
    hashes_by_doc_id: Mapping[str, tuple[str | None, str | None]],
) -> VectorStoreChunk:
    metadata = dict(chunk.metadata)
    file_hash, normalized_hash = hashes_by_doc_id.get(chunk.doc_id, (None, None))
    metadata.update(
        {
            "corpus": corpus,
            "namespace": collection_name,
            "collection_name": collection_name,
            "file_sha256": file_hash,
            "normalized_text_sha256": normalized_hash,
        }
    )
    if corpus == "financial" and metadata.get("ingestion_policy") != "financial":
        raise ValueError("financial chunk metadata has wrong ingestion policy")
    if corpus == "internal" and metadata.get("ingestion_policy") != "internal":
        raise ValueError("internal chunk metadata has wrong ingestion policy")
    return VectorStoreChunk(
        doc_id=chunk.doc_id,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        security_level=chunk.security_level,
        metadata=metadata,
    )


def _hashes_by_doc_id(
    documents: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[str | None, str | None]]:
    hashes: dict[str, tuple[str | None, str | None]] = {}
    for document in documents:
        doc_id = _optional_string(document.get("doc_id"))
        if doc_id is None:
            continue
        hashes[doc_id] = (
            _optional_string(document.get("file_sha256")),
            _optional_string(document.get("normalized_text_sha256")),
        )
    return hashes


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _build_bootstrap_report(
    *,
    ingestion_report: Mapping[str, Any],
    corpus: CorpusName,
    collection_name: str,
    mode: IngestionMode,
    unchanged_doc_ids: set[str],
    upserted_chunks: int,
    embedded_chunks: int,
    query_dry_run_p95_ms: float,
    internal_query_p95_ms: float,
    financial_query_p95_ms: float,
) -> dict[str, Any]:
    source_documents = cast(list[dict[str, Any]], ingestion_report["per_document"])
    per_document = []
    for document in source_documents:
        status = document["status"]
        rejection_reason = document["rejection_reason"]
        if document["doc_id"] in unchanged_doc_ids:
            status = "skip_unchanged"
            rejection_reason = "hash_unchanged"
        per_document.append(
            {
                "doc_id": document["doc_id"],
                "source_id": document["source_id"],
                "source_type": document["source_type"],
                "domain": document["domain"],
                "ingestion_policy": document["ingestion_policy"],
                "status": status,
                "rejection_reason": rejection_reason,
                "file_sha256": document["file_sha256"],
                "normalized_text_sha256": document["normalized_text_sha256"],
                "chunk_count": document["chunk_count"],
                "latency_ms": document["latency_ms"],
            }
        )

    report = {
        "corpus": corpus,
        "namespace": collection_name,
        "collection_name": collection_name,
        "mode": mode,
        "total_documents": ingestion_report["total_documents"],
        "parsed": ingestion_report["parsed_documents"],
        "chunked": ingestion_report["chunked_documents"],
        "embedded": embedded_chunks,
        "upserted": upserted_chunks,
        "skipped_unchanged": len(unchanged_doc_ids),
        "rejected": ingestion_report["rejected_documents"],
        "duplicates": ingestion_report["duplicate_documents"],
        "coverage": ingestion_report["coverage"],
        "p50_ingestion_ms": ingestion_report["p50_ingestion_ms"],
        "p95_ingestion_ms": ingestion_report["p95_ingestion_ms"],
        "query_dry_run_p95_ms": query_dry_run_p95_ms,
        "internal_query_p95_ms": internal_query_p95_ms,
        "financial_query_p95_ms": financial_query_p95_ms,
        "per_document": per_document,
    }
    _assert_bootstrap_report_sanitized(report)
    return report


def _assert_bootstrap_report_sanitized(report: dict[str, Any]) -> None:
    assert_report_is_sanitized(report)
    forbidden = _find_forbidden_keys(report)
    if forbidden:
        keys = ", ".join(sorted(forbidden))
        raise ValueError(f"bootstrap report contains forbidden keys: {keys}")


def _find_forbidden_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        found = {key for key in value if key in BOOTSTRAP_FORBIDDEN_KEYS}
        for nested in value.values():
            found.update(_find_forbidden_keys(nested))
        return found
    if isinstance(value, list):
        nested_found: set[str] = set()
        for item in value:
            nested_found.update(_find_forbidden_keys(item))
        return nested_found
    return set()


def _fake_embed_query(*, corpus: CorpusName, query_index: int) -> tuple[float, ...]:
    seed = len(corpus) + query_index
    return tuple(float((seed + offset) % 7) for offset in range(8))


def _fake_vector_search(*, collection_name: str, query_index: int) -> tuple[str, ...]:
    return tuple(f"{collection_name}:{query_index}:{rank}" for rank in range(3))


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
