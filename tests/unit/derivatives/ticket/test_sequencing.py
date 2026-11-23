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
    """Só a boleta que comprou recupera o saldo final confirmado."""
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
    assert book.available(plan, SELL, ticket="T1") == 1
    assert book.available(plan, SELL, ticket="T2") == 0
    with pytest.raises(SequenceRefusal):
        book.reserve(plan, SELL, "ord2", 1, ticket="T2")
    book.reserve(plan, SELL, "ord2", 1, ticket="T1")
    assert book.available(plan, SELL, ticket="T1") == 0


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
    from threading import Barrier

    p = plan_legs(draft(BUY, SELL), position())
    book = ReservationBook()
    book.confirm_buy(p, BUY, "fill", 3, ticket="origin")

    start = Barrier(8)

    def reserve(i: int) -> bool:
        start.wait(timeout=10)
        try:
            book.reserve(p, SELL, str(i), 3, ticket="origin")
        except SequenceRefusal:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as executor:
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
    assert book.available(p, SELL, ticket="origin") == 2
    assert book.available(p, SELL, ticket="next") == 0


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


def test_partial_execution_sequences_conserve_each_tickets_protection() -> None:
    """Confronta cada prefixo das 6⁴ sequências com a contabilidade por boleta."""
    plan = plan_legs(draft(BUY, SELL), position())
    for sequence in product(("buy1", "buy2", "reserve1", "reserve2", "fill", "release"), repeat=4):
        book = ReservationBook()
        bought = {"T1": 0, "T2": 0}
        sold = {"T1": 0, "T2": 0}
        live: list[tuple[str, str]] = []  # (ordem, boleta), na ordem de envio
        for i, event in enumerate(sequence):
            identity = str(i)
            if event in ("buy1", "buy2"):
                ticket = "T" + event[-1]
                book.confirm_buy(plan, BUY, identity, 1, ticket=ticket)
                bought[ticket] += 1
            elif event in ("reserve1", "reserve2"):
                ticket = "T" + event[-1]
                occupied = sold[ticket] + sum(owner == ticket for _, owner in live)
                if occupied < bought[ticket]:
                    book.reserve(plan, SELL, identity, 1, ticket=ticket)
                    live.append((identity, ticket))
                else:
                    with pytest.raises(SequenceRefusal):
                        book.reserve(plan, SELL, identity, 1, ticket=ticket)
            elif live:
                order, owner = live.pop(0)
                if event == "fill":
                    book.confirm_sale("sim", order, identity, 1)
                    sold[owner] += 1
                else:
                    book.confirm_release("sim", order, 1)
            for ticket in ("T1", "T2"):
                reserved = sum(owner == ticket for _, owner in live)
                assert book.available(plan, SELL, ticket=ticket) == bought[ticket] - sold[ticket] - reserved
            assert book.available(plan, SELL, ticket="T3") == 0


def test_equivalent_position_row_order_preserves_coverage() -> None:
    """A ordem das linhas preserva a cobertura própria da boleta."""
    t = draft(BUY, SELL)
    rows = tuple(holding(s) for s in "ABCD")
    pairs = (("A", "B"), ("C", "D"))
    p = plan_legs(t, Position(account="sim", holdings=rows, pairs=pairs))
    other = plan_legs(t, Position(account="sim", holdings=rows[::-1], pairs=pairs[::-1]))
    book = ReservationBook()
    book.confirm_buy(p, BUY, "buy1", 3, ticket="T1")
    for equivalent in (p, other):
        assert book.available(equivalent, SELL, ticket="T1") == 3
        assert book.available(equivalent, SELL, ticket="T2") == 0


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


def test_g3_separate_accounts_can_both_buy_back_ten() -> None:
    """A ocupação de sim não consome o saldo vendido de sim2."""
    book = ReservationBook()
    p = close_plan()
    other = plan_legs(p.draft, p.position.model_copy(update={"account": "sim2"}))
    book.admit(p, ticket="T1")
    book.admit(other, ticket="T2")


def test_g4_distinct_short_series_have_independent_capacity() -> None:
    """Recomprar B não ocupa a capacidade de recomprar D na mesma conta."""
    book = ReservationBook()
    q = Position(account="sim", holdings=(holding("A", 10), holding("B", -10),
                                          holding("C", 10), holding("D", -10)),
                 pairs=(("A", "B"), ("C", "D")))
    cd = draft(leg("C", Side.SELL, "1"), leg("D", Side.BUY, "1.50"), net="5", gross="25")
    book.admit(plan_legs(close_plan().draft, q), ticket="T1")
    book.admit(plan_legs(cd, q), ticket="T2")


def test_g6_admission_remembers_reconciled_position() -> None:
    """A foto da primeira admissão prevalece mesmo antes de qualquer execução."""
    book = ReservationBook()
    book.admit(close_plan(), ticket="T1")
    with pytest.raises(SequenceRefusal, match="foto divergente; conciliação necessária"):
        book.admissible(close_plan(long_balance=12), ticket="T2")


def test_v1_another_ticket_cannot_reserve_owning_tickets_fills() -> None:
    plan = plan_legs(draft(BUY, SELL), position())
    book = ReservationBook()
    book.confirm_buy(plan, BUY, "buy1", 4, ticket="T1")
    assert book.available(plan, SELL, ticket="T1") == 4
    assert book.available(plan, SELL, ticket="T2") == 0
    with pytest.raises(SequenceRefusal):
        book.reserve(plan, SELL, "sale2", 1, ticket="T2")
    assert book.available(plan, SELL, ticket="T1") == 4


def test_v2_partial_sale_and_release_affect_only_the_owner() -> None:
    plan = plan_legs(draft(BUY, SELL), position())
    book = ReservationBook()

    def balances() -> tuple[int, int]:
        return book.available(plan, SELL, ticket="T1"), book.available(plan, SELL, ticket="T2")

    book.confirm_buy(plan, BUY, "buy1", 4, ticket="T1")
    book.confirm_buy(plan, BUY, "buy2", 6, ticket="T2")
    book.reserve(plan, SELL, "sale1", 3, ticket="T1")
    assert balances() == (1, 6)
    book.confirm_sale("sim", "sale1", "fill1", 2)
    assert balances() == (1, 6)
    book.confirm_release("sim", "sale1", 1)
    assert balances() == (2, 6)
    with pytest.raises(SequenceRefusal):
        book.reserve(plan, SELL, "sale2", 7, ticket="T2")
    book.reserve(plan, SELL, "sale2", 6, ticket="T2")
    assert balances() == (2, 0)


def test_v3_only_own_buybacks_release_long_protection() -> None:
    plan = close_plan()
    buyback, sale = plan.legs
    book = ReservationBook()
    book.confirm_buy(plan, buyback, "repurchase1", 4, ticket="T1")
    assert book.available(plan, sale, ticket="T1") == 4
    assert book.available(plan, sale, ticket="T2") == 0
    book.confirm_buy(plan, buyback, "repurchase2", 6, ticket="T2")
    book.reserve(plan, sale, "sale1", 4, ticket="T1")
    assert book.available(plan, sale, ticket="T1") == 0
    assert book.available(plan, sale, ticket="T2") == 6


def test_v6_live_and_filled_sales_consume_only_the_paired_series() -> None:
    pos = Position(account="sim", holdings=tuple(holding(s) for s in "ABCD"),
                   pairs=(("A", "B"), ("C", "D")))
    buy_c, sell_d = leg("C", Side.BUY, "1"), leg("D", Side.SELL, "1.50")
    plan = plan_legs(draft(BUY, SELL, buy_c, sell_d), pos)
    book = ReservationBook()
    book.confirm_buy(plan, BUY, "buyA", 2, ticket="T1")
    book.confirm_buy(plan, buy_c, "buyC", 2, ticket="T1")
    book.reserve(plan, SELL, "sellB", 2, ticket="T1")
    assert book.available(plan, SELL, ticket="T1") == 0
    assert book.available(plan, sell_d, ticket="T1") == 2
    book.confirm_sale("sim", "sellB", "fillB", 2)
    assert book.available(plan, SELL, ticket="T1") == 0
    assert book.available(plan, sell_d, ticket="T1") == 2


def authorized(ticket: TicketDraft, *grants: tuple[str, str, int]) -> TicketDraft:
    """Constrói a versão por validação pública com as autorizações informadas."""
    coverage = tuple({"series": series, "origin": origin, "quantity": qty}
                     for series, origin, qty in grants)
    return TicketDraft.model_validate(dict(ticket) | {"coverage": coverage})


def sale_only(n: int, origin: str = "T1", *, pos: Position | None = None) -> LegPlan:
    """Monta uma venda de B coberta pela série A da boleta de origem."""
    amount = str(D("1.50") * n)
    ticket = draft(leg("B", Side.SELL, "1.50", n), net="-" + amount, gross=amount)
    return plan_legs(authorized(ticket, ("A", origin, n)), pos or position())


def surplus_book(*, bought: int = 10, stopped: bool = True) -> tuple[ReservationBook, LegPlan]:
    """Monta a origem com seis vendas conciliadas e as compras indicadas."""
    book = ReservationBook()
    plan = plan_legs(draft(BUY, SELL), position())
    book.admit(plan, ticket="T1")
    book.confirm_buy(plan, BUY, "origin-buy", bought, ticket="T1")
    book.reserve(plan, SELL, "origin-sale", 6, ticket="T1")
    book.confirm_sale("sim", "origin-sale", "origin-fill", 6)
    if stopped:
        book.close("sim", "T1")
    return book, plan


def test_w3_plan_requires_relevant_sufficient_evidenced_coverage() -> None:
    """O plano exige série documentada, venda correspondente e quantidade suficiente."""
    sell = leg("B", Side.SELL, "1.50", 4)
    bare = draft(sell, net="-6", gross="6")
    only = authorized(bare, ("A", "T1", 4))
    plan = plan_legs(only, position())
    assert plan.legs == (sell,) and plan.dependencies == (("B", "A", False),)
    assert plan.protection_for(sell) == "A"
    assert partial_exposure(only) == D("0")
    assert partial_exposure(only, known_costs=D(".07")) == D(".07")
    with pytest.raises(SequenceRefusal):
        partial_exposure(bare)
    with pytest.raises(SequenceRefusal, match="pareamento ausente ou ambíguo"):
        plan_legs(bare, position())
    five = leg("B", Side.SELL, "1.50", 5)
    with pytest.raises(SequenceRefusal, match="quantidade de proteção insuficiente"):
        plan_legs(authorized(draft(five, net="-7.50", gross="7.50"), ("A", "T1", 4)), position())
    mixed = draft(leg("A", Side.BUY, "1", 1), five, net="-6.50", gross="8.50")
    mixed_plan = plan_legs(authorized(mixed, ("A", "T1", 4)), position())
    assert mixed_plan.dependencies == plan.dependencies
    invalid = (("B", "autorização sem venda correspondente"), ("Z", "série sem evidência"))
    for series, reason in invalid:
        with pytest.raises(SequenceRefusal, match=reason):
            plan_legs(authorized(draft(BUY, SELL), (series, "T1", 4)), position())
    close = authorized(draft(leg("A", Side.SELL, "1", 4), net="-4", gross="4"), ("B", "T1", 4))
    assert plan_legs(close, close_plan().position).dependencies == (("A", "B", True),)


def test_w4_open_origin_cannot_lend() -> None:
    """A cobertura própria permanece com a origem enquanto a boleta estiver aberta."""
    book, origin = surplus_book(stopped=False)
    plan = sale_only(4)
    for admission in (book.admissible, book.admit):
        with pytest.raises(SequenceRefusal, match="boleta de origem não parada"):
            admission(plan, ticket="T2")
    assert book.available(plan, plan.legs[0], ticket="T2", origin="T1") == 0
    with pytest.raises(SequenceRefusal):
        book.reserve(plan, plan.legs[0], "borrow", 1, ticket="T2", origin="T1")
    assert book.available(origin, SELL, ticket="T1") == 4


def test_w5_release_returns_only_unfilled_surplus() -> None:
    """A liberação confirmada devolve à origem apenas o saldo que não executou."""
    book, origin = surplus_book()
    book.close("sim", "T1")
    plan = sale_only(4)
    sale = plan.legs[0]
    assert book.available(origin, SELL, ticket="T1") == 0
    with pytest.raises(SequenceRefusal):
        book.reserve(origin, SELL, "original", 1, ticket="T1")
    assert book.available(plan, sale, ticket="T2") == 0
    assert book.available(plan, sale, ticket="T2", origin="T1") == 4
    book.admit(plan, ticket="T2")
    with pytest.raises(SequenceRefusal):
        book.reserve(plan, sale, "borrow", 4, ticket="T2")
    book.reserve(plan, sale, "borrow", 4, ticket="T2", origin="T1")
    assert book.available(plan, sale, ticket="T2", origin="T1") == 0
    with pytest.raises(SequenceRefusal, match="sobra indisponível"):
        book.admissible(plan, ticket="T3")
    book.confirm_sale("sim", "borrow", "sold", 1)
    book.confirm_release("sim", "borrow", 3)
    assert book.available(plan, sale, ticket="T2", origin="T1") == 3
    book.admissible(plan, ticket="T3")
    assert book.available(plan, sale, ticket="T3", origin="T1") == 3


def test_w6_surplus_and_grant_both_bound_a_sale() -> None:
    """A reserva é limitada pela sobra global e pela autorização individual."""
    book, _ = surplus_book()
    plan = sale_only(3)
    sale = plan.legs[0]
    assert book.available(plan, sale, ticket="T2", origin="T1") == 3
    book.reserve(plan, sale, "borrow", 2, ticket="T2", origin="T1")
    assert book.available(plan, sale, ticket="T2", origin="T1") == 1
    book.confirm_sale("sim", "borrow", "sold", 2)
    assert book.available(plan, sale, ticket="T2", origin="T1") == 1
    other = sale_only(8)
    assert book.available(other, other.legs[0], ticket="T3", origin="T1") == 2


def test_w7_used_grant_stays_exhausted_after_execution() -> None:
    """A execução consome o limite mesmo após a ordem deixar de estar viva."""
    book, _ = surplus_book()
    buy, sale = leg("A", Side.BUY, "1", 2), leg("B", Side.SELL, "1.50", 5)
    ticket = authorized(draft(buy, sale, net="-5.50", gross="9.50"), ("A", "T1", 3))
    p = plan_legs(ticket, position())
    book.admit(p, ticket="T2")
    def balances() -> tuple[int, int]:
        return (book.available(p, sale, ticket="T2"),
                book.available(p, sale, ticket="T2", origin="T1"))
    assert balances() == (0, 3)
    book.reserve(p, sale, "borrow", 3, ticket="T2", origin="T1")
    book.confirm_sale("sim", "borrow", "sold", 3)
    assert balances() == (0, 0)
    book.confirm_buy(p, buy, "own", 2, ticket="T2")
    assert balances() == (2, 0)
    other = sale_only(4)
    assert book.available(other, other.legs[0], ticket="T3", origin="T1") == 1


def test_w8_own_and_borrowed_pools_are_separate() -> None:
    """Reservas em uma origem não debitam outra na mesma perna."""
    book, _ = surplus_book()
    buy = leg("A", Side.BUY, "1", 6)
    p = plan_legs(authorized(draft(buy, SELL, net="-9", gross="21"), ("A", "T1", 4)), position())
    book.admit(p, ticket="T2")
    def balances() -> tuple[int, int]:
        return (book.available(p, SELL, ticket="T2"),
                book.available(p, SELL, ticket="T2", origin="T1"))
    assert balances() == (0, 4)
    book.reserve(p, SELL, "borrow", 4, ticket="T2", origin="T1")
    book.confirm_buy(p, buy, "own", 6, ticket="T2")
    assert balances() == (6, 0)
    book.reserve(p, SELL, "own-sale", 6, ticket="T2")
    assert balances() == (0, 0)


def test_w9_origin_and_account_must_match() -> None:
    """A admissão e a consulta verificam identidade, conta e origem."""
    book, _ = surplus_book()
    own = sale_only(4, "T2")
    with pytest.raises(SequenceRefusal, match="boleta de origem não parada"):
        book.admissible(own, ticket="T2")
    assert book.available(own, own.legs[0], ticket="T2", origin="T2") == 0
    for account, ticket in (("sim", "T9"), ("outra", "T1")):
        with pytest.raises(SequenceRefusal, match="boleta desconhecida"):
            book.close(account, ticket)
    wrong = sale_only(4, "T9")
    assert book.available(wrong, wrong.legs[0], ticket="T2", origin="T1") == 0
    other = sale_only(4, pos=position(account="outra"))
    with pytest.raises(SequenceRefusal, match="boleta de origem não parada"):
        book.admissible(other, ticket="T2")
    assert book.available(other, other.legs[0], ticket="T2", origin="T1") == 0


def test_w10_self_grant_cannot_reopen_a_stopped_origin() -> None:
    """Uma autorização da própria boleta não permite usar sua sobra após a parada."""
    book = ReservationBook()
    p = plan_legs(authorized(draft(BUY, SELL), ("A", "T1", 4)), position())
    book.confirm_buy(p, BUY, "own", 10, ticket="T1")
    assert book.available(p, SELL, ticket="T1") == 10
    assert book.available(p, SELL, ticket="T1", origin="T1") == 0
    book.close("sim", "T1")
    assert book.available(p, SELL, ticket="T1") == 0
    assert book.available(p, SELL, ticket="T1", origin="T1") == 0
    with pytest.raises(SequenceRefusal, match="boleta de origem não parada"):
        book.admissible(p, ticket="T1")


def test_w11_only_one_borrower_reserves_the_surplus() -> None:
    """Oito admissões sem reserva podem disputar a mesma sobra; apenas uma reserva vence."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    book, _ = surplus_book()
    p = sale_only(4)
    barrier = Barrier(8)
    def reserve(i: int) -> bool:
        ticket = f"T{i}"
        book.admit(p, ticket=ticket)
        barrier.wait(timeout=10)
        try:
            book.reserve(p, p.legs[0], f"order-{i}", 4, ticket=ticket, origin="T1")
        except SequenceRefusal:
            return False
        return True
    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(reserve, range(2, 10))) == 1


def test_w12_late_buy_increases_closed_origins_surplus() -> None:
    """A parada permite conciliar compras que executaram tardiamente."""
    book, origin = surplus_book(bought=6)
    p = sale_only(4)
    with pytest.raises(SequenceRefusal, match="sobra indisponível"):
        book.admissible(p, ticket="T2")
    book.confirm_buy(origin, BUY, "late", 2, ticket="T1")
    book.admissible(p, ticket="T2")
    assert book.available(p, p.legs[0], ticket="T2", origin="T1") == 2


def test_w13_buyback_surplus_can_cover_unwinding() -> None:
    """A recompra da boleta parada libera a proteção longa para a venda autorizada."""
    book = ReservationBook()
    p = close_plan()
    buy, _ = p.legs
    book.admit(p, ticket="T1")
    book.confirm_buy(p, buy, "buyback", 4, ticket="T1")
    book.close("sim", "T1")
    sale = leg("A", Side.SELL, "1", 4)
    other = plan_legs(authorized(draft(sale, net="-4", gross="4"), ("B", "T1", 4)), p.position)
    assert book.available(other, sale, ticket="T2", origin="T1") == 4
    book.admit(other, ticket="T2")
    book.reserve(other, sale, "release-A", 4, ticket="T2", origin="T1")
    assert book.available(other, sale, ticket="T2", origin="T1") == 0


def test_w15_one_protective_buy_covers_two_distinct_sales() -> None:
    """As vendas de B e C concorrem pelas execuções da mesma proteção A."""
    b, c = leg("B", Side.SELL, "1.50", 4), leg("C", Side.SELL, "1.50", 6)
    pos = Position(account="sim", holdings=tuple(holding(s) for s in "ABC"),
                   pairs=(("A", "B"), ("A", "C")))
    p = plan_legs(draft(BUY, b, c), pos)
    book = ReservationBook()
    def balances() -> tuple[int, int]:
        return book.available(p, b, ticket="T1"), book.available(p, c, ticket="T1")
    book.confirm_buy(p, BUY, "first", 5, ticket="T1")
    assert balances() == (4, 5)
    book.reserve(p, b, "sell", 4, ticket="T1")
    assert balances() == (0, 1)
    book.confirm_buy(p, BUY, "second", 5, ticket="T1")
    assert balances() == (0, 6)
    book.confirm_sale("sim", "sell", "sold", 4)
    assert balances() == (0, 6)


def test_w16_account_cannot_buy_back_more_than_it_is_short() -> None:
    """O limite de recompra permanece compartilhado por toda a conta."""
    book = ReservationBook()
    p = close_plan()
    buy, _ = p.legs
    book.confirm_buy(p, buy, "first", 4, ticket="T1")
    book.confirm_buy(p, buy, "second", 6, ticket="T2")
    with pytest.raises(SequenceRefusal, match="execuções excedem posição vendida"):
        book.confirm_buy(p, buy, "excess", 1, ticket="T3")


def test_k2_same_origin_name_is_isolated_by_account() -> None:
    book, _ = surplus_book()
    other = position(account="outra")
    owner = plan_legs(draft(BUY, SELL), other)
    book.admit(owner, ticket="T1")
    book.confirm_buy(owner, BUY, "purchase", 7, ticket="T1")
    borrowers = (sale_only(8), sale_only(8, pos=other))

    def balances() -> tuple[int, ...]:
        return tuple(book.available(p, p.legs[0], ticket="T3", origin="T1") for p in borrowers)

    assert balances() == (4, 0)
    book.close("outra", "T1")
    assert balances() == (4, 7)


def test_k3_each_grant_accounts_for_its_own_fills_and_reservations() -> None:
    book = ReservationBook()
    owner = plan_legs(draft(BUY, SELL), position())
    for name, quantity in (("L1", 5), ("L2", 7)):
        book.confirm_buy(owner, BUY, name, quantity, ticket=name)
        book.close("sim", name)
    sale = leg("B", Side.SELL, "1.50", 8)
    plan = plan_legs(authorized(draft(sale, net="-12", gross="12"),
                                ("A", "L2", 5), ("A", "L1", 3)), position())
    book.admit(plan, ticket="T")

    def balances() -> tuple[int, ...]:
        return tuple(book.available(plan, sale, ticket="T", origin=name) for name in ("L1", "L2"))

    assert balances() == (3, 5)
    book.reserve(plan, sale, "borrow", 2, ticket="T", origin="L1")
    assert balances() == (1, 5)
    book.confirm_sale("sim", "borrow", "fill", 1)
    book.confirm_release("sim", "borrow", 1)
    assert balances() == (2, 5)


def test_k4_stopped_borrower_cannot_reserve_another_origin() -> None:
    book, _ = surplus_book()
    plan = sale_only(4)
    sale = plan.legs[0]
    book.admit(plan, ticket="T2")
    assert book.available(plan, sale, ticket="T2", origin="T1") == 4
    book.close("sim", "T2")
    assert book.available(plan, sale, ticket="T2", origin="T1") == 0
    with pytest.raises(SequenceRefusal, match="reserva indisponível"):
        book.reserve(plan, sale, "borrow", 1, ticket="T2", origin="T1")
    assert book.available(plan, sale, ticket="T3", origin="T1") == 4


def test_n4_live_reservation_survives_borrower_stop_until_exact_release() -> None:
    """A cedente recupera apenas o saldo vivo que a venue confirmou cancelado."""
    book, _ = surplus_book()
    plan = sale_only(4)
    sale = plan.legs[0]
    book.admit(plan, ticket="T2")
    book.reserve(plan, sale, "borrow", 4, ticket="T2", origin="T1")

    def balances() -> tuple[int, int]:
        return (book.available(plan, sale, ticket="T3", origin="T1"),
                book.available(plan, sale, ticket="T2", origin="T1"))

    book.close("sim", "T2")
    assert balances() == (0, 0)
    book.confirm_sale("sim", "borrow", "late", 1)
    assert balances() == (0, 0)
    with pytest.raises(SequenceRefusal, match="saldo final divergente"):
        book.confirm_release("sim", "borrow", 2)
    assert balances() == (0, 0)
    book.confirm_release("sim", "borrow", 3)
    assert balances() == (3, 0)


def zeroing_draft(n: int, lot: int = 1) -> TicketDraft:
    """Venda de A a um real por unidade, com limites assinados."""
    return draft(leg("A", Side.SELL, "1", n, lot), net=str(-n), gross=str(n))


def test_z1_free_long_sale_plan_and_partial_exposure() -> None:
    p = position(holding("A", 10), holding("B", -6))
    flat = position(holding("A", 10), holding("B"))
    single = Position(account="sim", holdings=(holding("A", 7),), pairs=())
    ticket = zeroing_draft(4)
    for n, photo in [(4, p), (10, flat), (7, single)]:
        one = zeroing_draft(n)
        plan = plan_legs(one, photo)
        assert plan.legs == one.legs and plan.dependencies == (("A", "A", True),)
        assert plan.protection_for(one.legs[0]) == "A"
    for n, photo in [(5, p), (11, flat)]:
        with pytest.raises(SequenceRefusal, match="saldo livre insuficiente"):
            plan_legs(zeroing_draft(n), photo)
    for one, photo in [(zeroing_draft(1), position()), (draft(leg("B", Side.SELL, "1.50", 1)), p)]:
        with pytest.raises(SequenceRefusal, match="pareamento ausente ou ambíguo"):
            plan_legs(one, photo)
    assert close_plan().dependencies == (("A", "B", True),)
    with pytest.raises(SequenceRefusal, match="autorização sem venda correspondente"):
        plan_legs(authorized(ticket, ("A", "T1", 4)), p)
    with pytest.raises(SequenceRefusal):
        partial_exposure(ticket)
    assert partial_exposure(ticket, zeroing=True) == 0
    assert partial_exposure(ticket, zeroing=True, known_costs=D(".07")) == D(".07")


def test_z2_shared_free_long_balance_is_exclusive() -> None:
    p = position(holding("A", 10), holding("B", -6))
    plan = plan_legs(zeroing_draft(4), p)
    sale, = plan.legs
    book = ReservationBook()
    book.admit(plan, ticket="T1")

    def balances() -> tuple[int, int]:
        return (book.available(plan, sale, ticket="T1"), book.available(plan, sale, ticket="T2"))

    assert balances() == (4, 4)
    assert book.available(plan, sale, ticket="T1", origin="T9") == 0
    book.reserve(plan, sale, "one", 3, ticket="T1")
    assert balances() == (1, 1)
    book.confirm_sale("sim", "one", "fill", 2)
    book.confirm_release("sim", "one", 1)
    assert balances() == (2, 2)
    book.admit(plan, ticket="T2")
    book.reserve(plan, sale, "two", 2, ticket="T2")
    assert balances() == (0, 0)
    for admission in (book.admissible, book.admit):
        with pytest.raises(SequenceRefusal, match="saldo livre indisponível"):
            admission(plan_legs(zeroing_draft(1), p), ticket="T3")
    with pytest.raises(SequenceRefusal, match="reserva indisponível"):
        book.reserve(plan, sale, "three", 1, ticket="T1")
    book.close("sim", "T1")
    book.confirm_release("sim", "two", 2)
    assert balances() == (0, 2)


def test_z3_limits_by_lot_leg_and_account() -> None:
    p = position(holding("A", 10), holding("B", -6))
    book = ReservationBook()
    one = plan_legs(zeroing_draft(1), p)
    four = plan_legs(zeroing_draft(4, 2), p)
    book.reserve(one, one.legs[0], "one", 1, ticket="T9")
    assert book.available(four, four.legs[0], ticket="T1") == 2
    book = ReservationBook()
    p = position(holding("A", 10), holding("B"))
    two = plan_legs(zeroing_draft(2), p)
    nine = plan_legs(zeroing_draft(9), p)
    assert book.available(two, two.legs[0], ticket="T1") == 2
    book.reserve(two, two.legs[0], "one", 2, ticket="T1")
    assert book.available(two, two.legs[0], ticket="T1") == 0
    assert book.available(nine, nine.legs[0], ticket="T2") == 8
    other = plan_legs(zeroing_draft(9), position(*p.holdings, account="outra"))
    assert book.available(other, other.legs[0], ticket="T1") == 9


def test_z4_free_stock_and_confirmed_buybacks_have_separate_capacity() -> None:
    p = position(holding("A", 10), holding("B", -6))
    buy = leg("B", Side.BUY, "1.50", 6)
    paired_sale = leg("A", Side.SELL, "1", 6)
    paired = plan_legs(draft(paired_sale, buy, net="3", gross="15"), p)
    free_sale = plan_legs(zeroing_draft(4), p)
    book = ReservationBook()
    book.admit(paired, ticket="T1")
    book.admit(free_sale, ticket="T2")

    def balances() -> tuple[int, int]:
        return (book.available(paired, paired_sale, ticket="T1"),
                book.available(free_sale, free_sale.legs[0], ticket="T2"))

    assert balances() == (0, 4)
    book.confirm_buy(paired, buy, "fill", 6, ticket="T1")
    assert balances() == (6, 4)
    book.reserve(paired, paired_sale, "paired", 6, ticket="T1")
    assert balances() == (0, 4)
    book.reserve(free_sale, free_sale.legs[0], "free", 4, ticket="T2")
    assert balances() == (0, 0)
    with pytest.raises(SequenceRefusal, match="saldo livre indisponível"):
        book.admissible(plan_legs(zeroing_draft(1), p), ticket="T3")


def test_z3_orders_on_other_free_series_do_not_reduce_capacity() -> None:
    """Na mesma conta, vender X não compromete o saldo inicial de A nem o inverso."""
    photo = Position(account="sim", holdings=(holding("A", 4), holding("X", 3)), pairs=())
    a = plan_legs(zeroing_draft(4), photo)
    x = plan_legs(draft(leg("X", Side.SELL, "1", 3), net="-3", gross="3"), photo)
    book = ReservationBook()
    book.reserve(x, x.legs[0], "x", 2, ticket="T1")
    book.confirm_sale("sim", "x", "executed-x", 1)
    assert book.available(a, a.legs[0], ticket="T2") == 4
    book.reserve(a, a.legs[0], "a", 4, ticket="T2")
    assert book.available(x, x.legs[0], ticket="T1") == 1
