"""Provas independentes do esquema de diferenças finitas."""
import math
from itertools import product
from random import Random
from typing import Any

import pytest

from backend.derivatives.domain.models import ExerciseStyle, OptionKind
from backend.derivatives.pricing import bsm
from backend.derivatives.pricing.binomial import crr_price
from backend.derivatives.pricing.fd_american import FdGrid, FdRefusal, FdRefusalCode, fd_price

R = math.log1p(.149)
CALL, PUT = OptionKind.CALL, OptionKind.PUT
AMERICAN, EUROPEAN = ExerciseStyle.AMERICAN, ExerciseStyle.EUROPEAN
Anchor = tuple[str, OptionKind, float, float, float, float, float, float, float, float, float]
GRID = FdGrid(400, 200, 6., 2)
ANCHORS: list[Anchor] = [
    ("A1", CALL, 100., 100., 1., R, 0., .25, 17.1763409420, 17.1763409420, 17.1763298697),
    ("A2", CALL, 110., 100., .5, R, 0., .30, 19.3912219359, 19.3912219359, 19.3912186245),
    ("A3", CALL, 95., 100., 21/252, R, 0., .35, 2.2781935933, 2.2781935933, 2.2781474390),
    ("B1", CALL, 100., 100., 1., R, .06, .25, 13.0277106261, 13.0276447430, 13.0276741026),
    ("B2", CALL, 110., 100., 1., .05, .10, .20, 11.7698519902, 10.1546263116, 11.7702532627),
    ("B3", CALL, 120., 100., .75, R, .08, .30, 25.6872917374, 25.6625238259, 25.6871730143),
    ("C1", PUT, 100., 100., 1., R, 0., .25, 5.6962274996, 4.2084278734, 5.6968511479),
    ("C2", PUT, 110., 100., .25, R, 0., .35, 2.5062680054, 2.3893161497, 2.5065055226),
    ("C3", PUT, 100., 100., 5/252, R, 0., .30, 1.5688683123, 1.5493677643, 1.5689431768),
]


@pytest.mark.parametrize(("case", "style"), [
    pytest.param(case, style, id=f"{case[0]}-{style.value}")
    for case, style in product(ANCHORS, (AMERICAN, EUROPEAN))
])
def test_t1_scheme_anchors(case: Anchor, style: ExerciseStyle) -> None:
    _, kind, spot, strike, years, rate, q, sigma, american, european, _ = case
    price = fd_price(kind=kind, style=style, spot=spot, strike=strike, time_years=years,
                     rate_cont=rate, dividend_yield=q, sigma=sigma, grid=FdGrid(400, 200, 6., 2))
    assert price == pytest.approx(american if style is AMERICAN else european, abs=1e-6, rel=0)


def _fd(case: Anchor, *, style: ExerciseStyle = AMERICAN, grid: FdGrid = GRID) -> float:
    _, kind, spot, strike, years, rate, q, sigma, *_ = case
    return fd_price(kind=kind, style=style, spot=spot, strike=strike, time_years=years,
                    rate_cont=rate, dividend_yield=q, sigma=sigma, grid=grid)


def _bsm(kind: OptionKind, spot: float, strike: float, years: float, rate: float,
         q: float, sigma: float) -> float:
    inputs = bsm.BsmInputs(kind, spot, strike, years, rate, sigma, q)
    return bsm.price(inputs, theta_basis=252).price


@pytest.mark.parametrize("case", [pytest.param(case, id=case[0]) for case in ANCHORS])
def test_t2_european_closed_form(case: Anchor) -> None:
    assert abs(_fd(case, style=EUROPEAN) - _bsm(*case[1:8])) <= 3e-4


@pytest.mark.parametrize("case", ANCHORS[:3], ids=["A1", "A2", "A3"])
def test_t3_no_early_exercise_without_yield(case: Anchor) -> None:
    assert abs(_fd(case) - _bsm(*case[1:8])) <= 2e-4


@pytest.mark.parametrize("case", [pytest.param(case, id=case[0]) for case in ANCHORS])
def test_t4_crr_pair_2000(case: Anchor) -> None:
    _, kind, spot, strike, years, rate, q, sigma, *_ = case
    pair = sum(crr_price(kind=kind, style=AMERICAN, spot=spot, strike=strike, time_years=years,
                         rate_cont=rate, dividend_yield=q, sigma=sigma, steps=steps)
               for steps in (2000, 2001)) / 2
    assert abs(_fd(case) - pair) <= 1.5e-3


@pytest.mark.parametrize("case", [pytest.param(case, id=case[0]) for case in ANCHORS])
def test_t5_convergence(case: Anchor) -> None:
    coarse, fine, finest = (_fd(case, grid=FdGrid(n, n // 2, 6., 2)) for n in (400, 800, 1600))
    assert abs(fine - finest) <= abs(coarse - fine) / 2.5


def test_t6_symmetry() -> None:
    rng = Random(27)
    for _ in range(20):
        spot = rng.uniform(94., 106.)
        years, sigma = rng.uniform(.3, 1.4), rng.uniform(.18, .35)
        r, q = rng.uniform(0., .09), rng.uniform(0., .09)
        call = fd_price(kind=CALL, style=AMERICAN, spot=spot, strike=100., time_years=years,
                        rate_cont=r, dividend_yield=q, sigma=sigma, grid=GRID)
        put = fd_price(kind=PUT, style=AMERICAN, spot=100., strike=spot, time_years=years,
                       rate_cont=q, dividend_yield=r, sigma=sigma, grid=GRID)
        assert abs(call - put) <= 1.5e-3


@pytest.mark.parametrize(("kind", "spot", "years", "rate", "q"), product(
    (CALL, PUT), (94., 97., 100., 103., 106.), (.25, .5, .75, 1., 1.25),
    (.01, .05), (0., .04, .08, .12, .16),
))
def test_t7_invariant_grid(
    kind: OptionKind, spot: float, years: float, rate: float, q: float,
) -> None:
    """Grade ampla, em 800×400 offline; a malha padrão tem suas âncoras próprias."""
    grid = FdGrid(800, 400, 6., 2)
    sign = 1 if kind is CALL else -1
    previous = max(0., sign * (spot - 100.))
    for sigma in (.18, .30):
        actual = fd_price(kind=kind, style=AMERICAN, spot=spot, strike=100., time_years=years,
                          rate_cont=rate, dividend_yield=q, sigma=sigma, grid=grid)
        assert actual >= max(0., sign * (spot - 100.))
        assert actual >= previous - 1e-9
        assert actual >= _bsm(kind, spot, 100., years, rate, q, sigma) - 3e-4
        previous = actual


DEFAULT: dict[str, Any] = dict(
    kind=CALL, style=AMERICAN, spot=100., strike=100., time_years=1.,
    rate_cont=R, dividend_yield=0., sigma=.25, grid=GRID,
)


def _price_with(**change: Any) -> float:
    values: dict[str, Any] = DEFAULT | change
    return fd_price(**values)


@pytest.mark.parametrize(("change", "code"), [
    ({"kind": "CALL"}, FdRefusalCode.INVALID_INPUT_TYPE),
    ({"style": False}, FdRefusalCode.INVALID_INPUT_TYPE),
    ({"grid": {}}, FdRefusalCode.INVALID_INPUT_TYPE),
    ({"spot": 100}, FdRefusalCode.INVALID_INPUT_TYPE),
    ({"spot": math.inf}, FdRefusalCode.NON_FINITE_INPUT),
    ({"sigma": math.nan}, FdRefusalCode.NON_FINITE_INPUT),
    ({"strike": 0.}, FdRefusalCode.INPUT_OUT_OF_DOMAIN),
    ({"time_years": -1.}, FdRefusalCode.INPUT_OUT_OF_DOMAIN),
    ({"dividend_yield": -.1}, FdRefusalCode.INPUT_OUT_OF_DOMAIN),
    ({"style": ExerciseStyle.UNKNOWN}, FdRefusalCode.INPUT_OUT_OF_DOMAIN),
    ({"sigma": 0.}, FdRefusalCode.ZERO_VOLATILITY),
    ({"grid": FdGrid(399, 200, 6., 2)}, FdRefusalCode.INVALID_GRID),
    ({"grid": FdGrid(400, "200", 6., 0)}, FdRefusalCode.INVALID_GRID),  # type: ignore[arg-type]
    ({"grid": FdGrid(400, 200, 6., 201)}, FdRefusalCode.INVALID_GRID),
    ({"grid": object.__new__(FdGrid)}, FdRefusalCode.INVALID_GRID),
    ({"sigma": .005}, FdRefusalCode.GRID_NOT_ADMISSIBLE),
    ({"sigma": 1e200}, FdRefusalCode.NOT_REPRESENTABLE),
    ({"time_years": 0., "sigma": 0.}, FdRefusalCode.ZERO_VOLATILITY),
])
def test_t8_refusals(change: dict[str, object], code: FdRefusalCode) -> None:
    with pytest.raises(FdRefusal) as caught:
        _price_with(**change)
    assert caught.value.code is code


def test_t9_admissible_positive_control() -> None:
    assert _price_with(sigma=.05) > 0.


@pytest.mark.parametrize(("kind", "spot", "expected"), [
    (CALL, 120., 20.), (CALL, 80., 0.), (PUT, 80., 20.), (PUT, 120., 0.),
])
def test_t10_expiry_is_exact_intrinsic(kind: OptionKind, spot: float, expected: float) -> None:
    assert _price_with(kind=kind, spot=spot, time_years=0.) == expected


def test_t11_european_ignores_american_obstacle() -> None:
    c1 = ANCHORS[6]
    assert _fd(c1, style=EUROPEAN) < _fd(c1)


def test_t12_rannacher_coarse_time_grid() -> None:
    a1 = ANCHORS[0]
    expected = _bsm(*a1[1:8])
    damped, plain = (abs(_fd(a1, grid=FdGrid(400, 20, 6., ran)) - expected) for ran in (2, 0))
    assert damped < plain / 5


def test_one_step_cn_uses_both_edge_times() -> None:
    """Uma equação interior com borda direita positiva no início e no fim."""
    spot, strike, years, rate, q, sigma = 100., 100., .25, .08, .02, .30
    drift = rate - q - sigma**2 / 2
    dx = 6 * sigma * math.sqrt(years) + abs(drift) * years
    s_right = spot * math.exp(dx)
    old_right = s_right - strike
    new_right = s_right * math.exp(-q * years) - strike * math.exp(-rate * years)
    old_center = (spot * math.expm1(dx / 2) - strike * dx / 2) / dx
    alpha, beta = sigma**2 / (2 * dx**2), drift / (2 * dx)
    diagonal, upper = -2 * alpha - rate, alpha + beta
    h = years / 2
    expected = ((1 + h * diagonal) * old_center + h * upper * (old_right + new_right)
                ) / (1 - h * diagonal)
    actual = fd_price(kind=CALL, style=EUROPEAN, spot=spot, strike=strike, time_years=years,
                      rate_cont=rate, dividend_yield=q, sigma=sigma, grid=FdGrid(2, 1, 6., 0))
    assert actual == pytest.approx(expected, abs=1e-12, rel=0.)
