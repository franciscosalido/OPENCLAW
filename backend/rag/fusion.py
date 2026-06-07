"""Deterministic Weighted Reciprocal Rank Fusion for OPENCLAW RAG.

This module is intentionally pure Python: no Qdrant imports, no network calls,
no file I/O, no embeddings, no rerankers and no runtime auto-tuning.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isclose, isfinite
from types import MappingProxyType
from typing import Any, Final

SOURCE_DENSE: Final[str] = "dense"
SOURCE_SPARSE: Final[str] = "sparse"

DEFAULT_RRF_K: Final[float] = 60.0
DEFAULT_DENSE_WEIGHT: Final[float] = 1.0
DEFAULT_SPARSE_WEIGHT: Final[float] = 1.0


def _validate_numeric(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    clean_value = float(value)
    if not isfinite(clean_value):
        raise ValueError(f"{field_name} must be finite")
    return clean_value


def _validate_text_id(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if "\x00" in value:
        raise ValueError(f"{field_name} cannot contain null bytes")
    clean_value = value.strip()
    if not clean_value:
        raise ValueError(f"{field_name} cannot be blank")
    return clean_value


def _validate_weight(value: float, field_name: str) -> float:
    clean_value = _validate_numeric(value, field_name)
    if clean_value < 0.0:
        raise ValueError("RRF weights must be non-negative")
    return clean_value


def _validate_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value <= 0:
        if field_name == "RRF k":
            raise ValueError("RRF k must be > 0")
        raise ValueError(f"{field_name} must be >= 1")
    return value


def _validate_positive_float(value: float, field_name: str) -> float:
    clean_value = _validate_numeric(value, field_name)
    if clean_value <= 0.0:
        if field_name == "RRF k":
            raise ValueError("RRF k must be > 0")
        raise ValueError(f"{field_name} must be > 0")
    return clean_value


@dataclass(frozen=True, slots=True)
class RankedResult:
    """One retrieval result in an already-ranked list.

    ``rank`` is the only retrieval signal used by RRF. ``raw_score`` is kept
    for diagnostics and never participates in the fusion formula.
    """

    result_id: str
    doc_id: str
    rank: int
    raw_score: float | None = None
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        clean_result_id = _validate_text_id(self.result_id, "result_id")
        clean_doc_id = _validate_text_id(self.doc_id, "doc_id")
        clean_rank = _validate_positive_int(self.rank, "rank")
        clean_raw_score = (
            None
            if self.raw_score is None
            else _validate_optional_score(self.raw_score, "raw_score")
        )
        clean_payload = _freeze_payload(self.payload)

        object.__setattr__(self, "result_id", clean_result_id)
        object.__setattr__(self, "doc_id", clean_doc_id)
        object.__setattr__(self, "rank", clean_rank)
        object.__setattr__(self, "raw_score", clean_raw_score)
        object.__setattr__(self, "payload", clean_payload)


@dataclass(frozen=True, slots=True)
class RRFWeightProfile:
    """Immutable Weighted RRF configuration.

    ``k`` is stored as float to support future benchmark sweeps.
    """

    dense_weight: float = DEFAULT_DENSE_WEIGHT
    sparse_weight: float = DEFAULT_SPARSE_WEIGHT
    k: float = DEFAULT_RRF_K
    name: str = "default"

    def __post_init__(self) -> None:
        clean_name = _validate_text_id(self.name, "RRF profile name")
        clean_dense_weight = _validate_weight(self.dense_weight, "dense_weight")
        clean_sparse_weight = _validate_weight(self.sparse_weight, "sparse_weight")
        clean_k = _validate_positive_float(self.k, "RRF k")

        if clean_dense_weight == 0.0 and clean_sparse_weight == 0.0:
            raise ValueError("at least one RRF weight must be positive")

        object.__setattr__(self, "name", clean_name)
        object.__setattr__(self, "dense_weight", clean_dense_weight)
        object.__setattr__(self, "sparse_weight", clean_sparse_weight)
        object.__setattr__(self, "k", clean_k)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation."""

        return {
            "name": self.name,
            "dense_weight": self.dense_weight,
            "sparse_weight": self.sparse_weight,
            "k": self.k,
        }


DEFAULT_PROFILE: Final[RRFWeightProfile] = RRFWeightProfile()


@dataclass(frozen=True, slots=True)
class FusedResult:
    """Final result produced by Weighted RRF.

    ``first_seen_order`` is the 0-based index in the concatenated
    ``[*dense_results, *sparse_results]`` input sequence where ``result_id``
    first appeared.
    """

    result_id: str
    doc_id: str
    rrf_score: float
    dense_rank: int | None
    sparse_rank: int | None
    dense_contribution: float
    sparse_contribution: float
    best_rank: int
    first_seen_order: int
    dense_raw_score: float | None = None
    sparse_raw_score: float | None = None
    payload: Mapping[str, object] = field(default_factory=dict)
    sources: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        clean_result_id = _validate_text_id(self.result_id, "result_id")
        clean_doc_id = _validate_text_id(self.doc_id, "doc_id")
        clean_dense_rank = _validate_optional_rank(self.dense_rank, "dense_rank")
        clean_sparse_rank = _validate_optional_rank(self.sparse_rank, "sparse_rank")

        if clean_dense_rank is None and clean_sparse_rank is None:
            raise ValueError("at least one source rank must be present")

        clean_rrf_score = _validate_non_negative_float(self.rrf_score, "rrf_score")
        clean_dense_contribution = _validate_non_negative_float(
            self.dense_contribution,
            "dense_contribution",
        )
        clean_sparse_contribution = _validate_non_negative_float(
            self.sparse_contribution,
            "sparse_contribution",
        )
        if not isclose(
            clean_rrf_score,
            clean_dense_contribution + clean_sparse_contribution,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "rrf_score must equal dense_contribution + sparse_contribution"
            )
        clean_best_rank = _validate_positive_int(self.best_rank, "best_rank")
        clean_first_seen_order = _validate_non_negative_int(
            self.first_seen_order,
            "first_seen_order",
        )
        present_ranks = [
            rank for rank in (clean_dense_rank, clean_sparse_rank) if rank is not None
        ]
        if clean_best_rank != min(present_ranks):
            raise ValueError("best_rank must be the minimum present source rank")

        clean_sources = frozenset(_validate_source(source) for source in self.sources)
        if not clean_sources:
            raise ValueError("sources cannot be empty")
        expected_sources: set[str] = set()
        if clean_dense_rank is not None:
            expected_sources.add(SOURCE_DENSE)
        if clean_sparse_rank is not None:
            expected_sources.add(SOURCE_SPARSE)
        if clean_sources != expected_sources:
            raise ValueError("sources must match present source ranks")
        clean_dense_raw_score = (
            None
            if self.dense_raw_score is None
            else _validate_optional_score(self.dense_raw_score, "dense_raw_score")
        )
        clean_sparse_raw_score = (
            None
            if self.sparse_raw_score is None
            else _validate_optional_score(self.sparse_raw_score, "sparse_raw_score")
        )
        clean_payload = _freeze_payload(self.payload)

        object.__setattr__(self, "result_id", clean_result_id)
        object.__setattr__(self, "doc_id", clean_doc_id)
        object.__setattr__(self, "rrf_score", clean_rrf_score)
        object.__setattr__(self, "dense_rank", clean_dense_rank)
        object.__setattr__(self, "sparse_rank", clean_sparse_rank)
        object.__setattr__(self, "dense_contribution", clean_dense_contribution)
        object.__setattr__(self, "sparse_contribution", clean_sparse_contribution)
        object.__setattr__(self, "best_rank", clean_best_rank)
        object.__setattr__(self, "first_seen_order", clean_first_seen_order)
        object.__setattr__(self, "dense_raw_score", clean_dense_raw_score)
        object.__setattr__(self, "sparse_raw_score", clean_sparse_raw_score)
        object.__setattr__(self, "payload", clean_payload)
        object.__setattr__(self, "sources", clean_sources)

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-friendly representation."""

        return {
            "result_id": self.result_id,
            "doc_id": self.doc_id,
            "rrf_score": self.rrf_score,
            "dense_rank": self.dense_rank,
            "sparse_rank": self.sparse_rank,
            "dense_contribution": self.dense_contribution,
            "sparse_contribution": self.sparse_contribution,
            "best_rank": self.best_rank,
            "first_seen_order": self.first_seen_order,
            "dense_raw_score": self.dense_raw_score,
            "sparse_raw_score": self.sparse_raw_score,
            "sources": sorted(self.sources),
            "payload": dict(self.payload),
        }


@dataclass(slots=True)
class _RRFAccumulator:
    result_id: str
    doc_id: str
    first_seen_order: int
    rrf_score: float = 0.0
    dense_rank: int | None = None
    sparse_rank: int | None = None
    dense_contribution: float = 0.0
    sparse_contribution: float = 0.0
    dense_raw_score: float | None = None
    sparse_raw_score: float | None = None
    payload: Mapping[str, object] = field(default_factory=dict)
    payload_rank: int | None = None
    payload_source: str | None = None


def fuse(
    *,
    dense_results: Sequence[RankedResult],
    sparse_results: Sequence[RankedResult],
    profile: RRFWeightProfile = DEFAULT_PROFILE,
    limit: int | None = None,
) -> list[FusedResult]:
    """Fuse dense and sparse rankings with deterministic Weighted RRF.

    The function trusts ``RankedResult.rank``. Callers must assign ranks from
    the retrieval order before calling ``fuse()``; raw scores are diagnostic
    only and are never used in the RRF formula.

    ``first_seen_order`` in each output is the 0-based index in the
    concatenated ``[*dense_results, *sparse_results]`` input sequence where
    the ``result_id`` first appeared. Inputs are iterated as provided and are
    never sorted or mutated in place. ``limit`` is applied after full fusion
    and deterministic sorting.

    Disabled channels still advance the concatenated input boundary. For
    example, with ``dense_weight=0.0``, sparse-only results keep
    ``first_seen_order`` offsets after ``len(dense_results)``.
    """

    clean_limit = _validate_optional_limit(limit)
    accumulators: dict[str, _RRFAccumulator] = {}
    next_order = 0

    next_order = _consume_ranking(
        source=SOURCE_DENSE,
        results=dense_results,
        weight=profile.dense_weight,
        k=profile.k,
        accumulators=accumulators,
        start_order=next_order,
    )
    _consume_ranking(
        source=SOURCE_SPARSE,
        results=sparse_results,
        weight=profile.sparse_weight,
        k=profile.k,
        accumulators=accumulators,
        start_order=next_order,
    )

    fused = [_build_fused_result(accumulator) for accumulator in accumulators.values()]
    fused.sort(key=_fused_sort_key)
    return fused if clean_limit is None else fused[:clean_limit]


@dataclass(frozen=True, slots=True)
class RRFFusion:
    """Configurable Weighted RRF fusion object for dependency injection."""

    profile: RRFWeightProfile = DEFAULT_PROFILE

    def fuse(
        self,
        *,
        dense_results: Sequence[RankedResult],
        sparse_results: Sequence[RankedResult],
        limit: int | None = None,
    ) -> list[FusedResult]:
        """Fuse dense and sparse rankings with the configured profile."""

        return fuse(
            dense_results=dense_results,
            sparse_results=sparse_results,
            profile=self.profile,
            limit=limit,
        )


def ranked_result_from_position(
    *,
    result_id: str,
    doc_id: str,
    zero_based_position: int,
    raw_score: float | None = None,
    payload: Mapping[str, object] | None = None,
) -> RankedResult:
    """Build a ``RankedResult`` from a retriever's 0-based ordered position."""

    clean_position = _validate_non_negative_int(
        zero_based_position,
        "zero_based_position",
    )
    return RankedResult(
        result_id=result_id,
        doc_id=doc_id,
        rank=clean_position + 1,
        raw_score=raw_score,
        payload={} if payload is None else payload,
    )


def _consume_ranking(
    *,
    source: str,
    results: Sequence[RankedResult],
    weight: float,
    k: float,
    accumulators: dict[str, _RRFAccumulator],
    start_order: int,
) -> int:
    if weight == 0.0:
        return start_order + len(results)

    seen_in_source: set[str] = set()
    for zero_based_position, result in enumerate(results):
        if result.result_id in seen_in_source:
            _validate_doc_id_consistency(
                accumulator=accumulators.get(result.result_id),
                result=result,
            )
            continue
        seen_in_source.add(result.result_id)

        contribution = weight / (k + float(result.rank))
        accumulator = accumulators.get(result.result_id)
        if accumulator is None:
            accumulator = _RRFAccumulator(
                result_id=result.result_id,
                doc_id=result.doc_id,
                first_seen_order=start_order + zero_based_position,
            )
            accumulators[result.result_id] = accumulator
        else:
            _validate_doc_id_consistency(accumulator=accumulator, result=result)

        _apply_contribution(
            accumulator=accumulator,
            source=source,
            rank=result.rank,
            contribution=contribution,
            raw_score=result.raw_score,
        )
        _maybe_update_payload(
            accumulator=accumulator,
            result=result,
            source=source,
        )

    return start_order + len(results)


def _validate_doc_id_consistency(
    *,
    accumulator: _RRFAccumulator | None,
    result: RankedResult,
) -> None:
    if accumulator is not None and accumulator.doc_id != result.doc_id:
        raise ValueError(
            f"conflicting doc_id for the same result_id: {result.result_id}"
        )


def _apply_contribution(
    *,
    accumulator: _RRFAccumulator,
    source: str,
    rank: int,
    contribution: float,
    raw_score: float | None,
) -> None:
    accumulator.rrf_score += contribution
    if source == SOURCE_DENSE:
        accumulator.dense_rank = rank
        accumulator.dense_contribution = contribution
        accumulator.dense_raw_score = raw_score
        return
    if source == SOURCE_SPARSE:
        accumulator.sparse_rank = rank
        accumulator.sparse_contribution = contribution
        accumulator.sparse_raw_score = raw_score
        return
    raise ValueError(f"unsupported RRF source: {source}")


def _maybe_update_payload(
    *,
    accumulator: _RRFAccumulator,
    result: RankedResult,
    source: str,
) -> None:
    current_rank = accumulator.payload_rank
    if current_rank is None or result.rank < current_rank:
        accumulator.payload = result.payload
        accumulator.payload_rank = result.rank
        accumulator.payload_source = source
        return

    if (
        result.rank == current_rank
        and source == SOURCE_DENSE
        and accumulator.payload_source != SOURCE_DENSE
    ):
        accumulator.payload = result.payload
        accumulator.payload_rank = result.rank
        accumulator.payload_source = source


def _build_fused_result(accumulator: _RRFAccumulator) -> FusedResult:
    ranks = [
        rank
        for rank in (accumulator.dense_rank, accumulator.sparse_rank)
        if rank is not None
    ]
    if not ranks:
        raise RuntimeError("internal RRF error: accumulator has no source rank")

    sources: set[str] = set()
    if accumulator.dense_rank is not None:
        sources.add(SOURCE_DENSE)
    if accumulator.sparse_rank is not None:
        sources.add(SOURCE_SPARSE)

    return FusedResult(
        result_id=accumulator.result_id,
        doc_id=accumulator.doc_id,
        rrf_score=accumulator.rrf_score,
        dense_rank=accumulator.dense_rank,
        sparse_rank=accumulator.sparse_rank,
        dense_contribution=accumulator.dense_contribution,
        sparse_contribution=accumulator.sparse_contribution,
        best_rank=min(ranks),
        first_seen_order=accumulator.first_seen_order,
        dense_raw_score=accumulator.dense_raw_score,
        sparse_raw_score=accumulator.sparse_raw_score,
        payload=accumulator.payload,
        sources=frozenset(sources),
    )


def _fused_sort_key(result: FusedResult) -> tuple[float, int, int, str]:
    return (
        -result.rrf_score,
        result.best_rank,
        result.first_seen_order,
        result.result_id,
    )


def _freeze_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    clean_payload: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("payload keys must be strings")
        clean_payload[key] = value
    return MappingProxyType(clean_payload)


def _validate_source(source: str) -> str:
    clean_source = _validate_text_id(source, "source")
    if clean_source not in {SOURCE_DENSE, SOURCE_SPARSE}:
        raise ValueError(f"unsupported RRF source: {clean_source}")
    return clean_source


def _validate_optional_score(value: float, field_name: str) -> float:
    return _validate_numeric(value, field_name)


def _validate_non_negative_float(value: float, field_name: str) -> float:
    clean_value = _validate_numeric(value, field_name)
    if clean_value < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return clean_value


def _validate_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _validate_optional_rank(value: int | None, field_name: str) -> int | None:
    if value is None:
        return None
    return _validate_positive_int(value, field_name)


def _validate_optional_limit(value: int | None) -> int | None:
    if value is None:
        return None
    return _validate_positive_int(value, "limit")


__all__ = [
    "SOURCE_DENSE",
    "SOURCE_SPARSE",
    "DEFAULT_RRF_K",
    "DEFAULT_DENSE_WEIGHT",
    "DEFAULT_SPARSE_WEIGHT",
    "RankedResult",
    "FusedResult",
    "RRFWeightProfile",
    "DEFAULT_PROFILE",
    "RRFFusion",
    "ranked_result_from_position",
    "fuse",
]
