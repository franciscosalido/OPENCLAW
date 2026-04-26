#!/usr/bin/env python
"""Ask a question through the local RAG pipeline.

Usage:
    python scripts/rag_ask_local.py "Qual a projeção da Selic para 2026?"
    python scripts/rag_ask_local.py "Quando devo rebalancear?" --top-k 3
    python scripts/rag_ask_local.py "Riscos de concentração" --thinking
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping
from typing import Any

from backend.rag.context_packer import ContextPacker
from backend.rag.embeddings import OllamaEmbedder
from backend.rag.generator import DEFAULT_GENERATION_MODEL, LocalGenerator
from backend.rag.health import check_local_services
from backend.rag.pipeline import LocalRagPipeline, RagPipelineResult
from backend.rag.prompt_builder import PromptBuilder
from backend.rag.qdrant_store import QdrantVectorStore
from backend.rag.retriever import DEFAULT_SCORE_THRESHOLD, Retriever


async def ask_local(
    question: str,
    top_k: int = 5,
    thinking_mode: bool = False,
    model: str = DEFAULT_GENERATION_MODEL,
    filters: Mapping[str, Any] | None = None,
) -> RagPipelineResult:
    """Run one local RAG question with default Ollama + Qdrant components."""

    async with OllamaEmbedder() as embedder, LocalGenerator(model=model) as generator:
        store = QdrantVectorStore()
        try:
            retriever = Retriever(
                embedder=embedder,
                store=store,
                packer=ContextPacker(),
                top_k=top_k,
                score_threshold=DEFAULT_SCORE_THRESHOLD,
            )
            pipeline = LocalRagPipeline(
                retriever=retriever,
                generator=generator,
                prompt_builder=PromptBuilder(),
                thinking_mode=thinking_mode,
            )
            return await pipeline.ask(question, top_k=top_k, filters=filters)
        finally:
            store.close()


def print_result(result: RagPipelineResult, verbose: bool = False) -> None:
    """Print a human-readable CLI result."""

    best_score = max((chunk.score for chunk in result.chunks_used), default=0.0)
    print(f"Pergunta: {result.question}")
    print(
        f"Chunks recuperados: {len(result.chunks_used)} "
        f"(melhor score: {best_score:.3f})"
    )
    if verbose:
        for chunk in result.chunks_used:
            preview = " ".join(chunk.text.split())[:160]
            print(f"  [{chunk.citation_id}] ({chunk.score:.3f}) {preview}")
    print("\nResposta:")
    print(result.answer)
    print(
        "\nLatencia: "
        f"retrieval={result.latency_ms['retrieval_ms']:.1f}ms | "
        f"prompt={result.latency_ms['prompt_ms']:.1f}ms | "
        f"generate={result.latency_ms['generation_ms']:.1f}ms | "
        f"total={result.latency_ms['total_ms']:.1f}ms"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pergunta ao RAG local do OpenClaw.")
    parser.add_argument("question", help="Pergunta em linguagem natural.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--thinking", action="store_true")
    parser.add_argument("--model", default=DEFAULT_GENERATION_MODEL)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


async def main_async() -> None:
    args = parse_args()
    check_local_services(require_qdrant=True, require_embedder=True)
    result = await ask_local(
        question=args.question,
        top_k=args.top_k,
        thinking_mode=args.thinking,
        model=args.model,
    )
    print_result(result, verbose=args.verbose)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
