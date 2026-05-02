from __future__ import annotations

import unittest
from collections.abc import Mapping, Sequence
from typing import Any

from backend.rag.context_packer import RetrievedChunk
from backend.rag.retriever import Retriever


class FakeEmbedder:
    def __init__(self) -> None:
        self.seen_texts: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.seen_texts.append(text)
        return [1.0, 0.0, 0.0]


class FakeStore:
    def __init__(self) -> None:
        self.seen_vector: Sequence[float] | None = None
        self.seen_top_k: int | None = None
        self.seen_threshold: float | None = None
        self.seen_filters: Mapping[str, Any] | None = None

    def search(
        self,
        vector: Sequence[float],
        top_k: int = 5,
        score_threshold: float | None = 0.3,
        filters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.seen_vector = vector
        self.seen_top_k = top_k
        self.seen_threshold = score_threshold
        self.seen_filters = filters
        return [
            {
                "id": "point-a",
                "score": 0.91,
                "doc_id": "doc-a",
                "chunk_index": 1,
                "text": "conteudo sintetico de selic",
                "payload": {"token_count": 4, "source": "synthetic"},
            },
            {
                "id": "point-b",
                "score": 0.82,
                "doc_id": "doc-a",
                "chunk_index": 0,
                "text": "introducao sintetica de selic",
                "payload": {"token_count": 4, "source": "synthetic"},
            },
        ]


class FakeAsyncStore:
    def __init__(self) -> None:
        self.delegate = FakeStore()

    async def search(
        self,
        vector: Sequence[float],
        top_k: int = 5,
        score_threshold: float | None = 0.3,
        filters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self.delegate.search(
            vector=vector,
            top_k=top_k,
            score_threshold=score_threshold,
            filters=filters,
        )


class FakePacker:
    def __init__(self) -> None:
        self.seen_chunks: list[RetrievedChunk] = []

    def pack(self, chunks: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
        self.seen_chunks = list(chunks)
        return sorted(self.seen_chunks, key=lambda chunk: chunk.chunk_index)


class RetrieverTests(unittest.IsolatedAsyncioTestCase):
    async def test_retrieve_orchestrates_embed_search_and_pack(self) -> None:
        embedder = FakeEmbedder()
        store = FakeStore()
        packer = FakePacker()
        retriever = Retriever(
            embedder=embedder,
            store=store,
            packer=packer,
            top_k=5,
            score_threshold=0.4,
        )

        chunks = await retriever.retrieve(
            "  Qual o impacto da Selic sintetica?  ",
            top_k=2,
            filters={"source": "synthetic"},
        )

        self.assertEqual(embedder.seen_texts, ["Qual o impacto da Selic sintetica?"])
        self.assertEqual(store.seen_vector, [1.0, 0.0, 0.0])
        self.assertEqual(store.seen_top_k, 2)
        self.assertEqual(store.seen_threshold, 0.4)
        self.assertEqual(store.seen_filters, {"source": "synthetic"})
        self.assertEqual([chunk.rank for chunk in packer.seen_chunks], [1, 2])
        self.assertEqual([chunk.chunk_index for chunk in chunks], [0, 1])
        self.assertIsNotNone(retriever.last_timings)

    async def test_retriever_timings_separate_embedding_search_pack(self) -> None:
        retriever = Retriever(
            embedder=FakeEmbedder(),
            store=FakeStore(),
            packer=FakePacker(),
        )

        await retriever.retrieve("pergunta sintetica")

        self.assertIsNotNone(retriever.last_timings)
        assert retriever.last_timings is not None
        timings = retriever.last_timings.as_dict()
        self.assertEqual(
            set(timings),
            {"embed_ms", "search_ms", "pack_ms", "total_ms"},
        )
        for value in timings.values():
            self.assertIsInstance(value, float)
            self.assertGreaterEqual(value, 0.0)

    async def test_retrieve_accepts_async_vector_store(self) -> None:
        retriever = Retriever(
            embedder=FakeEmbedder(),
            store=FakeAsyncStore(),
            packer=FakePacker(),
        )

        chunks = await retriever.retrieve("pergunta sintetica")

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].doc_id, "doc-a")

    async def test_retrieve_uses_default_top_k_when_not_overridden(self) -> None:
        store = FakeStore()
        retriever = Retriever(
            embedder=FakeEmbedder(),
            store=store,
            packer=FakePacker(),
            top_k=7,
            score_threshold=None,
        )

        await retriever.retrieve("pergunta sintetica")

        self.assertEqual(store.seen_top_k, 7)
        self.assertIsNone(store.seen_threshold)

    async def test_retrieve_validates_question_and_top_k(self) -> None:
        retriever = Retriever(
            embedder=FakeEmbedder(),
            store=FakeStore(),
            packer=FakePacker(),
        )

        with self.assertRaises(ValueError):
            await retriever.retrieve("   ")
        with self.assertRaises(ValueError):
            await retriever.retrieve("pergunta", top_k=0)

    async def test_constructor_validates_options(self) -> None:
        with self.assertRaises(ValueError):
            Retriever(
                embedder=FakeEmbedder(),
                store=FakeStore(),
                top_k=0,
            )
        with self.assertRaises(ValueError):
            Retriever(
                embedder=FakeEmbedder(),
                store=FakeStore(),
                score_threshold=1.5,
            )


if __name__ == "__main__":
    unittest.main()
