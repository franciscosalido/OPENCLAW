"""Provas independentes do esquema de diferenças finitas."""
import math
from itertools import product

import pytest

from backend.derivatives.domain.models import ExerciseStyle, OptionKind

R = math.log1p(.149)
CALL, PUT = OptionKind.CALL, OptionKind.PUT
AMERICAN, EUROPEAN = ExerciseStyle.AMERICAN, ExerciseStyle.EUROPEAN
ANCHORS = [
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
def test_t1_scheme_anchors(case: tuple, style: ExerciseStyle) -> None:
    from backend.derivatives.pricing.fd_american import FdGrid, fd_price

    _, kind, spot, strike, years, rate, q, sigma, american, european, _ = case
    price = fd_price(kind=kind, style=style, spot=spot, strike=strike, time_years=years,
                     rate_cont=rate, dividend_yield=q, sigma=sigma, grid=FdGrid(400, 200, 6., 2))
    assert price == pytest.approx(american if style is AMERICAN else european, abs=1e-6, rel=0)
