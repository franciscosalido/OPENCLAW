"""Cenários manuais do motor com venue, gate, reservas e recibo reais do simulador."""
import json
from collections.abc import Iterator
from datetime import datetime, timedelta
from decimal import Decimal as D
from unittest.mock import Mock

import pytest

from backend.derivatives.ticket.engine import AccountHalts, EngineRefusal, TicketEngine
from backend.derivatives.ticket.gate import Action, DecisionLedger, HumanDecision, issue
from backend.derivatives.ticket.guards import BookView
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
    BUY, SELL, close_plan, draft, holding, leg, position,
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
    assert e.state==T.STOPPED and e.orders[B]==O.CANCELLED and free(s)==6
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
    assert len(s.submitted()) == 2 and free(s) == 10


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
