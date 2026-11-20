"""IV por observação sintética, com oráculos de preço escolhidos por modelo."""

from dataclasses import replace
from decimal import Decimal
from itertools import product
from typing import Any
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from pydantic import ValidationError

from backend.derivatives.domain.carry import CarryAssumption
from backend.derivatives.domain.models import ExerciseStyle, OptionContract, OptionKind
from backend.derivatives.domain.series_terms import SeriesTerms
from backend.derivatives.pricing import american_bridge as bridge
from backend.derivatives.pricing.binomial import BinomialRefusal, BinomialRefusalCode
from backend.derivatives.pricing.conventions import TimeToExpiry
from config.american_iv_config_model import AmericanIvConfig, load_american_iv_config
from tests.unit.derivatives.test_american_bridge import (
    A1_TERMS, A2_TERMS, CALL, NONE, PUT, TTE, YIELD, _carry, _price,
)

SPOT = Decimal("100")
CRR = "crr_american_v1"

CFG = load_american_iv_config()

def _invert(
    target: Decimal, contract: OptionContract = CALL, *, terms: SeriesTerms = A1_TERMS,
    carry: CarryAssumption | None = YIELD, spot: Decimal = SPOT, rate_cont: float = 0.05,
    tte: TimeToExpiry = TTE, steps: int = 50, cfg: AmericanIvConfig = CFG,
) -> bridge.AmericanIvSolution | bridge.AmericanIvRefusal:
    return bridge.american_implied_vol(
        contract, terms=terms, carry=carry, spot=spot, target_price=target,
        rate_cont=rate_cont, tte=tte, steps=steps, cfg=cfg,
    )


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
    assert hi - lo <= CFG.tol_vol and lo <= result.sigma <= hi
    assert lo - 1e-12 <= vol <= hi + 1e-12


@pytest.mark.parametrize(("contract", "carry", "rate"), [
    (CALL, _carry("1e-16"), 0.05), (CALL, NONE, 0.0), (CALL, NONE, -0.03),
    (PUT, NONE, 0.05), (CALL, NONE, 0.05),
])
def test_only_the_american_pair(contract: OptionContract, carry: CarryAssumption,
                                rate: float) -> None:
    """Cada tentativa na árvore usa exatamente o par americano solicitado."""
    with patch.object(bridge, "crr_price", wraps=bridge.crr_price) as tree:
        result = _invert(Decimal("8"), contract, carry=carry, rate_cont=rate)
    assert isinstance(result, bridge.AmericanIvSolution) and result.model == CRR
    evaluations = [(c.kwargs["style"], c.kwargs["steps"], c.kwargs["sigma"])
                   for c in tree.call_args_list]
    assert 4 <= len(evaluations) <= 2 * (CFG.max_iterations + 4) and len(evaluations) % 2 == 0
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
    ("9", dict(contract=PUT, spot=Decimal("90"), carry=NONE), "iv:below_intrinsic"),
    ("10", dict(contract=PUT, spot=Decimal("90"), carry=NONE), "iv:not_identifiable"),
    ("0.00000000001", dict(contract=PUT, carry=NONE), "iv:not_identifiable"),
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


@pytest.mark.parametrize("kind", [CALL, PUT])
def test_low_local_sensitivity(kind: OptionContract) -> None:
    """Um preço interior mas insensível a um movimento de 1e-6 não determina IV."""
    spot = Decimal("0.000001")
    contract = kind.model_copy(update={"strike": spot})
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
    CFG.bracket_hi,
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
    assert tree.call_count <= 2 * (CFG.max_iterations + 4)


def test_tree_refusal_stops_search() -> None:
    """A recusa do próprio motor exige o código original e encerra a inversão."""
    exc = BinomialRefusal(BinomialRefusalCode.TREE_NOT_REPRESENTABLE)
    with patch.object(bridge, "crr_price", side_effect=exc) as tree:
        _assert_refused(_invert(Decimal("8")), "binomial:tree_not_representable")
    tree.assert_called_once()


@pytest.mark.parametrize("steps", [3, 10, 50, 200])
def test_zero_carry_positive_rate_keeps_same_model(steps: int) -> None:
    """Uma call sem carry não pode reintroduzir o desvio entre preço e IV."""
    sigma = .2
    quote = _price(carry=NONE, sigma=sigma, steps=steps)
    assert quote.price is not None
    result = _invert(quote.price, carry=NONE, steps=steps)
    assert isinstance(result, bridge.AmericanIvSolution)
    assert abs(result.sigma - sigma) <= 1e-6
    assert result.model == CRR


@pytest.fixture
def american_iv_yaml(tmp_path: Path) -> Path:
    """Cópia da fonte real de configuração, sem tocar o YAML padrão."""
    config_path = tmp_path / "american_iv.yaml"
    source = Path("config/american_iv.yaml")
    config_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return config_path


def _change_yaml(config_path: Path, **changes: object) -> None:
    content = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    content.update(changes)
    config_path.write_text(yaml.safe_dump(content), encoding="utf-8")


def test_american_iv_limits_come_from_yaml(american_iv_yaml: Path) -> None:
    """As regras de busca vêm de uma única seção YAML e chegam ao solver."""
    _change_yaml(american_iv_yaml, bracket_hi=0.15)
    settings = load_american_iv_config(american_iv_yaml)
    obs = _price(carry=NONE, sigma=.2, steps=50)
    assert obs.price is not None
    result = bridge.american_implied_vol(
        CALL, terms=A1_TERMS, carry=NONE, spot=SPOT, target_price=obs.price,
        rate_cont=.05, tte=TTE, steps=50, cfg=settings,
    )
    _assert_refused(result, "iv:unbracketed")


@pytest.mark.parametrize("changes", [
    {"bracket_hi": .00005}, {"bracket_lo": 0}, {"bracket_hi": float("inf")},
    {"tol_vol": float("nan")}, {"tol_price_rel": "1.0e-10"},
    {"max_iterations": True}, {"max_iterations": 0}, {"max_iterations": 65},
    {"unknown": 1},
])
def test_american_iv_rejects_invalid_yaml(
    american_iv_yaml: Path, changes: dict[str, object],
) -> None:
    _change_yaml(american_iv_yaml, **changes)
    with pytest.raises(ValidationError):
        load_american_iv_config(american_iv_yaml)


def test_yaml_iteration_budget_changes_solver(american_iv_yaml: Path) -> None:
    _change_yaml(american_iv_yaml, max_iterations=1)
    settings = load_american_iv_config(american_iv_yaml)
    result = _invert(Decimal("7"), cfg=settings)
    _assert_refused(result, "iv:no_convergence")
    assert result.iterations == 1 and result.expansions == 0


def test_yaml_price_tolerance_changes_identifiability(american_iv_yaml: Path) -> None:
    _change_yaml(american_iv_yaml, tol_price_rel=.5)
    settings = load_american_iv_config(american_iv_yaml)
    _assert_refused(_invert(Decimal("7"), cfg=settings), "iv:not_identifiable")


def test_yaml_vol_tolerance_changes_iteration_count(american_iv_yaml: Path) -> None:
    _change_yaml(american_iv_yaml, tol_vol=1.0)
    settings = load_american_iv_config(american_iv_yaml)
    midpoint = (settings.bracket_lo + settings.bracket_hi) / 2
    target = Decimal(str(2.0 + 10 * midpoint))
    with patch.object(bridge, "crr_price", side_effect=lambda **k: 2.0 + 10 * k["sigma"]):
        loose = _invert(target, carry=NONE, rate_cont=0.0, cfg=settings)
        tight = _invert(target, carry=NONE, rate_cont=0.0)
    assert isinstance(loose, bridge.AmericanIvSolution) and loose.iterations == 1
    assert isinstance(tight, bridge.AmericanIvSolution) and tight.iterations > 1
    assert abs(loose.sigma - tight.sigma) <= 1e-6


def test_american_iv_without_file_has_no_fallback(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_american_iv_config(tmp_path / "missing.yaml")


def test_american_iv_malformed_yaml_reports_safe_message(american_iv_yaml: Path) -> None:
    american_iv_yaml.write_text("private-marker: [", encoding="utf-8")
    with pytest.raises(ValueError, match="^YAML de IV americana inválido$"):
        load_american_iv_config(american_iv_yaml)


def test_american_iv_required_values_have_no_defaults(american_iv_yaml: Path) -> None:
    content = yaml.safe_load(american_iv_yaml.read_text(encoding="utf-8"))
    del content["tol_vol"]
    american_iv_yaml.write_text(yaml.safe_dump(content), encoding="utf-8")
    with pytest.raises(ValidationError, match="Field required"):
        load_american_iv_config(american_iv_yaml)


@pytest.mark.parametrize("unsafe", [
    None,
    {"bracket_hi": 2.0},
    CFG.model_copy(update={"tol_vol": float("nan")}),
    AmericanIvConfig.model_construct(**{**CFG.model_dump(), "max_iterations": 65}),
])
def test_forged_configuration_cannot_enter_solver(unsafe: Any) -> None:
    """A configuração deve ser exata, validada e com teto de 68 pares."""
    with patch.object(bridge, "crr_price", side_effect=AssertionError("CRR indevido")):
        _assert_refused(_invert(Decimal("7"), cfg=unsafe), "iv:invalid_config")


def test_invalid_target_precedes_invalid_config() -> None:
    """Config inválida não mascara recusa já definida para o alvo."""
    unsafe: Any = None
    _assert_refused(_invert(Decimal("-1"), cfg=unsafe), "iv:invalid_target")
