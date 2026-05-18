"""Sparse embedder protocol for lexical retrieval adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.rag.sparse_vector import SparseVector


@runtime_checkable
class SparseEmbedder(Protocol):
    """Common interface for BM25 and future sparse lexical embedders."""

    @property
    def model_name(self) -> str:
        """Return the sparse model name, for example ``Qdrant/bm25``."""
        ...

    def embed_sparse(self, text: str) -> SparseVector:
        """Embed one text into a sparse vector."""
        ...

    def embed_sparse_batch(self, texts: list[str]) -> list[SparseVector]:
        """Embed texts in order. Empty batches return an empty list."""
        ...


__all__ = ["SparseEmbedder"]
