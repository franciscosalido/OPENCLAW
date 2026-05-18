"""BM25 sparse embedder adapter.

PR-05 prepares the lexical sparse component only. This module does not import
Qdrant, does not write collections, and does not implement hybrid retrieval.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from importlib import import_module
from typing import Any, Protocol, cast

from loguru import logger

from backend.rag.sparse_embedder_protocol import SparseEmbedder
from backend.rag.sparse_vector import SparseVector

DEFAULT_BM25_MODEL_NAME = "Qdrant/bm25"
DEFAULT_BM25_BATCH_SIZE = 32

_log = logger.bind(component="sparse_embedder", provider="bm25")


class SparseEmbeddingLike(Protocol):
    """Minimal FastEmbed-like sparse encoder surface used by the adapter."""

    def embed(
        self,
        documents: Sequence[str],
        *,
        batch_size: int,
    ) -> Iterable[object]:
        """Embed documents and yield objects with ``indices`` and ``values``."""
        ...


class BM25SparseEmbedder(SparseEmbedder):
    """Adapter around ``fastembed.SparseTextEmbedding`` for BM25 vectors."""

    def __init__(
        self,
        model_name: str = DEFAULT_BM25_MODEL_NAME,
        *,
        encoder: SparseEmbeddingLike | None = None,
    ) -> None:
        clean_model_name = _clean_sparse_text(model_name, "model_name")
        self._model_name = clean_model_name
        self._encoder = (
            encoder if encoder is not None else self._load_model(clean_model_name)
        )
        _log.debug("BM25 sparse embedder initialized", model_name=clean_model_name)

    @staticmethod
    def _load_model(model_name: str) -> SparseEmbeddingLike:
        try:
            fastembed = import_module("fastembed")
        except ImportError as exc:
            raise ImportError(
                "BM25SparseEmbedder requires fastembed. Install optional sparse "
                "dependencies before running the real BM25 adapter."
            ) from exc
        sparse_text_embedding = getattr(fastembed, "SparseTextEmbedding")
        _log.info("loading BM25 sparse model", model_name=model_name)
        return cast(
            SparseEmbeddingLike,
            sparse_text_embedding(model_name=model_name),
        )

    @property
    def model_name(self) -> str:
        """Return the configured BM25 sparse model name."""
        return self._model_name

    def embed_sparse(self, text: str) -> SparseVector:
        """Embed a single text into a BM25 sparse vector."""
        [vector] = self.embed_sparse_batch([text], batch_size=1)
        return vector

    def embed_sparse_batch(
        self,
        texts: list[str],
        batch_size: int = DEFAULT_BM25_BATCH_SIZE,
    ) -> list[SparseVector]:
        """Embed a batch of texts while preserving input order."""
        if not texts:
            return []
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

        cleaned = [_clean_sparse_text(text, "text") for text in texts]
        _log.debug(
            "BM25 sparse batch started",
            batch_size=batch_size,
            text_count=len(cleaned),
        )

        results: list[SparseVector] = []
        for offset in range(0, len(cleaned), batch_size):
            chunk = cleaned[offset : offset + batch_size]
            raw_vectors = self._encoder.embed(chunk, batch_size=batch_size)
            for raw_vector in raw_vectors:
                results.append(_coerce_sparse_vector(raw_vector))

        if len(results) != len(cleaned):
            raise RuntimeError(
                "BM25SparseEmbedder expected "
                f"{len(cleaned)} sparse vectors, got {len(results)}"
            )

        nnz_mean = sum(vector.nnz for vector in results) / float(len(results))
        _log.debug(
            "BM25 sparse batch completed",
            produced=len(results),
            nnz_mean=nnz_mean,
        )
        return results


def _clean_sparse_text(value: object, label: str = "text") -> str:
    """Return stripped text or raise for invalid sparse embedder input."""
    if not isinstance(value, str):
        raise TypeError(f"sparse {label} must be str")
    if "\x00" in value:
        raise ValueError(f"sparse {label} cannot contain null bytes")
    clean = value.strip()
    if not clean:
        raise ValueError(f"sparse {label} cannot be empty or whitespace-only")
    return clean


def _coerce_sparse_vector(raw_vector: object) -> SparseVector:
    raw_indices = getattr(raw_vector, "indices", None)
    raw_values = getattr(raw_vector, "values", None)
    if raw_indices is None or raw_values is None:
        raise RuntimeError("sparse encoder returned object without indices/values")

    indices = [int(index) for index in _to_sequence(raw_indices, "indices")]
    values = [float(value) for value in _to_sequence(raw_values, "values")]
    sorted_indices, sorted_values = _sort_sparse(indices, values)
    return SparseVector(indices=sorted_indices, values=sorted_values)


def _to_sequence(value: object, label: str) -> Sequence[Any]:
    materialized = _tolist(value)
    if not isinstance(materialized, Sequence) or isinstance(
        materialized,
        (str, bytes),
    ):
        raise RuntimeError(f"sparse encoder returned malformed {label}")
    return materialized


def _tolist(value: object) -> object:
    method = getattr(value, "tolist", None)
    if callable(method):
        return method()
    return value


def _sort_sparse(
    indices: list[int],
    values: list[float],
) -> tuple[list[int], list[float]]:
    if len(indices) != len(values):
        raise ValueError(
            "SparseVector requires len(indices) == len(values), "
            f"got {len(indices)} vs {len(values)}"
        )
    if not indices:
        return [], []
    pairs = sorted(zip(indices, values, strict=True), key=lambda pair: pair[0])
    sorted_indices, sorted_values = zip(*pairs, strict=True)
    return list(sorted_indices), list(sorted_values)


__all__ = [
    "BM25SparseEmbedder",
    "DEFAULT_BM25_BATCH_SIZE",
    "DEFAULT_BM25_MODEL_NAME",
    "SparseEmbeddingLike",
]
