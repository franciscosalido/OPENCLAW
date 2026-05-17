"""Deterministic fake Qwen3 embedder for unit tests."""

from __future__ import annotations

import hashlib
import math

from backend.rag.embedder_protocol import DenseEmbedder


class FakeQwen3Embedder(DenseEmbedder):
    """Fake embedder: same input text and mode produce the same unit vector."""

    dimensions: int = 4096
    model_family: str = "qwen3"

    def embed_query(self, text: str) -> list[float]:
        """Embed a query using a mode-specific deterministic prefix."""
        return self._hash_vector(f"query::{text}")

    def embed_document(self, text: str) -> list[float]:
        """Embed a document using a mode-specific deterministic prefix."""
        return self._hash_vector(f"document::{text}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents in order."""
        return [self.embed_document(text) for text in texts]

    def _hash_vector(self, text: str) -> list[float]:
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        multiplier = 1_664_525
        increment = 1_013_904_223
        modulus = 2**32
        state = seed
        values: list[float] = []
        for _ in range(self.dimensions):
            state = (multiplier * state + increment) % modulus
            values.append((float(state) / float(modulus)) * 2.0 - 1.0)

        norm = math.sqrt(sum(value * value for value in values))
        if norm == 0.0:
            return values
        return [value / norm for value in values]


__all__ = ["FakeQwen3Embedder"]
