from __future__ import annotations

import os
import re
import time
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
import yaml
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
RAG_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "rag_config.yaml"
DEFAULT_QDRANT_URL = "http://127.0.0.1:6333"
DEFAULT_OLLAMA_API_BASE = "http://127.0.0.1:11434"
VECTOR_SIZE = 768
TOTAL_E2E_BUDGET_SECONDS = 180.0
GENERATION_OVERHEAD_SECONDS = 10.0
CITATION_RE = re.compile(r"\[[\w\d_#]+\]")
DISALLOWED_MARKET_EXAMPLE_RE = re.compile(
    r"\b(?:petr\d?|vale\d?|itub\d?|bbdc\d?|aapl|tsla)\b",
    re.IGNORECASE,
)
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
    collection_name = f"{TEMP_COLLECTION_PREFIX}{uuid4().hex[:8]}"
    embedding_metadata = _embedding_metadata_from_config()

    _assert_local_url(qdrant_url, "QDRANT_URL")
    _assert_local_url(ollama_base_url, "OLLAMA_API_BASE")
    _assert_local_url(llm_base_url, "QUIMERA_LLM_BASE_URL")
    await _skip_if_ollama_unreachable(ollama_base_url)
    await _skip_if_litellm_unreachable(llm_base_url, api_key)

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
        existing_collections = _skip_if_qdrant_unreachable(client, qdrant_url)
        assert collection_name != "openclaw_knowledge"
        assert collection_name not in existing_collections
        assert collection_name.startswith(TEMP_COLLECTION_PREFIX)
        store.ensure_collection()
        collection_created = True

        total_start = time.perf_counter()
        chunks, vectors, index_latency = await _embed_synthetic_corpus(
            embedder,
            embedding_metadata=embedding_metadata,
        )
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

        question = (
            "No Fundo Sintetico Alpha, qual regra controla renda variavel "
            "sintetica e liquidez?"
        )
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
        assert any(
            re.search(r"\[fundo_ficticio_alfa#\d+\]", message["content"])
            for message in result.messages
        )
        assert any("Inclua citacoes" in message["content"] for message in result.messages)
        assert len(result.answer) > 50, (
            f"Answer was too short. Got: {result.answer[:200]!r}"
        )
        assert CITATION_RE.search(result.answer), (
            f"Answer did not contain a citation marker. Got: {result.answer[:200]!r}"
        )
        assert _mentions_expected_concept(result.answer), (
            "Answer did not mention expected synthetic concept. "
            f"Got: {result.answer[:200]!r}"
        )
        assert not _mentions_disallowed_real_market_example(result.answer)
        assert result.latency_ms["generation_ms"] / 1000 < generation_budget
        assert total_elapsed < TOTAL_E2E_BUDGET_SECONDS

        for stored_chunk in chunks:
            _assert_embedding_metadata(
                stored_chunk.metadata,
                expected=embedding_metadata,
            )
        for retrieved_chunk in result.chunks_used:
            _assert_embedding_metadata(
                retrieved_chunk.payload,
                expected=embedding_metadata,
            )

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
                logger.warning(
                    "gw07_cleanup_failed collection={} error={}",
                    collection_name,
                    exc,
                )
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
    *,
    embedding_metadata: Mapping[str, Any],
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
                        **embedding_metadata,
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
            title="Fundo Sintetico Alpha",
            text=(
                "O Fundo Sintetico Alpha e um documento educacional inventado "
                "para validar recuperacao local. A regra principal afirma que "
                "renda variavel sintetica so pode receber novas alocacoes "
                "quando a reserva de liquidez simulada cobrir 12 meses de "
                "despesas projetadas. A regra existe apenas para testes e nao "
                "representa fundo real, carteira real ou recomendacao.\n\n"
                "A segunda regra do Fundo Sintetico Alpha descreve que renda "
                "variavel sintetica deve ser acompanhada por trilha de auditoria "
                "ficticia, limite de concentracao educacional e revisao mensal "
                "do comite simulado. O documento repete que todos os exemplos "
                "sao artificiais e que nenhum dado de investidor e usado.\n\n"
                "Em um evento hipotetico de estresse de liquidez, o Fundo "
                "Sintetico Alpha interrompe aportes em renda variavel sintetica, "
                "prioriza instrumentos simulados de menor prazo e registra a "
                "decisao com citacao do documento. Essa politica reforca a "
                "separacao entre teste tecnico e decisao financeira real.\n\n"
                "O anexo didatico do Fundo Sintetico Alpha explica que o "
                "assistente deve recuperar a regra de liquidez antes de gerar "
                "resposta. Se o contexto recuperado nao mencionar renda "
                "variavel sintetica, a resposta deve indicar insuficiencia de "
                "contexto. Se mencionar, a resposta deve citar a fonte no "
                "formato doc_id e chunk.\n\n"
                "Para fortalecer o teste de chunking, este paragrafo longo "
                "descreve uma rotina ficticia de acompanhamento semanal, "
                "validacao de limites, simulacao de caixa, revisao de premissas, "
                "registro de decisoes, comparacao com um plano educacional e "
                "controle de linguagem. A rotina nao contem nomes de empresas, "
                "nao contem codigos de negociacao, nao contem valores reais e "
                "nao descreve carteira verdadeira. Ela apenas fornece massa de "
                "texto para que o pipeline produza multiplos chunks, recupere "
                "contexto relevante e gere uma resposta citada usando o gateway "
                "local. A renda variavel sintetica aparece varias vezes porque "
                "e o conceito-alvo do smoke test, junto com a liquidez simulada "
                "de 12 meses. O texto tambem declara que risco, liquidez, "
                "concentracao, governanca ficticia e auditoria sintetica sao "
                "conceitos distintos dentro do corpus. Essa extensao garante "
                "que pelo menos um documento ultrapasse quatrocentos tokens em "
                "um formato totalmente artificial, inline e sem dependencia de "
                "arquivos privados.\n\n"
                "Um ultimo bloco de controle descreve uma ata simulada, uma "
                "fila ficticia de aprovacoes, uma justificativa educacional, "
                "um historico inventado de revisoes e um resumo sintetico de "
                "aprendizado. O bloco reforca que renda variavel sintetica "
                "depende de liquidez simulada, que a reserva de 12 meses e "
                "apenas uma regra didatica, que nenhum arquivo local privado "
                "foi lido e que a resposta deve permanecer presa ao contexto "
                "recuperado. Tambem adiciona termos de governanca sintetica, "
                "controle operacional ficticio e classificacao educacional "
                "para ampliar a superficie de recuperacao sem incluir dados "
                "reais."
            ),
        ),
        SyntheticDoc(
            doc_id="cenario_macro_sintetico",
            title="Cenario Macro Simulado",
            text=(
                "O Cenario Macro Simulado descreve uma economia inventada com "
                "juros educacionais, inflacao ficticia e crescimento abstrato. "
                "O objetivo e testar se o pipeline diferencia premissas de curto "
                "prazo, como pressao de custos simulada, de premissas de longo "
                "prazo, como produtividade teorica.\n\n"
                "O documento tambem compara renda fixa ficticia, renda variavel "
                "sintetica e caixa educacional sem citar empresas reais. Ele "
                "nao inclui tickers, nao inclui carteiras e nao inclui qualquer "
                "informacao privada."
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
                "por classe de ativo, incluindo renda variavel sintetica, e "
                "aciona revisao quando uma classe hipotetica domina a "
                "explicacao. A revisao deve ser registrada com o identificador "
                "do documento sintetico."
            ),
        ),
    ]


def _skip_if_qdrant_unreachable(client: QdrantClient, qdrant_url: str) -> set[str]:
    try:
        collections = client.get_collections().collections
    except Exception:  # noqa: BLE001
        pytest.skip(
            f"GW-07 E2E smoke skipped: Qdrant is not reachable at {qdrant_url}. "
            "Start the local Qdrant service before running live smoke."
        )
    names = {collection.name for collection in collections}
    logger.info(
        "gw07_qdrant_preflight | collections={} production_present={}",
        len(names),
        "openclaw_knowledge" in names,
    )
    return names


async def _skip_if_ollama_unreachable(base_url: str) -> None:
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
    except httpx.HTTPError:
        pytest.skip(
            f"GW-07 E2E smoke skipped: Ollama is not reachable at {base_url}. "
            "Start Ollama and pull nomic-embed-text before running live smoke."
        )


async def _skip_if_litellm_unreachable(base_url: str, api_key: str) -> None:
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
            response = await client.get(
                "/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            pytest.skip(
                "GW-07 E2E smoke skipped: LiteLLM authentication failed. "
                "QUIMERA_LLM_API_KEY must match the local LITELLM_MASTER_KEY."
            )
        pytest.skip(
            f"GW-07 E2E smoke skipped: LiteLLM /models returned HTTP "
            f"{exc.response.status_code} at {base_url}."
        )
    except httpx.HTTPError:
        pytest.skip(
            f"GW-07 E2E smoke skipped: LiteLLM is not reachable at {base_url}. "
            "Start infra/litellm/start_litellm.sh before running live smoke."
        )


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
    if missing:
        raise AssertionError(
            f"rag_config.yaml is missing embedding metadata fields: {sorted(missing)}"
        )

    assert metadata["embedding_provider"] == "ollama"
    assert metadata["embedding_model"] == "nomic-embed-text"
    assert metadata["embedding_dimensions"] == VECTOR_SIZE
    assert metadata["embedding_contract"] == "openai_compatible_v1_embeddings"
    assert metadata["embedding_alias"] == "quimera_embed"
    metadata["embedding_backend"] = "direct_ollama_current"
    return metadata


def _assert_embedding_metadata(
    payload: Mapping[str, Any],
    *,
    expected: Mapping[str, Any],
) -> None:
    assert payload["source_type"] == "synthetic"
    missing = REQUIRED_EMBEDDING_METADATA_FIELDS.difference(payload)
    assert not missing, f"payload missing embedding metadata fields: {sorted(missing)}"
    for field in REQUIRED_EMBEDDING_METADATA_FIELDS:
        assert payload[field] == expected[field]
    if "doc_id" in payload:
        assert str(payload["chunk_id"]).startswith(str(payload["doc_id"]))


def _mentions_expected_concept(answer: str) -> bool:
    normalized = _normalize_text(answer)
    return "renda variavel sintetica" in normalized


def _mentions_disallowed_real_market_example(answer: str) -> bool:
    return DISALLOWED_MARKET_EXAMPLE_RE.search(answer) is not None


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))
