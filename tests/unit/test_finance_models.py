from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from backend.temporal.finance_models import (
    KronosForecast,
    MarketBar,
    MarketCalendar,
    MarketFeature,
    MarketInstrument,
    ModelRun,
    QlibProjectionManifest,
    TemporalEnvelope,
)


NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


def test_finance_dataclasses_are_frozen_and_slots() -> None:
    instrument = MarketInstrument(
        instrument_id=uuid4(),
        symbol="AAPL",
        exchange="NASDAQ",
        asset_class="equity",
        currency="USD",
        timezone="America/New_York",
        metadata={},
        created_at=NOW,
    )

    assert is_dataclass(instrument)
    assert hasattr(MarketInstrument, "__slots__")
    with pytest.raises(FrozenInstanceError):
        instrument.symbol = "MSFT"  # type: ignore[misc]


def test_temporal_envelope_requires_timezone_aware_datetime() -> None:
    with pytest.raises(ValueError, match="ingested_at"):
        TemporalEnvelope(ingested_at=datetime(2026, 6, 4), schema_version="x-v1")


def test_temporal_envelope_requires_v1_schema_version() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        TemporalEnvelope(ingested_at=NOW, schema_version="market-bar-v2")


def test_market_instrument_rejects_empty_identity_fields() -> None:
    with pytest.raises(ValueError, match="symbol"):
        MarketInstrument(
            instrument_id=uuid4(),
            symbol=" ",
            exchange="NASDAQ",
            asset_class="equity",
            created_at=NOW,
        )


def test_market_calendar_rejects_open_session_without_window() -> None:
    with pytest.raises(ValueError, match="open_at"):
        MarketCalendar(
            calendar_id=uuid4(),
            exchange="NASDAQ",
            session_date=date(2026, 6, 4),
            is_open=True,
            open_at=None,
            close_at=None,
            created_at=NOW,
        )


def _bar(**overrides: object) -> MarketBar:
    values: dict[str, object] = {
        "ts": NOW,
        "instrument_id": uuid4(),
        "timeframe": "1d",
        "open": 10.0,
        "high": 12.0,
        "low": 9.0,
        "close": 11.0,
        "volume": 100.0,
        "amount": 1000.0,
        "factor": 1.0,
        "source_id": "synthetic",
        "ingested_at": NOW,
        "schema_version": "market-bar-v1",
        "quality_flags": {},
        "metadata": {},
    }
    values.update(overrides)
    return MarketBar(**values)  # type: ignore[arg-type]


def test_market_bar_rejects_timestamp_naive() -> None:
    with pytest.raises(ValueError, match="ts"):
        _bar(ts=datetime(2026, 6, 4))


@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
def test_market_bar_rejects_negative_ohlc(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        _bar(**{field: -1.0})


def test_market_bar_rejects_invalid_ohlc_shape() -> None:
    with pytest.raises(ValueError, match="high"):
        _bar(high=8.0)
    with pytest.raises(ValueError, match="low"):
        _bar(low=12.0)


def test_market_bar_rejects_negative_volume_amount_and_factor() -> None:
    with pytest.raises(ValueError, match="volume"):
        _bar(volume=-1.0)
    with pytest.raises(ValueError, match="amount"):
        _bar(amount=-1.0)
    with pytest.raises(ValueError, match="factor"):
        _bar(factor=0.0)


def test_market_feature_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="feature_name"):
        MarketFeature(
            ts=NOW,
            instrument_id=uuid4(),
            timeframe="1d",
            feature_name=" ",
            feature_value=1.0,
            feature_version="feature-v1",
            ingested_at=NOW,
            schema_version="market-feature-v1",
            metadata={},
        )


def test_model_run_rejects_inverted_input_window() -> None:
    with pytest.raises(ValueError, match="input_end_ts"):
        ModelRun(
            run_id=uuid4(),
            model_name="kronos",
            model_version="contract-v1",
            adapter_name="quimera",
            adapter_version="adapter-v1",
            input_start_ts=NOW,
            input_end_ts=NOW - timedelta(days=1),
            created_at=NOW,
            ingested_at=NOW,
            schema_version="model-run-v1",
            params={},
            metrics={},
            metadata={},
        )


def test_kronos_forecast_validates_horizon_sample_and_prediction_shape() -> None:
    base = dict(
        forecast_ts=NOW,
        run_id=uuid4(),
        instrument_id=uuid4(),
        timeframe="1d",
        horizon_step=0,
        high_pred=12.0,
        low_pred=10.0,
        sample_count=1,
        quantiles={},
        ingested_at=NOW,
        schema_version="kronos-forecast-v1",
        metadata={},
        created_at=NOW,
    )
    with pytest.raises(ValueError, match="horizon_step"):
        KronosForecast(**{**base, "horizon_step": -1})
    with pytest.raises(ValueError, match="sample_count"):
        KronosForecast(**{**base, "sample_count": 0})
    with pytest.raises(ValueError, match="high_pred"):
        KronosForecast(**{**base, "high_pred": 9.0})


def test_qlib_projection_manifest_validation() -> None:
    base = dict(
        projection_id=uuid4(),
        projection_name="daily-bars",
        projection_version="projection-v1",
        format="qlib_bin",
        source_query_hash="query",
        transform_hash="transform",
        row_count=1,
        start_ts=NOW,
        end_ts=NOW + timedelta(days=1),
        ingested_at=NOW,
        schema_version="qlib-projection-manifest-v1",
        metadata={},
        created_at=NOW,
    )
    with pytest.raises(ValueError, match="format"):
        QlibProjectionManifest(**{**base, "format": "duckdb"})
    with pytest.raises(ValueError, match="row_count"):
        QlibProjectionManifest(**{**base, "row_count": -1})
    with pytest.raises(ValueError, match="end_ts"):
        QlibProjectionManifest(**{**base, "end_ts": NOW - timedelta(days=1)})
