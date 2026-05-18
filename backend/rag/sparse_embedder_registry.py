"""Read-only registry for sparse embedding adapters."""

from __future__ import annotations

from collections.abc import Mapping
from threading import RLock
from types import MappingProxyType
from typing import Protocol

from backend.rag.sparse_embedder import BM25SparseEmbedder
from backend.rag.sparse_embedder_protocol import SparseEmbedder


class SparseEmbedderFactory(Protocol):
    """Factory that builds a sparse embedder."""

    def __call__(self) -> SparseEmbedder:
        """Return a sparse embedder instance."""
        ...


_REGISTRY: dict[str, SparseEmbedderFactory] = {}
_REGISTRY_LOCK = RLock()


def get_sparse_registry() -> Mapping[str, SparseEmbedderFactory]:
    """Return a read-only snapshot of registered sparse factories."""
    with _REGISTRY_LOCK:
        return MappingProxyType(dict(_REGISTRY))


def register_sparse(provider: str, factory: SparseEmbedderFactory) -> None:
    """Register a sparse provider factory exactly once."""
    provider_key = _normalize_provider(provider)
    with _REGISTRY_LOCK:
        if provider_key in _REGISTRY:
            raise ValueError(f"sparse provider {provider_key!r} already registered")
        _REGISTRY[provider_key] = factory


def clear_sparse_registry_for_tests() -> None:
    """Clear sparse providers for isolated unit tests."""
    with _REGISTRY_LOCK:
        _REGISTRY.clear()


def _normalize_provider(provider: str) -> str:
    if "\x00" in provider:
        raise ValueError("provider cannot contain null bytes")
    provider_key = provider.strip().casefold()
    if not provider_key:
        raise ValueError("provider cannot be empty")
    return provider_key


register_sparse("bm25", lambda: BM25SparseEmbedder())


__all__ = [
    "SparseEmbedderFactory",
    "clear_sparse_registry_for_tests",
    "get_sparse_registry",
    "register_sparse",
]
