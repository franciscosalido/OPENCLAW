"""Contrato numérico e recusas do núcleo binomial e da parametrização CRR."""

import math

import pytest

from backend.derivatives.domain.models import ExerciseStyle, OptionKind
from backend.derivatives.pricing.binomial import (
    BinomialRefusal,
    BinomialRefusalCode,
    TreeParameters,
    crr_parameters,
    tree_price,
)


def _hand_tree(up: float, down: float, rate: float, steps: int) -> TreeParameters:
    return TreeParameters(up=up, down=down, prob_up=(math.exp(rate) - down) / (up - down),
                          discount=math.exp(-rate), steps=steps)


def test_h1_american_put() -> None:
    """O exercício no nó de baixa do primeiro passo vale mais que a continuação."""
    value = tree_price(kind=OptionKind.PUT, style=ExerciseStyle.AMERICAN, spot=50.0,
                       strike=52.0, tree=_hand_tree(1.2, 0.8, 0.05, 2))
    assert value == pytest.approx(5.089632, abs=5e-5, rel=0)
    assert value == pytest.approx(5.089632474198, abs=1e-9, rel=0)


def test_crr_refuses_inadmissible_probability() -> None:
    """Um passo com carry alto e volatilidade baixa viola a condição de não arbitragem."""
    with pytest.raises(BinomialRefusal) as exc:
        crr_parameters(sigma=0.01, rate_cont=0.5, dividend_yield=0.0, time_years=1.0, steps=1)
    assert exc.value.code is BinomialRefusalCode.PROBABILITY_OUT_OF_RANGE
    assert str(exc.value) == "probability_out_of_range"
