"""DCG and NDCG metrics for pure in-memory retrieval evaluation."""

from __future__ import annotations

import math
from collections.abc import Sequence


def _validate_k(k: int) -> None:
    if k <= 0:
        raise ValueError("k must be greater than zero")


def _validate_relevance_scores(relevance_scores: Sequence[float]) -> None:
    for score in relevance_scores:
        if not math.isfinite(score):
            raise ValueError("relevance_scores must contain only finite values")
        if score < 0.0:
            raise ValueError("relevance_scores must not contain negative values")


def dcg_at_k(relevance_scores: Sequence[float], k: int) -> float:
    """Return discounted cumulative gain at k with exponential gains.

    Args:
        relevance_scores: Ranked relevance grades where larger is better.
        k: Cutoff rank.

    Returns:
        DCG@k using ``(2**rel - 1) / log2(rank + 1)``.

    Raises:
        ValueError: If ``k <= 0`` or any relevance score is negative or
            non-finite.

    Example:
        >>> dcg_at_k([2.0, 1.0], 2)
        3.6309297535714573
    """

    _validate_k(k)
    _validate_relevance_scores(relevance_scores)

    total = 0.0
    for rank, relevance in enumerate(relevance_scores[:k], start=1):
        gain = math.pow(2.0, relevance) - 1.0
        discount = math.log2(float(rank) + 1.0)
        total += gain / discount

    return total


def ndcg_at_k(relevance_scores: Sequence[float], k: int) -> float:
    """Return normalized discounted cumulative gain at k.

    Args:
        relevance_scores: Ranked relevance grades where larger is better.
        k: Cutoff rank.

    Returns:
        NDCG@k, or ``0.0`` when ideal DCG is zero.

    Raises:
        ValueError: If ``k <= 0`` or any relevance score is negative or
            non-finite.

    Example:
        >>> ndcg_at_k([1.0, 0.0, 2.0], 3)
        0.6885288806643944
    """

    _validate_k(k)
    _validate_relevance_scores(relevance_scores)

    actual = dcg_at_k(relevance_scores, k)
    ideal_scores = sorted(relevance_scores, reverse=True)
    ideal = dcg_at_k(ideal_scores, k)
    if ideal == 0.0:
        return 0.0

    return actual / ideal


def mean_ndcg_at_k(
    results: Sequence[Sequence[float]],
    k: int,
) -> float:
    """Return the macro-average of NDCG at k over relevance-score rankings.

    Args:
        results: Sequence of per-query ranked relevance-score sequences.
        k: Cutoff rank forwarded to ``ndcg_at_k``.

    Returns:
        Arithmetic mean of per-query NDCG scores.

    Raises:
        ValueError: If ``results`` is empty, ``k <= 0``, or any relevance score
            is negative or non-finite.

    Example:
        >>> mean_ndcg_at_k([[2.0, 1.0], [0.0, 0.0]], 2)
        0.5
    """

    if not results:
        raise ValueError("results must not be empty")

    total = 0.0
    for relevance_scores in results:
        total += ndcg_at_k(relevance_scores, k)

    return total / float(len(results))
