from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.quant.kronos.contracts import KronosPredictionParams
from backend.quant.kronos.frames import KronosKLineFrame


NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


class FakeSeries:
    def __init__(self, values: list[datetime]) -> None:
        self._values = values
        self.dtype = "datetime64[ns, UTC]"

    def __len__(self) -> int:
        return len(self._values)


class FakeDataFrame:
    def __init__(self, columns: list[str], length: int) -> None:
        self.columns = columns
        self._length = length

    def __len__(self) -> int:
        return self._length


def _series(length: int) -> FakeSeries:
    return FakeSeries([NOW + timedelta(days=i) for i in range(length)])


def test_kronos_frame_accepts_ohlcva_dataframe_contract() -> None:
    frame = KronosKLineFrame(
        instrument="AAPL",
        timeframe="1d",
        x_df=FakeDataFrame(["open", "high", "low", "close", "volume", "amount"], 3),
        x_timestamp=_series(3),
        y_timestamp=_series(2),
        source_manifest_id=uuid4(),
    )

    assert frame.instrument == "AAPL"


def test_kronos_frame_allows_missing_volume_amount() -> None:
    frame = KronosKLineFrame(
        instrument="AAPL",
        timeframe="1d",
        x_df=FakeDataFrame(["open", "high", "low", "close"], 3),
        x_timestamp=_series(3),
        y_timestamp=_series(1),
    )

    assert frame.source_manifest_id is None


def test_kronos_frame_rejects_missing_required_ohlc_columns() -> None:
    with pytest.raises(ValueError, match="close"):
        KronosKLineFrame(
            instrument="AAPL",
            timeframe="1d",
            x_df=FakeDataFrame(["open", "high", "low"], 3),
            x_timestamp=_series(3),
            y_timestamp=_series(1),
        )


def test_kronos_frame_validates_lengths_and_datetime_like_series() -> None:
    with pytest.raises(ValueError, match="len"):
        KronosKLineFrame(
            instrument="AAPL",
            timeframe="1d",
            x_df=FakeDataFrame(["open", "high", "low", "close"], 3),
            x_timestamp=_series(2),
            y_timestamp=_series(1),
        )
    with pytest.raises(ValueError, match="y_timestamp"):
        KronosKLineFrame(
            instrument="AAPL",
            timeframe="1d",
            x_df=FakeDataFrame(["open", "high", "low", "close"], 3),
            x_timestamp=_series(3),
            y_timestamp=FakeSeries([]),
        )


def test_kronos_contracts_do_not_import_runtime_ml_packages() -> None:
    assert "torch" not in sys.modules
    assert "kronos" not in sys.modules


def test_kronos_prediction_params_validation() -> None:
    assert KronosPredictionParams(lookback=64, pred_len=16, sample_count=1).pred_len == 16
    with pytest.raises(ValueError, match="lookback"):
        KronosPredictionParams(lookback=0, pred_len=16, sample_count=1)
    with pytest.raises(ValueError, match="pred_len"):
        KronosPredictionParams(lookback=64, pred_len=0, sample_count=1)
    with pytest.raises(ValueError, match="sample_count"):
        KronosPredictionParams(lookback=64, pred_len=16, sample_count=0)
    with pytest.raises(ValueError, match="T"):
        KronosPredictionParams(lookback=64, pred_len=16, sample_count=1, T=0.0)
    with pytest.raises(ValueError, match="top_p"):
        KronosPredictionParams(lookback=64, pred_len=16, sample_count=1, top_p=1.5)
