"""Pure helpers for versioned embedding metadata compatibility."""

from __future__ import annotations

import hashlib
import json

from backend.rag.embedding_config import EmbeddingProfileConfig


def compute_profile_fingerprint(profile: EmbeddingProfileConfig) -> str:
    """Return a stable short fingerprint for an embedding vector space.

    Args:
        profile: Validated embedding profile metadata.

    Returns:
        A 16-character SHA-256 hex prefix derived from vector-space-defining
        fields only.
    """
    effective_dimensions = profile.effective_dimensions or profile.dimensions
    key_fields = {
        "model": profile.model,
        "model_family": profile.model_family,
        "effective_dimensions": effective_dimensions,
        "distance": profile.distance,
        "normalized": profile.normalized,
        "document_instruction": profile.document_instruction,
    }
    canonical = json.dumps(key_fields, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def profiles_are_compatible(
    a: EmbeddingProfileConfig,
    b: EmbeddingProfileConfig,
) -> bool:
    """Return whether two profiles define the same embedding vector space.

    Args:
        a: First validated embedding profile.
        b: Second validated embedding profile.

    Returns:
        ``True`` only when model identity, effective dimensions, distance,
        normalization, and document-side instruction metadata are identical.
    """
    effective_a = a.effective_dimensions or a.dimensions
    effective_b = b.effective_dimensions or b.dimensions
    return (
        a.model == b.model
        and a.model_family == b.model_family
        and effective_a == effective_b
        and a.distance == b.distance
        and a.normalized == b.normalized
        and a.document_instruction == b.document_instruction
    )


__all__ = [
    "compute_profile_fingerprint",
    "profiles_are_compatible",
]
