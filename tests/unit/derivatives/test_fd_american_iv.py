"""Provas de inversão isolada do preço por diferenças finitas."""
from itertools import product

import pytest

from backend.derivatives.domain.models import ExerciseStyle, OptionKind


@pytest.mark.parametrize(("kind", "spot", "years", "sigma"), product(
    (OptionKind.CALL, OptionKind.PUT), (97., 100., 104., 108., 112.), (.5, 1.), (.2, .35),
))
def test_t13_round_trip(kind: OptionKind, spot: float, years: float, sigma: float) -> None:
    from backend.derivatives.pricing.fd_american import FdGrid, fd_implied_vol, fd_price

    grid = FdGrid(400, 200, 6., 2)
    target = fd_price(kind=kind, style=ExerciseStyle.AMERICAN, spot=spot, strike=100.,
                      time_years=years, rate_cont=.06, dividend_yield=.04, sigma=sigma, grid=grid)
    solved = fd_implied_vol(kind=kind, spot=spot, strike=100., time_years=years, rate_cont=.06,
                            dividend_yield=.04, target_price=target, grid=grid, bracket_lo=.001,
                            bracket_hi=2., max_iterations=64, tol_price_rel=1e-10, tol_vol=1e-8)
    assert solved.status == "ok"
    assert solved.sigma == pytest.approx(sigma, abs=1e-6, rel=0)
