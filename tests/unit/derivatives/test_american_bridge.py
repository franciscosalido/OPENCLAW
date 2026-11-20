"""Contrato da ponte americana, com preços de referência do Marco 2A."""

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TypedDict

import pytest

from backend.derivatives.domain.carry import CarryAssumption, CarryKind
from backend.derivatives.domain.models import ExerciseStyle, OptionContract, OptionKind
from backend.derivatives.domain.series_terms import (
    AdjustmentEvidence, AdjustmentPolicy, SeriesTerms,
)
from backend.derivatives.pricing.american_bridge import price_american_contract
from backend.derivatives.pricing.binomial import crr_price
from backend.derivatives.pricing.contract_pricing import PricingOutcome
from backend.derivatives.pricing.conventions import TimeToExpiry

DAY = date(2026, 11, 19)
TTE = TimeToExpiry(252, 1.0, "synthetic", "test", 252, False)
CALL = OptionContract(
    symbol="XPTO1", underlying="XPTO", kind=OptionKind.CALL, exercise_style=ExerciseStyle.AMERICAN,
    strike=Decimal("100"), expiry=date(2027, 11, 19),
    contract_size=100, quotation_form=1, isin=None,
)
PUT = CALL.model_copy(update={"kind": OptionKind.PUT})
REFERENCE = (Path(__file__).resolve().parents[2] / "fixtures/derivatives/reference"
             / "crr_american_reference.json")


def _terms(policy: AdjustmentPolicy, strike: Decimal = CALL.strike) -> SeriesTerms:
    evidence = None if policy is AdjustmentPolicy.UNKNOWN else AdjustmentEvidence(
        issuer="B3", document="synthetic", version="1", published_on=DAY, symbol="XPTO1",
        effective_on=DAY, policy=policy,
    )
    return SeriesTerms(
        symbol="XPTO1", effective_on=DAY, source="test", strike=strike, contract_size=100,
        quotation_form=1, exercise_style=ExerciseStyle.AMERICAN, currency="BRL",
        adjustment_policy=policy, evidence=evidence,
    )


def _carry(q: str | None) -> CarryAssumption:
    return CarryAssumption(
        symbol="XPTO1", effective_on=DAY, source="test",
        kind=CarryKind.NONE if q is None else CarryKind.CONTINUOUS_YIELD,
        dividend_yield=None if q is None else Decimal(q),
    )


A1_TERMS = _terms(AdjustmentPolicy.UNPROTECTED)
A2_TERMS = _terms(AdjustmentPolicy.UNKNOWN)
YIELD = _carry("0.08")
NONE = _carry(None)


def _price(
    contract: OptionContract = CALL, *, terms: SeriesTerms = A1_TERMS,
    carry: CarryAssumption | None = YIELD, spot: Decimal = Decimal("100"), rate_cont: float = 0.05,
    sigma: float = 0.2, tte: TimeToExpiry = TTE, steps: int = 200,
    assumptions: dict[str, str | float | bool] | None = None,
) -> PricingOutcome:
    return price_american_contract(
        contract, terms=terms, carry=carry, spot=spot, rate_cont=rate_cont,
        sigma=sigma, tte=tte, steps=steps, assumptions={} if assumptions is None else assumptions,
    )


@pytest.mark.parametrize(("contract", "terms", "carry", "ids"), [
    (CALL, A1_TERMS, YIELD, ("crr_06_call_yield", "crr_07_call_yield")),
    (PUT, A2_TERMS, NONE, ("crr_16_put_rate", "crr_17_put_rate")),
], ids=["A1", "A2"])
def test_t1_anchors(contract: OptionContract, terms: SeriesTerms, carry: CarryAssumption,
                    ids: tuple[str, str]) -> None:
    """Compara preço e prêmio com as médias decimais das duas árvores da referência."""
    cases = {row["case_id"]: row for row in json.loads(REFERENCE.read_bytes())["cases"]}
    american = sum(Decimal(cases[key]["american_price"]) for key in ids) / 2
    european = sum(Decimal(cases[key]["european_price"]) for key in ids) / 2
    outcome = _price(contract, terms=terms, carry=carry)
    assert outcome.supported and outcome.reason is None and outcome.price is not None
    assert abs(outcome.price - american) <= Decimal("1e-11") * max(1, american)
    premium = outcome.assumptions["early_exercise_premium"]
    assert isinstance(premium, float) and abs(premium - float(american - european)) <= 1e-9
    assert (outcome.model, outcome.regime, outcome.sigma_source) == (
        "crr_american_v1", "tree", "given",
    )
    assert outcome.greeks is None and outcome.iv is None


def test_t3_single_yield_source() -> None:
    """Substitui as hipóteses da Fase 01 somente na resposta suportada."""
    original: dict[str, str | float | bool] = {
        "dividend_yield": 0.0, "strike_adjusted_by_exchange_assumed": True,
        "calendar_id": "test_calendar",
    }
    assumptions = original.copy()
    refused = _price(carry=None, assumptions=assumptions)
    assert not refused.supported and refused.assumptions == original
    outcome = _price(assumptions=assumptions)
    assert outcome.supported and outcome.inputs_echo["dividend_yield"] == 0.08
    assert outcome.assumptions["carry_dividend_yield"] == 0.08
    assert "dividend_yield" not in outcome.assumptions, outcome.assumptions
    assert "strike_adjusted_by_exchange_assumed" not in outcome.assumptions
    assert outcome.assumptions == {
        "calendar_id": "test_calendar", "carry_kind": "CONTINUOUS_YIELD",
        "carry_dividend_yield": 0.08, "carry_source": "test", "carry_effective_on": DAY.isoformat(),
        "strike_adjustment_policy": "UNPROTECTED", "pricing_model": "crr_american_v1",
        "crr_steps": 200.0, "crr_pair_average": True,
        "early_exercise_premium": outcome.assumptions["early_exercise_premium"],
    }
    assert assumptions == original


def test_caller_cannot_override_resolved_keys() -> None:
    """Chave recebida com o mesmo nome de uma chave resolvida não vira segunda fonte."""
    forged: dict[str, str | float | bool] = {
        "carry_kind": "NONE", "carry_dividend_yield": 0.0, "carry_source": "forged",
        "carry_effective_on": "1900-01-01", "strike_adjustment_policy": "PROTECTED",
        "pricing_model": "bsm_european_v1", "crr_steps": 1.0, "crr_pair_average": False,
        "early_exercise_premium": -1.0, "calendar_id": "test_calendar",
    }
    outcome = _price(assumptions=forged)
    clean = _price(assumptions={"calendar_id": "test_calendar"})
    assert outcome.supported and outcome.assumptions == clean.assumptions
    assert outcome.assumptions["carry_dividend_yield"] == 0.08


_ECHO_FIELDS = (
    "symbol", "kind", "exercise_style", "spot", "strike", "time_years",
    "rate_cont", "sigma", "dividend_yield", "steps",
)


def test_t2_tree_pair() -> None:
    """Confere cada árvore, o eco ordenado e a conversão decimal da média."""
    outcome = _price()
    echo = outcome.inputs_echo
    assert tuple(echo) == (*_ECHO_FIELDS, "price_steps_n", "price_steps_n1", "european_same_trees")
    assert tuple(echo.values())[:10] == (
        "XPTO1", "CALL", "AMERICAN", 100.0, 100.0, 1.0, 0.05, 0.2, 0.08, 200.0,
    )
    assert type(echo["steps"]) is float
    assert type(outcome.assumptions["crr_steps"]) is float
    assert outcome.assumptions["crr_pair_average"] is True

    def reference(style: ExerciseStyle, n: int) -> float:
        return crr_price(
            kind=OptionKind.CALL, style=style, spot=100.0, strike=100.0, time_years=1.0,
            rate_cont=0.05, sigma=0.2, dividend_yield=0.08, steps=n,
        )

    first, second = echo["price_steps_n"], echo["price_steps_n1"]
    assert isinstance(first, float) and first == reference(ExerciseStyle.AMERICAN, 200)
    assert isinstance(second, float) and second == reference(ExerciseStyle.AMERICAN, 201)
    assert outcome.price == Decimal(str((first + second) / 2))
    assert echo["european_same_trees"] == (
        reference(ExerciseStyle.EUROPEAN, 200) + reference(ExerciseStyle.EUROPEAN, 201)
    ) / 2


class _Changes(TypedDict, total=False):
    contract: OptionContract
    terms: SeriesTerms
    carry: CarryAssumption | None
    spot: Decimal
    sigma: float
    rate_cont: float
    steps: int


_EURO = CALL.model_copy(update={"exercise_style": ExerciseStyle.EUROPEAN})
_OTHER_STRIKE = CALL.model_copy(update={"strike": Decimal("101")})
_MISMATCH = "american_bridge:series_terms_mismatch"
_MISSING_CARRY = "carry:missing_carry_assumption"
_UNRESOLVED = "unresolved"
_INVALID = SeriesTerms.model_construct(**{**A1_TERMS.model_dump(), "strike": Decimal("-1")})


def _assert_refusal(outcome: PricingOutcome, reason: str, q: str | float) -> None:
    assert outcome.supported is False and outcome.reason == reason
    assert all(field is None for field in (
        outcome.model, outcome.price, outcome.greeks, outcome.regime,
        outcome.iv, outcome.sigma_source,
    ))
    assert tuple(outcome.inputs_echo) == _ECHO_FIELDS
    assert outcome.inputs_echo["dividend_yield"] == q


@pytest.mark.parametrize(("changes", "reason", "q"), [
    ({"contract": _EURO}, "american_bridge:not_american", _UNRESOLVED),
    ({"contract": CALL.model_copy(update={"exercise_style": ExerciseStyle.UNKNOWN})},
     "unknown_exercise_style", _UNRESOLVED),
    ({"carry": None}, _MISSING_CARRY, _UNRESOLVED),
    ({"terms": _terms(AdjustmentPolicy.PROTECTED)}, "carry:dividend_double_count", _UNRESOLVED),
    ({"terms": A2_TERMS}, "carry:strike_adjustment_unknown", _UNRESOLVED),
    ({"carry": YIELD.model_copy(update={"symbol": "OUTRA"})}, _MISSING_CARRY, _UNRESOLVED),
    ({"terms": _INVALID}, "american_bridge:invalid_terms_or_carry", _UNRESOLVED),
    ({"contract": _OTHER_STRIKE}, _MISMATCH, 0.08),
    ({"contract": CALL.model_copy(update={"symbol": "OUTRA"})}, _MISMATCH, 0.08),
    ({"contract": CALL.model_copy(update={"contract_size": 1})}, _MISMATCH, 0.08),
    ({"contract": CALL.model_copy(update={"quotation_form": 1000})}, _MISMATCH, 0.08),
    ({"sigma": 0.0}, "binomial:zero_volatility", 0.08),
    ({"sigma": 1}, "binomial:invalid_input_type", 0.08),
    ({"sigma": float("nan")}, "binomial:non_finite_input", 0.08),
    ({"steps": 0}, "binomial:invalid_steps", 0.08),
    ({"steps": 5000}, "binomial:invalid_steps", 0.08),
    ({"steps": 10**400}, "binomial:invalid_steps", 0.08),
    ({"spot": Decimal("sNaN")}, "binomial:non_finite_input", 0.08),
    ({"spot": Decimal("0")}, "binomial:input_out_of_domain", 0.08),
    ({"sigma": 0.001, "rate_cont": 0.9}, "binomial:probability_out_of_range", 0.08),
    ({"terms": SeriesTerms.model_construct(**{**A1_TERMS.model_dump(), "currency": None})},
     "terms:unknown_currency", _UNRESOLVED),
    ({"terms": A1_TERMS.model_copy(update={"exercise_style": ExerciseStyle.EUROPEAN})},
     _MISMATCH, 0.08),
], ids=[
    "european", "unknown", "missing-carry", "double-count", "unknown-policy", "foreign-carry",
    "invalid-terms", "strike", "symbol", "lot", "quotation", "zero-sigma", "int-sigma", "nan",
    "zero-steps", "n1-limit", "huge-steps", "snan-spot", "zero-spot", "probability",
    "terms-refusal", "terms-style",
])
def test_t4_refusal(changes: _Changes, reason: str, q: str | float) -> None:
    """Uma linha por recusa, incluindo o motivo original e a etapa de resolução do carry."""
    assumptions: dict[str, str | float | bool] = {"dividend_yield": 0.0, "calendar_id": "synthetic"}
    outcome = _price(assumptions=assumptions.copy(), **changes)
    _assert_refusal(outcome, reason, q)
    assert outcome.assumptions == assumptions


@pytest.mark.parametrize(("changes", "reason", "q"), [
    ({"contract": _EURO, "carry": None}, "american_bridge:not_american", _UNRESOLVED),
    ({"contract": _OTHER_STRIKE, "carry": None}, _MISSING_CARRY, _UNRESOLVED),
    ({"contract": _OTHER_STRIKE, "sigma": 0.0}, _MISMATCH, 0.08),
])
def test_t5_precedence(changes: _Changes, reason: str, q: str | float) -> None:
    """A primeira precondição que falha determina a recusa."""
    _assert_refusal(_price(**changes), reason, q)


def test_t6_optional_lot_and_quotation() -> None:
    """Com lote e fator ausentes no contrato, os termos permitem o mesmo preço de A1."""
    missing = CALL.model_copy(update={"contract_size": None, "quotation_form": None})
    outcome = _price(missing)
    assert outcome.supported and outcome == _price()


@pytest.mark.parametrize(("spot", "expected", "steps"), [
    (Decimal("120"), Decimal("20.0"), 200),
    (Decimal("1e308"), Decimal("1e308"), 4999),
])
def test_t7_expiry(spot: Decimal, expected: Decimal, steps: int) -> None:
    """No vencimento, as duas árvores e sua média devolvem o intrínseco."""
    expiry = replace(TTE, business_days=0, year_fraction=0.0, is_expiry_day=True)
    outcome = _price(spot=spot, steps=steps, tte=expiry)
    assert outcome.supported and outcome.price == expected and outcome.regime == "expiry"
    assert outcome.assumptions["early_exercise_premium"] == 0.0


def test_t8_no_premium() -> None:
    """Call protegida sem rendimento e com taxa positiva não tem prêmio de exercício."""
    outcome = _price(terms=_terms(AdjustmentPolicy.PROTECTED), carry=NONE, rate_cont=0.13)
    assert outcome.supported and outcome.price is not None
    premium = outcome.assumptions["early_exercise_premium"]
    assert isinstance(premium, float) and abs(premium) <= 1e-11 * max(1.0, float(outcome.price))


@pytest.mark.parametrize(("kind", "strike", "rate", "q", "sigma", "years", "reference"), [
    (OptionKind.CALL, 90, 0.13, "0.13", 0.25, 0.25, "11.0944"),
    (OptionKind.CALL, 100, 0.13, "0.13", 0.25, 0.25, "4.8565"),
    (OptionKind.CALL, 110, 0.13, "0.13", 0.25, 0.25, "1.6336"),
    (OptionKind.CALL, 90, 0.05, "0.10", 0.20, 1.00, "11.3127"),
    (OptionKind.CALL, 100, 0.05, "0.10", 0.20, 1.00, "5.9283"),
    (OptionKind.CALL, 110, 0.05, "0.10", 0.20, 1.00, "2.8874"),
    (OptionKind.CALL, 90, 0.13, "0.06", 0.40, 1.00, "22.5981"),
    (OptionKind.CALL, 100, 0.13, "0.06", 0.40, 1.00, "17.8341"),
    (OptionKind.CALL, 110, 0.13, "0.06", 0.40, 1.00, "13.9470"),
    (OptionKind.PUT, 90, 0.13, None, 0.25, 0.25, "0.8434"),
    (OptionKind.PUT, 100, 0.13, None, 0.25, 0.25, "3.7929"),
    (OptionKind.PUT, 110, 0.13, None, 0.25, 0.25, "10.3163"),
])
def test_t9_discretization(kind: OptionKind, strike: int, rate: float, q: str | None,
                           sigma: float, years: float, reference: str) -> None:
    """Mede o erro a 400 passos contra os doze valores de alta resolução do cartão."""
    policy = AdjustmentPolicy.UNKNOWN if q is None else AdjustmentPolicy.UNPROTECTED
    terms = _terms(policy, Decimal(strike))
    contract = CALL.model_copy(update={"kind": kind, "strike": Decimal(strike)})
    outcome = _price(
        contract, terms=terms, carry=_carry(q), rate_cont=rate, sigma=sigma,
        tte=replace(TTE, year_fraction=years, business_days=int(252 * years)), steps=400,
    )
    assert outcome.supported and outcome.price is not None
    assert abs(outcome.price - Decimal(reference)) <= Decimal("0.01")


@pytest.mark.parametrize(("changes", "field", "reason"), [
    ({"sigma": 10**400}, "sigma", "binomial:invalid_input_type"),
    ({"sigma": None}, "sigma", "binomial:invalid_input_type"),
    ({"rate_cont": 10**400}, "rate_cont", "binomial:invalid_input_type"),
    ({"rate_cont": None}, "rate_cont", "binomial:invalid_input_type"),
    ({"steps": None}, "steps", "binomial:invalid_steps"),
    ({"steps": "a"}, "steps", "binomial:invalid_steps"),
    ({"spot": 100.0}, "spot", "american_bridge:invalid_spot_type"),
], ids=["sigma-huge", "sigma-none", "rate-huge", "rate-none", "steps-none", "steps-text",
        "float-spot"])
def test_f1_bad_input(changes: _Changes, field: str, reason: str) -> None:
    outcome = _price(**changes)
    _assert_refusal(outcome, reason, 0.08)
    assert outcome.inputs_echo[field] == "invalid"


class _BridgeChanges(_Changes, total=False):
    tte: TimeToExpiry


@pytest.mark.parametrize(("changes", "field", "reason"), [
    ({"sigma": "0.2"}, "sigma", "binomial:invalid_input_type"),
    ({"sigma": True}, "sigma", "binomial:invalid_input_type"),
    ({"sigma": Decimal("0.2")}, "sigma", "binomial:invalid_input_type"),
    ({"sigma": 1}, "sigma", "binomial:invalid_input_type"),
    ({"steps": True}, "steps", "binomial:invalid_steps"),
    ({"steps": 2.5}, "steps", "binomial:invalid_steps"),
    ({"steps": 10**400}, "steps", "binomial:invalid_steps"),
    ({"tte": replace(TTE, year_fraction=None)}, "time_years", "binomial:invalid_input_type"),
    ({"spot": None}, "spot", "american_bridge:invalid_spot_type"),
    ({"spot": "100"}, "spot", "american_bridge:invalid_spot_type"),
], ids=["sigma-text", "sigma-bool", "sigma-decimal", "sigma-int", "steps-bool", "steps-float",
        "steps-overflow", "years-none", "spot-none", "spot-text"])
def test_f2_echo_requires_exact_type(changes: _BridgeChanges, field: str, reason: str) -> None:
    outcome = _price(**changes)
    _assert_refusal(outcome, reason, 0.08)
    assert outcome.inputs_echo[field] == "invalid"


class _HostileType(type):
    def __eq__(self, other: object) -> bool:
        raise AssertionError("comparou o tipo da entrada")

    __hash__ = type.__hash__


class _Hostile(metaclass=_HostileType):
    def __float__(self) -> float:
        raise AssertionError("converteu a entrada")

    def __eq__(self, other: object) -> bool:
        raise AssertionError("comparou a entrada")


class _ForeignFloat(_Hostile, float):
    pass


class _ForeignInt(_Hostile, int):
    def __add__(self, other: object) -> int:
        raise AssertionError("somou antes da recusa do binomial")


class _ForeignDecimal(_Hostile, Decimal):
    def is_snan(self) -> bool:
        raise AssertionError("consultou a subclasse de Decimal")


@pytest.mark.parametrize(("changes", "field", "reason"), [
    ({"sigma": _Hostile()}, "sigma", "binomial:invalid_input_type"),
    ({"rate_cont": _ForeignFloat(0.05)}, "rate_cont", "binomial:invalid_input_type"),
    ({"tte": replace(TTE, year_fraction=_ForeignFloat(1))}, "time_years",
     "binomial:invalid_input_type"),
    ({"steps": _ForeignInt(200)}, "steps", "binomial:invalid_steps"),
    ({"spot": _ForeignDecimal("100")}, "spot", "american_bridge:invalid_spot_type"),
], ids=["float-hook", "float-subclass", "years-subclass", "int-subclass", "decimal-subclass"])
def test_f2_hostile_inputs(changes: _BridgeChanges, field: str, reason: str) -> None:
    outcome = _price(**changes)
    _assert_refusal(outcome, reason, 0.08)
    assert outcome.inputs_echo[field] == "invalid"


@pytest.mark.parametrize(("changes", "field", "expected"), [
    ({"spot": Decimal("sNaN")}, "spot", "nan"),
    ({"sigma": float("nan")}, "sigma", "nan"),
    ({"rate_cont": float("-inf")}, "rate_cont", "-inf"),
    ({"tte": replace(TTE, year_fraction=float("inf"))}, "time_years", "inf"),
])
def test_f2_exact_nonfinite_echo(changes: _BridgeChanges, field: str, expected: str) -> None:
    outcome = _price(**changes)
    _assert_refusal(outcome, "binomial:non_finite_input", 0.08)
    value = outcome.inputs_echo[field]
    assert type(value) is float and value.hex() == expected


_INVALID_SIGMA = _Hostile()
_INVALID_RATE = _ForeignFloat(0.05)
_INVALID_YEARS = _ForeignFloat(1)
_INVALID_STEPS = _ForeignInt(200)
_INVALID_TYPE = "binomial:invalid_input_type"


@pytest.mark.parametrize(("changes", "field", "sentinel", "reason"), [
    ({"sigma": _INVALID_SIGMA}, "sigma", _INVALID_SIGMA, _INVALID_TYPE),
    ({"rate_cont": _INVALID_RATE}, "rate_cont", _INVALID_RATE, _INVALID_TYPE),
    ({"tte": replace(TTE, year_fraction=_INVALID_YEARS)},
     "time_years", _INVALID_YEARS, _INVALID_TYPE),
    ({"steps": _INVALID_STEPS}, "steps", _INVALID_STEPS, "binomial:invalid_steps"),
], ids=["sigma", "rate", "years", "steps"])
def test_f2_invalid_inputs_reach_binomial_once(monkeypatch: pytest.MonkeyPatch,
                                               changes: _BridgeChanges, field: str,
                                               sentinel: object, reason: str) -> None:
    from unittest.mock import Mock

    tree = Mock(wraps=crr_price)
    monkeypatch.setattr("backend.derivatives.pricing.american_bridge.crr_price", tree)
    _assert_refusal(_price(**changes), reason, 0.08)
    tree.assert_called_once()
    assert tree.call_args.kwargs[field] is sentinel


@pytest.mark.parametrize(("changes", "reason", "q", "field"), [
    ({"contract": _EURO, "sigma": None}, "american_bridge:not_american", _UNRESOLVED, "sigma"),
    ({"carry": None, "spot": 100.0}, _MISSING_CARRY, _UNRESOLVED, "spot"),
    ({"contract": _OTHER_STRIKE, "spot": 100.0}, _MISMATCH, 0.08, "spot"),
    ({"sigma": None, "steps": None}, "binomial:invalid_input_type", 0.08, "sigma"),
], ids=["style", "carry", "terms-mismatch", "binomial-type-before-steps"])
def test_f3_first_refusal(changes: _Changes, reason: str, q: str | float, field: str) -> None:
    outcome = _price(**changes)
    _assert_refusal(outcome, reason, q)
    assert outcome.inputs_echo[field] == "invalid"


@pytest.mark.parametrize(("contract", "terms", "carry", "kind", "policy", "carry_kind", "q",
                          "price", "first", "second", "european", "premium"), [
    (CALL, A1_TERMS, YIELD, "CALL", "UNPROTECTED", "CONTINUOUS_YIELD", 0.08,
     "6.543803959785978", 6.537469676838961, 6.550138242732996, 6.142744211943331,
     0.4010597478426474),
    (PUT, A2_TERMS, NONE, "PUT", "UNKNOWN", "NONE", 0.0,
     "6.091951932388676", 6.086382749916067, 6.097521114861286, 5.572892044256312,
     0.5190598881323645),
], ids=["A1", "A2"])
def test_f4_complete_anchor(contract: OptionContract, terms: SeriesTerms, carry: CarryAssumption,
                            kind: str, policy: str, carry_kind: str, q: float, price: str,
                            first: float, second: float, european: float, premium: float) -> None:
    expected = PricingOutcome(
        supported=True, reason=None, model="crr_american_v1", price=Decimal(price), greeks=None,
        regime="tree", iv=None, sigma_source="given",
        inputs_echo={
            "symbol": "XPTO1", "kind": kind, "exercise_style": "AMERICAN",
            "spot": 100.0, "strike": 100.0, "time_years": 1.0, "rate_cont": 0.05, "sigma": 0.2,
            "dividend_yield": q, "steps": 200.0, "price_steps_n": first, "price_steps_n1": second,
            "european_same_trees": european,
        },
        assumptions={
            "carry_kind": carry_kind, "carry_dividend_yield": q, "carry_source": "test",
            "carry_effective_on": "2026-11-19", "strike_adjustment_policy": policy,
            "pricing_model": "crr_american_v1", "crr_steps": 200.0, "crr_pair_average": True,
            "early_exercise_premium": premium,
        },
    )
    outcome = _price(contract, terms=terms, carry=carry)
    assert outcome == expected
    assert outcome.model_dump_json() == expected.model_dump_json()


@pytest.mark.parametrize(("lot", "quotation"), [(None, 1000), (1, None)])
def test_f5_present_term_still_must_match(lot: int | None, quotation: int | None) -> None:
    contract = CALL.model_copy(update={"contract_size": lot, "quotation_form": quotation})
    _assert_refusal(_price(contract), _MISMATCH, 0.08)


def test_f5_currency_precedes_missing_carry() -> None:
    terms = SeriesTerms.model_construct(**{**A1_TERMS.model_dump(), "currency": None})
    _assert_refusal(_price(terms=terms, carry=None), "terms:unknown_currency", _UNRESOLVED)


def test_f5_steps_required() -> None:
    with pytest.raises(TypeError, match="missing 1 required keyword-only argument: 'steps'"):
        price_american_contract(
            CALL, terms=A1_TERMS, carry=YIELD, spot=Decimal("100"), rate_cont=0.05,
            sigma=0.2, tte=TTE, assumptions={},
        )
