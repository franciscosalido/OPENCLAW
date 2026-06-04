"""Shared type contracts for the semantic retrieval cache."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal


CachePayloadValue = bool | int | float | str | None | Sequence[str] | Sequence[float]
CacheFilterValue = bool | int | str
CacheFusionBackend = Literal["python_rrf", "qdrant_rrf"]

