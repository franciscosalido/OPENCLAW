"""Testes da IV por bissecao protegida (DL-PR04): round-trip, oraculo mpmath, limites
de nao-arbitragem, expansao de bracket, maximo de iteracoes, determinismo e dominio."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from backend.derivatives.domain.models import OptionKind
from backend.derivatives.pricing.bsm import BsmInputs, BsmResult, price
from backend.derivatives.pricing.implied_vol import (
    STATUSES_WITH_SIGMA,
    IvDiagnostic,
    IvResult,
    IvStatus,
    implied_vol,
    price_bounds,
)
from config.derivatives_config_model import Iv

ORACLE_PATH = Path("tests/fixtures/derivatives/reference/bsm_reference_cases.json")
CFG = Iv()
RATE = 0.10
T10 = 10.0 / 252.0
DEGENERATE = frozenset({IvStatus.LOW_VEGA, IvStatus.NO_CONVERGENCE})
BOTH_KINDS = (OptionKind.CALL, OptionKind.PUT)

RT_SIGMAS = (0.05, 0.2, 0.6, 1.2, 2.0)
RT_MONEYNESS = (0.7, 0.85, 1.0, 1.15, 1.3)
RT_TIMES = (T10, 0.5, 2.0)
RT_GRID = [(sig, m, t) for sig in RT_SIGMAS for m in RT_MONEYNESS for t in RT_TIMES]

# Pontos (sigma, K/S, T) do round-trip cuja vega bruta no sigma verdadeiro fica
# abaixo de low_vega_threshold: deep ITM/OTM com vol baixa e/ou prazo curto, onde o
# preco float e plano em sigma e a inversao e mal condicionada por construcao. O
# contrato nesses pontos e LOW_VEGA (sigma preenchido, mal condicionado) ou
# NO_CONVERGENCE (sem mudanca de sinal) — nunca excecao, nunca sigma == 0.0.
EXPECTED_LOW_VEGA_RT = frozenset({
    (0.05, 0.7, T10), (0.05, 0.7, 0.5), (0.05, 0.7, 2.0),
    (0.05, 0.85, T10), (0.05, 0.85, 0.5), (0.05, 0.85, 2.0),
    (0.05, 1.15, T10),
    (0.05, 1.3, T10), (0.05, 1.3, 0.5),
    (0.2, 0.7, T10), (0.2, 1.3, T10),
})

# Desfechos pinados dos seis casos `limit` do oraculo (call, put). O caso ATM de
# limite de tempo (T=1e-9, K=100) e bem condicionado (vega ~1.3e-3) e recupera
# sigma=0.20: errata registrada no SDD ao enunciado do card, que previa apenas
# LOW_VEGA/NO_CONVERGENCE para os `limit`.
EXPECTED_LIMIT_OUTCOMES = {
    "limit_sigma_1e-6_K90": (IvStatus.LOW_VEGA, IvStatus.LOW_VEGA),
    "limit_sigma_1e-6_K100": (IvStatus.NO_CONVERGENCE, IvStatus.NO_CONVERGENCE),
    "limit_sigma_1e-6_K110": (IvStatus.LOW_VEGA, IvStatus.LOW_VEGA),
    "limit_T_1e-9_K90": (IvStatus.NO_CONVERGENCE, IvStatus.LOW_VEGA),
    "limit_T_1e-9_K100": (IvStatus.OK, IvStatus.OK),
    "limit_T_1e-9_K110": (IvStatus.LOW_VEGA, IvStatus.NO_CONVERGENCE),
}


def _forward(kind: OptionKind, s: float, k: float, t: float, sigma: float,
             r: float = RATE, q: float = 0.0) -> BsmResult:
    inputs = BsmInputs(kind=kind, spot=s, strike=k, time_years=t, rate_cont=r,
                       sigma=sigma, dividend_yield=q)
    return price(inputs, theta_basis=252)


def _invert(target: float, kind: OptionKind, s: float, k: float, t: float,
            r: float = RATE, q: float = 0.0, cfg: Iv = CFG) -> IvResult:
    return implied_vol(target, kind=kind, spot=s, strike=k, time_years=t, rate_cont=r,
                       dividend_yield=q, cfg=cfg)


def _assert_sigma_status_invariant(result: IvResult) -> None:
    has_sigma = result.sigma is not None
    assert has_sigma == (result.diagnostic.status in STATUSES_WITH_SIGMA)
    if result.sigma is not None:
        assert result.sigma > 0.0


@pytest.mark.parametrize("kind", BOTH_KINDS)
@pytest.mark.parametrize(("sigma", "moneyness", "t"), RT_GRID)
def test_round_trip_recovers_sigma_or_flags_ill_conditioning(
    kind: OptionKind, sigma: float, moneyness: float, t: float,
) -> None:
    s, k = 100.0, 100.0 * moneyness
    forward = _forward(kind, s, k, t, sigma)
    vega_raw = forward.greeks.vega_per_pct_point * 100.0
    result = _invert(forward.price, kind, s, k, t)
    _assert_sigma_status_invariant(result)
    if (sigma, moneyness, t) in EXPECTED_LOW_VEGA_RT:
        assert vega_raw < CFG.low_vega_threshold
        assert result.diagnostic.status in DEGENERATE
    else:
        assert vega_raw >= CFG.low_vega_threshold
        assert result.diagnostic.status is IvStatus.OK
        assert result.sigma == pytest.approx(sigma, abs=1e-6)
        assert result.diagnostic.residual_vol is not None
        assert result.diagnostic.residual_vol <= CFG.tol_vol


def test_round_trip_low_vega_points_are_exactly_the_documented_ones() -> None:
    observed = {
        (sigma, m, t)
        for sigma, m, t in RT_GRID
        if _forward(OptionKind.CALL, 100.0, 100.0 * m, t, sigma)
        .greeks.vega_per_pct_point * 100.0 < CFG.low_vega_threshold
    }
    assert observed == EXPECTED_LOW_VEGA_RT


def _oracle_cases() -> list[dict[str, str]]:
    if not ORACLE_PATH.exists():
        return []
    payload = json.loads(ORACLE_PATH.read_text(encoding="utf-8"))
    return list(payload["cases"])


_ORACLE_CASES = _oracle_cases()
_ORACLE_IDS = [str(case["case_id"]) for case in _ORACLE_CASES] or ["oraculo-ausente"]


@pytest.mark.parametrize("kind", BOTH_KINDS)
@pytest.mark.parametrize("case", _ORACLE_CASES or [None], ids=_ORACLE_IDS)
def test_oracle_price_inversion(case: dict[str, str] | None, kind: OptionKind) -> None:
    if case is None:
        pytest.skip("oráculo mpmath ausente nesta árvore")
    s, k = float(case["S"]), float(case["K"])
    r, q = float(case["r_cont"]), float(case["q"])
    sigma_true, t = float(case["sigma"]), float(case["T_years"])
    field = "call_price" if kind is OptionKind.CALL else "put_price"
    result = _invert(float(case[field]), kind, s, k, t, r, q)
    _assert_sigma_status_invariant(result)
    vega_raw = float(case["vega_per_pct_point"]) * 100.0
    recoverable = vega_raw >= CFG.low_vega_threshold and sigma_true >= CFG.bracket_lo
    if recoverable:
        assert result.diagnostic.status is IvStatus.OK
        assert result.sigma == pytest.approx(sigma_true, abs=1e-7)
    else:
        assert result.diagnostic.status in DEGENERATE


@pytest.mark.parametrize(("case_id", "expected"), sorted(EXPECTED_LIMIT_OUTCOMES.items()))
def test_oracle_limit_cases_have_pinned_outcomes(
    case_id: str, expected: tuple[IvStatus, IvStatus],
) -> None:
    cases = {case["case_id"]: case for case in _ORACLE_CASES}
    if not cases:
        pytest.skip("oráculo mpmath ausente nesta árvore")
    case = cases[case_id]
    s, k = float(case["S"]), float(case["K"])
    r, q = float(case["r_cont"]), float(case["q"])
    t = float(case["T_years"])
    call = _invert(float(case["call_price"]), OptionKind.CALL, s, k, t, r, q)
    put = _invert(float(case["put_price"]), OptionKind.PUT, s, k, t, r, q)
    assert (call.diagnostic.status, put.diagnostic.status) == expected
    _assert_sigma_status_invariant(call)
    _assert_sigma_status_invariant(put)


def test_price_bounds_call_and_put() -> None:
    t, r, q = 0.5, 0.10, 0.02
    forward_leg = 100.0 * math.exp(-q * t)
    strike_leg = 90.0 * math.exp(-r * t)
    lower_c, upper_c = price_bounds(OptionKind.CALL, 100.0, 90.0, t, r, q)
    assert lower_c == pytest.approx(forward_leg - strike_leg, rel=1e-15)
    assert upper_c == pytest.approx(forward_leg, rel=1e-15)
    lower_p, upper_p = price_bounds(OptionKind.PUT, 100.0, 90.0, t, r, q)
    assert lower_p == 0.0
    assert upper_p == pytest.approx(strike_leg, rel=1e-15)
    lower_p_itm, _ = price_bounds(OptionKind.PUT, 80.0, 100.0, t, r, q)
    assert lower_p_itm == pytest.approx(
        100.0 * math.exp(-r * t) - 80.0 * math.exp(-q * t), rel=1e-15)


def test_below_intrinsic_returns_none_sigma() -> None:
    lower, _ = price_bounds(OptionKind.CALL, 100.0, 90.0, 0.5, RATE, 0.0)
    result = _invert(lower - 1.0, OptionKind.CALL, 100.0, 90.0, 0.5)
    assert result.diagnostic.status is IvStatus.BELOW_INTRINSIC
    assert result.sigma is None
    assert result.diagnostic.iterations == 0


def test_above_upper_bound_returns_none_sigma() -> None:
    result = _invert(100.5, OptionKind.CALL, 100.0, 90.0, 0.5)
    assert result.diagnostic.status is IvStatus.ABOVE_UPPER_BOUND
    assert result.sigma is None
    put = _invert(90.0 * math.exp(-RATE * 0.5) + 1.0, OptionKind.PUT, 100.0, 90.0, 0.5)
    assert put.diagnostic.status is IvStatus.ABOVE_UPPER_BOUND


def test_target_exactly_at_intrinsic_never_yields_sigma_zero() -> None:
    # ITM com r=q=0: o intrinseco 10.0 e plano em sigma no float ate ~0.02;
    # comportamento definido: converge no topo do plato e sinaliza LOW_VEGA.
    result = _invert(10.0, OptionKind.CALL, 100.0, 90.0, 0.5, r=0.0, q=0.0)
    assert result.diagnostic.status is IvStatus.LOW_VEGA
    assert result.sigma is not None
    assert result.sigma > 0.0
    assert result.diagnostic.vega_at_solution is not None
    assert result.diagnostic.vega_at_solution < CFG.low_vega_threshold


def test_otm_target_zero_never_yields_sigma_zero() -> None:
    result = _invert(0.0, OptionKind.CALL, 100.0, 130.0, T10)
    assert result.diagnostic.status in DEGENERATE
    _assert_sigma_status_invariant(result)


def test_low_vega_keeps_sigma_filled() -> None:
    # Plato logo acima do intrinseco: a solucao existe, mas e mal condicionada.
    result = _invert(10.0 + 1e-12, OptionKind.CALL, 100.0, 90.0, 0.5, r=0.0, q=0.0)
    assert result.diagnostic.status is IvStatus.LOW_VEGA
    assert result.sigma is not None
    assert result.sigma > 0.0


def test_root_below_bracket_lo_is_no_convergence() -> None:
    # sigma verdadeiro 1e-6 < bracket_lo=1e-4 (ATM, r=q=0): protecao do bracket.
    target = _forward(OptionKind.CALL, 100.0, 100.0, 0.5, 1e-6, r=0.0, q=0.0).price
    result = _invert(target, OptionKind.CALL, 100.0, 100.0, 0.5, r=0.0, q=0.0)
    assert result.diagnostic.status is IvStatus.NO_CONVERGENCE
    assert result.sigma is None
    assert "bracket_lo" in result.diagnostic.message


def test_expansion_recovers_sigma_seven() -> None:
    target = _forward(OptionKind.CALL, 100.0, 100.0, 0.5, 7.0).price
    result = _invert(target, OptionKind.CALL, 100.0, 100.0, 0.5)
    assert result.diagnostic.status is IvStatus.OK
    assert result.diagnostic.expansions >= 1
    assert result.sigma == pytest.approx(7.0, abs=1e-6)
    assert result.diagnostic.bracket_hi is not None
    assert result.diagnostic.bracket_hi <= CFG.bracket_hi_max


def test_target_beyond_bracket_hi_max_is_no_convergence() -> None:
    # Alvo no teto S e^{-qT}: exigiria sigma alem de bracket_hi_max.
    result = _invert(100.0, OptionKind.CALL, 100.0, 100.0, 0.5)
    assert result.diagnostic.status is IvStatus.NO_CONVERGENCE
    assert result.sigma is None
    assert result.diagnostic.expansions == 2
    assert "bracket_hi_max" in result.diagnostic.message


def test_max_iterations_exhaustion_reports_iterations_and_none_sigma() -> None:
    target = _forward(OptionKind.CALL, 100.0, 100.0, 0.5, 0.3).price
    result = _invert(target, OptionKind.CALL, 100.0, 100.0, 0.5,
                     cfg=Iv(max_iterations=5))
    assert result.diagnostic.status is IvStatus.NO_CONVERGENCE
    assert result.sigma is None
    assert result.diagnostic.iterations == 5
    assert result.diagnostic.residual_price is not None
    assert result.diagnostic.residual_vol is not None


def test_determinism_same_input_same_bits() -> None:
    target = _forward(OptionKind.PUT, 100.0, 110.0, 0.5, 0.42).price
    first = _invert(target, OptionKind.PUT, 100.0, 110.0, 0.5)
    second = _invert(target, OptionKind.PUT, 100.0, 110.0, 0.5)
    assert first == second
    assert first.sigma == second.sigma
    assert first.diagnostic.iterations == second.diagnostic.iterations
    assert first.diagnostic.residual_price == second.diagnostic.residual_price


def test_time_zero_is_not_applicable() -> None:
    result = _invert(5.0, OptionKind.CALL, 100.0, 95.0, 0.0)
    assert result.diagnostic.status is IvStatus.NOT_APPLICABLE
    assert result.sigma is None


@pytest.mark.parametrize("target", [math.nan, math.inf, -math.inf, -0.01])
def test_invalid_target_is_domain_error_without_exception(target: float) -> None:
    result = _invert(target, OptionKind.CALL, 100.0, 100.0, 0.5)
    assert result.diagnostic.status is IvStatus.DOMAIN_ERROR
    assert result.sigma is None


@pytest.mark.parametrize(("field", "value"), [
    ("s", -1.0), ("s", 0.0), ("k", 0.0), ("t", -0.1),
    ("s", math.nan), ("k", math.inf), ("r", math.nan), ("q", -0.01),
])
def test_invalid_inputs_are_domain_error_without_exception(
    field: str, value: float,
) -> None:
    kwargs: dict[str, float] = {"s": 100.0, "k": 100.0, "t": 0.5, "r": RATE, "q": 0.0}
    kwargs[field] = value
    result = _invert(5.0, OptionKind.CALL, kwargs["s"], kwargs["k"], kwargs["t"],
                     kwargs["r"], kwargs["q"])
    assert result.diagnostic.status is IvStatus.DOMAIN_ERROR
    assert result.sigma is None


def test_ivresult_invariant_rejects_inconsistent_construction() -> None:
    ok_diag = IvDiagnostic(IvStatus.OK, 30, 0.1, 0.1, 0.0, 0.0, 1.0, 0, "ok")
    none_diag = IvDiagnostic(IvStatus.NO_CONVERGENCE, 200, 0.1, 0.2, None, None,
                             None, 0, "estourou")
    with pytest.raises(ValueError, match="inconsistentes"):
        IvResult(None, ok_diag)
    with pytest.raises(ValueError, match="inconsistentes"):
        IvResult(0.3, none_diag)
    with pytest.raises(ValueError, match="positivo"):
        IvResult(0.0, ok_diag)


def test_status_enum_values_are_strings() -> None:
    assert IvStatus.OK.value == "ok"
    assert IvStatus.BELOW_INTRINSIC.value == "below_intrinsic"
    assert IvStatus.ABOVE_UPPER_BOUND.value == "above_upper_bound"
    assert IvStatus.NO_CONVERGENCE.value == "no_convergence"
    assert IvStatus.LOW_VEGA.value == "low_vega"
    assert IvStatus.NOT_APPLICABLE.value == "not_applicable"
    assert IvStatus.DOMAIN_ERROR.value == "domain_error"
    assert STATUSES_WITH_SIGMA == {IvStatus.OK, IvStatus.LOW_VEGA}
