"""IV por observação sintética, com oráculos de preço escolhidos por modelo."""

from dataclasses import replace
from decimal import Decimal
from itertools import product
from typing import Any
from unittest.mock import patch

import pytest

from backend.derivatives.domain.carry import CarryAssumption
from backend.derivatives.domain.models import ExerciseStyle, OptionContract, OptionKind
from backend.derivatives.pricing import american_bridge as bridge
from backend.derivatives.pricing.bsm import BsmInputs, price
from backend.derivatives.pricing.implied_vol import IvStatus, implied_vol
from config.derivatives_config_model import Iv
from tests.unit.derivatives.test_american_bridge import (
    A1_TERMS, A2_TERMS, CALL, NONE, PUT, TTE, YIELD, _carry, _price,
)

SPOT = Decimal("100")
CRR = "crr_american_v1"
BSM = "bsm_european_v1"


def _invert(target: Decimal, contract: OptionContract = CALL, **changes: Any
            ) -> bridge.AmericanIvSolution | bridge.AmericanIvRefusal:
    args = dict(terms=A1_TERMS, carry=YIELD, spot=SPOT, rate_cont=0.05, tte=TTE, steps=50)
    return bridge.american_implied_vol(contract, target_price=target, **(args | changes))


def _assert_refused(result: bridge.AmericanIvSolution | bridge.AmericanIvRefusal,
                    reason: str) -> None:
    assert isinstance(result, bridge.AmericanIvRefusal), result
    assert result.reason == reason and result.sigma is None


SCENARIOS = [
    (CALL, YIELD, 0.05), (CALL, NONE, 0.0), (PUT, NONE, 0.05), (PUT, YIELD, -0.025),
]


@pytest.mark.parametrize(("contract", "carry", "rate"), SCENARIOS,
                         ids=["call-yield", "call-zero-rate", "put", "put-negative-rate"])
@pytest.mark.parametrize(("spot", "years", "vol"), product(
    (Decimal("96"), SPOT, Decimal("104")), (0.25, 1.0), (0.217, 0.351),
))
def test_crr_round_trip(contract: OptionContract, carry: CarryAssumption, rate: float,
                        spot: Decimal, years: float, vol: float) -> None:
    """A média publicada pela ponte deve recuperar a vol em cada um dos 48 pontos."""
    tte = replace(TTE, year_fraction=years)
    obs = _price(contract, carry=carry, spot=spot, rate_cont=rate, tte=tte, sigma=vol, steps=50)
    assert obs.price is not None
    result = _invert(obs.price, contract, carry=carry, spot=spot, rate_cont=rate, tte=tte)
    assert isinstance(result, bridge.AmericanIvSolution), result
    assert result.model == CRR and abs(result.sigma - vol) <= 1e-6
    lo, hi = result.bracket
    assert hi - lo <= 1e-8 and lo <= result.sigma <= hi
    assert lo - 1e-12 <= vol <= hi + 1e-12


def _oracle(target: Decimal, rate: float = 0.05) -> float:
    oracle = implied_vol(float(target), kind=OptionKind.CALL, spot=100., strike=100.,
                         rate_cont=rate, dividend_yield=0., time_years=1., cfg=Iv())
    assert oracle.sigma is not None and oracle.diagnostic.status is IvStatus.OK
    return oracle.sigma


@pytest.mark.parametrize(("rate", "vol"), [(0.05, 0.2), (0.13, 0.41), (1e-14, 0.19)])
def test_d1_bsm_oracle(rate: float, vol: float) -> None:
    """O atalho usa a IV da Fase 1 para cada preço BSM elegível."""
    obs = Decimal(str(price(BsmInputs(OptionKind.CALL, 100., 100., 1., rate, vol),
                            theta_basis=252).price))
    with patch.object(bridge, "crr_price", side_effect=AssertionError("D1 chamou CRR")):
        result = _invert(obs, carry=NONE, rate_cont=rate)
    assert isinstance(result, bridge.AmericanIvSolution), result
    assert (result.model, result.sigma) == (BSM, _oracle(obs, rate))
    assert abs(result.sigma - vol) <= 1e-6


def test_cross_model_discretization() -> None:
    """O alvo cruzado mantém o preço do PR01A e a inversão estabelecida por D1."""
    obs = _price(carry=NONE, steps=200)
    assert obs.price is not None and abs(float(obs.price) - 10.449949594185) < 1e-11
    bsm = price(BsmInputs(OptionKind.CALL, 100., 100., 1., .05, .2), theta_basis=252)
    assert abs(bsm.price - 10.450583572186) < 1e-11
    result = _invert(obs.price, carry=NONE, steps=200)
    assert isinstance(result, bridge.AmericanIvSolution), result
    assert result.sigma == _oracle(obs.price)
    assert abs(result.sigma - .199983104711) < 1e-11
    assert 1.68e-5 < .2 - result.sigma < 1.70e-5


@pytest.mark.parametrize(("contract", "carry", "rate"), [
    (CALL, _carry("1e-16"), 0.05), (CALL, NONE, 0.0), (CALL, NONE, -0.03), (PUT, NONE, 0.05),
])
def test_only_the_american_pair(contract: OptionContract, carry: CarryAssumption,
                                rate: float) -> None:
    """Cada tentativa na árvore usa exatamente o par americano solicitado."""
    with patch.object(bridge, "crr_price", wraps=bridge.crr_price) as tree:
        result = _invert(Decimal("8"), contract, carry=carry, rate_cont=rate)
    assert isinstance(result, bridge.AmericanIvSolution) and result.model == CRR
    evaluations = [(c.kwargs["style"], c.kwargs["steps"], c.kwargs["sigma"])
                   for c in tree.call_args_list]
    assert 4 <= len(evaluations) <= 136 and len(evaluations) % 2 == 0
    for first, second in zip(evaluations[::2], evaluations[1::2], strict=True):
        assert first[:2] == (ExerciseStyle.AMERICAN, 50)
        assert second == (ExerciseStyle.AMERICAN, 51, first[2])


@pytest.mark.parametrize(("changes", "reason"), [
    (dict(contract=CALL.model_copy(update={"exercise_style": ExerciseStyle.EUROPEAN}), carry=None),
     "american_bridge:not_american"),
    (dict(contract=CALL.model_copy(update={"exercise_style": ExerciseStyle.UNKNOWN})),
     "unknown_exercise_style"),
    (dict(terms=A1_TERMS.model_copy(update={"strike": Decimal("101")}), carry=None),
     "carry:missing_carry_assumption"),
    (dict(terms=A1_TERMS.model_copy(update={"strike": Decimal("101")}), carry=NONE),
     "american_bridge:series_terms_mismatch"),
    (dict(terms=A2_TERMS, carry=YIELD), "carry:strike_adjustment_unknown"),
    (dict(spot=100., carry=NONE), "american_bridge:invalid_spot_type"),
    (dict(rate_cont=True), "binomial:invalid_input_type"),
    (dict(tte=replace(TTE, year_fraction=1)), "binomial:invalid_input_type"),
    (dict(steps=True, carry=NONE), "binomial:invalid_steps"),
    (dict(steps=5000), "binomial:invalid_steps"),
    (dict(steps=0), "binomial:invalid_steps"),
    (dict(rate_cont=float("nan")), "binomial:non_finite_input"),
    (dict(spot=Decimal("sNaN")), "binomial:non_finite_input"),
    (dict(spot=Decimal("0")), "binomial:input_out_of_domain"),
    (dict(tte=replace(TTE, year_fraction=-1.0)), "binomial:input_out_of_domain"),
    (dict(tte=replace(TTE, year_fraction=0.0)), "iv:expiry"),
])
def test_admission(changes: dict[str, Any], reason: str) -> None:
    """Estilo, termos, carry e domínio são verificados antes de inverter."""
    _assert_refused(_invert(Decimal("8"), **changes), reason)


@pytest.mark.parametrize("target", [True, 7.0, Decimal("-1"), Decimal("sNaN"),
                                    Decimal("Infinity"), Decimal("1e999")])
def test_invalid_target(target: Any) -> None:
    """Alvo é um preço Decimal finito e não negativo representável pelo motor."""
    _assert_refused(_invert(target), "iv:invalid_target")


@pytest.mark.parametrize(("target", "changes", "reason"), [
    ("9", dict(contract=PUT, spot=Decimal("90")), "iv:below_intrinsic"),
    ("10", dict(contract=PUT, spot=Decimal("90")), "iv:not_identifiable"),
    ("0.00000000001", dict(contract=PUT), "iv:not_identifiable"),
    ("4", dict(carry=NONE), "iv:below_intrinsic"),
    ("100.000000001", dict(carry=NONE), "iv:not_identifiable"),
    ("101", dict(), "iv:above_upper_bound"),
    ("90", dict(contract=PUT), "iv:unbracketed"),
    ("120", dict(contract=PUT, rate_cont=-0.1), "iv:above_upper_bound"),
    ("103", dict(contract=PUT, rate_cont=-0.1), "iv:unbracketed"),
    ("8", dict(rate_cont=30.), "iv:below_intrinsic"),
])
def test_bounds(target: str, changes: dict[str, Any], reason: str) -> None:
    """Distingue arbitragem, resolução de preço e limite de busca."""
    _assert_refused(_invert(Decimal(target), **changes), reason)


def test_low_local_sensitivity() -> None:
    """Um preço interior mas insensível a um movimento de 1e-6 não determina IV."""
    spot = Decimal("0.000001")
    contract = PUT.model_copy(update={"strike": spot})
    terms = A1_TERMS.model_copy(update={"strike": spot})
    obs = _price(contract, terms=terms, spot=spot, carry=NONE, steps=50)
    assert obs.price is not None and obs.price > Decimal("1e-9")
    _assert_refused(_invert(obs.price, contract, terms=terms, spot=spot, carry=NONE),
                    "iv:not_identifiable")


def test_independent_sides() -> None:
    """Uma recusa em um lado da cotação preserva a inversão do outro."""
    _assert_refused(_invert(Decimal("-1")), "iv:invalid_target")
    result = _invert(Decimal("7"))
    assert isinstance(result, bridge.AmericanIvSolution) and result.sigma > 0.0


@pytest.mark.parametrize("endpoint", [
    2.0,
    abs(.05 - .08) * (1 / 50) ** .5 + 1e-8,
])
def test_bracket_endpoint(endpoint: float) -> None:
    """Coincidência com preço extremo da busca não certifica raiz interior."""
    obs = _price(steps=50, sigma=endpoint)
    assert obs.price is not None
    _assert_refused(_invert(obs.price), "iv:not_identifiable")


def test_solver_exhaustion() -> None:
    """Um salto que envolve o alvo mas nunca o precifica esgota a bisseção."""
    def discontinuous(*, sigma: float, **kwargs: Any) -> float:
        return 3.0 if sigma < .3 else 9.0

    with patch.object(bridge, "crr_price", side_effect=discontinuous) as tree:
        _assert_refused(_invert(Decimal("7")), "iv:no_convergence")
    assert tree.call_count <= 136


def test_tree_refusal_stops_search() -> None:
    """A recusa do próprio motor exige o código original e encerra a inversão."""
    from backend.derivatives.pricing.binomial import BinomialRefusal, BinomialRefusalCode

    exc = BinomialRefusal(BinomialRefusalCode.TREE_NOT_REPRESENTABLE)
    with patch.object(bridge, "crr_price", side_effect=exc) as tree:
        _assert_refused(_invert(Decimal("8")), "binomial:tree_not_representable")
    tree.assert_called_once()


def test_d1_ill_conditioned() -> None:
    """Um oráculo europeu com LOW_VEGA não fornece número ao chamador americano."""
    spot = Decimal("0.000001")
    contract = CALL.model_copy(update={"strike": spot})
    terms = A1_TERMS.model_copy(update={"strike": spot})
    obs = price(BsmInputs(OptionKind.CALL, float(spot), float(spot), 1., .05, .2), theta_basis=252)
    oracle = implied_vol(obs.price, kind=OptionKind.CALL, spot=float(spot), strike=float(spot),
                         time_years=1., rate_cont=.05, dividend_yield=0., cfg=Iv())
    assert oracle.diagnostic.status is IvStatus.LOW_VEGA
    _assert_refused(_invert(Decimal(str(obs.price)), contract, carry=NONE, terms=terms, spot=spot),
                    "iv:not_identifiable")
