"""Q18 benchmark profile runner for Quimera / OPENCLAW.

Generates real ``QdrantBenchmarkRun`` artifact JSONs from live Qdrant queries.
Supports all Q18-07 profiles. Dense embeddings via nomic-embed-text (768-dim)
through Ollama. Sparse vectors via in-process BM25-style term matching.

Security:
- No query text, doc text, vectors, embeddings, payload or prompt in artifacts.
- Host must be localhost / 127.0.0.1 / ::1.
- Collection defaults to quimera_benchmark_hybrid_118.
- Requires RUN_Q18_BENCHMARK_PROFILE=1 + --execute to run live.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from qdrant_client import AsyncQdrantClient, models

# ─── constants ────────────────────────────────────────────────────────────────

PROFILE_RUN_ENV = "RUN_Q18_BENCHMARK_PROFILE"
PROFILE_RUN_REQUIRED = "1"
BENCHMARK_COLLECTION = "quimera_benchmark_hybrid_118"
BENCHMARK_COLLECTION_NOMIC = "quimera_benchmark_hybrid_118_nomic"
BENCHMARK_COLLECTION_QWEN3 = "quimera_benchmark_hybrid_118_qwen3"
LOCALHOST_ALLOWED = frozenset({"localhost", "127.0.0.1", "::1"})
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
ARTIFACT_SCHEMA_VERSION = "qdrant-benchmark-run-v1"

# Default embedding: Nomic (kept for backward compatibility with existing artifacts)
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
DEFAULT_EMBEDDING_PROVIDER = "ollama"
DEFAULT_EMBEDDING_DIMENSIONS = 768
DEFAULT_EMBEDDING_VERSION = "nomic-embed-text@benchmark"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"

# Qwen3 embedding defaults
QWEN3_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
QWEN3_EMBEDDING_DIMENSIONS = 1024
QWEN3_EMBEDDING_VERSION = "qwen3-embedding-0.6b@benchmark"
QWEN3_QUERY_INSTRUCTION = (
    "Given a financial advisory retrieval query in Portuguese, "
    "retrieve relevant passages from the Quimera financial knowledge base."
)

# Profiles that target Qwen3 embedding
QWEN3_PROFILE_PREFIX = "qdrant_118_qwen3_"
QWEN3_PROFILES = frozenset(
    {
        "qdrant_113_qwen3_historical_baseline",
        "qdrant_118_qwen3_baseline_ram",
        "qdrant_118_qwen3_balanced_local",
        "qdrant_118_qwen3_python_rrf",
        "qdrant_118_qwen3_native_rrf",
        "qdrant_118_qwen3_no_quantization",
        "qdrant_118_qwen3_turboquant_experimental",
        "qdrant_118_qwen3_dense_only",
        "qdrant_118_qwen3_hybrid",
    }
)

# Original Nomic profiles
NOMIC_PROFILES = frozenset(
    {
        "qdrant_113_historical_baseline",
        "qdrant_118_baseline_ram",
        "qdrant_118_balanced_local",
        "qdrant_118_python_rrf",
        "qdrant_118_native_rrf",
        "qdrant_118_no_quantization",
        "qdrant_118_turboquant_experimental",
        "qdrant_118_dense_only",
        "qdrant_118_hybrid",
    }
)

PROFILE_NAMES = NOMIC_PROFILES | QWEN3_PROFILES

FusionBackend = Literal["python_rrf", "qdrant_rrf", "qdrant_weighted_rrf", "none"]
RetrievalMode = Literal["dense_only", "hybrid"]


@dataclass(frozen=True, slots=True)
class ProfileSpec:
    fusion_backend: FusionBackend
    retrieval_mode: RetrievalMode
    quantization: str
    on_disk_vectors: bool | None
    on_disk_hnsw: bool | None
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_provider: str = DEFAULT_EMBEDDING_PROVIDER
    embedding_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS
    embedding_version: str = DEFAULT_EMBEDDING_VERSION
    query_instruction_used: bool = False
    default_collection: str = BENCHMARK_COLLECTION_NOMIC


def _make_qwen3_spec(
    fusion_backend: FusionBackend,
    retrieval_mode: RetrievalMode,
    quantization: str,
    on_disk_vectors: bool | None,
    on_disk_hnsw: bool | None,
) -> ProfileSpec:
    return ProfileSpec(
        fusion_backend=fusion_backend,
        retrieval_mode=retrieval_mode,
        quantization=quantization,
        on_disk_vectors=on_disk_vectors,
        on_disk_hnsw=on_disk_hnsw,
        embedding_model=QWEN3_EMBEDDING_MODEL,
        embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
        embedding_dimensions=QWEN3_EMBEDDING_DIMENSIONS,
        embedding_version=QWEN3_EMBEDDING_VERSION,
        query_instruction_used=True,
        default_collection=BENCHMARK_COLLECTION_QWEN3,
    )


PROFILE_SPECS: Mapping[str, ProfileSpec] = MappingProxyType(
    {
        # ── Nomic 768d profiles (backward-compatible) ───────────────────────
        "qdrant_113_historical_baseline": ProfileSpec(
            fusion_backend="python_rrf",
            retrieval_mode="hybrid",
            quantization="none",
            on_disk_vectors=None,
            on_disk_hnsw=None,
        ),
        "qdrant_118_baseline_ram": ProfileSpec(
            fusion_backend="python_rrf",
            retrieval_mode="hybrid",
            quantization="none",
            on_disk_vectors=False,
            on_disk_hnsw=False,
        ),
        "qdrant_118_balanced_local": ProfileSpec(
            fusion_backend="python_rrf",
            retrieval_mode="hybrid",
            quantization="none",
            on_disk_vectors=True,
            on_disk_hnsw=False,
        ),
        "qdrant_118_python_rrf": ProfileSpec(
            fusion_backend="python_rrf",
            retrieval_mode="hybrid",
            quantization="none",
            on_disk_vectors=False,
            on_disk_hnsw=False,
        ),
        "qdrant_118_native_rrf": ProfileSpec(
            fusion_backend="qdrant_rrf",
            retrieval_mode="hybrid",
            quantization="none",
            on_disk_vectors=False,
            on_disk_hnsw=False,
        ),
        "qdrant_118_no_quantization": ProfileSpec(
            fusion_backend="python_rrf",
            retrieval_mode="hybrid",
            quantization="none",
            on_disk_vectors=False,
            on_disk_hnsw=False,
        ),
        "qdrant_118_turboquant_experimental": ProfileSpec(
            fusion_backend="python_rrf",
            retrieval_mode="hybrid",
            quantization="turboquant",
            on_disk_vectors=False,
            on_disk_hnsw=False,
        ),
        "qdrant_118_dense_only": ProfileSpec(
            fusion_backend="none",
            retrieval_mode="dense_only",
            quantization="none",
            on_disk_vectors=False,
            on_disk_hnsw=False,
        ),
        "qdrant_118_hybrid": ProfileSpec(
            fusion_backend="python_rrf",
            retrieval_mode="hybrid",
            quantization="none",
            on_disk_vectors=False,
            on_disk_hnsw=False,
        ),
        # ── Qwen3 1024d profiles ────────────────────────────────────────────
        "qdrant_113_qwen3_historical_baseline": _make_qwen3_spec(
            fusion_backend="python_rrf",
            retrieval_mode="hybrid",
            quantization="none",
            on_disk_vectors=None,
            on_disk_hnsw=None,
        ),
        "qdrant_118_qwen3_baseline_ram": _make_qwen3_spec(
            fusion_backend="python_rrf",
            retrieval_mode="hybrid",
            quantization="none",
            on_disk_vectors=False,
            on_disk_hnsw=False,
        ),
        "qdrant_118_qwen3_balanced_local": _make_qwen3_spec(
            fusion_backend="python_rrf",
            retrieval_mode="hybrid",
            quantization="none",
            on_disk_vectors=True,
            on_disk_hnsw=False,
        ),
        "qdrant_118_qwen3_python_rrf": _make_qwen3_spec(
            fusion_backend="python_rrf",
            retrieval_mode="hybrid",
            quantization="none",
            on_disk_vectors=False,
            on_disk_hnsw=False,
        ),
        "qdrant_118_qwen3_native_rrf": _make_qwen3_spec(
            fusion_backend="qdrant_rrf",
            retrieval_mode="hybrid",
            quantization="none",
            on_disk_vectors=False,
            on_disk_hnsw=False,
        ),
        "qdrant_118_qwen3_no_quantization": _make_qwen3_spec(
            fusion_backend="python_rrf",
            retrieval_mode="hybrid",
            quantization="none",
            on_disk_vectors=False,
            on_disk_hnsw=False,
        ),
        "qdrant_118_qwen3_turboquant_experimental": _make_qwen3_spec(
            fusion_backend="python_rrf",
            retrieval_mode="hybrid",
            quantization="turboquant",
            on_disk_vectors=False,
            on_disk_hnsw=False,
        ),
        "qdrant_118_qwen3_dense_only": _make_qwen3_spec(
            fusion_backend="none",
            retrieval_mode="dense_only",
            quantization="none",
            on_disk_vectors=False,
            on_disk_hnsw=False,
        ),
        "qdrant_118_qwen3_hybrid": _make_qwen3_spec(
            fusion_backend="python_rrf",
            retrieval_mode="hybrid",
            quantization="none",
            on_disk_vectors=False,
            on_disk_hnsw=False,
        ),
    }
)

# ─── safe output schema (mirrors compare_qdrant_113_vs_118.py) ────────────────

FORBIDDEN_ARTIFACT_KEYS = frozenset(
    {
        "answer",
        "chunk_text",
        "dense_vector",
        "document_text",
        "embedding",
        "embeddings",
        "payload",
        "prompt",
        "query_text",
        "raw_text",
        "sparse_vector",
        "vector",
        "vectors",
    }
)


def _assert_safe(mapping: Mapping[str, object]) -> dict[str, object]:
    for key, val in mapping.items():
        if key in FORBIDDEN_ARTIFACT_KEYS:
            raise ValueError(f"forbidden artifact key: {key}")
        if isinstance(val, Mapping):
            _assert_safe(val)
        elif isinstance(val, list | tuple):
            for nested in val:
                if isinstance(nested, Mapping):
                    _assert_safe(nested)
    return dict(mapping)


# ─── corpus / query loading ───────────────────────────────────────────────────

def _load_yaml_safe(path: Path) -> object:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_benchmark_queries(root: Path) -> list[dict[str, object]]:
    path = root / "evaluation" / "benchmark_queries.yaml"
    if not path.exists():
        return []
    raw = _load_yaml_safe(path)
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _load_expected_results(root: Path) -> dict[str, dict[str, int]]:
    path = root / "evaluation" / "expected_results.yaml"
    if not path.exists():
        return {}
    raw = _load_yaml_safe(path)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, int]] = {}
    for qid, grades in raw.items():
        if isinstance(grades, dict):
            out[str(qid)] = {str(doc_id): int(g) for doc_id, g in grades.items()}
    return out


# ─── synthetic corpus builder ─────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class SyntheticDoc:
    doc_id: str
    terms: tuple[str, ...]


def build_synthetic_corpus(
    queries: list[dict[str, object]],
    expected: dict[str, dict[str, int]],
) -> list[SyntheticDoc]:
    """Build one synthetic document per expected doc_id, packed with anchor terms."""
    doc_terms: dict[str, set[str]] = {}
    for query in queries:
        qid = str(query.get("id", ""))
        if not qid:
            continue
        raw_terms = query.get("expected_terms", [])
        terms = [str(t) for t in raw_terms] if isinstance(raw_terms, list) else []
        for doc_id in (expected.get(qid) or {}).keys():
            if doc_id not in doc_terms:
                doc_terms[doc_id] = set()
            doc_terms[doc_id].update(terms)
    return [
        SyntheticDoc(doc_id=doc_id, terms=tuple(sorted(terms)))
        for doc_id, terms in doc_terms.items()
    ]


# ─── embedding helpers ────────────────────────────────────────────────────────

def _embed_sync(texts: list[str], model: str = DEFAULT_EMBEDDING_MODEL) -> list[list[float]]:
    """Embed via Ollama. Returns list of float vectors."""
    body = json.dumps({"model": model, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode("utf-8"))
    return [list(v) for v in data["embeddings"]]


def _apply_query_instruction(terms: list[str], instruction: str) -> str:
    """Build an instruction-prefixed query string for models that require it (e.g. Qwen3)."""
    query_text = " ".join(terms)
    return f"Instruct: {instruction}\nQuery: {query_text}"


def _probe_embedding_available(model: str) -> bool:
    """Return True if the embedding model responds to a single-text probe."""
    try:
        vecs = _embed_sync(["probe"], model=model)
        return bool(vecs and vecs[0])
    except Exception:
        return False


def _validate_collection_name(collection: str) -> str:
    """Reject collection names that could mutate production data."""
    forbidden_prefixes = frozenset({"quimera_knowledge", "openclaw_knowledge"})
    allowed_prefix = "quimera_benchmark_hybrid_118"
    clean = collection.strip()
    if not clean:
        raise ValueError("collection name must not be empty")
    for fp in forbidden_prefixes:
        if clean == fp or clean.startswith(fp + "_v") or clean.startswith(fp + "/"):
            raise ValueError(f"collection name is protected: {clean!r}")
    if not clean.startswith(allowed_prefix):
        raise ValueError(
            f"collection name must start with '{allowed_prefix}', got: {clean!r}"
        )
    return clean


def _normalize(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v))
    if norm < 1e-12:
        return v
    return [x / norm for x in v]


def _sparse_from_terms(terms: Sequence[str]) -> tuple[list[int], list[float]]:
    """TF-inspired sparse vector from terms. Indices are term hashes mod 8192."""
    freq: dict[int, float] = {}
    for term in terms:
        idx = int(hashlib.sha256(term.lower().encode("utf-8")).hexdigest(), 16) % 8192
        freq[idx] = freq.get(idx, 0.0) + 1.0
    if not freq:
        return [], []
    max_v = max(freq.values())
    indices = sorted(freq)
    values = [freq[i] / max_v for i in indices]
    return indices, values


def _query_terms_from_entry(entry: dict[str, object]) -> list[str]:
    raw = entry.get("expected_terms", [])
    if isinstance(raw, list):
        return [str(t) for t in raw]
    return []


# ─── Qdrant collection management ────────────────────────────────────────────

async def _collection_exists(client: AsyncQdrantClient, name: str) -> bool:
    colls = await client.get_collections()
    return any(c.name == name for c in colls.collections)


async def _create_collection(
    client: AsyncQdrantClient,
    name: str,
    quantization: str,
    on_disk_vectors: bool | None,
    dense_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
) -> None:
    quantization_config: models.QuantizationConfig | None = None
    if quantization == "scalar":
        quantization_config = models.ScalarQuantization(
            scalar=models.ScalarQuantizationConfig(
                type=models.ScalarType.INT8,
                always_ram=True,
            )
        )
    elif quantization == "turboquant":
        quantization_config = models.TurboQuantization(
            turbo=models.TurboQuantQuantizationConfig(
                bits=models.TurboQuantBitSize.BITS4,
                always_ram=True,
            )
        )

    hnsw_config: models.HnswConfigDiff | None = None
    if on_disk_vectors is not None:
        hnsw_config = models.HnswConfigDiff(on_disk=False)

    vectors_config: dict[str, models.VectorParams] = {
        DENSE_VECTOR_NAME: models.VectorParams(
            size=dense_dimensions,
            distance=models.Distance.COSINE,
            on_disk=bool(on_disk_vectors) if on_disk_vectors is not None else False,
        )
    }
    sparse_vectors: dict[str, models.SparseVectorParams] = {
        SPARSE_VECTOR_NAME: models.SparseVectorParams(
            index=models.SparseIndexParams(on_disk=False)
        )
    }
    await client.create_collection(
        collection_name=name,
        vectors_config=vectors_config,
        sparse_vectors_config=sparse_vectors,
        hnsw_config=hnsw_config,
        quantization_config=quantization_config,
    )


# ─── ingest helpers ───────────────────────────────────────────────────────────

async def _ingest_corpus(
    client: AsyncQdrantClient,
    collection: str,
    corpus: list[SyntheticDoc],
    dense_embeddings: list[list[float]],
) -> None:
    """Upsert synthetic documents as hybrid points."""
    points: list[models.PointStruct] = []
    for idx, (doc, dense) in enumerate(zip(corpus, dense_embeddings)):
        sparse_indices, sparse_values = _sparse_from_terms(doc.terms)
        point_id = idx + 1
        point = models.PointStruct(
            id=point_id,
            vector={
                DENSE_VECTOR_NAME: _normalize(dense),
                SPARSE_VECTOR_NAME: models.SparseVector(
                    indices=sparse_indices,
                    values=sparse_values,
                ),
            },
            payload={"doc_id": doc.doc_id, "corpus_id": "q18_synthetic_v1"},
        )
        points.append(point)
    if points:
        await client.upsert(collection_name=collection, points=points, wait=True)


# ─── search helpers ───────────────────────────────────────────────────────────

def _python_rrf(
    dense_hits: list[tuple[str, float]],
    sparse_hits: list[tuple[str, float]],
    k: float = 60.0,
) -> list[str]:
    scores: dict[str, float] = {}
    for rank, (doc_id, _score) in enumerate(dense_hits):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    for rank, (doc_id, _score) in enumerate(sparse_hits):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return [doc_id for doc_id, _ in sorted(scores.items(), key=lambda x: -x[1])]


def _scored_to_pairs(
    results: models.QueryResponse, id_to_doc: dict[int, str]
) -> list[tuple[str, float]]:
    out = []
    for r in results.points:
        pid = int(r.id)
        out.append((id_to_doc.get(pid, f"unknown_{pid}"), float(r.score)))
    return out


async def _search_python_rrf(
    client: AsyncQdrantClient,
    collection: str,
    dense_vec: list[float],
    sparse_indices: list[int],
    sparse_values: list[float],
    limit: int,
    id_to_doc: dict[int, str],
) -> tuple[list[str], float, float, float, float, float]:
    t0 = time.perf_counter()
    dense_results = await client.query_points(
        collection_name=collection,
        query=dense_vec,
        using=DENSE_VECTOR_NAME,
        limit=limit,
        with_payload=True,
    )
    t_dense = time.perf_counter()

    sparse_results = await client.query_points(
        collection_name=collection,
        query=models.SparseVector(indices=sparse_indices, values=sparse_values),
        using=SPARSE_VECTOR_NAME,
        limit=limit,
        with_payload=True,
    )
    t_sparse = time.perf_counter()

    dense_hits = _scored_to_pairs(dense_results, id_to_doc)
    sparse_hits = _scored_to_pairs(sparse_results, id_to_doc)
    t_fusion_start = time.perf_counter()
    ranked = _python_rrf(dense_hits, sparse_hits)[:limit]
    t1 = time.perf_counter()

    search_dense_ms = (t_dense - t0) * 1000
    search_sparse_ms = (t_sparse - t_dense) * 1000
    fusion_ms = (t1 - t_fusion_start) * 1000
    total_ms = (t1 - t0) * 1000
    return ranked, 0.0, search_dense_ms, search_sparse_ms, fusion_ms, total_ms


async def _search_dense_only(
    client: AsyncQdrantClient,
    collection: str,
    dense_vec: list[float],
    limit: int,
    id_to_doc: dict[int, str],
) -> tuple[list[str], float, float, float, float, float]:
    t0 = time.perf_counter()
    results = await client.query_points(
        collection_name=collection,
        query=dense_vec,
        using=DENSE_VECTOR_NAME,
        limit=limit,
        with_payload=True,
    )
    t1 = time.perf_counter()
    ranked = [id_to_doc.get(int(r.id), f"unknown_{r.id}") for r in results.points]
    total_ms = (t1 - t0) * 1000
    return ranked, 0.0, total_ms, 0.0, 0.0, total_ms


async def _search_native_rrf(
    client: AsyncQdrantClient,
    collection: str,
    dense_vec: list[float],
    sparse_indices: list[int],
    sparse_values: list[float],
    limit: int,
    id_to_doc: dict[int, str],
) -> tuple[list[str], float, float, float, float, float]:
    t0 = time.perf_counter()
    try:
        results = await client.query_points(
            collection_name=collection,
            prefetch=[
                models.Prefetch(query=dense_vec, using=DENSE_VECTOR_NAME, limit=limit * 2),
                models.Prefetch(
                    query=models.SparseVector(indices=sparse_indices, values=sparse_values),
                    using=SPARSE_VECTOR_NAME,
                    limit=limit * 2,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
        )
        t1 = time.perf_counter()
        ranked = [id_to_doc.get(int(r.id), f"unknown_{r.id}") for r in results.points]
        total_ms = (t1 - t0) * 1000
        return ranked, 0.0, 0.0, 0.0, 0.0, total_ms
    except Exception:
        return [], 0.0, 0.0, 0.0, 0.0, 0.0


# ─── metric computation ───────────────────────────────────────────────────────

def _precision_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    hits = sum(1 for doc in ranked[:k] if doc in relevant)
    return hits / k if k > 0 else 0.0


def _recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 1.0
    hits = sum(1 for doc in ranked[:k] if doc in relevant)
    return hits / len(relevant)


def _mrr(ranked: list[str], relevant: set[str]) -> float:
    for i, doc in enumerate(ranked):
        if doc in relevant:
            return 1.0 / (i + 1)
    return 0.0


def _dcg(ranked: list[str], grades: dict[str, int], k: int) -> float:
    total = 0.0
    for i, doc in enumerate(ranked[:k]):
        rel = grades.get(doc, 0)
        if rel > 0:
            total += (2 ** rel - 1) / math.log2(i + 2)
    return total


def _ndcg_at_k(ranked: list[str], grades: dict[str, int], k: int) -> float:
    ideal_docs = sorted(grades.keys(), key=lambda d: -grades[d])[:k]
    ideal_dcg: float = sum(
        (2 ** grades[d] - 1) / math.log2(i + 2) for i, d in enumerate(ideal_docs)
    )
    if ideal_dcg <= 0:
        return 0.0
    return float(_dcg(ranked, grades, k) / ideal_dcg)


# ─── p-tiles ─────────────────────────────────────────────────────────────────

def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = (pct / 100.0) * (len(s) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (idx - lo) * (s[hi] - s[lo])


# ─── Qdrant version probe ─────────────────────────────────────────────────────

def _probe_server_version(host: str, port: int) -> str | None:
    try:
        url = f"http://{host}:{port}/"
        data = urllib.request.urlopen(url, timeout=5).read().decode("utf-8")
        parsed = json.loads(data)
        return str(parsed.get("version", ""))
    except Exception:
        return None


def _probe_collection_size(host: str, port: int, collection: str) -> int | None:
    try:
        url = f"http://{host}:{port}/collections/{collection}"
        data = urllib.request.urlopen(url, timeout=5).read().decode("utf-8")
        parsed: dict[str, object] = json.loads(data)
        result = parsed.get("result", {})
        if not isinstance(result, dict):
            return None
        count = result.get("segments_count")
        return int(count) if isinstance(count, int) else None
    except Exception:
        return None


def _probe_collection_bytes(host: str, port: int, collection: str) -> int | None:
    try:
        url = f"http://{host}:{port}/collections/{collection}"
        data = urllib.request.urlopen(url, timeout=5).read().decode("utf-8")
        parsed = json.loads(data)
        disk_data = parsed.get("result", {}).get("disk_data_size", None)
        ram_data = parsed.get("result", {}).get("ram_data_size", None)
        if disk_data is not None:
            return int(disk_data)
        if ram_data is not None:
            return int(ram_data)
        return None
    except Exception:
        return None


# ─── corpus hash ──────────────────────────────────────────────────────────────

def _corpus_hash(corpus: list[SyntheticDoc]) -> str:
    content = "|".join(f"{d.doc_id}:{','.join(d.terms)}" for d in sorted(corpus, key=lambda x: x.doc_id))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _query_set_hash(queries: list[dict[str, object]]) -> str:
    content = "|".join(str(q.get("id", "")) for q in queries)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _stable_run_id(profile_name: str, ts: str) -> str:
    return hashlib.sha256(f"{profile_name}:{ts}".encode("utf-8")).hexdigest()[:16]


# ─── main benchmark logic ─────────────────────────────────────────────────────

async def run_benchmark(
    *,
    profile_name: str,
    host: str,
    port: int,
    collection: str,
    root: Path,
    drop_and_recreate: bool,
) -> dict[str, object]:
    spec = PROFILE_SPECS[profile_name]
    import importlib.metadata
    client_version = importlib.metadata.version("qdrant-client")
    server_version = _probe_server_version(host, port)

    embedding_model = spec.embedding_model
    embedding_dims = spec.embedding_dimensions
    embedding_provider = spec.embedding_provider
    embedding_version = spec.embedding_version
    query_instruction_used = spec.query_instruction_used

    # Guard: fail early if embedding model is unavailable rather than silently ingest wrong data
    if not _probe_embedding_available(embedding_model):
        raise RuntimeError(
            f"embedding model unavailable: {embedding_model!r} — "
            "pull it via 'ollama pull' or configure another provider"
        )

    queries = _load_benchmark_queries(root)
    expected = _load_expected_results(root)
    corpus = build_synthetic_corpus(queries, expected)

    if not corpus:
        raise RuntimeError("empty synthetic corpus — check benchmark_queries.yaml and expected_results.yaml")

    # Embed corpus texts (documents — no instruction for Qwen3)
    doc_texts = [" ".join(doc.terms) for doc in corpus]
    t_embed_start = time.perf_counter()
    dense_embeddings = _embed_sync(doc_texts, model=embedding_model)
    t_embed_end = time.perf_counter()
    embed_ms = (t_embed_end - t_embed_start) * 1000 / max(len(doc_texts), 1)

    # Validate embedding dimension against spec
    if dense_embeddings and len(dense_embeddings[0]) != embedding_dims:
        actual = len(dense_embeddings[0])
        raise RuntimeError(
            f"embedding dimension mismatch: spec={embedding_dims}, actual={actual} — "
            "check --embedding-dimensions or the model configuration"
        )

    # id_to_doc: point ID (1-based) -> doc_id
    id_to_doc = {idx + 1: doc.doc_id for idx, doc in enumerate(corpus)}

    client = AsyncQdrantClient(host=host, port=port, check_compatibility=False)
    try:
        exists = await _collection_exists(client, collection)
        if exists and drop_and_recreate:
            await client.delete_collection(collection)
            exists = False
        if not exists:
            await _create_collection(client, collection, spec.quantization, spec.on_disk_vectors, embedding_dims)
            await _ingest_corpus(client, collection, corpus, dense_embeddings)
        else:
            # Re-ingest to be safe (upsert is idempotent)
            await _ingest_corpus(client, collection, corpus, dense_embeddings)
    except Exception as exc:
        await client.close()
        raise RuntimeError(f"collection setup failed: {exc}") from exc

    # Build query vectors — Qwen3 profiles use an instruction prefix on the query side
    if query_instruction_used:
        query_texts = [
            _apply_query_instruction(_query_terms_from_entry(q), QWEN3_QUERY_INSTRUCTION)
            for q in queries
        ]
    else:
        query_texts = [" ".join(_query_terms_from_entry(q)) for q in queries]

    query_embeddings = _embed_sync(query_texts, model=embedding_model) if query_texts else []

    total_ms_list: list[float] = []
    p_at_5_list: list[float] = []
    recall_at_10_list: list[float] = []
    mrr_list: list[float] = []
    ndcg_at_5_list: list[float] = []
    search_dense_ms_list: list[float] = []
    search_sparse_ms_list: list[float] = []
    fusion_ms_list: list[float] = []

    native_rrf_overlap_count = 0
    native_rrf_total = 0
    tie_break_regression_count = 0

    for entry, q_dense in zip(queries, query_embeddings):
        qid = str(entry.get("id", ""))
        q_terms = _query_terms_from_entry(entry)
        grades = expected.get(qid, {})
        relevant = {doc_id for doc_id, grade in grades.items() if grade > 0}
        q_dense_norm = _normalize(q_dense)
        q_sparse_idx, q_sparse_val = _sparse_from_terms(q_terms)

        if spec.retrieval_mode == "dense_only":
            ranked, _, s_dense_ms, _, _, total_ms = await _search_dense_only(
                client, collection, q_dense_norm, 10, id_to_doc
            )
        elif spec.fusion_backend == "qdrant_rrf":
            ranked_native, _, _, _, _, total_ms_native = await _search_native_rrf(
                client, collection, q_dense_norm, q_sparse_idx, q_sparse_val, 10, id_to_doc
            )
            # Also compute python rrf for overlap comparison
            ranked_python, _, s_dense_ms, s_sparse_ms, fus_ms, _ = await _search_python_rrf(
                client, collection, q_dense_norm, q_sparse_idx, q_sparse_val, 10, id_to_doc
            )
            ranked = ranked_native if ranked_native else ranked_python
            total_ms = total_ms_native if ranked_native else 0.0
            # Overlap
            native_rrf_total += 1
            overlap = len(set(ranked_native[:10]) & set(ranked_python[:10])) / 10.0 if ranked_native else 0.0
            if overlap >= 0.9:
                native_rrf_overlap_count += 1
            if ranked_python and ranked_native and ranked_python[0] != ranked_native[0]:
                tie_break_regression_count += 1
            search_dense_ms_list.append(s_dense_ms)
            search_sparse_ms_list.append(s_sparse_ms)
            fusion_ms_list.append(fus_ms)
        else:
            ranked, _, s_dense_ms, s_sparse_ms, fus_ms, total_ms = await _search_python_rrf(
                client, collection, q_dense_norm, q_sparse_idx, q_sparse_val, 10, id_to_doc
            )
            search_dense_ms_list.append(s_dense_ms)
            search_sparse_ms_list.append(s_sparse_ms)
            fusion_ms_list.append(fus_ms)

        if relevant:
            p_at_5_list.append(_precision_at_k(ranked, relevant, 5))
            recall_at_10_list.append(_recall_at_k(ranked, relevant, 10))
            mrr_list.append(_mrr(ranked, relevant))
            ndcg_at_5_list.append(_ndcg_at_k(ranked, grades, 5))
        total_ms_list.append(total_ms)

    await client.close()

    def _avg(lst: list[float]) -> float | None:
        return sum(lst) / len(lst) if lst else None

    p50 = _percentile(total_ms_list, 50)
    p95 = _percentile(total_ms_list, 95)

    precision_mean = _avg(p_at_5_list)
    recall_mean = _avg(recall_at_10_list)
    mrr_mean = _avg(mrr_list)
    ndcg_mean = _avg(ndcg_at_5_list)

    ts_now = datetime.now(UTC).replace(microsecond=0).isoformat()
    run_id = _stable_run_id(profile_name, ts_now)

    meta: dict[str, object] = {
        "generated_at_utc": ts_now,
        "benchmark_schema_version": ARTIFACT_SCHEMA_VERSION,
        "corpus_doc_count": len(corpus),
        "query_count": len(queries),
        "embed_ms_per_doc": round(embed_ms, 3),
    }
    if spec.fusion_backend == "qdrant_rrf" and native_rrf_total > 0:
        meta["overlap_at_10"] = native_rrf_overlap_count / native_rrf_total
        meta["tie_break_regression_count"] = float(tie_break_regression_count)

    collection_bytes = _probe_collection_bytes(host, port, collection)

    artifact = _assert_safe(
        {
            "run_id": run_id,
            "scenario": "live_q18_benchmark",
            "qdrant_version": server_version,
            "profile_name": profile_name,
            "fusion_backend": spec.fusion_backend,
            "retrieval_mode": spec.retrieval_mode,
            "quantization": spec.quantization,
            "corpus_hash": _corpus_hash(corpus),
            "query_set_hash": _query_set_hash(queries),
            "quality": {
                "precision_at_5": precision_mean,
                "recall_at_10": recall_mean,
                "mrr": mrr_mean,
                "ndcg_at_5": ndcg_mean,
            },
            "latency": {
                "p50_ms": p50,
                "p95_ms": p95,
                "embed_dense_ms_p50": embed_ms,
                "embed_sparse_ms_p50": 0.0,
                "search_dense_ms_p50": _percentile(search_dense_ms_list, 50) if search_dense_ms_list else None,
                "search_sparse_ms_p50": _percentile(search_sparse_ms_list, 50) if search_sparse_ms_list else None,
                "fusion_ms_p50": _percentile(fusion_ms_list, 50) if fusion_ms_list else None,
                "total_ms_p50": p50,
                "total_ms_p95": p95,
            },
            "resources": {
                "memory_report_available": False,
                "peak_ram_mb": None,
                "collection_size_bytes": collection_bytes,
                "storage_config": {
                    "dense_dimensions": embedding_dims,
                    "on_disk_vectors": spec.on_disk_vectors,
                    "on_disk_hnsw": spec.on_disk_hnsw,
                },
                "quantization": spec.quantization,
                "on_disk_vectors": spec.on_disk_vectors,
                "on_disk_hnsw": spec.on_disk_hnsw,
                "qdrant_server_version": server_version,
                "qdrant_client_version": client_version,
            },
            "profile_config": {
                "dense_name": DENSE_VECTOR_NAME,
                "sparse_name": SPARSE_VECTOR_NAME,
                "dense_dimensions": embedding_dims,
                "dense_vector_name": DENSE_VECTOR_NAME,
                "sparse_vector_name": SPARSE_VECTOR_NAME,
                "embedding_model": embedding_model,
                "embedding_provider": embedding_provider,
                "embedding_dimensions": embedding_dims,
                "embedding_version": embedding_version,
                "query_instruction_used": query_instruction_used,
                "on_disk_vectors": spec.on_disk_vectors,
                "on_disk_hnsw": spec.on_disk_hnsw,
                "fusion_backend": spec.fusion_backend,
                "retrieval_mode": spec.retrieval_mode,
                "quantization": spec.quantization,
            },
            "metadata": meta,
        }
    )
    return artifact


# ─── CLI ─────────────────────────────────────────────────────────────────────

def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=sorted(PROFILE_NAMES))
    parser.add_argument(
        "--collection",
        default=None,
        help=(
            "Override the benchmark collection name. "
            "If omitted, the profile's default collection is used. "
            "Must start with 'quimera_benchmark_hybrid_118'."
        ),
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6333)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--drop-and-recreate", action="store_true")
    return parser.parse_args(argv)


def _ensure_localhost(host: str) -> str:
    clean = host.strip().casefold()
    if clean not in LOCALHOST_ALLOWED:
        raise ValueError(f"host must be localhost / 127.0.0.1 / ::1, got: {host!r}")
    return clean


def _resolve_collection(args_collection: str | None, profile_name: str) -> str:
    """Return the validated collection name, using spec default if not overridden."""
    spec = PROFILE_SPECS[profile_name]
    raw = args_collection if args_collection is not None else spec.default_collection
    return _validate_collection_name(raw)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    host = _ensure_localhost(args.host)

    try:
        collection = _resolve_collection(args.collection, args.profile)
    except ValueError as exc:
        sys.stderr.write(f"invalid collection: {exc}\n")
        return 2

    if args.execute and os.getenv(PROFILE_RUN_ENV) != PROFILE_RUN_REQUIRED:
        sys.stderr.write(
            f"live benchmark requires {PROFILE_RUN_ENV}=1 in environment\n"
        )
        return 2

    if not args.execute:
        spec = PROFILE_SPECS[args.profile]
        dry = {
            "dry_run": True,
            "profile": args.profile,
            "collection": collection,
            "embedding_model": spec.embedding_model,
            "embedding_dimensions": spec.embedding_dimensions,
            "embedding_provider": spec.embedding_provider,
            "query_instruction_used": spec.query_instruction_used,
            "host": host,
            "port": args.port,
            "output": str(args.output),
            "message": f"pass --execute and {PROFILE_RUN_ENV}=1 to run",
        }
        sys.stdout.write(json.dumps(dry, indent=2) + "\n")
        return 0

    try:
        artifact = asyncio.run(
            run_benchmark(
                profile_name=args.profile,
                host=host,
                port=args.port,
                collection=collection,
                root=Path("."),
                drop_and_recreate=args.drop_and_recreate,
            )
        )
        out_path = args.output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Wrap in runs list for compatibility with load_benchmark_runs
        wrapper = {"runs": [artifact], "schema_version": ARTIFACT_SCHEMA_VERSION}
        text = json.dumps(wrapper, ensure_ascii=False, indent=2, sort_keys=True)
        out_path.write_text(text + "\n", encoding="utf-8")
        sys.stdout.write(json.dumps(artifact, ensure_ascii=False, sort_keys=True) + "\n")
        return 0
    except Exception as exc:
        sys.stderr.write(f"q18 benchmark profile run failed: {type(exc).__name__}: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
