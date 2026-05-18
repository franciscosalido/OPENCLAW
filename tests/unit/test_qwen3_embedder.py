"""Unit tests for the Qwen3 dense embedder adapter."""

from __future__ import annotations

import math
import unittest
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch

from backend.rag.embedder_protocol import DenseEmbedder
from backend.rag.embedding_config import EmbeddingProfileConfig
from backend.rag.qwen3_embedder import Qwen3Embedder
from tests.fakes.fake_qwen3_embedder import FakeQwen3Embedder


def _qwen3_profile() -> EmbeddingProfileConfig:
    return EmbeddingProfileConfig(
        provider="sentence_transformers",
        model="Qwen/Qwen3-Embedding-8B",
        model_family="qwen3",
        version="v1",
        dimensions=4096,
        effective_dimensions=None,
        mrl_supported=True,
        context_length=32768,
        distance="cosine",
        normalized=True,
        instruction_aware=True,
        query_instruction=(
            "Given a financial knowledge retrieval query in Brazilian Portuguese "
            "or English, retrieve relevant passages that answer the query."
        ),
        document_instruction=None,
        profile_fingerprint=None,
    )


class RecordingEncoder:
    """Small encoder spy with deterministic vector output."""

    def __init__(self, dimensions: int = 4096) -> None:
        self.dimensions = dimensions
        self.calls: list[tuple[list[str], int, bool, bool]] = []

    def encode(
        self,
        sentences: Sequence[str],
        *,
        batch_size: int,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> list[list[float]]:
        texts = list(sentences)
        self.calls.append(
            (texts, batch_size, normalize_embeddings, show_progress_bar)
        )
        return [self._vector_for_text(text) for text in texts]

    def _vector_for_text(self, text: str) -> list[float]:
        first = float((sum(ord(char) for char in text) % 97) + 1)
        second = float((len(text) % 31) + 1)
        return [first, second] + [0.0] * (self.dimensions - 2)


class Qwen3EmbedderTests(unittest.TestCase):
    """Adapter tests without loading the real 8B model."""

    def test_fake_embedder_dimensions_and_norm(self) -> None:
        fake = FakeQwen3Embedder()

        vector = fake.embed_query("duration sintetica")
        norm = math.sqrt(sum(value * value for value in vector))

        self.assertIsInstance(fake, DenseEmbedder)
        self.assertEqual(len(vector), 4096)
        self.assertAlmostEqual(norm, 1.0, places=6)

    def test_fake_embedder_query_vs_document_differs(self) -> None:
        fake = FakeQwen3Embedder()
        text = "mesmo texto"

        self.assertNotEqual(fake.embed_query(text), fake.embed_document(text))

    def test_fake_embedder_is_deterministic_for_same_query(self) -> None:
        fake = FakeQwen3Embedder()

        first = fake.embed_query("criterio sintetico")
        second = fake.embed_query("criterio sintetico")

        self.assertEqual(first, second)

    def test_adapter_rejects_wrong_model_family(self) -> None:
        profile = _qwen3_profile().model_copy(update={"model_family": "nomic"})

        with self.assertRaisesRegex(ValueError, "model_family 'qwen3'"):
            Qwen3Embedder(profile, encoder=RecordingEncoder())

    def test_adapter_rejects_missing_instruction(self) -> None:
        profile = _qwen3_profile().model_copy(update={"query_instruction": None})

        with self.assertRaisesRegex(ValueError, "query_instruction"):
            Qwen3Embedder(profile, encoder=RecordingEncoder())

    def test_embed_query_applies_instruction_and_document_does_not(self) -> None:
        encoder = RecordingEncoder()
        profile = _qwen3_profile()
        embedder = Qwen3Embedder(profile, encoder=encoder)

        embedder.embed_query("qual o criterio sintetico?")
        embedder.embed_document("qual o criterio sintetico?")

        query_text = encoder.calls[0][0][0]
        document_text = encoder.calls[1][0][0]
        self.assertTrue(query_text.startswith(profile.query_instruction or ""))
        self.assertTrue(query_text.endswith("qual o criterio sintetico?"))
        self.assertEqual(document_text, "qual o criterio sintetico?")
        self.assertTrue(encoder.calls[0][2])
        self.assertFalse(encoder.calls[0][3])

    def test_document_instruction_is_applied_when_explicitly_configured(self) -> None:
        encoder = RecordingEncoder()
        profile = _qwen3_profile().model_copy(
            update={"document_instruction": "Represent this passage for retrieval."}
        )
        embedder = Qwen3Embedder(profile, encoder=encoder)

        embedder.embed_document("documento sintetico")

        document_text = encoder.calls[0][0][0]
        self.assertEqual(
            document_text,
            "Represent this passage for retrieval.\ndocumento sintetico",
        )

    def test_embed_documents_preserves_order_and_length(self) -> None:
        encoder = RecordingEncoder()
        embedder = Qwen3Embedder(_qwen3_profile(), encoder=encoder)
        texts = ["doc a", "doc b", "doc c"]

        vectors = embedder.embed_documents(texts, batch_size=2)

        self.assertEqual(len(vectors), 3)
        self.assertTrue(all(len(vector) == 4096 for vector in vectors))
        self.assertEqual(encoder.calls[0][0], ["doc a", "doc b"])
        self.assertEqual(encoder.calls[1][0], ["doc c"])

    def test_effective_dimensions_truncate_and_renormalize(self) -> None:
        profile = _qwen3_profile().model_copy(update={"effective_dimensions": 2})
        embedder = Qwen3Embedder(profile, encoder=RecordingEncoder())

        vector = embedder.embed_document("texto valido")
        norm = math.sqrt(sum(value * value for value in vector))

        self.assertEqual(len(vector), 2)
        # MRL proof: truncation keeps 2 dims, then L2 normalization restores norm 1.
        self.assertAlmostEqual(norm, 1.0, places=6)

    def test_adapter_validates_vector_dimensions(self) -> None:
        embedder = Qwen3Embedder(_qwen3_profile(), encoder=RecordingEncoder(10))

        with self.assertRaisesRegex(RuntimeError, "expected 4096 dims"):
            embedder.embed_query("texto valido")

    def test_empty_inputs_are_rejected(self) -> None:
        embedder = Qwen3Embedder(_qwen3_profile(), encoder=RecordingEncoder())

        with self.assertRaisesRegex(ValueError, "query text cannot be empty"):
            embedder.embed_query("  ")
        with self.assertRaisesRegex(ValueError, "texts cannot be empty"):
            embedder.embed_documents([])

    def test_missing_optional_dependency_has_clear_error(self) -> None:
        with patch(
            "backend.rag.qwen3_embedder.import_module",
            side_effect=ImportError("missing"),
        ):
            with self.assertRaisesRegex(ImportError, "openclaw\\[qwen3\\]"):
                Qwen3Embedder(_qwen3_profile())

    def test_qwen3_adapter_is_not_imported_by_existing_rag_runtime_modules(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        rag_files = sorted((repo_root / "backend" / "rag").glob("*.py"))
        scanned = [
            path
            for path in rag_files
            if path.name
            not in {
                "qwen3_embedder.py",
            }
        ]

        offenders = [
            path.name
            for path in scanned
            if "qwen3_embedder" in path.read_text(encoding="utf-8")
        ]

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
