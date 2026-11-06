"""Convencoes temporais: fracao de ano, taxa continua e TimeToExpiry (DL-PR02)."""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.derivatives.pricing.calendar import (
    CalendarId,
    TradingCalendar,
    load_calendars,
)
from backend.derivatives.pricing.conventions import (
    continuous_rate,
    model_assumptions,
    time_to_expiry,
    year_fraction,
)
from config.derivatives_config_model import Conventions, load_derivatives_config


@pytest.fixture(scope="module")
def b3() -> TradingCalendar:
    calendars = load_calendars(Conventions(), root=Path("."))
    return calendars[CalendarId.B3_LISTED_TRADING]


def test_year_fraction_10_business_days_basis_252() -> None:
    assert year_fraction(10, basis=252) == pytest.approx(0.03968254)


def test_year_fraction_basis_365() -> None:
    assert year_fraction(10, basis=365) == pytest.approx(10 / 365)


def test_year_fraction_negative_rejected() -> None:
    with pytest.raises(ValueError, match="negativo"):
        year_fraction(-1, basis=252)


def test_year_fraction_zero_is_zero() -> None:
    assert year_fraction(0, basis=252) == 0.0


def test_continuous_rate_annual_exp_252() -> None:
    assert continuous_rate(
        Decimal("3.4"), compounding="annual_exp_252"
    ) == pytest.approx(math.log(1.034))


def test_continuous_rate_already_continuous() -> None:
    assert continuous_rate(
        Decimal("3.4"), compounding="continuous"
    ) == pytest.approx(0.034)


def test_continuous_rate_zero() -> None:
    assert continuous_rate(Decimal("0"), compounding="annual_exp_252") == 0.0
    assert continuous_rate(Decimal("0"), compounding="continuous") == 0.0


def test_continuous_rate_negative_rate() -> None:
    assert continuous_rate(
        Decimal("-0.5"), compounding="annual_exp_252"
    ) == pytest.approx(math.log(0.995))


def test_time_to_expiry_regular_window(b3: TradingCalendar) -> None:
    result = time_to_expiry(
        b3,
        valuation_date=date(2026, 11, 5),
        expiry=date(2026, 11, 19),
        cfg=Conventions(),
    )
    assert result.business_days == 10
    assert result.year_fraction == pytest.approx(10 / 252)
    assert result.convention == "(D0,Dv]"
    assert result.calendar_id == "B3_LISTED_TRADING"
    assert result.basis == 252
    assert result.is_expiry_day is False


def test_time_to_expiry_on_expiry_day(b3: TradingCalendar) -> None:
    result = time_to_expiry(
        b3,
        valuation_date=date(2026, 11, 19),
        expiry=date(2026, 11, 19),
        cfg=Conventions(),
    )
    assert result.business_days == 0
    assert result.year_fraction == 0.0
    assert result.is_expiry_day is True


def test_time_to_expiry_valuation_after_expiry_rejected(
    b3: TradingCalendar,
) -> None:
    with pytest.raises(ValueError, match="start"):
        time_to_expiry(
            b3,
            valuation_date=date(2026, 11, 20),
            expiry=date(2026, 11, 19),
            cfg=Conventions(),
        )


def test_time_to_expiry_respects_interval_convention(
    b3: TradingCalendar,
) -> None:
    cfg = Conventions(interval_convention="[D0,Dv)")
    result = time_to_expiry(
        b3,
        valuation_date=date(2026, 11, 5),
        expiry=date(2026, 11, 20),
        cfg=cfg,
    )
    assert result.business_days == 11
    assert result.convention == "[D0,Dv)"


def test_model_assumptions_key_set_is_exact(b3: TradingCalendar) -> None:
    assumptions = model_assumptions(Conventions(), b3)
    assert set(assumptions) == {
        "calendar_id",
        "calendar_versions",
        "day_count_calendar",
        "day_count_calendar_assumed",
        "interval_convention",
        "interval_convention_assumed",
        "year_basis",
        "rate_compounding",
        "rate_compounding_assumed",
        "dividend_yield",
        "strike_adjusted_by_exchange_assumed",
    }


def test_model_assumptions_carries_default_yaml_values(
    b3: TradingCalendar,
) -> None:
    cfg = load_derivatives_config().conventions
    assumptions = model_assumptions(cfg, b3)
    assert assumptions["calendar_id"] == "B3_LISTED_TRADING"
    assert "B3_LISTED_TRADING:2026" in str(assumptions["calendar_versions"])
    assert assumptions["day_count_calendar"] == "trading"
    assert assumptions["day_count_calendar_assumed"] is True
    assert assumptions["interval_convention"] == "(D0,Dv]"
    assert assumptions["interval_convention_assumed"] is True
    assert assumptions["year_basis"] == 252.0
    assert assumptions["rate_compounding"] == "annual_exp_252"
    assert assumptions["rate_compounding_assumed"] is True
    assert assumptions["dividend_yield"] == 0.0
    assert assumptions["strike_adjusted_by_exchange_assumed"] is True
