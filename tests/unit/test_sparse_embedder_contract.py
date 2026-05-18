"""Unit tests for BM25 sparse embedder contract and registry."""

from __future__ import annotations

import unittest
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.rag.sparse_embedder import (
    BM25SparseEmbedder,
    DEFAULT_BM25_BATCH_SIZE,
    _clean_sparse_text,
)
from backend.rag.sparse_embedder_protocol import SparseEmbedder
from backend.rag.sparse_embedder_registry import (
    clear_sparse_registry_for_tests,
    get_sparse_registry,
    register_sparse,
)


class RecordingSparseEncoder:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], int]] = []

    def embed(
        self,
        documents: Sequence[str],
        *,
        batch_size: int,
    ) -> list[SimpleNamespace]:
        self.calls.append((list(documents), batch_size))
        return [
            SimpleNamespace(indices=[5, 1, 3], values=[0.5, 1.0, 0.75])
            for _ in documents
        ]


class ShortSparseEncoder:
    def embed(
        self,
        documents: Sequence[str],
        *,
        batch_size: int,
    ) -> list[SimpleNamespace]:
        return [SimpleNamespace(indices=[1], values=[1.0]) for _ in documents[:-1]]


class MalformedSparseEncoder:
    def embed(
        self,
        documents: Sequence[str],
        *,
        batch_size: int,
    ) -> list[SimpleNamespace]:
        return [SimpleNamespace(indices=[1, 2], values=[1.0]) for _ in documents]


class BM25SparseEmbedderContractTests(unittest.TestCase):
    def test_adapter_is_sparse_embedder_and_uses_default_model_name(self) -> None:
        embedder = BM25SparseEmbedder(encoder=RecordingSparseEncoder())

        self.assertIsInstance(embedder, SparseEmbedder)
        self.assertEqual(embedder.model_name, "Qdrant/bm25")

    def test_clean_sparse_text_rejects_invalid_inputs(self) -> None:
        with self.assertRaises(TypeError):
            _clean_sparse_text(None)
        with self.assertRaisesRegex(ValueError, "empty"):
            _clean_sparse_text(" \t\n")
        with self.assertRaisesRegex(ValueError, "null bytes"):
            _clean_sparse_text("abc\x00def")

    def test_embed_sparse_sorts_indices_and_preserves_values(self) -> None:
        encoder = RecordingSparseEncoder()
        embedder = BM25SparseEmbedder(encoder=encoder)

        vector = embedder.embed_sparse("texto valido")

        self.assertEqual(vector.indices, (1, 3, 5))
        self.assertEqual(vector.values, (1.0, 0.75, 0.5))
        self.assertEqual(encoder.calls, [(["texto valido"], 1)])

    def test_batch_empty_returns_empty_without_encoder_call(self) -> None:
        encoder = RecordingSparseEncoder()
        embedder = BM25SparseEmbedder(encoder=encoder)

        self.assertEqual(embedder.embed_sparse_batch([]), [])
        self.assertEqual(encoder.calls, [])

    def test_batch_multiple_preserves_order_and_uses_batches(self) -> None:
        encoder = RecordingSparseEncoder()
        embedder = BM25SparseEmbedder(encoder=encoder)

        vectors = embedder.embed_sparse_batch(["a", "b", "c"], batch_size=2)

        self.assertEqual(len(vectors), 3)
        self.assertEqual(encoder.calls, [(["a", "b"], 2), (["c"], 2)])

    def test_batch_rejects_invalid_batch_size(self) -> None:
        embedder = BM25SparseEmbedder(encoder=RecordingSparseEncoder())

        with self.assertRaisesRegex(ValueError, "batch_size"):
            embedder.embed_sparse_batch(["a"], batch_size=0)

    def test_result_count_mismatch_raises_runtime_error(self) -> None:
        embedder = BM25SparseEmbedder(encoder=ShortSparseEncoder())

        with self.assertRaisesRegex(RuntimeError, "expected 2 sparse vectors"):
            embedder.embed_sparse_batch(["a", "b"])

    def test_malformed_encoder_output_raises_value_error(self) -> None:
        embedder = BM25SparseEmbedder(encoder=MalformedSparseEncoder())

        with self.assertRaisesRegex(ValueError, "len\\(indices\\)"):
            embedder.embed_sparse("a")

    def test_missing_fastembed_dependency_has_clear_error(self) -> None:
        with patch(
            "backend.rag.sparse_embedder.import_module",
            side_effect=ImportError("missing"),
        ):
            with self.assertRaisesRegex(ImportError, "fastembed"):
                BM25SparseEmbedder()

    def test_module_has_no_top_level_fastembed_or_print(self) -> None:
        source = Path("backend/rag/sparse_embedder.py").read_text(encoding="utf-8")

        self.assertNotIn("from fastembed import", source)
        self.assertNotIn("import fastembed", source)
        self.assertNotIn("print(", source)

    def test_default_batch_size_is_exposed(self) -> None:
        self.assertEqual(DEFAULT_BM25_BATCH_SIZE, 32)


class SparseEmbedderRegistryTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_sparse_registry_for_tests()
        register_sparse("bm25", lambda: BM25SparseEmbedder())

    def test_default_bm25_provider_is_registered(self) -> None:
        registry = get_sparse_registry()

        self.assertIn("bm25", registry)

    def test_registry_returns_read_only_snapshot(self) -> None:
        before = get_sparse_registry()
        register_sparse("test_provider_snapshot", lambda: BM25SparseEmbedder())
        after = get_sparse_registry()

        self.assertNotIn("test_provider_snapshot", before)
        self.assertIn("test_provider_snapshot", after)
        with self.assertRaises(TypeError):
            before["x"] = lambda: BM25SparseEmbedder()  # type: ignore[index]

    def test_register_rejects_duplicate_provider(self) -> None:
        with self.assertRaisesRegex(ValueError, "already registered"):
            register_sparse("bm25", lambda: BM25SparseEmbedder())

    def test_register_normalizes_and_rejects_invalid_provider(self) -> None:
        register_sparse("  RC05_PROVIDER  ", lambda: BM25SparseEmbedder())

        self.assertIn("rc05_provider", get_sparse_registry())
        with self.assertRaisesRegex(ValueError, "empty"):
            register_sparse("   ", lambda: BM25SparseEmbedder())
        with self.assertRaisesRegex(ValueError, "null bytes"):
            register_sparse("bad\x00provider", lambda: BM25SparseEmbedder())


if __name__ == "__main__":
    unittest.main()
