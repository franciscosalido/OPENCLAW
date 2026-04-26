#!/usr/bin/env python
"""Ingest fictional PT-BR documents into local Qdrant.

Usage:
    python scripts/rag_ingest_synthetic.py

The script uses only synthetic documents bundled with the repository.
No real portfolio, brokerage, private document, or remote AI is accessed.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from backend.rag.embeddings import OllamaEmbedder
from backend.rag.qdrant_store import QdrantVectorStore, VectorStoreChunk
from backend.rag.synthetic_documents import (
    SyntheticDocument,
    get_synthetic_documents,
    vector_chunks_for_document,
)


class EmbedBatchClient(Protocol):
    """Minimal embedding batch interface required by synthetic ingest."""

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a sequence of texts."""
        ...


@dataclass(frozen=True)
class DocumentIngestResult:
    """Per-document ingest metrics."""

    doc_id: str
    chunk_count: int
    embedding_ms: float


@dataclass(frozen=True)
class IngestSummary:
    """Synthetic ingest summary."""

    documents: list[DocumentIngestResult]
    total_chunks: int
    total_ms: float


async def ingest_synthetic_documents(
    documents: Sequence[SyntheticDocument] | None = None,
    embedder: EmbedBatchClient | None = None,
    store: QdrantVectorStore | None = None,
    max_tokens: int = 400,
    overlap_tokens: int = 80,
    dry_run: bool = False,
) -> IngestSummary:
    """Ingest synthetic documents using injected or default local components."""

    selected_documents = list(documents or get_synthetic_documents())
    owned_embedder = embedder is None
    owned_store = store is None
    active_embedder: EmbedBatchClient = embedder or OllamaEmbedder()
    active_store = store or QdrantVectorStore()
    start = time.perf_counter()
    results: list[DocumentIngestResult] = []

    try:
        if not dry_run:
            active_store.ensure_collection()

        for document in selected_documents:
            chunks = vector_chunks_for_document(
                document,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
            )
            embedding_start = time.perf_counter()
            vectors = await _embed_chunks(active_embedder, chunks, dry_run=dry_run)
            embedding_ms = _elapsed_ms(embedding_start)

            if not dry_run:
                active_store.delete_document(document.doc_id)
                active_store.upsert(chunks, vectors)

            result = DocumentIngestResult(
                doc_id=document.doc_id,
                chunk_count=len(chunks),
                embedding_ms=embedding_ms,
            )
            results.append(result)
            print(
                f"{document.doc_id}: {len(chunks)} chunks | "
                f"embedding={embedding_ms:.1f}ms | "
                f"{'dry-run' if dry_run else 'upserted'}"
            )

        total_ms = _elapsed_ms(start)
        total_chunks = sum(result.chunk_count for result in results)
        print(f"Total: {total_chunks} chunks em {total_ms:.1f}ms")
        return IngestSummary(
            documents=results,
            total_chunks=total_chunks,
            total_ms=total_ms,
        )
    finally:
        if owned_embedder:
            await cast(OllamaEmbedder, active_embedder).aclose()
        if owned_store:
            active_store.close()


async def _embed_chunks(
    embedder: EmbedBatchClient,
    chunks: Sequence[VectorStoreChunk],
    dry_run: bool,
) -> list[list[float]]:
    if dry_run:
        return [[1.0] + [0.0] * 767 for _chunk in chunks]
    return await embedder.embed_batch([chunk.text for chunk in chunks])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingere documentos sinteticos no Qdrant local."
    )
    parser.add_argument("--max-tokens", type=int, default=400)
    parser.add_argument("--overlap-tokens", type=int, default=80)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Executa chunking e métricas sem chamar Ollama/Qdrant.",
    )
    return parser.parse_args()


async def main_async() -> None:
    args = parse_args()
    await ingest_synthetic_documents(
        max_tokens=args.max_tokens,
        overlap_tokens=args.overlap_tokens,
        dry_run=args.dry_run,
    )


def main() -> None:
    asyncio.run(main_async())


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


if __name__ == "__main__":
    main()
