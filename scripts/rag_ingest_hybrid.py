"""Hybrid ingest CLI for QUIMERA / OPENCLAW RAG.

This script prepares dense + sparse named-vector points for
``quimera_knowledge_v2``. It is conservative by design:

- dry-run is the default
- the legacy collection is protected
- no collection is created or deleted
- summaries never include raw text, vectors, embeddings, prompts, answers, or
  payload blobs

The core functions are pure and testable offline. A real Qdrant adapter can be
attached later through ``HybridUpsertClientProtocol`` without changing the
preparation contract.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import sys
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Protocol, TypeVar

HYBRID_COLLECTION_NAME = "quimera_knowledge_v2"
LEGACY_COLLECTION_NAME = "quimera_knowledge"

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"

DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_EMBEDDING_PROVIDER = "local"
DEFAULT_EMBEDDING_DIMENSIONS = 1024
DEFAULT_EMBEDDING_VERSION = "qwen3-embedding-0.6b@pending-local"
SCHEMA_VERSION = "qdrant-hybrid-v2"

DEFAULT_BATCH_SIZE = 32
MAX_BATCH_SIZE = 256

PROTECTED_COLLECTIONS = frozenset({LEGACY_COLLECTION_NAME})

FORBIDDEN_SUMMARY_KEYS = frozenset(
    {
        "text",
        "chunk_text",
        "raw_text",
        "content",
        "page_content",
        "vector",
        "vectors",
        "dense_vector",
        "sparse_vector",
        "embedding",
        "embeddings",
        "prompt",
        "answer",
        "payload",
    }
)

T = TypeVar("T")


class HybridIngestError(RuntimeError):
    """Sanitized ingest failure."""


class ClockProtocol(Protocol):
    def perf_counter(self) -> float: ...


class DenseEmbedderProtocol(Protocol):
    async def embed(self, text: str) -> Sequence[float]: ...


class SparseEmbedderProtocol(Protocol):
    async def embed(self, text: str) -> "SparseVector": ...


class HybridUpsertClientProtocol(Protocol):
    async def upsert_points(
        self,
        *,
        collection_name: str,
        points: Sequence["HybridIngestPoint"],
    ) -> None: ...


class _PerfCounterClock:
    def perf_counter(self) -> float:
        return time.perf_counter()


@dataclass(frozen=True, slots=True)
class Document:
    doc_id: str
    text: str
    source: str = "synthetic"

    def __post_init__(self) -> None:
        object.__setattr__(self, "doc_id", _validate_text(self.doc_id, "doc_id"))
        object.__setattr__(self, "text", _validate_text(self.text, "text"))
        object.__setattr__(self, "source", _validate_text(self.source, "source"))


@dataclass(frozen=True, slots=True)
class Chunk:
    doc_id: str
    chunk_id: str
    chunk_index: int
    text: str
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "doc_id", _validate_text(self.doc_id, "doc_id"))
        object.__setattr__(self, "chunk_id", _validate_text(self.chunk_id, "chunk_id"))
        object.__setattr__(self, "chunk_index", _validate_non_negative_int(self.chunk_index, "chunk_index"))
        object.__setattr__(self, "text", _validate_text(self.text, "text"))
        object.__setattr__(self, "source", _validate_text(self.source, "source"))


@dataclass(frozen=True, slots=True)
class SparseVector:
    indices: tuple[int, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        indices = tuple(_validate_sparse_index(index) for index in self.indices)
        values = tuple(_validate_finite_number(value, "sparse value") for value in self.values)
        if len(indices) != len(values):
            raise ValueError("sparse indices and values must have the same length")
        object.__setattr__(self, "indices", indices)
        object.__setattr__(self, "values", values)


@dataclass(frozen=True, slots=True)
class HybridIngestPoint:
    point_id: str
    dense_vector: tuple[float, ...]
    sparse_indices: tuple[int, ...]
    sparse_values: tuple[float, ...]
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "point_id", _validate_text(self.point_id, "point_id"))
        object.__setattr__(
            self,
            "dense_vector",
            tuple(_validate_finite_number(value, "dense value") for value in self.dense_vector),
        )
        sparse = SparseVector(indices=self.sparse_indices, values=self.sparse_values)
        object.__setattr__(self, "sparse_indices", sparse.indices)
        object.__setattr__(self, "sparse_values", sparse.values)
        object.__setattr__(self, "payload", _freeze_payload(self.payload))

    def to_qdrant_vector_dict(self) -> dict[str, object]:
        """Return the conceptual named-vector shape expected by Qdrant."""

        return {
            DENSE_VECTOR_NAME: list(self.dense_vector),
            SPARSE_VECTOR_NAME: {
                "indices": list(self.sparse_indices),
                "values": list(self.sparse_values),
            },
        }


@dataclass(frozen=True, slots=True)
class HybridIngestSummary:
    collection_name: str
    documents_count: int
    chunks_count: int
    points_prepared: int
    points_sent: int
    batches_sent: int
    dense_ms: float
    sparse_ms: float
    upload_ms: float
    total_ms: float
    dry_run: bool
    embedding_model: str
    embedding_provider: str
    embedding_dimensions: int
    embedding_version: str
    dense_vector_name: str
    sparse_vector_name: str
    batch_size: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "collection_name", _validate_text(self.collection_name, "collection_name"))
        for field_name in (
            "documents_count",
            "chunks_count",
            "points_prepared",
            "points_sent",
            "batches_sent",
        ):
            object.__setattr__(self, field_name, _validate_non_negative_int(getattr(self, field_name), field_name))
        for field_name in ("dense_ms", "sparse_ms", "upload_ms", "total_ms"):
            object.__setattr__(self, field_name, _validate_non_negative_float(getattr(self, field_name), field_name))
        metadata = validate_embedding_metadata(
            embedding_model=self.embedding_model,
            embedding_provider=self.embedding_provider,
            embedding_dimensions=self.embedding_dimensions,
            embedding_version=self.embedding_version,
            dense_vector_name=self.dense_vector_name,
            sparse_vector_name=self.sparse_vector_name,
        )
        object.__setattr__(self, "embedding_model", metadata.embedding_model)
        object.__setattr__(self, "embedding_provider", metadata.embedding_provider)
        object.__setattr__(self, "embedding_dimensions", metadata.embedding_dimensions)
        object.__setattr__(self, "embedding_version", metadata.embedding_version)
        object.__setattr__(self, "dense_vector_name", metadata.dense_vector_name)
        object.__setattr__(self, "sparse_vector_name", metadata.sparse_vector_name)
        object.__setattr__(self, "batch_size", _validate_batch_size(self.batch_size))

    def to_safe_dict(self) -> dict[str, object]:
        """Return a stable summary that never exposes raw content or vectors."""

        summary: dict[str, object] = {
            "collection_name": self.collection_name,
            "documents_count": self.documents_count,
            "chunks_count": self.chunks_count,
            "points_prepared": self.points_prepared,
            "points_sent": self.points_sent,
            "batches_sent": self.batches_sent,
            "dense_ms": self.dense_ms,
            "sparse_ms": self.sparse_ms,
            "upload_ms": self.upload_ms,
            "total_ms": self.total_ms,
            "dry_run": self.dry_run,
            "embedding_model": self.embedding_model,
            "embedding_provider": self.embedding_provider,
            "embedding_dimensions": self.embedding_dimensions,
            "embedding_version": self.embedding_version,
            "dense_vector_name": self.dense_vector_name,
            "sparse_vector_name": self.sparse_vector_name,
            "batch_size": self.batch_size,
        }
        forbidden = FORBIDDEN_SUMMARY_KEYS.intersection(summary)
        if forbidden:
            raise RuntimeError(f"unsafe summary keys: {sorted(forbidden)}")
        return summary


@dataclass(frozen=True, slots=True)
class EmbeddingMetadata:
    embedding_model: str
    embedding_provider: str
    embedding_dimensions: int
    embedding_version: str
    dense_vector_name: str
    sparse_vector_name: str


def _validate_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if "\x00" in value:
        raise ValueError(f"{field_name} cannot contain null bytes")
    clean = value.strip()
    if not clean:
        raise ValueError(f"{field_name} cannot be empty")
    return clean


def _validate_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _validate_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be >= 1")
    return value


def _validate_finite_number(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    clean = float(value)
    if not math.isfinite(clean):
        raise ValueError(f"{field_name} must be finite")
    return clean


def _validate_non_negative_float(value: float, field_name: str) -> float:
    clean = _validate_finite_number(value, field_name)
    if clean < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return clean


def _validate_sparse_index(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("sparse index must be an integer")
    if value < 0:
        raise ValueError("sparse index must be non-negative")
    return value


def _validate_optional_positive_int(value: int | None, field_name: str) -> int | None:
    if value is None:
        return None
    return _validate_positive_int(value, field_name)


def _validate_batch_size(batch_size: int) -> int:
    clean = _validate_positive_int(batch_size, "batch_size")
    if clean > MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be <= {MAX_BATCH_SIZE}")
    return clean


def _freeze_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    clean_payload: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("payload keys must be strings")
        clean_payload[key] = value
    return MappingProxyType(clean_payload)


def make_chunk_id(doc_id: str, chunk_index: int, text: str) -> str:
    clean_doc_id = _validate_text(doc_id, "doc_id")
    clean_index = _validate_non_negative_int(chunk_index, "chunk_index")
    clean_text = _validate_text(text, "text")
    raw = f"{clean_doc_id}\n{clean_index}\n{clean_text}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    return str(uuid.UUID(hex=digest[:32]))


def chunk_document(
    document: Document,
    *,
    max_chars: int = 1200,
    overlap_chars: int = 0,
) -> list[Chunk]:
    clean_max_chars = _validate_positive_int(max_chars, "max_chars")
    clean_overlap = _validate_non_negative_int(overlap_chars, "overlap_chars")
    if clean_overlap >= clean_max_chars:
        raise ValueError("overlap_chars must be < max_chars")

    step = clean_max_chars - clean_overlap
    chunks: list[Chunk] = []
    start = 0
    index = 0
    text = document.text
    while start < len(text):
        raw_chunk = text[start : start + clean_max_chars].strip()
        if raw_chunk:
            chunks.append(
                Chunk(
                    doc_id=document.doc_id,
                    chunk_id=make_chunk_id(document.doc_id, index, raw_chunk),
                    chunk_index=index,
                    text=raw_chunk,
                    source=document.source,
                )
            )
            index += 1
        start += step
    return chunks


def generate_synthetic_corpus() -> list[Document]:
    """Return small safe documents for dry-run demos and offline tests."""

    return [
        Document(
            doc_id="synthetic-selic",
            source="synthetic",
            text="Selic is a benchmark interest-rate concept used in Brazilian financial examples.",
        ),
        Document(
            doc_id="synthetic-fii",
            source="synthetic",
            text="Real estate funds can be represented as safe synthetic examples for retrieval tests.",
        ),
        Document(
            doc_id="synthetic-risk",
            source="synthetic",
            text="Portfolio risk examples in this corpus are synthetic and contain no private data.",
        ),
    ]


def load_corpus_from_path(path: Path, *, max_documents: int | None = None) -> list[Document]:
    clean_max_documents = _validate_optional_positive_int(max_documents, "max_documents")
    if not path.exists():
        raise FileNotFoundError(f"corpus path does not exist: {path}")

    files: list[Path]
    if path.is_file():
        if path.suffix.casefold() != ".txt":
            raise ValueError("corpus file must be .txt")
        files = [path]
        base = path.parent
    else:
        files = sorted(candidate for candidate in path.rglob("*.txt") if candidate.is_file())
        base = path

    if clean_max_documents is not None:
        files = files[:clean_max_documents]

    documents: list[Document] = []
    for file_path in files:
        text = file_path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        documents.append(
            Document(
                doc_id=_doc_id_from_path(base, file_path),
                text=text,
                source=str(file_path.relative_to(base)),
            )
        )
    return documents


def _doc_id_from_path(base: Path, file_path: Path) -> str:
    relative = file_path.relative_to(base).as_posix()
    digest = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16]
    stem = file_path.stem.strip() or "document"
    return f"{stem}-{digest}"


def validate_embedding_metadata(
    *,
    embedding_model: str,
    embedding_provider: str,
    embedding_dimensions: int,
    embedding_version: str,
    dense_vector_name: str,
    sparse_vector_name: str,
) -> EmbeddingMetadata:
    clean_dense = _validate_text(dense_vector_name, "dense_vector_name")
    clean_sparse = _validate_text(sparse_vector_name, "sparse_vector_name")
    if clean_dense == clean_sparse:
        raise ValueError("dense_vector_name and sparse_vector_name must differ")
    return EmbeddingMetadata(
        embedding_model=_validate_text(embedding_model, "embedding_model"),
        embedding_provider=_validate_text(embedding_provider, "embedding_provider"),
        embedding_dimensions=_validate_positive_int(embedding_dimensions, "embedding_dimensions"),
        embedding_version=_validate_text(embedding_version, "embedding_version"),
        dense_vector_name=clean_dense,
        sparse_vector_name=clean_sparse,
    )


def validate_dense_vector(vector: Sequence[float], *, embedding_dimensions: int) -> tuple[float, ...]:
    expected = _validate_positive_int(embedding_dimensions, "embedding_dimensions")
    clean = tuple(_validate_finite_number(value, "dense value") for value in vector)
    if len(clean) != expected:
        raise ValueError(f"dense vector has {len(clean)} dimensions; expected {expected}")
    return clean


def validate_sparse_vector(vector: SparseVector, *, allow_empty_sparse: bool = False) -> SparseVector:
    clean = SparseVector(indices=vector.indices, values=vector.values)
    if not allow_empty_sparse and not clean.indices:
        raise ValueError("sparse vector cannot be empty")
    return clean


def build_payload(
    *,
    chunk: Chunk,
    embedding_model: str,
    embedding_provider: str,
    embedding_dimensions: int,
    embedding_version: str,
    dense_vector_name: str,
    sparse_vector_name: str,
) -> Mapping[str, object]:
    return MappingProxyType(
        {
            "doc_id": chunk.doc_id,
            "chunk_id": chunk.chunk_id,
            "chunk_index": chunk.chunk_index,
            "source": chunk.source,
            "embedding_model": embedding_model,
            "embedding_provider": embedding_provider,
            "embedding_dimensions": embedding_dimensions,
            "embedding_version": embedding_version,
            "dense_vector_name": dense_vector_name,
            "sparse_vector_name": sparse_vector_name,
            "schema_version": SCHEMA_VERSION,
        }
    )


def prepare_hybrid_points(
    *,
    chunks: Sequence[Chunk],
    dense_vectors: Sequence[Sequence[float]],
    sparse_vectors: Sequence[SparseVector],
    embedding_model: str,
    embedding_provider: str,
    embedding_dimensions: int,
    embedding_version: str,
    dense_vector_name: str = DENSE_VECTOR_NAME,
    sparse_vector_name: str = SPARSE_VECTOR_NAME,
    allow_empty_sparse: bool = False,
) -> list[HybridIngestPoint]:
    if len(chunks) != len(dense_vectors) or len(chunks) != len(sparse_vectors):
        raise ValueError("chunks, dense_vectors, and sparse_vectors must have the same length")

    metadata = validate_embedding_metadata(
        embedding_model=embedding_model,
        embedding_provider=embedding_provider,
        embedding_dimensions=embedding_dimensions,
        embedding_version=embedding_version,
        dense_vector_name=dense_vector_name,
        sparse_vector_name=sparse_vector_name,
    )
    dimensions = metadata.embedding_dimensions

    points: list[HybridIngestPoint] = []
    for chunk, dense_vector, sparse_vector in zip(chunks, dense_vectors, sparse_vectors, strict=True):
        clean_dense = validate_dense_vector(dense_vector, embedding_dimensions=dimensions)
        clean_sparse = validate_sparse_vector(sparse_vector, allow_empty_sparse=allow_empty_sparse)
        payload = build_payload(
            chunk=chunk,
            embedding_model=metadata.embedding_model,
            embedding_provider=metadata.embedding_provider,
            embedding_dimensions=dimensions,
            embedding_version=metadata.embedding_version,
            dense_vector_name=metadata.dense_vector_name,
            sparse_vector_name=metadata.sparse_vector_name,
        )
        points.append(
            HybridIngestPoint(
                point_id=chunk.chunk_id,
                dense_vector=clean_dense,
                sparse_indices=clean_sparse.indices,
                sparse_values=clean_sparse.values,
                payload=payload,
            )
        )
    return points


async def embed_chunks(
    *,
    chunks: Sequence[Chunk],
    dense_embedder: DenseEmbedderProtocol,
    sparse_embedder: SparseEmbedderProtocol,
    clock: ClockProtocol,
) -> tuple[list[list[float]], list[SparseVector], float, float]:
    dense_start = clock.perf_counter()
    dense_vectors: list[list[float]] = []
    try:
        for chunk in chunks:
            dense_vectors.append(list(await dense_embedder.embed(chunk.text)))
    except Exception as exc:
        raise HybridIngestError("dense embedding failed during hybrid ingest") from exc
    dense_ms = _elapsed_ms(dense_start, clock.perf_counter())

    sparse_start = clock.perf_counter()
    sparse_vectors: list[SparseVector] = []
    try:
        for chunk in chunks:
            sparse_vectors.append(await sparse_embedder.embed(chunk.text))
    except Exception as exc:
        raise HybridIngestError("sparse embedding failed during hybrid ingest") from exc
    sparse_ms = _elapsed_ms(sparse_start, clock.perf_counter())

    return dense_vectors, sparse_vectors, dense_ms, sparse_ms


def batched(items: Sequence[T], batch_size: int) -> Iterator[list[T]]:
    clean_batch_size = _validate_batch_size(batch_size)
    for start in range(0, len(items), clean_batch_size):
        yield list(items[start : start + clean_batch_size])


def assert_collection_is_safe_for_ingest(collection_name: str) -> str:
    clean = _validate_text(collection_name, "collection_name")
    if clean in PROTECTED_COLLECTIONS:
        raise HybridIngestError(f"collection {clean!r} is protected and cannot be used for hybrid ingest")
    return clean


async def upload_hybrid_points(
    *,
    client: HybridUpsertClientProtocol,
    collection_name: str,
    points: Sequence[HybridIngestPoint],
    batch_size: int,
    dry_run: bool,
    clock: ClockProtocol,
) -> tuple[int, int, float]:
    clean_collection = assert_collection_is_safe_for_ingest(collection_name)
    clean_batch_size = _validate_batch_size(batch_size)
    start = clock.perf_counter()
    if dry_run:
        return 0, 0, _elapsed_ms(start, clock.perf_counter())

    points_sent = 0
    batches_sent = 0
    try:
        for batch in batched(points, clean_batch_size):
            if not batch:
                continue
            await client.upsert_points(collection_name=clean_collection, points=batch)
            points_sent += len(batch)
            batches_sent += 1
    except Exception as exc:
        raise HybridIngestError("hybrid point upload failed") from exc
    return points_sent, batches_sent, _elapsed_ms(start, clock.perf_counter())


async def run_ingest(
    *,
    documents: Sequence[Document],
    dense_embedder: DenseEmbedderProtocol,
    sparse_embedder: SparseEmbedderProtocol,
    upsert_client: HybridUpsertClientProtocol,
    collection_name: str = HYBRID_COLLECTION_NAME,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = True,
    max_chunks: int | None = None,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embedding_provider: str = DEFAULT_EMBEDDING_PROVIDER,
    embedding_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
    embedding_version: str = DEFAULT_EMBEDDING_VERSION,
    clock: ClockProtocol | None = None,
) -> HybridIngestSummary:
    active_clock = clock if clock is not None else _PerfCounterClock()
    total_start = active_clock.perf_counter()
    clean_collection = assert_collection_is_safe_for_ingest(collection_name)
    clean_batch_size = _validate_batch_size(batch_size)
    clean_max_chunks = _validate_optional_positive_int(max_chunks, "max_chunks")
    metadata = validate_embedding_metadata(
        embedding_model=embedding_model,
        embedding_provider=embedding_provider,
        embedding_dimensions=embedding_dimensions,
        embedding_version=embedding_version,
        dense_vector_name=DENSE_VECTOR_NAME,
        sparse_vector_name=SPARSE_VECTOR_NAME,
    )

    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunk_document(document))
    if clean_max_chunks is not None:
        chunks = chunks[:clean_max_chunks]

    dense_ms = 0.0
    sparse_ms = 0.0
    points: list[HybridIngestPoint] = []
    if chunks:
        dense_vectors, sparse_vectors, dense_ms, sparse_ms = await embed_chunks(
            chunks=chunks,
            dense_embedder=dense_embedder,
            sparse_embedder=sparse_embedder,
            clock=active_clock,
        )
        points = prepare_hybrid_points(
            chunks=chunks,
            dense_vectors=dense_vectors,
            sparse_vectors=sparse_vectors,
            embedding_model=metadata.embedding_model,
            embedding_provider=metadata.embedding_provider,
            embedding_dimensions=metadata.embedding_dimensions,
            embedding_version=metadata.embedding_version,
            dense_vector_name=metadata.dense_vector_name,
            sparse_vector_name=metadata.sparse_vector_name,
        )

    points_sent, batches_sent, upload_ms = await upload_hybrid_points(
        client=upsert_client,
        collection_name=clean_collection,
        points=points,
        batch_size=clean_batch_size,
        dry_run=dry_run,
        clock=active_clock,
    )
    total_ms = _elapsed_ms(total_start, active_clock.perf_counter())
    return HybridIngestSummary(
        collection_name=clean_collection,
        documents_count=len(documents),
        chunks_count=len(chunks),
        points_prepared=len(points),
        points_sent=points_sent,
        batches_sent=batches_sent,
        dense_ms=dense_ms,
        sparse_ms=sparse_ms,
        upload_ms=upload_ms,
        total_ms=total_ms,
        dry_run=dry_run,
        embedding_model=metadata.embedding_model,
        embedding_provider=metadata.embedding_provider,
        embedding_dimensions=metadata.embedding_dimensions,
        embedding_version=metadata.embedding_version,
        dense_vector_name=metadata.dense_vector_name,
        sparse_vector_name=metadata.sparse_vector_name,
        batch_size=clean_batch_size,
    )


def _elapsed_ms(start: float, end: float) -> float:
    raw = (end - start) * 1000.0
    if not math.isfinite(raw):
        raise ValueError("latency must be finite")
    return max(0.0, raw)


class _DeterministicDenseEmbedder:
    async def embed(self, text: str) -> Sequence[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        base = [((digest[index % len(digest)] / 255.0) * 2.0) - 1.0 for index in range(16)]
        repeats = (DEFAULT_EMBEDDING_DIMENSIONS + len(base) - 1) // len(base)
        return (base * repeats)[:DEFAULT_EMBEDDING_DIMENSIONS]


class _DeterministicSparseEmbedder:
    async def embed(self, text: str) -> SparseVector:
        seen: set[int] = set()
        indices: list[int] = []
        counter = 0
        while len(indices) < 4:
            digest = hashlib.sha256(f"{text}\n{counter}".encode("utf-8")).digest()
            candidate = int.from_bytes(digest[:4], byteorder="big") % 65_536
            if candidate not in seen:
                seen.add(candidate)
                indices.append(candidate)
            counter += 1
        values = tuple(1.0 / float(index + 1) for index in range(len(indices)))
        return SparseVector(indices=tuple(indices), values=values)


class _DryRunUpsertClient:
    async def upsert_points(
        self,
        *,
        collection_name: str,
        points: Sequence[HybridIngestPoint],
    ) -> None:
        raise HybridIngestError("execute mode requires an explicit real upsert client")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare hybrid dense+sparse ingest points.")
    parser.add_argument("--corpus-path", type=Path)
    parser.add_argument("--collection", default=HYBRID_COLLECTION_NAME)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-documents", type=int)
    parser.add_argument("--max-chunks", type=int)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--embedding-provider", default=DEFAULT_EMBEDDING_PROVIDER)
    parser.add_argument("--embedding-dimensions", type=int, default=DEFAULT_EMBEDDING_DIMENSIONS)
    parser.add_argument("--embedding-version", default=DEFAULT_EMBEDDING_VERSION)
    parser.add_argument("--synthetic", action="store_true")
    return parser


def _load_documents_for_cli(args: argparse.Namespace) -> list[Document]:
    if args.corpus_path is not None:
        return load_corpus_from_path(args.corpus_path, max_documents=args.max_documents)
    if args.synthetic:
        documents = generate_synthetic_corpus()
        if args.max_documents is not None:
            documents = documents[: _validate_positive_int(args.max_documents, "max_documents")]
        return documents
    raise HybridIngestError("provide --synthetic or --corpus-path")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    dry_run = not args.execute
    if args.dry_run:
        dry_run = True

    try:
        if args.execute:
            raise HybridIngestError("execute mode is not wired to a real upsert client in PR-09")
        documents = _load_documents_for_cli(args)
        summary = asyncio.run(
            run_ingest(
                documents=documents,
                dense_embedder=_DeterministicDenseEmbedder(),
                sparse_embedder=_DeterministicSparseEmbedder(),
                upsert_client=_DryRunUpsertClient(),
                collection_name=args.collection,
                batch_size=args.batch_size,
                dry_run=dry_run,
                max_chunks=args.max_chunks,
                embedding_model=args.embedding_model,
                embedding_provider=args.embedding_provider,
                embedding_dimensions=args.embedding_dimensions,
                embedding_version=args.embedding_version,
            )
        )
        sys.stdout.write(json.dumps(summary.to_safe_dict(), indent=2, ensure_ascii=False))
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        sys.stderr.write(f"hybrid ingest failed: {exc.__class__.__name__}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "HYBRID_COLLECTION_NAME",
    "LEGACY_COLLECTION_NAME",
    "DENSE_VECTOR_NAME",
    "SPARSE_VECTOR_NAME",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_EMBEDDING_PROVIDER",
    "DEFAULT_EMBEDDING_DIMENSIONS",
    "DEFAULT_EMBEDDING_VERSION",
    "DEFAULT_BATCH_SIZE",
    "MAX_BATCH_SIZE",
    "PROTECTED_COLLECTIONS",
    "FORBIDDEN_SUMMARY_KEYS",
    "HybridIngestError",
    "Document",
    "Chunk",
    "SparseVector",
    "EmbeddingMetadata",
    "HybridIngestPoint",
    "HybridIngestSummary",
    "DenseEmbedderProtocol",
    "SparseEmbedderProtocol",
    "HybridUpsertClientProtocol",
    "ClockProtocol",
    "make_chunk_id",
    "chunk_document",
    "generate_synthetic_corpus",
    "load_corpus_from_path",
    "validate_embedding_metadata",
    "validate_dense_vector",
    "validate_sparse_vector",
    "build_payload",
    "prepare_hybrid_points",
    "embed_chunks",
    "batched",
    "assert_collection_is_safe_for_ingest",
    "upload_hybrid_points",
    "run_ingest",
    "main",
]
