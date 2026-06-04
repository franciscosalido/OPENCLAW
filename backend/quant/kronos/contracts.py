"""Kronos adapter contracts without predictor implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.quant.kronos.frames import KronosKLineFrame


@dataclass(frozen=True, slots=True, kw_only=True)
class KronosPredictionParams:
    """Sampling and horizon parameters for a future Kronos adapter."""

    lookback: int
    pred_len: int
    sample_count: int
    T: float | None = None
    top_p: float | None = None

    def __post_init__(self) -> None:
        if self.lookback <= 0:
            raise ValueError("lookback must be > 0")
        if self.pred_len <= 0:
            raise ValueError("pred_len must be > 0")
        if self.sample_count < 1:
            raise ValueError("sample_count must be >= 1")
        if self.T is not None and self.T <= 0:
            raise ValueError("T must be > 0")
        if self.top_p is not None and not 0 < self.top_p <= 1:
            raise ValueError("top_p must satisfy 0 < top_p <= 1")


@dataclass(frozen=True, slots=True, kw_only=True)
class KronosForecastRequest:
    """Request envelope consumed by a future Kronos predictor adapter."""

    frame: KronosKLineFrame
    params: KronosPredictionParams


@dataclass(frozen=True, slots=True, kw_only=True)
class KronosForecastResult:
    """Result envelope returned by a future Kronos predictor adapter."""

    request: KronosForecastRequest
    predictions: Any
    metadata: dict[str, Any]
