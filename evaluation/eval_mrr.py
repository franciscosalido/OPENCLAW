"""Reciprocal-rank metrics for pure in-memory retrieval evaluation."""

from __future__ import annotations

import math
from collections.abc import Sequence


def reciprocal_rank(
    retrieved_ids: Sequence[str],
    expected_ids: frozenset[str],
) -> float:
    """Return the reciprocal rank of the first relevant retrieved document.

    Args:
        retrieved_ids: Ranked sequence of retrieved document IDs. Only the
            first occurrence of each document ID can count.
        expected_ids: Unordered set of relevant document IDs.

    Returns:
        ``1 / rank`` for the first relevant document, or ``0.0`` when no
        relevant document is retrieved.

    Raises:
        ValueError: If ``expected_ids`` is empty.

    Example:
        >>> reciprocal_rank(["x", "a", "b"], frozenset({"a"}))
        0.5
    """

    if not expected_ids:
        raise ValueError("expected_ids must not be empty")
    if not retrieved_ids:
        return 0.0

    seen: set[str] = set()
    for index, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in seen:
            continue
        seen.add(doc_id)
        if doc_id in expected_ids:
            return 1.0 / float(index)

    return 0.0


def mean_reciprocal_rank(rr_scores: Sequence[float]) -> float:
    """Return the arithmetic mean of precomputed reciprocal-rank scores.

    Args:
        rr_scores: Sequence of already computed reciprocal-rank scores.

    Returns:
        Arithmetic mean of the supplied reciprocal-rank scores.

    Raises:
        ValueError: If ``rr_scores`` is empty, contains a non-finite value, or
            contains a score outside ``[0.0, 1.0]``.

    Example:
        >>> mean_reciprocal_rank([1.0, 0.5, 0.0])
        0.5
    """

    if not rr_scores:
        raise ValueError("rr_scores must not be empty")

    total = 0.0
    for score in rr_scores:
        if not math.isfinite(score):
            raise ValueError("rr_scores must contain only finite values")
        if score < 0.0 or score > 1.0:
            raise ValueError("rr_scores must be in [0.0, 1.0]")
        total += score

    return total / float(len(rr_scores))
