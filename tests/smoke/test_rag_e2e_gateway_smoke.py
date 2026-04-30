from __future__ import annotations

import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
import pytest
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.http import models

from backend.gateway.client import (
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_RAG_MODEL,
    GatewayRuntimeConfig,
)
from backend.rag.chunking import chunk_text
from backend.rag.context_packer import ContextPacker
from backend.rag.embeddings import OllamaEmbedder
from backend.rag.generator import LocalGenerator
from backend.rag.pipeline import LocalRagPipeline
from backend.rag.prompt_builder import PromptBuilder
from backend.rag.qdrant_store import QdrantVectorStore, VectorStoreChunk
from backend.rag.retriever import Retriever


pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("RUN_RAG_E2E_SMOKE") != "1",
        reason="set RUN_RAG_E2E_SMOKE=1 to run live synthetic RAG E2E smoke",
    ),
]

TEMP_COLLECTION_PREFIX = "gw07_synthetic_rag_"
DEFAULT_QDRANT_URL = "http://127.0.0.1:6333"
DEFAULT_OLLAMA_API_BASE = "http://127.0.0.1:11434"
VECTOR_SIZE = 768
TOTAL_E2E_BUDGET_SECONDS = 180.0
GENERATION_OVERHEAD_SECONDS = 10.0
CITATION_RE = re.compile(r"\[[a-z0-9_]+#\d+\]")
DISALLOWED_MARKET_EXAMPLE_RE = re.compile(
    r"\b(?:petr\d?|vale\d?|itub\d?|bbdc\d?|aapl|tsla)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SyntheticDoc:
    doc_id: str
    title: str
    text: str


@pytest.mark.asyncio
async def test_synthetic_rag_e2e_through_local_gateway() -> None:
    api_key = os.environ.get("QUIMERA_LLM_API_KEY")
    if not api_key:
        pytest.skip(
            "QUIMERA_LLM_API_KEY is required for live GW-07 RAG E2E smoke; "
            "it must match the local LiteLLM master key."
        )

    qdrant_url = os.environ.get("QDRANT_URL", DEFAULT_QDRANT_URL)
    ollama_base_url = os.environ.get("OLLAMA_API_BASE", DEFAULT_OLLAMA_API_BASE)
    llm_base_url = os.environ.get("QUIMERA_LLM_BASE_URL", DEFAULT_LLM_BASE_URL)
    generation_alias = os.environ.get("QUIMERA_LLM_RAG_MODEL", DEFAULT_LLM_RAG_MODEL)
    collection_name = f"{TEMP_COLLECTION_PREFIX}{uuid4().hex[:10]}"

    _assert_local_url(qdrant_url, "QDRANT_URL")
    _assert_local_url(ollama_base_url, "OLLAMA_API_BASE")
    _assert_local_url(llm_base_url, "QUIMERA_LLM_BASE_URL")
    await _assert_ollama_reachable(ollama_base_url)
    await _assert_litellm_reachable(llm_base_url, api_key)

    client = QdrantClient(url=qdrant_url)
    embedder = OllamaEmbedder(base_url=ollama_base_url)
    store = QdrantVectorStore(
        collection_name=collection_name,
        vector_size=VECTOR_SIZE,
        distance=models.Distance.COSINE,
        client=client,
    )
    collection_created = False
    cleanup_errors: list[str] = []

    try:
        _assert_qdrant_reachable(client)
        store.ensure_collection()
        collection_created = True

        total_start = time.perf_counter()
        chunks, vectors, index_latency = await _embed_synthetic_corpus(embedder)
        assert len(chunks) >= 5

        store.upsert(chunks, vectors)
        assert store.count() == len(chunks)

        retriever = Retriever(
            embedder=embedder,
            store=store,
            packer=ContextPacker(max_context_tokens=900),
            top_k=5,
            score_threshold=0.0,
        )
        generator = LocalGenerator(
            model=generation_alias,
            base_url=llm_base_url,
            api_key=api_key,
            temperature=0.0,
            max_tokens=512,
        )
        pipeline = LocalRagPipeline(
            retriever=retriever,
            generator=generator,
            prompt_builder=PromptBuilder(),
            temperature=0.0,
        )

        question = "Qual regra de liquidez aparece no Fundo Ficticio Alfa?"
        try:
            result = await pipeline.ask(question, top_k=5)
        finally:
            await generator.aclose()

        total_elapsed = time.perf_counter() - total_start
        generation_budget = (
            GatewayRuntimeConfig(
                base_url=llm_base_url,
                api_key=api_key,
                default_model=generation_alias,
            )
            .validated()
            .resolve_timeout(generation_alias)
            + GENERATION_OVERHEAD_SECONDS
        )

        assert result.chunks_used
        assert any(chunk.doc_id == "fundo_ficticio_alfa" for chunk in result.chunks_used)
        assert any("[fundo_ficticio_alfa#" in message["content"] for message in result.messages)
        assert any("Inclua citacoes" in message["content"] for message in result.messages)
        assert len(result.answer) > 50
        assert CITATION_RE.search(result.answer), result.answer
        assert _mentions_expected_concept(result.answer)
        assert not _mentions_disallowed_real_market_example(result.answer)
        assert result.latency_ms["generation_ms"] / 1000 < generation_budget
        assert total_elapsed < TOTAL_E2E_BUDGET_SECONDS

        for chunk in result.chunks_used:
            _assert_embedding_metadata(chunk.payload)

        logger.info(
            "gw07_rag_e2e | collection={} chunks={} used={} "
            "indexing_ms={:.1f} retrieval_ms={:.1f} generation_ms={:.1f} "
            "total_ms={:.1f}",
            collection_name,
            len(chunks),
            len(result.chunks_used),
            index_latency * 1000,
            result.latency_ms["retrieval_ms"],
            result.latency_ms["generation_ms"],
            result.latency_ms["total_ms"],
        )
    finally:
        if collection_created:
            try:
                _delete_temp_collection(client, collection_name)
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(f"{collection_name}: {exc}")
        await embedder.aclose()
        client.close()

    if cleanup_errors:
        pytest.fail(
            "Temporary Qdrant collection cleanup failed; remove only collections "
            f"with prefix {TEMP_COLLECTION_PREFIX!r}: {cleanup_errors}"
        )


async def _embed_synthetic_corpus(
    embedder: OllamaEmbedder,
) -> tuple[list[VectorStoreChunk], list[list[float]], float]:
    docs = _synthetic_docs()
    chunks: list[VectorStoreChunk] = []

    for document in docs:
        for chunk in chunk_text(document.text, max_tokens=55, overlap_tokens=12):
            chunks.append(
                VectorStoreChunk(
                    doc_id=document.doc_id,
                    chunk_index=chunk.index,
                    text=chunk.text,
                    metadata={
                        "chunk_id": f"{document.doc_id}#{chunk.index}",
                        "title": document.title,
                        "source_type": "synthetic",
                        "start_char": chunk.start_char,
                        "end_char": chunk.end_char,
                        "embedding_provider": "ollama",
                        "embedding_model": "nomic-embed-text",
                        "embedding_dimensions": VECTOR_SIZE,
                        "embedding_version": "local-ollama-current",
                        "embedding_contract": "openai_compatible_v1_embeddings",
                        "embedding_alias": "quimera_embed",
                        "embedding_backend": "direct_ollama_current",
                    },
                )
            )

    start = time.perf_counter()
    vectors = await embedder.embed_batch([chunk.text for chunk in chunks])
    return chunks, vectors, time.perf_counter() - start


def _synthetic_docs() -> list[SyntheticDoc]:
    return [
        SyntheticDoc(
            doc_id="fundo_ficticio_alfa",
            title="Fundo Ficticio Alfa",
            text=(
                "O Fundo Ficticio Alfa e um estudo educacional inventado para "
                "testes locais. Ele descreve uma regra de liquidez simulada: "
                "manter uma reserva operacional equivalente a 12 meses de "
                "despesas projetadas antes de ampliar exposicao a ativos de "
                "maior volatilidade.\n\n"
                "A politica sintetica do Fundo Ficticio Alfa tambem exige que "
                "qualquer aumento de risco seja acompanhado por justificativa "
                "documentada, limite de concentracao e revisao mensal pelo "
                "comite ficticio. Nenhum dado real de carteira e usado.\n\n"
                "Quando o cenario hipotetico indica estresse de liquidez, o "
                "fundo reduz novas alocacoes simuladas e prioriza instrumentos "
                "educacionais de menor prazo. Esta regra existe apenas para "
                "validar recuperacao e citacoes no pipeline RAG."
            ),
        ),
        SyntheticDoc(
            doc_id="cenario_macro_sintetico",
            title="Cenario Macro Sintetico Brasil",
            text=(
                "O Cenario Macro Sintetico Brasil apresenta uma narrativa "
                "ficticia sobre juros, inflacao e crescimento. O documento "
                "afirma que decisoes educacionais devem separar hipoteses de "
                "curto prazo, como inflacao persistente, de premissas de longo "
                "prazo, como produtividade e credito.\n\n"
                "Em um ambiente simulado de juros altos, o material recomenda "
                "testar a sensibilidade de renda fixa ficticia e fundos "
                "imobiliarios sinteticos, sempre sem usar nomes de empresas, "
                "codigos de negociacao ou carteiras reais."
            ),
        ),
        SyntheticDoc(
            doc_id="politica_risco_sintetica",
            title="Politica de Risco Sintetica",
            text=(
                "A Politica de Risco Sintetica define que toda resposta do "
                "assistente deve citar fontes recuperadas e evitar inferencias "
                "sem suporte. Ela tambem orienta que dados pessoais, credenciais "
                "e documentos privados nunca sejam usados em testes.\n\n"
                "Para concentracao, a politica ficticia usa limites didaticos "
                "por classe de ativo e aciona revisao quando uma classe "
                "hipotetica domina a explicacao. A revisao deve ser registrada "
                "com o identificador do documento sintetico."
            ),
        ),
    ]


def _assert_qdrant_reachable(client: QdrantClient) -> None:
    try:
        client.get_collections()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            "Qdrant is not reachable at QDRANT_URL. Start the local Qdrant "
            "service before running GW-07 live smoke."
        )


async def _assert_ollama_reachable(base_url: str) -> None:
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        pytest.fail(
            "Ollama is not reachable at OLLAMA_API_BASE. Start Ollama and pull "
            "nomic-embed-text before running GW-07 live smoke."
        )


async def _assert_litellm_reachable(base_url: str, api_key: str) -> None:
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
            response = await client.get(
                "/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            pytest.fail(
                "LiteLLM authentication failed. QUIMERA_LLM_API_KEY must match "
                "the local LITELLM_MASTER_KEY."
            )
        pytest.fail(
            "LiteLLM /models returned an error. Verify the local gateway and "
            "semantic aliases before running GW-07 live smoke."
        )
    except httpx.HTTPError:
        pytest.fail(
            "LiteLLM is not reachable at QUIMERA_LLM_BASE_URL. Start "
            "infra/litellm/start_litellm.sh before running GW-07 live smoke."
        )


def _assert_local_url(url: str, variable_name: str) -> None:
    if not (
        url.startswith("http://127.0.0.1:")
        or url.startswith("http://localhost:")
        or url.startswith("http://[::1]:")
    ):
        pytest.fail(f"{variable_name} must point to a local-only HTTP URL.")


def _delete_temp_collection(client: QdrantClient, collection_name: str) -> None:
    if not collection_name.startswith(TEMP_COLLECTION_PREFIX):
        raise ValueError(
            f"refusing to delete collection without {TEMP_COLLECTION_PREFIX!r} prefix"
        )
    if client.collection_exists(collection_name):
        client.delete_collection(collection_name)


def _assert_embedding_metadata(payload: Mapping[str, Any]) -> None:
    assert payload["source_type"] == "synthetic"
    assert payload["embedding_provider"] == "ollama"
    assert payload["embedding_model"] == "nomic-embed-text"
    assert payload["embedding_dimensions"] == VECTOR_SIZE
    assert payload["embedding_version"] == "local-ollama-current"
    assert payload["embedding_contract"] == "openai_compatible_v1_embeddings"
    assert payload["embedding_alias"] == "quimera_embed"
    assert payload["embedding_backend"] == "direct_ollama_current"
    assert str(payload["chunk_id"]).startswith(str(payload["doc_id"]))


def _mentions_expected_concept(answer: str) -> bool:
    normalized = answer.casefold()
    return "liquidez" in normalized or "12" in normalized


def _mentions_disallowed_real_market_example(answer: str) -> bool:
    return DISALLOWED_MARKET_EXAMPLE_RE.search(answer) is not None
