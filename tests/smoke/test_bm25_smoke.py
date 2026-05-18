"""Optional smoke tests for the real FastEmbed BM25 sparse adapter."""

from __future__ import annotations

import os

import pytest

from backend.rag.sparse_embedder import BM25SparseEmbedder
from backend.rag.sparse_vector import SparseVector

SMOKE_ENABLED = os.getenv("RUN_SPARSE_EMBEDDING_SMOKE") == "1"

pytestmark = pytest.mark.skipif(
    not SMOKE_ENABLED,
    reason="set RUN_SPARSE_EMBEDDING_SMOKE=1 to run BM25 sparse smoke tests",
)


def test_bm25_real_adapter_returns_sparse_vector() -> None:
    embedder = BM25SparseEmbedder()

    vector = embedder.embed_sparse("documento sintetico sobre duration e Selic")

    assert isinstance(vector, SparseVector)
    assert vector.nnz > 0
    assert len(vector.indices) == len(vector.values)
    assert all(index >= 0 for index in vector.indices)
    assert all(value > 0.0 for value in vector.values)


def test_bm25_real_adapter_batch_preserves_length() -> None:
    embedder = BM25SparseEmbedder()

    vectors = embedder.embed_sparse_batch(["alpha financeiro", "beta macro"])

    assert len(vectors) == 2
    assert all(vector.nnz > 0 for vector in vectors)
