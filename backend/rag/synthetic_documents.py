"""Synthetic local-only documents for RAG-0 smoke tests and demos."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from backend.rag.chunking import Chunk, chunk_text
from backend.rag.qdrant_store import DEFAULT_SECURITY_LEVEL, VectorStoreChunk


@dataclass(frozen=True)
class SyntheticDocument:
    """A fictional document safe for local RAG ingestion."""

    doc_id: str
    title: str
    text: str
    source_type: str = "synthetic"
    security_level: str = DEFAULT_SECURITY_LEVEL
    metadata: Mapping[str, Any] = field(default_factory=dict)


def get_synthetic_documents() -> list[SyntheticDocument]:
    """Return the five fictional PT-BR documents used by RAG-0."""

    return [
        SyntheticDocument(
            doc_id="selic_projecao",
            title="Cenario sintetico de Selic 2026",
            text=(
                "Este documento sintetico descreve um cenario educacional para "
                "a Selic em 2026. A taxa basica pode permanecer elevada quando "
                "a inflacao esperada demora a convergir, o que aumenta a "
                "atratividade relativa da renda fixa pos-fixada. Em um ambiente "
                "de queda gradual da Selic, titulos prefixados e indexados a "
                "inflacao podem capturar ganhos de marcacao a mercado, mas "
                "continuam sujeitos a volatilidade.\n\n"
                "Para uma carteira ficticia e sem dados reais, o impacto mais "
                "importante e a comparacao entre carrego, prazo e risco. A "
                "decisao prudente exige separar reserva de liquidez, objetivos "
                "de medio prazo e capital de longo prazo. Este texto nao "
                "recomenda ativos, nao usa posicoes reais e serve apenas para "
                "testar recuperacao de contexto no OpenClaw."
            ),
        ),
        SyntheticDocument(
            doc_id="fiis_analise",
            title="Analise sintetica de FIIs",
            text=(
                "Este documento sintetico resume fatores de analise de fundos "
                "imobiliarios de logistica. O investidor pode observar vacancia, "
                "prazo medio dos contratos, qualidade dos inquilinos, localizacao "
                "dos galpoes e sensibilidade ao ciclo de juros. Dividend yield "
                "isolado nao e suficiente para avaliar risco.\n\n"
                "Em um cenario ficticio, FIIs tendem a sofrer quando juros reais "
                "sobem, pois a renda fixa passa a competir com os rendimentos "
                "distribuidos. Quando a Selic cai, o desconto exigido pelo "
                "mercado pode diminuir. O texto e sintetico, nao cita fundos "
                "reais e nao representa recomendacao de investimento."
            ),
        ),
        SyntheticDocument(
            doc_id="rebalanceamento",
            title="Rebalanceamento sintetico",
            text=(
                "Este documento sintetico apresenta uma regra educacional de "
                "rebalanceamento. Uma politica simples usa bandas de tolerancia: "
                "quando uma classe de ativo se afasta muito do alvo definido, a "
                "alocacao e trazida de volta ao plano. Isso reduz decisoes "
                "emocionais e evita concentracao acidental.\n\n"
                "A regra 5/25 e um exemplo didatico: classes maiores podem ser "
                "rebalanceadas quando desviam cinco pontos percentuais, enquanto "
                "classes menores usam um desvio relativo. O objetivo e manter "
                "disciplina, nao prever mercado. Nenhuma carteira real e usada."
            ),
        ),
        SyntheticDocument(
            doc_id="regime_macro",
            title="Regimes macro sinteticos",
            text=(
                "Este documento sintetico classifica regimes de mercado para "
                "testes de RAG. Em expansao, crescimento e lucros podem melhorar, "
                "favorecendo ativos de risco. Em contracao, liquidez e qualidade "
                "ganham importancia. Em crise, preservacao de capital e gestao "
                "de drawdown se tornam prioridades.\n\n"
                "A leitura de regime nao deve ser mecanica. Indicadores podem "
                "divergir e mudar rapidamente. Para o OpenClaw, este texto "
                "serve apenas como base ficticia para validar retrieval, "
                "citacoes e resposta fundamentada."
            ),
        ),
        SyntheticDocument(
            doc_id="risco_concentracao",
            title="Risco de concentracao sintetico",
            text=(
                "Este documento sintetico descreve risco de concentracao. Uma "
                "carteira pode parecer diversificada em quantidade de ativos, "
                "mas ainda estar exposta ao mesmo fator de risco, como juros, "
                "credito, liquidez ou setor economico. Correlacao aumenta em "
                "momentos de estresse.\n\n"
                "A mitigacao envolve limites por classe, emissor, setor e fator "
                "de risco, alem de revisao periodica. Drawdowns devem ser "
                "avaliados antes de aumentar exposicao. O conteudo e ficticio e "
                "nao contem patrimonio, saldo ou posicao real."
            ),
        ),
    ]


def vector_chunks_for_document(
    document: SyntheticDocument,
    max_tokens: int = 400,
    overlap_tokens: int = 80,
) -> list[VectorStoreChunk]:
    """Chunk one synthetic document into Qdrant-ready chunks."""

    chunks = chunk_text(
        document.text,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
    )
    return [
        _to_vector_store_chunk(document=document, chunk=chunk)
        for chunk in chunks
    ]


def _to_vector_store_chunk(
    document: SyntheticDocument,
    chunk: Chunk,
) -> VectorStoreChunk:
    metadata = {
        "title": document.title,
        "source_type": document.source_type,
        "start_char": chunk.start_char,
        "end_char": chunk.end_char,
    }
    metadata.update(dict(document.metadata))
    return VectorStoreChunk(
        doc_id=document.doc_id,
        chunk_index=chunk.index,
        text=chunk.text,
        security_level=document.security_level,
        metadata=metadata,
    )
