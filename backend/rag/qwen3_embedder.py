"""Qwen3-Embedding-8B dense adapter for shadow embedding experiments.

The adapter is intentionally isolated from the current dense runtime. It does
not touch retrievers, vector stores, or Qdrant collections; it only formats
texts, calls an injected or lazily loaded encoder, and validates output vectors.
"""

from __future__ import annotations

import math
from importlib import import_module
from collections.abc import Sequence
from typing import Protocol, cast

from backend.rag.embedder_protocol import DenseEmbedder
from backend.rag.embedding_config import EmbeddingProfileConfig
from backend.rag.embedding_metadata import compute_profile_fingerprint

DEFAULT_QWEN3_BATCH_SIZE = 8


class SentenceTransformerLike(Protocol):
    """Minimal encoder surface used by ``Qwen3Embedder``."""

    def encode(
        self,
        sentences: Sequence[str],
        *,
        batch_size: int,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> object:
        """Encode a batch of strings and return a matrix-like object."""
        ...


class Qwen3Embedder(DenseEmbedder):
    """Instruction-aware adapter for a validated Qwen3 embedding profile."""

    def __init__(
        self,
        profile: EmbeddingProfileConfig,
        *,
        device: str = "cpu",
        encoder: SentenceTransformerLike | None = None,
    ) -> None:
        if profile.model_family != "qwen3":
            raise ValueError(
                "Qwen3Embedder requires model_family 'qwen3', "
                f"got {profile.model_family!r}"
            )
        if not profile.instruction_aware:
            raise ValueError("Qwen3Embedder requires instruction_aware=True")
        if profile.query_instruction is None:
            raise ValueError("Qwen3Embedder requires query_instruction to be set")

        self._profile = profile
        self._effective_dimensions = profile.effective_dimensions or profile.dimensions
        self._truncate = self._effective_dimensions < profile.dimensions
        self._profile_fingerprint = compute_profile_fingerprint(profile)
        self._encoder = encoder if encoder is not None else self._load_model(
            profile.model,
            device,
        )

    @staticmethod
    def _load_model(model_name: str, device: str) -> SentenceTransformerLike:
        try:
            sentence_transformers = import_module("sentence_transformers")
        except ImportError as exc:
            raise ImportError(
                "Qwen3Embedder requires sentence-transformers>=2.7.0 and "
                "transformers>=4.51.0. Install optional extras with: "
                "pip install 'openclaw[qwen3]'"
            ) from exc
        sentence_transformer = getattr(sentence_transformers, "SentenceTransformer")
        return cast(
            SentenceTransformerLike,
            sentence_transformer(model_name, device=device, trust_remote_code=True),
        )

    @property
    def dimensions(self) -> int:
        """Return effective Qwen3 vector dimensions."""
        return self._effective_dimensions

    @property
    def model_family(self) -> str:
        """Return ``qwen3`` for this adapter."""
        return self._profile.model_family

    @property
    def profile_fingerprint(self) -> str:
        """Return the PR-04A profile fingerprint."""
        return self._profile_fingerprint

    def embed_query(self, text: str) -> list[float]:
        """Embed a query with the configured Qwen3 query instruction."""
        [vector] = self._encode_batch([self._format_query(text)], batch_size=1)
        self._validate_vector(vector)
        return vector

    def embed_document(self, text: str) -> list[float]:
        """Embed a document without adding a query instruction."""
        [vector] = self._encode_batch([self._format_document(text)], batch_size=1)
        self._validate_vector(vector)
        return vector

    def embed_documents(
        self,
        texts: list[str],
        batch_size: int = DEFAULT_QWEN3_BATCH_SIZE,
    ) -> list[list[float]]:
        """Embed documents in batches while preserving input order."""
        if not texts:
            raise ValueError("texts cannot be empty")
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

        results: list[list[float]] = []
        for offset in range(0, len(texts), batch_size):
            batch = texts[offset : offset + batch_size]
            formatted = [self._format_document(text) for text in batch]
            vectors = self._encode_batch(formatted, batch_size=batch_size)
            for vector in vectors:
                self._validate_vector(vector)
            results.extend(vectors)
        return results

    def _format_query(self, text: str) -> str:
        query = _clean_text(text, "query")
        instruction = self._profile.query_instruction
        if instruction is None:
            raise RuntimeError("Qwen3 query_instruction unexpectedly missing")
        return f"{instruction.strip()}\n{query}"

    def _format_document(self, text: str) -> str:
        document = _clean_text(text, "document")
        instruction = self._profile.document_instruction
        if instruction is None:
            return document
        return f"{instruction.strip()}\n{document}"

    def _encode_batch(self, texts: list[str], *, batch_size: int) -> list[list[float]]:
        encoded = self._encoder.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        raw_vectors = _coerce_vectors(encoded)
        return [self._truncate_and_normalize(vector) for vector in raw_vectors]

    def _truncate_and_normalize(self, vector: list[float]) -> list[float]:
        active = vector[: self._effective_dimensions] if self._truncate else vector
        norm = math.sqrt(sum(value * value for value in active))
        if norm == 0.0:
            return active
        return [value / norm for value in active]

    def _validate_vector(self, vector: list[float]) -> None:
        if len(vector) != self._effective_dimensions:
            raise RuntimeError(
                "Qwen3Embedder expected "
                f"{self._effective_dimensions} dims, got {len(vector)}"
            )


def _clean_text(text: str, label: str) -> str:
    if "\x00" in text:
        raise ValueError(f"{label} text cannot contain null bytes")
    clean = text.strip()
    if not clean:
        raise ValueError(f"{label} text cannot be empty")
    return clean


def _coerce_vectors(encoded: object) -> list[list[float]]:
    materialized = _tolist(encoded)
    if not isinstance(materialized, Sequence) or isinstance(
        materialized,
        (str, bytes),
    ):
        raise RuntimeError("encoder returned a non-sequence embedding result")

    vectors: list[list[float]] = []
    for row in materialized:
        vector = _tolist(row)
        if not isinstance(vector, Sequence) or isinstance(vector, (str, bytes)):
            raise RuntimeError("encoder returned a malformed embedding vector")
        vectors.append([float(value) for value in vector])
    return vectors


def _tolist(value: object) -> object:
    method = getattr(value, "tolist", None)
    if callable(method):
        return method()
    return value


__all__ = ["Qwen3Embedder", "SentenceTransformerLike"]
