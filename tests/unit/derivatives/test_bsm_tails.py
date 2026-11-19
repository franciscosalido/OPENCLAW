"""Adendo 2 DL-PR04: caudas BSM nao negativas e paridade sem relaxar tolerancias."""

from __future__ import annotations

import math

import pytest

from backend.derivatives.domain.models import OptionKind
from backend.derivatives.pricing.bsm import BsmInputs, BsmResult, price

SPOT = 100.0
SIGMAS = (0.02, 0.05, 0.1, 0.2, 0.4, 0.8, 2.0)
MONEYNESS = tuple(step / 10.0 for step in range(3, 31))
TIMES = (1.0 / 252.0, 10.0 / 252.0, 0.25, 0.5, 1.0, 2.0)
RATES = (0.0, 0.05, 0.10, 0.15)


def _result(kind: OptionKind, sigma: float, moneyness: float, t: float,
            r: float, q: float = 0.0) -> BsmResult:
    return price(BsmInputs(kind=kind, spot=SPOT, strike=SPOT * moneyness,
                           time_years=t, rate_cont=r, sigma=sigma, dividend_yield=q),
                 theta_basis=252)


@pytest.mark.parametrize("sigma", SIGMAS)
@pytest.mark.parametrize("moneyness", MONEYNESS)
@pytest.mark.parametrize("t", TIMES)
@pytest.mark.parametrize("r", RATES)
def test_tail_prices_are_nonnegative_and_obey_put_call_parity(
    sigma: float, moneyness: float, t: float, r: float,
) -> None:
    call = _result(OptionKind.CALL, sigma, moneyness, t, r)
    put = _result(OptionKind.PUT, sigma, moneyness, t, r)
    assert call.price >= 0.0
    assert put.price >= 0.0
    residual = call.price - put.price - (SPOT - SPOT * moneyness * math.exp(-r * t))
    assert abs(residual) <= 1e-12


def test_linux_aarch64_put_tail_remains_strictly_positive() -> None:
    put = _result(OptionKind.PUT, 0.05, 0.7, 2.0, 0.10)
    assert put.price > 0.0
    # As gregas tambem usam as caudas diretas, sem 1 - N(d) arredondado a zero.
    assert put.greeks.delta < 0.0
    assert put.greeks.rho_per_pct_point < 0.0


@pytest.mark.parametrize("kind", (OptionKind.CALL, OptionKind.PUT))
def test_zero_vol_atm_forward_keeps_half_delta_and_carry(kind: OptionKind) -> None:
    t, r, q = 2.0, 0.10, 0.10
    result = _result(kind, 0.0, 1.0, t, r, q)
    sign = 1.0 if kind is OptionKind.CALL else -1.0
    discount = math.exp(-r * t)
    assert result.regime == "zero_vol"
    assert result.price == 0.0
    assert result.d1 is None and result.d2 is None
    assert result.greeks.delta == sign * discount * 0.5
    assert result.greeks.gamma == 0.0
    assert result.greeks.vega_per_pct_point == 0.0
    assert result.greeks.theta_per_day == 0.0
    assert result.greeks.rho_per_pct_point == sign * SPOT * t * discount * 0.5 * 0.01
