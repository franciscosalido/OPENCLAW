"""Provas de inversão isolada do preço por diferenças finitas."""
from dataclasses import replace
from decimal import Decimal
from itertools import product
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from backend.derivatives.domain.models import ExerciseStyle, OptionKind
from backend.derivatives.pricing.american_bridge import AmericanIvSolution, american_implied_vol
from backend.derivatives.pricing.fd_american import FdGrid, FdIvResult, fd_implied_vol, fd_price
from config.american_fd_config_model import load_american_fd_config
from config.american_iv_config_model import load_american_iv_config
from tests.unit.derivatives.test_american_bridge import A1_TERMS, CALL, TTE, _carry
from tests.unit.derivatives.test_fd_american import ANCHORS, GRID, R, Anchor


@pytest.mark.parametrize(("kind", "spot", "years", "sigma"), product(
    (OptionKind.CALL, OptionKind.PUT), (97., 100., 104., 108., 112.), (.5, 1.), (.2, .35),
))
def test_t13_round_trip(kind: OptionKind, spot: float, years: float, sigma: float) -> None:
    grid = FdGrid(400, 200, 6., 2)
    target = fd_price(kind=kind, style=ExerciseStyle.AMERICAN, spot=spot, strike=100.,
                      time_years=years, rate_cont=.06, dividend_yield=.04, sigma=sigma, grid=grid)
    solved = fd_implied_vol(kind=kind, spot=spot, strike=100., time_years=years, rate_cont=.06,
                            dividend_yield=.04, target_price=target, grid=grid, bracket_lo=.001,
                            bracket_hi=2., max_iterations=64, tol_price_rel=1e-10, tol_vol=1e-8)
    assert solved.status == "ok"
    assert solved.sigma == pytest.approx(sigma, abs=1e-6, rel=0)


IV: dict[str, Any] = dict(
    kind=OptionKind.CALL, spot=100., strike=100., time_years=1.,
    rate_cont=R, dividend_yield=.06, target_price=13.0276741026,
    grid=GRID, bracket_lo=.001, bracket_hi=2., max_iterations=64,
    tol_price_rel=1e-10, tol_vol=1e-8,
)


def _iv_with(**change: Any) -> FdIvResult:
    values: dict[str, Any] = IV | change
    return fd_implied_vol(**values)


def _case_iv(case: Anchor) -> dict[str, Any]:
    _, kind, spot, strike, years, rate, q, _, _, _, target = case
    return IV | dict(kind=kind, spot=spot, strike=strike, time_years=years,
                     rate_cont=rate, dividend_yield=q, target_price=target)


@pytest.mark.parametrize("case", [pytest.param(case, id=case[0]) for case in ANCHORS])
def test_t14_inverse_independent_target(case: Anchor) -> None:
    found = fd_implied_vol(**_case_iv(case))
    assert found.status == "ok" and found.sigma is not None
    assert abs(found.sigma - case[7]) <= 5e-5


@pytest.mark.parametrize("case", [pytest.param(case, id=case[0]) for case in ANCHORS])
def test_t15_iv_against_crr_200(case: Anchor) -> None:
    _, kind, spot, strike, years, rate, q, _, _, _, target = case
    terms = A1_TERMS.model_copy(update={"strike": Decimal(str(strike))})
    contract = CALL.model_copy(update={"kind": kind, "strike": terms.strike})
    crr = american_implied_vol(
        contract, terms=terms, carry=_carry(str(q) if q else None), spot=Decimal(str(spot)),
        rate_cont=rate, tte=replace(TTE, year_fraction=years), target_price=Decimal(str(target)),
        cfg=load_american_iv_config(), steps=200,
    )
    fd = fd_implied_vol(**_case_iv(case))
    assert isinstance(crr, AmericanIvSolution)
    assert fd.status == "ok" and fd.sigma is not None
    assert abs(crr.sigma - fd.sigma) <= 5e-4


@pytest.mark.parametrize(("change", "status"), [
    ({"target_price": 0.}, "not_identifiable"),
    ({"target_price": 9999.}, "unbracketed"),
    ({"max_iterations": 1}, "no_convergence"),
    ({"time_years": 0.}, "invalid_input"),
    ({"bracket_hi": 40.}, "grid_not_admissible"),
])
def test_t16_named_states(change: dict[str, object], status: str) -> None:
    found = _iv_with(**change)
    assert found.status == status and found.sigma is None


def test_t16_near_initial_bracket_endpoint_has_no_sigma() -> None:
    """A raiz fica dentro do bracket, mas a sonda à esquerda sairia dele."""
    known = fd_price(kind=OptionKind.CALL, style=ExerciseStyle.AMERICAN, spot=100.,
                     strike=100., time_years=1., rate_cont=R, dividend_yield=.06,
                     sigma=.25, grid=GRID)
    result = _iv_with(target_price=known, bracket_lo=.2499999)
    assert result.status == "not_identifiable" and result.sigma is None


@pytest.mark.parametrize("name", list(IV))
def test_t17_wrong_type_for_every_argument(name: str) -> None:
    found = _iv_with(**{name: True})
    assert found.status == "invalid_input" and found.sigma is None


def test_t17_invalid_before_expiry() -> None:
    result = _iv_with(time_years=0., spot=float("inf"))
    assert result.status == "invalid_input" and result.sigma is None


@pytest.mark.parametrize("bad", [
    {"unknown": 1}, {"space_nodes": 401}, {"space_nodes": "400"},
    {"bracket_lo": 2.}, {"bracket_lo": 3.}, {"max_iterations": True},
    {"rannacher_steps": 201}, {"tol_vol": float("inf")}, None,
])
def test_t18_invalid_yaml(tmp_path: Path, bad: dict[str, object] | None) -> None:
    source = Path("config/american_fd.yaml")
    content = yaml.safe_load(source.read_text(encoding="utf-8"))
    if bad is None:
        content.pop("space_nodes")
    else:
        content.update(bad)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(content), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_american_fd_config(config_path)


def test_t18_delivered_profile() -> None:
    config = load_american_fd_config()
    assert (config.space_nodes, config.time_steps, config.width_stdevs, config.rannacher_steps) == (
        400, 200, 6., 2,
    )
    assert (config.bracket_lo, config.bracket_hi, config.max_iterations) == (.001, 2., 64)
    assert (config.tol_price_rel, config.tol_vol) == (1e-10, 1e-8)
    assert (config.divergence_vol, config.low_sensitivity_price) == (5e-4, 1e-4)
