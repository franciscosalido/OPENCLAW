"""Ollama embedding bakeoff contracts for Qwen3-Embedding-4B vs Nomic.

This module is intentionally safe to import: it does not call Ollama, Qdrant,
network services, subprocesses, or the filesystem at import time. It models the
Qwen3-Embedding-4B candidate as an opt-in benchmark path while keeping
``nomic-embed-text`` as the baseline/fallback.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

import httpx

OLLAMA_READINESS_SCHEMA_VERSION = "ollama-readiness-v1"
EMBEDDING_BAKEOFF_SUMMARY_SCHEMA_VERSION = "embedding-bakeoff-qwen3-4b-summary-v1"
EMBEDDING_BAKEOFF_COLLECTION_SCHEMA_VERSION = "qdrant-hybrid-118-embedding-bakeoff-qwen3-4b-v1"

OLLAMA_VERSION_CONTRACT_LAST_VERIFIED = "2026-05-28"
OLLAMA_LATEST_STABLE_KNOWN = "0.24.0"
OLLAMA_KNOWN_PRERELEASES: frozenset[str] = frozenset({"0.30.0"})
OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434"
OLLAMA_EMBED_PATH = "/api/embed"
OLLAMA_LEGACY_EMBEDDINGS_PATH = "/api/embeddings"

QWEN3_4B_MODEL_ID = "Qwen/Qwen3-Embedding-4B"
QWEN3_4B_OLLAMA_MODEL_ID = "qwen3-embedding:4b"
QWEN3_4B_DEFAULT_DIMENSIONS = 2560
QWEN3_4B_ALLOWED_DIMENSIONS = tuple(range(32, 2561))
QWEN3_4B_CONTEXT_LENGTH = 32768
QWEN3_4B_INSTRUCTION_AWARE = True
QWEN3_QUERY_INSTRUCTION = (
    "Given a Portuguese financial advisory retrieval query, retrieve relevant "
    "passages from the Quimera financial knowledge base."
)

NOMIC_MODEL_ID = "nomic-embed-text"
NOMIC_DEFAULT_DIMENSIONS = 768

BAKEOFF_COLLECTION = "quimera_benchmark_embedding_bakeoff_118"
NOMIC_BENCHMARK_COLLECTION = "quimera_benchmark_hybrid_118_nomic"
QWEN3_4B_BENCHMARK_COLLECTION = "quimera_benchmark_hybrid_118_qwen3_4b"
ALLOWED_BAKEOFF_COLLECTIONS = frozenset(
    {
        BAKEOFF_COLLECTION,
        NOMIC_BENCHMARK_COLLECTION,
        QWEN3_4B_BENCHMARK_COLLECTION,
    }
)
DENSE_NOMIC_VECTOR_NAME = "dense_nomic"
DENSE_QWEN3_4B_VECTOR_NAME = "dense_qwen3_4b"
SPARSE_VECTOR_NAME = "sparse"

REQUIRED_BAKEOFF_PAYLOAD_FIELDS = (
    "doc_id",
    "chunk_id",
    "chunk_index",
    "source",
    "schema_version",
    "corpus_id",
    "security_level",
    "embedding_models_available",
    "dense_nomic_model",
    "dense_nomic_dimensions",
    "dense_qwen3_4b_model",
    "dense_qwen3_4b_dimensions",
    "sparse_provider",
)

FORBIDDEN_OUTPUT_KEYS = frozenset(
    {
        "query",
        "query_text",
        "text",
        "chunk_text",
        "document_text",
        "payload",
        "prompt",
        "answer",
        "vector",
        "vectors",
        "embedding",
        "embeddings",
    }
)


class EmbeddingCandidateDecision(str, Enum):
    """Possible D2P outcomes for the Qwen3-4B vs Nomic bakeoff."""

    PROMOTE_QWEN3_4B_DEFAULT = "promote_qwen3_4b_default"
    KEEP_NOMIC_DEFAULT = "keep_nomic_default"
    QWEN3_4B_EXPERIMENTAL_ONLY = "qwen3_4b_experimental_only"
    INCONCLUSIVE_QWEN3_4B_UNAVAILABLE = "inconclusive_qwen3_4b_unavailable"
    DEFER_DUE_TO_LATENCY_OR_MEMORY = "defer_due_to_latency_or_memory"


@dataclass(frozen=True, slots=True)
class OllamaReadiness:
    """Safe readiness report for local Ollama embedding bakeoff."""

    schema_version: str
    ollama_available: bool
    ollama_version: str | None
    target_version: str | None
    latest_stable_known: str | None
    pre_release_available: str | None
    api_version_ok: bool
    embed_endpoint_ok: bool
    running_models: tuple[str, ...]
    qwen3_4b_available: bool
    nomic_available: bool
    ready_for_bakeoff: bool
    notes: tuple[str, ...] = ()

    def to_safe_dict(self) -> dict[str, object]:
        """Serialize readiness without model outputs or user text."""
        return _safe_dict(
            {
                "schema_version": self.schema_version,
                "ollama_available": self.ollama_available,
                "ollama_version": self.ollama_version,
                "target_version": self.target_version,
                "latest_stable_known": self.latest_stable_known,
                "pre_release_available": self.pre_release_available,
                "api_version_ok": self.api_version_ok,
                "embed_endpoint_ok": self.embed_endpoint_ok,
                "running_models": self.running_models,
                "qwen3_4b_available": self.qwen3_4b_available,
                "nomic_available": self.nomic_available,
                "ready_for_bakeoff": self.ready_for_bakeoff,
                "notes": self.notes,
            }
        )


@dataclass(frozen=True, slots=True)
class EmbeddingModelContract:
    """Immutable embedding model contract for bakeoff configuration."""

    model_id: str
    default_dimensions: int
    allowed_dimensions: tuple[int, ...]
    context_length: int | None
    instruction_aware: bool
    baseline_or_candidate: str

    def __post_init__(self) -> None:
        _validate_text(self.model_id, "model_id")
        if self.default_dimensions <= 0:
            raise ValueError("default_dimensions must be positive")
        if self.default_dimensions not in self.allowed_dimensions:
            raise ValueError("default_dimensions must be allowed")
        if self.context_length is not None and self.context_length <= 0:
            raise ValueError("context_length must be positive")
        if self.baseline_or_candidate not in {"baseline", "candidate"}:
            raise ValueError("baseline_or_candidate must be baseline or candidate")

    def to_safe_dict(self) -> dict[str, object]:
        """Serialize the model contract."""
        return _safe_dict(
            {
                "model_id": self.model_id,
                "default_dimensions": self.default_dimensions,
                "allowed_dimensions_min": min(self.allowed_dimensions),
                "allowed_dimensions_max": max(self.allowed_dimensions),
                "context_length": self.context_length,
                "instruction_aware": self.instruction_aware,
                "baseline_or_candidate": self.baseline_or_candidate,
            }
        )


@dataclass(frozen=True, slots=True)
class EmbeddingBatchResult:
    """Safe metadata for an embedding batch response."""

    model: str
    dimensions: int
    count: int
    batch_size: int
    keep_alive: str | None
    load_duration_ns: int | None
    total_duration_ns: int | None
    prompt_eval_count: int | None
    embeddings: tuple[tuple[float, ...], ...] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_text(self.model, "model")
        if self.dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if self.count != len(self.embeddings):
            raise ValueError("count must match embeddings length")
        for vector in self.embeddings:
            if len(vector) != self.dimensions:
                raise ValueError("embedding dimension mismatch")
            if not all(math.isfinite(value) for value in vector):
                raise ValueError("embedding contains non-finite value")

    def __repr__(self) -> str:
        """Return a safe representation that never includes raw vector values."""
        return (
            f"EmbeddingBatchResult(model={self.model!r}, dimensions={self.dimensions}, "
            f"count={self.count}, batch_size={self.batch_size}, keep_alive={self.keep_alive!r}, "
            f"embeddings=<{self.count}x{self.dimensions} values excluded>)"
        )

    def to_safe_dict(self) -> dict[str, object]:
        """Serialize metadata only; raw embeddings are intentionally excluded."""
        return _safe_dict(
            {
                "model": self.model,
                "dimensions": self.dimensions,
                "count": self.count,
                "batch_size": self.batch_size,
                "keep_alive": self.keep_alive,
                "load_duration_ns": self.load_duration_ns,
                "total_duration_ns": self.total_duration_ns,
                "prompt_eval_count": self.prompt_eval_count,
            }
        )


@dataclass(frozen=True, slots=True)
class OllamaModelLoadResult:
    """Safe metadata from an explicit model preload probe."""

    model: str
    dimensions: int | None
    keep_alive: str | None
    load_duration_ns: int | None
    total_duration_ns: int | None
    loaded: bool

    def to_safe_dict(self) -> dict[str, object]:
        """Serialize model load metadata without embedding values."""
        return _safe_dict(
            {
                "model": self.model,
                "dimensions": self.dimensions,
                "keep_alive": self.keep_alive,
                "load_duration_ns": self.load_duration_ns,
                "total_duration_ns": self.total_duration_ns,
                "loaded": self.loaded,
            }
        )


@dataclass(frozen=True, slots=True)
class OllamaModelUnloadResult:
    """Safe metadata from an explicit manual model unload request."""

    model: str
    unloaded_requested: bool
    total_duration_ns: int | None

    def to_safe_dict(self) -> dict[str, object]:
        """Serialize model unload metadata."""
        return _safe_dict(
            {
                "model": self.model,
                "unloaded_requested": self.unloaded_requested,
                "total_duration_ns": self.total_duration_ns,
            }
        )


@dataclass(frozen=True, slots=True)
class EmbeddingBakeoffCollectionSpec:
    """Conceptual Qdrant bakeoff schema with both dense vectors on each point."""

    collection_name: str = BAKEOFF_COLLECTION
    dense_nomic_vector_name: str = DENSE_NOMIC_VECTOR_NAME
    dense_qwen3_4b_vector_name: str = DENSE_QWEN3_4B_VECTOR_NAME
    sparse_vector_name: str = SPARSE_VECTOR_NAME
    nomic_dimensions: int = NOMIC_DEFAULT_DIMENSIONS
    qwen3_4b_dimensions: int = QWEN3_4B_DEFAULT_DIMENSIONS
    schema_version: str = EMBEDDING_BAKEOFF_COLLECTION_SCHEMA_VERSION
    payload_fields: tuple[str, ...] = REQUIRED_BAKEOFF_PAYLOAD_FIELDS

    def __post_init__(self) -> None:
        _validate_text(self.collection_name, "collection_name")
        if self.collection_name in {"quimera_knowledge", "quimera_knowledge_v2", "openclaw_knowledge"}:
            raise ValueError("protected collection cannot be used for bakeoff")
        if self.collection_name not in ALLOWED_BAKEOFF_COLLECTIONS:
            raise ValueError("collection must be a declared bakeoff collection")
        names = {self.dense_nomic_vector_name, self.dense_qwen3_4b_vector_name, self.sparse_vector_name}
        if len(names) != 3:
            raise ValueError("vector names must be distinct")
        if self.nomic_dimensions != NOMIC_DEFAULT_DIMENSIONS:
            raise ValueError("nomic dimensions must remain 768")
        if self.qwen3_4b_dimensions != QWEN3_4B_DEFAULT_DIMENSIONS:
            raise ValueError("Qwen3-4B benchmark dimensions must remain 2560")
        for field_name in self.payload_fields:
            _validate_text(field_name, "payload_field")

    def build_vectors_config(self) -> dict[str, object]:
        """Return conceptual named dense vector config."""
        return {
            self.dense_nomic_vector_name: {"size": self.nomic_dimensions, "distance": "Cosine"},
            self.dense_qwen3_4b_vector_name: {"size": self.qwen3_4b_dimensions, "distance": "Cosine"},
        }

    def build_sparse_vectors_config(self) -> dict[str, object]:
        """Return conceptual sparse vector config."""
        return {self.sparse_vector_name: {}}

    def to_safe_dict(self) -> dict[str, object]:
        """Serialize collection contract without payload values or vectors."""
        return _safe_dict(
            {
                "collection_name": self.collection_name,
                "schema_version": self.schema_version,
                "dense_named_vector_config": self.build_vectors_config(),
                "sparse_named_vector_config": self.build_sparse_vectors_config(),
                "payload_fields": self.payload_fields,
            }
        )


@dataclass(frozen=True, slots=True)
class EmbeddingBakeoffScenario:
    """Declared benchmark scenario for Qwen3-4B vs Nomic."""

    scenario_id: str
    model: str
    retrieval_mode: str
    dimensions: int
    instruction_enabled: bool
    cold_start: bool
    batch_mode: str

    def to_safe_dict(self) -> dict[str, object]:
        """Serialize scenario metadata."""
        return _safe_dict(
            {
                "scenario_id": self.scenario_id,
                "model": self.model,
                "retrieval_mode": self.retrieval_mode,
                "dimensions": self.dimensions,
                "instruction_enabled": self.instruction_enabled,
                "cold_start": self.cold_start,
                "batch_mode": self.batch_mode,
            }
        )


@dataclass(frozen=True, slots=True)
class EmbeddingBakeoffMetrics:
    """Quality, latency, Ollama and resource metrics for a scenario."""

    precision_at_5: float | None = None
    recall_at_10: float | None = None
    mrr: float | None = None
    ndcg_at_5: float | None = None
    embed_ms_p50: float | None = None
    embed_ms_p95: float | None = None
    search_ms_p50: float | None = None
    search_ms_p95: float | None = None
    fusion_ms: float | None = None
    total_ms_p50: float | None = None
    total_ms_p95: float | None = None
    load_duration_ns: int | None = None
    total_duration_ns: int | None = None
    prompt_eval_count: int | None = None
    batch_size: int | None = None
    keep_alive: str | None = None
    memory_snapshot_available: bool = False
    collection_size_bytes: int | None = None
    embedding_dimensions: int | None = None
    model_size_bytes: int | None = None

    def __post_init__(self) -> None:
        for name, value in self.to_safe_dict().items():
            if isinstance(value, int | float) and value is not None:
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError(f"{name} must be finite")
                if value < 0:
                    raise ValueError(f"{name} must be non-negative")

    def to_safe_dict(self) -> dict[str, object]:
        """Serialize metrics."""
        return _safe_dict(
            {
                "precision_at_5": self.precision_at_5,
                "recall_at_10": self.recall_at_10,
                "mrr": self.mrr,
                "ndcg_at_5": self.ndcg_at_5,
                "embed_ms_p50": self.embed_ms_p50,
                "embed_ms_p95": self.embed_ms_p95,
                "search_ms_p50": self.search_ms_p50,
                "search_ms_p95": self.search_ms_p95,
                "fusion_ms": self.fusion_ms,
                "total_ms_p50": self.total_ms_p50,
                "total_ms_p95": self.total_ms_p95,
                "load_duration_ns": self.load_duration_ns,
                "total_duration_ns": self.total_duration_ns,
                "prompt_eval_count": self.prompt_eval_count,
                "batch_size": self.batch_size,
                "keep_alive": self.keep_alive,
                "memory_snapshot_available": self.memory_snapshot_available,
                "collection_size_bytes": self.collection_size_bytes,
                "embedding_dimensions": self.embedding_dimensions,
                "model_size_bytes": self.model_size_bytes,
            }
        )


@dataclass(frozen=True, slots=True)
class EmbeddingBakeoffRun:
    """One safe bakeoff run entry."""

    scenario: EmbeddingBakeoffScenario
    metrics: EmbeddingBakeoffMetrics
    evidence_complete: bool

    def to_safe_dict(self) -> dict[str, object]:
        """Serialize run metadata and metrics."""
        return _safe_dict(
            {
                "scenario": self.scenario.to_safe_dict(),
                "metrics": self.metrics.to_safe_dict(),
                "evidence_complete": self.evidence_complete,
            }
        )


@dataclass(frozen=True, slots=True)
class EmbeddingBakeoffSummary:
    """Machine-readable Qwen3-4B vs Nomic decision summary."""

    schema_version: str
    generated_at_utc: str
    artifact_only: bool
    live_benchmark_executed: bool
    bakeoff_collection: str
    scenarios: tuple[EmbeddingBakeoffRun, ...]
    decision: EmbeddingCandidateDecision
    winner: str | None
    python_rrf_default: bool
    nomic_kept_as_fallback: bool
    safety: Mapping[str, bool] = field(
        default_factory=lambda: MappingProxyType(
            {
                "includes_query_text": False,
                "includes_document_text": False,
                "includes_payload": False,
                "includes_vectors": False,
                "includes_embeddings": False,
            }
        )
    )

    def to_safe_dict(self) -> dict[str, object]:
        """Serialize summary safely."""
        return _safe_dict(
            {
                "schema_version": self.schema_version,
                "generated_at_utc": self.generated_at_utc,
                "artifact_only": self.artifact_only,
                "live_benchmark_executed": self.live_benchmark_executed,
                "bakeoff_collection": self.bakeoff_collection,
                "scenarios": tuple(run.to_safe_dict() for run in self.scenarios),
                "decision": self.decision.value,
                "winner": self.winner,
                "python_rrf_default": self.python_rrf_default,
                "nomic_kept_as_fallback": self.nomic_kept_as_fallback,
                "safety": dict(self.safety),
            }
        )


class OllamaEmbeddingClient:
    """Async client for safe, batched Ollama ``/api/embed`` calls."""

    def __init__(
        self,
        *,
        base_url: str = OLLAMA_DEFAULT_BASE_URL,
        model: str,
        dimensions: int | None,
        keep_alive: str | None = "30m",
        timeout_s: float = 120.0,
        batch_size: int = 8,
        query_instruction: str | None = QWEN3_QUERY_INSTRUCTION,
        truncate: bool = True,
        max_concurrency: int = 1,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        _validate_text(base_url, "base_url")
        _validate_text(model, "model")
        if dimensions is not None and dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self.keep_alive = keep_alive
        self.timeout_s = timeout_s
        self.batch_size = batch_size
        self.query_instruction = query_instruction
        self.truncate = truncate
        self._client = client
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatchResult:
        """Embed documents without query instruction."""
        return await self._embed_batch(texts)

    async def embed_queries(self, queries: Sequence[str]) -> EmbeddingBatchResult:
        """Embed queries with Qwen3 instruction formatting when configured."""
        formatted = tuple(format_qwen3_query(query, self.query_instruction) for query in queries)
        return await self._embed_batch(formatted)

    async def preload_model(self) -> OllamaModelLoadResult:
        """Warm the model with a safe probe text and configured keep_alive."""
        result = await self._embed_batch(("probe",))
        return OllamaModelLoadResult(
            model=self.model,
            dimensions=result.dimensions,
            keep_alive=self.keep_alive,
            load_duration_ns=result.load_duration_ns,
            total_duration_ns=result.total_duration_ns,
            loaded=bool(result.embeddings),
        )

    async def unload_model(self) -> OllamaModelUnloadResult:
        """Request model unload explicitly; never called automatically."""
        payload = build_embed_payload(
            model=self.model,
            inputs=("probe",),
            dimensions=self.dimensions,
            keep_alive="0",
            truncate=self.truncate,
        )
        data = await self._post_embed(payload)
        return OllamaModelUnloadResult(
            model=self.model,
            unloaded_requested=True,
            total_duration_ns=_int_or_none(data.get("total_duration")),
        )

    async def _embed_batch(self, texts: Sequence[str]) -> EmbeddingBatchResult:
        if not texts:
            raise ValueError("texts must not be empty")
        for item in texts:
            _validate_text(item, "input")
        payload = build_embed_payload(
            model=self.model,
            inputs=tuple(texts),
            dimensions=self.dimensions,
            keep_alive=self.keep_alive,
            truncate=self.truncate,
        )
        data = await self._post_embed(payload)
        raw_embeddings = data.get("embeddings")
        if not isinstance(raw_embeddings, list) or not raw_embeddings:
            raise ValueError("Ollama response did not contain embeddings")
        embeddings = tuple(tuple(float(value) for value in vector) for vector in raw_embeddings)
        dimensions = len(embeddings[0])
        return EmbeddingBatchResult(
            model=self.model,
            dimensions=dimensions,
            count=len(embeddings),
            batch_size=len(texts),
            keep_alive=self.keep_alive,
            load_duration_ns=_int_or_none(data.get("load_duration")),
            total_duration_ns=_int_or_none(data.get("total_duration")),
            prompt_eval_count=_int_or_none(data.get("prompt_eval_count")),
            embeddings=embeddings,
        )

    async def _post_embed(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        async with self._semaphore:
            if self._client is None:
                async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_s) as client:
                    response = await client.post(OLLAMA_EMBED_PATH, json=dict(payload))
            else:
                response = await self._client.post(OLLAMA_EMBED_PATH, json=dict(payload), timeout=self.timeout_s)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, Mapping):
            raise ValueError("Ollama response must be a JSON object")
        return data


def qwen3_4b_contract() -> EmbeddingModelContract:
    """Return the Qwen3-Embedding-4B candidate contract."""
    return EmbeddingModelContract(
        model_id=QWEN3_4B_MODEL_ID,
        default_dimensions=QWEN3_4B_DEFAULT_DIMENSIONS,
        allowed_dimensions=QWEN3_4B_ALLOWED_DIMENSIONS,
        context_length=QWEN3_4B_CONTEXT_LENGTH,
        instruction_aware=QWEN3_4B_INSTRUCTION_AWARE,
        baseline_or_candidate="candidate",
    )


def nomic_contract() -> EmbeddingModelContract:
    """Return the Nomic baseline/fallback contract."""
    return EmbeddingModelContract(
        model_id=NOMIC_MODEL_ID,
        default_dimensions=NOMIC_DEFAULT_DIMENSIONS,
        allowed_dimensions=(NOMIC_DEFAULT_DIMENSIONS,),
        context_length=None,
        instruction_aware=False,
        baseline_or_candidate="baseline",
    )


def default_bakeoff_collection_spec() -> EmbeddingBakeoffCollectionSpec:
    """Return the preferred single-collection bakeoff schema contract."""
    return EmbeddingBakeoffCollectionSpec()


def declared_bakeoff_scenarios() -> tuple[EmbeddingBakeoffScenario, ...]:
    """Return the official Qwen3-4B vs Nomic scenario set."""
    return (
        EmbeddingBakeoffScenario("nomic_dense_only", NOMIC_MODEL_ID, "dense_only", 768, False, False, "batched"),
        EmbeddingBakeoffScenario("qwen3_4b_dense_only", QWEN3_4B_MODEL_ID, "dense_only", 2560, False, False, "batched"),
        EmbeddingBakeoffScenario("nomic_hybrid_python_rrf", NOMIC_MODEL_ID, "hybrid", 768, False, False, "batched"),
        EmbeddingBakeoffScenario("qwen3_4b_hybrid_python_rrf", QWEN3_4B_MODEL_ID, "hybrid", 2560, True, False, "batched"),
        EmbeddingBakeoffScenario("qwen3_4b_instruction_on", QWEN3_4B_MODEL_ID, "hybrid", 2560, True, False, "batched"),
        EmbeddingBakeoffScenario("qwen3_4b_instruction_off", QWEN3_4B_MODEL_ID, "hybrid", 2560, False, False, "batched"),
        EmbeddingBakeoffScenario("qwen3_4b_dimensions_1024", QWEN3_4B_MODEL_ID, "hybrid", 1024, True, False, "batched"),
        EmbeddingBakeoffScenario("qwen3_4b_dimensions_1536", QWEN3_4B_MODEL_ID, "hybrid", 1536, True, False, "batched"),
        EmbeddingBakeoffScenario("qwen3_4b_dimensions_2560", QWEN3_4B_MODEL_ID, "hybrid", 2560, True, False, "batched"),
        EmbeddingBakeoffScenario("cold_ollama_qwen3_4b", QWEN3_4B_MODEL_ID, "hybrid", 2560, True, True, "single"),
        EmbeddingBakeoffScenario("warm_ollama_qwen3_4b", QWEN3_4B_MODEL_ID, "hybrid", 2560, True, False, "single"),
        EmbeddingBakeoffScenario("batch_vs_single_embed", QWEN3_4B_MODEL_ID, "hybrid", 2560, True, False, "batch_vs_single"),
    )


def format_qwen3_query(query: str, instruction: str | None = QWEN3_QUERY_INSTRUCTION) -> str:
    """Apply the Qwen instruction format to a query; documents must not use this."""
    clean_query = _validate_text(query, "query")
    if instruction is None:
        return clean_query
    clean_instruction = _validate_text(instruction, "instruction")
    return f"Instruct: {clean_instruction}\nQuery: {clean_query}"


def build_embed_payload(
    *,
    model: str,
    inputs: Sequence[str],
    dimensions: int | None,
    keep_alive: str | None,
    truncate: bool = True,
) -> dict[str, object]:
    """Build an Ollama /api/embed payload using list batching."""
    _validate_text(model, "model")
    if not inputs:
        raise ValueError("inputs must not be empty")
    clean_inputs = tuple(_validate_text(item, "input") for item in inputs)
    payload: dict[str, object] = {
        "model": model,
        "input": list(clean_inputs),
        "truncate": truncate,
    }
    if dimensions is not None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        payload["dimensions"] = dimensions
    if keep_alive is not None:
        payload["keep_alive"] = _validate_text(keep_alive, "keep_alive")
    return payload


def parse_ollama_version(raw: str) -> str | None:
    """Extract a semantic version from Ollama CLI/API text."""
    clean = raw.strip()
    if not clean:
        return None
    for token in clean.replace(",", " ").split():
        candidate = token.removeprefix("v")
        if _looks_like_version(candidate):
            return candidate
    return clean.removeprefix("v") if _looks_like_version(clean.removeprefix("v")) else None


def select_latest_stable(
    releases: Sequence[str],
    *,
    allow_prerelease: bool = False,
    known_prereleases: frozenset[str] = OLLAMA_KNOWN_PRERELEASES,
) -> str | None:
    """Select the highest stable release unless prereleases are explicitly allowed."""
    parsed: list[tuple[tuple[int, int, int], str, bool]] = []
    for release in releases:
        normalized = release.strip().removeprefix("v")
        is_prerelease = (
            any(marker in normalized for marker in ("-", "rc", "beta", "alpha"))
            or normalized in known_prereleases
        )
        if is_prerelease and not allow_prerelease:
            continue
        base = normalized.split("-", maxsplit=1)[0]
        parts = base.split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            continue
        parsed.append(((int(parts[0]), int(parts[1]), int(parts[2])), normalized, is_prerelease))
    if not parsed:
        return None
    parsed.sort(key=lambda item: item[0])
    return parsed[-1][1]


def expected_dimension_for_model(model: str, dimensions: int | None = None) -> int | None:
    """Return expected output dimension for known models."""
    if model == QWEN3_4B_MODEL_ID:
        return dimensions or QWEN3_4B_DEFAULT_DIMENSIONS
    if model in {NOMIC_MODEL_ID, "nomic-embed-text:latest"}:
        return NOMIC_DEFAULT_DIMENSIONS
    return None


def decide_embedding_candidate(
    *,
    qwen3_available: bool,
    qwen3_ndcg_at_5: float | None,
    nomic_ndcg_at_5: float | None,
    qwen3_recall_at_10: float | None,
    nomic_recall_at_10: float | None,
    qwen3_total_p95_ms: float | None,
    nomic_total_p95_ms: float | None,
    memory_ok: bool | None,
) -> EmbeddingCandidateDecision:
    """Decide Qwen3-4B vs Nomic using conservative D2P thresholds."""
    if not qwen3_available:
        return EmbeddingCandidateDecision.INCONCLUSIVE_QWEN3_4B_UNAVAILABLE
    required = (
        qwen3_ndcg_at_5,
        nomic_ndcg_at_5,
        qwen3_recall_at_10,
        nomic_recall_at_10,
        qwen3_total_p95_ms,
        nomic_total_p95_ms,
    )
    if any(value is None for value in required):
        return EmbeddingCandidateDecision.QWEN3_4B_EXPERIMENTAL_ONLY
    assert qwen3_ndcg_at_5 is not None
    assert nomic_ndcg_at_5 is not None
    assert qwen3_recall_at_10 is not None
    assert nomic_recall_at_10 is not None
    assert qwen3_total_p95_ms is not None
    assert nomic_total_p95_ms is not None
    if memory_ok is False or qwen3_total_p95_ms > nomic_total_p95_ms * 2.0:
        return EmbeddingCandidateDecision.DEFER_DUE_TO_LATENCY_OR_MEMORY
    ndcg_gain = qwen3_ndcg_at_5 - nomic_ndcg_at_5
    recall_not_worse = qwen3_recall_at_10 >= nomic_recall_at_10
    if recall_not_worse and ndcg_gain >= 0.01:
        return EmbeddingCandidateDecision.PROMOTE_QWEN3_4B_DEFAULT
    if recall_not_worse and ndcg_gain >= -0.005:
        return EmbeddingCandidateDecision.QWEN3_4B_EXPERIMENTAL_ONLY
    return EmbeddingCandidateDecision.KEEP_NOMIC_DEFAULT


def build_empty_bakeoff_summary(*, generated_at_utc: str | None = None) -> EmbeddingBakeoffSummary:
    """Build an artifact-only summary with declared scenarios and no invented metrics."""
    now = generated_at_utc or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    runs = tuple(
        EmbeddingBakeoffRun(scenario=scenario, metrics=EmbeddingBakeoffMetrics(), evidence_complete=False)
        for scenario in declared_bakeoff_scenarios()
    )
    return EmbeddingBakeoffSummary(
        schema_version=EMBEDDING_BAKEOFF_SUMMARY_SCHEMA_VERSION,
        generated_at_utc=now,
        artifact_only=True,
        live_benchmark_executed=False,
        bakeoff_collection=BAKEOFF_COLLECTION,
        scenarios=runs,
        decision=EmbeddingCandidateDecision.INCONCLUSIVE_QWEN3_4B_UNAVAILABLE,
        winner=None,
        python_rrf_default=True,
        nomic_kept_as_fallback=True,
    )


def bakeoff_csv_header() -> tuple[str, ...]:
    """Return stable CSV columns for embedding bakeoff rows."""
    return (
        "schema_version",
        "scenario_id",
        "model",
        "retrieval_mode",
        "dimensions",
        "instruction_enabled",
        "precision_at_5",
        "recall_at_10",
        "mrr",
        "ndcg_at_5",
        "embed_ms_p50",
        "embed_ms_p95",
        "search_ms_p50",
        "search_ms_p95",
        "fusion_ms",
        "total_ms_p50",
        "total_ms_p95",
        "load_duration_ns",
        "total_duration_ns",
        "prompt_eval_count",
        "batch_size",
        "keep_alive",
        "memory_snapshot_available",
        "collection_size_bytes",
        "model_size_bytes",
        "evidence_complete",
    )


def render_bakeoff_svg(summary: EmbeddingBakeoffSummary) -> str:
    """Render a small dependency-free SVG dashboard."""
    rows = "".join(
        f"<text x='24' y='{90 + i * 24}'>{_xml_escape(run.scenario.scenario_id)}: "
        f"{'complete' if run.evidence_complete else 'TBD'}</text>"
        for i, run in enumerate(summary.scenarios[:12])
    )
    return (
        "<svg xmlns='http://www.w3.org/2000/svg' width='960' height='420' role='img'>"
        "<rect width='960' height='420' fill='#f8fafc'/>"
        "<text x='24' y='36' font-size='22'>Qwen3-Embedding-4B vs Nomic Bakeoff</text>"
        "<text x='24' y='64'>Quality · Latency · Ollama · Resources · Decision</text>"
        f"{rows}"
        f"<text x='520' y='110'>Decision: {_xml_escape(summary.decision.value)}</text>"
        f"<text x='520' y='140'>Winner: {_xml_escape(str(summary.winner))}</text>"
        "<text x='520' y='170'>Python Weighted RRF: ground truth</text>"
        "<text x='520' y='200'>Nomic fallback: retained</text>"
        "</svg>"
    )


def build_pkd_machine_block(*, winner: str | None = None) -> dict[str, object]:
    """Return the PKD-D2P machine-readable decision block."""
    return {
        "schema_version": "pkd-d2p-qwen3-4b-vs-nomic-v1",
        "decision_type": "D2P",
        "reversible": True,
        "candidates": [NOMIC_MODEL_ID, QWEN3_4B_MODEL_ID],
        "qwen3_4b_dimensions": QWEN3_4B_DEFAULT_DIMENSIONS,
        "python_rrf_default": True,
        "winner": winner,
    }


def _safe_dict(payload: Mapping[str, object]) -> dict[str, object]:
    for key, value in payload.items():
        if key in FORBIDDEN_OUTPUT_KEYS:
            raise ValueError(f"forbidden output key: {key}")
        if isinstance(value, Mapping):
            _safe_dict(value)
        elif isinstance(value, tuple | list):
            for item in value:
                if isinstance(item, Mapping):
                    _safe_dict(item)
    return dict(payload)


def _validate_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    clean = value.strip()
    if not clean:
        raise ValueError(f"{field_name} must not be empty")
    if "\x00" in clean:
        raise ValueError(f"{field_name} must not contain null byte")
    return clean


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _looks_like_version(candidate: str) -> bool:
    parts = candidate.split(".")
    return len(parts) == 3 and all(part.isdigit() for part in parts)


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
