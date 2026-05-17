"""Optional smoke tests for the real Qwen3 embedding adapter."""

from __future__ import annotations

import math
import os

import pytest

from backend.rag.embedding_config import EmbeddingProfileConfig
from backend.rag.qwen3_embedder import Qwen3Embedder

SMOKE_ENABLED = os.getenv("RUN_QWEN3_EMBEDDING_SMOKE") == "1"


def _qwen3_profile() -> EmbeddingProfileConfig:
    return EmbeddingProfileConfig(
        provider="sentence_transformers",
        model=os.getenv("QUIMERA_QWEN3_MODEL", "Qwen/Qwen3-Embedding-8B"),
        model_family="qwen3",
        version="v1",
        dimensions=4096,
        effective_dimensions=None,
        mrl_supported=True,
        context_length=32768,
        distance="cosine",
        normalized=True,
        instruction_aware=True,
        query_instruction=(
            "Given a financial knowledge retrieval query in Brazilian Portuguese "
            "or English, retrieve relevant passages that answer the query."
        ),
        document_instruction=None,
        profile_fingerprint=None,
    )


@pytest.mark.skipif(
    not SMOKE_ENABLED,
    reason="set RUN_QWEN3_EMBEDDING_SMOKE=1 to run real Qwen3 smoke tests",
)
def test_qwen3_real_adapter_returns_normalized_4096_dimensional_vectors() -> None:
    embedder = Qwen3Embedder(_qwen3_profile())
    text = "Qual documento sintetico explica duration em renda fixa?"

    query_vector = embedder.embed_query(text)
    document_vector = embedder.embed_document(text)
    batch_vectors = embedder.embed_documents(["documento a", "documento b", "documento c"])

    query_norm = math.sqrt(sum(value * value for value in query_vector))
    dot = sum(q * d for q, d in zip(query_vector, document_vector, strict=True))

    assert len(query_vector) == 4096
    assert len(document_vector) == 4096
    assert len(batch_vectors) == 3
    assert all(len(vector) == 4096 for vector in batch_vectors)
    assert query_norm == pytest.approx(1.0, abs=1e-3)
    assert dot < 0.9999
