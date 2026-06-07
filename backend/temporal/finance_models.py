"""Canonical dataclasses for Janus temporal finance memory."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID


QlibProjectionFormat = Literal["qlib_bin", "parquet", "csv", "pandas"]
VALID_QLIB_PROJECTION_FORMATS: frozenset[str] = frozenset(
    ("qlib_bin", "parquet", "csv", "pandas")
)


@dataclass(frozen=True, slots=True, kw_only=True)
class TemporalEnvelope:
    """Shared metadata envelope for canonical temporal records."""

    ingested_at: datetime
    schema_version: str
    source_id: str | None = None
    lineage_hash: str | None = None

    def __post_init__(self) -> None:
        _require_tzaware(self.ingested_at, "ingested_at")
        _require_non_empty(self.schema_version, "schema_version")
        if not self.schema_version.endswith("-v1"):
            raise ValueError("schema_version must end with '-v1' in PR-02")
        if self.source_id is not None:
            _require_non_empty(self.source_id, "source_id")
        if self.lineage_hash is not None:
            _require_non_empty(self.lineage_hash, "lineage_hash")


@dataclass(frozen=True, slots=True, kw_only=True)
class MarketInstrument:
    """Tradable or observable market instrument."""

    instrument_id: UUID
    symbol: str
    exchange: str
    asset_class: str
    created_at: datetime
    currency: str | None = None
    timezone: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_uuid(self.instrument_id, "instrument_id")
        _require_non_empty(self.symbol, "symbol")
        _require_non_empty(self.exchange, "exchange")
        _require_non_empty(self.asset_class, "asset_class")
        if self.currency is not None:
            _require_non_empty(self.currency, "currency")
        if self.timezone is not None:
            _require_non_empty(self.timezone, "timezone")
        _require_tzaware(self.created_at, "created_at")
        _freeze_mapping(self, "metadata", self.metadata)


@dataclass(frozen=True, slots=True, kw_only=True)
class MarketCalendar:
    """One exchange session calendar row."""

    calendar_id: UUID
    exchange: str
    session_date: date
    is_open: bool
    created_at: datetime
    open_at: datetime | None = None
    close_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_uuid(self.calendar_id, "calendar_id")
        _require_non_empty(self.exchange, "exchange")
        if not isinstance(self.session_date, date):
            raise TypeError("session_date must be a date")
        if not isinstance(self.is_open, bool):
            raise TypeError("is_open must be a bool")
        _require_tzaware(self.created_at, "created_at")
        if self.open_at is not None:
            _require_tzaware(self.open_at, "open_at")
        if self.close_at is not None:
            _require_tzaware(self.close_at, "close_at")
        if self.is_open:
            if self.open_at is None:
                raise ValueError("open_at is required for open sessions")
            if self.close_at is None:
                raise ValueError("close_at is required for open sessions")
            if self.close_at <= self.open_at:
                raise ValueError("close_at must be greater than open_at")
        _freeze_mapping(self, "metadata", self.metadata)


@dataclass(frozen=True, slots=True, kw_only=True)
class MarketBar:
    """Canonical OHLCVA bar stored in PostgreSQL/TimescaleDB."""

    ts: datetime
    instrument_id: UUID
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    source_id: str
    ingested_at: datetime
    schema_version: str
    volume: float | None = None
    amount: float | None = None
    factor: float | None = None
    quality_flags: Mapping[str, Any] = field(default_factory=dict)
    lineage_hash: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_tzaware(self.ts, "ts")
        _require_uuid(self.instrument_id, "instrument_id")
        _require_non_empty(self.timeframe, "timeframe")
        _validate_ohlc(self.open, self.high, self.low, self.close)
        if self.volume is not None:
            _require_non_negative(self.volume, "volume")
        if self.amount is not None:
            _require_non_negative(self.amount, "amount")
        if self.factor is not None:
            _require_positive(self.factor, "factor")
        _validate_envelope_fields(
            ingested_at=self.ingested_at,
            schema_version=self.schema_version,
            source_id=self.source_id,
            lineage_hash=self.lineage_hash,
        )
        _freeze_mapping(self, "quality_flags", self.quality_flags)
        _freeze_mapping(self, "metadata", self.metadata)


@dataclass(frozen=True, slots=True, kw_only=True)
class MarketFeature:
    """Typed feature derived from canonical market bars."""

    ts: datetime
    instrument_id: UUID
    timeframe: str
    feature_name: str
    feature_version: str
    ingested_at: datetime
    schema_version: str
    feature_value: float | None = None
    source_bar_version: str | None = None
    source_id: str | None = None
    lineage_hash: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_tzaware(self.ts, "ts")
        _require_uuid(self.instrument_id, "instrument_id")
        _require_non_empty(self.timeframe, "timeframe")
        _require_non_empty(self.feature_name, "feature_name")
        _require_non_empty(self.feature_version, "feature_version")
        if self.source_bar_version is not None:
            _require_non_empty(self.source_bar_version, "source_bar_version")
        _validate_envelope_fields(
            ingested_at=self.ingested_at,
            schema_version=self.schema_version,
            source_id=self.source_id,
            lineage_hash=self.lineage_hash,
        )
        _freeze_mapping(self, "metadata", self.metadata)


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelRun:
    """One model or adapter execution record."""

    run_id: UUID
    model_name: str
    model_version: str
    adapter_name: str
    adapter_version: str
    input_start_ts: datetime
    input_end_ts: datetime
    created_at: datetime
    ingested_at: datetime
    schema_version: str
    source_id: str | None = None
    lineage_hash: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    metrics: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_uuid(self.run_id, "run_id")
        _require_non_empty(self.model_name, "model_name")
        _require_non_empty(self.model_version, "model_version")
        _require_non_empty(self.adapter_name, "adapter_name")
        _require_non_empty(self.adapter_version, "adapter_version")
        _require_tzaware(self.input_start_ts, "input_start_ts")
        _require_tzaware(self.input_end_ts, "input_end_ts")
        if self.input_end_ts < self.input_start_ts:
            raise ValueError("input_end_ts must be >= input_start_ts")
        _require_tzaware(self.created_at, "created_at")
        _validate_envelope_fields(
            ingested_at=self.ingested_at,
            schema_version=self.schema_version,
            source_id=self.source_id,
            lineage_hash=self.lineage_hash,
        )
        _freeze_mapping(self, "params", self.params)
        _freeze_mapping(self, "metrics", self.metrics)
        _freeze_mapping(self, "metadata", self.metadata)


@dataclass(frozen=True, slots=True, kw_only=True)
class KronosForecast:
    """Persisted Kronos-compatible forecast row."""

    forecast_ts: datetime
    run_id: UUID
    instrument_id: UUID
    timeframe: str
    horizon_step: int
    ingested_at: datetime
    schema_version: str
    created_at: datetime
    open_pred: float | None = None
    high_pred: float | None = None
    low_pred: float | None = None
    close_pred: float | None = None
    volume_pred: float | None = None
    amount_pred: float | None = None
    quantiles: Mapping[str, Any] = field(default_factory=dict)
    sample_count: int | None = None
    source_id: str | None = None
    lineage_hash: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_tzaware(self.forecast_ts, "forecast_ts")
        _require_uuid(self.run_id, "run_id")
        _require_uuid(self.instrument_id, "instrument_id")
        _require_non_empty(self.timeframe, "timeframe")
        if self.horizon_step < 0:
            raise ValueError("horizon_step must be >= 0")
        if self.sample_count is not None and self.sample_count < 1:
            raise ValueError("sample_count must be >= 1")
        if (
            self.high_pred is not None
            and self.low_pred is not None
            and self.high_pred < self.low_pred
        ):
            raise ValueError("high_pred must be >= low_pred")
        _validate_envelope_fields(
            ingested_at=self.ingested_at,
            schema_version=self.schema_version,
            source_id=self.source_id,
            lineage_hash=self.lineage_hash,
        )
        _require_tzaware(self.created_at, "created_at")
        _freeze_mapping(self, "quantiles", self.quantiles)
        _freeze_mapping(self, "metadata", self.metadata)


@dataclass(frozen=True, slots=True, kw_only=True)
class QlibProjectionManifest:
    """Metadata for a disposable Qlib-compatible projection."""

    projection_id: UUID
    projection_name: str
    projection_version: str
    format: QlibProjectionFormat
    source_query_hash: str
    transform_hash: str
    ingested_at: datetime
    schema_version: str
    created_at: datetime
    storage_uri: str | None = None
    checksum: str | None = None
    row_count: int | None = None
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    expires_at: datetime | None = None
    source_id: str | None = None
    lineage_hash: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_uuid(self.projection_id, "projection_id")
        _require_non_empty(self.projection_name, "projection_name")
        _require_non_empty(self.projection_version, "projection_version")
        if self.format not in VALID_QLIB_PROJECTION_FORMATS:
            raise ValueError("format must be one of qlib_bin, parquet, csv, pandas")
        _require_non_empty(self.source_query_hash, "source_query_hash")
        _require_non_empty(self.transform_hash, "transform_hash")
        if self.storage_uri is not None:
            _require_non_empty(self.storage_uri, "storage_uri")
        if self.checksum is not None:
            _require_non_empty(self.checksum, "checksum")
        if self.row_count is not None and self.row_count < 0:
            raise ValueError("row_count must be >= 0")
        if self.start_ts is not None:
            _require_tzaware(self.start_ts, "start_ts")
        if self.end_ts is not None:
            _require_tzaware(self.end_ts, "end_ts")
        if (
            self.start_ts is not None
            and self.end_ts is not None
            and self.end_ts < self.start_ts
        ):
            raise ValueError("end_ts must be >= start_ts")
        if self.expires_at is not None:
            _require_tzaware(self.expires_at, "expires_at")
        _validate_envelope_fields(
            ingested_at=self.ingested_at,
            schema_version=self.schema_version,
            source_id=self.source_id,
            lineage_hash=self.lineage_hash,
        )
        _require_tzaware(self.created_at, "created_at")
        _freeze_mapping(self, "metadata", self.metadata)


def _validate_envelope_fields(
    *,
    ingested_at: datetime,
    schema_version: str,
    source_id: str | None,
    lineage_hash: str | None,
) -> None:
    TemporalEnvelope(
        ingested_at=ingested_at,
        schema_version=schema_version,
        source_id=source_id,
        lineage_hash=lineage_hash,
    )


def _require_uuid(value: UUID, field_name: str) -> None:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


def _require_tzaware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_non_negative(value: float, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")


def _require_positive(value: float, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")


def _require_mapping(value: Mapping[str, Any], field_name: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")


def _freeze_mapping(
    instance: object, field_name: str, value: Mapping[str, Any]
) -> None:
    _require_mapping(value, field_name)
    object.__setattr__(instance, field_name, dict(value))


def _validate_ohlc(open_: float, high: float, low: float, close: float) -> None:
    _require_non_negative(open_, "open")
    _require_non_negative(high, "high")
    _require_non_negative(low, "low")
    _require_non_negative(close, "close")
    if high < low:
        raise ValueError("high must be >= low")
    if high < open_:
        raise ValueError("high must be >= open")
    if high < close:
        raise ValueError("high must be >= close")
    if low > open_:
        raise ValueError("low must be <= open")
    if low > close:
        raise ValueError("low must be <= close")
