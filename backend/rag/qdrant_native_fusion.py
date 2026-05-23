"""Experimental Qdrant native RRF comparison contracts for Quimera.

Python ``RRFFusion`` remains the source of truth. This module only models an
opt-in laboratory adapter and pure comparison helpers for Qdrant native
RRF/Weighted RRF experiments. It does not import MCP, OpenTelemetry or
qdrant_client, and it never creates, deletes or upserts collections.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Protocol, runtime_checkable

BENCHMARK_COLLECTION = "quimera_benchmark_hybrid_118"
CANDIDATE_COLLECTION = "quimera_knowledge_v2"
LEGACY_COLLECTION = "quimera_knowledge"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
DEFAULT_RRF_K = 60.0
COMPARISON_SCHEMA_VERSION = "fusion-comparison-v1"

RetrievalProfileName = Literal["neutral", "semantic_hybrid", "lexical_hybrid"]
NativeFusionMode = Literal["rrf", "weighted_rrf"]
FusionBackend = Literal["python_rrf", "qdrant_rrf", "qdrant_weighted_rrf"]

FORBIDDEN_SAFE_KEYS = frozenset(
    {
        "answer",
        "chunk_text",
        "content",
        "dense_vector",
        "document",
        "documents",
        "embedding",
        "embeddings",
        "message",
        "messages",
        "payload",
        "points",
        "prompt",
        "query",
        "query_text",
        "raw_text",
        "response",
        "sparse_vector",
        "text",
        "vector",
        "vectors",
    }
)

_TICKER_RE = re.compile(r"\b[A-Z]{4}\d{1,2}\b")
_ACRONYMS = frozenset({"CRI", "CRA", "CDI", "IPCA", "CDB", "FII", "ETF", "LCI", "LCA", "DY", "FGC"})
_QUESTION_PREFIXES = frozenset({"qual", "como", "quando", "onde", "por que", "porque", "explique"})


class NativeFusionDisabled(RuntimeError):
    """Raised when the experimental native adapter is used while disabled."""


class NativeFusionError(RuntimeError):
    """Raised for sanitized native fusion failures."""


@runtime_checkable
class SparseVectorLike(Protocol):
    """Minimal sparse vector shape used by Qdrant native fusion builders."""

    @property
    def indices(self) -> Sequence[int]:
        """Sparse vector indices."""
        ...

    @property
    def values(self) -> Sequence[float]:
        """Sparse vector values."""
        ...


class NativeFusionClientProtocol(Protocol):
    """Minimal Qdrant Query API client contract."""

    async def query_points(
        self,
        *,
        collection_name: str,
        prefetch: Sequence[object],
        query: object,
        limit: int,
        with_payload: bool = True,
    ) -> object:
        """Run a non-mutating Query API request."""
        ...


class FusionRunnerProtocol(Protocol):
    """Common runner contract for Python and native fusion comparison."""

    async def retrieve(
        self,
        *,
        query_id: str,
        dense_vector: Sequence[float],
        sparse_vector: SparseVectorLike,
        top_k: int,
    ) -> Sequence["FusionCandidate"]:
        """Return already-fused candidates for one query."""
        ...


@dataclass(frozen=True, slots=True)
class RetrievalProfile:
    """Weighted RRF profile for future dual-profile MCP retrieval."""

    name: RetrievalProfileName
    dense_weight: float
    sparse_weight: float
    k: float
    description: str
    intended_query_style: str

    def __post_init__(self) -> None:
        if self.name not in {"neutral", "semantic_hybrid", "lexical_hybrid"}:
            raise ValueError("unsupported retrieval profile")
        object.__setattr__(self, "dense_weight", _validate_non_negative_float(self.dense_weight, "dense_weight"))
        object.__setattr__(self, "sparse_weight", _validate_non_negative_float(self.sparse_weight, "sparse_weight"))
        object.__setattr__(self, "k", _validate_positive_float(self.k, "k"))
        if self.dense_weight == 0.0 and self.sparse_weight == 0.0:
            raise ValueError("at least one RRF weight must be positive")
        object.__setattr__(self, "description", _validate_text(self.description, "description"))
        object.__setattr__(self, "intended_query_style", _validate_text(self.intended_query_style, "intended_query_style"))

    def to_safe_dict(self) -> dict[str, object]:
        """Return a safe profile mapping."""

        return _assert_safe_dict(
            {
                "name": self.name,
                "dense_weight": self.dense_weight,
                "sparse_weight": self.sparse_weight,
                "k": self.k,
                "description": self.description,
                "intended_query_style": self.intended_query_style,
            }
        )


def _validate_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if "\x00" in value:
        raise ValueError(f"{field_name} cannot contain null bytes")
    clean = value.strip()
    if not clean:
        raise ValueError(f"{field_name} cannot be empty")
    return clean


def _validate_finite_float(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    clean = float(value)
    if not math.isfinite(clean):
        raise ValueError(f"{field_name} must be finite")
    return clean


def _validate_non_negative_float(value: float, field_name: str) -> float:
    clean = _validate_finite_float(value, field_name)
    if clean < 0.0:
        raise ValueError(f"{field_name} must be >= 0")
    return clean


def _validate_positive_float(value: float, field_name: str) -> float:
    clean = _validate_finite_float(value, field_name)
    if clean <= 0.0:
        raise ValueError(f"{field_name} must be > 0")
    return clean


NEUTRAL_PROFILE = RetrievalProfile(
    name="neutral",
    dense_weight=1.0,
    sparse_weight=1.0,
    k=DEFAULT_RRF_K,
    description="Neutral dense/sparse RRF profile.",
    intended_query_style="ambiguous_or_balanced",
)
SEMANTIC_HYBRID_PROFILE = RetrievalProfile(
    name="semantic_hybrid",
    dense_weight=1.30,
    sparse_weight=1.00,
    k=DEFAULT_RRF_K,
    description="Dense-heavy profile for human natural-language queries.",
    intended_query_style="human_natural_language",
)
LEXICAL_HYBRID_PROFILE = RetrievalProfile(
    name="lexical_hybrid",
    dense_weight=1.00,
    sparse_weight=1.40,
    k=DEFAULT_RRF_K,
    description="Sparse-heavy profile for ticker/acronym/code-heavy queries.",
    intended_query_style="ticker_acronym_identifier_heavy",
)


@dataclass(frozen=True, slots=True)
class NativeFusionConfig:
    """Opt-in native fusion adapter config."""

    collection_name: str = BENCHMARK_COLLECTION
    dense_vector_name: str = DENSE_VECTOR_NAME
    sparse_vector_name: str = SPARSE_VECTOR_NAME
    search_top_k: int = 20
    return_top_k: int = 10
    fusion_mode: NativeFusionMode = "rrf"
    profile: RetrievalProfile = NEUTRAL_PROFILE
    enabled: bool = False
    prefer_grpc: bool | None = None

    def __post_init__(self) -> None:
        clean_collection = _validate_text(self.collection_name, "collection_name")
        if clean_collection in {CANDIDATE_COLLECTION, LEGACY_COLLECTION}:
            raise ValueError("protected collections cannot be used for native fusion")
        object.__setattr__(self, "collection_name", clean_collection)
        object.__setattr__(self, "dense_vector_name", _validate_text(self.dense_vector_name, "dense_vector_name"))
        object.__setattr__(self, "sparse_vector_name", _validate_text(self.sparse_vector_name, "sparse_vector_name"))
        if self.dense_vector_name == self.sparse_vector_name:
            raise ValueError("dense_vector_name and sparse_vector_name must differ")
        object.__setattr__(self, "search_top_k", _validate_positive_int(self.search_top_k, "search_top_k"))
        object.__setattr__(self, "return_top_k", _validate_positive_int(self.return_top_k, "return_top_k"))
        if self.search_top_k < self.return_top_k:
            raise ValueError("search_top_k must be >= return_top_k")
        if self.fusion_mode not in {"rrf", "weighted_rrf"}:
            raise ValueError("fusion_mode must be rrf or weighted_rrf")
        if not isinstance(self.profile, RetrievalProfile):
            raise TypeError("profile must be RetrievalProfile")
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be a bool")
        if self.prefer_grpc is not None and not isinstance(self.prefer_grpc, bool):
            raise TypeError("prefer_grpc must be a bool or None")


@dataclass(frozen=True, slots=True)
class FusionCandidate:
    """One normalized fused candidate from Python or native Qdrant RRF."""

    result_id: str
    doc_id: str
    rank: int
    score: float | None
    backend: FusionBackend
    source: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "result_id", _validate_text(self.result_id, "result_id"))
        object.__setattr__(self, "doc_id", _validate_text(self.doc_id, "doc_id"))
        object.__setattr__(self, "rank", _validate_positive_int(self.rank, "rank"))
        object.__setattr__(
            self,
            "score",
            None if self.score is None else _validate_finite_float(self.score, "score"),
        )
        if self.backend not in {"python_rrf", "qdrant_rrf", "qdrant_weighted_rrf"}:
            raise ValueError("unsupported backend")
        if self.source is not None:
            object.__setattr__(self, "source", _validate_text(self.source, "source"))

    def to_safe_dict(self) -> dict[str, object]:
        """Return a safe candidate mapping without payload data."""

        return _assert_safe_dict(
            {
                "result_id": self.result_id,
                "doc_id": self.doc_id,
                "rank": self.rank,
                "score": self.score,
                "backend": self.backend,
                "source": self.source,
            }
        )


@dataclass(frozen=True, slots=True)
class FusionDivergence:
    """Safe pairwise divergence summary for Python vs native RRF."""

    query_id: str
    profile_name: str
    python_top_ids: tuple[str, ...]
    native_top_ids: tuple[str, ...]
    overlap_at_k: float
    jaccard_at_k: float
    order_equal: bool
    set_equal: bool
    rank_delta_mean: float | None
    rank_delta_max: int | None
    score_correlation_hint: float | None
    tie_break_notes: tuple[str, ...]
    latency_python_ms: float | None
    latency_native_ms: float | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "query_id", _validate_text(self.query_id, "query_id"))
        object.__setattr__(self, "profile_name", _validate_text(self.profile_name, "profile_name"))
        object.__setattr__(self, "python_top_ids", tuple(_validate_text(item, "python_top_id") for item in self.python_top_ids))
        object.__setattr__(self, "native_top_ids", tuple(_validate_text(item, "native_top_id") for item in self.native_top_ids))
        object.__setattr__(self, "overlap_at_k", _validate_ratio(self.overlap_at_k, "overlap_at_k"))
        object.__setattr__(self, "jaccard_at_k", _validate_ratio(self.jaccard_at_k, "jaccard_at_k"))
        if not isinstance(self.order_equal, bool):
            raise TypeError("order_equal must be a bool")
        if not isinstance(self.set_equal, bool):
            raise TypeError("set_equal must be a bool")
        object.__setattr__(
            self,
            "rank_delta_mean",
            None
            if self.rank_delta_mean is None
            else _validate_non_negative_float(self.rank_delta_mean, "rank_delta_mean"),
        )
        if self.rank_delta_max is not None:
            object.__setattr__(self, "rank_delta_max", _validate_non_negative_int(self.rank_delta_max, "rank_delta_max"))
        object.__setattr__(
            self,
            "score_correlation_hint",
            None
            if self.score_correlation_hint is None
            else _validate_ratio(self.score_correlation_hint, "score_correlation_hint"),
        )
        object.__setattr__(self, "tie_break_notes", tuple(_validate_text(note, "tie_break_note") for note in self.tie_break_notes))
        for field_name in ("latency_python_ms", "latency_native_ms"):
            value = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                None if value is None else _validate_non_negative_float(value, field_name),
            )

    def to_safe_dict(self) -> dict[str, object]:
        """Return a JSON-friendly divergence mapping."""

        return _assert_safe_dict(
            {
                "query_id": self.query_id,
                "profile_name": self.profile_name,
                "python_top_ids": list(self.python_top_ids),
                "native_top_ids": list(self.native_top_ids),
                "overlap_at_k": self.overlap_at_k,
                "jaccard_at_k": self.jaccard_at_k,
                "order_equal": self.order_equal,
                "set_equal": self.set_equal,
                "rank_delta_mean": self.rank_delta_mean,
                "rank_delta_max": self.rank_delta_max,
                "score_correlation_hint": self.score_correlation_hint,
                "tie_break_notes": list(self.tie_break_notes),
                "latency_python_ms": self.latency_python_ms,
                "latency_native_ms": self.latency_native_ms,
            }
        )


@dataclass(frozen=True, slots=True)
class FusionComparisonEvent:
    """Safe OTel-friendly comparison event without query text."""

    schema_version: str = COMPARISON_SCHEMA_VERSION
    query_hash: str = ""
    query_id: str = ""
    profile_name: str = ""
    python_backend: str = "python_rrf"
    native_backend: str = "qdrant_rrf"
    overlap_at_k: float = 0.0
    order_equal: bool = False
    latency_python_ms: float | None = None
    latency_native_ms: float | None = None
    qdrant_server_version: str | None = None
    qdrant_client_version: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != COMPARISON_SCHEMA_VERSION:
            raise ValueError("unsupported schema_version")
        object.__setattr__(self, "query_hash", _validate_text(self.query_hash, "query_hash"))
        object.__setattr__(self, "query_id", _validate_text(self.query_id, "query_id"))
        object.__setattr__(self, "profile_name", _validate_text(self.profile_name, "profile_name"))
        object.__setattr__(self, "python_backend", _validate_text(self.python_backend, "python_backend"))
        object.__setattr__(self, "native_backend", _validate_text(self.native_backend, "native_backend"))
        object.__setattr__(self, "overlap_at_k", _validate_ratio(self.overlap_at_k, "overlap_at_k"))
        if not isinstance(self.order_equal, bool):
            raise TypeError("order_equal must be a bool")
        for field_name in ("latency_python_ms", "latency_native_ms"):
            value = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                None if value is None else _validate_non_negative_float(value, field_name),
            )
        for field_name in ("qdrant_server_version", "qdrant_client_version"):
            value = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                None if value is None else _validate_text(value, field_name),
            )

    def to_safe_dict(self) -> dict[str, object]:
        """Return a safe comparison event mapping."""

        return _assert_safe_dict(
            {
                "schema_version": self.schema_version,
                "query_hash": self.query_hash,
                "query_id": self.query_id,
                "profile_name": self.profile_name,
                "python_backend": self.python_backend,
                "native_backend": self.native_backend,
                "overlap_at_k": self.overlap_at_k,
                "order_equal": self.order_equal,
                "latency_python_ms": self.latency_python_ms,
                "latency_native_ms": self.latency_native_ms,
                "qdrant_server_version": self.qdrant_server_version,
                "qdrant_client_version": self.qdrant_client_version,
            }
        )


def retrieval_profile_registry() -> Mapping[str, RetrievalProfile]:
    """Return immutable retrieval profile registry."""

    return MappingProxyType(
        {
            NEUTRAL_PROFILE.name: NEUTRAL_PROFILE,
            SEMANTIC_HYBRID_PROFILE.name: SEMANTIC_HYBRID_PROFILE,
            LEXICAL_HYBRID_PROFILE.name: LEXICAL_HYBRID_PROFILE,
        }
    )


def default_retrieval_profile() -> RetrievalProfile:
    """Return the neutral future MCP retrieval profile."""

    return NEUTRAL_PROFILE


def get_retrieval_profile(name: str) -> RetrievalProfile:
    """Return retrieval profile by name."""

    clean_name = _validate_text(name, "profile_name")
    try:
        return retrieval_profile_registry()[clean_name]
    except KeyError as exc:
        raise KeyError("unknown retrieval profile") from exc


def profile_to_python_rrf_weights(profile: RetrievalProfile) -> dict[str, float]:
    """Return Python RRFFusion-compatible weights."""

    return {
        "dense": profile.dense_weight,
        "sparse": profile.sparse_weight,
        "k": profile.k,
    }


def profile_to_qdrant_prefetch_weights(
    profile: RetrievalProfile,
    prefetch_order: Sequence[str],
) -> list[float]:
    """Return native weighted RRF weights in Qdrant prefetch order."""

    weights_by_channel = {
        DENSE_VECTOR_NAME: profile.dense_weight,
        SPARSE_VECTOR_NAME: profile.sparse_weight,
    }
    weights: list[float] = []
    for channel in prefetch_order:
        clean_channel = _validate_text(channel, "prefetch_channel")
        if clean_channel not in weights_by_channel:
            raise ValueError("unsupported prefetch channel")
        weights.append(weights_by_channel[clean_channel])
    return weights


def classify_query_profile(query: str) -> RetrievalProfile:
    """Classify query style deterministically without LLM calls."""

    clean_query = _validate_text(query, "query")
    words = clean_query.split()
    ticker_hits = len(_TICKER_RE.findall(clean_query))
    acronym_hits = sum(1 for token in words if token.strip("?:,.;").upper() in _ACRONYMS)
    numeric_hits = sum(1 for token in words if any(char.isdigit() for char in token))
    uppercase_tokens = [
        token
        for token in words
        if len(token) > 1 and token.isupper() and any(char.isalpha() for char in token)
    ]
    uppercase_ratio = len(uppercase_tokens) / max(1, len(words))
    lower_query = clean_query.casefold()
    natural_question = any(lower_query.startswith(prefix) for prefix in _QUESTION_PREFIXES) or "?" in clean_query

    if ticker_hits > 0 or acronym_hits >= 2 or numeric_hits >= 2 or uppercase_ratio >= 0.5:
        return LEXICAL_HYBRID_PROFILE
    if natural_question and len(words) >= 6:
        return SEMANTIC_HYBRID_PROFILE
    return NEUTRAL_PROFILE


def make_query_hash(query: str) -> str:
    """Return short SHA-256 query hash without exposing query text."""

    clean_query = _validate_text(query, "query")
    return hashlib.sha256(clean_query.encode("utf-8")).hexdigest()[:16]


def build_prefetch_plan(
    *,
    dense_vector: Sequence[float],
    sparse_vector: SparseVectorLike,
    config: NativeFusionConfig,
    prefetch_order: tuple[str, str] = (SPARSE_VECTOR_NAME, DENSE_VECTOR_NAME),
) -> tuple[Mapping[str, object], ...]:
    """Build conceptual dense/sparse Query API prefetch plan."""

    _validate_dense_vector(dense_vector)
    _validate_sparse_vector(sparse_vector)
    if set(prefetch_order) != {SPARSE_VECTOR_NAME, DENSE_VECTOR_NAME}:
        raise ValueError("prefetch_order must contain sparse and dense")
    plans: list[Mapping[str, object]] = []
    for channel in prefetch_order:
        if channel == SPARSE_VECTOR_NAME:
            plans.append(
                MappingProxyType(
                    {
                        "using": config.sparse_vector_name,
                        "limit": config.search_top_k,
                        "query_kind": "sparse",
                    }
                )
            )
        else:
            plans.append(
                MappingProxyType(
                    {
                        "using": config.dense_vector_name,
                        "limit": config.search_top_k,
                        "query_kind": "dense",
                    }
                )
            )
    return tuple(plans)


def build_rrf_query_config(config: NativeFusionConfig) -> Mapping[str, object]:
    """Build conceptual native RRF query config."""

    rrf: dict[str, object] = {"k": config.profile.k}
    if config.fusion_mode == "weighted_rrf":
        rrf["weights"] = profile_to_qdrant_prefetch_weights(
            config.profile,
            (SPARSE_VECTOR_NAME, DENSE_VECTOR_NAME),
        )
    return MappingProxyType({"rrf": MappingProxyType(rrf)})


class QdrantNativeFusionRetriever:
    """Experimental opt-in Qdrant native RRF retriever adapter."""

    def __init__(
        self,
        *,
        client: NativeFusionClientProtocol,
        config: NativeFusionConfig,
    ) -> None:
        self._client = client
        self._config = config

    async def retrieve(
        self,
        *,
        dense_vector: Sequence[float],
        sparse_vector: SparseVectorLike,
        query_id: str,
    ) -> tuple[FusionCandidate, ...]:
        """Run an experimental native fusion query and normalize candidates."""

        _validate_text(query_id, "query_id")
        if not self._config.enabled:
            raise NativeFusionDisabled("native fusion is disabled")
        prefetch = build_prefetch_plan(
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            config=self._config,
        )
        query = build_rrf_query_config(self._config)
        try:
            response = await self._client.query_points(
                collection_name=self._config.collection_name,
                prefetch=prefetch,
                query=query,
                limit=self._config.return_top_k,
                with_payload=True,
            )
        except Exception as exc:
            raise NativeFusionError("native fusion query failed") from exc
        return _normalize_query_points_response(response, self._backend())

    def _backend(self) -> FusionBackend:
        return "qdrant_weighted_rrf" if self._config.fusion_mode == "weighted_rrf" else "qdrant_rrf"


def compute_overlap_at_k(
    python_ids: Sequence[str],
    native_ids: Sequence[str],
    k: int,
) -> float:
    """Return overlap ratio over the top-k Python set."""

    clean_k = _validate_positive_int(k, "k")
    left = set(_top_ids(python_ids, clean_k))
    right = set(_top_ids(native_ids, clean_k))
    if not left and not right:
        return 1.0
    if not left:
        return 0.0
    return len(left & right) / len(left)


def compute_jaccard_at_k(
    python_ids: Sequence[str],
    native_ids: Sequence[str],
    k: int,
) -> float:
    """Return top-k Jaccard overlap."""

    clean_k = _validate_positive_int(k, "k")
    left = set(_top_ids(python_ids, clean_k))
    right = set(_top_ids(native_ids, clean_k))
    union = left | right
    if not union:
        return 1.0
    return len(left & right) / len(union)


def compute_rank_delta_stats(
    python_ids: Sequence[str],
    native_ids: Sequence[str],
    k: int,
) -> tuple[float | None, int | None]:
    """Return mean/max absolute rank delta for shared top-k ids."""

    clean_k = _validate_positive_int(k, "k")
    left = _top_ids(python_ids, clean_k)
    right = _top_ids(native_ids, clean_k)
    native_rank = {item: index + 1 for index, item in enumerate(right)}
    deltas = [
        abs((index + 1) - native_rank[item])
        for index, item in enumerate(left)
        if item in native_rank
    ]
    if not deltas:
        return None, None
    return sum(deltas) / len(deltas), max(deltas)


def compute_fusion_divergence(
    *,
    query_id: str,
    profile: RetrievalProfile,
    python_results: Sequence[FusionCandidate],
    native_results: Sequence[FusionCandidate],
    top_k: int,
    latency_python_ms: float | None = None,
    latency_native_ms: float | None = None,
) -> FusionDivergence:
    """Compute safe pairwise Python-vs-native fusion divergence."""

    clean_k = _validate_positive_int(top_k, "top_k")
    python_ids = tuple(candidate.result_id for candidate in python_results[:clean_k])
    native_ids = tuple(candidate.result_id for candidate in native_results[:clean_k])
    order_equal = python_ids == native_ids
    set_equal = set(python_ids) == set(native_ids)
    mean_delta, max_delta = compute_rank_delta_stats(python_ids, native_ids, clean_k)
    tie_break_notes: list[str] = []
    if set_equal and not order_equal:
        tie_break_notes.append("same_set_different_order")
    if not set_equal:
        tie_break_notes.append("different_result_set")

    return FusionDivergence(
        query_id=query_id,
        profile_name=profile.name,
        python_top_ids=python_ids,
        native_top_ids=native_ids,
        overlap_at_k=compute_overlap_at_k(python_ids, native_ids, clean_k),
        jaccard_at_k=compute_jaccard_at_k(python_ids, native_ids, clean_k),
        order_equal=order_equal,
        set_equal=set_equal,
        rank_delta_mean=mean_delta,
        rank_delta_max=max_delta,
        score_correlation_hint=None,
        tie_break_notes=tuple(tie_break_notes),
        latency_python_ms=latency_python_ms,
        latency_native_ms=latency_native_ms,
    )


async def compare_fusion_for_query(
    *,
    query_id: str,
    dense_vector: Sequence[float],
    sparse_vector: SparseVectorLike,
    python_runner: FusionRunnerProtocol,
    native_runner: FusionRunnerProtocol,
    profile: RetrievalProfile,
    top_k: int,
) -> FusionDivergence:
    """Run pairwise fusion comparison for one query id."""

    clean_query_id = _validate_text(query_id, "query_id")
    python_results = await python_runner.retrieve(
        query_id=clean_query_id,
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        top_k=top_k,
    )
    native_results = await native_runner.retrieve(
        query_id=clean_query_id,
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        top_k=top_k,
    )
    return compute_fusion_divergence(
        query_id=clean_query_id,
        profile=profile,
        python_results=python_results,
        native_results=native_results,
        top_k=top_k,
    )


async def retrieve_native_with_python_fallback(
    *,
    native_runner: FusionRunnerProtocol,
    python_runner: FusionRunnerProtocol,
    query_id: str,
    dense_vector: Sequence[float],
    sparse_vector: SparseVectorLike,
    top_k: int,
) -> tuple[str, Sequence[FusionCandidate]]:
    """Try native fusion, falling back to Python RRF on sanitized failure."""

    try:
        native_results = await native_runner.retrieve(
            query_id=query_id,
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            top_k=top_k,
        )
        return "qdrant_native", native_results
    except Exception:
        python_results = await python_runner.retrieve(
            query_id=query_id,
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            top_k=top_k,
        )
        return "python_rrf", python_results


def build_rrf_monitoring_attributes(
    *,
    backend: str,
    fusion_mode: str,
    profile: RetrievalProfile,
    native_enabled: bool,
) -> dict[str, object]:
    """Return OTel-compatible fusion attributes without importing OTel."""

    return _assert_safe_dict(
        {
            "rag.fusion.backend": _validate_text(backend, "backend"),
            "rag.fusion.mode": _validate_text(fusion_mode, "fusion_mode"),
            "rag.fusion.profile": profile.name,
            "rag.fusion.dense_weight": profile.dense_weight,
            "rag.fusion.sparse_weight": profile.sparse_weight,
            "rag.fusion.k": profile.k,
            "rag.fusion.python_source_of_truth": True,
            "rag.fusion.native_enabled": bool(native_enabled),
        }
    )


def fusion_comparison_otel_attributes(
    divergence: FusionDivergence,
) -> dict[str, object]:
    """Return OTel-compatible attributes for one comparison row."""

    return _assert_safe_dict(
        {
            "rag.fusion.overlap_at_k": divergence.overlap_at_k,
            "rag.fusion.order_equal": divergence.order_equal,
            "rag.fusion.set_equal": divergence.set_equal,
            "rag.fusion.rank_delta_mean": divergence.rank_delta_mean,
            "rag.fusion.profile": divergence.profile_name,
        }
    )


def _normalize_query_points_response(
    response: object,
    backend: FusionBackend,
) -> tuple[FusionCandidate, ...]:
    points = _extract_points(response)
    candidates: list[FusionCandidate] = []
    for index, point in enumerate(points):
        result_id = _extract_point_id(point)
        payload = _extract_payload(point)
        doc_id = payload.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id.strip():
            raise NativeFusionError("native fusion point is missing doc_id")
        candidates.append(
            FusionCandidate(
                result_id=result_id,
                doc_id=doc_id,
                rank=index + 1,
                score=_extract_score(point),
                backend=backend,
                source="qdrant_native",
            )
        )
    return tuple(candidates)


def _extract_points(response: object) -> Sequence[object]:
    if isinstance(response, Mapping):
        points = response.get("points")
        if isinstance(points, Sequence) and not isinstance(points, (str, bytes, bytearray)):
            return points
        result = response.get("result")
        if isinstance(result, Mapping):
            nested = result.get("points")
            if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes, bytearray)):
                return nested
    points_attr = getattr(response, "points", None)
    if isinstance(points_attr, Sequence) and not isinstance(points_attr, (str, bytes, bytearray)):
        return points_attr
    return ()


def _extract_point_id(point: object) -> str:
    if isinstance(point, Mapping):
        point_id = point.get("id")
    else:
        point_id = getattr(point, "id", None)
    if point_id is None:
        raise NativeFusionError("native fusion point is missing id")
    return _validate_text(str(point_id), "point_id")


def _extract_payload(point: object) -> Mapping[str, object]:
    if isinstance(point, Mapping):
        payload = point.get("payload")
    else:
        payload = getattr(point, "payload", None)
    if isinstance(payload, Mapping):
        return payload
    return {}


def _extract_score(point: object) -> float | None:
    if isinstance(point, Mapping):
        score = point.get("score")
    else:
        score = getattr(point, "score", None)
    return None if score is None else _validate_finite_float(score, "score")


def _top_ids(ids: Sequence[str], k: int) -> tuple[str, ...]:
    return tuple(_validate_text(item, "result_id") for item in ids[:k])


def _validate_dense_vector(vector: Sequence[float]) -> None:
    if isinstance(vector, (str, bytes, bytearray)):
        raise TypeError("dense_vector must be a numeric sequence")
    for value in vector:
        _validate_finite_float(value, "dense_vector value")


def _validate_sparse_vector(vector: SparseVectorLike) -> None:
    if len(vector.indices) != len(vector.values):
        raise ValueError("sparse vector indices and values length mismatch")
    for index in vector.indices:
        _validate_non_negative_int(index, "sparse index")
    for value in vector.values:
        _validate_finite_float(value, "sparse value")


def _validate_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return value


def _validate_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


def _validate_ratio(value: float, field_name: str) -> float:
    clean = _validate_non_negative_float(value, field_name)
    if clean > 1.0:
        raise ValueError(f"{field_name} must be <= 1")
    return clean


def _assert_safe_dict(value: dict[str, object]) -> dict[str, object]:
    _assert_no_forbidden_keys(value)
    return value


def _assert_no_forbidden_keys(value: Mapping[str, object]) -> None:
    for key, item in value.items():
        if str(key).casefold() in FORBIDDEN_SAFE_KEYS:
            raise ValueError("safe dict contains forbidden key")
        if isinstance(item, Mapping):
            _assert_no_forbidden_keys(item)


__all__ = [
    "BENCHMARK_COLLECTION",
    "CANDIDATE_COLLECTION",
    "COMPARISON_SCHEMA_VERSION",
    "DENSE_VECTOR_NAME",
    "FusionCandidate",
    "FusionComparisonEvent",
    "FusionDivergence",
    "FusionRunnerProtocol",
    "LEXICAL_HYBRID_PROFILE",
    "LEGACY_COLLECTION",
    "NEUTRAL_PROFILE",
    "NativeFusionClientProtocol",
    "NativeFusionConfig",
    "NativeFusionDisabled",
    "NativeFusionError",
    "QdrantNativeFusionRetriever",
    "RetrievalProfile",
    "SEMANTIC_HYBRID_PROFILE",
    "SPARSE_VECTOR_NAME",
    "SparseVectorLike",
    "build_prefetch_plan",
    "build_rrf_monitoring_attributes",
    "build_rrf_query_config",
    "classify_query_profile",
    "compare_fusion_for_query",
    "compute_fusion_divergence",
    "compute_jaccard_at_k",
    "compute_overlap_at_k",
    "compute_rank_delta_stats",
    "default_retrieval_profile",
    "fusion_comparison_otel_attributes",
    "get_retrieval_profile",
    "make_query_hash",
    "profile_to_python_rrf_weights",
    "profile_to_qdrant_prefetch_weights",
    "retrieval_profile_registry",
    "retrieve_native_with_python_fallback",
]
