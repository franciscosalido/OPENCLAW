"""Pure Qdrant 1.18 tuning profile contracts for local Quimera benchmarks.

This module is declarative only. It does not import the Qdrant client, call
network endpoints, mutate collections, run retrieval, or execute benchmarks.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

DEFAULT_PROFILE_NAME = "balanced_local"
MONITORING_METRICS_ENDPOINT = "/metrics?per_collection=true"
MONITORING_TELEMETRY_ENDPOINT = "/telemetry"

FORBIDDEN_SAFE_DICT_KEYS = frozenset(
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
        "raw_text",
        "response",
        "sparse_vector",
        "text",
        "vector",
        "vectors",
    }
)

_ALLOWED_TURBO_BITS = frozenset({"bits4", "bits2", "bits1_5", "bits1"})


class QuantizationKind(str, Enum):
    """Supported conceptual quantization families."""

    NONE = "none"
    SCALAR = "scalar"
    TURBOQUANT = "turboquant"


class TuningProfileName(str, Enum):
    """Canonical Q18-05 tuning profile names."""

    BASELINE_RAM = "baseline_ram"
    BALANCED_LOCAL = "balanced_local"
    LOW_MEMORY = "low_memory"
    TURBOQUANT_EXPERIMENTAL = "turboquant_experimental"
    HIGH_PRECISION_DISK = "high_precision_disk"


class BenchmarkReadiness(str, Enum):
    """How ready a profile is for benchmark or adoption decisions."""

    BASELINE = "baseline"
    READY_FOR_AB_TEST = "ready_for_ab_test"
    EXPERIMENTAL_REQUIRES_BENCHMARK = "experimental_requires_benchmark"


@dataclass(frozen=True, slots=True)
class QuantizationConfig:
    """Conceptual quantization settings for a future Qdrant profile."""

    kind: QuantizationKind
    bits: int | None = None
    turbo_bits: str | None = None
    always_ram: bool | None = None
    rescore: bool | None = None
    description: str = ""

    def __post_init__(self) -> None:
        clean_kind = _coerce_enum(self.kind, QuantizationKind, "kind")
        clean_description = _validate_text(
            self.description, "description", allow_empty=True
        )
        clean_turbo_bits = (
            None
            if self.turbo_bits is None
            else _validate_text(self.turbo_bits, "turbo_bits")
        )
        if self.bits is not None:
            _validate_positive_int(self.bits, "bits")
        if self.always_ram is not None and not isinstance(self.always_ram, bool):
            raise TypeError("always_ram must be a bool or None")
        if self.rescore is not None and not isinstance(self.rescore, bool):
            raise TypeError("rescore must be a bool or None")

        if clean_kind is QuantizationKind.NONE:
            if any(
                value is not None
                for value in (
                    self.bits,
                    clean_turbo_bits,
                    self.always_ram,
                    self.rescore,
                )
            ):
                raise ValueError("none quantization cannot define tuning fields")
        elif clean_kind is QuantizationKind.SCALAR:
            if self.bits not in (None, 8):
                raise ValueError("scalar quantization only supports bits=8 in Q18-05")
            if clean_turbo_bits is not None:
                raise ValueError("scalar quantization cannot define turbo_bits")
        elif clean_kind is QuantizationKind.TURBOQUANT:
            if self.bits is not None and clean_turbo_bits is not None:
                raise ValueError("turboquant must use bits or turbo_bits, not both")
            if self.bits is not None and self.bits not in {1, 2, 4}:
                raise ValueError("turboquant bits must be 1, 2 or 4")
            if clean_turbo_bits is None:
                clean_turbo_bits = (
                    f"bits{self.bits}" if self.bits is not None else "bits4"
                )
            if clean_turbo_bits not in _ALLOWED_TURBO_BITS:
                raise ValueError("turbo_bits is not supported")

        object.__setattr__(self, "kind", clean_kind)
        object.__setattr__(self, "turbo_bits", clean_turbo_bits)
        object.__setattr__(self, "description", clean_description)

    def to_safe_dict(self) -> dict[str, object]:
        """Return a JSON-friendly quantization summary."""

        return _assert_safe_dict(
            {
                "kind": self.kind.value,
                "bits": self.bits,
                "turbo_bits": self.turbo_bits,
                "always_ram": self.always_ram,
                "rescore": self.rescore,
                "description": self.description,
            }
        )

    def to_qdrant_conceptual_dict(self) -> dict[str, object]:
        """Return conceptual Qdrant-shaped quantization config."""

        if self.kind is QuantizationKind.NONE:
            return {"type": QuantizationKind.NONE.value}
        if self.kind is QuantizationKind.SCALAR:
            return _drop_none(
                {
                    "type": QuantizationKind.SCALAR.value,
                    "bits": 8 if self.bits is None else self.bits,
                    "always_ram": self.always_ram,
                    "rescore": self.rescore,
                }
            )
        return _drop_none(
            {
                "type": QuantizationKind.TURBOQUANT.value,
                "bits": self.turbo_bits,
                "always_ram": self.always_ram,
                "rescore": self.rescore,
            }
        )


@dataclass(frozen=True, slots=True)
class IndexTuningConfig:
    """Index/collection-level conceptual tuning settings."""

    dense_on_disk: bool
    hnsw_on_disk: bool
    quantization: QuantizationConfig | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dense_on_disk, bool):
            raise TypeError("dense_on_disk must be a bool")
        if not isinstance(self.hnsw_on_disk, bool):
            raise TypeError("hnsw_on_disk must be a bool")
        if self.quantization is not None and not isinstance(
            self.quantization, QuantizationConfig
        ):
            raise TypeError("quantization must be QuantizationConfig or None")

    def to_safe_dict(self) -> dict[str, object]:
        """Return a safe index config mapping."""

        return _assert_safe_dict(
            {
                "dense_on_disk": self.dense_on_disk,
                "hnsw_on_disk": self.hnsw_on_disk,
                "quantization": (
                    None
                    if self.quantization is None
                    else self.quantization.to_safe_dict()
                ),
            }
        )

    def to_qdrant_conceptual_dict(self) -> dict[str, object]:
        """Return conceptual Qdrant collection/index settings."""

        return _drop_none(
            {
                "vectors_on_disk": self.dense_on_disk,
                "hnsw_config": {"on_disk": self.hnsw_on_disk},
                "quantization_config": (
                    None
                    if self.quantization is None
                    else self.quantization.to_qdrant_conceptual_dict()
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class QueryTuningConfig:
    """Query/search-level conceptual tuning settings."""

    hnsw_ef: int | None = None
    exact: bool = False
    quantization_rescore: bool | None = None
    oversampling_factor: float | None = None

    def __post_init__(self) -> None:
        if self.hnsw_ef is not None:
            _validate_positive_int(self.hnsw_ef, "hnsw_ef")
        if not isinstance(self.exact, bool):
            raise TypeError("exact must be a bool")
        if self.quantization_rescore is not None and not isinstance(
            self.quantization_rescore, bool
        ):
            raise TypeError("quantization_rescore must be a bool or None")
        if self.oversampling_factor is not None:
            _validate_positive_float(self.oversampling_factor, "oversampling_factor")

    def to_safe_dict(self) -> dict[str, object]:
        """Return a safe query config mapping."""

        return _assert_safe_dict(
            {
                "hnsw_ef": self.hnsw_ef,
                "exact": self.exact,
                "quantization_rescore": self.quantization_rescore,
                "oversampling_factor": self.oversampling_factor,
            }
        )

    def to_qdrant_search_params_dict(self) -> dict[str, object]:
        """Return conceptual Qdrant search params, omitting unset values."""

        return _drop_none(
            {
                "hnsw_ef": self.hnsw_ef,
                "exact": self.exact,
                "quantization": (
                    None
                    if self.quantization_rescore is None
                    else {"rescore": self.quantization_rescore}
                ),
                "oversampling_factor": self.oversampling_factor,
            }
        )


@dataclass(frozen=True, slots=True)
class QdrantTuningProfile:
    """One declarative local-first Qdrant tuning profile."""

    name: TuningProfileName
    description: str
    memory_goal: str
    latency_risk: str
    recall_risk: str
    index_config: IndexTuningConfig
    query_config: QueryTuningConfig
    experimental: bool
    requires_benchmark: bool
    benchmark_readiness: BenchmarkReadiness
    intended_use: str
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "name",
            _coerce_enum(self.name, TuningProfileName, "name"),
        )
        object.__setattr__(
            self,
            "benchmark_readiness",
            _coerce_enum(
                self.benchmark_readiness,
                BenchmarkReadiness,
                "benchmark_readiness",
            ),
        )
        for field_name in (
            "description",
            "memory_goal",
            "latency_risk",
            "recall_risk",
            "intended_use",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_text(getattr(self, field_name), field_name),
            )
        if not isinstance(self.index_config, IndexTuningConfig):
            raise TypeError("index_config must be IndexTuningConfig")
        if not isinstance(self.query_config, QueryTuningConfig):
            raise TypeError("query_config must be QueryTuningConfig")
        if not isinstance(self.experimental, bool):
            raise TypeError("experimental must be a bool")
        if not isinstance(self.requires_benchmark, bool):
            raise TypeError("requires_benchmark must be a bool")
        object.__setattr__(
            self,
            "notes",
            tuple(_validate_text(note, "note") for note in self.notes),
        )
        if self.name is TuningProfileName.TURBOQUANT_EXPERIMENTAL:
            if not self.experimental or not self.requires_benchmark:
                raise ValueError("turboquant profile must remain experimental")
            if self.index_config.quantization is None:
                raise ValueError("turboquant profile requires quantization")
            if self.index_config.quantization.kind is not QuantizationKind.TURBOQUANT:
                raise ValueError("turboquant profile must use TurboQuant")

    def to_safe_dict(self) -> dict[str, object]:
        """Return JSON-friendly profile config with no runtime data."""

        return _assert_safe_dict(
            {
                "name": self.name.value,
                "description": self.description,
                "memory_goal": self.memory_goal,
                "latency_risk": self.latency_risk,
                "recall_risk": self.recall_risk,
                "index_config": self.index_config.to_safe_dict(),
                "query_config": self.query_config.to_safe_dict(),
                "experimental": self.experimental,
                "requires_benchmark": self.requires_benchmark,
                "benchmark_readiness": self.benchmark_readiness.value,
                "intended_use": self.intended_use,
                "notes": list(self.notes),
            }
        )

    def to_qdrant_collection_params_dict(self) -> dict[str, object]:
        """Return conceptual Qdrant collection params for future adapters."""

        return build_qdrant_collection_params(self)

    def to_qdrant_search_params_dict(self) -> dict[str, object]:
        """Return conceptual Qdrant search params for future adapters."""

        return build_qdrant_search_params(self)

    def to_otel_attributes(self) -> dict[str, object]:
        """Return flat OpenTelemetry-compatible attributes without OTel imports."""

        quantization = self.index_config.quantization
        return {
            "qdrant.profile": self.name.value,
            "qdrant.quantization": (
                QuantizationKind.NONE.value
                if quantization is None
                else quantization.kind.value
            ),
            "qdrant.dense_on_disk": self.index_config.dense_on_disk,
            "qdrant.hnsw_on_disk": self.index_config.hnsw_on_disk,
            "qdrant.hnsw_ef": self.query_config.hnsw_ef,
            "qdrant.exact": self.query_config.exact,
            "qdrant.quantization_rescore": self.query_config.quantization_rescore,
            "qdrant.oversampling_factor": self.query_config.oversampling_factor,
            "qdrant.experimental": self.experimental,
        }

    def is_default_safe(self) -> bool:
        """Return whether this profile can be used as the default benchmark profile."""

        return (
            self.name is TuningProfileName.BALANCED_LOCAL
            and not self.experimental
            and not self.requires_benchmark
            and self.index_config.quantization is None
        )


@dataclass(frozen=True, slots=True)
class QdrantTuningRunSummary:
    """Future benchmark summary schema for one Qdrant tuning profile."""

    profile_name: str
    profile_config: Mapping[str, object]
    qdrant_server_version: str | None
    qdrant_client_version: str | None
    memory_report_available: bool
    metrics_endpoint: str | None
    telemetry_endpoint: str | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    recall_at_10: float | None
    ndcg_at_5: float | None
    peak_ram_mb: float | None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "profile_name", _validate_text(self.profile_name, "profile_name")
        )
        object.__setattr__(
            self, "profile_config", _freeze_safe_mapping(self.profile_config)
        )
        for field_name in ("qdrant_server_version", "qdrant_client_version"):
            value = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                None if value is None else _validate_text(value, field_name),
            )
        if not isinstance(self.memory_report_available, bool):
            raise TypeError("memory_report_available must be a bool")
        for field_name in ("metrics_endpoint", "telemetry_endpoint"):
            value = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                None if value is None else _validate_text(value, field_name),
            )
        for field_name in (
            "latency_p50_ms",
            "latency_p95_ms",
            "recall_at_10",
            "ndcg_at_5",
            "peak_ram_mb",
        ):
            value = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                None
                if value is None
                else _validate_non_negative_float(value, field_name),
            )
        object.__setattr__(
            self,
            "notes",
            tuple(_validate_text(note, "summary_note") for note in self.notes),
        )

    def to_safe_dict(self) -> dict[str, object]:
        """Return a safe benchmark summary skeleton."""

        return _assert_safe_dict(
            {
                "profile_name": self.profile_name,
                "profile_config": dict(self.profile_config),
                "qdrant_server_version": self.qdrant_server_version,
                "qdrant_client_version": self.qdrant_client_version,
                "memory_report_available": self.memory_report_available,
                "metrics_endpoint": self.metrics_endpoint,
                "telemetry_endpoint": self.telemetry_endpoint,
                "latency_p50_ms": self.latency_p50_ms,
                "latency_p95_ms": self.latency_p95_ms,
                "recall_at_10": self.recall_at_10,
                "ndcg_at_5": self.ndcg_at_5,
                "peak_ram_mb": self.peak_ram_mb,
                "notes": list(self.notes),
            }
        )


def baseline_ram_profile() -> QdrantTuningProfile:
    """Return the pure RAM control profile."""

    return QdrantTuningProfile(
        name=TuningProfileName.BASELINE_RAM,
        description="Full-precision RAM control profile for comparability.",
        memory_goal="high_memory_control",
        latency_risk="low",
        recall_risk="low",
        index_config=IndexTuningConfig(
            dense_on_disk=False,
            hnsw_on_disk=False,
            quantization=None,
        ),
        query_config=QueryTuningConfig(),
        experimental=False,
        requires_benchmark=False,
        benchmark_readiness=BenchmarkReadiness.BASELINE,
        intended_use="control profile for A/B comparisons",
        notes=("No quantization and no on-disk settings.",),
    )


def balanced_local_profile() -> QdrantTuningProfile:
    """Return the conservative local-first default profile."""

    return QdrantTuningProfile(
        name=TuningProfileName.BALANCED_LOCAL,
        description="Conservative RAM-first profile for initial local benchmarks.",
        memory_goal="balanced_local",
        latency_risk="low",
        recall_risk="low",
        index_config=IndexTuningConfig(
            dense_on_disk=False,
            hnsw_on_disk=False,
            quantization=None,
        ),
        query_config=QueryTuningConfig(),
        experimental=False,
        requires_benchmark=False,
        benchmark_readiness=BenchmarkReadiness.READY_FOR_AB_TEST,
        intended_use="default Q18 benchmark profile",
        notes=("Benchmark controls hnsw_ef.", "TurboQuant is not enabled."),
    )


def low_memory_profile() -> QdrantTuningProfile:
    """Return an on-disk profile that isolates memory pressure reduction."""

    return QdrantTuningProfile(
        name=TuningProfileName.LOW_MEMORY,
        description="On-disk dense vectors and HNSW for lower local RAM pressure.",
        memory_goal="low_memory",
        latency_risk="medium_high",
        recall_risk="low_medium",
        index_config=IndexTuningConfig(
            dense_on_disk=True,
            hnsw_on_disk=True,
            quantization=None,
        ),
        query_config=QueryTuningConfig(),
        experimental=False,
        requires_benchmark=True,
        benchmark_readiness=BenchmarkReadiness.READY_FOR_AB_TEST,
        intended_use="memory pressure experiment without quantization",
        notes=("Isolates on-disk behavior before quantization experiments.",),
    )


def turboquant_experimental_profile() -> QdrantTuningProfile:
    """Return the TurboQuant bits4 experimental profile."""

    return QdrantTuningProfile(
        name=TuningProfileName.TURBOQUANT_EXPERIMENTAL,
        description="TurboQuant bits4 with rescoring for measured local evaluation.",
        memory_goal="low_memory_quantized",
        latency_risk="medium",
        recall_risk="unknown",
        index_config=IndexTuningConfig(
            dense_on_disk=False,
            hnsw_on_disk=False,
            quantization=QuantizationConfig(
                kind=QuantizationKind.TURBOQUANT,
                turbo_bits="bits4",
                always_ram=True,
                rescore=True,
                description="Experimental TurboQuant bits4 profile; not a default.",
            ),
        ),
        query_config=QueryTuningConfig(
            quantization_rescore=True,
            oversampling_factor=2.0,
        ),
        experimental=True,
        requires_benchmark=True,
        benchmark_readiness=BenchmarkReadiness.EXPERIMENTAL_REQUIRES_BENCHMARK,
        intended_use="experimental compression profile for Q18 benchmark",
        notes=(
            "Never promote before Recall@10, NDCG@5, latency and memory benchmark.",
        ),
    )


def high_precision_disk_profile() -> QdrantTuningProfile:
    """Return an accuracy-first disk-backed profile."""

    return QdrantTuningProfile(
        name=TuningProfileName.HIGH_PRECISION_DISK,
        description="High-precision disk-backed profile under RAM pressure.",
        memory_goal="moderate_low_memory",
        latency_risk="high",
        recall_risk="low",
        index_config=IndexTuningConfig(
            dense_on_disk=True,
            hnsw_on_disk=True,
            quantization=None,
        ),
        query_config=QueryTuningConfig(hnsw_ef=None, exact=False),
        experimental=False,
        requires_benchmark=True,
        benchmark_readiness=BenchmarkReadiness.READY_FOR_AB_TEST,
        intended_use="accuracy-first profile when RAM pressure matters",
        notes=("Avoids aggressive quantization to protect recall.",),
    )


def get_all_profiles() -> tuple[QdrantTuningProfile, ...]:
    """Return all Q18-05 profiles in deterministic benchmark order."""

    return (
        baseline_ram_profile(),
        balanced_local_profile(),
        low_memory_profile(),
        turboquant_experimental_profile(),
        high_precision_disk_profile(),
    )


def profile_registry() -> Mapping[str, QdrantTuningProfile]:
    """Return an immutable profile registry keyed by profile name."""

    return MappingProxyType(
        {profile.name.value: profile for profile in get_all_profiles()}
    )


def get_profile(name: str | TuningProfileName) -> QdrantTuningProfile:
    """Return a profile by enum or string name."""

    key = (
        name.value
        if isinstance(name, TuningProfileName)
        else _validate_text(name, "name")
    )
    try:
        return profile_registry()[key]
    except KeyError as exc:
        raise KeyError("unknown Qdrant tuning profile") from exc


def default_tuning_profile() -> QdrantTuningProfile:
    """Return the safe default benchmark tuning profile."""

    return get_profile(DEFAULT_PROFILE_NAME)


def build_qdrant_collection_params(profile: QdrantTuningProfile) -> dict[str, object]:
    """Return conceptual Qdrant collection params for a profile."""

    return _assert_safe_dict(
        {
            **profile.index_config.to_qdrant_conceptual_dict(),
            "tuning_profile": profile.name.value,
        }
    )


def build_qdrant_search_params(profile: QdrantTuningProfile) -> dict[str, object]:
    """Return conceptual Qdrant search params for a profile."""

    return _assert_safe_dict(profile.query_config.to_qdrant_search_params_dict())


def qdrant_monitoring_probe_config(
    profile: QdrantTuningProfile,
    collection_name: str,
) -> dict[str, object]:
    """Return future monitoring probe config without calling endpoints."""

    clean_collection = _validate_text(collection_name, "collection_name")
    return _assert_safe_dict(
        {
            "profile_name": profile.name.value,
            "collection_name": clean_collection,
            "metrics_endpoint": MONITORING_METRICS_ENDPOINT,
            "telemetry_endpoint": MONITORING_TELEMETRY_ENDPOINT,
            "expected_metric_labels": ("collection", "endpoint", "status"),
            "otel_attributes": profile.to_otel_attributes(),
            "purpose": "future_q18_benchmark_monitoring",
        }
    )


def build_benchmark_summary(
    *,
    profile: QdrantTuningProfile,
    qdrant_server_version: str | None = None,
    qdrant_client_version: str | None = None,
    memory_report_available: bool = False,
    latency_p50_ms: float | None = None,
    latency_p95_ms: float | None = None,
    recall_at_10: float | None = None,
    ndcg_at_5: float | None = None,
    peak_ram_mb: float | None = None,
) -> QdrantTuningRunSummary:
    """Build a future benchmark summary skeleton for one profile."""

    monitoring = qdrant_monitoring_probe_config(profile, "quimera_benchmark_hybrid_118")
    return QdrantTuningRunSummary(
        profile_name=profile.name.value,
        profile_config=profile.to_safe_dict(),
        qdrant_server_version=qdrant_server_version,
        qdrant_client_version=qdrant_client_version,
        memory_report_available=memory_report_available,
        metrics_endpoint=str(monitoring["metrics_endpoint"]),
        telemetry_endpoint=str(monitoring["telemetry_endpoint"]),
        latency_p50_ms=latency_p50_ms,
        latency_p95_ms=latency_p95_ms,
        recall_at_10=recall_at_10,
        ndcg_at_5=ndcg_at_5,
        peak_ram_mb=peak_ram_mb,
    )


def _validate_text(value: str, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if "\x00" in value:
        raise ValueError(f"{field_name} cannot contain null bytes")
    clean = value.strip()
    if not clean and not allow_empty:
        raise ValueError(f"{field_name} cannot be empty")
    return clean


def _validate_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return value


def _validate_positive_float(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    clean = float(value)
    if not math.isfinite(clean) or clean <= 0.0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return clean


def _validate_non_negative_float(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    clean = float(value)
    if not math.isfinite(clean) or clean < 0.0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return clean


def _coerce_enum(value: object, enum_type: type[Enum], field_name: str) -> Enum:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError as exc:
            raise ValueError(f"{field_name} is not supported") from exc
    raise TypeError(f"{field_name} must be {enum_type.__name__}")


def _drop_none(value: Mapping[str, object]) -> dict[str, object]:
    return {key: item for key, item in value.items() if item is not None}


def _freeze_safe_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(_assert_safe_dict(dict(value)))


def _assert_safe_dict(value: dict[str, object]) -> dict[str, object]:
    _assert_no_forbidden_keys(value)
    return value


def _assert_no_forbidden_keys(value: Mapping[str, object]) -> None:
    for key, item in value.items():
        if str(key).casefold() in FORBIDDEN_SAFE_DICT_KEYS:
            raise ValueError("safe dict contains forbidden key")
        if isinstance(item, Mapping):
            _assert_no_forbidden_keys(item)


__all__ = [
    "BenchmarkReadiness",
    "DEFAULT_PROFILE_NAME",
    "IndexTuningConfig",
    "MONITORING_METRICS_ENDPOINT",
    "MONITORING_TELEMETRY_ENDPOINT",
    "QdrantTuningProfile",
    "QdrantTuningRunSummary",
    "QuantizationConfig",
    "QuantizationKind",
    "QueryTuningConfig",
    "TuningProfileName",
    "balanced_local_profile",
    "baseline_ram_profile",
    "build_benchmark_summary",
    "build_qdrant_collection_params",
    "build_qdrant_search_params",
    "default_tuning_profile",
    "get_all_profiles",
    "get_profile",
    "high_precision_disk_profile",
    "low_memory_profile",
    "profile_registry",
    "qdrant_monitoring_probe_config",
    "turboquant_experimental_profile",
]
