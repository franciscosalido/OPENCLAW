"""Duck-typed Kronos K-line frame contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


REQUIRED_OHLC_COLUMNS: frozenset[str] = frozenset(("open", "high", "low", "close"))


@dataclass(frozen=True, slots=True, kw_only=True)
class KronosKLineFrame:
    """Input frame shape expected by a future Kronos adapter."""

    instrument: str
    timeframe: str
    x_df: Any
    x_timestamp: Any
    y_timestamp: Any
    source_manifest_id: UUID | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.instrument, "instrument")
        _require_non_empty(self.timeframe, "timeframe")
        _validate_dataframe_like(self.x_df)
        _validate_datetime_series_like(self.x_timestamp, "x_timestamp")
        _validate_datetime_series_like(self.y_timestamp, "y_timestamp")
        if len(self.x_df) != len(self.x_timestamp):
            raise ValueError("len(x_df) must equal len(x_timestamp)")
        if len(self.y_timestamp) < 1:
            raise ValueError("y_timestamp must contain at least one timestamp")
        if self.source_manifest_id is not None and not isinstance(
            self.source_manifest_id, UUID
        ):
            raise TypeError("source_manifest_id must be a UUID")


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


def _validate_dataframe_like(value: Any) -> None:
    if not hasattr(value, "columns") or not hasattr(value, "__len__"):
        raise TypeError("x_df must look like a pandas DataFrame")
    columns = {str(column) for column in value.columns}
    missing = REQUIRED_OHLC_COLUMNS - columns
    if missing:
        raise ValueError(f"x_df is missing required OHLC columns: {sorted(missing)}")


def _validate_datetime_series_like(value: Any, field_name: str) -> None:
    if not hasattr(value, "__len__"):
        raise TypeError(f"{field_name} must look like a pandas Series")
    dtype = str(getattr(value, "dtype", "")).lower()
    if "datetime" not in dtype:
        raise ValueError(f"{field_name} must be datetime-like")
