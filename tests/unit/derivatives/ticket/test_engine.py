"""Cenários manuais do motor com venue, gate, reservas e recibo reais do simulador."""
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from backend.derivatives.ticket.engine import AccountHalts, EngineRefusal, TicketEngine
from backend.derivatives.ticket.gate import Action, DecisionLedger, HumanDecision, issue
from backend.derivatives.ticket.guards import BookView, DeadlineRefusal
from backend.derivatives.ticket.models import EditableField, FieldRef, Leg, MarketSuggestion, Side
from backend.derivatives.ticket.paper_venue import PaperVenue
from backend.derivatives.ticket.receipt import Receipt
from backend.derivatives.ticket.replay import AuctionFill, CancelRejected, ReplayEvent, VenueTimeout
from backend.derivatives.ticket.sequencing import (
    LegPlan, Position, ReservationBook, SequenceRefusal, plan_legs,
)
from backend.derivatives.ticket.state import Event as E, OrderState as O, TicketState as T
from backend.derivatives.ticket.trigger import Source, TriggerSpec, spec_digest
from backend.derivatives.ticket.venue import OrderSnapshot, VenueOrder, VenueReport
from config.ticket_sim_config_model import load_ticket_sim_config
from tests.unit.derivatives.ticket.test_guards import NOW, CLOSE, quote
from tests.unit.derivatives.ticket.test_models import PRICE
from tests.unit.derivatives.ticket.test_sequencing import (
    BUY, SELL, authorized, close_plan, draft, holding, leg, position, sale_only,
)
from tests.unit.derivatives.ticket.test_trigger import SPEC, trade

A, B = "T1:A:1", "T1:B:1"
END = NOW.replace(hour=15)


def at(second: float) -> datetime:
    """Instante sintético em segundos desde a abertura do cenário."""
    return NOW + timedelta(seconds=second)


class Session:
    """Dirige o replay; cada motor recebe somente relatórios próprios."""
    def __init__(self) -> None:
        self.paper = PaperVenue(CLOSE)
        self.venue = Mock(wraps=self.paper)
        self.book = BookView()
        self.res = ReservationBook()
        self.ledger = DecisionLedger()
        self.halts = AccountHalts()
        self.receipts: list[Receipt] = []
        self.engines: list[TicketEngine] = []
        self.nonce = 0
        self.q("A", 0)
        self.q("B", 1)

    def engine(self, ticket: str, pos: Position) -> TicketEngine:
        """Constrói um motor com o livro e a venue desta sessão."""
        r = Receipt()
        self.receipts.append(r)
        e = TicketEngine(ticket, pos, venue=self.venue, book=self.book,
                         reservations=self.res, ledger=self.ledger, halts=self.halts,
                         receipt=r, config=load_ticket_sim_config())
        self.engines.append(e)
        return e

    def new(self, pos: Position | None = None, closing: bool = False, **changes: object
            ) -> TicketEngine:
        """Propõe a boleta de referência antes de decidir."""
        e = self.engine(f"T{len(self.receipts) + 1}", pos or position())
        legs = (leg("A", Side.SELL, "1"), leg("B", Side.BUY, "1.50")) if closing else (BUY, SELL)
        d = draft(*legs, net="5" if closing else "-5")
        e.propose(d.model_copy(update=dict(send_deadline=END, order_validity=CLOSE) | changes), NOW)
        return e

    def dec(self, e: TicketEngine, action: Action = Action.EXECUTE, **kwargs: object
            ) -> HumanDecision:
        """Emite uma decisão da versão corrente quando a ação exige prévia."""
        self.nonce += 1
        return issue(action, ticket=f"T{self.engines.index(e)+1}", nonce=f"n{self.nonce}",
                     issued_at=NOW, expires_at=END,
                     preview=e.preview if action in (Action.EXECUTE, Action.ARM) else None,
                     **kwargs)

    def step(self, ev: ReplayEvent) -> None:
        """Atualiza a foto e a venue uma vez por evento."""
        self.book.advance(ev)
        reports = self.paper.advance(ev)
        for e in self.engines:
            e.on_reports([r for r in reports if r.order_id in e.orders], ev.ts)
            e.on_market(ev)

    def q(self, symbol: str, sec: float, *, bid: str | None = None, ask: str | None = None,
          size: int = 50, phase: str = "CONTINUOUS") -> None:
        """Envia cotação com o lado omitido igual ao da abertura."""
        q = quote(symbol, bid=bid or (".95" if symbol=="A" else "1.45"),
                  ask=ask or ("1.02" if symbol=="A" else "1.55"),
                  bs=size, size=size, phase=phase)
        self.step(q.model_copy(update={"ts":at(sec)}))

    def confirmed(self) -> TicketEngine:
        """Confirma a proposta de referência às 14:00:02."""
        e = self.new()
        e.confirm(self.dec(e), at(2))
        return e

    def submitted(self) -> list[tuple[str, int, D, datetime]]:
        """Pedidos efetivos na fronteira da venue."""
        return [(o.order_id, o.quantity, o.limit_price, ts)
                for (o, ts), _ in self.venue.submit.call_args_list]

    def cancel(self, e: TicketEngine, oid: str, sec: int) -> None:
        """Cancela o saldo somente com decisão emitida para a ordem."""
        e.cancel(oid, self.dec(e, Action.CANCEL_ORDER, order_id=oid), at(sec))

    def arm(self, e: TicketEngine, spec: TriggerSpec = SPEC) -> None:
        """Arma sem consumir decisão de execução."""
        e.arm(spec, self.dec(e, Action.ARM, spec_digest=spec_digest(spec)), at(2))


@pytest.fixture
def s() -> Iterator[Session]:
    """Verifica integridade e representação do dinheiro ao fim de cada cenário."""
    session = Session()
    yield session
    def check(data: object) -> None:
        if isinstance(data, dict):
            for key, v in data.items():
                if key in {"price","limit_price","net_limit","gross_cap","partial_exposure"}:
                    assert isinstance(v, str)
                check(v)
        elif isinstance(data, list):
            for v in data:
                check(v)
    for receipt in session.receipts:
        assert receipt.verify()
        for record in receipt.events:
            check(json.loads(record.payload))


@pytest.mark.parametrize("kind", ["CALL", "PUT"], ids=["S01", "S02"])
def test_complete(s: Session, kind: str) -> None:
    """Mesmos limites e sequência factual para calls e puts."""
    rows = [holding(x).model_copy(update={"kind":kind}) for x in ("A","B")]
    e = s.new(position(*rows))
    e.confirm(s.dec(e), at(2))
    s.q("A",3,ask="1")
    s.q("B",4,bid="1.50")
    assert e.state == T.COMPLETED and dict(e.orders) == {A:O.FILLED,B:O.FILLED}
    assert s.submitted() == [(A,10,D("1"),at(2)), (B,10,D("1.50"),at(3))]
    assert [r.kind for r in s.receipts[0].events] == [
        E.PREVIEW,E.CONFIRM,E.START,E.VENUE_LIVE,E.VENUE_FILL,E.VENUE_LIVE,E.VENUE_FILL,E.COMPLETE]


@pytest.mark.parametrize("again", [False,True], ids=["S03","S22"])
def test_expire_uncrossed_sale(s: Session, again: bool) -> None:
    """Preço da venda permanece assinado até a expiração nativa."""
    e = s.confirmed()
    s.q("A",3,ask="1")
    s.q("B",4,bid="1.49")
    if again:
        s.q("B",5,bid="1.49")
    s.q("A",25200)
    assert s.submitted() == [(A,10,D("1"),at(2)),(B,10,D("1.50"),at(3))]
    assert e.state == T.STOPPED and e.orders[A]==O.FILLED and e.orders[B]==O.EXPIRED
    assert s.paper.poll(B) == (O.EXPIRED,0,0)


def free(s: Session, ticket: str = "T1") -> int:
    """Saldo para a próxima venda da boleta de referência."""
    p = plan_legs(draft(BUY,SELL).model_copy(update=dict(send_deadline=END,order_validity=CLOSE)),
                  position())
    return s.res.available(p, SELL, ticket=ticket)


def test_s04_partial(s: Session) -> None:
    e=s.confirmed()
    s.q("A",3,ask="1",size=3)
    assert e.orders[A]==O.PARTIAL and e.state==T.WORKING and free(s)==0
    assert s.submitted()==[(A,10,D("1"),at(2)),(B,3,D("1.50"),at(3))]


@pytest.mark.parametrize("cancel", [True,False], ids=["S05","X7"])
def test_auction(s: Session, cancel: bool) -> None:
    e=s.confirmed()
    s.q("A",3,ask="1",size=3)
    s.q("A",4,ask="1",phase="AUCTION")
    if cancel:
        s.cancel(e,A,4)
        assert e.orders[A]==O.CANCEL_REQUESTED
    s.step(AuctionFill(type="auction_fill",seq=5,ts=at(5),symbol="A",price=D("1"),size=1))
    if cancel:
        s.step(CancelRejected(type="cancel_rejected",seq=6,ts=at(6),order=A))
    assert e.orders[A]==O.PARTIAL and s.paper.poll(A)==(O.PARTIAL,4,6)
    assert e.state==T.WORKING and free(s)==1 and len(s.submitted())==2


def test_s06_discard(s: Session) -> None:
    e=s.new()
    e.discard(s.dec(e,Action.DISCARD),at(2))
    assert e.state==T.DENIED and not e.orders and not s.venue.mock_calls


def test_s07_cancel_buy(s: Session) -> None:
    e=s.confirmed()
    s.cancel(e,A,2)
    assert e.orders[A]==O.CANCEL_REQUESTED
    s.q("A",3)
    assert e.orders[A]==O.CANCELLED and e.state==T.STOPPED


def test_s08_cancel_partial_sale(s: Session) -> None:
    e=s.confirmed()
    s.q("A",3,ask="1")
    s.cancel(e,B,3)
    s.q("B",4,bid="1.50",size=4)
    assert e.state==T.STOPPED and e.orders[B]==O.CANCELLED and free(s)==0
    assert third_party_surplus(s) == 6
    assert s.paper.poll(B)==(O.CANCELLED,4,0) and len(s.submitted())==2
    assert [r.kind for r in s.receipts[0].events][-3:]==[E.VENUE_PARTIAL,E.VENUE_CANCELLED,E.STOP]


def test_s09_shared_coverage(s: Session) -> None:
    one=s.confirmed()
    two=s.new()
    two.confirm(s.dec(two),at(2))
    s.q("A",3,ask="1",size=3)
    assert one.orders[A]==O.PARTIAL and dict(two.orders)=={"T2:A:1":O.LIVE}
    assert s.submitted()[-1]==(B,3,D("1.50"),at(3)) and free(s,"T2")==0


def test_s10_trigger_only_then_confirm(s: Session) -> None:
    e=s.new()
    s.arm(e)
    s.q("A",3,ask="1")
    s.q("A",4,ask=".99")
    assert e.state==T.TRIGGERED and not e.orders and not s.submitted()
    assert [r.kind for r in s.receipts[0].events].count(E.TRIGGER)==1
    e.confirm(s.dec(e),at(5))
    assert e.state==T.WORKING and e.orders[A]==O.LIVE


def test_s11_reused_arm(s: Session) -> None:
    e=s.new()
    s.q("A",3,ask="1")
    d=s.dec(e,Action.ARM,spec_digest=spec_digest(SPEC))
    with pytest.raises(ValueError, match="condição já verdadeira"):
        e.arm(SPEC,d,at(4))
    assert e.state==T.DRAFT
    s.q("A",4)
    e.arm(SPEC,d,at(5))
    assert e.state==T.ARMED and not s.submitted()


def test_s12_strategy(s: Session) -> None:
    e=s.new()
    s.arm(e,SPEC.model_copy(update=dict(source=Source.STRATEGY_TRADE,
                                                   threshold=D(".50"),min_size=1)))
    s.step(trade("SIMPLE",ts=at(3)))
    assert e.state==T.ARMED
    s.step(trade("STRATEGY",ts=at(4)))
    assert e.state==T.TRIGGERED


def test_s13_expired_trigger(s: Session) -> None:
    e=s.new()
    s.arm(e)
    s.q("A",3600.000001,ask="1")
    assert e.state==T.EXPIRED
    with pytest.raises(EngineRefusal):
        e.confirm(s.dec(e),at(3601))
    assert not s.submitted()


def test_s14_refresh_and_cancel_blocked_market(s: Session) -> None:
    e=s.new()
    d=s.dec(e)
    with pytest.raises(EngineRefusal,match="cotação vencida"):
        e.confirm(d,at(10))
    assert not s.submitted() and not e.orders and e.state==T.DRAFT
    s.q("A",10)
    s.q("B",11)
    e.confirm(d,at(12))
    s.q("A",13,phase="AUCTION")
    s.cancel(e,A,13)
    assert e.orders[A]==O.CANCEL_REQUESTED


def test_s15_native_expiry(s: Session) -> None:
    e=s.confirmed()
    s.q("A",3,ask="1",size=3)
    s.q("A",3601,ask="1")
    s.q("B",25200)
    assert e.state==T.STOPPED and dict(e.orders)=={A:O.FILLED,B:O.EXPIRED}
    assert len(s.submitted())==2 and s.paper.poll(A)==(O.FILLED,10,0)


@pytest.mark.parametrize(("changes","message"), [
    (dict(order_validity=NOW.replace(hour=20)),"validade que a venue não garante"),
    (dict(net_limit=D("-5.01")),None),
],ids=["S16","X1"])
def test_refused_confirmation_preserves_nonce(s: Session, changes: dict, message: str|None) -> None:
    e=s.new(**changes)
    d=s.dec(e)
    with pytest.raises(ValueError,match=message):
        e.confirm(d,at(2))
    assert e.state==T.DRAFT and not s.submitted() and not e.orders
    s.ledger.consume(d,action=Action.EXECUTE,ticket="T1",now=at(2),preview=e.preview)


def test_s17_edit_and_locked_refresh(s: Session) -> None:
    e=s.new()
    old=s.dec(e)
    e.edit(PRICE,D(".99"),at(2))
    e.refresh(MarketSuggestion("other",{PRICE:D("1.01")}),at(2))
    assert e.preview.version==2 and len(s.receipts[0].events)==2
    with pytest.raises(ValueError,match="resumo divergente"):
        e.confirm(old,at(2))
    e.confirm(s.dec(e),at(2))
    assert s.submitted()==[(A,10,D(".99"),at(2))]


def test_s18_duplicate_confirm(s: Session) -> None:
    e=s.new()
    d=s.dec(e)
    e.confirm(d,at(2))
    with pytest.raises(EngineRefusal):
        e.confirm(d,at(2))
    assert len(s.submitted())==1


def timeout(s: Session) -> TicketEngine:
    """Envio registrado cujo retorno é incerto."""
    s.step(VenueTimeout(type="timeout",seq=3,ts=at(2),call="submit",registered=True))
    e=s.confirmed()
    assert e.orders[A]==O.UNCERTAIN and e.state==T.UNCERTAIN and s.halts.blocked("sim")
    return e


def test_s19_reconcile_and_resume(s: Session) -> None:
    e=timeout(s)
    other=s.new()
    s.q("A",3,ask="1")
    assert e.orders[A]==O.UNCERTAIN and len(s.submitted())==1
    d=s.dec(other)
    with pytest.raises(EngineRefusal):
        other.confirm(d,at(3))
    s.ledger.consume(d,action=Action.EXECUTE,ticket="T2",now=at(3),preview=other.preview)
    e.reconcile(A,at(3))
    assert e.orders[A]==O.FILLED and e.state==T.WORKING and e.paused and not s.halts.blocked("sim")
    e.resume(s.dec(e,Action.RESUME),at(3))
    assert s.submitted()==[(A,10,D("1"),at(2)),(B,10,D("1.50"),at(3))]


def test_s20_pause_fill_resume(s: Session) -> None:
    e=s.confirmed()
    e.pause(at(2))
    assert s.paper.poll(A)==(O.LIVE,0,10)
    s.q("A",3,ask="1")
    assert e.orders[A]==O.FILLED and len(s.submitted())==1
    e.resume(s.dec(e,Action.RESUME),at(3))
    assert s.submitted()[-1]==(B,10,D("1.50"),at(3))
    s.venue.request_cancel.assert_not_called()


def test_s21_close(s: Session) -> None:
    e=s.new(position(holding("A",10),holding("B",-10)),closing=True)
    assert e.preview.partial_exposure==D("15.00")
    e.confirm(s.dec(e),at(2))
    s.q("B",3,ask="1.50")
    s.q("A",4,bid="1",ask="1.05")
    assert e.state==T.COMPLETED
    assert s.submitted()==[(B,10,D("1.50"),at(2)),(A,10,D("1"),at(3))]


def test_x2_rejected(s: Session) -> None:
    s.venue.submit.side_effect=lambda order,now: VenueReport(order.order_id,E.VENUE_REJECTED,
                                                             None,None,now)
    e=s.confirmed()
    assert dict(e.orders)=={A:O.REJECTED} and e.state==T.STOPPED


def test_x3_temporary_block(s: Session) -> None:
    e=s.confirmed()
    s.q("A",7,ask="1")
    assert e.orders[A]==O.FILLED and len(s.submitted())==1 and e.state==T.WORKING
    s.q("B",8)
    assert s.submitted()[-1]==(B,10,D("1.50"),at(8))


def test_x4_edit_armed(s: Session) -> None:
    e=s.new()
    s.arm(e)
    with pytest.raises(EngineRefusal):
        e.edit(PRICE,D(".99"),at(2))


def test_x5_cancel_other_and_terminal(s: Session) -> None:
    e=s.confirmed()
    s.q("A",3,ask="1")
    for oid in ["T2:A:1",A]:
        d=s.dec(e,Action.CANCEL_ORDER,order_id=oid)
        with pytest.raises(EngineRefusal):
            e.cancel(oid,d,at(3))
        s.ledger.consume(d,action=Action.CANCEL_ORDER,ticket="T1",now=at(3),order_id=oid)


def test_x6_resume_uncertain(s: Session) -> None:
    e=timeout(s)
    d=s.dec(e,Action.RESUME)
    with pytest.raises(EngineRefusal):
        e.resume(d,at(2))
    s.ledger.consume(d,action=Action.RESUME,ticket="T1",now=at(2))


def test_x8_caution(s: Session) -> None:
    s.q("B",1,bid="1.44")
    e=s.confirmed()
    assert e.orders[A]==O.LIVE


@pytest.mark.parametrize("snapshot", [None, OrderSnapshot(O.PARTIAL, 1, 9),
                                      OrderSnapshot(O.FILLED, 9, 0)])
def test_poll_mismatch_is_atomic(s: Session, snapshot: OrderSnapshot | None) -> None:
    e=timeout(s)
    s.q("A",3,ask="1")
    s.venue.poll.return_value=snapshot
    before=s.receipts[0].events
    with pytest.raises(EngineRefusal):
        e.reconcile(A,at(3))
    assert e.orders[A]==O.UNCERTAIN and s.halts.blocked("sim") and free(s)==0
    assert s.receipts[0].events==before


def test_send_deadline_with_both_books_fresh(s: Session) -> None:
    """Isola prazo de envio da cotação vencida, que também protege S15."""
    e = s.confirmed()
    s.q("B", 3599)
    s.q("A", 3601, ask="1")
    assert e.orders[A] == O.FILLED
    assert e.state == T.STOPPED and len(s.submitted()) == 1


def test_s01_audit_of_actual_price_quantity_and_signed_request(s: Session) -> None:
    """Recibo usa texto para o preço real e conserva quantidade e ID de execução."""
    e = s.confirmed()
    s.q("A", 3, ask=".98")
    s.q("B", 4, bid="1.50")
    assert e.state == T.COMPLETED
    fills = [json.loads(r.payload) for r in s.receipts[0].events if r.kind == E.VENUE_FILL]
    assert [(f["execution"], f["quantity"], D(f["price"])) for f in fills] == [
        (A+"#1", 10, D(".98")), (B+"#1", 10, D("1.50"))]
    assert all(type(f["price"]) is str for f in fills)


def test_reconcile_unregistered_submit_does_not_resend(s: Session) -> None:
    """Ausência em poll sem fatos posteriores encerra a tentativa."""
    s.step(VenueTimeout(type="timeout", seq=3, ts=at(2), call="submit", registered=False))
    e = s.confirmed()
    e.reconcile(A, at(3))
    assert e.orders[A] == O.REJECTED and e.state == T.STOPPED
    assert not s.halts.blocked("sim") and len(s.submitted()) == 1


def test_uncertain_sale_reserves_until_reconciled(s: Session) -> None:
    """Venda registrada ocupa o saldo durante timeout e converte a reserva só após poll."""
    e = s.confirmed()
    s.step(VenueTimeout(type="timeout", seq=3, ts=at(2), call="submit", registered=True))
    s.q("A", 3, ask="1")
    assert e.orders[B] == O.UNCERTAIN and free(s) == 0
    s.q("B", 4, bid="1.50")
    assert e.state == T.UNCERTAIN and e.orders[B] == O.UNCERTAIN
    e.reconcile(B, at(4))
    assert e.orders[B] == O.FILLED and e.state == T.COMPLETED and free(s) == 0


def test_disarm_and_rejected_second_propose(s: Session) -> None:
    e = s.new()
    with pytest.raises(EngineRefusal):
        e.propose(draft(BUY, SELL), at(2))
    s.arm(e)
    e.disarm(s.dec(e, Action.DISARM), at(2))
    assert e.state == T.DENIED and not s.submitted()


@pytest.mark.parametrize("cancel", [False, True], ids=["C1", "C2"])
def test_closing_capacity_precedes_nonce_and_submission(s: Session, cancel: bool) -> None:
    p = position(holding("A", 10), holding("B", -10))
    one, two = s.new(p, closing=True), s.new(p, closing=True)
    one.confirm(s.dec(one), at(2))
    decision = s.dec(two)
    with pytest.raises(SequenceRefusal):
        two.confirm(decision, at(2))
    assert two.state == T.DRAFT and not two.orders and len(s.submitted()) == 1
    if cancel:
        s.cancel(one, B, 2)
        s.q("B", 3)
        assert one.orders[B] == O.CANCELLED and one.state == T.STOPPED
        two.confirm(decision, at(3))
        assert s.submitted()[-1] == ("T2:B:1", 10, D("1.50"), at(3))
    else:
        s.ledger.consume(decision, action=Action.EXECUTE, ticket="T2", now=at(2),
                         preview=two.preview)
        s.q("B", 3, ask="1.50")
        assert one.orders[B] == O.FILLED
        assert s.submitted()[-1] == (A, 10, D("1.00"), at(3))
    assert len(s.submitted()) == 2


def test_c3_divergent_photo_cannot_consume_or_submit(s: Session) -> None:
    s.confirmed()
    s.q("A", 3, ask="1.00")
    two = s.new(position(holding("A", 5), holding("B")))
    decision = s.dec(two)
    with pytest.raises(SequenceRefusal, match="foto divergente; conciliação necessária"):
        two.confirm(decision, at(3))
    assert two.state == T.DRAFT and not two.orders
    assert all(oid.startswith("T1:") for oid, *_ in s.submitted())
    s.ledger.consume(decision, action=Action.EXECUTE, ticket="T2", now=at(3), preview=two.preview)


class FirstBuyFails(ReservationBook):
    """A primeira contabilização falha depois de uma execução factual da venue."""
    failed = False

    def confirm_buy(self, plan: LegPlan, leg: Leg, execution: str, quantity: int, *,
                    ticket: str) -> None:
        if not self.failed:
            self.failed = True
            raise SequenceRefusal("falha contábil sintética")
        super().confirm_buy(plan, leg, execution, quantity, ticket=ticket)


@pytest.mark.parametrize("uncertain", [False, True], ids=["C4", "C5"])
def test_fill_survives_accounting_refusal(s: Session, uncertain: bool) -> None:
    s.res = FirstBuyFails()
    e = timeout(s) if uncertain else s.confirmed()
    s.q("A", 3, ask="1.00")
    if uncertain:
        e.reconcile(A, at(3))
    assert e.orders[A] == O.FILLED and s.paper.poll(A) == (O.FILLED, 10, 0)
    events = s.receipts[0].events
    index = next(i for i, r in enumerate(events) if r.kind == E.VENUE_FILL)
    fill = json.loads(events[index].payload)
    assert (fill["quantity"], fill["price"]) == (10, "1.00")
    assert events[index+1].kind == E.DIVERGENCE
    assert json.loads(events[index+1].payload)["order_id"] == A
    assert e.state == T.STOPPED and s.halts.blocked("sim") and len(s.submitted()) == 1
    if uncertain:
        with pytest.raises(EngineRefusal):
            e.reconcile(A, at(3))
        assert events == s.receipts[0].events and s.halts.blocked("sim")
    else:
        two = s.new()
        decision = s.dec(two)
        with pytest.raises(EngineRefusal):
            two.confirm(decision, at(3))
        s.ledger.consume(decision, action=Action.EXECUTE, ticket="T2", now=at(3),
                         preview=two.preview)


def test_c6_rejected_sale_is_final(s: Session) -> None:
    def submit(order: VenueOrder, now: datetime) -> VenueReport:
        if order.side == Side.SELL:
            return VenueReport(order.order_id, E.VENUE_REJECTED, None, None, now)
        return s.paper.submit(order, now)
    s.venue.submit.side_effect = submit
    e = s.confirmed()
    s.q("A", 3, ask="1")
    assert dict(e.orders) == {A: O.FILLED, B: O.REJECTED} and e.state == T.STOPPED
    s.q("B", 4)
    s.q("A", 5)
    assert len(s.submitted()) == 2 and free(s) == 0
    assert third_party_surplus(s) == 10


def test_l1_recheck_gross_after_favorable_partial(s: Session) -> None:
    e = s.confirmed()
    s.q("A", 3, ask="1", size=3)
    s.q("B", 4, bid="1.54")
    s.q("A", 5, ask="1", size=7)
    assert e.state == T.STOPPED
    assert [(oid, n) for oid, n, _, _ in s.submitted()] == [(A, 10), (B, 3)]
    fills = [json.loads(r.payload) for r in s.receipts[0].events if r.kind == E.VENUE_FILL]
    assert fills[0]["price"] == "1.54" and fills[0]["quantity"] == 3


def test_l2_pause_never_calls_venue(s: Session) -> None:
    e = s.confirmed()
    before = list(s.venue.mock_calls)
    e.pause(at(2))
    assert s.venue.mock_calls == before
    s.q("A", 3, ask="1")
    e.resume(s.dec(e, Action.RESUME), at(3))
    assert s.submitted()[-1] == (B, 10, D("1.50"), at(3))


def test_l3_release_is_per_order(s: Session) -> None:
    e = s.confirmed()
    s.q("A", 3, ask="1", size=3)
    s.q("B", 4, bid="1.50", size=3)
    s.q("A", 5, ask="1", size=4)
    s.cancel(e, "T1:B:2", 5)
    s.q("B", 6, bid="1.45")
    assert [(oid, n) for oid, n, _, _ in s.submitted()] == [(A, 10), (B, 3), ("T1:B:2", 4)]
    assert e.orders[B] == O.FILLED and e.orders["T1:B:2"] == O.CANCELLED
    assert free(s) == 4 and e.state == T.WORKING


def test_r15_continues_batch_after_partial_buy_refusal(s: Session) -> None:
    s.res = FirstBuyFails()
    engine = s.confirmed()
    reports = [VenueReport(A, E.VENUE_PARTIAL, 3, D("1.00"), at(3)),
               VenueReport(A, E.VENUE_FILL, 7, D("1.00"), at(4))]
    engine.on_reports(reports, at(4))
    facts = [(r.kind, json.loads(r.payload)) for r in s.receipts[0].events
             if r.kind in (E.VENUE_PARTIAL, E.VENUE_FILL, E.DIVERGENCE)]
    assert [(kind, data.get("quantity")) for kind, data in facts] == [
        (E.VENUE_PARTIAL, 3), (E.DIVERGENCE, None), (E.VENUE_FILL, 7)]
    assert engine.orders[A] == O.FILLED and s.halts.blocked("sim")
    assert free(s) == 7 and len(s.submitted()) == 1


@pytest.mark.parametrize("ticket", ["T:X", "T#1", "T 1", "", "Té", "Tİ", "T\n"])
def test_i1_invalid_ticket_refused_at_construction(s: Session, ticket: str) -> None:
    """O domínio ASCII exclui separadores, espaços e a quebra de linha final."""
    with pytest.raises(EngineRefusal):
        s.engine(ticket, position())


def test_i2_valid_ticket_round_trips_into_order_id(s: Session) -> None:
    """Toda a pontuação autorizada e a caixa da boleta permanecem no identificador."""
    ticket = "T-1_a.b"
    e = s.engine(ticket, position())
    e.propose(draft(BUY, SELL).model_copy(update={"send_deadline": END, "order_validity": CLOSE}),
              NOW)
    d = issue(Action.EXECUTE, ticket=ticket, nonce="n1", issued_at=NOW, expires_at=END,
              preview=e.preview)
    e.confirm(d, at(2))
    assert dict(e.orders) == {"T-1_a.b:A:1": O.LIVE}


def test_i2_restored_legs_preserve_valid_symbol_in_order_id(s: Session) -> None:
    """A proposta reconstrói pernas serializadas e conserva a pontuação assinada."""
    symbol = "X-1_A.B"
    pos = Position(account="sim", holdings=(holding(symbol),), pairs=())
    e = s.engine("T1", pos)
    d = draft(leg(symbol, Side.BUY, "1.00"), net="10", gross="10")
    restored = d.model_copy(update={"legs": tuple(row.model_dump() for row in d.legs),
                                    "send_deadline": END, "order_validity": CLOSE})
    s.q(symbol, 1, bid=".95", ask="1.02")
    e.propose(restored, NOW)
    e.confirm(s.dec(e), at(2))
    assert dict(e.orders) == {"T1:X-1_A.B:1": O.LIVE}


def test_i3_restored_symbol_still_refused_before_planning(s: Session) -> None:
    """Reconstruir a perna preserva a recusa tipada e o recibo vazio."""
    e = s.engine("T1", position())
    d = draft(BUY, SELL)
    rows = (BUY.model_dump() | {"symbol": "X:A"}, SELL.model_dump())
    with pytest.raises(EngineRefusal):
        e.propose(d.model_copy(update={"legs": rows}), NOW)
    assert e.preview is None and not s.receipts[0].events


@pytest.mark.parametrize(("buy", "sell"), [("X:A", "B"), ("A", "B#1"), ("A", "É")])
def test_i3_bad_leg_symbol_refused_before_preview(s: Session, buy: str, sell: str) -> None:
    """Uma perna inválida em qualquer posição impede a primeira prévia."""
    pos = Position(account="sim", holdings=(holding(buy), holding(sell)), pairs=((buy, sell),))
    e = s.engine("T1", pos)
    with pytest.raises(EngineRefusal):
        e.propose(draft(leg(buy, Side.BUY, "1"), leg(sell, Side.SELL, "1.50")), NOW)
    assert e.preview is None and not s.receipts[0].events


@pytest.mark.parametrize("refresh", [False, True], ids=["edit", "refresh"])
def test_i3_invalid_symbol_preserves_prior_preview(s: Session, refresh: bool) -> None:
    """A identidade é conferida antes do plano, inclusive em uma nova versão."""
    e = s.new()
    preview, events = e.preview, s.receipts[0].events
    symbol = FieldRef(EditableField.SYMBOL, 0)
    with pytest.raises(EngineRefusal):
        if refresh:
            e.refresh(MarketSuggestion("q2", {symbol: "X:A"}), at(2))
        else:
            e.edit(symbol, "X:A", at(2))
    assert e.preview == preview and s.receipts[0].events == events


def test_g1_missing_order_after_timeout_releases_buyback(s: Session) -> None:
    """A segunda boleta usa a capacidade integral após a rejeição conciliada."""
    pos = close_plan().position
    one, two = s.new(pos, closing=True), s.new(pos, closing=True)
    s.step(VenueTimeout(type="timeout", seq=3, ts=at(2), call="submit", registered=False))
    one.confirm(s.dec(one), at(2))
    assert one.state == T.UNCERTAIN and s.halts.blocked("sim")
    one.reconcile(B, at(3))
    assert s.paper.poll(B) is None and one.orders[B] == O.REJECTED
    assert one.state == T.STOPPED and not s.halts.blocked("sim")
    two.confirm(s.dec(two), at(3))
    assert dict(two.orders) == {"T2:B:1": O.LIVE}


def test_g2_expired_buyback_releases_capacity(s: Session) -> None:
    """Depois do fechamento, o livro admite outra recompra de dez unidades."""
    plan = close_plan()
    e = s.new(plan.position, closing=True)
    e.confirm(s.dec(e), at(2))
    s.q("B", 25200)
    assert e.orders[B] == O.EXPIRED and e.state == T.STOPPED
    s.res.admissible(plan, ticket="T2")


def test_g5_release_refusal_preserves_cancel_and_halts_account(s: Session) -> None:
    """A recusa ao liberar saldo conserva o fato terminal e precede o STOP."""
    class RefuseRelease(ReservationBook):
        """Livro sintético cuja liberação final sempre recusa."""

        def confirm_release(self, account: str, order: str, remaining: int) -> None:
            """Simula uma divergência contábil após o cancelamento."""
            raise SequenceRefusal("saldo divergente")

    s.res = RefuseRelease()
    e = s.confirmed()
    s.q("A", 3, ask="1.00")
    assert dict(e.orders) == {A: O.FILLED, B: O.LIVE}
    s.cancel(e, B, 3)
    s.q("B", 4)
    assert e.orders[B] == O.CANCELLED and s.paper.poll(B) == (O.CANCELLED, 0, 0)
    receipt = s.receipts[0]
    assert [r.kind for r in receipt.events[-3:]] == [E.VENUE_CANCELLED, E.DIVERGENCE, E.STOP]
    assert s.halts.blocked("sim") and receipt.verify() and e.state == T.STOPPED


def test_g7_paused_draft_preserves_nonce_and_receipt(s: Session) -> None:
    """A pausa impede confirmar e preserva a decisão emitida para a prévia."""
    e = s.new()
    e.pause(at(2))
    d = s.dec(e)
    with pytest.raises(EngineRefusal):
        e.confirm(d, at(2))
    assert e.state == T.DRAFT and not e.orders
    assert [r.kind for r in s.receipts[0].events] == [E.PREVIEW, E.PAUSE]
    s.ledger.consume(d, action=Action.EXECUTE, ticket="T1", now=at(2), preview=e.preview)


def test_g8_stale_then_fresh_quote_at_exact_send_deadline(s: Session) -> None:
    """O prazo inclui as 15h tanto na decisão de fechar quanto no envio."""
    e = s.confirmed()
    s.q("A", 3600, ask="1.00")
    assert dict(e.orders) == {A: O.FILLED} and e.state == T.WORKING
    assert len(s.submitted()) == 1
    s.q("B", 3600)
    assert e.orders[B] == O.LIVE and e.state == T.WORKING
    assert s.submitted() == [(A, 10, D("1.00"), at(2)), (B, 10, D("1.50"), END)]


def closing_decision(e: TicketEngine, action: Action = Action.EXECUTE) -> HumanDecision:
    """Emite decisão sintética cuja validade atravessa o fechamento."""
    return issue(action, ticket="T1", nonce=action.value, issued_at=NOW,
                 expires_at=CLOSE + timedelta(seconds=1),
                 preview=e.preview if action == Action.EXECUTE else None)


def closing_quotes(s: Session) -> None:
    """Atualiza os dois lados do spread antes da última janela."""
    s.q("A", 25196)
    s.q("B", 25196.5)


def test_f1_confirm_before_expiration(s: Session) -> None:
    """Uma confirmação ainda válida envia a primeira compra."""
    closing_quotes(s)
    e = s.new(send_deadline=CLOSE)
    now = CLOSE - timedelta(microseconds=1)
    e.confirm(closing_decision(e), now)
    assert e.state == T.WORKING and e.orders == {A: O.LIVE}
    assert s.submitted() == [(A, 10, D("1"), now)]
    assert [r.kind for r in s.receipts[0].events] == [E.PREVIEW, E.CONFIRM, E.START, E.VENUE_LIVE]


@pytest.mark.parametrize("delay", [0, 1], ids=["F2", "F3"])
def test_confirm_at_or_after_expiration(s: Session, delay: int) -> None:
    """A expiração preserva decisão, proposta e recibo."""
    closing_quotes(s)
    e = s.new(send_deadline=CLOSE)
    now = CLOSE + timedelta(microseconds=delay)
    decision = closing_decision(e)
    with pytest.raises(DeadlineRefusal):
        e.confirm(decision, now)
    assert e.state == T.DRAFT and not e.orders and not s.submitted()
    assert [r.kind for r in s.receipts[0].events] == [E.PREVIEW]
    s.ledger.consume(decision, action=Action.EXECUTE, ticket="T1", now=now, preview=e.preview)


def buyback_plan(pos: Position, deadline: datetime = END) -> LegPlan:
    """Reconstrói o plano da segunda boleta para consultar o livro diretamente."""
    proposed = draft(leg("A", Side.SELL, "1"), leg("B", Side.BUY, "1.50"), net="5")
    return plan_legs(proposed.model_copy(update=dict(send_deadline=deadline,
                                                    order_validity=CLOSE)), pos)


def test_f2b_refusal_precedes_buyback_reservation(s: Session) -> None:
    """Recusar no fechamento mantém a capacidade da outra boleta."""
    closing_quotes(s)
    pos = close_plan().position
    first, second = (s.new(pos, closing=True, send_deadline=CLOSE) for _ in range(2))
    with pytest.raises(DeadlineRefusal):
        first.confirm(closing_decision(first), CLOSE)
    assert not s.submitted() and second.preview is not None
    s.res.admissible(buyback_plan(pos, CLOSE), ticket="T2")


@pytest.mark.parametrize("delay", [0, -1], ids=["F4", "F5"])
def test_resume_at_validity_boundary(s: Session, delay: int) -> None:
    """Uma retomada humana também respeita a validade assinada."""
    closing_quotes(s)
    e = s.new(send_deadline=CLOSE)
    start = CLOSE - timedelta(seconds=3)
    e.confirm(closing_decision(e), start)
    e.pause(start)
    s.q("A", 25198, ask="1")
    s.q("B", 25199)
    now = CLOSE + timedelta(microseconds=delay)
    e.resume(closing_decision(e, Action.RESUME), now)
    if delay == 0:
        assert s.submitted() == [(A, 10, D("1"), start)]
        assert e.state == T.STOPPED and e.orders == {A: O.FILLED}
        assert [r.kind for r in s.receipts[0].events] == [
            E.PREVIEW, E.CONFIRM, E.START, E.VENUE_LIVE, E.PAUSE, E.VENUE_FILL, E.RESUME, E.STOP]
    else:
        assert s.submitted() == [(A, 10, D("1"), start), (B, 10, D("1.50"), now)]
        assert e.state == T.WORKING and e.orders == {A: O.FILLED, B: O.LIVE}


def two_buybacks(s: Session, *, registered: bool) -> tuple[Position, TicketEngine, TicketEngine]:
    """T1 ocupa duas recompras, mas somente a primeira chega ao envio."""
    pos = Position(account="sim", holdings=(holding("A", 10), holding("B", -10),
                                           holding("C", -10), holding("D", 10)),
                   pairs=(("A", "B"), ("D", "C")))
    s.q("C", 1)
    s.q("D", 1)
    first = s.engine("T1", pos)
    proposal = draft(leg("C", Side.BUY, "1.50"), leg("B", Side.BUY, "1.50"),
                     leg("D", Side.SELL, "1"), leg("A", Side.SELL, "1"), net="10", gross="50")
    first.propose(proposal.model_copy(update=dict(send_deadline=END, order_validity=CLOSE)), NOW)
    second = s.new(pos, closing=True)
    s.step(VenueTimeout(type="timeout", seq=3, ts=at(2), call="submit", registered=registered))
    first.confirm(s.dec(first), at(2))
    assert first.state == T.UNCERTAIN and first.orders == {"T1:C:1": O.UNCERTAIN}
    assert s.submitted() == [("T1:C:1", 10, D("1.50"), at(2))]
    return pos, first, second


def test_r1_release_never_sent_on_reconciliation(s: Session) -> None:
    """A segunda boleta consegue concluir a desmontagem após o poll."""
    _, first, second = two_buybacks(s, registered=False)
    first.reconcile("T1:C:1", at(3))
    assert first.state == T.STOPPED and first.orders == {"T1:C:1": O.REJECTED}
    assert not s.halts.blocked("sim")
    second.confirm(s.dec(second), at(3))
    s.q("B", 4, ask="1.50")
    s.q("A", 5, bid="1")
    assert second.state == T.COMPLETED
    assert s.submitted() == [("T1:C:1", 10, D("1.50"), at(2)), ("T2:B:1", 10, D("1.50"), at(3)),
                             ("T2:A:1", 10, D("1"), at(4))]


def test_r2_uncertain_account_preserves_decision(s: Session) -> None:
    """A incerteza recusa a segunda decisão antes do consumo."""
    _, _, second = two_buybacks(s, registered=False)
    decision = s.dec(second)
    with pytest.raises(EngineRefusal):
        second.confirm(decision, at(2))
    s.ledger.consume(decision, action=Action.EXECUTE, ticket="T2", now=at(2),
                     preview=second.preview)


def test_r3_readmission_occupies_capacity(s: Session) -> None:
    """A capacidade liberada só pode ser ocupada por uma boleta de cada vez."""
    pos, first, second = two_buybacks(s, registered=False)
    first.reconcile("T1:C:1", at(3))
    second.confirm(s.dec(second), at(3))
    third = s.new(pos, closing=True)
    decision = s.dec(third)
    with pytest.raises(SequenceRefusal):
        third.confirm(decision, at(3))
    s.ledger.consume(decision, action=Action.EXECUTE, ticket="T3", now=at(3), preview=third.preview)


@pytest.mark.parametrize(("quantity", "net", "gross"), [(6, "3", "15"), (7, "3.50", "17.50")])
def test_r4_partial_buyback_keeps_executed_quantity(s: Session, quantity: int,
                                                    net: str, gross: str) -> None:
    """Quatro unidades executadas deixam seis disponíveis para a próxima boleta."""
    pos = close_plan().position
    first = s.new(pos, closing=True)
    first.confirm(s.dec(first), at(2))
    s.q("B", 3, ask="1.50", size=4)
    s.cancel(first, B, 3)
    s.q("B", 4, ask="1.60")
    s.q("A", 4, bid="1")
    assert first.state == T.STOPPED and first.orders == {B: O.CANCELLED, A: O.FILLED}
    assert s.paper.poll(B) == (O.CANCELLED, 4, 0) and s.paper.poll(A) == (O.FILLED, 4, 0)
    second = s.new(pos, closing=True, legs=(leg("A", Side.SELL, "1", quantity),
                                           leg("B", Side.BUY, "1.50", quantity)),
                   net_limit=D(net), gross_cap=D(gross))
    if quantity == 7:
        with pytest.raises(SequenceRefusal):
            second.confirm(s.dec(second), at(5))
    else:
        second.confirm(s.dec(second), at(5))
        assert s.submitted()[-1] == ("T2:B:1", 6, D("1.50"), at(5))


def test_r5_uncertain_keeps_unsent_occupation(s: Session) -> None:
    """O livro mantém a ocupação mesmo sem consultar o bloqueio da conta."""
    pos, _, second = two_buybacks(s, registered=False)
    assert second.preview is not None
    with pytest.raises(SequenceRefusal):
        s.res.admissible(buyback_plan(pos), ticket="T2")


def test_r6_release_never_sent_on_drive_stop(s: Session) -> None:
    """A compra viva preserva a ocupação até a parada confirmada."""
    pos, first, second = two_buybacks(s, registered=True)
    first.reconcile("T1:C:1", at(3))
    assert first.state == T.WORKING and first.paused and first.orders == {"T1:C:1": O.LIVE}
    assert second.preview is not None
    with pytest.raises(SequenceRefusal):
        s.res.admissible(buyback_plan(pos), ticket="T2")
    s.cancel(first, "T1:C:1", 3)
    s.q("C", 4, ask="1.60")
    s.q("A", 4)
    s.q("B", 4)
    assert first.state == T.STOPPED
    assert [r.kind for r in s.receipts[0].events][-4:] == [
        E.PAUSE, E.REQUEST_CANCEL, E.VENUE_CANCELLED, E.STOP]
    second.confirm(s.dec(second), at(5))
    assert second.orders == {"T2:B:1": O.LIVE}


def test_divergence_retains_unsent_buyback_after_reconciliation(s: Session) -> None:
    """Conciliar a ordem não resolve uma divergência independente da conta."""
    pos, first, _ = two_buybacks(s, registered=False)
    s.halts.hold("sim", "divergence")
    first.reconcile("T1:C:1", at(3))
    assert first.state == T.STOPPED and s.halts.blocked("sim")
    with pytest.raises(SequenceRefusal):
        s.res.admissible(buyback_plan(pos), ticket="T2")


def test_r1_other_account_divergence_preserves_local_release(s: Session) -> None:
    """Uma divergência alheia não retém a recompra da conta conciliada."""
    _, first, second = two_buybacks(s, registered=False)
    s.halts.hold("outra", "divergence")
    first.reconcile("T1:C:1", at(3))
    assert first.state == T.STOPPED and not s.halts.blocked("sim")
    assert s.halts.blocked("outra")
    second.confirm(s.dec(second), at(3))
    assert second.orders == {"T2:B:1": O.LIVE}


def test_r6_another_uncertain_ticket_does_not_strand_buyback(s: Session) -> None:
    """Encerrar as duas boletas libera a capacidade apesar da sobreposição de bloqueios."""
    pos, first, second = two_buybacks(s, registered=True)
    first.reconcile("T1:C:1", at(3))
    third = s.new(pos, legs=(BUY,), net_limit=D("10"), gross_cap=D("10"))
    s.step(VenueTimeout(type="timeout", seq=4, ts=at(3), call="submit", registered=False))
    third.confirm(s.dec(third), at(3))
    assert third.state == T.UNCERTAIN
    s.cancel(first, "T1:C:1", 3)
    s.q("C", 4, ask="1.60")
    assert first.state == T.STOPPED and s.halts.blocked("sim")
    third.reconcile("T3:A:1", at(4))
    assert third.state == T.STOPPED and not s.halts.blocked("sim")
    second.confirm(s.dec(second), at(5))
    assert second.orders == {"T2:B:1": O.LIVE}


def assert_gross(engine: TicketEngine, signed: str, executed: str, projected: str) -> None:
    """Confere as três medidas sem converter a consulta para ponto flutuante."""
    gross = engine.gross()
    values = (gross.signed, gross.executed, gross.projected)
    assert all(isinstance(value, D) for value in values)
    assert values == (D(signed), D(executed), D(projected))


def receipt_gross(s: Session) -> dict[int, dict[str, str]]:
    """Seleciona todos os registros que realmente declararam gross."""
    return {event.seq: data["gross"] for event in s.receipts[0].events
            if "gross" in (data := json.loads(event.payload))}


def money_row(executed: str, projected: str) -> dict[str, str]:
    """Linha esperada do recibo da estrutura de 25 reais."""
    return {"signed": "25.00", "executed": executed, "projected": projected}


@pytest.mark.parametrize("cap", ["25", "30"])
def test_b0_signed_cap_can_differ_from_initial_projection(s: Session, cap: str) -> None:
    """A proposta já expõe o limite vigente, mesmo quando ele inclui folga."""
    assert_gross(s.new(gross_cap=D(cap)), cap, "0", "25")


def test_b1_better_sale_revalues_the_gross(s: Session) -> None:
    """A venda melhora e o projetado cai ao executado quando a boleta para."""
    e = s.confirmed()
    s.q("A", 3, ask="1", size=3)
    s.q("B", 4, bid="1.54")
    s.q("A", 5, ask="1", size=7)
    assert e.state == T.STOPPED
    assert_gross(e, "25", "14.62", "14.62")
    assert receipt_gross(s) == {5: money_row("3.00", "25.00"), 7: money_row("7.62", "25.12"),
                                8: money_row("14.62", "25.12"), 9: money_row("14.62", "14.62")}
    assert json.loads(s.receipts[0].events[5].payload)["protection"] == "A"


def stopped_buyback(s: Session) -> TicketEngine:
    """Para a desmontagem com seis compras aplicadas e quatro ainda na venue."""
    e = s.new(close_plan().position, closing=True)
    e.confirm(s.dec(e), at(2))
    s.q("B", 3, ask="1.50", size=3)
    s.q("A", 4, bid="1.04", ask="1.10")
    s.q("B", 5, ask="1.50", size=3)
    assert e.state == T.STOPPED and e.orders == {B: O.PARTIAL, A: O.FILLED}
    assert [(oid, qty) for oid, qty, _, _ in s.submitted()] == [(B, 10), (A, 3)]
    return e


def test_b2_stop_counts_only_the_open_buyback_balance(s: Session) -> None:
    """O saldo de quatro a 1,50 continua exposto após a parada."""
    e = stopped_buyback(s)
    assert_gross(e, "25", "12.12", "18.12")
    assert receipt_gross(s) == {5: money_row("4.50", "25.00"), 7: money_row("7.62", "25.12"),
                                8: money_row("12.12", "25.12"), 9: money_row("12.12", "18.12")}
    assert json.loads(s.receipts[0].events[5].payload)["protection"] == "B"


def test_b2b_late_fill_uses_the_terminal_projection(s: Session) -> None:
    """Aplicar a execução tardia não reabre a boleta."""
    e = stopped_buyback(s)
    s.q("B", 6, ask="1.50", size=4)
    assert e.state == T.STOPPED and e.orders[B] == O.FILLED
    assert_gross(e, "25", "18.12", "18.12")
    assert receipt_gross(s)[10] == money_row("18.12", "18.12")


def test_b3_open_buyback_keeps_its_capacity(s: Session) -> None:
    """O saldo ainda vivo impede até uma recompra de uma unidade em outra boleta."""
    stopped_buyback(s)
    s.q("A", 5)
    second = s.new(close_plan().position, closing=True, legs=(leg("B", Side.BUY, "1.50", 1),
                   leg("A", Side.SELL, "1", 1)), net_limit=D(".50"), gross_cap=D("2.50"))
    decision = s.dec(second)
    with pytest.raises(SequenceRefusal):
        second.confirm(decision, at(6))
    s.ledger.consume(decision, action=Action.EXECUTE, ticket="T2", now=at(6),
                     preview=second.preview)


def test_b6_gross_requires_a_proposal(s: Session) -> None:
    """Um motor sem prévia não tem limite assinado."""
    with pytest.raises(EngineRefusal):
        s.engine("T1", position()).gross()


def test_b7_denied_proposal_has_no_future_execution(s: Session) -> None:
    """Descartar elimina a quantidade que poderia ser enviada."""
    e = s.new()
    e.discard(s.dec(e, Action.DISCARD), at(2))
    assert e.state == T.DENIED
    assert_gross(e, "25", "0", "0")
    assert receipt_gross(s) == {}


def test_b8_gross_on_ticket_reconciliation_only(s: Session) -> None:
    """Só a conciliação da boleta que para carrega os brutos."""
    _, first, _ = two_buybacks(s, registered=False)
    first.reconcile("T1:C:1", at(3))
    last = s.receipts[0].events[-1]
    assert last.kind == E.RECONCILE and first.state == T.STOPPED
    assert receipt_gross(s) == {last.seq: {"signed": "50.00", "executed": "0.00",
                                          "projected": "0.00"}}


def test_h1_expired_ticket_projects_no_remaining_quantity(s: Session) -> None:
    e = s.new()
    s.arm(e)
    s.q("A", 3600.000001, ask="1")
    assert e.state == T.EXPIRED
    assert e.gross() == (D("25.00"), D("0.00"), D("0.00"))


def _stopped_with_two_open_sell_orders(s: Session) -> TicketEngine:
    e = s.confirmed()
    for second in (3, 4):
        s.q("A", second, ask="1.00", size=2)
    s.q("B", 5, bid="1.54", size=1)
    s.q("A", 6, ask="1.00", size=2)
    return e


def test_h2_stopped_ticket_sums_both_open_orders_of_one_series(s: Session) -> None:
    e = _stopped_with_two_open_sell_orders(s)
    assert e.state == T.STOPPED
    assert e.orders == {"T1:A:1": O.PARTIAL, "T1:B:1": O.PARTIAL, "T1:B:2": O.LIVE}
    assert e.gross() == (D("25.00"), D("7.54"), D("16.04"))


def test_h3_pending_cancel_preserves_open_projection(s: Session) -> None:
    e = _stopped_with_two_open_sell_orders(s)
    s.cancel(e, "T1:B:1", 7)
    assert e.orders["T1:B:1"] == O.CANCEL_REQUESTED
    assert e.gross() == (D("25.00"), D("7.54"), D("16.04"))


def test_v4_stopped_tickets_unused_protection_stays_with_owner(s: Session) -> None:
    first = s.confirmed()
    s.q("A", 3, ask="1")
    s.q("B", 4, bid="1.50", size=6)
    assert s.paper.poll(B) == (O.PARTIAL, 6, 4)
    s.cancel(first, B, 4)
    s.q("B", 5)
    assert first.state == T.STOPPED and first.orders[B] == O.CANCELLED

    second = s.new()
    second.confirm(s.dec(second), at(5))
    assert dict(second.orders) == {"T2:A:1": O.LIVE}
    requests = [(A, 10, D("1"), at(2)), (B, 10, D("1.50"), at(3)),
                ("T2:A:1", 10, D("1"), at(5))]
    assert s.submitted() == requests
    s.q("A", 6, ask="1", size=3)
    assert dict(second.orders) == {"T2:A:1": O.PARTIAL, "T2:B:1": O.LIVE}
    assert s.submitted() == requests + [("T2:B:1", 3, D("1.50"), at(6))]


def test_v5_paused_ticket_keeps_its_fills_until_resumed(s: Session) -> None:
    first = s.confirmed()
    first.pause(at(2))
    s.q("A", 3, ask="1")
    assert first.paused and first.orders[A] == O.FILLED
    assert (free(s, "T1"), free(s, "T2")) == (10, 0)
    second = s.new()
    second.confirm(s.dec(second), at(3))
    assert dict(second.orders) == {"T2:A:1": O.LIVE}
    assert (free(s, "T1"), free(s, "T2")) == (10, 0)

    first.resume(s.dec(first, Action.RESUME), at(4))
    assert first.state == T.WORKING and first.orders[B] == O.LIVE
    assert s.submitted() == [(A, 10, D("1"), at(2)), ("T2:A:1", 10, D("1"), at(3)),
                             (B, 10, D("1.50"), at(4))]


def third_party_surplus(s: Session, origin: str = "T1") -> int:
    """Consulta independente da sobra atribuída à origem."""
    p = sale_only(10, origin)
    return s.res.available(p, p.legs[0], ticket="observer", origin=origin)


def stop_origin(s: Session, *, divergent: bool = False) -> TicketEngine:
    """Compra dez A, vende seis B e concilia o cancelamento do restante."""
    owner = s.confirmed()
    s.q("A", 3, ask="1")
    s.q("B", 4, bid="1.50", size=6)
    s.cancel(owner, B, 4)
    if divergent:
        s.halts.hold("sim", "divergence")
    s.q("B", 5)
    assert owner.state == T.STOPPED and owner.orders[B] == O.CANCELLED
    return owner


def borrower(s: Session, qty: int = 4, *, price: str = "1.50", own: int = 0,
             grants: tuple[tuple[str, str, int], ...] = ()) -> TicketEngine:
    """Propõe a venda autorizada, com compra própria opcional."""
    sale = leg("B", Side.SELL, price, qty)
    legs = (leg("A", Side.BUY, "1", own), sale) if own else (sale,)
    volume = D(price) * qty
    ticket = authorized(draft(*legs, net=str(own - volume), gross=str(own + volume)),
                        *(grants or (("A", "T1", qty - own),)))
    return s.new(legs=ticket.legs, coverage=ticket.coverage, net_limit=ticket.net_limit,
                 gross_cap=ticket.gross_cap)


def order_rows(receipt: Receipt, oid: str) -> list[dict[str, object]]:
    """Dados públicos do pedido e dos fatos posteriores da mesma ordem."""
    return [data for event in receipt.events
            if (data := json.loads(event.payload)).get("order_id") == oid]


def test_x1_authorized_sale_records_origin_for_each_fill(s: Session) -> None:
    stop_origin(s)
    assert third_party_surplus(s) == 4
    e = borrower(s)
    assert e.preview is not None and e.preview.partial_exposure == D("0")
    assert [(g.series, g.origin, g.quantity) for g in e.preview.coverage] == [("A", "T1", 4)]
    e.confirm(s.dec(e), at(5))
    oid = "T2:B:1"
    assert e.state == T.WORKING and e.orders == {oid: O.LIVE}
    assert len(s.submitted()) == 3 and s.submitted()[2] == (oid, 4, D("1.50"), at(5))
    assert third_party_surplus(s) == 0
    receipt = s.receipts[1]
    requested, = order_rows(receipt, oid)
    assert (requested["protection"], requested["origin"]) == ("A", "T1")
    assert isinstance(requested["request"], dict) and requested["request"]["quantity"] == 4
    s.q("B", 6, bid="1.50", size=3)
    s.q("B", 7, bid="1.50", size=1)
    _, partial, final = order_rows(receipt, oid)
    for row, expected in ((partial, ("T2:B:1#1", 3, "1.50", "T1", "4.50")),
                          (final, ("T2:B:1#2", 1, "1.50", "T1", "6.00"))):
        gross = row["gross"]
        assert isinstance(gross, dict)
        assert (row["execution"], row["quantity"], row["price"], row["origin"],
                gross["executed"]) == expected
    assert e.state == T.COMPLETED
    assert [event.kind for event in receipt.events] == [
        E.PREVIEW, E.CONFIRM, E.START, E.VENUE_LIVE, E.VENUE_PARTIAL, E.VENUE_FILL, E.COMPLETE]
    assert all("origin" not in json.loads(row.payload) for row in s.receipts[0].events)


def test_x2_confirm_after_release_reuses_unspent_decision(s: Session) -> None:
    stop_origin(s)
    first, second = borrower(s), borrower(s)
    first.confirm(s.dec(first), at(5))
    decision = s.dec(second)
    with pytest.raises(SequenceRefusal, match="sobra indisponível"):
        second.confirm(decision, at(5))
    assert second.state == T.DRAFT and not second.orders and len(s.submitted()) == 3
    assert [r.kind for r in s.receipts[2].events] == [E.PREVIEW]
    s.cancel(first, "T2:B:1", 5)
    s.q("B", 6)
    assert first.state == T.STOPPED
    second.confirm(decision, at(6))
    assert s.submitted()[3:] == [("T3:B:1", 4, D("1.50"), at(6))]


def test_x3_paused_owner_keeps_protection(s: Session) -> None:
    owner = s.confirmed()
    owner.pause(at(2))
    s.q("A", 3, ask="1")
    e = borrower(s)
    with pytest.raises(SequenceRefusal, match="boleta de origem não parada"):
        e.confirm(s.dec(e), at(3))
    assert e.state == T.DRAFT and not e.orders
    owner.resume(s.dec(owner, Action.RESUME), at(4))
    assert owner.orders[B] == O.LIVE and s.submitted()[-1] == (B, 10, D("1.50"), at(4))


def test_x4_borrow_now_then_use_own_filled_purchase(s: Session) -> None:
    stop_origin(s)
    e = borrower(s, 10, own=6)
    assert e.preview is not None and e.preview.partial_exposure == D("6")
    e.confirm(s.dec(e), at(5))
    first, second = "T2:B:1", "T2:B:2"
    assert s.submitted()[2:] == [("T2:A:1", 6, D("1"), at(5)), (first, 4, D("1.50"), at(5))]
    s.q("A", 6, ask="1", size=6)
    assert e.orders["T2:A:1"] == O.FILLED and s.submitted()[4:] == [(second, 6, D("1.50"), at(6))]
    s.q("B", 7, bid="1.50", size=10)
    assert e.state == T.COMPLETED
    request, fill = order_rows(s.receipts[1], first)
    assert request["origin"] == fill["origin"] == "T1" and fill["quantity"] == 4
    request, fill = order_rows(s.receipts[1], second)
    assert request["protection"] == "A" and fill["quantity"] == 6
    assert "origin" not in request and "origin" not in fill


def test_x5_own_fills_precede_grants_on_resume(s: Session) -> None:
    stop_origin(s)
    first, e = borrower(s, 2), borrower(s, 10, own=6)
    first.confirm(s.dec(first), at(5))
    e.confirm(s.dec(e), at(5))
    assert s.submitted()[3:] == [("T3:A:1", 6, D("1"), at(5)), ("T3:B:1", 2, D("1.50"), at(5))]
    e.pause(at(5))
    s.q("A", 6, ask="1", size=6)
    assert e.orders["T3:A:1"] == O.FILLED
    s.cancel(first, "T2:B:1", 6)
    s.q("B", 7)
    assert first.state == T.STOPPED and len(s.submitted()) == 5
    e.resume(s.dec(e, Action.RESUME), at(8))
    assert s.submitted()[5:] == [("T3:B:2", 6, D("1.50"), at(8)), ("T3:B:3", 2, D("1.50"), at(8))]
    r = s.receipts[2]
    assert order_rows(r, "T3:B:1")[0]["origin"] == order_rows(r, "T3:B:3")[0]["origin"] == "T1"
    assert "origin" not in order_rows(r, "T3:B:2")[0]


def test_x6_uses_two_origins_in_canonical_order(s: Session) -> None:
    stop_origin(s)
    second = s.new()
    second.confirm(s.dec(second), at(5))
    s.q("A", 6, ask="1")
    s.q("B", 7, bid="1.50", size=7)
    s.cancel(second, "T2:B:1", 7)
    s.q("B", 8)
    assert second.state == T.STOPPED
    assert (third_party_surplus(s), third_party_surplus(s, "T2")) == (4, 3)
    e = borrower(s, 5, grants=(("A", "T2", 2), ("A", "T1", 3)))
    e.confirm(s.dec(e), at(8))
    assert s.submitted()[4:] == [("T3:B:1", 3, D("1.50"), at(8)), ("T3:B:2", 2, D("1.50"), at(8))]
    assert [order_rows(s.receipts[2], oid)[0]["origin"] for oid in ("T3:B:1", "T3:B:2")] == [
        "T1", "T2"]
    assert (third_party_surplus(s), third_party_surplus(s, "T2")) == (1, 1)


def test_x7_stopped_borrower_cannot_reuse_or_lend_borrowed_quantity(s: Session) -> None:
    stop_origin(s)
    e = borrower(s)
    e.confirm(s.dec(e), at(5))
    s.cancel(e, "T2:B:1", 5)
    s.q("B", 6)
    assert e.state == T.STOPPED
    p = sale_only(4)
    p = plan_legs(p.draft.model_copy(update=dict(send_deadline=END, order_validity=CLOSE)),
                  position())
    assert s.res.available(p, p.legs[0], ticket="T2", origin="T1") == 0
    assert (third_party_surplus(s), third_party_surplus(s, "T2")) == (4, 0)


def test_x8_edit_preserves_grant_and_rejects_insufficient_quantity(s: Session) -> None:
    stop_origin(s)
    e = borrower(s)
    quantity = FieldRef(EditableField.QUANTITY, 0)
    e.edit(quantity, 2, at(5))
    assert e.preview is not None and e.preview.version == 2 and e.preview.legs[0].quantity == 2
    assert [(g.series, g.origin, g.quantity) for g in e.preview.coverage] == [("A", "T1", 4)]
    with pytest.raises(SequenceRefusal, match="quantidade de proteção insuficiente"):
        e.edit(quantity, 5, at(5))
    assert e.preview.version == 2


def test_x9_divergence_prevents_lending_even_after_unblock(s: Session) -> None:
    stop_origin(s, divergent=True)
    assert third_party_surplus(s) == 0
    s.halts.release("sim", "divergence")
    e = borrower(s)
    with pytest.raises(SequenceRefusal, match="boleta de origem não parada"):
        e.confirm(s.dec(e), at(5))


def test_x10_completed_owner_keeps_unused_protection(s: Session) -> None:
    owner = s.new(legs=(BUY, leg("B", Side.SELL, "1.50", 6)), net_limit=D("1"), gross_cap=D("19"))
    owner.confirm(s.dec(owner), at(2))
    s.q("A", 3, ask="1")
    s.q("B", 4, bid="1.50", size=6)
    assert owner.state == T.COMPLETED and third_party_surplus(s) == 0
    e = borrower(s)
    with pytest.raises(SequenceRefusal, match="boleta de origem não parada"):
        e.confirm(s.dec(e), at(5))
    assert e.state == T.DRAFT


def contested_surplus(s: Session) -> tuple[TicketEngine, TicketEngine]:
    """Primeira boleta ocupa duas unidades com preço que o próximo negócio não alcança."""
    stop_origin(s)
    first, second = borrower(s, 2, price="1.60"), borrower(s)
    first.confirm(s.dec(first), at(5))
    second.confirm(s.dec(second), at(5))
    assert s.submitted()[2:] == [("T2:B:1", 2, D("1.60"), at(5)), ("T3:B:1", 2, D("1.50"), at(5))]
    return first, second


def test_x11_paused_borrower_waits_for_returned_surplus(s: Session) -> None:
    first, second = contested_surplus(s)
    second.pause(at(5))
    s.cancel(first, "T2:B:1", 5)
    s.q("B", 6)
    assert first.state == T.STOPPED and second.orders == {"T3:B:1": O.LIVE}
    s.q("B", 7, bid="1.50", size=10)
    assert second.state == T.WORKING and second.orders == {"T3:B:1": O.FILLED}
    second.resume(s.dec(second, Action.RESUME), at(8))
    assert s.submitted()[4:] == [("T3:B:2", 2, D("1.50"), at(8))]
    assert order_rows(s.receipts[2], "T3:B:2")[0]["origin"] == "T1"


def test_x12_exhausted_surplus_stops_after_partial_strategy(s: Session) -> None:
    first, second = contested_surplus(s)
    s.q("B", 6, bid="1.50", size=10)
    assert first.orders == {"T2:B:1": O.LIVE} and second.orders == {"T3:B:1": O.FILLED}
    assert second.state == T.STOPPED
    last = s.receipts[2].events[-1]
    assert last.kind == E.STOP and json.loads(last.payload)["gross"] == {
        "signed": "6.00", "executed": "3.00", "projected": "3.00"}


def test_x6_interleaved_grants_use_canonical_priority_within_each_series(s: Session) -> None:
    """A mesma origem em duas séries preserva a prioridade específica da venda."""
    s.q("C", 1)
    s.q("D", 1)
    pos = Position(account="sim", holdings=tuple(holding(x) for x in "ABCD"),
                   pairs=(("A", "B"), ("C", "D")))
    for origin, symbols in (("P", "AC"), ("Q", "A")):
        plan = plan_legs(draft(*(leg(symbol, Side.BUY, "1", 2) for symbol in symbols)), pos)
        s.res.admit(plan, ticket=origin)
        for buy in plan.legs:
            s.res.confirm_buy(plan, buy, origin + buy.symbol, 2, ticket=origin)
        s.res.close("sim", origin)
    sales = draft(leg("B", Side.SELL, "1.50", 2), leg("D", Side.SELL, "1.50", 2),
                  net="-6", gross="6")
    ticket = authorized(sales, ("C", "P", 2), ("A", "Q", 2), ("A", "P", 2))
    e = s.new(pos=pos, legs=ticket.legs, coverage=ticket.coverage,
              net_limit=ticket.net_limit, gross_cap=ticket.gross_cap)
    e.confirm(s.dec(e), at(2))
    assert [(oid, qty, order_rows(s.receipts[0], oid)[0]["origin"])
            for oid, qty, _, _ in s.submitted()] == [("T1:B:1", 2, "P"), ("T1:D:1", 2, "P")]


def test_x1_reconciled_stop_makes_owned_fills_available(s: Session) -> None:
    """O poll sem registro da venda libera as dez compras da origem parada."""
    owner = s.confirmed()
    s.step(VenueTimeout(type="timeout", seq=3, ts=at(2), call="submit", registered=False))
    s.q("A", 3, ask="1")
    assert owner.orders[B] == O.UNCERTAIN and third_party_surplus(s) == 0
    owner.reconcile(B, at(4))
    assert owner.state == T.STOPPED and third_party_surplus(s) == 10


def test_x1_uncertain_borrowed_order_keeps_origin_through_poll(s: Session) -> None:
    """O pedido incerto mantém a origem e o saldo ocupado até conciliar ambos os fills."""
    stop_origin(s)
    e = borrower(s)
    s.step(VenueTimeout(type="timeout", seq=9, ts=at(5), call="submit", registered=True))
    e.confirm(s.dec(e), at(5))
    oid = "T2:B:1"
    assert e.orders == {oid: O.UNCERTAIN} and third_party_surplus(s) == 0
    request, = order_rows(s.receipts[1], oid)
    assert request["origin"] == "T1" and request["protection"] == "A"
    s.q("B", 6, bid="1.50", size=3)
    s.q("B", 7, bid="1.50", size=1)
    assert e.state == T.UNCERTAIN
    e.reconcile(oid, at(7))
    assert e.state == T.COMPLETED and third_party_surplus(s) == 0
    assert [(r["quantity"], r["origin"]) for r in order_rows(s.receipts[1], oid)
            if "execution" in r] == [(3, "T1"), (1, "T1")]


def test_n3_fill_during_cancel_keeps_origin_and_releases_only_remainder(s: Session) -> None:
    """A unidade executada pertence à cedente, inclusive durante o cancelamento."""
    stop_origin(s)
    e = borrower(s)
    e.confirm(s.dec(e), at(5))
    oid = "T2:B:1"
    s.cancel(e, oid, 5)
    assert e.state == T.WORKING and e.orders[oid] == O.CANCEL_REQUESTED
    assert third_party_surplus(s) == 0
    s.q("B", 6, bid="1.50", size=1)
    events = s.receipts[1].events
    assert [event.kind for event in events] == [
        E.PREVIEW, E.CONFIRM, E.START, E.VENUE_LIVE, E.REQUEST_CANCEL,
        E.VENUE_PARTIAL, E.VENUE_CANCELLED, E.STOP]
    rows = order_rows(s.receipts[1], oid)
    assert [(r["origin"], r["quantity"], r["state"]) for r in rows if "execution" in r] == [
        ("T1", 1, O.CANCEL_REQUESTED.value)]
    for event in events:
        if event.kind in (E.REQUEST_CANCEL, E.VENUE_CANCELLED):
            assert "origin" not in json.loads(event.payload)
    assert e.state == T.STOPPED and e.orders[oid] == O.CANCELLED
    assert third_party_surplus(s) == 3


def assert_report_divergence(s: Session, oid: str, reason: str, filled: int,
                             report: dict[str, object], ts: datetime) -> None:
    """Confere o envelope completo, inclusive campos ausentes e o tipo da quantidade."""
    event = s.receipts[0].events[-1]
    expected = {"ticket": "T1", "order_id": oid, "reason": reason, "filled": filled,
                "report": report}
    assert event.kind == E.DIVERGENCE and event.ts == ts
    assert json.dumps(json.loads(event.payload), sort_keys=True) == json.dumps(expected,
                                                                               sort_keys=True)
    assert s.halts.divergent("sim")


def test_y1_overfill_is_quarantined_and_exact_remainder_still_fills(s: Session) -> None:
    """Seis mais seis excede dez; só as quatro unidades válidas entram depois."""
    e = s.confirmed()
    e.on_reports([VenueReport(A, E.VENUE_PARTIAL, 6, D("1"), at(3))], at(3))
    assert e.orders == {A: O.PARTIAL, B: O.LIVE} and e.gross().executed == D("6")
    before = len(s.receipts[0].events)
    e.on_reports([VenueReport(A, E.VENUE_FILL, 6, D("1"), at(4))], at(4))
    assert len(s.receipts[0].events) == before + 1
    assert_report_divergence(s, A, "execução acima da quantidade da ordem", 6,
                             {"event": "venue_fill", "quantity": 6, "price": "1"}, at(4))
    assert e.orders[A] == O.PARTIAL and e.state == T.WORKING and e.gross().executed == D("6")
    assert free(s) == 0 and len(s.submitted()) == 2
    e.on_reports([VenueReport(A, E.VENUE_FILL, 4, D("1"), at(5))], at(5))
    assert e.orders[A] == O.FILLED and e.gross().executed == D("10") and free(s) == 4
    assert len(s.submitted()) == 2 and s.receipts[0].verify()


def test_y2_impossible_reports_preserve_terminal_and_live_orders(s: Session) -> None:
    """Execução após preenchimento e cancelamento sem pedido são contradições distintas."""
    e = s.confirmed()
    s.q("A", 3, ask="1")
    e.on_reports([VenueReport(A, E.VENUE_PARTIAL, 1, D("1"), at(4))], at(4))
    reason = "relato impossível para o estado da ordem"
    assert_report_divergence(s, A, reason, 10, {"event": "venue_partial", "quantity": 1,
                                                "price": "1"}, at(4))
    e.on_reports([VenueReport(B, E.VENUE_CANCELLED, None, None, at(4))], at(4))
    assert_report_divergence(s, B, reason, 0, {"event": "venue_cancelled"}, at(4))
    assert e.orders == {A: O.FILLED, B: O.LIVE} and e.gross().executed == D("10")


def test_y3_known_fact_is_ignored_only_for_identical_content(s: Session) -> None:
    """Repetição inclusive no mesmo lote não altera os fatos; reuso divergente bloqueia."""
    e = s.confirmed()
    first = VenueReport(A, E.VENUE_PARTIAL, 3, D("1"), at(3), fact="x1")
    e.on_reports([first], at(3))
    events = s.receipts[0].events
    e.on_reports([first], at(3))
    e.on_reports([first, first], at(3))
    assert s.receipts[0].events == events and not s.halts.blocked("sim")
    assert e.gross().executed == D("3") and len(s.submitted()) == 2
    e.on_reports([first._replace(quantity=4)], at(4))
    assert_report_divergence(s, A, "fato repetido com conteúdo diferente", 3,
                             {"event": "venue_partial", "quantity": 4, "price": "1",
                              "fact": "x1"}, at(3))
    assert e.gross().executed == D("3") and len(s.submitted()) == 2


def test_y4_correction_references_only_previously_applied_facts(s: Session) -> None:
    """Referências conhecidas e ausentes ficam no recibo sem reescrever o saldo."""
    e = s.confirmed()
    first = VenueReport(A, E.VENUE_PARTIAL, 3, D("1"), at(3), fact="x1")
    e.on_reports([first], at(3))
    known = VenueReport(A, E.VENUE_PARTIAL, 2, D("1"), at(4), fact="x2", corrects="x1")
    for report, reason in (
        (known, "correção oficial"),
        (known._replace(fact="x3", corrects="zz", ts=at(5)), "correção sem fato original"),
        (known._replace(fact="x1", corrects="x2", ts=at(6)), "correção sem fato original"),
    ):
        e.on_reports([report], report.ts)
        assert_report_divergence(s, A, reason, 3, {
            "event": "venue_partial", "quantity": 2, "price": "1",
            "fact": report.fact, "corrects": report.corrects}, report.ts)
        assert e.orders[A] == O.PARTIAL and e.gross().executed == D("3")


def test_y5_pending_cancel_accepts_valid_fill_while_account_is_blocked(s: Session) -> None:
    """O bloqueio impede envios e conserva o fill que cruza com o cancelamento."""
    e = s.confirmed()
    s.q("A", 3, ask="1")
    e.on_reports([VenueReport(A, E.VENUE_PARTIAL, 1, D("1"), at(3))], at(3))
    assert s.halts.divergent("sim")
    s.cancel(e, B, 4)
    s.q("B", 5, bid="1.50", size=4)
    tail = s.receipts[0].events[-4:]
    assert [r.kind for r in tail] == [
        E.REQUEST_CANCEL, E.VENUE_PARTIAL, E.VENUE_CANCELLED, E.STOP]
    fill = json.loads(tail[1].payload)
    assert (fill["order_id"], fill["quantity"], fill["gross"]["executed"]) == (B, 4, "16.00")
    assert e.state == T.STOPPED and e.orders[B] == O.CANCELLED and s.halts.divergent("sim")
    assert third_party_surplus(s) == 0 and len(s.submitted()) == 2


def test_y6_batch_continues_after_impossible_report(s: Session) -> None:
    """A segunda ordem recebe a execução válida do mesmo lote."""
    e = s.confirmed()
    s.q("A", 3, ask="1")
    before = len(s.receipts[0].events)
    e.on_reports([VenueReport(A, E.VENUE_PARTIAL, 1, D("1"), at(4)),
                  VenueReport(B, E.VENUE_PARTIAL, 4, D("1.50"), at(4))], at(4))
    assert [r.kind for r in s.receipts[0].events[before:]] == [E.DIVERGENCE, E.VENUE_PARTIAL]
    assert e.orders[B] == O.PARTIAL and e.gross().executed == D("16")


@pytest.mark.parametrize(("quantity", "price"), [
    (0, D("1")), (-1, D("1")), (None, D("1")), (3, None), (True, D("1"))])
def test_y7_malformed_fill_preserves_received_fields(s: Session, quantity: int | None,
                                                    price: D | None) -> None:
    """Uma execução malformada não ocupa, libera nem altera o executado da ordem."""
    e = s.confirmed()
    e.on_reports([VenueReport(A, E.VENUE_PARTIAL, quantity, price, at(3))], at(3))
    report: dict[str, object] = {"event": "venue_partial"}
    if quantity is not None:
        report["quantity"] = quantity
    if price is not None:
        report["price"] = "1"
    assert_report_divergence(s, A, "execução malformada", 0, report, at(3))
    assert e.orders == {A: O.LIVE} and e.gross().executed == 0 and len(s.submitted()) == 1


def test_y8_identical_reports_without_fact_are_distinct_fills(s: Session) -> None:
    """Duas execuções sem identificador continuam sendo dois fatos."""
    e = s.confirmed()
    r = VenueReport(A, E.VENUE_PARTIAL, 3, D("1"), at(3))
    e.on_reports([r, r], at(3))
    fills = [json.loads(row.payload)["execution"] for row in s.receipts[0].events
             if row.kind == E.VENUE_PARTIAL]
    assert fills == [A + "#1", A + "#2"] and e.gross().executed == D("6")
    assert not s.halts.blocked("sim")


def test_y9_divergence_blocks_only_the_affected_account(s: Session) -> None:
    """A segunda boleta da mesma conta é recusada antes do envio."""
    e = s.confirmed()
    s.q("A", 3, ask="1")
    e.on_reports([VenueReport(A, E.VENUE_PARTIAL, 1, D("1"), at(4))], at(4))
    other = s.new()
    with pytest.raises(EngineRefusal, match="conta em estado incerto"):
        other.confirm(s.dec(other), at(5))
    assert other.state == T.DRAFT and not other.orders and len(s.submitted()) == 2
    assert not s.halts.blocked("outra")


def test_y1_reports_last_quantity_actually_posted_to_book(s: Session) -> None:
    """Uma recusa contábil anterior separa o bruto factual do saldo conciliado."""
    s.res = FirstBuyFails()
    e = s.confirmed()
    e.on_reports([VenueReport(A, E.VENUE_PARTIAL, 3, D("1"), at(3)),
                  VenueReport(A, E.VENUE_PARTIAL, 2, D("1"), at(4)),
                  VenueReport(A, E.VENUE_FILL, 6, D("1"), at(5))], at(5))
    assert_report_divergence(s, A, "execução acima da quantidade da ordem", 2,
                             {"event": "venue_fill", "quantity": 6, "price": "1"}, at(5))
    assert e.gross().executed == D("5") and free(s) == 2


def test_y3_reused_fact_with_boolean_quantity_is_not_an_identical_message(s: Session) -> None:
    """True e 1 representam mensagens distintas, inclusive antes da regra de formato."""
    e = s.confirmed()
    first = VenueReport(A, E.VENUE_PARTIAL, 1, D("1"), at(3), fact="x1")
    e.on_reports([first, first._replace(quantity=True)], at(3))
    assert_report_divergence(s, A, "fato repetido com conteúdo diferente", 1, {
        "event": "venue_partial", "price": "1", "quantity": True, "fact": "x1"}, at(3))


def test_y3_immediate_submit_fact_is_known_to_later_batch(s: Session) -> None:
    """Uma resposta identificada já aplicada não pode voltar como transição impossível."""
    def submit(req: VenueOrder, ts: datetime) -> VenueReport:
        return s.paper.submit(req, ts)._replace(fact="accepted")

    s.venue.submit.side_effect = submit
    e = s.confirmed()
    before = s.receipts[0].events
    e.on_reports([VenueReport(A, E.VENUE_LIVE, None, None, at(2), fact="accepted")], at(3))
    assert e.orders == {A: O.LIVE} and s.receipts[0].events == before
    assert not s.halts.blocked("sim")


def test_y3_reconciled_fill_becomes_known_after_poll(s: Session) -> None:
    """O fato incerto só é aplicado pela conciliação e depois resiste à retransmissão."""
    e = timeout(s)
    reports = s.paper.advance(quote("A", ask="1.00").model_copy(update={"ts": at(3)}))
    fill, = reports
    identified = fill._replace(fact="late")
    e.on_reports([identified], at(3))
    assert e.state == T.UNCERTAIN and e.gross().executed == 0
    e.reconcile(A, at(3))
    before = s.receipts[0].events
    e.on_reports([identified], at(4))
    assert s.receipts[0].events == before and e.gross().executed == D("10")
    assert not s.halts.blocked("sim")


def test_y3_retransmission_compares_instants_across_dst_fold(s: Session) -> None:
    """01:30 ocorre às 05:30Z e às 06:30Z na volta do horário de verão."""
    e = s.confirmed()
    local = datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo("America/New_York"))
    first = VenueReport(A, E.VENUE_PARTIAL, 3, D("1"), local, fact="fold")
    e.on_reports([first], at(3))
    before = s.receipts[0].events
    e.on_reports([first._replace(ts=datetime(2026, 11, 1, 5, 30, tzinfo=UTC))], at(4))
    assert s.receipts[0].events == before and not s.halts.divergent("sim")
    e.on_reports([first._replace(ts=local.replace(fold=1))], at(5))
    assert_report_divergence(s, A, "fato repetido com conteúdo diferente", 3, {
        "event": "venue_partial", "quantity": 3, "price": "1", "fact": "fold"},
        datetime(2026, 11, 1, 6, 30, tzinfo=UTC))
    assert e.gross().executed == D("3")


def test_y3_conflicting_price_text_preserved_in_receipt(s: Session) -> None:
    """O preço tem o mesmo valor econômico, mas a representação recebida difere."""
    e = s.confirmed()
    first = VenueReport(A, E.VENUE_PARTIAL, 3, D("1.0"), at(3), fact="scale")
    e.on_reports([first, first._replace(price=D("1.00"))], at(3))
    assert_report_divergence(s, A, "fato repetido com conteúdo diferente", 3, {
        "event": "venue_partial", "quantity": 3, "price": "1.00", "fact": "scale"}, at(3))
    assert e.gross().executed == D("3")


@pytest.mark.parametrize("field", ["order_id", "event"])
def test_identity_conflict_even_if_only_order_or_event_differs(s: Session, field: str) -> None:
    """A mesma identidade não autoriza mudar só a ordem ou só o evento."""
    e = s.confirmed()
    first = VenueReport(A, E.VENUE_PARTIAL, 3, D("1"), at(3), fact="f")
    e.on_reports([first], at(3))
    other = (first._replace(order_id=B) if field == "order_id"
             else first._replace(event=E.VENUE_FILL))
    e.on_reports([other], at(4))
    assert_report_divergence(s, other.order_id, "fato repetido com conteúdo diferente",
                             0 if field == "order_id" else 3,
                             {"event": other.event.value, "quantity": 3, "price": "1",
                              "fact": "f"}, at(3))
    assert e.gross().executed == 3 and e.orders == {A: O.PARTIAL, B: O.LIVE}


def test_final_duplicate_keeps_send_due_to_first_fill(s: Session) -> None:
    """A decisão após o lote vê as três compras executadas uma única vez."""
    e = s.confirmed()
    first = VenueReport(A, E.VENUE_PARTIAL, 3, D("1"), at(3), fact="f")
    e.on_reports([first, first], at(3))
    assert [(oid, qty) for oid, qty, _, _ in s.submitted()] == [(A, 10), (B, 3)]
    assert e.gross().executed == 3 and not s.halts.blocked("sim")


def test_reconcile_checks_duplicate_correction_and_valid_tail_atomically(s: Session) -> None:
    """O poll incompatível não grava fatos; a repetição com poll correto grava cada um uma vez."""
    e = timeout(s)
    first = VenueReport(A, E.VENUE_PARTIAL, 3, D("1"), at(3), fact="f")
    correction = first._replace(quantity=2, fact="change", corrects="f")
    tail = first._replace(quantity=1, fact="tail")
    e.on_reports([first, first, correction, tail], at(3))
    before = s.receipts[0].events
    s.venue.poll.return_value = OrderSnapshot(O.PARTIAL, 9, 1)
    with pytest.raises(EngineRefusal):
        e.reconcile(A, at(4))
    assert s.receipts[0].events == before and e.orders[A] == O.UNCERTAIN
    assert free(s) == 0 and not s.halts.divergent("sim")
    s.venue.poll.return_value = OrderSnapshot(O.PARTIAL, 4, 6)
    e.reconcile(A, at(5))
    rows = s.receipts[0].events[len(before):]
    assert [row.kind for row in rows] == [
        E.RECONCILE, E.VENUE_PARTIAL, E.DIVERGENCE, E.VENUE_PARTIAL, E.RECONCILE, E.PAUSE]
    discrepancy = json.loads(rows[2].payload)
    assert discrepancy["reason"] == "correção oficial" and discrepancy["filled"] == 3
    assert discrepancy["report"] == {"event": "venue_partial", "quantity": 2, "price": "1",
                                     "fact": "change", "corrects": "f"}
    assert e.gross().executed == 4 and free(s) == 4 and s.halts.divergent("sim")
    e.on_reports([correction._replace(corrects=None)], at(6))
    assert e.gross().executed == 6 and free(s) == 6 and e.orders[A] == O.PARTIAL
    assert len(s.submitted()) == 1 and s.receipts[0].verify()


def test_pending_corrected_report_is_never_posted_as_original(s: Session) -> None:
    """A correção recebida na fila deixa a identidade livre para um fato original posterior."""
    e = timeout(s)
    correction = VenueReport(A, E.VENUE_PARTIAL, 2, D("1"), at(3), fact="c", corrects="absent")
    e.on_reports([correction], at(3))
    s.venue.poll.return_value = OrderSnapshot(O.LIVE, 0, 10)
    e.reconcile(A, at(4))
    divergences = [json.loads(row.payload) for row in s.receipts[0].events
                   if row.kind == E.DIVERGENCE]
    assert [(row["reason"], row["filled"]) for row in divergences] == [
        ("correção sem fato original", 0)]
    assert e.orders[A] == O.LIVE and e.gross().executed == 0
    e.on_reports([correction._replace(corrects=None)], at(5))
    assert e.orders[A] == O.PARTIAL and e.gross().executed == 2
    assert s.halts.divergent("sim") and s.receipts[0].verify()


@pytest.mark.parametrize(("quantity", "reason"), [
    (True, "execução malformada"), (11, "execução acima da quantidade da ordem")])
def test_pending_bad_fill_cannot_hide_valid_fill(s: Session, quantity: int, reason: str) -> None:
    """Um relato ruim na fila não muda o saldo usado para conferir a execução seguinte."""
    e = timeout(s)
    bad = VenueReport(A, E.VENUE_PARTIAL, quantity, D("1"), at(3), fact="bad")
    good = VenueReport(A, E.VENUE_FILL, 10, D("1"), at(4), fact="good")
    e.on_reports([bad, good], at(4))
    s.venue.poll.return_value = OrderSnapshot(O.FILLED, 10, 0)
    e.reconcile(A, at(5))
    rows = s.receipts[0].events
    divergence, = [json.loads(row.payload) for row in rows if row.kind == E.DIVERGENCE]
    assert (divergence["filled"], divergence["reason"]) == (0, reason)
    assert type(divergence["report"]["quantity"]) is type(quantity)
    assert divergence["report"]["quantity"] == quantity
    assert [row.kind for row in rows if row.kind in (E.VENUE_PARTIAL, E.VENUE_FILL)] == [
        E.VENUE_FILL]
    assert e.orders[A] == O.FILLED and e.gross().executed == 10 and free(s) == 10
    assert s.halts.divergent("sim") and s.receipts[0].verify()
