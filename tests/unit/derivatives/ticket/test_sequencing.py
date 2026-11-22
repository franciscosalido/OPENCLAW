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
    (holding("A", -1), holding("B", 1)),
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
    assert book.available(plan, SELL, ticket="T2") == 0
    book.confirm_buy(plan, BUY, "buy-fill", 3, ticket="T1")
    book.reserve(plan, SELL, "ord1", 3, ticket="T1")
    book.confirm_sale("sim", "ord1", "sell-fill1", 1)
    assert book.available(plan, SELL, ticket="T2") == 0
    with pytest.raises(SequenceRefusal):
        book.reserve(plan, SELL, "ord2", 1, ticket="T2")
    # Pedido de cancelamento local não é um fato conciliado.
    book.confirm_sale("sim", "ord1", "sell-fill2", 1)
    assert book.available(plan, SELL, ticket="T2") == 0
    book.confirm_release("sim", "ord1", 1)
    assert book.available(plan, SELL, ticket="T2") == 1
    book.reserve(plan, SELL, "ord2", 1, ticket="T2")
    assert book.available(plan, SELL, ticket="T2") == 0


def test_scope_and_duplicate_fills() -> None:
    """A conta e a série executada delimitam o crédito de proteção."""
    p = plan_legs(draft(BUY, SELL), position())
    other = plan_legs(draft(BUY, SELL), position(account="other"))
    book = ReservationBook()
    book.confirm_buy(p, BUY, "fill", 3, ticket="T1")
    with pytest.raises(SequenceRefusal):
        book.confirm_buy(p, BUY, "fill", 3, ticket="T1")
    assert book.available(other, SELL, ticket="T1") == 0
    assert book.available(p, SELL, ticket="T1") == 3


@pytest.mark.parametrize(("buy", "net", "gross", "cost", "fills", "expected"), [
    ("1", "-5", "25", "0", (), True), ("1", "-5.01", "25", "0", (), False),
    ("1", "-5", "24.99", "0", (), False), ("1", "-4.99", "25.01", ".01", (), True),
    ("1", "-5.30", "24.70", "0",
     (Fill(execution="f1", symbol="A", side=Side.BUY, quantity=3, price=D(".90")),), True), ("2", "5", "35", "0", (), True), ("2", "4.99", "35", "0", (), False),
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


def test_reservations_race_and_failed_release() -> None:
    """Somente uma reserva concorrente vence; recibos repetidos não alteram saldos."""
    from concurrent.futures import ThreadPoolExecutor

    p = plan_legs(draft(BUY, SELL), position())
    book = ReservationBook()
    book.confirm_buy(p, BUY, "fill", 3, ticket="origin")

    def reserve(i: int) -> bool:
        try:
            book.reserve(p, SELL, str(i), 3, ticket=str(i))
        except SequenceRefusal:
            return False
        return True

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(reserve, range(8)))
    assert sum(results) == 1
    order = str(results.index(True))
    book.confirm_sale("sim", order, "late", 1)
    with pytest.raises(SequenceRefusal):
        book.confirm_sale("sim", order, "late", 1)
    with pytest.raises(SequenceRefusal):
        book.confirm_release("sim", order, 3)
    assert book.available(p, SELL, ticket="next") == 0
    book.confirm_release("sim", order, 2)
    assert book.available(p, SELL, ticket="next") == 2


def test_incompatible_evidence_and_shared_initial_protection() -> None:
    """Uma mesma proteção inicial não cobre duas vendas nem cruza vencimentos."""
    rows = (holding("A", 3), holding("B", -2), holding("C", -2))
    pos = Position(account="sim", holdings=rows, pairs=(("A", "B"), ("A", "C")))
    with pytest.raises(SequenceRefusal):
        plan_legs(draft(BUY, SELL), pos)
    later = holding("B").model_copy(update={"expiry": date(2028, 1, 15)})
    with pytest.raises(SequenceRefusal):
        plan_legs(draft(BUY, SELL), position(holding("A"), later))


def test_separate_protectors_do_not_share_fills() -> None:
    """Uma conta pode ter dois pares elegíveis e saldos independentes."""
    pos = Position(account="sim", holdings=tuple(holding(s) for s in "ABCD"),
                   pairs=(("A", "B"), ("C", "D")))
    c, d = leg("C", Side.BUY, "1"), leg("D", Side.SELL, "1.50")
    p = plan_legs(draft(SELL, d, BUY, c), pos)
    assert p.legs == (BUY, c, SELL, d)
    book = ReservationBook()
    book.confirm_buy(p, BUY, "f1", 2, ticket="T1")
    assert book.available(p, d, ticket="T1") == 0
    assert book.available(p, SELL, ticket="T1") == 2


def test_closing_waits_for_actual_buyback() -> None:
    """S21: proteção original só se libera na proporção recomprada e conciliada."""
    b, a = leg("B", Side.BUY, "1.50"), leg("A", Side.SELL, "1")
    p = plan_legs(draft(a, b), position(holding("A", 10), holding("B", -10)))
    book = ReservationBook()
    assert book.available(p, a, ticket="close") == 0
    book.confirm_buy(p, b, "rebuy", 3, ticket="close")
    assert book.available(p, a, ticket="close") == 3
    book.reserve(p, a, "sell", 3, ticket="close")
    assert book.available(p, a, ticket="other") == 0


def test_signed_projection_rejects_repeats_overfill_wrong_side_and_missing_cost() -> None:
    """Execuções entram uma vez e só dentro da versão em avaliação."""
    t = draft(BUY, SELL)
    fill = Fill(execution="fid", symbol="A", side=Side.BUY, quantity=3, price=D("1"))
    for facts in [(fill, fill), (fill.model_copy(update={"quantity": 11}),),
                  (fill.model_copy(update={"side": Side.SELL}),),
                  (fill.model_copy(update={"price": D("1.01")}),)]:
        assert not within_signed_limits(t, facts, SELL, known_costs=D("0"))
    assert not within_signed_limits(t, (), SELL, known_costs=D("NaN"))
    assert not within_signed_limits(t, (), SELL, known_costs=D(".01"))
    assert partial_exposure(t, known_costs=D(".01")) == D("10.01")
