"""Fitas manuais V1–V14 e transições por tentativa de envio."""
from datetime import timedelta
from decimal import Decimal as D

import pytest

from backend.derivatives.ticket.models import Side
from backend.derivatives.ticket.paper_venue import PaperVenue
from backend.derivatives.ticket.replay import AuctionFill, CancelRejected, TradeEvent, VenueTimeout
from backend.derivatives.ticket.state import Event, OrderState as S, reconcile, transition
from backend.derivatives.ticket.venue import VenueOrder, VenueRefusal
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


def play(tape: str, expected: str, snapshot: str) -> list:
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
                assert (found.state, found.filled, found.remaining) == (S.LIVE,0,10) if (
                    "timeout-yes" in tape and found is not None) else found is None
                assert (found is not None) == ("timeout-yes" in tape)
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
