"""Tabela de casos de qualidade com relogio injetado (DL-PR01)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from backend.derivatives.domain.models import (
    ExerciseStyle,
    OptionContract,
    OptionKind,
    Quote,
    SpotObservation,
    SpotSource,
)
from backend.derivatives.domain.quality import assess_quality
from config.derivatives_config_model import Quality

NOW = datetime(2021, 5, 10, 22, 0, tzinfo=UTC)
CFG = Quality()  # max_age_s=60, spot_sync_tolerance_s=60


def make_quote(**overrides: Any) -> Quote:
    base: dict[str, Any] = {
        "bid": Decimal("0.02"),
        "ask": Decimal("0.05"),
        "last": Decimal("0.03"),
        "bid_size": 10,
        "ask_size": 10,
        "volume": 5,
        "trades": 2,
        "last_trade_at": NOW,
        "source_time": NOW,
        "received_at": NOW,
    }
    base.update(overrides)
    return Quote(**base)


def make_contract(**overrides: Any) -> OptionContract:
    base: dict[str, Any] = {
        "symbol": "PETRE100",
        "underlying": "PETR3",
        "kind": OptionKind.CALL,
        "exercise_style": ExerciseStyle.AMERICAN,
        "strike": Decimal("9.21"),
        "expiry": date(2021, 5, 21),
        "contract_size": 100,
        "quotation_form": 100,
        "isin": None,
    }
    base.update(overrides)
    return OptionContract(**base)


def make_spot(**overrides: Any) -> SpotObservation:
    base: dict[str, Any] = {
        "price": Decimal("24.71"),
        "source": SpotSource.STOCK_ENDPOINT,
        "observed_at": NOW,
    }
    base.update(overrides)
    return SpotObservation(**base)


def test_stale_at_exact_threshold_is_false() -> None:
    quote = make_quote(source_time=NOW - timedelta(seconds=CFG.max_age_s))
    flags = assess_quality(quote=quote, contract=make_contract(), spot=make_spot(), now=NOW, cfg=CFG)
    assert flags.age_s == float(CFG.max_age_s)
    assert flags.stale is False


def test_stale_one_second_past_threshold() -> None:
    quote = make_quote(source_time=NOW - timedelta(seconds=CFG.max_age_s + 1))
    flags = assess_quality(quote=quote, contract=make_contract(), spot=make_spot(), now=NOW, cfg=CFG)
    assert flags.stale is True


def test_missing_source_time_is_stale_with_metadata() -> None:
    quote = make_quote(source_time=None)
    flags = assess_quality(quote=quote, contract=make_contract(), spot=make_spot(), now=NOW, cfg=CFG)
    assert flags.age_s is None
    assert flags.stale is True
    assert "source_time" in flags.missing_metadata


def test_missing_sides_flags() -> None:
    quote = make_quote(bid=None, ask=None, last=None)
    flags = assess_quality(quote=quote, contract=make_contract(), spot=make_spot(), now=NOW, cfg=CFG)
    assert flags.missing_bid is True
    assert flags.missing_ask is True
    assert flags.missing_last is True


def test_zero_volume_flag() -> None:
    zero = assess_quality(
        quote=make_quote(volume=0), contract=make_contract(), spot=make_spot(), now=NOW, cfg=CFG
    )
    live = assess_quality(
        quote=make_quote(volume=5), contract=make_contract(), spot=make_spot(), now=NOW, cfg=CFG
    )
    assert zero.zero_volume is True
    assert live.zero_volume is False


def test_crossed_market_flag() -> None:
    crossed = assess_quality(
        quote=make_quote(bid=Decimal("0.06"), ask=Decimal("0.05")),
        contract=make_contract(), spot=make_spot(), now=NOW, cfg=CFG,
    )
    normal = assess_quality(
        quote=make_quote(), contract=make_contract(), spot=make_spot(), now=NOW, cfg=CFG
    )
    one_sided = assess_quality(
        quote=make_quote(ask=None), contract=make_contract(), spot=make_spot(), now=NOW, cfg=CFG
    )
    assert crossed.crossed_market is True
    assert normal.crossed_market is False
    assert one_sided.crossed_market is False


def test_spot_none_not_synchronous_with_metadata() -> None:
    flags = assess_quality(quote=make_quote(), contract=make_contract(), spot=None, now=NOW, cfg=CFG)
    assert flags.spot_not_synchronous is True
    assert flags.spot_source is None
    assert "spot" in flags.missing_metadata


def test_spot_option_last_trade_always_not_synchronous() -> None:
    spot = make_spot(source=SpotSource.OPTION_LAST_TRADE)
    flags = assess_quality(quote=make_quote(), contract=make_contract(), spot=spot, now=NOW, cfg=CFG)
    assert flags.spot_not_synchronous is True
    assert flags.spot_source is SpotSource.OPTION_LAST_TRADE


def test_spot_within_tolerance_is_synchronous() -> None:
    spot = make_spot(observed_at=NOW - timedelta(seconds=CFG.spot_sync_tolerance_s))
    flags = assess_quality(quote=make_quote(), contract=make_contract(), spot=spot, now=NOW, cfg=CFG)
    assert flags.spot_not_synchronous is False


def test_spot_beyond_tolerance_not_synchronous() -> None:
    spot = make_spot(observed_at=NOW - timedelta(seconds=CFG.spot_sync_tolerance_s + 1))
    flags = assess_quality(quote=make_quote(), contract=make_contract(), spot=spot, now=NOW, cfg=CFG)
    assert flags.spot_not_synchronous is True


def test_spot_missing_time_not_synchronous() -> None:
    spot = make_spot(observed_at=None)
    flags = assess_quality(quote=make_quote(), contract=make_contract(), spot=spot, now=NOW, cfg=CFG)
    assert flags.spot_not_synchronous is True


def test_quote_missing_time_not_synchronous() -> None:
    quote = make_quote(source_time=None)
    flags = assess_quality(quote=quote, contract=make_contract(), spot=make_spot(), now=NOW, cfg=CFG)
    assert flags.spot_not_synchronous is True


def test_missing_metadata_fixed_order() -> None:
    contract = make_contract(
        exercise_style=ExerciseStyle.UNKNOWN, contract_size=None, quotation_form=None
    )
    flags = assess_quality(
        quote=make_quote(source_time=None), contract=contract, spot=None, now=NOW, cfg=CFG
    )
    assert flags.missing_metadata == (
        "exercise_style", "contract_size", "quotation_form", "source_time", "spot"
    )


def test_naive_now_raises() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        assess_quality(
            quote=make_quote(), contract=make_contract(), spot=make_spot(),
            now=datetime(2021, 5, 10, 22, 0), cfg=CFG,
        )
