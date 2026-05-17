"""Shadow collection contract for Qwen3 dense embedding experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Final

from backend.rag.embedding_config import EmbeddingProfileConfig
from backend.rag.embedding_metadata import compute_profile_fingerprint

QWEN3_SHADOW_COLLECTION: Final[str] = "quimera_knowledge_qwen3_dense_v1"
SHADOW_COLLECTIONS: Final[frozenset[str]] = frozenset({QWEN3_SHADOW_COLLECTION})
PROTECTED_COLLECTIONS: Final[frozenset[str]] = frozenset(
    {
        "quimera_knowledge",
        "quimera_knowledge_v2",
    }
)


def assert_collection_is_shadow(name: str) -> None:
    """Validate that *name* is an explicitly declared shadow collection."""
    clean_name = name.strip()
    if clean_name in PROTECTED_COLLECTIONS:
        raise ValueError(
            f"Collection {clean_name!r} is protected; PR-04B may only target "
            f"shadow collections: {sorted(SHADOW_COLLECTIONS)}"
        )
    if clean_name not in SHADOW_COLLECTIONS:
        raise ValueError(
            f"Collection {clean_name!r} is not a declared shadow collection"
        )


@dataclass(frozen=True, slots=True)
class VectorPayloadMetadata:
    """Embedding provenance metadata safe to attach to vector payloads."""

    model: str
    model_family: str
    dimensions: int
    effective_dimensions: int
    distance: str
    normalized: bool
    version: str
    query_instruction: str | None
    provider: str
    profile_fingerprint: str
    indexed_at: str

    @classmethod
    def from_profile(
        cls,
        profile: EmbeddingProfileConfig,
        *,
        indexed_at: datetime | None = None,
    ) -> VectorPayloadMetadata:
        """Build payload metadata from a validated PR-04A profile."""
        effective_dimensions = profile.effective_dimensions or profile.dimensions
        timestamp = indexed_at or datetime.now(tz=timezone.utc)
        return cls(
            model=profile.model,
            model_family=profile.model_family,
            dimensions=profile.dimensions,
            effective_dimensions=effective_dimensions,
            distance=profile.distance,
            normalized=profile.normalized,
            version=profile.version,
            query_instruction=profile.query_instruction,
            provider=profile.provider,
            profile_fingerprint=compute_profile_fingerprint(profile),
            indexed_at=timestamp.isoformat(),
        )

    def to_payload(self) -> dict[str, object]:
        """Return a JSON-serializable payload metadata mapping."""
        return asdict(self)


__all__ = [
    "PROTECTED_COLLECTIONS",
    "QWEN3_SHADOW_COLLECTION",
    "SHADOW_COLLECTIONS",
    "VectorPayloadMetadata",
    "assert_collection_is_shadow",
]
