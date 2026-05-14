"""Latency percentile metrics for pure in-memory retrieval evaluation."""

from __future__ import annotations

import math
from collections.abc import Sequence


def latency_percentiles(
    latencies_ms: Sequence[float],
    percentiles: Sequence[int] = (50, 95, 99),
) -> dict[int, float]:
    """Return latency percentiles with linear interpolation.

    Args:
        latencies_ms: Sequence of latency samples in milliseconds.
        percentiles: Percentile cutoffs in the inclusive range ``[0, 100]``.

    Returns:
        Mapping from each requested percentile to its interpolated latency.

    Raises:
        ValueError: If ``latencies_ms`` is empty, any latency is non-finite, or
            any percentile is outside ``[0, 100]``.

    Example:
        >>> latency_percentiles([10.0, 20.0, 30.0], (50,))
        {50: 20.0}
    """

    if not latencies_ms:
        raise ValueError("latencies_ms must not be empty")

    sorted_latencies = sorted(latencies_ms)
    for latency in sorted_latencies:
        if not math.isfinite(latency):
            raise ValueError("latencies_ms must contain only finite values")

    result: dict[int, float] = {}
    max_index = len(sorted_latencies) - 1
    for percentile in percentiles:
        if percentile < 0 or percentile > 100:
            raise ValueError("percentiles must be in [0, 100]")

        rank = (float(percentile) / 100.0) * float(max_index)
        lower_index = math.floor(rank)
        upper_index = math.ceil(rank)

        if lower_index == upper_index:
            result[percentile] = float(sorted_latencies[lower_index])
            continue

        lower_value = sorted_latencies[lower_index]
        upper_value = sorted_latencies[upper_index]
        weight = rank - float(lower_index)
        result[percentile] = lower_value + (upper_value - lower_value) * weight

    return result
