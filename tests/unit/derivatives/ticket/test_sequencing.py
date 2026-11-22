"""Oráculos manuais de G2/G3 no simulador."""
from datetime import date
from decimal import Decimal as D, localcontext
from itertools import product

import pytest

from backend.derivatives.ticket.models import Leg, Side, TicketDraft
from backend.derivatives.ticket.sequencing import (
    Fill, Holding, LegPlan, Position, ReservationBook, SequenceRefusal, partial_exposure, plan_legs,
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
     (Fill(execution="f1", symbol="A", side=Side.BUY, quantity=3, price=D(".90")),),
     True),
    ("2", "5", "35", "0", (), True), ("2", "4.99", "35", "0", (), False),
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


def test_partial_execution_sequences_conserve_shared_protection() -> None:
    """Em cada prefixo, confronta o livro com saldos separados de dois participantes."""
    plan = plan_legs(draft(BUY, SELL), position())
    for sequence in product(("buy", "reserve-1", "reserve-2", "fill", "release"), repeat=4):
        book = ReservationBook()
        bought = sold = 0
        live: list[str] = []
        for i, event in enumerate(sequence):
            identity = str(i)
            if event == "buy":
                book.confirm_buy(plan, BUY, identity, 1, ticket="buyer")
                bought += 1
            elif event.startswith("reserve"):
                if sold + len(live) < bought:
                    book.reserve(plan, SELL, identity, 1, ticket=event)
                    live.append(identity)
                else:
                    with pytest.raises(SequenceRefusal):
                        book.reserve(plan, SELL, identity, 1, ticket=event)
            elif live:
                order = live.pop(0)
                if event == "fill":
                    book.confirm_sale("sim", order, identity, 1)
                    sold += 1
                else:
                    book.confirm_release("sim", order, 1)
            assert sold + len(live) <= bought
            assert book.available(plan, SELL, ticket="observer") == bought - sold - len(live)


def test_equivalent_position_row_order_preserves_coverage() -> None:
    """A ordem de apresentação dos registros não altera o saldo por conta e série."""
    t = draft(BUY, SELL)
    rows = tuple(holding(s) for s in "ABCD")
    pairs = (("A", "B"), ("C", "D"))
    p = plan_legs(t, Position(account="sim", holdings=rows, pairs=pairs))
    other = plan_legs(t, Position(account="sim", holdings=rows[::-1], pairs=pairs[::-1]))
    book = ReservationBook()
    book.confirm_buy(p, BUY, "buy1", 3, ticket="T1")
    assert book.available(other, SELL, ticket="T2") == 3
    assert book.available(other, SELL, ticket="T1") == 3


CONDOR = (leg("A", Side.BUY, "3.00"), leg("D", Side.BUY, "0.50"),
          leg("B", Side.SELL, "2.00"), leg("C", Side.SELL, "1.00"))


@pytest.mark.parametrize(("legs", "cost", "expected"), [
    ((BUY, SELL), "0", "10.00"), (CONDOR, "0", "35.00"), (CONDOR, "0.07", "35.07"),
], ids=["trava", "condor", "condor-com-custo"])
def test_b1_maximum_outlay_without_sales(legs: tuple[Leg, ...], cost: str, expected: str) -> None:
    """Todas as compras podem executar antes da primeira venda, com o custo pago uma vez."""
    ticket = draft(*legs)
    with localcontext() as ctx:
        ctx.prec = 1
        assert partial_exposure(ticket, known_costs=D(cost)) == D(expected)


def test_b1_exposure_without_a_protective_buy_refuses() -> None:
    """Uma venda isolada não admite cálculo de desembolso protetor."""
    with pytest.raises(SequenceRefusal):
        partial_exposure(draft(SELL))


def test_r2_buy_fills_cannot_exceed_signed_quantity() -> None:
    """Comprar 6 e depois mais 5 ultrapassaria as 10 assinadas."""
    plan = plan_legs(draft(BUY, SELL), position())
    book = ReservationBook()
    book.confirm_buy(plan, BUY, "b1", 6, ticket="T1")
    with pytest.raises(SequenceRefusal):
        book.confirm_buy(plan, BUY, "b2", 5, ticket="T1")
    assert book.available(plan, SELL, ticket="T1") == 6


def test_r3_sale_cannot_exceed_live_reservation() -> None:
    """Uma execução recusada deixa disponíveis as quatro unidades da ordem."""
    plan = plan_legs(draft(BUY, SELL), position())
    book = ReservationBook()
    book.confirm_buy(plan, BUY, "b1", 6, ticket="T1")
    book.reserve(plan, SELL, "order", 4, ticket="T1")
    with pytest.raises(SequenceRefusal):
        book.confirm_sale("sim", "order", "s1", 5)
    book.confirm_sale("sim", "order", "s1", 1)


def test_r4_release_requires_exact_live_balance() -> None:
    """Com uma venda e três ainda vivas, apenas a baixa exata de três libera cinco."""
    plan = plan_legs(draft(BUY, SELL), position())
    book = ReservationBook()
    book.confirm_buy(plan, BUY, "b1", 6, ticket="T1")
    book.reserve(plan, SELL, "order", 4, ticket="T1")
    book.confirm_sale("sim", "order", "s1", 1)
    with pytest.raises(SequenceRefusal):
        book.confirm_release("sim", "order", 2)
    book.confirm_release("sim", "order", 3)
    assert book.available(plan, SELL, ticket="T1") == 5


@pytest.mark.parametrize("ticket", ["T1", "T2"], ids=["r5a", "r5b"])
@pytest.mark.parametrize("operation", ["confirm_buy", "available"])
def test_changed_account_photo_requires_reconciliation(ticket: str, operation: str) -> None:
    """A mesma conta exige conciliação tanto para a boleta registrada quanto para outra."""
    t = draft(BUY, SELL)
    original = plan_legs(t, position())
    changed = plan_legs(t, position(holding("A", 5), holding("B")))
    book = ReservationBook()
    book.confirm_buy(original, BUY, "seed", 1, ticket="T1")
    with pytest.raises(SequenceRefusal, match="foto divergente"):
        if operation == "confirm_buy":
            book.confirm_buy(changed, BUY, "next", 1, ticket=ticket)
        else:
            book.available(changed, SELL, ticket=ticket)
    assert book.available(original, SELL, ticket="T1") == 1


def test_r5c_same_photo_cannot_replace_registered_ticket_plan() -> None:
    """Aumentar a compra assinada muda o plano mesmo com a mesma foto."""
    plan = plan_legs(draft(BUY, SELL), position())
    changed = plan_legs(draft(leg("A", Side.BUY, "1", 12), SELL), position())
    book = ReservationBook()
    book.confirm_buy(plan, BUY, "seed", 1, ticket="T1")
    with pytest.raises(SequenceRefusal, match="identidade ou plano divergente"):
        book.available(changed, SELL, ticket="T1")


def test_r5d_noncanonical_plan_refuses_before_comparing_photos() -> None:
    """Mesmo sob outra foto, a adulteração da dependência invalida primeiro o plano."""
    t = draft(BUY, SELL)
    plan = plan_legs(t, position())
    changed = plan_legs(t, position(holding("A", 5), holding("B")))
    book = ReservationBook()
    book.confirm_buy(plan, BUY, "seed", 1, ticket="T1")
    with pytest.raises(SequenceRefusal, match="identidade ou plano divergente"):
        book.available(changed._replace(dependencies=()), SELL, ticket="T2")


def test_r6_net_includes_known_cost() -> None:
    """Um centavo de custo reduz o crédito de 5,00 para 4,99."""
    for net, expected in [("-5.00", False), ("-4.99", True)]:
        t = draft(BUY, SELL, net=net, gross="25.01")
        assert within_signed_limits(t, (), SELL, known_costs=D("0.01")) is expected


def test_r7_buyback_cannot_cross_short_balance() -> None:
    """A desmontagem de dez vendidas não admite recompra de vinte."""
    closing = draft(leg("B", Side.BUY, "1.50", 20), leg("A", Side.SELL, "1.00"))
    with pytest.raises(SequenceRefusal, match="recompra atravessa saldo"):
        plan_legs(closing, position(holding("A", 10), holding("B", -10)))


def test_r8_reservation_requires_whole_lots() -> None:
    """De seis unidades, uma reserva de quatro quebra o lote de três."""
    buy, sell = leg("A", Side.BUY, "1", 6, 3), leg("B", Side.SELL, "1.50", 6, 3)
    plan = plan_legs(draft(buy, sell), position())
    book = ReservationBook()
    book.confirm_buy(plan, buy, "b1", 6, ticket="T1")
    with pytest.raises(SequenceRefusal):
        book.reserve(plan, sell, "order", 4, ticket="T1")
    book.reserve(plan, sell, "order", 3, ticket="T1")
    assert book.available(plan, sell, ticket="T1") == 3


def test_r10_sale_cannot_exceed_planned_protection() -> None:
    """Dez unidades de compra planejada não cobrem vinte de venda."""
    with pytest.raises(SequenceRefusal, match="quantidade de proteção insuficiente"):
        plan_legs(draft(BUY, leg("B", Side.SELL, "1.50", 20)), position())


def test_r11_available_rounds_remaining_ticket_capacity_to_lot() -> None:
    """A conta tem saldo, mas as oito restantes de T1 comportam só dois lotes de três."""
    buy, sell = leg("A", Side.BUY, "1", 9, 3), leg("B", Side.SELL, "1.50", 9, 3)
    plan = plan_legs(draft(buy, sell), position())
    book = ReservationBook()
    book.confirm_buy(plan, buy, "b1", 9, ticket="T1")
    book.confirm_buy(plan, buy, "b2", 9, ticket="T2")
    book.reserve(plan, sell, "order", 3, ticket="T1")
    book.confirm_sale("sim", "order", "s1", 1)
    book.confirm_release("sim", "order", 2)
    assert book.available(plan, sell, ticket="T1") == 6


@pytest.mark.parametrize("ticket", ["", None, 7])
def test_reviewer_book_requires_a_ticket_identity(ticket: object) -> None:
    """Revisor: sem identidade de boleta o livro não credita, não consulta e não reserva."""
    plan, book = plan_legs(draft(BUY, SELL), position()), ReservationBook()
    with pytest.raises(SequenceRefusal, match="identidade"):
        book.confirm_buy(plan, BUY, "e1", 1, ticket=ticket)  # type: ignore[arg-type]
    with pytest.raises(SequenceRefusal, match="identidade"):
        book.available(plan, SELL, ticket=ticket)  # type: ignore[arg-type]
    book.confirm_buy(plan, BUY, "e1", 1, ticket="T1")
    assert book.available(plan, SELL, ticket="T1") == 1


@pytest.mark.parametrize("cost", [D("-0.01"), D("NaN"), D("Infinity"), 0.01, 1])
def test_reviewer_partial_exposure_refuses_invalid_cost(cost: object) -> None:
    """Revisor: custo negativo, não finito ou fora de Decimal não entra na exposição."""
    with pytest.raises(SequenceRefusal):
        partial_exposure(draft(BUY, SELL), known_costs=cost)  # type: ignore[arg-type]
    assert partial_exposure(draft(BUY, SELL), known_costs=D("0.07")) == D("10.07")


def close_plan(quantity: int = 10, long_balance: int = 10) -> LegPlan:
    """Desmontagens D6, D7 e D10 com os limites totais literais do cartão."""
    net, gross = {6: ("3", "15"), 7: ("3.50", "17.50"), 10: ("5", "25")}[quantity]
    sale = leg("A", Side.SELL, "1", quantity)
    buy = leg("B", Side.BUY, "1.50", quantity)
    return plan_legs(draft(sale, buy, net=net, gross=gross),
                     position(holding("A", long_balance), holding("B", -10)))


def test_k1_conflicting_buybacks_refuse() -> None:
    book = ReservationBook()
    p = close_plan()
    book.admit(p, ticket="T1")
    with pytest.raises(SequenceRefusal):
        book.admissible(p, ticket="T2")


def settled_four() -> ReservationBook:
    """Admite dez, credita quatro, encerra a compra."""
    book = ReservationBook()
    p = close_plan()
    book.admit(p, ticket="T1")
    book.confirm_buy(p, p.legs[0], "e1", 4, ticket="T1")
    book.settle_buy("sim", "T1", "B")
    return book


def test_k2_settled_capacity_boundary() -> None:
    book = settled_four()
    book.admissible(close_plan(6), ticket="T2")
    with pytest.raises(SequenceRefusal):
        book.admissible(close_plan(7), ticket="T2")


def test_k3_settlement_caps_later_buy_fills() -> None:
    book = settled_four()
    p = close_plan()
    with pytest.raises(SequenceRefusal):
        book.confirm_buy(p, p.legs[0], "late", 1, ticket="T1")


def test_k4_admissible_is_read_only() -> None:
    book = ReservationBook()
    book.admissible(close_plan(), ticket="T1")
    book.admissible(close_plan(long_balance=12), ticket="T2")


def test_k5_opening_buys_have_independent_capacity() -> None:
    book = ReservationBook()
    p = plan_legs(draft(BUY, SELL), position())
    book.admit(p, ticket="T1")
    book.admit(p, ticket="T2")


def test_k6_admission_is_idempotent() -> None:
    book = ReservationBook()
    p = close_plan()
    book.admit(p, ticket="T1")
    book.admit(p, ticket="T1")
    book.admissible(p, ticket="T1")


def test_k7_failed_admit_leaves_no_occupation() -> None:
    book = ReservationBook()
    p = close_plan()
    book.admit(p, ticket="T1")
    with pytest.raises(SequenceRefusal):
        book.admit(p, ticket="T2")
    with pytest.raises(SequenceRefusal):
        book.settle_buy("sim", "T2", "B")
