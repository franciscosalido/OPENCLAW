"""Oráculos manuais de G2/G3 no simulador."""
from datetime import date
from decimal import Decimal as D, localcontext
from itertools import product

import pytest

from backend.derivatives.ticket.models import Leg, Side, TicketDraft
from backend.derivatives.ticket.sequencing import (
    Fill, Holding, Position, ReservationBook, SequenceRefusal, partial_exposure, plan_legs,
    releasable_quantity, within_signed_limits,
)
from tests.unit.derivatives.ticket.test_models import TIME


def leg(symbol: str, side: Side, price: str, n: int = 10, lot: int = 1) -> Leg:
    """Limite sintético sem inferência pelo símbolo."""
    return Leg(symbol=symbol, side=side, quantity=n, lot_size=lot, limit_price=D(price))


BUY = leg("A", Side.BUY, "1")
SELL = leg("B", Side.SELL, "1.50")


def draft(*legs: Leg, net: str = "-5", gross: str = "25") -> TicketDraft:
    """Versão assinável, valores totais da tabela."""
    return TicketDraft(legs=legs, net_limit=D(net), gross_cap=D(gross),
                       send_deadline=TIME, order_validity=TIME, quote_snapshot_id="q")


def holding(symbol: str, balance: int = 0, multiplier: int = 1) -> Holding:
    """Identidade e exposição explicitamente conciliadas na conta do cenário."""
    return Holding(symbol=symbol, underlying="ETF", kind="CALL", expiry=date(2027, 1, 15),
                   multiplier=multiplier, balance=balance)


def position(*rows: Holding, account: str = "sim") -> Position:
    """Evidência de A como proteção para B na posição da conta."""
    return Position(account=account, holdings=rows or (holding("A"), holding("B")),
                    pairs=(("A", "B"),))


def test_s03_and_s21() -> None:
    """A compra órfã perde o prêmio; desmontagem recompra a ponta vendida primeiro."""
    t = draft(SELL, BUY)
    assert plan_legs(t, position()).legs == (BUY, SELL)
    assert partial_exposure(t) == D("10.00")
    close_buy, close_sell = leg("B", Side.BUY, "1.50"), leg("A", Side.SELL, "1")
    closing = plan_legs(draft(close_sell, close_buy), position(holding("A", 10), holding("B", -10)))
    assert closing.legs == (close_buy, close_sell)
    assert closing.protection_for(close_sell) == "B"


@pytest.mark.parametrize("rows", [
    (holding("A"),), (holding("A"), holding("B", multiplier=100)),
    (holding("A", 1), holding("B", -1)),
])
def test_unverifiable_or_crossing_positions_refuse(rows: tuple[Holding, ...]) -> None:
    """Somente planos de abertura ou desmontagem com evidência coerente."""
    with pytest.raises(SequenceRefusal):
        plan_legs(draft(SELL, BUY), position(*rows))


def test_s04_rounding() -> None:
    """Enviado, executado e livre são grandezas distintas."""
    assert releasable_quantity(SELL, 0, 0, 0) == 0
    assert releasable_quantity(SELL, 3, 0, 0) == 3
    assert releasable_quantity(leg("B", Side.SELL, "1.50", 12, 3), 7, 2, 1) == 3


def test_s09_cancel_and_late_fill() -> None:
    """Duas boletas da conta disputam uma única cobertura confirmada."""
    plan = plan_legs(draft(SELL, BUY), position())
    book = ReservationBook()
    book.confirm_buy(plan, BUY, "buy-fill", 3)
    book.reserve(plan, SELL, "ord1", 3)
    book.confirm_sale("ord1", "sell-fill1", 1)
    assert book.available(plan, SELL) == 0
    with pytest.raises(SequenceRefusal):
        book.reserve(plan, SELL, "ord2", 1)
    # Pedido de cancelamento local não é um fato conciliado.
    book.confirm_sale("ord1", "sell-fill2", 1)
    assert book.available(plan, SELL) == 0
    book.confirm_release("ord1", 1)
    assert book.available(plan, SELL) == 1
    book.reserve(plan, SELL, "ord2", 1)
    assert book.available(plan, SELL) == 0


def test_scope_and_duplicate_fills() -> None:
    """A conta e a série executada delimitam o crédito de proteção."""
    p = plan_legs(draft(BUY, SELL), position())
    other = plan_legs(draft(BUY, SELL), position(account="other"))
    book = ReservationBook()
    book.confirm_buy(p, BUY, "fill", 3)
    with pytest.raises(SequenceRefusal):
        book.confirm_buy(p, BUY, "fill", 3)
    assert book.available(other, SELL) == 0
    assert book.available(p, SELL) == 3


@pytest.mark.parametrize(("buy", "net", "gross", "cost", "fills", "expected"), [
    ("1", "-5", "25", "0", (), True), ("1", "-5.01", "25", "0", (), False),
    ("1", "-5", "24.99", "0", (), False), ("1", "-4.99", "25.01", ".01", (), True),
    ("1", "-5.30", "24.70", "0", (Fill(symbol="A", side=Side.BUY, quantity=3, price=D(".90")),),
     True), ("2", "5", "35", "0", (), True), ("2", "4.99", "35", "0", (), False),
])
def test_entire_signed_structure(buy: str, net: str, gross: str, cost: str,
                                 fills: tuple[Fill, ...], expected: bool) -> None:
    """Resultados literais calculados na especificação antes de implementar."""
    t = draft(leg("A", Side.BUY, buy), SELL, net=net, gross=gross)
    with localcontext() as ctx:
        ctx.prec = 1
        assert within_signed_limits(t, fills, SELL, known_costs=D(cost)) is expected


@pytest.mark.parametrize("next_leg", [leg("A", Side.BUY, "1.01"), leg("B", Side.SELL, "1.49"),
                                      leg("B", Side.SELL, "1.51")])
def test_s22_individual_price_or_gross_cap(next_leg: Leg) -> None:
    """Não desloca limites nem aceita execução projetada acima do teto bruto."""
    assert not within_signed_limits(draft(BUY, SELL), (), next_leg, known_costs=D("0"))


def test_supplemental_lot_invariant() -> None:
    """Explora todos os saldos pequenos; a tabela manual fixa as fronteiras de referência."""
    for bought, sold, reserved in product(range(8), repeat=3):
        if sold + reserved <= bought:
            n = releasable_quantity(leg("B", Side.SELL, "1", 6, 2), bought, sold, reserved)
            assert 0 <= n <= 6 and n % 2 == 0 and sold + reserved + n <= bought
