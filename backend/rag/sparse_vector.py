"""Sparse vector contract for future Qdrant BM25 retrieval.

This module intentionally imports no Qdrant client. It only models the
metadata shape Qdrant sparse vectors use: ``indices`` plus ``values``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SparseVector:
    """Sparse embedding vector compatible with the Qdrant sparse contract.

    Args:
        indices: Non-negative integer indices for non-zero sparse dimensions.
        values: Sparse weights, aligned one-to-one with ``indices``.

    Raises:
        ValueError: If lengths differ, indices are negative/duplicated, or
            values are non-finite.
    """

    indices: list[int]
    values: list[float]

    def __post_init__(self) -> None:
        copied_indices = [int(index) for index in self.indices]
        copied_values = [float(value) for value in self.values]
        object.__setattr__(self, "indices", copied_indices)
        object.__setattr__(self, "values", copied_values)

        if len(copied_indices) != len(copied_values):
            raise ValueError(
                "SparseVector requires len(indices) == len(values), "
                f"got {len(copied_indices)} vs {len(copied_values)}"
            )
        if any(index < 0 for index in copied_indices):
            raise ValueError("SparseVector indices must be non-negative integers")
        if len(set(copied_indices)) != len(copied_indices):
            raise ValueError("SparseVector indices must be unique")
        if any(not math.isfinite(value) for value in copied_values):
            raise ValueError("SparseVector values must be finite floats")

    @property
    def nnz(self) -> int:
        """Return the number of non-zero sparse dimensions."""
        return len(self.indices)

    def is_empty(self) -> bool:
        """Return True when the vector has no active sparse dimensions."""
        return self.nnz == 0

    def to_qdrant_payload(self) -> dict[str, list[int] | list[float]]:
        """Return a Qdrant-compatible sparse vector payload without Qdrant."""
        return {
            "indices": list(self.indices),
            "values": list(self.values),
        }


__all__ = ["SparseVector"]
