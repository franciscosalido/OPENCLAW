"""Perfis de vencimento das mesas E1–E9 do cartão DL3-PR08B."""
from dataclasses import FrozenInstanceError
from decimal import Decimal as D
from fractions import Fraction as F

import pytest

from backend.derivatives.pricing.expiry_payoff import ExpiryLeg, PayoffRefusal, expiry_result
from backend.derivatives.pricing.partial_position import Execution, PlannedLeg, partial_view


def call(side, strike, quantity, price):
    return ExpiryLeg("CALL", side, D(strike), quantity, D(price))


PLAN = (PlannedLeg("C95", call("BUY", 95, 1, 7)), PlannedLeg("C100", call("SELL", 100, 2, "3.50")),
        PlannedLeg("C105", call("BUY", 105, 1, 2)))


def trade(symbol, quantity, price):
    return Execution(symbol, quantity, D(price))


def profile(p):
    return p.net_entry, p.breakevens, p.max_gain, p.max_loss, p.gain_unlimited, p.loss_unlimited


def butterfly(*fills):
    view = partial_view(PLAN, fills)
    assert profile(view.planned) == (D(2), (F(97), F(103)), D(3), D(-2), False, False)
    return view


def spots(view, *prices):
    return tuple(expiry_result(view.executed_legs, D(s)) for s in prices)


def test_e1_nothing_executed():
    v = butterfly()
    assert v.executed is None and v.executed_legs == ()
    assert v.pending == (("C95", 1), ("C100", 2), ("C105", 1))
    with pytest.raises((FrozenInstanceError, AttributeError)):
        v.pending = ()


def test_e2_one_wing_and_half_the_body():
    v = butterfly(trade("C95", 1, 7), trade("C100", 1, "3.50"))
    assert profile(v.executed) == (D("3.50"), (F(197, 2),), D("1.50"), D("-3.50"), False, False)
    assert spots(v, 90, 100, 110) == (D("-3.50"), D("1.50"), D("1.50"))
    assert v.executed_legs == (call("BUY", 95, 1, 7), call("SELL", 100, 1, "3.50"))
    assert v.pending == (("C100", 1), ("C105", 1))


def test_e3_only_short_body_has_unlimited_loss():
    v = butterfly(trade("C100", 2, "3.50"))
    assert profile(v.executed) == (D(-7), (F(207, 2),), D(7), None, False, True)
    assert spots(v, 100, 110) == (D(7), D(-13))
    assert v.pending == (("C95", 1), ("C105", 1))


def test_e4_short_body_and_lower_wing():
    v = butterfly(trade("C95", 1, 7), trade("C100", 2, "3.50"))
    assert profile(v.executed) == (D(0), (F(0), F(95), F(105)), D(5), None, False, True)
    assert spots(v, 90, 100, 110) == (D(0), D(5), D(-5))
    assert v.pending == (("C105", 1),)


def test_e5_actual_prices_sorted_inside_plan_order():
    v = butterfly(trade("C105", 1, 2), trade("C100", 1, "3.60"), trade("C95", 1, "6.90"),
                  trade("C100", 1, "3.40"))
    assert v.executed_legs == (call("BUY", 95, 1, "6.90"), call("SELL", 100, 1, "3.40"),
                               call("SELL", 100, 1, "3.60"), call("BUY", 105, 1, 2))
    assert profile(v.executed) == (D("1.90"), (F(969, 10), F(1031, 10)),
                                   D("3.10"), D("-1.90"), False, False)
    assert spots(v, 95, 100, 105) == (D("-1.90"), D("3.10"), D("-1.90"))
    assert v.pending == ()


def test_e6_only_upper_wing_has_unlimited_gain():
    v = butterfly(trade("C105", 1, 2))
    assert profile(v.executed) == (D(2), (F(107),), None, D(-2), True, False)
    assert v.pending == (("C95", 1), ("C100", 2))


def test_e7_repeated_fill_price_accumulates():
    v = butterfly(trade("C100", 1, "3.50"), trade("C100", 1, "3.500"))
    assert v.executed_legs == (call("SELL", 100, 2, "3.50"),)
    assert profile(v.executed) == (D(-7), (F(207, 2),), D(7), None, False, True)
    assert v.pending == (("C95", 1), ("C105", 1))


def test_e8_nine_prices_one_symbol():
    plan = [PlannedLeg("L", call("BUY", 100, 9, 5))]
    prices = list(map(D, ("4.91", "4.92", "4.93", "4.94", "4.95", "4.96", "4.97", "4.98", "4.99")))
    v = partial_view(plan, [Execution("L", 1, p) for p in reversed(prices)])
    assert v.executed_legs == tuple(call("BUY", 100, 1, p) for p in prices)
    assert profile(v.executed) == (D("44.55"), (F(2099, 20),), None, D("-44.55"), True, False)
    assert profile(v.planned) == (D(45), (F(105),), None, D(-45), True, False)
    assert v.pending == ()


@pytest.mark.parametrize("action", [
    lambda: partial_view([], []),
    lambda: partial_view([PlannedLeg(str(n), PLAN[0].leg) for n in range(9)], []),
    lambda: partial_view([PLAN[0], PLAN[0]], []),
    lambda: PlannedLeg("", PLAN[0].leg),
    lambda: Execution("", 1, D(1)),
    lambda: partial_view(PLAN, [trade("UNKNOWN", 1, 1)]),
    lambda: partial_view(PLAN, [trade("C95", 2, 7)]),
    lambda: partial_view(PLAN, [trade("C95", 1, 7), trade("C95", 1, 6)]),
    lambda: Execution("C95", 0, D(1)), lambda: Execution("C95", True, D(1)),
    lambda: Execution("C95", 1, D(-1)), lambda: Execution("C95", 1, 3.5),
    lambda: Execution("C95", 1, D("NaN")), lambda: Execution("C95", 1, D("Infinity")),
    lambda: partial_view([PlannedLeg("L", call("BUY", 100, 65, 5))],
                         [trade("L", 1, p) for p in range(65)]),
    lambda: partial_view(PLAN, [object()]), lambda: partial_view(PLAN, [], multiplier=False),
    lambda: partial_view(PLAN, memoryview(b"abcd").cast("B", shape=(2, 2))),
])
def test_e9_invalid_inputs(action):
    with pytest.raises(PayoffRefusal):
        action()


def test_put_multiplier_same_price_on_two_symbols_and_input_isolation():
    plan = [PlannedLeg("P", ExpiryLeg("PUT", "SELL", D(100), 2, D(4))), PLAN[0]]
    fills = [trade("C95", 1, 3), trade("P", 1, 3)]
    v = partial_view(plan, fills, multiplier=10)
    fills.clear()
    plan.clear()
    assert v.executed_legs == (ExpiryLeg("PUT", "SELL", D(100), 1, D(3)), call("BUY", 95, 1, 3))
    assert v.executed.net_entry == D(0) and v.executed.max_loss == D(-1000)
    assert v.planned.net_entry == D(-10)
    assert v.pending == (("P", 1),)


def test_limit_counts_groups_instead_of_reports():
    plan = [PlannedLeg("L", call("BUY", 100, 65, 1))]
    v = partial_view(plan, [trade("L", 1, p) for p in range(64)] + [trade("L", 1, 0)])
    assert len(v.executed_legs) == 64 and v.executed_legs[0].quantity == 2
    assert v.pending == ()


def test_decimal_price_and_text_symbol_keep_value_semantics_as_group_keys():
    class SeriesName(str):
        __hash__ = None

    class Price(D):
        __hash__ = None

    plan = [PlannedLeg(SeriesName("C95"), call("BUY", 95, 2, 7))]
    fills = [Execution("C95", 1, D("6.90")), Execution(SeriesName("C95"), 1, Price("6.900"))]
    view = partial_view(plan, fills)
    assert view.executed_legs == (call("BUY", 95, 2, "6.90"),)
    assert view.executed.net_entry == D("13.80") and view.pending == ()


def partially_filled_condor(*fills):
    plan = (PlannedLeg("P90", ExpiryLeg("PUT", "BUY", D(90), 1, D(1))),
            PlannedLeg("P95", ExpiryLeg("PUT", "SELL", D(95), 1, D("2.50"))),
            PlannedLeg("C105", call("SELL", 105, 1, "2.50")),
            PlannedLeg("C110", call("BUY", 110, 1, 1)))
    view = partial_view(plan, fills)
    assert profile(view.planned) == (D(-3), (F(92), F(108)), D(3), D(-2), False, False)
    return view


def test_g9_iron_condor_only_shorts_filled_has_unlimited_loss():
    view = partially_filled_condor(trade("P95", 1, "2.50"), trade("C105", 1, "2.50"))
    assert profile(view.executed) == (D(-5), (F(90), F(110)), D(5), None, False, True)
    assert spots(view, 0, 90, 100, 110, 120) == (D(-90), D(0), D(5), D(0), D(-10))
    assert view.executed_legs == (ExpiryLeg("PUT", "SELL", D(95), 1, D("2.50")),
                                  call("SELL", 105, 1, "2.50"))
    assert view.pending == (("P90", 1), ("C110", 1))


def test_g10_iron_condor_only_put_spread_filled_has_limited_loss():
    view = partially_filled_condor(trade("P90", 1, 1), trade("P95", 1, "2.50"))
    assert profile(view.executed) == (D("-1.50"), (F(187, 2),), D("1.50"), D("-3.50"), False, False)
    assert spots(view, 85, 90, 95, 100) == (D("-3.50"), D("-3.50"), D("1.50"), D("1.50"))
    assert view.pending == (("C105", 1), ("C110", 1))


def test_h1_eight_series_with_and_without_last_fill():
    plan = [PlannedLeg(f"S{i}", call("BUY", 100 + i, 1, 1)) for i in range(1, 9)]
    pending = (("S1", 1), ("S2", 1), ("S3", 1), ("S4", 1),
               ("S5", 1), ("S6", 1), ("S7", 1), ("S8", 1))
    empty = partial_view(plan, [])
    assert profile(empty.planned) == (D(8), (F(209, 2),), None, D(-8), True, False)
    assert empty.executed is None
    assert empty.pending == pending

    filled = partial_view(plan, [trade("S8", 1, 1)])
    assert profile(filled.executed) == (D(1), (F(109),), None, D(-1), True, False)
    assert filled.pending == pending[:-1]


@pytest.mark.parametrize("symbol", [95, None, b"P90"])
def test_h2_non_text_symbol_refused_in_plan_and_execution(symbol):
    with pytest.raises(PayoffRefusal):
        PlannedLeg(symbol, PLAN[0].leg)
    with pytest.raises(PayoffRefusal):
        Execution(symbol, 1, D(1))
