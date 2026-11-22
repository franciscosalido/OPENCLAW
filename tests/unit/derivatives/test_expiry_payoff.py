"""Provas de mesa para o resultado no vencimento, por unidade monetária."""
from dataclasses import FrozenInstanceError
from decimal import Decimal as D, localcontext
from fractions import Fraction as F

import pytest

from backend.derivatives.pricing.expiry_payoff import (
    ExpiryLeg, PayoffRefusal, expiry_leg_results, expiry_profile, expiry_result,
)


def leg(kind, side, strike, quantity, premium):
    return ExpiryLeg(kind, side, D(strike), quantity, D(premium))


def butterfly(size=1):
    return (leg("CALL", "BUY", 95, size, "7.00"), leg("CALL", "SELL", 100, 2 * size, "3.50"),
            leg("CALL", "BUY", 105, size, "2.00"))


def profile_values(profile):
    return (profile.net_entry, profile.breakevens, profile.max_gain, profile.max_loss,
            profile.gain_unlimited, profile.loss_unlimited)


def test_p1_francisco_call_butterfly():
    legs = butterfly()
    assert tuple(expiry_result(legs, D(s)) for s in (90, 95, 96, 97, 100, 103, 104, 105, 110)) == (
        D(-2), D(-2), D(-1), D(0), D(3), D(0), D(-1), D(-2), D(-2))
    parts = expiry_leg_results(legs, D(100))
    assert parts == (D(-2), D(7), D(-2))
    assert all(isinstance(part, D) for part in parts)
    profile = expiry_profile(legs)
    assert profile_values(profile) == (D(2), (F(97), F(103)), D(3), D(-2), False, False)
    assert all(isinstance(point, F) for point in profile.breakevens)
    assert all(isinstance(x, D) for x in (profile.net_entry, profile.max_gain, profile.max_loss))
    with pytest.raises((AttributeError, FrozenInstanceError)):
        profile.net_entry = D(0)
    with pytest.raises((AttributeError, FrozenInstanceError)):
        legs[0].quantity = 8


def test_p2_scaled_butterfly_with_fixed_costs():
    legs = butterfly(10)
    with localcontext() as ctx:
        ctx.prec = 2
        results = tuple(expiry_result(legs, D(s), multiplier=100, costs=D("12.50"))
                        for s in (95, 100, 105))
        assert results == (D("-2012.50"), D("2987.50"), D("-2012.50"))
        assert profile_values(expiry_profile(legs, multiplier=100, costs=D("12.50"))) == (
            D(2000), (F(7761, 80), F(8239, 80)), D("2987.50"), D("-2012.50"), False, False)


@pytest.mark.parametrize("legs,spots,results,entry,roots,gain,loss", [
    pytest.param([leg("CALL", "BUY", 100, 1, 5)], [0, 90, 105, 120], [-5, -5, 0, 15],
                 5, [105], None, -5, id="P3-long-call"),
    pytest.param([leg("CALL", "SELL", 100, 1, 5)], [0, 100, 105, 120], [5, 5, 0, -15],
                 -5, [105], 5, None, id="P4-short-call"),
    pytest.param([leg("PUT", "SELL", 100, 1, 5)], [0, 95, 100, 120], [-95, 0, 5, 5],
                 -5, [95], 5, -95, id="P5-short-put"),
    pytest.param([leg("PUT", "BUY", 100, 1, 5)], [0, 95, 100, 120], [95, 0, -5, -5],
                 5, [95], 95, -5, id="P6-long-put"),
    pytest.param([leg("CALL", "BUY", 100, 1, 5), leg("CALL", "SELL", 105, 1, 5)],
                 [0, 100, 102, 105, 120], [0, 0, 2, 5, 5], 0, [0, 100], 5, 0, id="P7-plateau"),
    pytest.param([leg("CALL", "BUY", 100, 1, 5), leg("CALL", "SELL", 110, 2, 2)],
                 [90, 101, 110, 119, 130], [-1, 0, 9, 0, -11], 1, [101, 119], 9, None,
                 id="P8-ratio"),
])
def test_profiles(legs, spots, results, entry, roots, gain, loss):
    assert [expiry_result(legs, D(s)) for s in spots] == list(map(D, results))
    assert profile_values(expiry_profile(legs)) == (
        D(entry), tuple(map(F, roots)), None if gain is None else D(gain),
        None if loss is None else D(loss), gain is None, loss is None)


@pytest.mark.parametrize("args", [
    ("STOCK", "BUY", D(10), 1, D(1)), ("CALL", "HOLD", D(10), 1, D(1)),
    ("CALL", "BUY", D(0), 1, D(1)), ("CALL", "BUY", D(1), 0, D(1)),
    ("CALL", "BUY", D(1), True, D(1)), ("CALL", "BUY", D(1), 1, D(-1)),
    ("CALL", "BUY", 1.0, 1, D(0)), ("CALL", "BUY", D(1), 1, 0.5),
    ("PUT", "BUY", D("NaN"), 1, D(0)), ("PUT", "BUY", D(1), 1, D("Infinity")),
])
def test_p9_refuse_invalid_leg(args):
    with pytest.raises(PayoffRefusal):
        ExpiryLeg(*args)


@pytest.mark.parametrize("args,kwargs", [
    (([], D(0)), {}), ((butterfly() * 3, D(0)), {}), ((butterfly(), D(-1)), {}),
    ((butterfly(), 1.5), {}), ((butterfly(), D(0)), {"multiplier": 0}),
    ((butterfly(), D(0)), {"costs": D(-1)}), ((butterfly(), D(0)), {"costs": 1.5}),
    ((butterfly(), D("sNaN")), {}), (([None], D(0)), {}),
])
def test_p9_refuse_invalid_structure_or_spot(args, kwargs):
    with pytest.raises(PayoffRefusal):
        expiry_result(*args, **kwargs)


def test_net_call_quantity_is_independent_of_leg_order_and_last_side():
    legs = (leg("CALL", "SELL", 110, 2, 2), leg("CALL", "BUY", 100, 1, 5))
    assert profile_values(expiry_profile(legs)) == (D(1), (F(101), F(119)), D(9), None, False, True)


def test_fractional_tail_root_and_eight_legs():
    legs = (leg("CALL", "BUY", 10, 3, 1),)
    assert expiry_profile(legs, costs=D(1)).breakevens == (F(34, 3),)
    assert expiry_result(legs * 8, D(12)) == D(24)
