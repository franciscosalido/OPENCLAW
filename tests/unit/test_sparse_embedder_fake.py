"""Unit tests for the deterministic fake BM25 sparse embedder."""

from __future__ import annotations

import unittest

from backend.rag.sparse_embedder_protocol import SparseEmbedder
from tests.fakes.fake_bm25_embedder import FakeBM25Embedder


class FakeBM25EmbedderTests(unittest.TestCase):
    def test_fake_embedder_is_sparse_embedder(self) -> None:
        self.assertIsInstance(FakeBM25Embedder(), SparseEmbedder)

    def test_same_text_produces_same_sparse_vector(self) -> None:
        embedder = FakeBM25Embedder()

        first = embedder.embed_sparse("duration sintetica")
        second = embedder.embed_sparse("duration sintetica")

        self.assertEqual(first, second)
        self.assertEqual(first.nnz, 8)

    def test_batch_empty_returns_empty_list(self) -> None:
        self.assertEqual(FakeBM25Embedder().embed_sparse_batch([]), [])

    def test_batch_multiple_preserves_order(self) -> None:
        embedder = FakeBM25Embedder()
        texts = ["alpha", "beta", "gamma"]

        vectors = embedder.embed_sparse_batch(texts)

        self.assertEqual(vectors, [embedder.embed_sparse(text) for text in texts])
        self.assertNotEqual(vectors[0], vectors[1])

    def test_empty_text_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "empty"):
            FakeBM25Embedder().embed_sparse("  ")


if __name__ == "__main__":
    unittest.main()
