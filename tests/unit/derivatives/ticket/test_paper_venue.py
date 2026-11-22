"""Fitas manuais V1–V14 e transições por tentativa de envio."""
from datetime import timedelta
from decimal import Decimal as D

import pytest

from backend.derivatives.ticket.models import Side
from backend.derivatives.ticket.paper_venue import PaperVenue
from backend.derivatives.ticket.replay import AuctionFill, CancelRejected, TradeEvent, VenueTimeout
from backend.derivatives.ticket.state import Event, OrderState as S, reconcile, transition
from backend.derivatives.ticket.venue import VenueOrder, VenueRefusal, VenueReport
from tests.unit.derivatives.ticket.test_guards import CLOSE, NOW, quote


@pytest.mark.parametrize(("tape","expected","snapshot"), [
    ("buy;q A 1 50", "live;fill 10 1", "FILLED 10 0"),
    ("buy;q A .98 50", "live;fill 10 .98", "FILLED 10 0"),
    ("buy;q A 1 3;q A 1 4;q A 1.01 100;q A .99 100",
     "live;partial 3 1;partial 4 1;fill 3 .99", "FILLED 10 0"),
    ("buy;SIMPLE;STRATEGY;q A 1.02 50", "live", "LIVE 0 10"),
    ("sell;q B 1.50 6;q B 1.55 10", "live;partial 6 1.50;fill 4 1.55", "FILLED 10 0"),
    ("buy 5;second;q A 1 7", "live;live:o2;fill 5 1;partial:o2 2 1","FILLED 5 0/PARTIAL 2 3"),
    ("buy;q A 1 3;q A 1 100 AUCTION;cancel;auction;reject",
     "live;partial 3 1;partial 1 1;cancel_rejected_partial", "PARTIAL 4 6"),
    ("sell;cancel;q B 1.50 4", "live;partial 4 1.50;cancelled", "CANCELLED 4 0"),
    ("sell;cancel;q B 1.40 50", "live;cancelled", "CANCELLED 0 0"),
    ("sell;cancel;q B 1.50 10", "live;fill 10 1.50", "FILLED 10 0"),
    ("buy;cancel;q B 1.50 50", "live", "LIVE 0 10"),
    ("buy;q A 1 3;close", "live;partial 3 1;expired", "EXPIRED 3 0"),
    ("invalid", "rejected", "none"),
    ("timeout-yes;buy;q A 1 50", "uncertain;fill 10 1", "FILLED 10 0"),
    ("timeout-no;buy", "uncertain", "none"),
    ("buy;gap", "live;fill 10 1", "FILLED 10 0"),
    ("buy 9 3;q A 1 4", "live;partial 4 1", "PARTIAL 4 5"),
    ("buy;unknown;duplicate;live-check;q A 1 50;terminal;duplicate",
     "live;rejected;fill 10 1;rejected", "FILLED 10 0"),
    ("buy;q A 1 100 SUSPENDED", "live", "LIVE 0 10"),
    ("buy;cancel;reject", "live;cancel_rejected_live", "LIVE 0 10"),
    ("buy;spurious", "live", "LIVE 0 10"),
    ("bad-lot", "rejected", "none"), ("at-close", "rejected", "none"),
], ids=("V1 V2 V3 V4 V5 V6 V7 V8 V8b V8c V8d V9 V10 V11 V11b V12 V13 V14 suspended "
        "cancel-rejected-live spurious invalid-lot closed").split())
def test_tape(tape: str, expected: str, snapshot: str) -> None:
    """A mesma fita produz relatórios idênticos em duas sessões independentes."""
    first = play(tape, expected, snapshot)
    assert play(tape, expected, snapshot) == first


def play(tape: str, expected: str, snapshot: str) -> list[VenueReport]:
    """Consome cada relatório pela máquina existente e compara com a fita literal."""
    venue = PaperVenue(CLOSE)
    assert not venue.advance(quote())  # cotação executável anterior ao envio
    states = {}
    reports = []
    for seq, op in enumerate(tape.split(";"), 2):
        cmd, *args = op.split()
        common = dict(ts=NOW, seq=seq)
        out = ()
        if cmd in {"buy","sell","bad-lot","duplicate","invalid","second","at-close"}:
            order = VenueOrder(order_id="o2" if cmd=="second" else "o1",
                symbol="B" if cmd=="sell" else "A", side=Side.SELL if cmd=="sell" else Side.BUY,
                quantity=int(args[0]) if args else 5 if cmd=="second" else 10,
                lot_size=int(args[1]) if len(args)>1 else 3 if cmd=="bad-lot" else 1,
                limit_price=D("1.50" if cmd=="sell" else "1"),
                valid_until=CLOSE-timedelta(hours=1) if cmd=="invalid" else CLOSE)
            report = venue.submit(order, CLOSE if cmd=="at-close" else NOW)
            state = transition(S.PENDING_SEND, report.event)
            if state == S.UNCERTAIN:
                found = venue.poll(order.order_id)
                if "timeout-yes" in tape:
                    assert found and (found.state, found.filled, found.remaining) == (S.LIVE, 0, 10)
                else:
                    assert found is None
                state = reconcile(state, found.state if found else S.REJECTED, evidence="poll")
            if state != S.REJECTED:
                states[order.order_id] = state
            reports.append(report)
        elif cmd=="cancel":
            assert venue.request_cancel("o1",NOW) is None
            states["o1"] = transition(states["o1"],Event.REQUEST_CANCEL)
        elif cmd in {"unknown","terminal"}:
            with pytest.raises(VenueRefusal):
                venue.request_cancel("missing" if cmd=="unknown" else "o1",NOW)
        elif cmd=="live-check":
            s = venue.poll("o1")
            assert s and (s.state,s.filled,s.remaining)==(S.LIVE,0,10)
        elif cmd=="q":
            sym,price,n,*phase=args
            q=quote(sym, bid=price if sym=="B" else ".95",ask=price if sym=="A" else "2",
                    bs=int(n),size=int(n),phase=phase[0] if phase else "CONTINUOUS",age=0)
            out=venue.advance(q.model_copy(update=common))
        elif cmd in {"gap","close"}:
            out=venue.advance(quote(age=0).model_copy(update=dict(
                seq=seq, ts=CLOSE if cmd=="close" else NOW,gap_before=cmd=="gap")))
        elif cmd in {"SIMPLE","STRATEGY"}:
            out=venue.advance(TradeEvent.model_validate(common | dict(
                type="trade", symbol="A",price=D(".90"),size=100,kind=cmd)))
        elif cmd=="auction":
            out=venue.advance(AuctionFill.model_validate(common | dict(
                type="auction_fill",symbol="A",price=D("1"),size=1)))
        elif cmd in {"reject","spurious"}:
            event=CancelRejected.model_validate(common | dict(type="cancel_rejected",order="o1"))
            if cmd=="spurious":
                with pytest.raises(VenueRefusal):
                    venue.advance(event)
            else:
                out=venue.advance(event)
        else:
            out=venue.advance(VenueTimeout.model_validate(common | dict(
                type="timeout",call="submit",registered=cmd=="timeout-yes")))
        for r in out:
            states[r.order_id] = transition(states[r.order_id],r.event)
            reports.append(r)
    wants=[]
    for row in expected.split(";"):
        action,*values=row.split()
        name,_,oid=action.partition(":")
        wants.append((oid or "o1", name, int(values[0]) if values else None,
                      D(values[1]) if values else None))
    assert [(r.order_id,r.event.value.removeprefix("venue_"),r.quantity,r.price)
            for r in reports] == wants
    for oid, text in zip(("o1","o2"),snapshot.split("/")):
        s=venue.poll(oid)
        if text=="none":
            assert s is None
        else:
            state,filled,remaining=text.split()
            assert s and (s.state.value,s.filled,s.remaining)==(state,int(filled),int(remaining))
    if "partial 4 1;fill 3 .99" in expected or "fill 4 1.55" in expected:
        assert sum(r.quantity*r.price for r in reports if r.price is not None) == (
            D("9.97") if tape.startswith("buy") else D("15.20"))
    return reports


def test_auction_eligibility_size_and_cancel_are_separate() -> None:
    """Injeção de leilão compartilha quantidade e respeita lado, preço e fase da série."""
    venue = PaperVenue(CLOSE)
    for oid, side, price in [("ineligible", Side.BUY, ".99"), ("buyer", Side.BUY, "1"),
                             ("seller", Side.SELL, "1"), ("expensive", Side.SELL, "1.01")]:
        order = VenueOrder(order_id=oid, symbol="A", side=side, quantity=5, lot_size=1,
                           limit_price=D(price), valid_until=CLOSE)
        assert venue.submit(order, NOW).event is Event.VENUE_LIVE
    auction = AuctionFill(type="auction_fill", seq=5, ts=NOW, symbol="A", price=D("1"), size=7)
    venue.advance(quote(ask="1.02", age=0))
    assert venue.advance(auction) == ()
    venue.advance(quote(phase="SUSPENDED", age=0))
    actual = venue.advance(auction)
    assert [(r.order_id, r.event, r.quantity, r.price, r.ts) for r in actual] == [
        ("buyer", Event.VENUE_FILL, 5, D("1"), NOW),
        ("seller", Event.VENUE_PARTIAL, 2, D("1"), NOW)]
    assert venue.advance(auction.model_copy(update={"size":10})) == (
        VenueReport("seller", Event.VENUE_FILL, 3, D("1"), NOW),)


def test_closed_session_expires_all_live_orders_only_once() -> None:
    """Expiração abrange todas as séries, inclusive pedidos locais pendentes."""
    venue = PaperVenue(CLOSE)
    for symbol in "AB":
        venue.submit(VenueOrder(order_id=symbol, symbol=symbol, side=Side.BUY, quantity=1,
                                limit_price=D("1"), lot_size=1, valid_until=CLOSE), NOW)
    venue.request_cancel("B", NOW)
    event = quote().model_copy(update={"ts": CLOSE})
    assert venue.advance(event) == (VenueReport("A", Event.VENUE_EXPIRED, None, None, CLOSE),
                                    VenueReport("B", Event.VENUE_EXPIRED, None, None, CLOSE))
    assert not venue.advance(event)


def test_no_match_in_submit_and_timeout_is_consumed_once() -> None:
    """O envio observa apenas eventos futuros mesmo quando o último ask já cruzava."""
    venue = PaperVenue(CLOSE)
    venue.advance(quote(ask=".95"))
    order = VenueOrder(order_id="o1", symbol="A", side=Side.BUY, quantity=5,
                       lot_size=1, limit_price=D("1"), valid_until=CLOSE)
    venue.advance(VenueTimeout(type="timeout", call="submit", registered=False, seq=2, ts=NOW))
    assert venue.submit(order, NOW).event is Event.UNCERTAIN
    assert venue.poll("o1") is None
    assert venue.submit(order, NOW).event is Event.VENUE_LIVE
    assert venue.poll("o1") == (S.LIVE, 0, 5)


def test_quote_matches_all_orders_before_any_cancellation_report() -> None:
    """Uma confirmação da ordem antiga sai após a execução da outra compra da série."""
    venue = PaperVenue(CLOSE)
    for oid, price in [("old", ".90"), ("new", "1.00")]:
        order = VenueOrder(order_id=oid, symbol="A", side=Side.BUY, quantity=5, lot_size=1,
                           limit_price=D(price), valid_until=CLOSE)
        assert venue.submit(order, NOW).event is Event.VENUE_LIVE
    venue.request_cancel("old", NOW)
    assert venue.advance(quote(age=0)) == (
        VenueReport("new", Event.VENUE_FILL, 5, D("1"), NOW),
        VenueReport("old", Event.VENUE_CANCELLED, None, None, NOW),
    )


@pytest.mark.parametrize("fill", [False, True], ids=["recusa-anterior", "execucao-integral"])
def test_cancel_rejection_requires_a_still_pending_request(fill: bool) -> None:
    """A recusa prévia e a execução integral encerram o pedido de cancelamento."""
    venue = PaperVenue(CLOSE)
    order = VenueOrder(order_id="A1", symbol="A", side=Side.BUY, quantity=2, lot_size=1,
                       limit_price=D("1"), valid_until=CLOSE)
    venue.submit(order, NOW)
    venue.request_cancel("A1", NOW)
    reject = CancelRejected(type="cancel_rejected", seq=3, ts=NOW, order="A1")
    if fill:
        assert venue.advance(quote(age=0))[0].event is Event.VENUE_FILL
    else:
        assert venue.advance(reject)[0].event is Event.VENUE_CANCEL_REJECTED_LIVE
    with pytest.raises(VenueRefusal):
        venue.advance(reject.model_copy(update={"seq":4}))


def test_replay_cannot_reject_cancellation_for_unknown_id() -> None:
    """Uma recusa de fixture sem ordem registrada é erro tipado."""
    with pytest.raises(VenueRefusal):
        PaperVenue(CLOSE).advance(CancelRejected(type="cancel_rejected", seq=1, ts=NOW,
                                                order="ausente"))


@pytest.mark.parametrize(("microseconds", "event"), [
    (-1, Event.VENUE_LIVE), (0, Event.VENUE_REJECTED), (1, Event.VENUE_REJECTED),
])
def test_f6_submit_at_session_boundary(microseconds: int, event: Event) -> None:
    """O simulador aceita o último microssegundo anterior ao fechamento."""
    request = VenueOrder(order_id="o1", symbol="A", side=Side.BUY, quantity=10, lot_size=1,
                         limit_price=D("1"), valid_until=CLOSE)
    instant = CLOSE + timedelta(microseconds=microseconds)
    assert PaperVenue(CLOSE).submit(request, instant).event == event
