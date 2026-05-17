"""Versioned embedding profile contract for RAG-1A PR-04A.

This module validates embedding metadata only. It must not instantiate
embedding models, connect to vector stores, create collections, or alter the
current dense-only runtime behavior.

Pydantic ``frozen=True`` protects normal assignment/deletion. It is not a
security boundary against CPython escape hatches such as ``object.__setattr__``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

STRICT_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, strict=True)
RAG1A_ALLOWED_ACTIVE_PROFILES = frozenset({"nomic_dense_v1"})
KNOWN_MODEL_DIMENSIONS = {
    "nomic": 768,
    "qwen3": 4096,
}
KNOWN_CONTEXT_LIMITS = {
    "nomic": 2048,
    "qwen3": 32768,
}
SUPPORTED_NORMALIZED_DISTANCES = frozenset({"cosine", "dot"})
VERSION_PATTERN = re.compile(r"^v\d+(?:\.\d+)?$")


class EmbeddingProfileConfig(BaseModel):
    """Immutable contract for one embedding vector space."""

    model_config = STRICT_MODEL_CONFIG

    provider: str
    model: str
    model_family: str
    version: str
    dimensions: int = Field(gt=0)
    effective_dimensions: int | None = Field(default=None, gt=0)
    mrl_supported: bool = False
    context_length: int | None = Field(default=None, gt=0)
    distance: str
    normalized: bool
    instruction_aware: bool = False
    query_instruction: str | None = None
    document_instruction: str | None = None
    profile_fingerprint: str | None = None

    @field_validator(
        "provider",
        "model",
        "model_family",
        "version",
        "distance",
        mode="after",
    )
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        """Reject empty strings in required text fields."""
        clean = value.strip()
        if not clean:
            raise ValueError("required string fields cannot be empty")
        return clean

    @field_validator("version", mode="before")
    @classmethod
    def validate_version_format(cls, value: object) -> object:
        """Require profile versions like ``v1`` or ``v1.2``."""
        if not isinstance(value, str):
            raise ValueError("version must match 'v<major>' or 'v<major>.<minor>'")
        clean = value.strip()
        if VERSION_PATTERN.fullmatch(clean) is None:
            raise ValueError("version must match 'v<major>' or 'v<major>.<minor>'")
        return clean

    @field_validator("distance", mode="after")
    @classmethod
    def normalize_distance(cls, value: str) -> str:
        """Normalize distance names for stable fingerprinting."""
        return value.strip().lower()

    @field_validator("model_family", mode="after")
    @classmethod
    def normalize_model_family(cls, value: str) -> str:
        """Normalize model family names for deterministic guards."""
        return value.strip().lower()

    @field_validator("query_instruction", "document_instruction", mode="before")
    @classmethod
    def normalize_optional_instruction(cls, value: object) -> object:
        """Normalize blank instructions and reject null-byte payloads."""
        if value is None or not isinstance(value, str):
            return value
        if "\x00" in value:
            raise ValueError("instruction fields cannot contain null bytes")
        clean = value.strip()
        return clean if clean else None

    @model_validator(mode="after")
    def validate_known_dimensions(self) -> EmbeddingProfileConfig:
        """Reject known model families configured with incompatible dimensions."""
        expected_dimensions = KNOWN_MODEL_DIMENSIONS.get(self.model_family)
        if expected_dimensions is not None and self.dimensions != expected_dimensions:
            raise ValueError(
                f"model_family {self.model_family!r} requires "
                f"dimensions={expected_dimensions}"
            )
        return self

    @model_validator(mode="after")
    def validate_mrl_consistency(self) -> EmbeddingProfileConfig:
        """Ensure Matryoshka dimensions are explicit and internally valid."""
        if self.effective_dimensions is not None and not self.mrl_supported:
            raise ValueError(
                "effective_dimensions requires mrl_supported=true"
            )
        if (
            self.effective_dimensions is not None
            and self.effective_dimensions > self.dimensions
        ):
            raise ValueError("effective_dimensions must be <= dimensions")
        return self

    @model_validator(mode="after")
    def validate_instruction_contract(self) -> EmbeddingProfileConfig:
        """Keep query instructions aligned with instruction-aware models."""
        if self.instruction_aware and not _has_text(self.query_instruction):
            raise ValueError(
                "instruction_aware=true requires query_instruction"
            )
        if not self.instruction_aware and self.query_instruction is not None:
            raise ValueError(
                "instruction_aware=false requires query_instruction=null"
            )
        return self

    @model_validator(mode="after")
    def validate_distance_normalization(self) -> EmbeddingProfileConfig:
        """Validate distance semantics against vector normalization."""
        if self.normalized and self.distance not in SUPPORTED_NORMALIZED_DISTANCES:
            raise ValueError("normalized=true requires distance in {'cosine', 'dot'}")
        if not self.normalized and self.distance == "dot":
            raise ValueError("normalized=false cannot use distance='dot'")
        return self

    @model_validator(mode="after")
    def validate_context_length(self) -> EmbeddingProfileConfig:
        """Reject context windows above known family limits."""
        if self.context_length is None:
            return self
        max_context_length = KNOWN_CONTEXT_LIMITS.get(self.model_family)
        if (
            max_context_length is not None
            and self.context_length > max_context_length
        ):
            raise ValueError(
                f"model_family {self.model_family!r} supports context_length "
                f"<= {max_context_length}"
            )
        return self

    @model_validator(mode="after")
    def validate_declared_fingerprint(self) -> EmbeddingProfileConfig:
        """Validate a declared fingerprint without requiring one in YAML."""
        if self.profile_fingerprint is None:
            return self
        # deferred import: breaks circular dependency with embedding_metadata.
        from backend.rag.embedding_metadata import compute_profile_fingerprint

        expected = compute_profile_fingerprint(self)
        if self.profile_fingerprint != expected:
            raise ValueError("profile_fingerprint does not match profile metadata")
        return self


class CollectionBindingConfig(BaseModel):
    """Declarative mapping from collection name to embedding profile."""

    model_config = STRICT_MODEL_CONFIG

    profile: str

    @field_validator("profile", mode="after")
    @classmethod
    def profile_must_not_be_empty(cls, value: str) -> str:
        """Reject empty profile references."""
        clean = value.strip()
        if not clean:
            raise ValueError("collection binding profile cannot be empty")
        return clean


class EmbeddingsConfig(BaseModel):
    """Versioned embedding profile registry for the RAG config contract."""

    model_config = STRICT_MODEL_CONFIG

    config_version: str
    active_profile: str
    candidate_profiles: list[str] = Field(default_factory=list)
    profiles: dict[str, EmbeddingProfileConfig]
    collection_bindings: dict[str, CollectionBindingConfig]

    @field_validator("config_version", mode="after")
    @classmethod
    def config_version_must_be_v1(cls, value: str) -> str:
        """Accept only schema version 1.x in PR-04A."""
        if not value.startswith("1."):
            raise ValueError("embeddings.config_version must start with '1.'")
        return value

    @field_validator("active_profile", mode="after")
    @classmethod
    def active_profile_must_not_be_empty(cls, value: str) -> str:
        """Reject empty active profile identifiers."""
        clean = value.strip()
        if not clean:
            raise ValueError("active_profile cannot be empty")
        return clean

    @field_validator("candidate_profiles", mode="after")
    @classmethod
    def candidate_profiles_must_be_unique(cls, value: list[str]) -> list[str]:
        """Reject duplicate candidate profile identifiers."""
        if len(value) != len(set(value)):
            raise ValueError("candidate_profiles must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_active_profile_exists(self) -> EmbeddingsConfig:
        """Require the active profile to exist in the profile registry."""
        if self.active_profile not in self.profiles:
            raise ValueError(f"active_profile {self.active_profile!r} is not defined")
        return self

    @model_validator(mode="after")
    def validate_candidate_profiles_exist(self) -> EmbeddingsConfig:
        """Require all candidates to exist in the profile registry."""
        missing = sorted(set(self.candidate_profiles) - set(self.profiles))
        if missing:
            raise ValueError(f"candidate_profiles are not defined: {missing}")
        return self

    @model_validator(mode="after")
    def validate_collection_bindings(self) -> EmbeddingsConfig:
        """Require every collection binding to reference a known profile."""
        missing = sorted(
            {
                binding.profile
                for binding in self.collection_bindings.values()
                if binding.profile not in self.profiles
            }
        )
        if missing:
            raise ValueError(f"collection_bindings reference unknown profiles: {missing}")
        return self

    @model_validator(mode="after")
    def validate_sprint_guards(self) -> EmbeddingsConfig:
        """Keep RAG-1A runtime on the current Nomic profile only.

        Sprint guard: relax this when Qwen3 becomes an allowed
        ``active_profile`` during the embedding migration sprint.
        """
        if self.active_profile not in RAG1A_ALLOWED_ACTIVE_PROFILES:
            allowed = sorted(RAG1A_ALLOWED_ACTIVE_PROFILES)
            raise ValueError(
                f"active_profile {self.active_profile!r} is not enabled in RAG-1A "
                f"- allowed profiles: {allowed}"
            )
        for collection_name, binding in self.collection_bindings.items():
            if binding.profile != self.active_profile:
                raise ValueError(
                    f"collection {collection_name!r} must remain bound to "
                    f"active_profile {self.active_profile!r} in RAG-1A"
                )
        return self


def load_embeddings_config(path: Path) -> EmbeddingsConfig:
    """Load and validate the ``embeddings`` config block.

    Args:
        path: YAML file containing either an ``embeddings`` top-level block or
            the embeddings mapping itself.

    Returns:
        The validated embedding profile registry.

    Raises:
        ValueError: If the YAML shape is invalid or violates PR-04A guards.
        yaml.YAMLError: If the YAML file cannot be parsed.
    """
    raw_yaml = path.read_text(encoding="utf-8")
    raw_config = yaml.safe_load(raw_yaml)
    if not isinstance(raw_config, Mapping):
        raise ValueError("embedding config YAML must contain a mapping")

    embeddings_config = raw_config.get("embeddings", raw_config)
    if not isinstance(embeddings_config, Mapping):
        raise ValueError("embeddings block must contain a mapping")

    return EmbeddingsConfig.model_validate(
        cast("dict[str, object]", embeddings_config)
    )


def _has_text(value: str | None) -> bool:
    return value is not None and "\x00" not in value and bool(value.strip())


__all__ = [
    "CollectionBindingConfig",
    "EmbeddingProfileConfig",
    "EmbeddingsConfig",
    "load_embeddings_config",
]
