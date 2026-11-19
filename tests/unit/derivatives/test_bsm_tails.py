"""Adendo 2 DL-PR04: caudas BSM nao negativas e paridade sem relaxar tolerancias."""

from __future__ import annotations

import math
from decimal import Decimal, localcontext

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


def _decimal_pi() -> Decimal:
    """Pi na precisao do contexto (receita da documentacao do modulo ``decimal``)."""
    lasts, term, total, n, na, d, da = Decimal(0), Decimal(3), Decimal(3), 1, 0, 0, 24
    while total != lasts:
        lasts = total
        n, na = n + na, na + 8
        d, da = d + da, da + 32
        term = (term * n) / d
        total += term
    return total


def _decimal_cdf(x: Decimal, pi: Decimal) -> Decimal:
    """N(x) pela serie de Maclaurin da integral normal, na precisao do contexto."""
    # Acima de |x| = 12 os termos da serie passam de 1e31 e comem a precisao de 100 digitos.
    assert abs(x) < 12
    term = total = x
    for k in range(1, 4000):
        term *= -x * x / (2 * k)
        increment = term / (2 * k + 1)
        total += increment
        if abs(increment) < Decimal("1e-90"):
            return Decimal("0.5") + total / (2 * pi).sqrt()
    raise ArithmeticError("serie da normal nao convergiu")


def _decimal_bsm(kind: OptionKind, strike: str, t: str, r: str, sigma: str) -> float:
    """Oraculo independente do codigo de producao: BSM em ``Decimal`` com 100 digitos."""
    with localcontext() as ctx:
        ctx.prec = 100
        pi = _decimal_pi()
        spot, k, years, rate, vol = (Decimal(v) for v in ("100", strike, t, r, sigma))
        root = vol * years.sqrt()
        d1 = ((spot / k).ln() + (rate + vol * vol / 2) * years) / root
        d2 = d1 - root
        discounted = k * (-rate * years).exp()
        if kind is OptionKind.CALL:
            return float(spot * _decimal_cdf(d1, pi) - discounted * _decimal_cdf(d2, pi))
        return float(discounted * _decimal_cdf(-d2, pi) - spot * _decimal_cdf(-d1, pi))


# Caudas onde ``1 - N(d)`` em ponto flutuante arredondaria a zero ou perderia os digitos.
DEEP_TAILS = (
    (OptionKind.PUT, "70", "2", "0.10", "0.05"),
    (OptionKind.PUT, "80", "0.5", "0.15", "0.04"),
    (OptionKind.CALL, "130", "0.25", "0", "0.05"),
    (OptionKind.CALL, "180", "1", "0.05", "0.05"),
)


@pytest.mark.parametrize(("kind", "strike", "t", "r", "sigma"), DEEP_TAILS)
def test_deep_tail_price_matches_the_decimal_oracle(
    kind: OptionKind, strike: str, t: str, r: str, sigma: str,
) -> None:
    # Positividade e paridade nao bastam: um mutante que trocou erfc por erf devolvia
    # 3.9e-16 no lugar de 1.145e-15 e passava em todo este arquivo (revisao de 19/11).
    # Tolerancia so relativa: o piso absoluto padrao do pytest (1e-12) aceitaria qualquer
    # coisa nesta ordem de grandeza.
    expected = _decimal_bsm(kind, strike, t, r, sigma)
    got = price(BsmInputs(kind=kind, spot=SPOT, strike=float(strike), time_years=float(t),
                          rate_cont=float(r), sigma=float(sigma)), theta_basis=252).price
    assert 0.0 < expected < 1e-12
    assert got == pytest.approx(expected, rel=1e-9, abs=0.0)


def test_decimal_oracle_reproduces_the_independent_review_reference() -> None:
    # Valor obtido pelo revisor independente com outra implementacao (Decimal, 80 digitos).
    oracle = _decimal_bsm(OptionKind.PUT, "70", "2", "0.10", "0.05")
    assert oracle == pytest.approx(1.145122080277693e-15, rel=1e-14, abs=0.0)


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
