"""Shared type contracts for the semantic retrieval cache."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, Protocol


CachePayloadValue = bool | int | float | str | None | Sequence[str] | Sequence[float]
CacheFilterValue = bool | int | str
CacheFusionBackend = Literal["python_rrf", "qdrant_rrf"]


class CacheCollectionClient(Protocol):
    """Minimum async Qdrant surface used by CacheCollectionManager."""

    async def collection_exists(self, collection_name: str) -> bool: ...

    async def create_collection(self, **kwargs: Any) -> Any: ...

    async def get_collection(self, collection_name: str) -> Any: ...

    async def create_payload_index(self, **kwargs: Any) -> Any: ...


class CacheLayerClient(Protocol):
    """Minimum async Qdrant surface used by CacheLayer."""

    async def query_points(self, **kwargs: Any) -> Any: ...

    async def upsert(self, **kwargs: Any) -> Any: ...

    async def count(self, **kwargs: Any) -> Any: ...

    async def delete(self, **kwargs: Any) -> Any: ...

    async def scroll(self, **kwargs: Any) -> Any: ...

    async def set_payload(self, **kwargs: Any) -> Any: ...
