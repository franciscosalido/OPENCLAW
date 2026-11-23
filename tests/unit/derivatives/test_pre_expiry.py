"""Contas de mesa J1–J7 e preços das pontes K1–K4 do DL3-PR08D."""
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import MAX_EMAX, Decimal as D, localcontext

import pytest

from backend.derivatives.domain.carry import CarryAssumption, CarryKind
from backend.derivatives.domain.models import ExerciseStyle, OptionContract, OptionKind
from backend.derivatives.domain.series_terms import (
    AdjustmentEvidence, AdjustmentPolicy, SeriesTerms,
)
from backend.derivatives.pricing.american_bridge import price_american_contract
from backend.derivatives.pricing.contract_pricing import PricingOutcome, price_contract
from backend.derivatives.pricing.conventions import TimeToExpiry
from backend.derivatives.pricing.expiry_payoff import ExpiryLeg, PayoffRefusal, expiry_result
from backend.derivatives.pricing.pre_expiry import PreExpiryEstimate, pre_expiry_estimate
from config.derivatives_config_model import Conventions


def butterfly(kind="CALL", size=1):
    premiums = ("7.00", "3.50", "2.00") if kind == "CALL" else ("2.00", "3.50", "7.00")
    return [ExpiryLeg(kind, side, D(k), n * size, D(p)) for side, k, n, p in
            zip(("BUY", "SELL", "BUY"), (95, 100, 105), (1, 2, 1), premiums, strict=True)]


def declared(legs, prices=("7.40", "3.90", "1.90")):
    return [PricingOutcome(supported=True, reason=None, model="declarado", price=D(p),
                           greeks=None, regime=None, assumptions={},
                           inputs_echo={"kind": leg.kind, "strike": float(leg.strike),
                                        "spot": 101.0, "time_years": 0.25})
            for leg, p in zip(legs, prices, strict=True)]


def test_j1_call_butterfly_keeps_leg_order_and_original_outcomes():
    legs = butterfly()
    prices = declared(legs)
    est = pre_expiry_estimate(legs, prices)
    assert isinstance(est, PreExpiryEstimate)
    assert (est.net_entry, est.theoretical_value, est.result) == (D(2), D("1.50"), D("-0.50"))
    assert est.leg_results == (D("0.40"), D("-0.80"), D("-0.10"))
    assert isinstance(est.outcomes, tuple)
    assert all(a is b for a, b in zip(est.outcomes, prices, strict=True))
    prices.clear()
    assert len(est.outcomes) == 3
    with pytest.raises((AttributeError, FrozenInstanceError)):
        est.result = D(0)


def test_j2_quantity_multiplier_and_one_fixed_cost():
    legs = butterfly(size=10)
    with localcontext() as ctx:
        ctx.prec = 2
        est = pre_expiry_estimate(legs, declared(legs), multiplier=100, costs=D("12.50"))
    assert (est.net_entry, est.theoretical_value, est.result) == (D(2000), D(1500), D("-512.50"))
    assert est.leg_results == (D(400), D(-800), D(-100))


def test_j3_credit_iron_condor():
    legs = [ExpiryLeg("PUT", "BUY", D(90), 1, D(1)),
            ExpiryLeg("PUT", "SELL", D(95), 1, D("2.50")),
            ExpiryLeg("CALL", "SELL", D(105), 1, D("2.50")),
            ExpiryLeg("CALL", "BUY", D(110), 1, D(1))]
    est = pre_expiry_estimate(legs, declared(legs, ("0.60", "1.70", "1.80", "0.70")))
    assert (est.net_entry, est.theoretical_value, est.result) == (D(-3), D("-2.20"), D("0.80"))
    assert est.leg_results == (D("-0.40"), D("0.80"), D("0.70"), D("-0.30"))


def test_j4_seventeen_digits_survive_a_two_digit_context():
    legs = [ExpiryLeg("CALL", "BUY", D(100), 7, D("3.50"))]
    with localcontext() as ctx:
        ctx.prec = 2
        est = pre_expiry_estimate(legs, declared(legs, ("3.2457812345678912",)), multiplier=100)
    assert est.net_entry == D(2450)
    assert est.theoretical_value == D("2272.04686419752384")
    assert est.result == D("-177.95313580247616")
    assert est.leg_results == (D("-177.95313580247616"),)


def test_j5_default_and_explicit_leg_limits():
    legs = [ExpiryLeg("CALL", "BUY", D(100), 1, D(5))] * 9
    prices = declared(legs, ["5.50"] * 9)
    with pytest.raises(PayoffRefusal):
        pre_expiry_estimate(legs, prices)
    assert pre_expiry_estimate(legs[:8], prices[:8]).result == D(4)
    assert pre_expiry_estimate(legs, prices, max_legs=9).result == D("4.50")
    assert pre_expiry_estimate(legs[:1] * 64, prices[:1] * 64, max_legs=64).result == D(32)


@pytest.mark.parametrize("kwargs", [
    {"max_legs": n} for n in (0, 65, True, 8.0)
] + [{"multiplier": 0}, {"multiplier": True}, {"costs": D(-1)}, {"costs": 1.5},
     {"costs": D("NaN")}])
def test_j5_j6_invalid_controls(kwargs):
    legs = butterfly()
    with pytest.raises(PayoffRefusal):
        pre_expiry_estimate(legs, declared(legs), **kwargs)


@pytest.mark.parametrize("change", [
    lambda l, p: (l, p[:2]), lambda l, p: (l[:2], p), lambda l, p: ([], []),
    lambda l, p: (l, []), lambda l, p: (l, [p[0], None, p[2]]),
    lambda l, p: ([None, *l[1:]], p), lambda l, p: (iter(l), p), lambda l, p: (l, iter(p)),
])
def test_j6_refuses_invalid_collections(change):
    legs = butterfly()
    with pytest.raises(PayoffRefusal):
        pre_expiry_estimate(*change(legs, declared(legs)))


@pytest.mark.parametrize("key,value", [
    ("price", None), ("price", D("-0.01")), ("kind", "PUT"), ("strike", 101.0),
    ("spot", 102.0), ("time_years", 0.5),
])
def test_j6_refuses_bad_mark_or_inconsistent_echo(key, value):
    legs = butterfly()
    prices = declared(legs)
    update = {"price": value} if key == "price" else {"inputs_echo": {
        **prices[1].inputs_echo, key: value}}
    prices[1] = prices[1].model_copy(update=update)
    with pytest.raises(PayoffRefusal):
        pre_expiry_estimate(legs, prices)


@pytest.mark.parametrize("key", ["spot", "time_years"])
def test_common_reference_must_be_present_even_for_one_leg(key):
    legs = butterfly()[:1]
    prices = declared(legs, ("1",))
    prices[0].inputs_echo.pop(key)
    with pytest.raises(PayoffRefusal):
        pre_expiry_estimate(legs, prices)


def test_unrepresentable_result_is_a_typed_refusal():
    legs = butterfly()[:1]
    prices = declared(legs, (D((0, (9,), MAX_EMAX)),))
    with pytest.raises(PayoffRefusal):
        pre_expiry_estimate(legs, prices, multiplier=10)


def test_j7_bridge_refusal_with_a_price_preserves_reason_and_leg_number():
    legs = butterfly()
    prices = declared(legs)
    prices[1] = prices[1].model_copy(update={"supported": False, "reason": "iv_unavailable:x"})
    with pytest.raises(PayoffRefusal) as error:
        pre_expiry_estimate(legs, prices)
    assert "perna 2" in str(error.value) and "iv_unavailable:x" in str(error.value)


TTE = TimeToExpiry(21, 21 / 252, "synthetic", "test", 252, False)
EXPIRY = TimeToExpiry(0, 0.0, "synthetic", "test", 252, True)


def bridge(leg, spot, tte, *, wrong_engine=False):
    symbol = f"XPTO-{leg.kind}-{leg.strike}"
    american = leg.kind == "CALL"
    style = ExerciseStyle.AMERICAN if american else ExerciseStyle.EUROPEAN
    day = date(2026, 11, 23)
    contract = OptionContract(symbol=symbol, underlying="XPTO", kind=OptionKind(leg.kind),
                              exercise_style=style, strike=leg.strike, expiry=date(2026, 12, 22),
                              contract_size=100, quotation_form=1, isin=None)
    if wrong_engine or not american:
        return price_contract(contract, spot=D(spot), tte=tte, rate_cont=0.10, sigma=0.30,
                              cfg=Conventions(), assumptions={})
    policy = AdjustmentPolicy.PROTECTED
    evidence = AdjustmentEvidence(issuer="B3", document="synthetic", version="1", published_on=day,
                                  symbol=symbol, effective_on=day, policy=policy)
    terms = SeriesTerms(symbol=symbol, effective_on=day, source="synthetic", strike=leg.strike,
                        contract_size=100, quotation_form=1, exercise_style=style, currency="BRL",
                        adjustment_policy=policy, evidence=evidence)
    carry = CarryAssumption(symbol=symbol, effective_on=day, source="synthetic",
                            kind=CarryKind.NONE)
    return price_american_contract(contract, terms=terms, carry=carry, spot=D(spot), tte=tte,
                                   rate_cont=0.10, sigma=0.30, steps=200, assumptions={})


@pytest.mark.parametrize("kind,model,prices,result", [
    ("CALL", "crr_american_v1", ("7.013498439", "3.870317449", "1.838002754"), "-0.889133705"),
    ("PUT", "bsm_european_v1", ("1.223926336", "3.040496887", "5.966987738"), "-0.890079700"),
])
def test_k1_k2_real_bridge_marks(kind, model, prices, result):
    legs = butterfly(kind)
    marks = [bridge(leg, 100, TTE) for leg in legs]
    est = pre_expiry_estimate(legs, marks)
    for mark, expected in zip(est.outcomes, prices, strict=True):
        assert mark.model == model and abs(mark.price - D(expected)) <= D("1e-8")
    assert est.net_entry == D(2)
    assert abs(est.result - D(result)) <= D("1e-8")
    assert est.result == est.theoretical_value - est.net_entry


@pytest.mark.parametrize("kind", ["CALL", "PUT"])
@pytest.mark.parametrize("spot", [90, 95, 100, 105, 110])
def test_k3_at_expiry_matches_terminal_payoff_exactly(kind, spot):
    legs = butterfly(kind)
    est = pre_expiry_estimate(legs, [bridge(leg, spot, EXPIRY) for leg in legs])
    assert est.result == expiry_result(legs, D(spot))


def test_k4_european_bridge_refuses_the_american_body():
    legs = butterfly()
    marks = [bridge(leg, 100, TTE, wrong_engine=(i == 1)) for i, leg in enumerate(legs)]
    assert [mark.supported for mark in marks] == [True, False, True]
    with pytest.raises(PayoffRefusal, match="perna 2"):
        pre_expiry_estimate(legs, marks)


def test_exact_mark_beyond_decimal128_precision():
    legs = [ExpiryLeg("CALL", "BUY", D(100), 1, D(0))]
    price = D("1.234567890123456789012345678901234567")
    with localcontext() as ctx:
        ctx.prec = 2
        est = pre_expiry_estimate(legs, declared(legs, (price,)))
    assert (est.theoretical_value, est.result, est.leg_results) == (price, price, (price,))


@pytest.mark.parametrize("key", ["spot", "time_years"])
def test_common_infinite_reference_is_refused(key):
    legs = butterfly()
    marks = declared(legs)
    for mark in marks:
        mark.inputs_echo[key] = float("inf")
    with pytest.raises(PayoffRefusal):
        pre_expiry_estimate(legs, marks)


def test_unreadable_sequence_reports_domain_refusal():
    unreadable = memoryview(b"abcd").cast("B", shape=(2, 2))
    with pytest.raises(PayoffRefusal):
        pre_expiry_estimate(unreadable, [])
