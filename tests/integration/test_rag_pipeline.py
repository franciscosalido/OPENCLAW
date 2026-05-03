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
from backend.rag.synthetic_documents import SyntheticDocument
from scripts.rag_ingest_synthetic import ingest_synthetic_documents


VECTOR_SIZE = 4
CITATION_RE = re.compile(r"\[[a-z_]+#\d+\]")


class KeywordEmbedder:
    async def embed(self, text: str) -> list[float]:
        return _vector_for_text(text)

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [_vector_for_text(text) for text in texts]


class CitationGenerator:
    def __init__(self) -> None:
        self.seen_messages: Sequence[dict[str, str]] = []
        self.seen_thinking_mode: bool | None = None

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        temperature: float | None = None,
        thinking_mode: bool = False,
        max_tokens: int | None = None,
        keep_alive: str | None = None,
    ) -> str:
        del max_tokens, keep_alive
        self.seen_messages = messages
        self.seen_thinking_mode = thinking_mode
        user_content = messages[-1]["content"]
        citations = CITATION_RE.findall(user_content)
        if not citations:
            return (
                "Nao ha contexto local suficiente para responder com seguranca. "
                "Nenhum chunk foi recuperado para sustentar uma resposta."
            )
        return (
            "Resposta sintetica fundamentada no contexto local recuperado. "
            f"A evidencia principal esta em {citations[0]}, com suporte de "
            "chunks recuperados pelo Qdrant local."
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
    collection = f"openclaw_pipeline_{uuid4().hex}"
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_rag_pipeline_with_cleanup(
    qdrant_store: QdrantVectorStore,
) -> None:
    document = SyntheticDocument(
        doc_id="selic_integracao",
        title="Selic sintetica de integracao",
        text=(
            "Selic sintetica elevada favorece renda fixa local. "
            "Este documento nao contem carteira real nem dado privado.\n\n"
            "Rebalanceamento disciplinado reduz decisoes emocionais em um "
            "cenario de juros e risco variaveis."
        ),
    )
    embedder = KeywordEmbedder()

    summary = await ingest_synthetic_documents(
        documents=[document],
        embedder=embedder,
        store=qdrant_store,
        max_tokens=20,
        overlap_tokens=4,
    )
    assert summary.total_chunks >= 1
    assert qdrant_store.count() == summary.total_chunks

    retriever = Retriever(
        embedder=embedder,
        store=qdrant_store,
        packer=ContextPacker(max_context_tokens=100),
        top_k=3,
        score_threshold=0.1,
    )
    chunks = await retriever.retrieve("Como a Selic afeta renda fixa?")
    assert chunks
    assert chunks[0].score >= 0.1

    prompt = PromptBuilder().build("Como a Selic afeta renda fixa?", chunks)
    assert "[selic_integracao#" in prompt[-1]["content"]

    generator = CitationGenerator()
    pipeline = LocalRagPipeline(
        retriever=retriever,
        generator=generator,
        prompt_builder=PromptBuilder(),
    )
    result = await pipeline.ask("Como a Selic afeta renda fixa?", top_k=3)

    assert len(result.answer) > 50
    assert "[selic_integracao#" in result.answer
    assert result.chunks_used
    assert result.latency_ms["total_ms"] >= 0.0

    deleted = qdrant_store.delete_document(document.doc_id)
    assert deleted == summary.total_chunks
    assert qdrant_store.count() == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pipeline_empty_retrieval_and_thinking_mode() -> None:
    generator = CitationGenerator()
    pipeline = LocalRagPipeline(
        retriever=EmptyRetriever(),
        generator=generator,
        prompt_builder=PromptBuilder(),
        thinking_mode=True,
    )

    result = await pipeline.ask("Pergunta sem contexto local?")

    assert result.chunks_used == []
    assert "Nao ha contexto local suficiente" in result.answer
    assert generator.seen_thinking_mode is True
    assert "/think" in generator.seen_messages[-1]["content"]


def _vector_for_text(text: str) -> list[float]:
    normalized = text.casefold()
    if "selic" in normalized or "renda fixa" in normalized:
        return [1.0, 0.0, 0.0, 0.0]
    if "rebalance" in normalized:
        return [0.0, 1.0, 0.0, 0.0]
    if "risco" in normalized or "concentracao" in normalized:
        return [0.0, 0.0, 1.0, 0.0]
    return [0.0, 0.0, 0.0, 1.0]
