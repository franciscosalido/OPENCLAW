"""Q18 Qdrant 1.18 benchmark comparison and decision artifacts.

The default mode is artifact-only: it reads existing metadata artifacts, writes
safe reports, and never connects to Qdrant. Live benchmarking is intentionally
left behind an explicit environment variable and CLI flag so unit tests and
normal documentation runs remain offline and non-mutating.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Literal

SUMMARY_SCHEMA_VERSION = "qdrant-118-benchmark-summary-v1"
CSV_SCHEMA_VERSION = "qdrant-118-benchmark-csv-v1"
DECISION_SCHEMA_VERSION = "qdrant-118-decision-v1"
LIVE_BENCHMARK_ENV = "RUN_QDRANT_118_BENCHMARK"
LIVE_BENCHMARK_REQUIRED_VALUE = "1"
DEFAULT_RESULTS_DIR = Path("evaluation") / "results"
DEFAULT_SUMMARY_JSON = "qdrant_118_benchmark_summary.json"
DEFAULT_ROWS_CSV = "qdrant_118_benchmark_rows.csv"
DEFAULT_REPORT_MD = "qdrant_118_benchmark_report.md"
DEFAULT_CHARTS_SVG = "qdrant_118_benchmark_charts.svg"
DEFAULT_DOC_REPORT = Path("docs") / "rag" / "qdrant_118_upgrade_results.md"
DEFAULT_ADR = Path("docs") / "ADR" / "ADR-018-qdrant-118-upgrade.md"
POSTGRESQL_SCOPE = "out_of_scope_for_q18"
PYTHON_RRF_DEFAULT_DECISION = "keep_python_rrf_default"
TURBOQUANT_EXPERIMENTAL_DECISION = "accept_turboquant_experimental_only"

FORBIDDEN_OUTPUT_TOKENS = frozenset(
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


class ComparisonScenario(str, Enum):
    """Official Q18-07 comparison scenarios."""

    QDRANT_113_VS_118_BASELINE = "qdrant_113_vs_118_baseline"
    QDRANT_118_BASELINE_VS_BALANCED = "qdrant_118_baseline_vs_balanced"
    QDRANT_118_PYTHON_RRF_VS_NATIVE_RRF = "qdrant_118_python_rrf_vs_native_rrf"
    QDRANT_118_NO_QUANT_VS_TURBOQUANT = "qdrant_118_no_quant_vs_turboquant"
    QDRANT_118_DENSE_ONLY_VS_HYBRID = "qdrant_118_dense_only_vs_hybrid"
    # Qwen3 embedding scenarios
    QDRANT_113_VS_118_QWEN3_BASELINE = "qdrant_113_vs_118_qwen3_baseline"
    QDRANT_118_QWEN3_BASELINE_VS_BALANCED = "qdrant_118_qwen3_baseline_vs_balanced"
    QDRANT_118_QWEN3_PYTHON_RRF_VS_NATIVE_RRF = "qdrant_118_qwen3_python_rrf_vs_native_rrf"
    QDRANT_118_QWEN3_NO_QUANT_VS_TURBOQUANT = "qdrant_118_qwen3_no_quant_vs_turboquant"
    QDRANT_118_QWEN3_DENSE_ONLY_VS_HYBRID = "qdrant_118_qwen3_dense_only_vs_hybrid"
    QDRANT_118_NOMIC_VS_QWEN3_EMBEDDING = "qdrant_118_nomic_vs_qwen3_embedding"


class BenchmarkDecision(str, Enum):
    """Possible Q18-07 decisions."""

    ACCEPT_QDRANT_118_BASELINE = "accept_qdrant_118_baseline"
    ACCEPT_QDRANT_118_BALANCED_PROFILE = "accept_qdrant_118_balanced_profile"
    ACCEPT_TURBOQUANT_EXPERIMENTAL_ONLY = "accept_turboquant_experimental_only"
    KEEP_PYTHON_RRF_DEFAULT = "keep_python_rrf_default"
    PROMOTE_QDRANT_NATIVE_RRF = "promote_qdrant_native_rrf"
    DEFER_DUE_TO_REGRESSION = "defer_due_to_regression"
    INCONCLUSIVE_MISSING_EVIDENCE = "inconclusive_missing_evidence"
    # Qwen3-specific decisions
    ACCEPT_QWEN3_AS_EMBEDDING_DEFAULT = "accept_qwen3_as_embedding_default"
    KEEP_NOMIC_TEMPORARILY = "keep_nomic_temporarily"
    QWEN3_INCONCLUSIVE_MISSING_BASELINE = "qwen3_inconclusive_missing_baseline"
    DEFER_QWEN3_DUE_TO_REGRESSION = "defer_qwen3_due_to_regression"
    ACCEPT_QDRANT_118_WITH_QWEN3 = "accept_qdrant_118_with_qwen3"
    DEFER_QDRANT_118_WITH_QWEN3 = "defer_qdrant_118_with_qwen3"


FusionBackend = Literal["python_rrf", "qdrant_rrf", "qdrant_weighted_rrf", "none"]
RetrievalMode = Literal["dense_only", "hybrid"]


@dataclass(frozen=True, slots=True)
class ComparisonSpec:
    """Stable declaration for one official scenario."""

    scenario: ComparisonScenario
    profile_a: str
    profile_b: str
    purpose: str
    required_artifacts: tuple[str, ...]
    decision_question: str

    def to_safe_dict(self) -> dict[str, object]:
        """Return a JSON-friendly scenario declaration."""

        return _assert_safe_mapping(
            {
                "scenario": self.scenario.value,
                "profile_a": self.profile_a,
                "profile_b": self.profile_b,
                "purpose": self.purpose,
                "required_artifacts": list(self.required_artifacts),
                "decision_question": self.decision_question,
            }
        )


COMPARISONS: tuple[ComparisonSpec, ...] = (
    ComparisonSpec(
        scenario=ComparisonScenario.QDRANT_113_VS_118_BASELINE,
        profile_a="qdrant_113_historical_baseline",
        profile_b="qdrant_118_baseline_ram",
        purpose="version_upgrade",
        required_artifacts=("historical_113", "qdrant_118_baseline_ram"),
        decision_question="Does Qdrant 1.18 preserve quality and acceptable latency versus 1.13.x?",
    ),
    ComparisonSpec(
        scenario=ComparisonScenario.QDRANT_118_BASELINE_VS_BALANCED,
        profile_a="qdrant_118_baseline_ram",
        profile_b="qdrant_118_balanced_local",
        purpose="profile_default",
        required_artifacts=("qdrant_118_baseline_ram", "qdrant_118_balanced_local"),
        decision_question="Should balanced_local become the continued local-first benchmark default?",
    ),
    ComparisonSpec(
        scenario=ComparisonScenario.QDRANT_118_PYTHON_RRF_VS_NATIVE_RRF,
        profile_a="qdrant_118_python_rrf",
        profile_b="qdrant_118_native_rrf",
        purpose="fusion_backend",
        required_artifacts=("qdrant_118_python_rrf", "qdrant_118_native_rrf"),
        decision_question="Can native RRF replace Python RRFFusion without quality or tie-break regressions?",
    ),
    ComparisonSpec(
        scenario=ComparisonScenario.QDRANT_118_NO_QUANT_VS_TURBOQUANT,
        profile_a="qdrant_118_no_quantization",
        profile_b="qdrant_118_turboquant_experimental",
        purpose="quantization",
        required_artifacts=("qdrant_118_no_quantization", "qdrant_118_turboquant_experimental"),
        decision_question="Does TurboQuant reduce memory or latency while preserving recall and NDCG?",
    ),
    ComparisonSpec(
        scenario=ComparisonScenario.QDRANT_118_DENSE_ONLY_VS_HYBRID,
        profile_a="qdrant_118_dense_only",
        profile_b="qdrant_118_hybrid",
        purpose="retrieval_mode",
        required_artifacts=("qdrant_118_dense_only", "qdrant_118_hybrid"),
        decision_question="Does hybrid retrieval remain preferable over dense-only on Qdrant 1.18?",
    ),
    # ── Qwen3 scenarios ───────────────────────────────────────────────────────
    ComparisonSpec(
        scenario=ComparisonScenario.QDRANT_113_VS_118_QWEN3_BASELINE,
        profile_a="qdrant_113_qwen3_historical_baseline",
        profile_b="qdrant_118_qwen3_baseline_ram",
        purpose="version_upgrade_qwen3",
        required_artifacts=("qdrant_113_qwen3_baseline", "qdrant_118_qwen3_baseline_ram"),
        decision_question="Does Qdrant 1.18 preserve quality and latency versus 1.13.x when using Qwen3 embedding?",
    ),
    ComparisonSpec(
        scenario=ComparisonScenario.QDRANT_118_QWEN3_BASELINE_VS_BALANCED,
        profile_a="qdrant_118_qwen3_baseline_ram",
        profile_b="qdrant_118_qwen3_balanced_local",
        purpose="profile_default_qwen3",
        required_artifacts=("qdrant_118_qwen3_baseline_ram", "qdrant_118_qwen3_balanced_local"),
        decision_question="Should qwen3_balanced_local become the default Qwen3 benchmark profile?",
    ),
    ComparisonSpec(
        scenario=ComparisonScenario.QDRANT_118_QWEN3_PYTHON_RRF_VS_NATIVE_RRF,
        profile_a="qdrant_118_qwen3_python_rrf",
        profile_b="qdrant_118_qwen3_native_rrf",
        purpose="fusion_backend_qwen3",
        required_artifacts=("qdrant_118_qwen3_python_rrf", "qdrant_118_qwen3_native_rrf"),
        decision_question="Can native RRF replace Python RRF without regressions when using Qwen3 embedding?",
    ),
    ComparisonSpec(
        scenario=ComparisonScenario.QDRANT_118_QWEN3_NO_QUANT_VS_TURBOQUANT,
        profile_a="qdrant_118_qwen3_no_quantization",
        profile_b="qdrant_118_qwen3_turboquant_experimental",
        purpose="quantization_qwen3",
        required_artifacts=("qdrant_118_qwen3_no_quantization", "qdrant_118_qwen3_turboquant_experimental"),
        decision_question="Does TurboQuant preserve Qwen3 recall and NDCG while reducing storage?",
    ),
    ComparisonSpec(
        scenario=ComparisonScenario.QDRANT_118_QWEN3_DENSE_ONLY_VS_HYBRID,
        profile_a="qdrant_118_qwen3_dense_only",
        profile_b="qdrant_118_qwen3_hybrid",
        purpose="retrieval_mode_qwen3",
        required_artifacts=("qdrant_118_qwen3_dense_only", "qdrant_118_qwen3_hybrid"),
        decision_question="Does hybrid retrieval remain preferable over dense-only when using Qwen3 embedding?",
    ),
    ComparisonSpec(
        scenario=ComparisonScenario.QDRANT_118_NOMIC_VS_QWEN3_EMBEDDING,
        profile_a="qdrant_118_python_rrf",
        profile_b="qdrant_118_qwen3_python_rrf",
        purpose="embedding_model_comparison",
        required_artifacts=("qdrant_118_python_rrf", "qdrant_118_qwen3_python_rrf"),
        decision_question=(
            "Does Qwen3-Embedding-4B (2560d) outperform nomic-embed-text (768d) "
            "in NDCG@5, Recall@10, and P95 latency on Qdrant 1.18?"
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class QualityMetrics:
    """Quality metrics where higher values are better."""

    precision_at_5: float | None = None
    recall_at_10: float | None = None
    mrr: float | None = None
    ndcg_at_5: float | None = None

    def __post_init__(self) -> None:
        for field_name in ("precision_at_5", "recall_at_10", "mrr", "ndcg_at_5"):
            object.__setattr__(
                self,
                field_name,
                _validate_optional_metric(getattr(self, field_name), field_name),
            )

    def to_safe_dict(self) -> dict[str, object]:
        """Return quality metrics as a safe mapping."""

        return {
            "precision_at_5": self.precision_at_5,
            "recall_at_10": self.recall_at_10,
            "mrr": self.mrr,
            "ndcg_at_5": self.ndcg_at_5,
        }


@dataclass(frozen=True, slots=True)
class LatencyMetrics:
    """Latency metrics in milliseconds where lower values are better."""

    p50_ms: float | None = None
    p95_ms: float | None = None
    embed_dense_ms_p50: float | None = None
    embed_sparse_ms_p50: float | None = None
    search_dense_ms_p50: float | None = None
    search_sparse_ms_p50: float | None = None
    fusion_ms_p50: float | None = None
    total_ms_p50: float | None = None
    total_ms_p95: float | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "p50_ms",
            "p95_ms",
            "embed_dense_ms_p50",
            "embed_sparse_ms_p50",
            "search_dense_ms_p50",
            "search_sparse_ms_p50",
            "fusion_ms_p50",
            "total_ms_p50",
            "total_ms_p95",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_optional_non_negative(getattr(self, field_name), field_name),
            )

    def to_safe_dict(self) -> dict[str, object]:
        """Return latency metrics as a safe mapping."""

        return {
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "embed_dense_ms_p50": self.embed_dense_ms_p50,
            "embed_sparse_ms_p50": self.embed_sparse_ms_p50,
            "search_dense_ms_p50": self.search_dense_ms_p50,
            "search_sparse_ms_p50": self.search_sparse_ms_p50,
            "fusion_ms_p50": self.fusion_ms_p50,
            "total_ms_p50": self.total_ms_p50,
            "total_ms_p95": self.total_ms_p95,
        }


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    """Resource/config snapshot where lower memory/storage is usually better."""

    memory_report_available: bool
    peak_ram_mb: float | None = None
    collection_size_bytes: int | None = None
    vector_storage: Mapping[str, object] = field(default_factory=dict)
    quantization: str = "none"
    on_disk_vectors: bool | None = None
    on_disk_hnsw: bool | None = None
    qdrant_server_version: str | None = None
    qdrant_client_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.memory_report_available, bool):
            raise TypeError("memory_report_available must be a bool")
        object.__setattr__(
            self,
            "peak_ram_mb",
            _validate_optional_non_negative(self.peak_ram_mb, "peak_ram_mb"),
        )
        if self.collection_size_bytes is not None:
            object.__setattr__(
                self,
                "collection_size_bytes",
                _validate_non_negative_int(self.collection_size_bytes, "collection_size_bytes"),
            )
        object.__setattr__(
            self,
            "vector_storage",
            MappingProxyType(_assert_safe_mapping(dict(self.vector_storage))),
        )
        object.__setattr__(self, "quantization", _validate_text(self.quantization, "quantization"))
        for field_name in ("on_disk_vectors", "on_disk_hnsw"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, bool):
                raise TypeError(f"{field_name} must be a bool or None")
        for field_name in ("qdrant_server_version", "qdrant_client_version"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _validate_text(value, field_name))

    def to_safe_dict(self) -> dict[str, object]:
        """Return a safe resource snapshot.

        The public key is ``storage_config`` rather than ``vector_storage`` so
        standard reports do not contain raw vector-like field names.
        """

        return _assert_safe_mapping(
            {
                "memory_report_available": self.memory_report_available,
                "peak_ram_mb": self.peak_ram_mb,
                "collection_size_bytes": self.collection_size_bytes,
                "storage_config": dict(self.vector_storage),
                "quantization": self.quantization,
                "on_disk_vectors": self.on_disk_vectors,
                "on_disk_hnsw": self.on_disk_hnsw,
                "qdrant_server_version": self.qdrant_server_version,
                "qdrant_client_version": self.qdrant_client_version,
            }
        )


@dataclass(frozen=True, slots=True)
class QdrantBenchmarkRun:
    """One benchmark run or artifact row under comparison."""

    run_id: str
    scenario: str
    qdrant_version: str | None
    profile_name: str
    fusion_backend: FusionBackend
    retrieval_mode: RetrievalMode
    quantization: str
    corpus_hash: str | None
    query_set_hash: str | None
    quality: QualityMetrics
    latency: LatencyMetrics
    resources: ResourceSnapshot
    profile_config: Mapping[str, object]
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _validate_text(self.run_id, "run_id"))
        object.__setattr__(self, "scenario", _validate_text(self.scenario, "scenario"))
        if self.qdrant_version is not None:
            object.__setattr__(
                self,
                "qdrant_version",
                _validate_text(self.qdrant_version, "qdrant_version"),
            )
        object.__setattr__(self, "profile_name", _validate_text(self.profile_name, "profile_name"))
        if self.fusion_backend not in {"python_rrf", "qdrant_rrf", "qdrant_weighted_rrf", "none"}:
            raise ValueError("unsupported fusion_backend")
        if self.retrieval_mode not in {"dense_only", "hybrid"}:
            raise ValueError("unsupported retrieval_mode")
        object.__setattr__(self, "quantization", _validate_text(self.quantization, "quantization"))
        for field_name in ("corpus_hash", "query_set_hash"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _validate_text(value, field_name))
        if not isinstance(self.quality, QualityMetrics):
            raise TypeError("quality must be QualityMetrics")
        if not isinstance(self.latency, LatencyMetrics):
            raise TypeError("latency must be LatencyMetrics")
        if not isinstance(self.resources, ResourceSnapshot):
            raise TypeError("resources must be ResourceSnapshot")
        object.__setattr__(
            self,
            "profile_config",
            MappingProxyType(_assert_safe_mapping(dict(self.profile_config))),
        )
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(_assert_safe_mapping(dict(self.metadata))),
        )

    def to_safe_dict(self) -> dict[str, object]:
        """Return the run as a safe report mapping."""

        return _assert_safe_mapping(
            {
                "run_id": self.run_id,
                "scenario": self.scenario,
                "qdrant_version": self.qdrant_version,
                "profile_name": self.profile_name,
                "fusion_backend": self.fusion_backend,
                "retrieval_mode": self.retrieval_mode,
                "quantization": self.quantization,
                "corpus_hash": self.corpus_hash,
                "query_set_hash": self.query_set_hash,
                "quality": self.quality.to_safe_dict(),
                "latency": self.latency.to_safe_dict(),
                "resources": self.resources.to_safe_dict(),
                "profile_config": dict(self.profile_config),
                "metadata": dict(self.metadata),
            }
        )


@dataclass(frozen=True, slots=True)
class BenchmarkScenarioResult:
    """Comparison result for one official scenario."""

    scenario: str
    profile_a: str
    profile_b: str
    run_a: QdrantBenchmarkRun | None
    run_b: QdrantBenchmarkRun | None
    deltas: Mapping[str, object]
    decision_hint: str
    evidence_complete: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario", _validate_text(self.scenario, "scenario"))
        object.__setattr__(self, "profile_a", _validate_text(self.profile_a, "profile_a"))
        object.__setattr__(self, "profile_b", _validate_text(self.profile_b, "profile_b"))
        object.__setattr__(self, "deltas", MappingProxyType(_assert_safe_mapping(dict(self.deltas))))
        object.__setattr__(self, "decision_hint", _validate_text(self.decision_hint, "decision_hint"))
        if not isinstance(self.evidence_complete, bool):
            raise TypeError("evidence_complete must be a bool")

    def to_safe_dict(self) -> dict[str, object]:
        """Return scenario result as safe JSON."""

        return _assert_safe_mapping(
            {
                "scenario": self.scenario,
                "profile_a": self.profile_a,
                "profile_b": self.profile_b,
                "run_a": None if self.run_a is None else self.run_a.to_safe_dict(),
                "run_b": None if self.run_b is None else self.run_b.to_safe_dict(),
                "deltas": dict(self.deltas),
                "decision_hint": self.decision_hint,
                "evidence_complete": self.evidence_complete,
            }
        )


@dataclass(frozen=True, slots=True)
class Qdrant118BenchmarkSummary:
    """Executive Q18-07 benchmark and decision summary."""

    generated_at_utc: str
    artifact_only: bool
    live_benchmark_executed: bool
    baseline_113_present: bool
    scenarios: tuple[BenchmarkScenarioResult, ...]
    final_decision: str
    recommended_default_profile: str | None
    python_rrf_default: bool
    native_rrf_decision: str
    turboquant_decision: str
    postgresql_scope: str = POSTGRESQL_SCOPE
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
    schema_version: str = SUMMARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SUMMARY_SCHEMA_VERSION:
            raise ValueError("unsupported summary schema_version")
        object.__setattr__(self, "generated_at_utc", _validate_text(self.generated_at_utc, "generated_at_utc"))
        for field_name in ("artifact_only", "live_benchmark_executed", "baseline_113_present", "python_rrf_default"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a bool")
        if self.recommended_default_profile is not None:
            object.__setattr__(
                self,
                "recommended_default_profile",
                _validate_text(self.recommended_default_profile, "recommended_default_profile"),
            )
        object.__setattr__(self, "final_decision", _validate_text(self.final_decision, "final_decision"))
        object.__setattr__(
            self,
            "native_rrf_decision",
            _validate_text(self.native_rrf_decision, "native_rrf_decision"),
        )
        object.__setattr__(
            self,
            "turboquant_decision",
            _validate_text(self.turboquant_decision, "turboquant_decision"),
        )
        object.__setattr__(
            self,
            "postgresql_scope",
            _validate_text(self.postgresql_scope, "postgresql_scope"),
        )
        clean_safety = dict(self.safety)
        expected = {
            "includes_query_text": False,
            "includes_document_text": False,
            "includes_payload": False,
            "includes_vectors": False,
            "includes_embeddings": False,
        }
        if clean_safety != expected:
            raise ValueError("summary safety flags must all be false")
        object.__setattr__(self, "safety", MappingProxyType(expected))

    def to_safe_dict(self) -> dict[str, object]:
        """Return the complete safe executive summary."""

        return _assert_safe_mapping(
            {
                "schema_version": self.schema_version,
                "generated_at_utc": self.generated_at_utc,
                "artifact_only": self.artifact_only,
                "live_benchmark_executed": self.live_benchmark_executed,
                "baseline_113_present": self.baseline_113_present,
                "scenarios": [scenario.to_safe_dict() for scenario in self.scenarios],
                "final_decision": self.final_decision,
                "recommended_default_profile": self.recommended_default_profile,
                "python_rrf_default": self.python_rrf_default,
                "native_rrf_decision": self.native_rrf_decision,
                "turboquant_decision": self.turboquant_decision,
                "postgresql_scope": self.postgresql_scope,
                "safety": dict(self.safety),
            }
        )


def compute_deltas(
    run_a: QdrantBenchmarkRun,
    run_b: QdrantBenchmarkRun,
) -> dict[str, object]:
    """Compute quality, latency and resource deltas between two runs."""

    metrics: tuple[tuple[str, float | None, float | None, str], ...] = (
        ("precision_at_5", run_a.quality.precision_at_5, run_b.quality.precision_at_5, "higher"),
        ("recall_at_10", run_a.quality.recall_at_10, run_b.quality.recall_at_10, "higher"),
        ("mrr", run_a.quality.mrr, run_b.quality.mrr, "higher"),
        ("ndcg_at_5", run_a.quality.ndcg_at_5, run_b.quality.ndcg_at_5, "higher"),
        ("total_ms_p50", _latency_p50(run_a), _latency_p50(run_b), "lower"),
        ("total_ms_p95", _latency_p95(run_a), _latency_p95(run_b), "lower"),
        ("peak_ram_mb", run_a.resources.peak_ram_mb, run_b.resources.peak_ram_mb, "lower"),
        (
            "collection_size_bytes",
            _optional_int_to_float(run_a.resources.collection_size_bytes),
            _optional_int_to_float(run_b.resources.collection_size_bytes),
            "lower",
        ),
    )
    return _assert_safe_mapping(
        {name: _delta_entry(a, b, direction) for name, a, b, direction in metrics}
    )


def latency_p95_multiplier(run_a: QdrantBenchmarkRun, run_b: QdrantBenchmarkRun) -> float | None:
    """Return run_b p95 divided by run_a p95, if both are available."""

    a = _latency_p95(run_a)
    b = _latency_p95(run_b)
    if a is None or b is None or a == 0.0:
        return None
    return b / a


def memory_reduction_pct(run_a: QdrantBenchmarkRun, run_b: QdrantBenchmarkRun) -> float | None:
    """Return positive percent reduction when run_b uses less peak RAM."""

    a = run_a.resources.peak_ram_mb
    b = run_b.resources.peak_ram_mb
    if a is None or b is None or a == 0.0:
        return None
    return ((a - b) / a) * 100.0


def make_scenario_result(
    spec: ComparisonSpec,
    runs_by_profile: Mapping[str, QdrantBenchmarkRun],
) -> BenchmarkScenarioResult:
    """Build one scenario result from available artifacts."""

    run_a = runs_by_profile.get(spec.profile_a)
    run_b = runs_by_profile.get(spec.profile_b)
    if run_a is not None and run_b is not None:
        evidence_complete = True
        deltas = compute_deltas(run_a, run_b)
    else:
        evidence_complete = False
        deltas = {}
    hint = _decision_hint(spec.scenario, run_a, run_b, deltas)
    return BenchmarkScenarioResult(
        scenario=spec.scenario.value,
        profile_a=spec.profile_a,
        profile_b=spec.profile_b,
        run_a=run_a,
        run_b=run_b,
        deltas=deltas,
        decision_hint=hint,
        evidence_complete=evidence_complete,
    )


_NOMIC_BASELINE_SCENARIOS = frozenset(
    {
        ComparisonScenario.QDRANT_113_VS_118_BASELINE.value,
        ComparisonScenario.QDRANT_118_BASELINE_VS_BALANCED.value,
        ComparisonScenario.QDRANT_118_PYTHON_RRF_VS_NATIVE_RRF.value,
        ComparisonScenario.QDRANT_118_NO_QUANT_VS_TURBOQUANT.value,
        ComparisonScenario.QDRANT_118_DENSE_ONLY_VS_HYBRID.value,
    }
)

_QWEN3_SCENARIOS = frozenset(
    {
        ComparisonScenario.QDRANT_113_VS_118_QWEN3_BASELINE.value,
        ComparisonScenario.QDRANT_118_QWEN3_BASELINE_VS_BALANCED.value,
        ComparisonScenario.QDRANT_118_QWEN3_PYTHON_RRF_VS_NATIVE_RRF.value,
        ComparisonScenario.QDRANT_118_QWEN3_NO_QUANT_VS_TURBOQUANT.value,
        ComparisonScenario.QDRANT_118_QWEN3_DENSE_ONLY_VS_HYBRID.value,
        ComparisonScenario.QDRANT_118_NOMIC_VS_QWEN3_EMBEDDING.value,
    }
)


def decide_qdrant_118_upgrade(
    scenarios: Sequence[BenchmarkScenarioResult],
    *,
    baseline_113_present: bool,
) -> str:
    """Return the final Q18-07 decision from scenario evidence.

    Only the original Nomic 768d baseline scenarios drive the Qdrant upgrade
    decision.  Qwen3 embedding scenarios are evaluated separately via
    ``decide_qwen3_embedding`` so that missing Qwen3 evidence does not push
    the Qdrant upgrade into INCONCLUSIVE.
    """
    # Filter to the Nomic baseline scenarios only
    nomic_scenarios = [s for s in scenarios if s.scenario in _NOMIC_BASELINE_SCENARIOS]
    if not nomic_scenarios or not all(result.evidence_complete for result in nomic_scenarios):
        return BenchmarkDecision.INCONCLUSIVE_MISSING_EVIDENCE.value
    if not baseline_113_present:
        return BenchmarkDecision.INCONCLUSIVE_MISSING_EVIDENCE.value
    if any(result.decision_hint == BenchmarkDecision.DEFER_DUE_TO_REGRESSION.value for result in nomic_scenarios):
        return BenchmarkDecision.DEFER_DUE_TO_REGRESSION.value
    balanced = _scenario_by_id(nomic_scenarios, ComparisonScenario.QDRANT_118_BASELINE_VS_BALANCED)
    if balanced is not None and balanced.decision_hint == BenchmarkDecision.ACCEPT_QDRANT_118_BALANCED_PROFILE.value:
        return BenchmarkDecision.ACCEPT_QDRANT_118_BALANCED_PROFILE.value
    return BenchmarkDecision.ACCEPT_QDRANT_118_BASELINE.value


def decide_qwen3_embedding(
    scenarios: Sequence[BenchmarkScenarioResult],
    *,
    qwen3_available: bool,
) -> str:
    """Return the Qwen3 embedding decision from available Qwen3 scenario evidence."""
    if not qwen3_available:
        return BenchmarkDecision.QWEN3_INCONCLUSIVE_MISSING_BASELINE.value
    qwen3_scenarios = [s for s in scenarios if s.scenario in _QWEN3_SCENARIOS]
    if not qwen3_scenarios or not all(result.evidence_complete for result in qwen3_scenarios):
        return BenchmarkDecision.QWEN3_INCONCLUSIVE_MISSING_BASELINE.value
    if any(result.decision_hint == BenchmarkDecision.DEFER_DUE_TO_REGRESSION.value for result in qwen3_scenarios):
        return BenchmarkDecision.DEFER_QWEN3_DUE_TO_REGRESSION.value
    nomic_vs_qwen3 = _scenario_by_id(qwen3_scenarios, ComparisonScenario.QDRANT_118_NOMIC_VS_QWEN3_EMBEDDING)
    if nomic_vs_qwen3 is None or not nomic_vs_qwen3.evidence_complete:
        return BenchmarkDecision.QWEN3_INCONCLUSIVE_MISSING_BASELINE.value
    # If Qwen3 shows regression vs Nomic, keep Nomic temporarily
    if nomic_vs_qwen3.decision_hint == BenchmarkDecision.DEFER_DUE_TO_REGRESSION.value:
        return BenchmarkDecision.KEEP_NOMIC_TEMPORARILY.value
    return BenchmarkDecision.ACCEPT_QWEN3_AS_EMBEDDING_DEFAULT.value


def decision_sentence(summary: Qdrant118BenchmarkSummary) -> str:
    """Return one human-readable decision sentence."""

    if summary.final_decision == BenchmarkDecision.INCONCLUSIVE_MISSING_EVIDENCE.value:
        return (
            "Q18-07 remains inconclusive because required benchmark artifacts are "
            "missing; Python RRFFusion remains default, TurboQuant remains "
            "experimental, and PostgreSQL/GraphRAG remain out of scope."
        )
    if summary.final_decision == BenchmarkDecision.DEFER_DUE_TO_REGRESSION.value:
        return (
            "Qdrant 1.18 promotion is deferred due to measured regression; "
            "retain the previous safe profile and Python RRFFusion default."
        )
    return (
        f"Qdrant 1.18 {summary.recommended_default_profile or 'baseline'} is accepted "
        "for continued local-first evaluation; Python RRFFusion remains default "
        "unless native RRF has explicit strong evidence; TurboQuant remains experimental; "
        "PostgreSQL/GraphRAG remain out of scope."
    )


def build_benchmark_span_attributes(
    *,
    scenario: str,
    run: QdrantBenchmarkRun,
) -> dict[str, object]:
    """Return OpenTelemetry-compatible benchmark span attributes."""

    return _assert_safe_mapping(
        {
            "benchmark.scenario": _validate_text(scenario, "scenario"),
            "rag.qdrant.version": run.qdrant_version,
            "rag.qdrant.profile": run.profile_name,
            "rag.fusion.backend": run.fusion_backend,
            "rag.retrieval.mode": run.retrieval_mode,
            "rag.quantization": run.quantization,
            "rag.corpus.hash": run.corpus_hash,
            "rag.query_set.hash": run.query_set_hash,
            "rag.memory_report_available": run.resources.memory_report_available,
        }
    )


def build_comparison_span_attributes(result: BenchmarkScenarioResult) -> dict[str, object]:
    """Return OpenTelemetry-compatible comparison span attributes."""

    return _assert_safe_mapping(
        {
            "benchmark.scenario": result.scenario,
            "benchmark.profile_a": result.profile_a,
            "benchmark.profile_b": result.profile_b,
            "benchmark.evidence_complete": result.evidence_complete,
            "benchmark.decision_hint": result.decision_hint,
        }
    )


def load_benchmark_runs(path: Path | None) -> tuple[QdrantBenchmarkRun, ...]:
    """Load optional benchmark runs from JSON artifacts."""

    if path is None:
        return ()
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, Mapping) and isinstance(data.get("runs"), list):
        raw_runs = data["runs"]
    elif isinstance(data, list):
        raw_runs = data
    else:
        raise ValueError("benchmark artifact must be a list or contain runs")
    return tuple(_run_from_mapping(item) for item in raw_runs if isinstance(item, Mapping))


def load_historical_baseline(path: Path | None) -> QdrantBenchmarkRun | None:
    """Load the optional Qdrant 1.13 historical baseline."""

    if path is None:
        return None
    runs = load_benchmark_runs(path)
    return runs[0] if runs else None


def build_summary(
    *,
    runs: Sequence[QdrantBenchmarkRun],
    historical_baseline: QdrantBenchmarkRun | None = None,
    artifact_only: bool = True,
    live_benchmark_executed: bool = False,
    generated_at_utc: str | None = None,
) -> Qdrant118BenchmarkSummary:
    """Build the executive benchmark summary from available artifacts."""

    clean_runs = list(runs)
    if historical_baseline is not None:
        clean_runs.append(historical_baseline)
    runs_by_profile = {run.profile_name: run for run in clean_runs}
    scenarios = tuple(make_scenario_result(spec, runs_by_profile) for spec in COMPARISONS)
    baseline_113_present = historical_baseline is not None or "qdrant_113_historical_baseline" in runs_by_profile
    final_decision = decide_qdrant_118_upgrade(
        scenarios,
        baseline_113_present=baseline_113_present,
    )
    native_decision = _native_rrf_decision(scenarios)
    default_profile = (
        "balanced_local"
        if final_decision == BenchmarkDecision.ACCEPT_QDRANT_118_BALANCED_PROFILE.value
        else None
    )
    return Qdrant118BenchmarkSummary(
        generated_at_utc=generated_at_utc or _utc_now_iso(),
        artifact_only=artifact_only,
        live_benchmark_executed=live_benchmark_executed,
        baseline_113_present=baseline_113_present,
        scenarios=scenarios,
        final_decision=final_decision,
        recommended_default_profile=default_profile,
        python_rrf_default=native_decision != BenchmarkDecision.PROMOTE_QDRANT_NATIVE_RRF.value,
        native_rrf_decision=native_decision,
        turboquant_decision=TURBOQUANT_EXPERIMENTAL_DECISION,
    )


def render_svg_dashboard(summary: Qdrant118BenchmarkSummary) -> str:
    """Render a standalone SVG dashboard without external dependencies."""

    scenario_rows = list(summary.scenarios)
    width = 980
    height = 760
    quality = _svg_bar_section(
        title="Quality",
        x=30,
        y=90,
        values=_scenario_metric_values(scenario_rows, "ndcg_at_5"),
        color="#2563eb",
    )
    latency = _svg_bar_section(
        title="Latency",
        x=520,
        y=90,
        values=_scenario_metric_values(scenario_rows, "total_ms_p95"),
        color="#b45309",
    )
    resources = _svg_bar_section(
        title="Resources",
        x=30,
        y=360,
        values=_scenario_metric_values(scenario_rows, "peak_ram_mb"),
        color="#15803d",
    )
    decision = _svg_decision_matrix(scenario_rows, x=520, y=360)
    fusion = _svg_fusion_panel(scenario_rows, x=30, y=650)
    safe_text = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Qdrant 1.18 benchmark dashboard">
  <rect width="100%" height="100%" fill="#f8fafc"/>
  <text x="30" y="40" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="#111827">Qdrant 1.18 Benchmark Dashboard</text>
  <text x="30" y="66" font-family="Arial, sans-serif" font-size="13" fill="#475569">Decision: {html.escape(summary.final_decision)} | Artifact-only: {str(summary.artifact_only).lower()}</text>
  {quality}
  {latency}
  {resources}
  {decision}
  {fusion}
</svg>
"""
    _assert_safe_text(safe_text)
    return safe_text


def write_csv(summary: Qdrant118BenchmarkSummary, path: Path) -> None:
    """Write long-form benchmark rows."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        for scenario in summary.scenarios:
            for run in (scenario.run_a, scenario.run_b):
                if run is None:
                    continue
                row = _csv_row(summary, scenario, run)
                _assert_safe_text("|".join(str(value) for value in row.values()))
                writer.writerow(row)


def write_json(summary: Qdrant118BenchmarkSummary, path: Path) -> None:
    """Write the executive JSON summary."""

    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(summary.to_safe_dict(), ensure_ascii=False, indent=2, sort_keys=True)
    _assert_safe_text(text)
    path.write_text(text + "\n", encoding="utf-8")


def write_markdown_report(summary: Qdrant118BenchmarkSummary, path: Path) -> None:
    """Write a Markdown benchmark report."""

    path.parent.mkdir(parents=True, exist_ok=True)
    text = render_markdown_report(summary)
    _assert_safe_text(text)
    path.write_text(text, encoding="utf-8")


def write_svg(summary: Qdrant118BenchmarkSummary, path: Path) -> None:
    """Write the SVG dashboard."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_svg_dashboard(summary), encoding="utf-8")


def render_markdown_report(summary: Qdrant118BenchmarkSummary) -> str:
    """Render the human benchmark report."""

    scenario_lines = "\n".join(
        f"| `{item.scenario}` | `{item.profile_a}` | `{item.profile_b}` | `{item.decision_hint}` | {str(item.evidence_complete).lower()} |"
        for item in summary.scenarios
    )
    decision_block = json.dumps(machine_readable_decision(summary), indent=2, sort_keys=True)
    return f"""# Qdrant 1.18 Upgrade Results

## Executive Summary

{decision_sentence(summary)}

This report is artifact-only by default. It records missing evidence as missing
evidence and never invents benchmark numbers.

## Hypotheses

- Qdrant 1.18 improves local-first observability/performance.
- `balanced_local` is safer default than TurboQuant before measurement.
- TurboQuant may reduce memory but requires quality benchmark evidence.
- Native RRF may reduce app-side work but must match Python RRFFusion behavior.

## Evidence Sources

- Q18-04 schema contract: `quimera_benchmark_hybrid_118`.
- Q18-05 tuning profiles: `baseline_ram`, `balanced_local`,
  `turboquant_experimental`.
- Q18-06 native RRF comparison contracts.
- Historical Qdrant 1.13 baseline present: `{str(summary.baseline_113_present).lower()}`.

## Documentation Paths

The canonical ADR directory in this repository is `docs/ADR`. Lowercase
`docs/adr` references should be treated as legacy/case-insensitive aliases.

## Methodology

Each scenario compares two named artifact profiles. Quality metrics are higher
is better. Latency and resource metrics are lower is better. Missing values are
reported as `null`/TBD and excluded from promotion claims.

## Scenario Matrix

| Scenario | Profile A | Profile B | Decision hint | Evidence complete |
|---|---|---|---|---|
{scenario_lines}

## Results

Quality, latency and resource deltas are stored in
`evaluation/results/qdrant_118_benchmark_summary.json` when generated.

## Visual Summary

See `evaluation/results/qdrant_118_benchmark_charts.svg`.

## Decision

`{summary.final_decision}`

Python RRFFusion default: `{str(summary.python_rrf_default).lower()}`.
Native RRF decision: `{summary.native_rrf_decision}`.
TurboQuant decision: `{summary.turboquant_decision}`.

## Why PostgreSQL / GraphRAG Are Out Of Scope

Q18 decides Qdrant engine, tuning and fusion behavior. PostgreSQL, pgvector and
GraphRAG require a separate backend/data-model sprint and are explicitly outside
this cycle.

## Rollback

- Return to the previous accepted Qdrant profile.
- Keep Python RRFFusion default.
- Disable TurboQuant.
- Use artifact-only comparison until live evidence is regenerated.
- Revert Qdrant version only in a dedicated rollback PR.

## Limitations

- Historical 1.13 baseline artifacts may be absent.
- Local measurements do not represent production concurrency.
- Deep memory reporting may be unavailable in some artifacts.
- TurboQuant requires a broader corpus before adoption.
- Native RRF may diverge in tie-break behavior even with high overlap.

## Machine-readable block

<!-- machine-readable: qdrant-118-decision-v1 -->
```json
{decision_block}
```
"""


def render_adr(summary: Qdrant118BenchmarkSummary) -> str:
    """Render the final Q18 ADR text."""

    status = "Accepted"
    if summary.final_decision == BenchmarkDecision.INCONCLUSIVE_MISSING_EVIDENCE.value:
        status = "Proposed"
    elif summary.final_decision == BenchmarkDecision.DEFER_DUE_TO_REGRESSION.value:
        status = "Deferred"
    decision_block = json.dumps(machine_readable_decision(summary), indent=2, sort_keys=True)
    return f"""# ADR-0XX: Qdrant 1.18 Upgrade Decision

Status: {status}

## Context

Q18 evaluated Qdrant 1.18 as the next local-first vector backend for Quimera
after RAG-1A established dense+sparse hybrid retrieval and Python RRFFusion.

## Decision

{decision_sentence(summary)}

## Evidence

Evidence is recorded in `docs/rag/qdrant_118_upgrade_results.md` and, when
generated, `evaluation/results/qdrant_118_benchmark_summary.json`.

## Alternatives Considered

1. Keep Qdrant 1.13.x historical baseline.
2. Accept Qdrant 1.18 baseline profile.
3. Accept Qdrant 1.18 `balanced_local`.
4. Promote native Qdrant RRF.
5. Migrate to PostgreSQL/pgvector or GraphRAG now.

## Consequences

- Python RRFFusion remains the default unless native RRF earns explicit strong
  evidence.
- TurboQuant remains experimental unless quality, latency and memory thresholds
  are all satisfied.
- PostgreSQL/GraphRAG stay outside Q18.

## Default Config

Recommended profile: `{summary.recommended_default_profile or "TBD"}`.

## Python vs Native RRF

Native RRF decision: `{summary.native_rrf_decision}`.

Native RRF promotion is intentionally conservative: it requires strong overlap,
no material quality regression, no tie-break regressions and p95 latency that is
equal to or faster than Python RRFFusion (`p95_multiplier <= 1.0`).

## TurboQuant Decision

TurboQuant decision: `{summary.turboquant_decision}`.

## PostgreSQL/GraphRAG Scope

`{summary.postgresql_scope}`

## Rollback

1. Keep Python RRFFusion.
2. Disable TurboQuant.
3. Return to the previous accepted profile.
4. Re-run Q18-07 artifact-only comparison.
5. Revert Qdrant version only through a dedicated rollback PR.

## Conditions for Reversal

- Recall@10 delta below `-0.01`.
- NDCG@5 delta below `-0.01`.
- p95 latency multiplier above `2.5`.
- Native RRF tie-break regressions appear.
- Native RRF p95 latency is slower than Python RRFFusion when promotion is
  being considered (`native/python p95 multiplier > 1.0`).
- Memory reporting contradicts local-first resource goals.

## Follow-ups

- Generate real Q18 artifacts with `RUN_QDRANT_118_BENCHMARK=1`.
- Expand corpus and query categories before any production-style promotion.
- Keep PostgreSQL/GraphRAG as a future architecture discussion, not Q18 scope.

## Machine-readable block

<!-- machine-readable: qdrant-118-decision-v1 -->
```json
{decision_block}
```
"""


def machine_readable_decision(summary: Qdrant118BenchmarkSummary) -> dict[str, object]:
    """Return the stable decision block for reports and ADR."""

    return _assert_safe_mapping(
        {
            "schema_version": DECISION_SCHEMA_VERSION,
            "decision": summary.final_decision,
            "python_rrf_default": summary.python_rrf_default,
            "native_rrf": summary.native_rrf_decision,
            "turboquant": "experimental_only",
            "postgresql": "out_of_scope",
            "baseline_113_present": summary.baseline_113_present,
            "recommended_default_profile": summary.recommended_default_profile,
        }
    )


CSV_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "scenario",
    "run_id",
    "profile_name",
    "qdrant_version",
    "fusion_backend",
    "retrieval_mode",
    "quantization",
    "precision_at_5",
    "recall_at_10",
    "mrr",
    "ndcg_at_5",
    "total_ms_p50",
    "total_ms_p95",
    "peak_ram_mb",
    "collection_size_bytes",
    "memory_report_available",
    "evidence_complete",
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI args."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, action="append", default=[])
    parser.add_argument("--historical-baseline", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--doc-report", type=Path, default=DEFAULT_DOC_REPORT)
    parser.add_argument("--adr-path", type=Path, default=DEFAULT_ADR)
    parser.add_argument("--execute-live-benchmark", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""

    args = parse_args(argv)
    try:
        if args.execute_live_benchmark and os.getenv(LIVE_BENCHMARK_ENV) != LIVE_BENCHMARK_REQUIRED_VALUE:
            raise RuntimeError("live benchmark requires RUN_QDRANT_118_BENCHMARK=1")
        live_executed = bool(args.execute_live_benchmark)
        artifacts = tuple(run for path in args.artifact for run in load_benchmark_runs(path))
        historical = load_historical_baseline(args.historical_baseline)
        summary = build_summary(
            runs=artifacts,
            historical_baseline=historical,
            artifact_only=not live_executed,
            live_benchmark_executed=live_executed,
        )
        output_dir = args.output_dir
        write_json(summary, output_dir / DEFAULT_SUMMARY_JSON)
        write_csv(summary, output_dir / DEFAULT_ROWS_CSV)
        write_markdown_report(summary, output_dir / DEFAULT_REPORT_MD)
        write_svg(summary, output_dir / DEFAULT_CHARTS_SVG)
        write_markdown_report(summary, args.doc_report)
        args.adr_path.parent.mkdir(parents=True, exist_ok=True)
        args.adr_path.write_text(render_adr(summary), encoding="utf-8")
        sys.stdout.write(json.dumps(summary.to_safe_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return 0
    except Exception as exc:
        sys.stderr.write(f"qdrant benchmark comparison failed: {type(exc).__name__}\n")
        return 2


def _run_from_mapping(raw: Mapping[str, object]) -> QdrantBenchmarkRun:
    quality = raw.get("quality")
    latency = raw.get("latency")
    resources = raw.get("resources")
    profile_config_raw = raw.get("profile_config")
    profile_config: Mapping[str, object] = (
        profile_config_raw if isinstance(profile_config_raw, Mapping) else {}
    )
    metadata_raw = raw.get("metadata")
    metadata: Mapping[str, object] = metadata_raw if isinstance(metadata_raw, Mapping) else {}
    return QdrantBenchmarkRun(
        run_id=str(raw.get("run_id", _stable_hash(json.dumps(raw, sort_keys=True, default=str)))),
        scenario=str(raw.get("scenario", "artifact")),
        qdrant_version=_optional_str(raw.get("qdrant_version")),
        profile_name=str(raw.get("profile_name", "")),
        fusion_backend=_coerce_fusion_backend(raw.get("fusion_backend", "none")),
        retrieval_mode=_coerce_retrieval_mode(raw.get("retrieval_mode", "hybrid")),
        quantization=str(raw.get("quantization", "none")),
        corpus_hash=_optional_str(raw.get("corpus_hash")),
        query_set_hash=_optional_str(raw.get("query_set_hash")),
        quality=_quality_from_mapping(quality if isinstance(quality, Mapping) else {}),
        latency=_latency_from_mapping(latency if isinstance(latency, Mapping) else {}),
        resources=_resources_from_mapping(resources if isinstance(resources, Mapping) else {}),
        profile_config=profile_config,
        metadata=metadata,
    )


def _quality_from_mapping(raw: Mapping[str, object]) -> QualityMetrics:
    return QualityMetrics(
        precision_at_5=_optional_float(raw.get("precision_at_5")),
        recall_at_10=_optional_float(raw.get("recall_at_10")),
        mrr=_optional_float(raw.get("mrr")),
        ndcg_at_5=_optional_float(raw.get("ndcg_at_5")),
    )


def _latency_from_mapping(raw: Mapping[str, object]) -> LatencyMetrics:
    return LatencyMetrics(
        p50_ms=_optional_float(raw.get("p50_ms")),
        p95_ms=_optional_float(raw.get("p95_ms")),
        embed_dense_ms_p50=_optional_float(raw.get("embed_dense_ms_p50")),
        embed_sparse_ms_p50=_optional_float(raw.get("embed_sparse_ms_p50")),
        search_dense_ms_p50=_optional_float(raw.get("search_dense_ms_p50")),
        search_sparse_ms_p50=_optional_float(raw.get("search_sparse_ms_p50")),
        fusion_ms_p50=_optional_float(raw.get("fusion_ms_p50")),
        total_ms_p50=_optional_float(raw.get("total_ms_p50")),
        total_ms_p95=_optional_float(raw.get("total_ms_p95")),
    )


def _resources_from_mapping(raw: Mapping[str, object]) -> ResourceSnapshot:
    storage_raw = raw.get("storage_config")
    if isinstance(storage_raw, Mapping):
        storage: Mapping[str, object] = storage_raw
    else:
        legacy_storage_raw = raw.get("vector_storage")
        storage = legacy_storage_raw if isinstance(legacy_storage_raw, Mapping) else {}
    return ResourceSnapshot(
        memory_report_available=bool(raw.get("memory_report_available", False)),
        peak_ram_mb=_optional_float(raw.get("peak_ram_mb")),
        collection_size_bytes=_optional_int(raw.get("collection_size_bytes")),
        vector_storage=storage,
        quantization=str(raw.get("quantization", "none")),
        on_disk_vectors=_optional_bool(raw.get("on_disk_vectors")),
        on_disk_hnsw=_optional_bool(raw.get("on_disk_hnsw")),
        qdrant_server_version=_optional_str(raw.get("qdrant_server_version")),
        qdrant_client_version=_optional_str(raw.get("qdrant_client_version")),
    )


def _decision_hint(
    scenario: ComparisonScenario,
    run_a: QdrantBenchmarkRun | None,
    run_b: QdrantBenchmarkRun | None,
    deltas: Mapping[str, object],
) -> str:
    if run_a is None or run_b is None:
        return BenchmarkDecision.INCONCLUSIVE_MISSING_EVIDENCE.value
    recall = _abs_delta(deltas, "recall_at_10")
    ndcg = _abs_delta(deltas, "ndcg_at_5")
    p95_multiplier = latency_p95_multiplier(run_a, run_b)
    if recall is not None and recall < -0.01:
        return BenchmarkDecision.DEFER_DUE_TO_REGRESSION.value
    if ndcg is not None and ndcg < -0.01:
        return BenchmarkDecision.DEFER_DUE_TO_REGRESSION.value
    if p95_multiplier is not None and p95_multiplier > 2.5:
        return BenchmarkDecision.DEFER_DUE_TO_REGRESSION.value
    if scenario is ComparisonScenario.QDRANT_118_BASELINE_VS_BALANCED:
        return BenchmarkDecision.ACCEPT_QDRANT_118_BALANCED_PROFILE.value
    if scenario is ComparisonScenario.QDRANT_118_PYTHON_RRF_VS_NATIVE_RRF:
        return _native_decision_from_runs(run_a, run_b)
    if scenario is ComparisonScenario.QDRANT_118_NO_QUANT_VS_TURBOQUANT:
        return BenchmarkDecision.ACCEPT_TURBOQUANT_EXPERIMENTAL_ONLY.value
    return BenchmarkDecision.ACCEPT_QDRANT_118_BASELINE.value


def _native_decision_from_runs(run_a: QdrantBenchmarkRun, run_b: QdrantBenchmarkRun) -> str:
    overlap = _metadata_float(run_b, "overlap_at_10")
    tie_break_regressions = _metadata_float(run_b, "tie_break_regression_count")
    ndcg_delta = None
    if run_a.quality.ndcg_at_5 is not None and run_b.quality.ndcg_at_5 is not None:
        ndcg_delta = run_b.quality.ndcg_at_5 - run_a.quality.ndcg_at_5
    p95_multiplier = latency_p95_multiplier(run_a, run_b)
    if (
        overlap is not None
        and overlap >= 0.95
        and (ndcg_delta is None or ndcg_delta >= -0.01)
        and (p95_multiplier is None or p95_multiplier <= 1.0)
        and (tie_break_regressions is None or tie_break_regressions == 0.0)
    ):
        return BenchmarkDecision.PROMOTE_QDRANT_NATIVE_RRF.value
    return BenchmarkDecision.KEEP_PYTHON_RRF_DEFAULT.value


def _native_rrf_decision(scenarios: Sequence[BenchmarkScenarioResult]) -> str:
    scenario = _scenario_by_id(scenarios, ComparisonScenario.QDRANT_118_PYTHON_RRF_VS_NATIVE_RRF)
    if scenario is None:
        return BenchmarkDecision.KEEP_PYTHON_RRF_DEFAULT.value
    if scenario.decision_hint == BenchmarkDecision.PROMOTE_QDRANT_NATIVE_RRF.value:
        return BenchmarkDecision.PROMOTE_QDRANT_NATIVE_RRF.value
    return BenchmarkDecision.KEEP_PYTHON_RRF_DEFAULT.value


def _scenario_by_id(
    scenarios: Sequence[BenchmarkScenarioResult],
    scenario: ComparisonScenario,
) -> BenchmarkScenarioResult | None:
    for item in scenarios:
        if item.scenario == scenario.value:
            return item
    return None


def _delta_entry(a: float | None, b: float | None, direction: str) -> dict[str, object]:
    if a is None or b is None:
        return {"a": a, "b": b, "absolute_delta": None, "relative_delta_pct": None, "winner": "incomplete"}
    absolute = b - a
    relative = None if a == 0.0 else (absolute / a) * 100.0
    if math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12):
        winner = "tie"
    elif direction == "higher":
        winner = "profile_b" if b > a else "profile_a"
    else:
        winner = "profile_b" if b < a else "profile_a"
    return {
        "a": a,
        "b": b,
        "absolute_delta": absolute,
        "relative_delta_pct": relative,
        "winner": winner,
    }


def _latency_p50(run: QdrantBenchmarkRun) -> float | None:
    return run.latency.total_ms_p50 if run.latency.total_ms_p50 is not None else run.latency.p50_ms


def _latency_p95(run: QdrantBenchmarkRun) -> float | None:
    return run.latency.total_ms_p95 if run.latency.total_ms_p95 is not None else run.latency.p95_ms


def _abs_delta(deltas: Mapping[str, object], metric: str) -> float | None:
    value = deltas.get(metric)
    if not isinstance(value, Mapping):
        return None
    raw = value.get("absolute_delta")
    return raw if isinstance(raw, float) else None


def _metadata_float(run: QdrantBenchmarkRun, key: str) -> float | None:
    return _optional_float(run.metadata.get(key))


def _csv_row(
    summary: Qdrant118BenchmarkSummary,
    scenario: BenchmarkScenarioResult,
    run: QdrantBenchmarkRun,
) -> dict[str, object]:
    return {
        "schema_version": CSV_SCHEMA_VERSION,
        "scenario": scenario.scenario,
        "run_id": run.run_id,
        "profile_name": run.profile_name,
        "qdrant_version": run.qdrant_version or "",
        "fusion_backend": run.fusion_backend,
        "retrieval_mode": run.retrieval_mode,
        "quantization": run.quantization,
        "precision_at_5": _fmt(run.quality.precision_at_5),
        "recall_at_10": _fmt(run.quality.recall_at_10),
        "mrr": _fmt(run.quality.mrr),
        "ndcg_at_5": _fmt(run.quality.ndcg_at_5),
        "total_ms_p50": _fmt(_latency_p50(run)),
        "total_ms_p95": _fmt(_latency_p95(run)),
        "peak_ram_mb": _fmt(run.resources.peak_ram_mb),
        "collection_size_bytes": "" if run.resources.collection_size_bytes is None else run.resources.collection_size_bytes,
        "memory_report_available": str(run.resources.memory_report_available).lower(),
        "evidence_complete": str(scenario.evidence_complete and summary.schema_version == SUMMARY_SCHEMA_VERSION).lower(),
    }


def _scenario_metric_values(
    scenarios: Sequence[BenchmarkScenarioResult],
    metric: str,
) -> tuple[tuple[str, float | None], ...]:
    values: list[tuple[str, float | None]] = []
    for scenario in scenarios:
        label = scenario.scenario.replace("qdrant_118_", "").replace("qdrant_", "")
        run = scenario.run_b
        if run is None:
            values.append((label, None))
        elif metric == "ndcg_at_5":
            values.append((label, run.quality.ndcg_at_5))
        elif metric == "total_ms_p95":
            values.append((label, _latency_p95(run)))
        elif metric == "peak_ram_mb":
            values.append((label, run.resources.peak_ram_mb))
    return tuple(values)


def _svg_bar_section(
    *,
    title: str,
    x: int,
    y: int,
    values: Sequence[tuple[str, float | None]],
    color: str,
) -> str:
    max_value = max((value for _label, value in values if value is not None), default=1.0)
    parts = [
        f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" font-size="18" font-weight="700" fill="#111827">{html.escape(title)}</text>'
    ]
    for index, (label, value) in enumerate(values[:5]):
        row_y = y + 28 + (index * 34)
        width = 0 if value is None else int((value / max_value) * 260) if max_value > 0 else 0
        shown = "TBD" if value is None else _fmt(value)
        parts.append(f'<text x="{x}" y="{row_y + 14}" font-family="Arial, sans-serif" font-size="10" fill="#334155">{html.escape(label[:30])}</text>')
        parts.append(f'<rect x="{x + 170}" y="{row_y}" width="{width}" height="16" fill="{color}" opacity="0.82"/>')
        parts.append(f'<text x="{x + 438}" y="{row_y + 13}" font-family="Arial, sans-serif" font-size="11" fill="#334155">{html.escape(shown)}</text>')
    return "\n  ".join(parts)


def _svg_decision_matrix(
    scenarios: Sequence[BenchmarkScenarioResult],
    *,
    x: int,
    y: int,
) -> str:
    parts = [
        f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" font-size="18" font-weight="700" fill="#111827">Decision</text>',
        f'<text x="{x}" y="{y + 26}" font-family="Arial, sans-serif" font-size="10" font-weight="700" fill="#475569">Scenario</text>',
        f'<text x="{x + 190}" y="{y + 26}" font-family="Arial, sans-serif" font-size="10" font-weight="700" fill="#475569">Winner</text>',
        f'<text x="{x + 260}" y="{y + 26}" font-family="Arial, sans-serif" font-size="10" font-weight="700" fill="#475569">Confidence</text>',
        f'<text x="{x + 345}" y="{y + 26}" font-family="Arial, sans-serif" font-size="10" font-weight="700" fill="#475569">Decision</text>',
    ]
    for index, scenario in enumerate(scenarios[:5]):
        row_y = y + 44 + (index * 34)
        winner = _scenario_winner(scenario)
        confidence = "complete" if scenario.evidence_complete else "TBD"
        parts.append(f'<text x="{x}" y="{row_y + 13}" font-family="Arial, sans-serif" font-size="10" fill="#334155">{html.escape(scenario.scenario[:36])}</text>')
        parts.append(f'<text x="{x + 190}" y="{row_y + 13}" font-family="Arial, sans-serif" font-size="10" fill="#0f172a">{html.escape(winner)}</text>')
        parts.append(f'<text x="{x + 260}" y="{row_y + 13}" font-family="Arial, sans-serif" font-size="10" fill="#0f172a">{html.escape(confidence)}</text>')
        parts.append(f'<text x="{x + 345}" y="{row_y + 13}" font-family="Arial, sans-serif" font-size="10" fill="#0f172a">{html.escape(scenario.decision_hint[:28])}</text>')
    return "\n  ".join(parts)


def _scenario_winner(scenario: BenchmarkScenarioResult) -> str:
    if not scenario.evidence_complete:
        return "TBD"
    counts = {"profile_a": 0, "profile_b": 0}
    for value in scenario.deltas.values():
        if isinstance(value, Mapping):
            winner = value.get("winner")
            if winner in counts:
                counts[winner] += 1
    if counts["profile_b"] > counts["profile_a"]:
        return "profile_b"
    if counts["profile_a"] > counts["profile_b"]:
        return "profile_a"
    return "tie"


def _svg_fusion_panel(
    scenarios: Sequence[BenchmarkScenarioResult],
    *,
    x: int,
    y: int,
) -> str:
    fusion = _scenario_by_id(scenarios, ComparisonScenario.QDRANT_118_PYTHON_RRF_VS_NATIVE_RRF)
    hint = "TBD" if fusion is None else fusion.decision_hint
    return (
        f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" font-size="18" font-weight="700" fill="#111827">Fusion comparison</text>'
        f'\n  <text x="{x}" y="{y + 26}" font-family="Arial, sans-serif" font-size="13" fill="#334155">Python RRF vs native RRF: {html.escape(hint)}</text>'
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


def _validate_optional_metric(value: float | None, field_name: str) -> float | None:
    clean = _validate_optional_non_negative(value, field_name)
    if clean is not None and clean > 1.0:
        raise ValueError(f"{field_name} must be <= 1")
    return clean


def _validate_optional_non_negative(value: float | None, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric or None")
    clean = float(value)
    if not math.isfinite(clean):
        raise ValueError(f"{field_name} must be finite")
    if clean < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return clean


def _validate_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _assert_safe_mapping(value: Mapping[str, object]) -> dict[str, object]:
    for key, item in value.items():
        if key in FORBIDDEN_OUTPUT_TOKENS:
            raise ValueError(f"forbidden output key: {key}")
        if isinstance(item, Mapping):
            _assert_safe_mapping(item)
        elif isinstance(item, list | tuple):
            for nested in item:
                if isinstance(nested, Mapping):
                    _assert_safe_mapping(nested)
    return dict(value)


def _assert_safe_text(text: str) -> None:
    """Reject any output that contains forbidden bare data keys.

    Keys are matched as quoted JSON tokens so that safe metadata fields that
    share a prefix (e.g. ``dense_vector_name``, ``sparse_vector_name``) are
    not caught as false positives.  Each entry in *forbidden* is a complete
    quoted string as it would appear in JSON output.
    """
    lower = text.lower()
    forbidden = {
        '"query_text"',
        '"query"',
        '"chunk_text"',
        '"document_text"',
        '"raw_text"',
        '"dense_vector"',
        '"sparse_vector"',
        '"payload"',
        '"embedding"',
        '"embeddings"',
        '"vector"',
        '"vectors"',
        '"prompt"',
        '"answer"',
    }
    for token in forbidden:
        if token in lower:
            raise ValueError("unsafe benchmark output")


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    clean = float(value)
    return clean if math.isfinite(clean) else None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    clean = value.strip()
    return clean or None


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _optional_int_to_float(value: int | None) -> float | None:
    return None if value is None else float(value)


def _coerce_fusion_backend(value: object) -> FusionBackend:
    if value in {"python_rrf", "qdrant_rrf", "qdrant_weighted_rrf", "none"}:
        return value  # type: ignore[return-value]
    raise ValueError("unsupported fusion backend")


def _coerce_retrieval_mode(value: object) -> RetrievalMode:
    if value in {"dense_only", "hybrid"}:
        return value  # type: ignore[return-value]
    raise ValueError("unsupported retrieval mode")


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}".rstrip("0").rstrip(".") if value != 0.0 else "0.0"


if __name__ == "__main__":
    raise SystemExit(main())
