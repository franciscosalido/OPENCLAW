"""Qdrant 1.18 hybrid benchmark schema contract for Quimera.

This module owns schema factory, validation and safe snapshots only. It does
not implement retrieval, ingest, fusion, tuning or benchmark logic.
"""

from __future__ import annotations

import importlib.metadata
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, cast

BENCHMARK_COLLECTION = "quimera_benchmark_hybrid_118"
CANDIDATE_COLLECTION = "quimera_knowledge_v2"
LEGACY_COLLECTION = "quimera_knowledge"
SCHEMA_VERSION = "qdrant-hybrid-118-v1"
DEFAULT_DENSE_VECTOR_NAME = "dense"
DEFAULT_SPARSE_VECTOR_NAME = "sparse"
DEFAULT_DENSE_DIMENSIONS = 1024
DEFAULT_DENSE_DISTANCE = "COSINE"
DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_EMBEDDING_PROVIDER = "local"
DEFAULT_EMBEDDING_VERSION = "qwen3-embedding-0.6b@benchmark"
SNAPSHOT_ROOT = Path("docs/specs/qdrant-1-18-upgrade")

PAYLOAD_INDEX_TYPES: Mapping[str, str] = MappingProxyType(
    {
        "doc_id": "keyword",
        "chunk_id": "keyword",
        "chunk_index": "integer",
        "source": "keyword",
        "schema_version": "keyword",
        "embedding_model": "keyword",
        "embedding_provider": "keyword",
        "embedding_dimensions": "integer",
        "embedding_version": "keyword",
        "corpus_id": "keyword",
        "security_level": "keyword",
    }
)
FORBIDDEN_SPEC_FIELDS = frozenset(
    {
        "answer",
        "chunk_text",
        "content",
        "dense_vector",
        "embedding",
        "embeddings",
        "payload",
        "prompt",
        "query",
        "sparse_vector",
        "text",
        "vector",
        "vectors",
    }
)
ALLOWED_PAYLOAD_INDEX_SCHEMAS = frozenset(
    {"keyword", "integer", "float", "datetime", "uuid", "text", "geo"}
)


class HybridSchemaError(RuntimeError):
    """Raised when Qdrant hybrid schema validation or creation fails."""


@dataclass(frozen=True, slots=True)
class PayloadIndexSpec:
    """One payload index field and Qdrant field schema."""

    field_name: str
    field_schema: str

    def __post_init__(self) -> None:
        clean_name = _validate_text(self.field_name, "field_name")
        clean_schema = _validate_text(self.field_schema, "field_schema").casefold()
        if clean_schema not in ALLOWED_PAYLOAD_INDEX_SCHEMAS:
            raise ValueError("field_schema is not supported")
        object.__setattr__(self, "field_name", clean_name)
        object.__setattr__(self, "field_schema", clean_schema)


@dataclass(frozen=True, slots=True)
class HybridCollectionSpec118:
    """Immutable Qdrant 1.18 benchmark hybrid collection specification."""

    collection_name: str = BENCHMARK_COLLECTION
    dense_vector_name: str = DEFAULT_DENSE_VECTOR_NAME
    sparse_vector_name: str = DEFAULT_SPARSE_VECTOR_NAME
    dense_dimensions: int = DEFAULT_DENSE_DIMENSIONS
    dense_distance: str = DEFAULT_DENSE_DISTANCE
    schema_version: str = SCHEMA_VERSION
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_provider: str = DEFAULT_EMBEDDING_PROVIDER
    embedding_dimensions: int = DEFAULT_DENSE_DIMENSIONS
    embedding_version: str = DEFAULT_EMBEDDING_VERSION
    payload_indexes: tuple[str, ...] = tuple(PAYLOAD_INDEX_TYPES)
    payload_index_types: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType(dict(PAYLOAD_INDEX_TYPES))
    )

    def __post_init__(self) -> None:
        clean_payload_indexes = tuple(
            _validate_text(name, "payload_index") for name in self.payload_indexes
        )
        clean_payload_index_types = MappingProxyType(
            {
                _validate_text(name, "payload_index_type_key"): _validate_text(
                    schema,
                    "payload_index_type_value",
                ).casefold()
                for name, schema in self.payload_index_types.items()
            }
        )
        object.__setattr__(
            self,
            "collection_name",
            _validate_text(self.collection_name, "collection_name"),
        )
        object.__setattr__(
            self,
            "dense_vector_name",
            _validate_text(self.dense_vector_name, "dense_vector_name"),
        )
        object.__setattr__(
            self,
            "sparse_vector_name",
            _validate_text(self.sparse_vector_name, "sparse_vector_name"),
        )
        object.__setattr__(
            self,
            "dense_distance",
            _validate_text(self.dense_distance, "dense_distance"),
        )
        object.__setattr__(
            self,
            "schema_version",
            _validate_text(self.schema_version, "schema_version"),
        )
        object.__setattr__(
            self,
            "embedding_model",
            _validate_text(self.embedding_model, "embedding_model"),
        )
        object.__setattr__(
            self,
            "embedding_provider",
            _validate_text(self.embedding_provider, "embedding_provider"),
        )
        object.__setattr__(
            self,
            "embedding_version",
            _validate_text(self.embedding_version, "embedding_version"),
        )
        object.__setattr__(self, "payload_indexes", clean_payload_indexes)
        object.__setattr__(self, "payload_index_types", clean_payload_index_types)
        validate_spec_118(self)

    def required_payload_fields(self) -> frozenset[str]:
        """Return the exact required payload metadata fields."""

        return frozenset(self.payload_indexes)

    def to_safe_dict(self) -> dict[str, object]:
        """Return a safe schema summary without point payloads or vectors."""

        return {
            "collection_name": self.collection_name,
            "dense_vector_name": self.dense_vector_name,
            "sparse_vector_name": self.sparse_vector_name,
            "dense_dimensions": self.dense_dimensions,
            "dense_distance": self.dense_distance,
            "schema_version": self.schema_version,
            "embedding_model": self.embedding_model,
            "embedding_provider": self.embedding_provider,
            "embedding_dimensions": self.embedding_dimensions,
            "embedding_version": self.embedding_version,
            "payload_indexes": list(self.payload_indexes),
            "payload_index_types": dict(self.payload_index_types),
        }


@dataclass(frozen=True, slots=True)
class HybridCollectionSnapshot:
    """Safe snapshot of the Qdrant hybrid benchmark collection schema."""

    collection_name: str
    schema_version: str
    dense_vector_name: str
    sparse_vector_name: str
    dense_dimensions: int
    dense_distance: str
    payload_indexes: tuple[str, ...]
    qdrant_server_version: str | None = None
    qdrant_client_version: str | None = None
    optimizer_config: Mapping[str, object] | None = None
    quantization_config: Mapping[str, object] | None = None
    on_disk: bool | None = None
    telemetry: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "collection_name",
            _validate_text(self.collection_name, "collection_name"),
        )
        object.__setattr__(
            self,
            "schema_version",
            _validate_text(self.schema_version, "schema_version"),
        )
        object.__setattr__(
            self,
            "dense_vector_name",
            _validate_text(self.dense_vector_name, "dense_vector_name"),
        )
        object.__setattr__(
            self,
            "sparse_vector_name",
            _validate_text(self.sparse_vector_name, "sparse_vector_name"),
        )
        object.__setattr__(
            self,
            "dense_distance",
            _validate_text(self.dense_distance, "dense_distance"),
        )
        object.__setattr__(
            self,
            "dense_dimensions",
            _validate_positive_int(self.dense_dimensions, "dense_dimensions"),
        )
        object.__setattr__(
            self,
            "payload_indexes",
            tuple(_validate_text(name, "payload_index") for name in self.payload_indexes),
        )

    def to_safe_dict(self) -> dict[str, object]:
        """Return a safe JSON-friendly schema snapshot."""

        return {
            "collection_name": self.collection_name,
            "schema_version": self.schema_version,
            "dense_vector_name": self.dense_vector_name,
            "sparse_vector_name": self.sparse_vector_name,
            "dense_dimensions": self.dense_dimensions,
            "dense_distance": self.dense_distance,
            "payload_indexes": list(self.payload_indexes),
            "qdrant_server_version": self.qdrant_server_version,
            "qdrant_client_version": self.qdrant_client_version,
            "optimizer_config": _safe_mapping(self.optimizer_config),
            "quantization_config": _safe_mapping(self.quantization_config),
            "on_disk": self.on_disk,
            "telemetry": _safe_mapping(self.telemetry),
        }


class HybridSchemaClientProtocol(Protocol):
    """Minimal client contract for Qdrant 1.18 hybrid schema creation."""

    async def collection_exists(self, collection_name: str) -> bool:
        """Return whether a collection exists."""
        ...

    async def create_collection(self, spec: HybridCollectionSpec118) -> None:
        """Create the benchmark collection from spec."""
        ...

    async def create_payload_indexes(self, spec: HybridCollectionSpec118) -> None:
        """Create all payload indexes declared by spec."""
        ...

    async def get_collection_info(self, collection_name: str) -> Mapping[str, object]:
        """Return a safe, simplified collection info mapping."""
        ...

    async def get_qdrant_versions(self) -> Mapping[str, str | None]:
        """Return server/client versions when available."""
        ...


class QdrantHybridSchemaClient118:
    """Thin Qdrant adapter for Q18-04 schema creation only."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def collection_exists(self, collection_name: str) -> bool:
        return bool(await self._client.collection_exists(collection_name=collection_name))

    async def create_collection(self, spec: HybridCollectionSpec118) -> None:
        from qdrant_client import models

        await self._client.create_collection(
            collection_name=spec.collection_name,
            vectors_config={
                spec.dense_vector_name: models.VectorParams(
                    size=spec.dense_dimensions,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                spec.sparse_vector_name: models.SparseVectorParams()
            },
        )

    async def create_payload_indexes(self, spec: HybridCollectionSpec118) -> None:
        from qdrant_client import models

        for index in build_payload_index_specs(spec):
            await self._client.create_payload_index(
                collection_name=spec.collection_name,
                field_name=index.field_name,
                field_schema=_payload_schema_type(models, index.field_schema),
            )

    async def get_collection_info(self, collection_name: str) -> Mapping[str, object]:
        info = await self._client.get_collection(collection_name=collection_name)
        raw = _model_to_mapping(info)
        config = _safe_mapping(raw.get("config"))
        params = _safe_mapping(config.get("params")) if config else {}
        payload_schema = _safe_mapping(raw.get("payload_schema"))
        return {
            "collection_name": collection_name,
            "vectors": _extract_vectors_config(params),
            "sparse_vectors": _extract_sparse_vectors_config(params),
            "payload_indexes": tuple(sorted(payload_schema)),
            "optimizer_config": _safe_mapping(config.get("optimizer_config")) if config else {},
            "quantization_config": _safe_mapping(config.get("quantization_config")) if config else {},
        }

    async def get_qdrant_versions(self) -> Mapping[str, str | None]:
        return {
            "qdrant_server_version": None,
            "qdrant_client_version": importlib.metadata.version("qdrant-client"),
        }


def _validate_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if "\x00" in value:
        raise ValueError(f"{field_name} cannot contain null bytes")
    clean = value.strip()
    if not clean:
        raise ValueError(f"{field_name} cannot be empty")
    return clean


def _validate_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be >= 1")
    return value


def _safe_mapping(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return {
            str(key): _safe_json_value(item)
            for key, item in value.items()
            if str(key).casefold() not in FORBIDDEN_SPEC_FIELDS
        }
    return {}


def _safe_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _safe_mapping(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_safe_json_value(item) for item in value]
    return str(value)


def default_hybrid_collection_spec_118() -> HybridCollectionSpec118:
    """Return the canonical Q18-04 benchmark schema spec."""

    return HybridCollectionSpec118()


def build_vectors_config(spec: HybridCollectionSpec118) -> dict[str, object]:
    """Build conceptual dense named-vector config."""

    validate_spec_118(spec)
    return {
        spec.dense_vector_name: {
            "size": spec.dense_dimensions,
            "distance": "Cosine",
        }
    }


def build_sparse_vectors_config(spec: HybridCollectionSpec118) -> dict[str, object]:
    """Build conceptual sparse named-vector config."""

    validate_spec_118(spec)
    return {spec.sparse_vector_name: {}}


def build_payload_index_specs(
    spec: HybridCollectionSpec118,
) -> tuple[PayloadIndexSpec, ...]:
    """Build all payload index specs in canonical order."""

    validate_spec_118(spec)
    return tuple(
        PayloadIndexSpec(field_name=name, field_schema=spec.payload_index_types[name])
        for name in spec.payload_indexes
    )


def build_collection_create_payload(spec: HybridCollectionSpec118) -> dict[str, object]:
    """Build conceptual create-collection payload for docs/tests."""

    return {
        "vectors": build_vectors_config(spec),
        "sparse_vectors": build_sparse_vectors_config(spec),
    }


def validate_spec_118(spec: HybridCollectionSpec118) -> None:
    """Validate the Q18-04 benchmark schema contract."""

    if spec.collection_name != BENCHMARK_COLLECTION:
        raise ValueError("collection_name must be quimera_benchmark_hybrid_118")
    if spec.collection_name in {CANDIDATE_COLLECTION, LEGACY_COLLECTION}:
        raise ValueError("protected collections cannot be used for benchmark schema")
    if spec.dense_vector_name == spec.sparse_vector_name:
        raise ValueError("dense_vector_name and sparse_vector_name must differ")
    _validate_positive_int(spec.dense_dimensions, "dense_dimensions")
    _validate_positive_int(spec.embedding_dimensions, "embedding_dimensions")
    if spec.embedding_dimensions != spec.dense_dimensions:
        raise ValueError("embedding_dimensions must match dense_dimensions")
    if spec.dense_distance not in {"COSINE", "Cosine"}:
        raise ValueError("dense_distance must be COSINE")
    if not spec.payload_indexes:
        raise ValueError("payload_indexes cannot be empty")
    if set(spec.payload_index_types) != set(spec.payload_indexes):
        raise ValueError("payload_index_types must cover exactly payload_indexes")
    forbidden = FORBIDDEN_SPEC_FIELDS.intersection(
        name.casefold() for name in spec.payload_indexes
    )
    if forbidden:
        raise ValueError("payload_indexes contain forbidden fields")
    for field_schema in spec.payload_index_types.values():
        if field_schema not in {"keyword", "integer"}:
            raise ValueError("Q18-04 payload indexes must be keyword or integer")


def validate_collection_info_against_spec(
    collection_info: Mapping[str, object],
    spec: HybridCollectionSpec118,
) -> None:
    """Validate simplified collection info against spec."""

    validate_spec_118(spec)
    vectors = _safe_mapping(collection_info.get("vectors"))
    sparse_vectors = _safe_mapping(collection_info.get("sparse_vectors"))
    dense = _safe_mapping(vectors.get(spec.dense_vector_name))
    if not dense:
        raise HybridSchemaError("dense vector config is missing")
    if dense.get("size") != spec.dense_dimensions:
        raise HybridSchemaError("dense vector dimension mismatch")
    if str(dense.get("distance")) not in {"Cosine", "COSINE"}:
        raise HybridSchemaError("dense vector distance mismatch")
    if spec.sparse_vector_name not in sparse_vectors:
        raise HybridSchemaError("sparse vector config is missing")
    payload_indexes = collection_info.get("payload_indexes")
    if not isinstance(payload_indexes, Sequence) or isinstance(payload_indexes, (str, bytes, bytearray)):
        raise HybridSchemaError("payload_indexes must be a sequence")
    missing = set(spec.payload_indexes) - {str(name) for name in payload_indexes}
    if missing:
        raise HybridSchemaError("payload indexes are missing")


def schema_snapshot_from_collection_info(
    collection_info: Mapping[str, object],
    spec: HybridCollectionSpec118,
    *,
    server_version: str | None = None,
    client_version: str | None = None,
    telemetry: Mapping[str, object] | None = None,
) -> HybridCollectionSnapshot:
    """Create a safe schema snapshot from simplified collection info."""

    validate_collection_info_against_spec(collection_info, spec)
    dense = _safe_mapping(
        _safe_mapping(collection_info.get("vectors")).get(spec.dense_vector_name)
    )
    return HybridCollectionSnapshot(
        collection_name=spec.collection_name,
        schema_version=spec.schema_version,
        dense_vector_name=spec.dense_vector_name,
        sparse_vector_name=spec.sparse_vector_name,
        dense_dimensions=_coerce_int(dense.get("size"), "dense size"),
        dense_distance=str(dense["distance"]),
        payload_indexes=tuple(sorted(spec.payload_indexes)),
        qdrant_server_version=server_version,
        qdrant_client_version=client_version,
        optimizer_config=_safe_mapping(collection_info.get("optimizer_config")),
        quantization_config=_safe_mapping(collection_info.get("quantization_config")),
        on_disk=_extract_on_disk(collection_info, spec),
        telemetry=telemetry,
    )


def write_schema_snapshot(
    snapshot: HybridCollectionSnapshot,
    path: Path,
    *,
    allow_any_path: bool = False,
) -> None:
    """Write a safe JSON schema snapshot."""

    target = path
    if not allow_any_path:
        root = SNAPSHOT_ROOT.resolve()
        resolved = target.resolve()
        if root not in (resolved, *resolved.parents):
            raise ValueError("schema snapshot path must stay under docs/specs/qdrant-1-18-upgrade")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(snapshot.to_safe_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_metrics_probe_config(collection_name: str) -> dict[str, object]:
    """Return future Q18-05 metrics/telemetry endpoints without calling them."""

    clean_collection = _validate_text(collection_name, "collection_name")
    return {
        "metrics_endpoint": "/metrics?per_collection=true",
        "telemetry_endpoint": "/telemetry",
        "collection": clean_collection,
        "purpose": "Q18-05 benchmark input",
    }


async def ensure_benchmark_collection_118(
    client: HybridSchemaClientProtocol,
    spec: HybridCollectionSpec118,
    *,
    fail_if_exists: bool = False,
) -> HybridCollectionSnapshot:
    """Ensure the benchmark collection exists and matches the Q18-04 spec."""

    validate_spec_118(spec)
    if await client.collection_exists(spec.collection_name):
        if fail_if_exists:
            raise HybridSchemaError("benchmark collection already exists")
    else:
        await client.create_collection(spec)
        await client.create_payload_indexes(spec)

    collection_info = await client.get_collection_info(spec.collection_name)
    validate_collection_info_against_spec(collection_info, spec)
    versions = await client.get_qdrant_versions()
    return schema_snapshot_from_collection_info(
        collection_info,
        spec,
        server_version=versions.get("qdrant_server_version"),
        client_version=versions.get("qdrant_client_version"),
    )


def _payload_schema_type(models: object, schema: str) -> object:
    payload_schema_type = getattr(models, "PayloadSchemaType")
    if schema == "keyword":
        return payload_schema_type.KEYWORD
    if schema == "integer":
        return payload_schema_type.INTEGER
    raise ValueError("unsupported payload schema")


def _coerce_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HybridSchemaError(f"{field_name} must be an integer")
    return value


def _model_to_mapping(model: object) -> Mapping[str, object]:
    if hasattr(model, "model_dump"):
        dumpable = cast(Any, model)
        dumped = dumpable.model_dump(mode="json", exclude_none=True)
        if isinstance(dumped, Mapping):
            return dumped
    if isinstance(model, Mapping):
        return model
    return {}


def _extract_vectors_config(params: Mapping[str, object]) -> dict[str, object]:
    vectors = params.get("vectors")
    return _safe_mapping(vectors)


def _extract_sparse_vectors_config(params: Mapping[str, object]) -> dict[str, object]:
    sparse_vectors = params.get("sparse_vectors")
    return _safe_mapping(sparse_vectors)


def _extract_on_disk(
    collection_info: Mapping[str, object],
    spec: HybridCollectionSpec118,
) -> bool | None:
    dense = _safe_mapping(
        _safe_mapping(collection_info.get("vectors")).get(spec.dense_vector_name)
    )
    on_disk = dense.get("on_disk")
    return on_disk if isinstance(on_disk, bool) else None


__all__ = [
    "BENCHMARK_COLLECTION",
    "CANDIDATE_COLLECTION",
    "LEGACY_COLLECTION",
    "HybridCollectionSnapshot",
    "HybridCollectionSpec118",
    "HybridSchemaClientProtocol",
    "HybridSchemaError",
    "PayloadIndexSpec",
    "QdrantHybridSchemaClient118",
    "build_collection_create_payload",
    "build_payload_index_specs",
    "build_metrics_probe_config",
    "build_sparse_vectors_config",
    "build_vectors_config",
    "default_hybrid_collection_spec_118",
    "ensure_benchmark_collection_118",
    "schema_snapshot_from_collection_info",
    "validate_collection_info_against_spec",
    "validate_spec_118",
    "write_schema_snapshot",
]
