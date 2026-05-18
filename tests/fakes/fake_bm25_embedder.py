"""Deterministic fake BM25 sparse embedder for unit tests."""

from __future__ import annotations

import hashlib

from backend.rag.sparse_embedder import _clean_sparse_text
from backend.rag.sparse_embedder_protocol import SparseEmbedder
from backend.rag.sparse_vector import SparseVector

_FAKE_VOCAB_SIZE = 30_000
_FAKE_NNZ = 8


class FakeBM25Embedder(SparseEmbedder):
    """Fake sparse embedder: same input text produces the same vector."""

    model_name: str = "fake-bm25"

    def embed_sparse(self, text: str) -> SparseVector:
        """Embed one text deterministically without external dependencies."""
        return self._sparse_from_text(_clean_sparse_text(text, "text"))

    def embed_sparse_batch(self, texts: list[str]) -> list[SparseVector]:
        """Embed texts in order. Empty batches return an empty list."""
        return [self.embed_sparse(text) for text in texts]

    def _sparse_from_text(self, text: str) -> SparseVector:
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)
        multiplier = 1_664_525
        increment = 1_013_904_223
        modulus = 2**32
        state = seed % modulus
        seen: set[int] = set()
        pairs: list[tuple[int, float]] = []
        rank = 1
        while len(pairs) < _FAKE_NNZ:
            state = (multiplier * state + increment) % modulus
            index = int(state % _FAKE_VOCAB_SIZE)
            if index in seen:
                continue
            seen.add(index)
            pairs.append((index, round(1.0 / float(rank), 6)))
            rank += 1

        sorted_pairs = sorted(pairs, key=lambda pair: pair[0])
        return SparseVector(
            indices=[index for index, _ in sorted_pairs],
            values=[value for _, value in sorted_pairs],
        )


__all__ = ["FakeBM25Embedder"]
