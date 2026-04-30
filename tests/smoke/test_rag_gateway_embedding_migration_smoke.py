from __future__ import annotations

import math
import os
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
import yaml
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.http import models

from backend.gateway.client import DEFAULT_LLM_BASE_URL, DEFAULT_LLM_RAG_MODEL
from backend.rag.chunking import chunk_text
from backend.rag.context_packer import ContextPacker
from backend.rag.embedder_factory import (
    BACKEND_GATEWAY_LITELLM,
    ENV_RAG_EMBEDDING_BACKEND,
    create_rag_embedder,
)
from backend.rag.embeddings import OllamaEmbedder
from backend.rag.generator import LocalGenerator
from backend.rag.pipeline import LocalRagPipeline
from backend.rag.prompt_builder import PromptBuilder
from backend.rag.qdrant_store import QdrantVectorStore, VectorStoreChunk
from backend.rag.retriever import Retriever


TEMP_COLLECTION_PREFIX = "gw08_embedding_migration_"
RAG_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "rag_config.yaml"
DEFAULT_QDRANT_URL = "http://127.0.0.1:6333"
DEFAULT_OLLAMA_API_BASE = "http://127.0.0.1:11434"
VECTOR_SIZE = 768
CITATION_RE = re.compile(r"\[[\w\d_#]+\]")
REQUIRED_EMBEDDING_METADATA_FIELDS = frozenset(
    {
        "embedding_provider",
        "embedding_model",
        "embedding_dimensions",
        "embedding_version",
        "embedding_contract",
        "embedding_alias",
        "embedding_backend",
    }
)


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_gw08_gateway_embedding_migration_e2e() -> None:
    if os.environ.get("RUN_GW08_EMBEDDING_MIGRATION_SMOKE") != "1":
        pytest.skip("set RUN_GW08_EMBEDDING_MIGRATION_SMOKE=1 to run GW-08 smoke")

    api_key = _required_api_key()
    qdrant_url = os.environ.get("QDRANT_URL", DEFAULT_QDRANT_URL)
    ollama_base_url = os.environ.get("OLLAMA_API_BASE", DEFAULT_OLLAMA_API_BASE)
    llm_base_url = os.environ.get("QUIMERA_LLM_BASE_URL", DEFAULT_LLM_BASE_URL)
    generation_alias = os.environ.get("QUIMERA_LLM_RAG_MODEL", DEFAULT_LLM_RAG_MODEL)
    collection_name = f"{TEMP_COLLECTION_PREFIX}{uuid4().hex[:8]}"
    embedding_metadata = _embedding_metadata_from_config()

    _assert_local_url(qdrant_url, "QDRANT_URL")
    _assert_local_url(ollama_base_url, "OLLAMA_API_BASE")
    _assert_local_url(llm_base_url, "QUIMERA_LLM_BASE_URL")
    await _skip_if_ollama_unreachable(ollama_base_url)
    await _skip_if_litellm_unreachable(llm_base_url, api_key)

    client = QdrantClient(url=qdrant_url)
    embedder = create_rag_embedder(
        env={
            "QUIMERA_LLM_API_KEY": api_key,
            "QUIMERA_LLM_BASE_URL": llm_base_url,
            ENV_RAG_EMBEDDING_BACKEND: BACKEND_GATEWAY_LITELLM,
        }
    )
    store = QdrantVectorStore(
        collection_name=collection_name,
        vector_size=VECTOR_SIZE,
        distance=models.Distance.COSINE,
        client=client,
    )
    collection_created = False

    try:
        existing_collections = _skip_if_qdrant_unreachable(client, qdrant_url)
        assert collection_name != "openclaw_knowledge"
        assert collection_name not in existing_collections
        store.ensure_collection()
        collection_created = True

        chunks = _chunks_for_synthetic_corpus(embedding_metadata)
        start = time.perf_counter()
        vectors = await embedder.embed_batch([chunk.text for chunk in chunks])
        indexing_ms = (time.perf_counter() - start) * 1000
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

        try:
            result = await pipeline.ask(
                "Qual regra controla reserva sintetica de emergencia?",
                top_k=5,
            )
        finally:
            await generator.aclose()

        assert len(result.answer) > 50, result.answer[:200]
        assert CITATION_RE.search(result.answer), result.answer[:200]
        assert "reserva sintetica de emergencia" in _normalize(result.answer), (
            result.answer[:200]
        )
        assert result.chunks_used
        for retrieved_chunk in result.chunks_used:
            _assert_embedding_metadata(
                retrieved_chunk.payload,
                expected=embedding_metadata,
            )

        logger.info(
            "gw08_embedding_migration | collection={} chunks={} used={} "
            "indexing_ms={:.1f} total_ms={:.1f}",
            collection_name,
            len(chunks),
            len(result.chunks_used),
            indexing_ms,
            result.latency_ms["total_ms"],
        )
    finally:
        if collection_created:
            try:
                _delete_temp_collection(client, collection_name)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "gw08_cleanup_failed collection={} error={}",
                    collection_name,
                    exc,
                )
        await _maybe_close(embedder)
        client.close()


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_gw08_gateway_embedding_parity_with_direct_ollama() -> None:
    if os.environ.get("RUN_GW08_EMBEDDING_PARITY_SMOKE") != "1":
        pytest.skip("set RUN_GW08_EMBEDDING_PARITY_SMOKE=1 to run parity smoke")

    api_key = _required_api_key()
    ollama_base_url = os.environ.get("OLLAMA_API_BASE", DEFAULT_OLLAMA_API_BASE)
    llm_base_url = os.environ.get("QUIMERA_LLM_BASE_URL", DEFAULT_LLM_BASE_URL)
    _assert_local_url(ollama_base_url, "OLLAMA_API_BASE")
    _assert_local_url(llm_base_url, "QUIMERA_LLM_BASE_URL")
    await _skip_if_ollama_unreachable(ollama_base_url)
    await _skip_if_litellm_unreachable(llm_base_url, api_key)

    synthetic_text = (
        "Texto sintetico de paridade sobre reserva sintetica de emergencia "
        "e renda variavel educacional."
    )
    direct = OllamaEmbedder(base_url=ollama_base_url)
    gateway = create_rag_embedder(
        env={
            "QUIMERA_LLM_API_KEY": api_key,
            "QUIMERA_LLM_BASE_URL": llm_base_url,
            ENV_RAG_EMBEDDING_BACKEND: BACKEND_GATEWAY_LITELLM,
        }
    )
    try:
        direct_vector = await direct.embed(synthetic_text)
        gateway_vector = await gateway.embed(synthetic_text)
        batch = await gateway.embed_batch([synthetic_text, synthetic_text])
    finally:
        await direct.aclose()
        await _maybe_close(gateway)

    _assert_vector(direct_vector, label="direct_ollama")
    _assert_vector(gateway_vector, label="gateway_litellm")
    assert len(batch) == 2
    for vector in batch:
        _assert_vector(vector, label="gateway_litellm_batch")

    cosine = _cosine_similarity(direct_vector, gateway_vector)
    logger.info(
        "gw08_embedding_parity | cosine_similarity={:.6f} dims={}",
        cosine,
        len(gateway_vector),
    )
    assert cosine >= 0.9999


def _chunks_for_synthetic_corpus(
    embedding_metadata: Mapping[str, Any],
) -> list[VectorStoreChunk]:
    docs = {
        "reserva_sintetica": (
            "Reserva Sintetica de Emergencia",
            "A Reserva Sintetica de Emergencia e um conceito ficticio criado "
            "para validar a migracao controlada de embeddings. A regra central "
            "afirma que qualquer alocacao educacional deve preservar uma "
            "reserva sintetica de emergencia antes de ampliar risco simulado. "
            "O texto nao contem documentos reais, empresas reais, tickers ou "
            "carteiras reais.\n\n"
            "A reserva sintetica de emergencia tambem define que respostas "
            "devem citar chunks recuperados e nunca misturar vetores de "
            "backends diferentes na mesma colecao temporaria.",
        ),
        "politica_migracao": (
            "Politica de Migracao Sintetica",
            "A Politica de Migracao Sintetica registra que quimera_embed e o "
            "alias canonico para novos testes controlados. O backend atual e "
            "gateway_litellm_current, com rollback para direct_ollama quando "
            "necessario. A colecao temporaria deve ser apagada ao final.",
        ),
        "controle_vetorial": (
            "Controle Vetorial Ficticio",
            "O Controle Vetorial Ficticio exige dimensao 768, modelo concreto "
            "nomic-embed-text e contrato openai_compatible_v1_embeddings. "
            "Ele existe apenas para garantir metadata auditavel em testes.",
        ),
    }
    chunks: list[VectorStoreChunk] = []
    for doc_id, (title, text) in docs.items():
        for chunk in chunk_text(text, max_tokens=60, overlap_tokens=12):
            chunks.append(
                VectorStoreChunk(
                    doc_id=doc_id,
                    chunk_index=chunk.index,
                    text=chunk.text,
                    metadata={
                        "chunk_id": f"{doc_id}#{chunk.index}",
                        "title": title,
                        "source_type": "synthetic",
                        **embedding_metadata,
                    },
                )
            )
    return chunks


def _embedding_metadata_from_config() -> dict[str, Any]:
    raw = yaml.safe_load(RAG_CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise TypeError("rag_config.yaml must contain a mapping")
    rag = raw.get("rag")
    if not isinstance(rag, Mapping):
        raise TypeError("rag_config.yaml must contain rag mapping")
    embedding = rag.get("embedding")
    if not isinstance(embedding, Mapping):
        raise TypeError("rag_config.yaml must contain rag.embedding mapping")
    metadata = {
        field: embedding[field]
        for field in REQUIRED_EMBEDDING_METADATA_FIELDS
        if field in embedding
    }
    missing = REQUIRED_EMBEDDING_METADATA_FIELDS.difference(metadata)
    assert not missing
    assert metadata["embedding_alias"] == "quimera_embed"
    assert metadata["embedding_backend"] == "gateway_litellm_current"
    assert metadata["embedding_model"] == "nomic-embed-text"
    assert metadata["embedding_dimensions"] == VECTOR_SIZE
    return metadata


def _assert_embedding_metadata(
    payload: Mapping[str, Any],
    *,
    expected: Mapping[str, Any],
) -> None:
    assert payload["source_type"] == "synthetic"
    missing = REQUIRED_EMBEDDING_METADATA_FIELDS.difference(payload)
    assert not missing
    for field in REQUIRED_EMBEDDING_METADATA_FIELDS:
        assert payload[field] == expected[field]


def _required_api_key() -> str:
    api_key = os.environ.get("QUIMERA_LLM_API_KEY")
    if not api_key:
        pytest.skip("QUIMERA_LLM_API_KEY is required for GW-08 live smoke")
    return api_key


def _skip_if_qdrant_unreachable(client: QdrantClient, qdrant_url: str) -> set[str]:
    try:
        collections = client.get_collections().collections
    except Exception:  # noqa: BLE001
        pytest.skip(f"GW-08 smoke skipped: Qdrant is not reachable at {qdrant_url}")
    return {collection.name for collection in collections}


async def _skip_if_ollama_unreachable(base_url: str) -> None:
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
    except httpx.HTTPError:
        pytest.skip(f"GW-08 smoke skipped: Ollama is not reachable at {base_url}")


async def _skip_if_litellm_unreachable(base_url: str, api_key: str) -> None:
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
            response = await client.get(
                "/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
    except httpx.HTTPError:
        pytest.skip(f"GW-08 smoke skipped: LiteLLM is not reachable at {base_url}")


def _assert_local_url(url: str, variable_name: str) -> None:
    if not (
        url.startswith("http://127.0.0.1:")
        or url.startswith("http://localhost:")
        or url.startswith("http://[::1]:")
    ):
        pytest.fail(f"{variable_name} must point to a local-only HTTP URL.")


def _delete_temp_collection(client: QdrantClient, collection_name: str) -> None:
    assert collection_name.startswith(TEMP_COLLECTION_PREFIX), (
        f"Refusing to delete collection {collection_name!r} - prefix guard failed"
    )
    if client.collection_exists(collection_name):
        client.delete_collection(collection_name)


async def _maybe_close(embedder: object) -> None:
    close = getattr(embedder, "aclose", None)
    if close is not None:
        await close()


def _assert_vector(vector: Sequence[float], *, label: str) -> None:
    assert len(vector) == VECTOR_SIZE, f"{label} returned {len(vector)} dimensions"
    assert all(isinstance(value, float) for value in vector)


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _normalize(value: str) -> str:
    return value.casefold()
