"""Read-only provider registry for dense embedding adapters.

The registry is intentionally tiny in PR-04B: it only provides an immutable
lookup surface and duplicate-provider guards. Runtime promotion of Qwen3 or any
other provider remains out of scope.
"""

from __future__ import annotations

from collections.abc import Mapping
from threading import RLock
from types import MappingProxyType
from typing import Protocol

from backend.rag.embedder_protocol import DenseEmbedder
from backend.rag.embedding_config import EmbeddingProfileConfig


class EmbedderFactory(Protocol):
    """Factory that builds a dense embedder from a validated profile."""

    def __call__(self, profile: EmbeddingProfileConfig) -> DenseEmbedder:
        """Return a dense embedder for ``profile``."""
        ...


_REGISTRY: dict[str, EmbedderFactory] = {}
_REGISTRY_LOCK = RLock()


def get_registry() -> Mapping[str, EmbedderFactory]:
    """Return a read-only snapshot of registered dense embedder factories.

    Returns:
        Immutable provider-to-factory mapping. Mutating the returned object is
        impossible, and later registrations do not mutate previous snapshots.
    """
    with _REGISTRY_LOCK:
        return MappingProxyType(dict(_REGISTRY))


def register(provider: str, factory: EmbedderFactory) -> None:
    """Register a provider factory exactly once.

    Args:
        provider: Provider key, normalized with ``strip().casefold()``.
        factory: Factory callable for the provider.

    Raises:
        ValueError: If ``provider`` is empty, contains a null byte, or was
            already registered.
    """
    provider_key = _normalize_provider(provider)
    with _REGISTRY_LOCK:
        if provider_key in _REGISTRY:
            raise ValueError(f"embedder provider {provider_key!r} is already registered")
        _REGISTRY[provider_key] = factory


def clear_registry_for_tests() -> None:
    """Clear registered providers for isolated unit tests.

    Production code should not call this helper. It exists so randomized test
    order and repeated local test runs do not depend on global module state.
    """
    with _REGISTRY_LOCK:
        _REGISTRY.clear()


def _normalize_provider(provider: str) -> str:
    if "\x00" in provider:
        raise ValueError("provider cannot contain null bytes")
    provider_key = provider.strip().casefold()
    if not provider_key:
        raise ValueError("provider cannot be empty")
    return provider_key


__all__ = ["EmbedderFactory", "clear_registry_for_tests", "get_registry", "register"]
