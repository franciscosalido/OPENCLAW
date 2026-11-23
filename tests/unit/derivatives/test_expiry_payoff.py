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


def test_refuse_oversized_sequence_without_materializing_it():
    with pytest.raises(PayoffRefusal):
        expiry_profile(range(2**100))


def test_cancelling_legs_preserve_representable_total_at_decimal_exponent_limit():
    from decimal import MAX_EMAX

    unit = D((0, (1,), MAX_EMAX))
    spot = D((0, (3,), MAX_EMAX))
    positions = (leg("CALL", "BUY", unit, 10, unit), leg("CALL", "SELL", unit, 10, unit))
    assert expiry_result(positions, spot) == D(0)
    with localcontext() as ctx:
        from decimal import InvalidOperation
        ctx.traps[InvalidOperation] = False
        with pytest.raises(PayoffRefusal):
            expiry_leg_results(positions, spot)


def test_neutral_pair_inside_zero_interval_has_no_extra_breakeven():
    legs = (leg("CALL", "BUY", 100, 1, 5), leg("CALL", "SELL", 105, 1, 5),
            leg("CALL", "BUY", 95, 1, 1), leg("CALL", "SELL", 95, 1, 1))
    assert expiry_profile(legs).breakevens == (F(0), F(100))


def test_p9_unreadable_sequence_is_a_typed_refusal():
    values = memoryview(b"abcd").cast("B", shape=(2, 2))
    with pytest.raises(PayoffRefusal):
        expiry_profile(values)


@pytest.mark.parametrize("func,args", [
    (expiry_leg_results, (D(100),)), (expiry_result, (D(100),)), (expiry_profile, ()),
])
def test_e10_explicit_leg_budget_and_default(func, args):
    options = [leg("CALL", "BUY", 100, 1, 5)] * 9
    with pytest.raises(PayoffRefusal):
        func(options, *args)
    result = func(options, *args, max_legs=9)
    if func is expiry_profile:
        assert result.net_entry == D(45)
    elif func is expiry_result:
        assert result == D(-45)
    else:
        assert result == (D(-5),) * 9
    for invalid in (0, 65, True, 8.0):
        with pytest.raises(PayoffRefusal):
            func(options[:1], *args, max_legs=invalid)
    with pytest.raises(PayoffRefusal):
        func(options[:2], *args, max_legs=1)


def test_e10_eight_legs_are_accepted_by_default_in_all_three_functions():
    legs = [leg("CALL", "BUY", 100, 1, 5)] * 8
    assert expiry_leg_results(legs, D(100)) == (D(-5),) * 8
    assert expiry_result(legs, D(100)) == D(-40)
    assert expiry_profile(legs).net_entry == D(40)


def put_butterfly(wing=1, body=2):
    return (leg("PUT", "BUY", 95, wing, "2.00"), leg("PUT", "SELL", 100, body, "3.50"),
            leg("PUT", "BUY", 105, wing, "7.00"))


def iron_condor(quantity=1):
    return (leg("PUT", "BUY", 90, quantity, "1.00"), leg("PUT", "SELL", 95, quantity, "2.50"),
            leg("CALL", "SELL", 105, quantity, "2.50"), leg("CALL", "BUY", 110, quantity, "1.00"))


@pytest.mark.parametrize("legs,multiplier,cost,entry,roots,gain,loss,points", [
    pytest.param(put_butterfly(), 1, "0", "2", (F(97), F(103)), "3", "-2",
                 [(90, -2), (95, -2), (97, 0), (100, 3), (103, 0), (105, -2), (110, -2)],
                 id="G1-put-butterfly"),
    pytest.param((leg("CALL", "BUY", 100, 1, 5), leg("CALL", "SELL", 105, 1, 3)),
                 1, "0", "2", (F(102),), "3", "-2",
                 [(95, -2), (100, -2), (102, 0), (105, 3), (110, 3)], id="G2-bull-call"),
    pytest.param((leg("CALL", "SELL", 100, 1, 5), leg("CALL", "BUY", 105, 1, 3)),
                 1, "0", "-2", (F(102),), "2", "-3",
                 [(95, 2), (100, 2), (102, 0), (105, -3), (110, -3)], id="G3-bear-call"),
    pytest.param((leg("PUT", "SELL", 100, 1, 4), leg("PUT", "BUY", 95, 1, "2.50")),
                 1, "0", "-1.50", (F(197, 2),), "1.50", "-3.50",
                 [(90, "-3.50"), (95, "-3.50"), (100, "1.50"), (105, "1.50")], id="G4-bull-put"),
    pytest.param((leg("PUT", "BUY", 100, 1, 4), leg("PUT", "SELL", 95, 1, "2.50")),
                 1, "0", "1.50", (F(197, 2),), "3.50", "-1.50",
                 [(90, "3.50"), (95, "3.50"), (100, "-1.50"), (105, "-1.50")], id="G5-bear-put"),
    pytest.param(iron_condor(), 1, "0", "-3", (F(92), F(108)), "3", "-2",
                 [(85, -2), (90, -2), (92, 0), (95, 3), (100, 3), (105, 3), (108, 0),
                  (110, -2), (115, -2)], id="G6-iron-condor"),
    pytest.param(iron_condor(10), 100, "37.60", "-3000", (F(115047, 1250), F(134953, 1250)),
                 "2962.40", "-2037.60", [(85, "-2037.60"), (90, "-2037.60"), (100, "2962.40"),
                                         (110, "-2037.60"), (115, "-2037.60")], id="G7-scaled"),
    pytest.param(put_butterfly(3, 6), 100, "9.90", "600", (F(97033, 1000), F(102967, 1000)),
                 "890.10", "-609.90", [(95, "-609.90"), (100, "890.10"), (105, "-609.90")],
                 id="G8-scaled"),
])
def test_structure_at_expiry(legs, multiplier, cost, entry, roots, gain, loss, points):
    assert profile_values(expiry_profile(legs, multiplier=multiplier, costs=D(cost))) == (
        D(entry), roots, D(gain), D(loss), False, False)
    for spot, expected in points:
        assert expiry_result(legs, D(spot), multiplier=multiplier, costs=D(cost)) == D(expected)


@pytest.mark.parametrize("legs,multiplier,spot,expected", [
    pytest.param(put_butterfly(), 1, 100, (-2, 7, -2), id="G1-body"),
    pytest.param(put_butterfly(), 1, 90, (3, -13, 8), id="G1-below"),
    pytest.param(iron_condor(), 1, 100, (-1, "2.50", "2.50", -1), id="G6-middle"),
    pytest.param(iron_condor(), 1, 85, (4, "-7.50", "2.50", -1), id="G6-below"),
    pytest.param(iron_condor(), 1, 115, (-1, "2.50", "-7.50", 4), id="G6-above"),
    pytest.param(iron_condor(10), 100, 100, (-1000, 2500, 2500, -1000), id="G7-scaled"),
])
def test_leg_results_before_costs_in_plan_order(legs, multiplier, spot, expected):
    assert expiry_leg_results(legs, D(spot), multiplier=multiplier) == tuple(map(D, expected))
