"""End-to-end hybrid RAG smoke test with a temporary Qdrant collection.

This test is opt-in and intentionally small. It proves the full controlled
pipeline with synthetic Brazilian-finance documents:

document -> chunks -> dense+sparse vectors -> Qdrant named vectors ->
AsyncHybridRetriever -> Python-side RRFFusion -> citable result.

No Qdrant client is created at module import time.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import re
import unicodedata
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pytest

from backend.rag.hybrid_retriever import (
    AsyncHybridRetriever,
    HybridRetrieverConfig,
    SearchHit,
)
from backend.rag.sparse_vector import SparseVector as RetrieverSparseVector
from scripts.rag_ingest_hybrid import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_PROVIDER,
    DEFAULT_EMBEDDING_VERSION,
    DENSE_VECTOR_NAME,
    HYBRID_COLLECTION_NAME,
    LEGACY_COLLECTION_NAME,
    SCHEMA_VERSION,
    SPARSE_VECTOR_NAME,
    Document,
    HybridIngestPoint,
    chunk_document,
    prepare_hybrid_points,
    upload_hybrid_points,
)

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.getenv("RUN_HYBRID_SMOKE") != "1",
        reason="set RUN_HYBRID_SMOKE=1 to run hybrid RAG smoke test",
    ),
]

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
SMOKE_COLLECTION_PREFIX = "quimera_hybrid_smoke_"
SETUP_TIMEOUT_S = 10.0
UPSERT_TIMEOUT_S = 15.0
QUERY_TIMEOUT_S = 30.0
CLEANUP_TIMEOUT_S = 10.0

FORBIDDEN_RESULT_PAYLOAD_KEYS = {
    "dense_vector",
    "sparse_vector",
    "vector",
    "embedding",
    "embeddings",
    "prompt",
    "answer",
}

FORBIDDEN_TRACE_KEYS = {
    "query",
    "text",
    "chunk_text",
    "vector",
    "embedding",
    "prompt",
    "answer",
}

_TOKEN_TO_INDEX: dict[str, int] = {
    "mxrf11": 101,
    "fii": 102,
    "papel": 103,
    "cri": 104,
    "high": 105,
    "grade": 106,
    "renda": 107,
    "mensal": 108,
    "dividend": 109,
    "yield": 110,
    "selic": 111,
    "tesouro": 112,
    "taxa": 113,
    "liquidez": 114,
    "diaria": 115,
    "reserva": 116,
    "emergencia": 117,
    "baixo": 118,
    "risco": 119,
    "cdi": 120,
    "ipca": 121,
    "prefixado": 122,
    "duration": 123,
    "longa": 124,
    "marcacao": 125,
    "mercado": 126,
    "alta": 127,
    "juros": 128,
    "preco": 129,
    "cai": 130,
    "curto": 131,
    "prazo": 132,
}


def _qdrant_client_types() -> tuple[type[Any], Any]:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.http import models

    return AsyncQdrantClient, models


def _make_smoke_collection_name() -> str:
    return f"{SMOKE_COLLECTION_PREFIX}{uuid.uuid4().hex[:12]}"


def _assert_smoke_collection_name(name: str) -> str:
    if not isinstance(name, str):
        raise TypeError("collection name must be a string")
    if "\x00" in name:
        raise ValueError("collection name cannot contain null bytes")
    clean = name.strip()
    if not clean:
        raise ValueError("collection name cannot be empty")
    if clean in {LEGACY_COLLECTION_NAME, HYBRID_COLLECTION_NAME}:
        raise ValueError("protected collection cannot be used as smoke collection")
    if not clean.startswith(SMOKE_COLLECTION_PREFIX):
        raise ValueError("smoke collection name must use the smoke prefix")
    return clean


async def _safe_delete_smoke_collection(client: Any, collection_name: str) -> None:
    clean_name = _assert_smoke_collection_name(collection_name)
    if await client.collection_exists(clean_name):
        await asyncio.wait_for(
            client.delete_collection(collection_name=clean_name),
            timeout=CLEANUP_TIMEOUT_S,
        )


async def _qdrant_available(client: Any) -> bool:
    try:
        await asyncio.wait_for(client.get_collections(), timeout=SETUP_TIMEOUT_S)
    except Exception:
        return False
    return True


async def _create_smoke_hybrid_collection(client: Any, collection_name: str) -> None:
    clean_name = _assert_smoke_collection_name(collection_name)
    _client_type, models = _qdrant_client_types()
    await asyncio.wait_for(
        client.create_collection(
            collection_name=clean_name,
            vectors_config={
                DENSE_VECTOR_NAME: models.VectorParams(
                    size=DEFAULT_EMBEDDING_DIMENSIONS,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: models.SparseVectorParams(),
            },
        ),
        timeout=SETUP_TIMEOUT_S,
    )


async def _assert_hybrid_collection_ready(client: Any, collection_name: str) -> None:
    clean_name = _assert_smoke_collection_name(collection_name)
    collection = await asyncio.wait_for(
        client.get_collection(collection_name=clean_name),
        timeout=SETUP_TIMEOUT_S,
    )
    config = collection.config.params
    vectors = config.vectors
    sparse_vectors = config.sparse_vectors

    assert isinstance(vectors, Mapping)
    assert DENSE_VECTOR_NAME in vectors
    assert vectors[DENSE_VECTOR_NAME].size == DEFAULT_EMBEDDING_DIMENSIONS
    _client_type, models = _qdrant_client_types()
    assert vectors[DENSE_VECTOR_NAME].distance == models.Distance.COSINE
    assert isinstance(sparse_vectors, Mapping)
    assert SPARSE_VECTOR_NAME in sparse_vectors
    assert DENSE_VECTOR_NAME != SPARSE_VECTOR_NAME


async def _legacy_snapshot(client: Any) -> frozenset[str]:
    collections = await asyncio.wait_for(client.get_collections(), timeout=SETUP_TIMEOUT_S)
    return frozenset(collection.name for collection in collections.collections)


def _assert_legacy_untouched(before: frozenset[str], after: frozenset[str]) -> None:
    assert LEGACY_COLLECTION_NAME not in after - before
    if LEGACY_COLLECTION_NAME in before:
        assert LEGACY_COLLECTION_NAME in after
    if HYBRID_COLLECTION_NAME in before:
        assert HYBRID_COLLECTION_NAME in after


def _synthetic_financial_documents() -> list[Document]:
    return [
        Document(
            doc_id="smoke-fii-mxrf11",
            source="synthetic",
            text=(
                "MXRF11 é um FII de papel em exemplo controlado. "
                "A carteira sintética possui CRI high grade, busca renda mensal "
                "e discute dividend yield em cenário de Selic alta. "
                "Este é conteúdo sintético para teste."
            ),
        ),
        Document(
            doc_id="smoke-tesouro-selic",
            source="synthetic",
            text=(
                "Tesouro Selic acompanha a taxa Selic e aparece em exemplos de "
                "liquidez diária para reserva de emergência. O material sintético "
                "compara baixo risco, CDI e caixa conservador. "
                "Este é conteúdo sintético para teste."
            ),
        ),
        Document(
            doc_id="smoke-marcacao-prefixado-ipca",
            source="synthetic",
            text=(
                "Tesouro IPCA+ e Tesouro Prefixado com duration longa sofrem "
                "marcação a mercado. Em alta de juros, o preço cai no curto prazo. "
                "Este é conteúdo sintético para teste."
            ),
        ),
    ]


def test_synthetic_corpus_has_no_real_data_markers() -> None:
    forbidden = {"cpf", "cnpj", "conta", "carteira", "patrimônio", "posicao real", "posição real"}
    corpus_text = " ".join(document.text.casefold() for document in _synthetic_financial_documents())
    assert forbidden.isdisjoint(corpus_text)


def test_safe_delete_rejects_dangerous_collection_names() -> None:
    for name in ("", "bad\x00name", LEGACY_COLLECTION_NAME, HYBRID_COLLECTION_NAME, "not_a_smoke_collection"):
        with pytest.raises((TypeError, ValueError)):
            _assert_smoke_collection_name(name)


def _normalise_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _normalise_text(text))


def _token_index(token: str) -> int:
    known = _TOKEN_TO_INDEX.get(token)
    if known is not None:
        return known
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return 10_000 + (int(digest[:8], 16) % 50_000)


class SmokeDenseEmbedder:
    """Deterministic local dense embedder for smoke infrastructure only."""

    def __init__(self, dim: int = DEFAULT_EMBEDDING_DIMENSIONS) -> None:
        self._dim = dim

    async def embed(self, text: str) -> list[float]:
        values = [0.0] * self._dim
        for token in _tokens(text):
            slot = _token_index(token) % self._dim
            values[slot] += 1.0
        norm = math.sqrt(sum(value * value for value in values))
        if norm == 0.0:
            return values
        return [value / norm for value in values]


class SmokeSparseEmbedder:
    """Deterministic lexical sparse embedder for smoke infrastructure only."""

    async def embed(self, text: str) -> RetrieverSparseVector:
        weights: dict[int, float] = {}
        for token in _tokens(text):
            index = _token_index(token)
            weights[index] = weights.get(index, 0.0) + 1.0
        ordered = sorted(weights.items())
        return RetrieverSparseVector(
            indices=tuple(index for index, _value in ordered),
            values=tuple(value for _index, value in ordered),
        )


class SmokeQdrantUpsertClient:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def upsert_points(
        self,
        *,
        collection_name: str,
        points: Sequence[HybridIngestPoint],
    ) -> None:
        _client_type, models = _qdrant_client_types()
        qdrant_points = [
            models.PointStruct(
                id=point.point_id,
                vector={
                    DENSE_VECTOR_NAME: list(point.dense_vector),
                    SPARSE_VECTOR_NAME: models.SparseVector(
                        indices=list(point.sparse_indices),
                        values=list(point.sparse_values),
                    ),
                },
                payload=dict(point.payload),
            )
            for point in points
        ]
        await self._client.upsert(
            collection_name=collection_name,
            points=qdrant_points,
            wait=True,
        )


class SmokeDenseSearcher:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def search_dense(
        self,
        *,
        collection_name: str,
        vector_name: str,
        vector: list[float],
        limit: int,
        min_score: float | None = None,
    ) -> Sequence[SearchHit]:
        response = await self._client.query_points(
            collection_name=collection_name,
            query=vector,
            using=vector_name,
            limit=limit,
            score_threshold=min_score,
            with_payload=True,
        )
        return [_scored_point_to_search_hit(point) for point in response.points]


class SmokeSparseSearcher:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def search_sparse(
        self,
        *,
        collection_name: str,
        vector_name: str,
        vector: RetrieverSparseVector,
        limit: int,
        min_score: float | None = None,
    ) -> Sequence[SearchHit]:
        _client_type, models = _qdrant_client_types()
        response = await self._client.query_points(
            collection_name=collection_name,
            query=models.SparseVector(
                indices=list(vector.indices),
                values=list(vector.values),
            ),
            using=vector_name,
            limit=limit,
            score_threshold=min_score,
            with_payload=True,
        )
        return [_scored_point_to_search_hit(point) for point in response.points]


def _scored_point_to_search_hit(point: Any) -> SearchHit:
    payload = point.payload if isinstance(point.payload, Mapping) else {}
    return SearchHit(
        result_id=str(point.id),
        score=float(point.score),
        payload=dict(payload),
    )


def _retriever_sparse_to_ingest_sparse(vector: RetrieverSparseVector) -> Any:
    from scripts.rag_ingest_hybrid import SparseVector as IngestSparseVector

    return IngestSparseVector(indices=tuple(vector.indices), values=tuple(vector.values))


async def _prepare_and_upload_documents(client: Any, collection_name: str) -> None:
    documents = _synthetic_financial_documents()
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    dense_embedder = SmokeDenseEmbedder()
    sparse_embedder = SmokeSparseEmbedder()
    dense_vectors = [await dense_embedder.embed(chunk.text) for chunk in chunks]
    sparse_vectors = [
        _retriever_sparse_to_ingest_sparse(await sparse_embedder.embed(chunk.text))
        for chunk in chunks
    ]
    points = prepare_hybrid_points(
        chunks=chunks,
        dense_vectors=dense_vectors,
        sparse_vectors=sparse_vectors,
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
        embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
        embedding_version=DEFAULT_EMBEDDING_VERSION,
    )
    sent, _batches, _upload_ms = await asyncio.wait_for(
        upload_hybrid_points(
            client=SmokeQdrantUpsertClient(client),
            collection_name=collection_name,
            points=points,
            batch_size=8,
            dry_run=False,
            clock=_PerfClock(),
        ),
        timeout=UPSERT_TIMEOUT_S,
    )
    assert sent == len(points)
    assert len(points) >= len(documents)


@dataclass(frozen=True)
class _PerfClock:
    def perf_counter(self) -> float:
        return asyncio.get_running_loop().time()


def _assert_required_metadata(payload: Mapping[str, object]) -> None:
    required = {
        "doc_id",
        "chunk_id",
        "chunk_index",
        "source",
        "embedding_model",
        "embedding_provider",
        "embedding_dimensions",
        "embedding_version",
        "dense_vector_name",
        "sparse_vector_name",
        "schema_version",
    }
    assert required <= set(payload)
    assert payload["source"] == "synthetic"
    assert payload["embedding_model"] == DEFAULT_EMBEDDING_MODEL
    assert payload["embedding_provider"] == DEFAULT_EMBEDDING_PROVIDER
    assert payload["embedding_dimensions"] == DEFAULT_EMBEDDING_DIMENSIONS
    assert payload["embedding_version"] == DEFAULT_EMBEDDING_VERSION
    assert payload["dense_vector_name"] == DENSE_VECTOR_NAME
    assert payload["sparse_vector_name"] == SPARSE_VECTOR_NAME
    assert payload["schema_version"] == SCHEMA_VERSION
    assert FORBIDDEN_RESULT_PAYLOAD_KEYS.isdisjoint(payload)


def _assert_trace_is_safe(trace: Mapping[str, object]) -> None:
    search_ms = _number_from_trace(trace, "search_ms")
    total_ms = _number_from_trace(trace, "total_ms")
    dense_candidates = _int_from_trace(trace, "dense_candidates")
    sparse_candidates = _int_from_trace(trace, "sparse_candidates")
    fused_count = _int_from_trace(trace, "fused_count")
    returned_count = _int_from_trace(trace, "returned_count")

    assert search_ms >= 0.0
    assert total_ms >= 0.0
    assert dense_candidates >= 0
    assert sparse_candidates >= 0
    assert fused_count >= returned_count
    assert returned_count >= 1
    assert FORBIDDEN_TRACE_KEYS.isdisjoint(trace)


def _number_from_trace(trace: Mapping[str, object], key: str) -> float:
    value = trace[key]
    assert isinstance(value, (int, float))
    return float(value)


def _int_from_trace(trace: Mapping[str, object], key: str) -> int:
    value = trace[key]
    assert isinstance(value, int)
    return value


async def test_hybrid_rag_smoke_end_to_end() -> None:
    AsyncQdrantClient, _models = _qdrant_client_types()
    client = AsyncQdrantClient(url=QDRANT_URL)
    collection_name = _make_smoke_collection_name()
    before: frozenset[str] | None = None

    try:
        if not await _qdrant_available(client):
            pytest.skip(f"Qdrant is not available at {QDRANT_URL}")

        before = await _legacy_snapshot(client)
        await _create_smoke_hybrid_collection(client, collection_name)
        await _assert_hybrid_collection_ready(client, collection_name)
        during = await _legacy_snapshot(client)
        assert during - before == {collection_name}

        await _prepare_and_upload_documents(client, collection_name)

        retriever = AsyncHybridRetriever(
            dense_embedder=SmokeDenseEmbedder(),
            sparse_embedder=SmokeSparseEmbedder(),
            dense_searcher=SmokeDenseSearcher(client),
            sparse_searcher=SmokeSparseSearcher(client),
            config=HybridRetrieverConfig(
                collection_name=collection_name,
                dense_vector_name=DENSE_VECTOR_NAME,
                sparse_vector_name=SPARSE_VECTOR_NAME,
                search_top_k=5,
                return_top_k=5,
                embed_timeout_s=QUERY_TIMEOUT_S,
                search_timeout_s=QUERY_TIMEOUT_S,
            ),
        )

        result = await asyncio.wait_for(
            retriever.retrieve(
                "qual documento fala sobre dividend yield de FII de papel "
                "com CRI high grade em cenário de Selic alta?"
            ),
            timeout=QUERY_TIMEOUT_S,
        )

        assert result.results
        assert result.trace.returned_count >= 1
        by_doc_id = {item.doc_id: item for item in result.results}
        assert "smoke-fii-mxrf11" in by_doc_id

        expected = by_doc_id["smoke-fii-mxrf11"]
        assert expected.result_id
        assert expected.doc_id
        assert expected.rrf_score > 0
        assert expected.sources
        assert expected.dense_rank is not None or expected.sparse_rank is not None

        payload = expected.payload
        _assert_required_metadata(payload)
        assert payload["doc_id"] == "smoke-fii-mxrf11"
        assert payload["chunk_id"] == expected.result_id

        citation = {
            "doc_id": payload["doc_id"],
            "chunk_id": payload["chunk_id"],
            "chunk_index": payload["chunk_index"],
            "source": payload["source"],
        }
        assert citation == {
            "doc_id": "smoke-fii-mxrf11",
            "chunk_id": expected.result_id,
            "chunk_index": 0,
            "source": "synthetic",
        }

        _assert_trace_is_safe(result.trace.to_dict())

    except asyncio.TimeoutError as exc:
        pytest.fail(f"hybrid smoke timed out after setup: {exc.__class__.__name__}")
    finally:
        if await _qdrant_available(client):
            await _safe_delete_smoke_collection(client, collection_name)
            after = await _legacy_snapshot(client)
            if before is not None:
                _assert_legacy_untouched(before, after)
                assert collection_name not in after
        await client.close()
