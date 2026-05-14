"""Recall metrics for pure in-memory retrieval evaluation."""

from __future__ import annotations

from collections.abc import Sequence


def recall_at_k(
    retrieved_ids: Sequence[str],
    expected_ids: frozenset[str],
    k: int,
) -> float:
    """Return the fraction of relevant documents found in the top-k results.

    Args:
        retrieved_ids: Ranked sequence of retrieved document IDs. Rank position
            matters and duplicates do not accumulate extra credit.
        expected_ids: Unordered set of relevant document IDs.
        k: Cutoff rank.

    Returns:
        Recall at k as a float in ``[0.0, 1.0]``.

    Raises:
        ValueError: If ``k <= 0`` or ``expected_ids`` is empty.

    Example:
        >>> recall_at_k(["a", "b", "c"], frozenset({"a", "c", "d"}), 3)
        0.6666666666666666
    """

    if k <= 0:
        raise ValueError("k must be greater than zero")
    if not expected_ids:
        raise ValueError("expected_ids must not be empty")
    if not retrieved_ids:
        return 0.0

    seen: set[str] = set()
    hit_count = 0
    for doc_id in retrieved_ids[:k]:
        if doc_id in seen:
            continue
        seen.add(doc_id)
        if doc_id in expected_ids:
            hit_count += 1

    return float(hit_count) / float(len(expected_ids))


def mean_recall_at_k(
    results: Sequence[tuple[Sequence[str], frozenset[str]]],
    k: int,
) -> float:
    """Return the macro-average of recall at k over retrieval results.

    Args:
        results: Sequence of ``(retrieved_ids, expected_ids)`` pairs.
        k: Cutoff rank forwarded to ``recall_at_k``.

    Returns:
        Arithmetic mean of per-query recall scores.

    Raises:
        ValueError: If ``results`` is empty, ``k <= 0``, or any
            ``expected_ids`` set is empty.

    Example:
        >>> mean_recall_at_k([(["a"], frozenset({"a"})), ([], frozenset({"b"}))], 1)
        0.5
    """

    if not results:
        raise ValueError("results must not be empty")

    total = 0.0
    for retrieved_ids, expected_ids in results:
        total += recall_at_k(retrieved_ids, expected_ids, k)

    return total / float(len(results))
