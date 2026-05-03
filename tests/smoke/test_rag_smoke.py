from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient

from backend.rag.context_packer import ContextPacker, RetrievedChunk
from backend.rag.pipeline import LocalRagPipeline
from backend.rag.prompt_builder import PromptBuilder
from backend.rag.qdrant_store import QdrantVectorStore
from backend.rag.retriever import Retriever
from backend.rag.synthetic_documents import get_synthetic_documents
from scripts.rag_ask_local import print_result
from scripts.rag_ingest_synthetic import ingest_synthetic_documents


VECTOR_SIZE = 4
SCORE_THRESHOLD = 0.1
CITATION_RE = re.compile(r"\[[a-z_]+#\d+\]")


class KeywordEmbedder:
    async def embed(self, text: str) -> list[float]:
        return _vector_for_text(text)

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [_vector_for_text(text) for text in texts]


class SmokeGenerator:
    def __init__(self) -> None:
        self.seen_thinking_mode: bool | None = None
        self.seen_messages: Sequence[dict[str, str]] = []

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
        content = messages[-1]["content"]
        citations = CITATION_RE.findall(content)
        if not citations:
            return (
                "Nao ha contexto local suficiente para responder com seguranca. "
                "O pipeline continuou estavel mesmo sem chunks recuperados."
            )
        return (
            "Resposta sintetica local com base nos chunks recuperados pelo RAG. "
            f"A primeira evidencia aparece em {citations[0]} e a resposta "
            "mantem citacao explicita para auditoria do MVP."
        )


class EmptyRetriever:
    async def retrieve(
        self,
        question: str,
        top_k: int | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        return []


@pytest.fixture
def qdrant_store() -> Iterator[QdrantVectorStore]:
    collection = f"openclaw_smoke_{uuid4().hex}"
    client = QdrantClient(":memory:")
    store = QdrantVectorStore(
        collection_name=collection,
        vector_size=VECTOR_SIZE,
        client=client,
    )
    try:
        yield store
    finally:
        if client.collection_exists(collection):
            client.delete_collection(collection)
        client.close()


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_synthetic_rag_smoke_three_queries(
    qdrant_store: QdrantVectorStore,
) -> None:
    embedder = KeywordEmbedder()
    summary = await ingest_synthetic_documents(
        embedder=embedder,
        store=qdrant_store,
        max_tokens=50,
        overlap_tokens=8,
    )
    assert summary.total_chunks >= 5

    queries = [
        "Qual o impacto sintetico da Selic na renda fixa?",
        "Quando devo rebalancear uma alocacao sintetica?",
        "Quais riscos de concentracao aparecem no contexto?",
    ]
    retriever = Retriever(
        embedder=embedder,
        store=qdrant_store,
        packer=ContextPacker(max_context_tokens=400),
        top_k=3,
        score_threshold=SCORE_THRESHOLD,
    )
    generator = SmokeGenerator()
    pipeline = LocalRagPipeline(
        retriever=retriever,
        generator=generator,
        prompt_builder=PromptBuilder(),
    )

    for query in queries:
        result = await pipeline.ask(query, top_k=3)
        print_result(result, verbose=True)

        assert len(result.answer) > 50
        assert CITATION_RE.search(result.answer)
        assert result.chunks_used
        assert result.latency_ms["total_ms"] < 30_000
        assert all(chunk.score >= SCORE_THRESHOLD for chunk in result.chunks_used)


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_pipeline_thinking_mode_true_smoke(
    qdrant_store: QdrantVectorStore,
) -> None:
    embedder = KeywordEmbedder()
    await ingest_synthetic_documents(
        documents=[get_synthetic_documents()[0]],
        embedder=embedder,
        store=qdrant_store,
        max_tokens=60,
        overlap_tokens=8,
    )
    generator = SmokeGenerator()
    pipeline = LocalRagPipeline(
        retriever=Retriever(
            embedder=embedder,
            store=qdrant_store,
            packer=ContextPacker(max_context_tokens=200),
            score_threshold=SCORE_THRESHOLD,
        ),
        generator=generator,
        prompt_builder=PromptBuilder(),
        thinking_mode=True,
    )

    result = await pipeline.ask("Analise o cenario sintetico da Selic.", top_k=2)

    assert len(result.answer) > 50
    assert generator.seen_thinking_mode is True
    assert "/think" in generator.seen_messages[-1]["content"]
    assert result.chunks_used


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_pipeline_empty_retrieval_smoke() -> None:
    generator = SmokeGenerator()
    pipeline = LocalRagPipeline(
        retriever=EmptyRetriever(),
        generator=generator,
        prompt_builder=PromptBuilder(),
    )

    result = await pipeline.ask("Pergunta sem base local?")

    assert result.chunks_used == []
    assert "Nao ha contexto local suficiente" in result.answer
    assert result.latency_ms["total_ms"] >= 0.0


def _vector_for_text(text: str) -> list[float]:
    normalized = text.casefold()
    if "selic" in normalized or "renda fixa" in normalized:
        return [1.0, 0.0, 0.0, 0.0]
    if "rebalance" in normalized:
        return [0.0, 1.0, 0.0, 0.0]
    if "risco" in normalized or "concentracao" in normalized:
        return [0.0, 0.0, 1.0, 0.0]
    return [0.0, 0.0, 0.0, 1.0]
