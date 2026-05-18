"""Synchronous dense embedder protocol for PR-04B shadow adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DenseEmbedder(Protocol):
    """Common interface for synchronous dense embedding adapters."""

    @property
    def dimensions(self) -> int:
        """Return the output vector dimension."""
        ...

    @property
    def model_family(self) -> str:
        """Return the embedding model family."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed one retrieval query."""
        ...

    def embed_document(self, text: str) -> list[float]:
        """Embed one document passage."""
        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed document passages, preserving input order."""
        ...


__all__ = ["DenseEmbedder"]
