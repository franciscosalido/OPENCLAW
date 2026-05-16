"""Validated RAG retrieval configuration contract for RAG-1A PR-04.

This module defines the YAML contract for dense, hybrid, and future agentic
retrieval settings. PR-04 is intentionally configuration-only: loading this
contract must not instantiate retrievers, connect to Qdrant, build sparse
indexes, or alter collections.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field

RetrievalMode = Literal["dense", "hybrid", "agentic"]
FusionStrategy = Literal["rrf"]
NoResultFallback = Literal["empty", "relax_threshold", "rewrite_query"]
DenseProvider = Literal["ollama"]
SparseProvider = Literal["fastembed"]
ToolParameterType = Literal["string", "integer"]

STRICT_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)


class FusionConfig(BaseModel):
    """Reciprocal-rank-fusion configuration contract."""

    model_config = STRICT_MODEL_CONFIG

    strategy: FusionStrategy
    rrf_k: int = Field(gt=0)


class QueryRewriteConfig(BaseModel):
    """Future query rewrite policy, disabled in PR-04."""

    model_config = STRICT_MODEL_CONFIG

    enabled: bool
    model: str | None
    max_attempts: int = Field(ge=1)


class RetrievalConfig(BaseModel):
    """Top-level retrieval policy shared by dense and future modes."""

    model_config = STRICT_MODEL_CONFIG

    mode: RetrievalMode
    max_rounds: int = Field(ge=1)
    top_k: int = Field(gt=0)
    fusion: FusionConfig
    min_score: float | None
    no_result_fallback: NoResultFallback
    query_rewrite: QueryRewriteConfig


class HybridCollectionsConfig(BaseModel):
    """Logical corpus-to-collection names for future hybrid retrieval."""

    model_config = STRICT_MODEL_CONFIG

    internal: str
    financial: str
    default: str


class DenseVectorConfig(BaseModel):
    """Dense vector model metadata for the current dense-only baseline."""

    model_config = STRICT_MODEL_CONFIG

    provider: DenseProvider
    model: str
    dimensions: int = Field(gt=0)
    model_version: str


class SparseVectorConfig(BaseModel):
    """Sparse vector model metadata reserved for a future RAG sprint."""

    model_config = STRICT_MODEL_CONFIG

    provider: SparseProvider
    model: str
    tokenizer_language: str
    model_version: str


class HybridSearchConfig(BaseModel):
    """Hybrid retrieval config block, present but disabled in PR-04."""

    model_config = STRICT_MODEL_CONFIG

    enabled: bool
    dense_vector_name: str
    sparse_vector_name: str
    collections: HybridCollectionsConfig
    dense: DenseVectorConfig
    sparse: SparseVectorConfig


class AgenticPolicyConfig(BaseModel):
    """Agentic retrieval policy block, present but disabled in PR-04."""

    model_config = STRICT_MODEL_CONFIG

    enabled: bool
    allow_query_decomposition: bool
    allow_iterative_retrieval: bool
    max_retrieval_steps: int = Field(ge=1)
    max_tool_calls: int = Field(ge=1)
    max_query_rewrites: int = Field(ge=0)
    max_context_reads: int = Field(ge=1)


class ToolParameterConfig(BaseModel):
    """Metadata for one future retrieval tool parameter."""

    model_config = STRICT_MODEL_CONFIG

    name: str
    type: ToolParameterType
    required: bool
    enum: tuple[str, ...] | None = None
    default: str | int | None = None


class ToolMetadataConfig(BaseModel):
    """Read-only tool metadata contract for future Agentic RAG."""

    model_config = STRICT_MODEL_CONFIG

    name: str
    description: str
    parameters: tuple[ToolParameterConfig, ...]


class RagConfig(BaseModel):
    """Validated RAG retrieval configuration.

    The legacy ``rag``, ``gateway``, and ``agent0`` mappings remain accepted so
    the existing runtime loaders can keep reading ``config/rag_config.yaml``
    without behavior changes while PR-04 introduces the stricter retrieval
    contract at the top level.
    """

    model_config = STRICT_MODEL_CONFIG

    config_version: str
    retrieval: RetrievalConfig
    hybrid_search: HybridSearchConfig
    agentic_policy: AgenticPolicyConfig
    tool_metadata: ToolMetadataConfig
    rag: dict[str, object] | None = None
    gateway: dict[str, object] | None = None
    agent0: dict[str, object] | None = None


def load_rag_config(path: Path) -> RagConfig:
    """Load and validate the PR-04 RAG configuration contract.

    Args:
        path: Path to a YAML file matching the PR-04 RAG config schema.

    Returns:
        A fully validated ``RagConfig`` instance.

    Raises:
        ValueError: If YAML is not a mapping, config version is unsupported,
            hybrid/agentic behavior is enabled, or another future-only option
            is activated in this dense-only sprint.
        yaml.YAMLError: If the YAML file cannot be parsed.

    Example:
        ``config = load_rag_config(Path("config/rag_config.yaml"))``
    """
    raw_yaml = path.read_text(encoding="utf-8")
    raw_config = yaml.safe_load(raw_yaml)
    if not isinstance(raw_config, dict):
        raise ValueError("rag_config.yaml must contain a YAML mapping")

    config = RagConfig.model_validate(cast("dict[str, object]", raw_config))
    _validate_pr04_runtime_guards(config)
    return config


def _validate_pr04_runtime_guards(config: RagConfig) -> None:
    """Reject future retrieval modes while PR-04 remains config-only."""
    if not config.config_version.startswith("1."):
        raise ValueError("config_version must start with '1.'")

    if config.retrieval.mode == "hybrid":
        raise ValueError("retrieval.mode 'hybrid' requires future RAG sprint")

    if config.retrieval.mode == "agentic":
        raise ValueError(
            "retrieval.mode 'agentic' reserved for Agentic RAG sprint"
        )

    if config.hybrid_search.enabled:
        raise ValueError("hybrid_search.enabled must be false in RAG-1A PR04")

    if config.retrieval.no_result_fallback != "empty":
        raise ValueError(
            "retrieval.no_result_fallback must be 'empty' in RAG-1A PR04"
        )

    if config.retrieval.query_rewrite.enabled:
        raise ValueError(
            "retrieval.query_rewrite.enabled must be false in RAG-1A PR04"
        )

    if config.agentic_policy.enabled:
        raise ValueError("agentic_policy.enabled must be false in RAG-1A PR04")


__all__ = [
    "AgenticPolicyConfig",
    "DenseVectorConfig",
    "FusionConfig",
    "HybridCollectionsConfig",
    "HybridSearchConfig",
    "QueryRewriteConfig",
    "RagConfig",
    "RetrievalConfig",
    "SparseVectorConfig",
    "ToolMetadataConfig",
    "ToolParameterConfig",
    "load_rag_config",
]
