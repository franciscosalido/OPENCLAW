from __future__ import annotations

import unittest
from collections.abc import Mapping, Sequence
from typing import Any

from backend.rag.context_packer import RetrievedChunk
from backend.rag.pipeline import LocalRagPipeline
from backend.rag.prompt_builder import PromptBuilder


class FakeRetriever:
    def __init__(self) -> None:
        self.last_timings: dict[str, float] | None = None
        self.seen_question: str | None = None
        self.seen_top_k: int | None = None

    async def retrieve(
        self,
        question: str,
        top_k: int | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        self.seen_question = question
        self.seen_top_k = top_k
        self.last_timings = {"embed_ms": 1.0, "search_ms": 2.0, "pack_ms": 1.0}
        return [
            RetrievedChunk(
                id="selic:0",
                score=0.91,
                doc_id="selic_sintetica",
                chunk_index=0,
                text=(
                    "Documento sintetico: Selic mais alta tende a elevar a "
                    "atratividade relativa da renda fixa local."
                ),
                token_count=14,
                rank=1,
                payload={"source": "synthetic"},
            ),
            RetrievedChunk(
                id="rebalanceamento:1",
                score=0.74,
                doc_id="rebalanceamento_sintetico",
                chunk_index=1,
                text=(
                    "Documento sintetico: rebalanceamento pode usar bandas "
                    "predefinidas para reduzir decisoes emocionais."
                ),
                token_count=13,
                rank=2,
                payload={"source": "synthetic"},
            ),
        ]


class FakeGenerator:
    def __init__(self) -> None:
        self.seen_messages: Sequence[dict[str, str]] = []
        self.seen_thinking_mode: bool | None = None

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        temperature: float | None = None,
        thinking_mode: bool = False,
        max_tokens: int | None = None,
    ) -> str:
        del max_tokens
        self.seen_messages = messages
        self.seen_thinking_mode = thinking_mode
        return (
            "Com base no contexto local sintetico, Selic mais alta favorece "
            "renda fixa em relacao a ativos de maior risco [selic_sintetica#0]. "
            "O rebalanceamento deve seguir bandas previamente definidas "
            "[rebalanceamento_sintetico#1]."
        )


class LocalRagPipelineSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_returns_answer_citations_chunks_and_latency(self) -> None:
        retriever = FakeRetriever()
        generator = FakeGenerator()
        pipeline = LocalRagPipeline(
            retriever=retriever,
            generator=generator,
            prompt_builder=PromptBuilder(),
            thinking_mode=False,
        )

        result = await pipeline.ask(
            "Qual o impacto sintetico da Selic?",
            top_k=2,
            filters={"source": "synthetic"},
        )

        self.assertGreater(len(result.answer), 50)
        self.assertIn("[selic_sintetica#0]", result.answer)
        self.assertIn("[rebalanceamento_sintetico#1]", result.answer)
        self.assertEqual(result.citations, ["selic_sintetica#0", "rebalanceamento_sintetico#1"])
        self.assertEqual(len(result.chunks_used), 2)
        self.assertEqual(retriever.seen_question, "Qual o impacto sintetico da Selic?")
        self.assertEqual(retriever.seen_top_k, 2)
        self.assertFalse(generator.seen_thinking_mode)
        self.assertIn("/no_think", generator.seen_messages[1]["content"])
        self.assertGreaterEqual(result.latency_ms["retrieval_ms"], 0.0)
        self.assertGreaterEqual(result.latency_ms["prompt_ms"], 0.0)
        self.assertGreaterEqual(result.latency_ms["generation_ms"], 0.0)
        self.assertGreaterEqual(result.latency_ms["total_ms"], 0.0)

    async def test_pipeline_rejects_empty_question(self) -> None:
        pipeline = LocalRagPipeline(
            retriever=FakeRetriever(),
            generator=FakeGenerator(),
            prompt_builder=PromptBuilder(),
        )

        with self.assertRaises(ValueError):
            await pipeline.ask("   ")


if __name__ == "__main__":
    unittest.main()
