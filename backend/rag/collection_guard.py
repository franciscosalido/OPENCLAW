"""Traceability guard for RAG collection embedding metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from loguru import logger
from qdrant_client import QdrantClient


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAG_CONFIG_PATH = REPO_ROOT / "config" / "rag_config.yaml"
REQUIRED_EMBEDDING_METADATA_FIELDS = frozenset(
    {
        "embedding_backend",
        "embedding_model",
        "embedding_dimensions",
        "embedding_contract",
        "embedding_alias",
    }
)


class CollectionMetadataMismatchError(RuntimeError):
    """Raised when strict collection metadata validation detects drift."""


class EmbeddingDimensionMismatchError(RuntimeError):
    """Raised when stored vector dimensions diverge from active configuration."""


@dataclass(frozen=True)
class CollectionMetadataSample:
    """Summary of sampled embedding metadata from a Qdrant collection."""

    collection_name: str
    sampled_count: int
    found_backends: frozenset[str]
    found_models: frozenset[str]
    found_dimensions: frozenset[int]
    found_contracts: frozenset[str]
    found_aliases: frozenset[str]
    metadata_absent_count: int


@dataclass(frozen=True)
class CollectionMetadataCheckResult:
    """Comparison between sampled collection metadata and active config."""

    sample: CollectionMetadataSample
    active_backend: str
    active_model: str
    active_dimensions: int
    active_contract: str
    active_alias: str
    backend_matches: bool
    model_matches: bool
    dimensions_match: bool
    contract_matches: bool
    alias_matches: bool
    metadata_complete: bool


@dataclass(frozen=True)
class ActiveEmbeddingMetadata:
    """Active embedding metadata values used for payload comparison."""

    backend: str
    model: str
    dimensions: int
    contract: str
    alias: str


def load_active_embedding_metadata(
    config_path: str | Path = DEFAULT_RAG_CONFIG_PATH,
) -> ActiveEmbeddingMetadata:
    """Load active embedding metadata from ``config/rag_config.yaml``."""
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("rag_config.yaml must contain a mapping")
    rag = raw.get("rag")
    if not isinstance(rag, Mapping):
        raise ValueError("rag_config.yaml must contain rag mapping")
    embedding = rag.get("embedding")
    if not isinstance(embedding, Mapping):
        raise ValueError("rag_config.yaml must contain rag.embedding mapping")

    return ActiveEmbeddingMetadata(
        backend=_required_string(embedding, "embedding_backend"),
        model=_required_string(embedding, "embedding_model"),
        dimensions=_required_int(embedding, "embedding_dimensions"),
        contract=_required_string(embedding, "embedding_contract"),
        alias=_required_string(embedding, "embedding_alias"),
    )


def check_collection_metadata(
    client: QdrantClient,
    collection_name: str,
    *,
    active_backend: str,
    active_model: str,
    active_dimensions: int,
    active_contract: str,
    active_alias: str,
    sample_size: int = 10,
    strict: bool = False,
) -> CollectionMetadataCheckResult:
    """Sample Qdrant payload metadata and warn on embedding provenance drift.

    The guard never requests vectors and never mutates the collection.
    """
    clean_collection_name = _validate_non_empty(collection_name, "collection_name")
    clean_active_backend = _validate_non_empty(active_backend, "active_backend")
    clean_active_model = _validate_non_empty(active_model, "active_model")
    clean_active_contract = _validate_non_empty(active_contract, "active_contract")
    clean_active_alias = _validate_non_empty(active_alias, "active_alias")
    if active_dimensions <= 0:
        raise ValueError("active_dimensions must be greater than zero")
    if sample_size <= 0:
        raise ValueError("sample_size must be greater than zero")

    scroll_result = client.scroll(
        collection_name=clean_collection_name,
        limit=sample_size,
        with_payload=True,
        with_vectors=False,
    )
    points = _points_from_scroll(scroll_result)
    sample = _sample_payloads(clean_collection_name, points)

    result = CollectionMetadataCheckResult(
        sample=sample,
        active_backend=clean_active_backend,
        active_model=clean_active_model,
        active_dimensions=active_dimensions,
        active_contract=clean_active_contract,
        active_alias=clean_active_alias,
        backend_matches=_matches(sample.found_backends, clean_active_backend),
        model_matches=_matches(sample.found_models, clean_active_model),
        dimensions_match=_matches(sample.found_dimensions, active_dimensions),
        contract_matches=_matches(sample.found_contracts, clean_active_contract),
        alias_matches=_matches(sample.found_aliases, clean_active_alias),
        metadata_complete=sample.metadata_absent_count == 0,
    )

    _handle_result(result, strict=strict)
    return result


def check_collection_metadata_from_config(
    client: QdrantClient,
    collection_name: str,
    *,
    config_path: str | Path = DEFAULT_RAG_CONFIG_PATH,
    sample_size: int = 10,
    strict: bool = False,
) -> CollectionMetadataCheckResult:
    """Check collection metadata using active values from RAG config."""
    active = load_active_embedding_metadata(config_path)
    return check_collection_metadata(
        client,
        collection_name,
        active_backend=active.backend,
        active_model=active.model,
        active_dimensions=active.dimensions,
        active_contract=active.contract,
        active_alias=active.alias,
        sample_size=sample_size,
        strict=strict,
    )


def _sample_payloads(
    collection_name: str,
    points: Sequence[Any],
) -> CollectionMetadataSample:
    found_backends: set[str] = set()
    found_models: set[str] = set()
    found_dimensions: set[int] = set()
    found_contracts: set[str] = set()
    found_aliases: set[str] = set()
    metadata_absent_count = 0

    for point in points:
        payload = _payload_from_point(point)
        if not _has_required_metadata(payload):
            metadata_absent_count += 1
        _add_string(found_backends, payload.get("embedding_backend"))
        _add_string(found_models, payload.get("embedding_model"))
        _add_int(found_dimensions, payload.get("embedding_dimensions"))
        _add_string(found_contracts, payload.get("embedding_contract"))
        _add_string(found_aliases, payload.get("embedding_alias"))

    return CollectionMetadataSample(
        collection_name=collection_name,
        sampled_count=len(points),
        found_backends=frozenset(found_backends),
        found_models=frozenset(found_models),
        found_dimensions=frozenset(found_dimensions),
        found_contracts=frozenset(found_contracts),
        found_aliases=frozenset(found_aliases),
        metadata_absent_count=metadata_absent_count,
    )


def _handle_result(
    result: CollectionMetadataCheckResult,
    *,
    strict: bool,
) -> None:
    sample = result.sample
    if sample.sampled_count == 0:
        return

    if not result.dimensions_match:
        logger.warning(
            "collection_dimension_mismatch | collection={} stored_dimensions={} "
            "active_dimensions={} action={}",
            sample.collection_name,
            sorted(sample.found_dimensions),
            result.active_dimensions,
            "raise",
        )
        raise EmbeddingDimensionMismatchError(
            "Collection embedding dimensions do not match active configuration."
        )

    mismatch_reasons: list[str] = []
    if not result.metadata_complete:
        logger.warning(
            "collection_metadata_absent | collection={} absent_count={} "
            "sampled_count={} reason={}",
            sample.collection_name,
            sample.metadata_absent_count,
            sample.sampled_count,
            "collection_predates_traceability_metadata",
        )
    if not result.backend_matches:
        mismatch_reasons.append("backend")
        logger.warning(
            "collection_backend_mismatch | collection={} stored_backends={} "
            "active_backend={} action={}",
            sample.collection_name,
            sorted(sample.found_backends),
            result.active_backend,
            _action(strict),
        )
    if not result.model_matches:
        mismatch_reasons.append("model")
        logger.warning(
            "collection_model_mismatch | collection={} stored_models={} "
            "active_model={} recommendation=reindex_required action={}",
            sample.collection_name,
            sorted(sample.found_models),
            result.active_model,
            _action(strict),
        )
    if not result.contract_matches:
        mismatch_reasons.append("contract")
        logger.warning(
            "collection_contract_mismatch | collection={} stored_contracts={} "
            "active_contract={} action={}",
            sample.collection_name,
            sorted(sample.found_contracts),
            result.active_contract,
            _action(strict),
        )
    if not result.alias_matches:
        mismatch_reasons.append("alias")
        logger.warning(
            "collection_alias_mismatch | collection={} stored_aliases={} "
            "active_alias={} action={}",
            sample.collection_name,
            sorted(sample.found_aliases),
            result.active_alias,
            _action(strict),
        )

    if strict and mismatch_reasons:
        joined_reasons = ", ".join(mismatch_reasons)
        raise CollectionMetadataMismatchError(
            f"Collection embedding metadata mismatch: {joined_reasons}"
        )


def _points_from_scroll(scroll_result: object) -> Sequence[Any]:
    if isinstance(scroll_result, tuple):
        points = scroll_result[0]
    else:
        points = getattr(scroll_result, "points", scroll_result)
    if not isinstance(points, Sequence):
        raise TypeError("Qdrant scroll result did not include a point sequence")
    return points


def _payload_from_point(point: object) -> Mapping[str, Any]:
    if isinstance(point, Mapping):
        payload = point.get("payload", {})
    else:
        payload = getattr(point, "payload", {})
    if isinstance(payload, Mapping):
        return payload
    return {}


def _has_required_metadata(payload: Mapping[str, Any]) -> bool:
    return all(field in payload for field in REQUIRED_EMBEDDING_METADATA_FIELDS)


def _matches[T](found_values: frozenset[T], active_value: T) -> bool:
    return not found_values or found_values == frozenset({active_value})


def _add_string(values: set[str], value: object) -> None:
    if isinstance(value, str) and value.strip():
        values.add(value.strip())


def _add_int(values: set[int], value: object) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        values.add(value)


def _required_string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"rag.embedding.{key} must be a non-empty string")
    return value.strip()


def _required_int(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"rag.embedding.{key} must be an integer")
    if value <= 0:
        raise ValueError(f"rag.embedding.{key} must be greater than zero")
    return value


def _validate_non_empty(value: str, field_name: str) -> str:
    clean_value = value.strip()
    if not clean_value:
        raise ValueError(f"{field_name} cannot be empty")
    return clean_value


def _action(strict: bool) -> str:
    if strict:
        return "raise"
    return "warn_only"
