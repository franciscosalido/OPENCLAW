"""Testes do coprocessador BSM (DL-PR03): Hull, paridade, diferencas finitas centrais,
unidades declaradas, regimes-limite, dominio e oraculo mpmath do Codex."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Literal

import pytest

from backend.derivatives.domain.models import ExerciseStyle, OptionKind
from backend.derivatives.pricing.bsm import (
    BsmInputs,
    BsmResult,
    PricingDomainError,
    PricingModel,
    norm_cdf,
    norm_pdf,
    price,
    unsupported,
)

ORACLE_PATH = Path("tests/fixtures/derivatives/reference/bsm_reference_cases.json")
RATE = 0.10
H_REL = 1e-5

PARITY_GRID = [
    (s, k, sigma, t, q)
    for s in (80.0, 100.0, 120.0)
    for k in (90.0, 100.0, 110.0)
    for sigma in (0.05, 0.3, 1.0)
    for t in (1.0 / 252.0, 0.5, 2.0)
    for q in (0.0, 0.03)
]

REGULAR_POINTS = [
    (100.0, 100.0, 0.5, 0.10, 0.3, 0.0),
    (100.0, 90.0, 1.0, 0.05, 0.2, 0.03),
    (80.0, 110.0, 2.0, 0.10, 0.4, 0.02),
    (120.0, 100.0, 0.25, 0.12, 0.15, 0.0),
]

BOTH_KINDS = [OptionKind.CALL, OptionKind.PUT]


def _result(kind: OptionKind, s: float, k: float, t: float, r: float, sigma: float,
            q: float = 0.0, basis: Literal[252, 365] = 252) -> BsmResult:
    inputs = BsmInputs(kind=kind, spot=s, strike=k, time_years=t, rate_cont=r,
                       sigma=sigma, dividend_yield=q)
    return price(inputs, theta_basis=basis)


def _premium(kind: OptionKind, s: float, k: float, t: float, r: float, sigma: float,
             q: float) -> float:
    return _result(kind, s, k, t, r, sigma, q).price


def test_hull_reference_call() -> None:
    res = _result(OptionKind.CALL, 42.0, 40.0, 0.5, 0.10, 0.20)
    assert res.price == pytest.approx(4.76, abs=5e-3)
    assert res.d1 == pytest.approx(0.7693, abs=1e-3)
    assert res.d2 == pytest.approx(0.6278, abs=1e-3)
    assert res.regime == "regular"
    assert res.model is PricingModel.BSM_EUROPEAN
    assert res.notes == ()


def test_hull_reference_put() -> None:
    res = _result(OptionKind.PUT, 42.0, 40.0, 0.5, 0.10, 0.20)
    assert res.price == pytest.approx(0.81, abs=5e-3)
    assert res.regime == "regular"


@pytest.mark.parametrize(("s", "k", "sigma", "t", "q"), PARITY_GRID)
def test_put_call_parity(s: float, k: float, sigma: float, t: float, q: float) -> None:
    call = _premium(OptionKind.CALL, s, k, t, RATE, sigma, q)
    put = _premium(OptionKind.PUT, s, k, t, RATE, sigma, q)
    residual = call - put - (s * math.exp(-q * t) - k * math.exp(-RATE * t))
    assert abs(residual) <= 1e-9


@pytest.mark.parametrize("kind", BOTH_KINDS)
@pytest.mark.parametrize(("s", "k", "t", "r", "sigma", "q"), REGULAR_POINTS)
def test_delta_matches_central_difference(kind: OptionKind, s: float, k: float, t: float,
                                          r: float, sigma: float, q: float) -> None:
    h = s * H_REL
    fd = (_premium(kind, s + h, k, t, r, sigma, q)
          - _premium(kind, s - h, k, t, r, sigma, q)) / (2.0 * h)
    assert _result(kind, s, k, t, r, sigma, q).greeks.delta == pytest.approx(fd, rel=1e-5)


@pytest.mark.parametrize("kind", BOTH_KINDS)
@pytest.mark.parametrize(("s", "k", "t", "r", "sigma", "q"), REGULAR_POINTS)
def test_gamma_matches_second_difference(kind: OptionKind, s: float, k: float, t: float,
                                         r: float, sigma: float, q: float) -> None:
    h = s * H_REL
    fd = (_premium(kind, s + h, k, t, r, sigma, q) - 2.0 * _premium(kind, s, k, t, r, sigma, q)
          + _premium(kind, s - h, k, t, r, sigma, q)) / (h * h)
    assert _result(kind, s, k, t, r, sigma, q).greeks.gamma == pytest.approx(fd, rel=1e-5)


@pytest.mark.parametrize("kind", BOTH_KINDS)
@pytest.mark.parametrize(("s", "k", "t", "r", "sigma", "q"), REGULAR_POINTS)
def test_vega_matches_central_difference(kind: OptionKind, s: float, k: float, t: float,
                                         r: float, sigma: float, q: float) -> None:
    h = sigma * H_REL
    fd = (_premium(kind, s, k, t, r, sigma + h, q)
          - _premium(kind, s, k, t, r, sigma - h, q)) / (2.0 * h)
    greeks = _result(kind, s, k, t, r, sigma, q).greeks
    assert greeks.vega_per_pct_point == pytest.approx(fd * 0.01, rel=1e-5)


@pytest.mark.parametrize("kind", BOTH_KINDS)
@pytest.mark.parametrize(("s", "k", "t", "r", "sigma", "q"), REGULAR_POINTS)
def test_rho_matches_central_difference(kind: OptionKind, s: float, k: float, t: float,
                                        r: float, sigma: float, q: float) -> None:
    h = r * H_REL
    fd = (_premium(kind, s, k, t, r + h, sigma, q)
          - _premium(kind, s, k, t, r - h, sigma, q)) / (2.0 * h)
    greeks = _result(kind, s, k, t, r, sigma, q).greeks
    assert greeks.rho_per_pct_point == pytest.approx(fd * 0.01, rel=1e-5)


@pytest.mark.parametrize("kind", BOTH_KINDS)
@pytest.mark.parametrize(("s", "k", "t", "r", "sigma", "q"), REGULAR_POINTS)
def test_theta_matches_central_difference_in_t(kind: OptionKind, s: float, k: float,
                                               t: float, r: float, sigma: float,
                                               q: float) -> None:
    h = t * H_REL
    fd_dp_dt_years = (_premium(kind, s, k, t + h, r, sigma, q)
                      - _premium(kind, s, k, t - h, r, sigma, q)) / (2.0 * h)
    annual = _result(kind, s, k, t, r, sigma, q).greeks.theta_per_day * 252.0
    assert annual == pytest.approx(-fd_dp_dt_years, rel=1e-5)


@pytest.mark.parametrize(("s", "k", "t", "r", "sigma", "q"), REGULAR_POINTS)
def test_greek_identities_and_bounds(s: float, k: float, t: float, r: float, sigma: float,
                                     q: float) -> None:
    call = _result(OptionKind.CALL, s, k, t, r, sigma, q).greeks
    put = _result(OptionKind.PUT, s, k, t, r, sigma, q).greeks
    assert call.delta - put.delta == pytest.approx(math.exp(-q * t), abs=1e-12)
    assert call.gamma == put.gamma
    assert call.vega_per_pct_point == put.vega_per_pct_point
    assert 0.0 < call.delta < 1.0
    assert -1.0 < put.delta < 0.0
    assert call.gamma > 0.0
    assert call.vega_per_pct_point > 0.0


@pytest.mark.parametrize(("s", "k", "t", "r", "sigma", "q"), REGULAR_POINTS)
def test_vega_and_rho_units_are_per_pct_point(s: float, k: float, t: float, r: float,
                                              sigma: float, q: float) -> None:
    call = _result(OptionKind.CALL, s, k, t, r, sigma, q)
    put = _result(OptionKind.PUT, s, k, t, r, sigma, q)
    assert call.d1 is not None and call.d2 is not None
    vega_raw = s * math.exp(-q * t) * norm_pdf(call.d1) * math.sqrt(t)
    assert call.greeks.vega_per_pct_point == pytest.approx(vega_raw * 0.01, rel=1e-12)
    rho_call_raw = k * t * math.exp(-r * t) * norm_cdf(call.d2)
    rho_put_raw = -k * t * math.exp(-r * t) * norm_cdf(-call.d2)
    assert call.greeks.rho_per_pct_point == pytest.approx(rho_call_raw * 0.01, rel=1e-12)
    assert put.greeks.rho_per_pct_point == pytest.approx(rho_put_raw * 0.01, rel=1e-12)


@pytest.mark.parametrize("kind", BOTH_KINDS)
def test_theta_per_day_times_basis_is_annual_theta(kind: OptionKind) -> None:
    s, k, t, r, sigma, q = 100.0, 100.0, 0.5, 0.10, 0.3, 0.0
    res_252 = _result(kind, s, k, t, r, sigma, q, basis=252)
    res_365 = _result(kind, s, k, t, r, sigma, q, basis=365)
    assert res_252.greeks.theta_basis == 252
    assert res_365.greeks.theta_basis == 365
    annual_252 = res_252.greeks.theta_per_day * 252.0
    annual_365 = res_365.greeks.theta_per_day * 365.0
    assert annual_252 == pytest.approx(annual_365, rel=1e-12)
    assert res_252.d1 is not None and res_252.d2 is not None
    df_q, df_r = math.exp(-q * t), math.exp(-r * t)
    diffusion_term = s * df_q * norm_pdf(res_252.d1) * sigma / (2.0 * math.sqrt(t))
    if kind is OptionKind.CALL:
        expected = (-diffusion_term + q * s * df_q * norm_cdf(res_252.d1)
                    - r * k * df_r * norm_cdf(res_252.d2))
    else:
        expected = (-diffusion_term - q * s * df_q * norm_cdf(-res_252.d1)
                    + r * k * df_r * norm_cdf(-res_252.d2))
    assert annual_252 == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize(("kind", "spot", "expected_price", "expected_delta"), [
    (OptionKind.CALL, 105.0, 5.0, 1.0),
    (OptionKind.CALL, 95.0, 0.0, 0.0),
    (OptionKind.CALL, 100.0, 0.0, 0.5),
    (OptionKind.PUT, 95.0, 5.0, -1.0),
    (OptionKind.PUT, 105.0, 0.0, 0.0),
    (OptionKind.PUT, 100.0, 0.0, -0.5),
])
def test_expiry_regime_prices_intrinsic_without_exception(
    kind: OptionKind, spot: float, expected_price: float, expected_delta: float,
) -> None:
    res = _result(kind, spot, 100.0, 0.0, 0.10, 0.25)
    assert res.regime == "expiry"
    assert res.price == expected_price
    assert res.greeks.delta == expected_delta
    assert (res.greeks.gamma, res.greeks.vega_per_pct_point, res.greeks.theta_per_day,
            res.greeks.rho_per_pct_point) == (0.0, 0.0, 0.0, 0.0)
    assert res.d1 is None and res.d2 is None
    assert "expiry_day_intrinsic" in res.notes


@pytest.mark.parametrize(("kind", "s", "k"), [
    (OptionKind.CALL, 100.0, 90.0),
    (OptionKind.CALL, 80.0, 100.0),
    (OptionKind.PUT, 80.0, 100.0),
    (OptionKind.PUT, 100.0, 90.0),
])
def test_zero_vol_regime_prices_discounted_intrinsic(kind: OptionKind, s: float,
                                                     k: float) -> None:
    t, r, q = 0.5, 0.10, 0.02
    res = _result(kind, s, k, t, r, 0.0, q)
    forward_gap = s * math.exp(-q * t) - k * math.exp(-r * t)
    expected = max(forward_gap, 0.0) if kind is OptionKind.CALL else max(-forward_gap, 0.0)
    assert res.regime == "zero_vol"
    assert res.price == pytest.approx(expected, abs=1e-15)
    assert res.greeks.vega_per_pct_point == 0.0
    assert res.d1 is None and res.d2 is None
    assert "zero_volatility_limit" in res.notes


def test_zero_vol_greeks_follow_discounted_intrinsic_derivative() -> None:
    t, r, q = 0.5, 0.10, 0.02
    itm = _result(OptionKind.CALL, 100.0, 90.0, t, r, 0.0, q)
    assert itm.greeks.delta == pytest.approx(math.exp(-q * t), rel=1e-12)
    assert itm.greeks.gamma == 0.0
    assert itm.greeks.rho_per_pct_point == pytest.approx(
        90.0 * t * math.exp(-r * t) * 0.01, rel=1e-12)
    assert itm.greeks.theta_per_day * 252.0 == pytest.approx(
        q * 100.0 * math.exp(-q * t) - r * 90.0 * math.exp(-r * t), rel=1e-12)
    otm = _result(OptionKind.CALL, 80.0, 100.0, t, r, 0.0, q)
    assert (otm.greeks.delta, otm.greeks.gamma, otm.greeks.rho_per_pct_point,
            otm.greeks.theta_per_day) == (0.0, 0.0, 0.0, 0.0)
    itm_put = _result(OptionKind.PUT, 80.0, 100.0, t, r, 0.0, q)
    assert itm_put.greeks.delta == pytest.approx(-math.exp(-q * t), rel=1e-12)


@pytest.mark.parametrize(("kind", "s", "k"), [
    (OptionKind.CALL, 100.0, 90.0),
    (OptionKind.CALL, 80.0, 100.0),
    (OptionKind.PUT, 100.0, 110.0),
])
def test_tiny_sigma_converges_to_zero_vol_limit(kind: OptionKind, s: float,
                                                k: float) -> None:
    t, r, q = 0.5, 0.10, 0.0
    tiny = _result(kind, s, k, t, r, 1e-6, q)
    limit = _result(kind, s, k, t, r, 0.0, q)
    assert tiny.regime == "regular"
    assert limit.regime == "zero_vol"
    assert tiny.price == pytest.approx(limit.price, abs=1e-6)


@pytest.mark.parametrize(("field", "value"), [
    ("spot", 0.0),
    ("spot", -1.0),
    ("strike", 0.0),
    ("strike", -2.0),
    ("time_years", -0.1),
    ("sigma", -0.01),
    ("dividend_yield", -0.001),
    ("spot", math.nan),
    ("strike", math.inf),
    ("time_years", math.nan),
    ("time_years", math.inf),
    ("rate_cont", math.nan),
    ("rate_cont", math.inf),
    ("sigma", math.inf),
])
def test_domain_violations_raise_pricing_domain_error(field: str, value: float) -> None:
    kwargs: dict[str, float] = {"spot": 100.0, "strike": 100.0, "time_years": 0.5,
                                "rate_cont": 0.1, "sigma": 0.2, "dividend_yield": 0.0}
    kwargs[field] = value
    with pytest.raises(PricingDomainError):
        BsmInputs(kind=OptionKind.CALL, **kwargs)


def test_pricing_domain_error_is_value_error() -> None:
    assert issubclass(PricingDomainError, ValueError)


def test_norm_helpers_sanity() -> None:
    assert norm_cdf(0.0) == 0.5
    assert norm_cdf(1e9) == 1.0
    assert norm_cdf(-1e9) == 0.0
    assert norm_cdf(1.0) + norm_cdf(-1.0) == 1.0
    assert norm_pdf(0.0) == pytest.approx(1.0 / math.sqrt(2.0 * math.pi), rel=1e-15)


def test_unsupported_reasons() -> None:
    assert unsupported(ExerciseStyle.AMERICAN) == "american_not_supported_phase1"
    assert unsupported(ExerciseStyle.UNKNOWN) == "unknown_exercise_style"


def test_pricing_model_identity() -> None:
    assert PricingModel.BSM_EUROPEAN.value == "bsm_european_v1"
    res = _result(OptionKind.CALL, 100.0, 100.0, 0.5, 0.1, 0.2)
    assert res.model is PricingModel.BSM_EUROPEAN


def _oracle_cases() -> list[dict[str, str]]:
    if not ORACLE_PATH.exists():
        return []
    payload = json.loads(ORACLE_PATH.read_text(encoding="utf-8"))
    return list(payload["cases"])


_ORACLE_CASES = _oracle_cases()


@pytest.mark.parametrize(
    "case",
    _ORACLE_CASES or [None],
    ids=[str(case["case_id"]) for case in _ORACLE_CASES] or ["oraculo-ausente"],
)
def test_bsm_against_mpmath_oracle(case: dict[str, str] | None) -> None:
    if case is None:
        pytest.skip("oráculo mpmath ainda não entregue — entra no PR04")
    s, k = float(case["S"]), float(case["K"])
    r, q = float(case["r_cont"]), float(case["q"])
    sigma, t = float(case["sigma"]), float(case["T_years"])
    assert abs(float(case["parity_residual"])) < 1e-20
    call = _result(OptionKind.CALL, s, k, t, r, sigma, q)
    put = _result(OptionKind.PUT, s, k, t, r, sigma, q)
    if case["case_type"] == "limit":
        assert call.regime == "regular"
        assert put.regime == "regular"
        return
    assert call.price == pytest.approx(float(case["call_price"]), abs=1e-9)
    assert put.price == pytest.approx(float(case["put_price"]), abs=1e-9)
    assert call.greeks.delta == pytest.approx(float(case["delta_call"]), abs=1e-9)
    assert put.greeks.delta == pytest.approx(float(case["delta_put"]), abs=1e-9)
    assert call.greeks.gamma == pytest.approx(float(case["gamma"]), abs=1e-9)
    assert call.d1 == pytest.approx(float(case["d1"]), abs=1e-9)
    assert call.d2 == pytest.approx(float(case["d2"]), abs=1e-9)
    assert call.greeks.vega_per_pct_point == pytest.approx(
        float(case["vega_per_pct_point"]), abs=1e-8)
    assert call.greeks.rho_per_pct_point == pytest.approx(
        float(case["rho_per_pct_point_call"]), abs=1e-8)
    assert put.greeks.rho_per_pct_point == pytest.approx(
        float(case["rho_per_pct_point_put"]), abs=1e-8)
    assert call.greeks.theta_per_day == pytest.approx(
        float(case["theta_per_day_252"]), abs=1e-8)
    call_365 = _result(OptionKind.CALL, s, k, t, r, sigma, q, basis=365)
    assert call_365.greeks.theta_per_day == pytest.approx(
        float(case["theta_per_day_365"]), abs=1e-8)
