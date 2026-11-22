"""Oráculos literais do gatilho de aviso, sem motor ou envio."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from backend.derivatives.ticket.guards import BookView
from backend.derivatives.ticket.replay import QuoteEvent, ReplayEvent, TradeEvent
from backend.derivatives.ticket.trigger import (
    Direction, Outcome, Source, Trigger, TriggerRefusal, TriggerSpec, TriggerState, spec_digest,
)
from tests.unit.derivatives.ticket.test_guards import NOW, quote

UNTIL = NOW + timedelta(hours=1)
MID = NOW + timedelta(minutes=30)
SPEC = TriggerSpec(symbol="A", source=Source.ASK, direction=Direction.AT_OR_BELOW,
                   threshold=D("1.00"), min_size=10, armed_until=UNTIL)


def q(**changes: object) -> QuoteEvent:
    """Cotação de A no horário padrão da tabela."""
    return QuoteEvent.model_validate(dict(quote(ask="1.02",age=0)) | {"ts":MID} | changes)


def trade(kind: str, **changes: object) -> TradeEvent:
    """Negócio independente da foto da série."""
    return TradeEvent.model_validate(dict(seq=2, ts=MID, type="trade", symbol="A",
                                         price=D(".45"), size=5, kind=kind) | changes)


@pytest.mark.parametrize(("photo","source","now","expected"), [
    (q(),Source.ASK,NOW,None), (q(ask=D("1")),Source.ASK,NOW,"condição já verdadeira"),
    (q(ask=D("1"),ask_size=9),Source.ASK,NOW,None), (None,Source.ASK,NOW,"sem cotação"),
    (q(gap_before=True),Source.ASK,NOW,"perda de sequência"),
    (q(phase="AUCTION"),Source.ASK,NOW,"fora do contínuo"), (q(),Source.ASK,UNTIL,"prazo vencido"),
    (q(),Source.STRATEGY_TRADE,NOW,None),
    (q(bid=D("1"),ask=D("1")),Source.ASK,NOW,"livro inválido"),
],ids="A1 A2 A3 A4 A5 A6 A7 A8 A9".split())
def test_arm(photo: QuoteEvent | None, source: Source, now: datetime, expected: str | None) -> None:
    """Verifica cada fronteira ao armar."""
    book=BookView()
    if photo:
        book.advance(photo.model_copy(update={"ts":NOW}))
    trigger=Trigger(SPEC.model_copy(update={"source":source}))
    if expected:
        with pytest.raises(TriggerRefusal, match=expected):
            trigger.arm(book,now)
    else:
        trigger.arm(book,now)
        assert trigger.state == TriggerState.ARMED


@pytest.mark.parametrize(("spec","events","outcomes","state"), [
    ("ask",[q(ask=D("1.01"))],"NONE","ARMED"), ("ask",[q(ask=D("1"))],"FIRED","FIRED"),
    ("ask",[q(ask=D("1"),ask_size=9)],"NONE","ARMED"),
    ("ask",[q(ask=D(".99"),ask_size=10)],"FIRED","FIRED"),
    ("ask",[q(symbol="B",bid=D(".85"),ask=D(".90"))],"NONE","ARMED"),
    ("ask",[q(ask=D(".99"),phase="AUCTION")],"NONE","ARMED"),
    ("ask",[q(ask=D(".99"),gap_before=True)],"NONE","ARMED"),
    ("ask",[q(ask=D(".99"),gap_before=True),q(ask=D(".99"))],"NONE NONE","ARMED"),
    ("ask",[q(bid=D("1"),ask=D("1"))],"NONE","ARMED"),
    ("ask",[trade("SIMPLE",price=D(".90"),size=100)],"NONE","ARMED"),
    ("ask",[q(ask=D(".99"),ts=UNTIL)],"FIRED","FIRED"),
    ("ask",[q(ask=D(".99"),ts=UNTIL+timedelta(microseconds=1))],"EXPIRED","EXPIRED"),
    ("ask",[q(ask=D("1")),q(ask=D(".98"))],"FIRED NONE","FIRED"),
    ("ask",[q(ts=UNTIL+timedelta(microseconds=1)),q(ask=D(".98"))],"EXPIRED NONE","EXPIRED"),
    ("disarm",[q(ask=D(".99"))],"NONE","DISARMED"),
    ("strategy",[trade("SIMPLE")],"NONE","ARMED"),
    ("strategy",[trade("STRATEGY")],"FIRED","FIRED"),
    ("simple",[trade("STRATEGY")],"NONE","ARMED"), ("simple",[trade("SIMPLE")],"FIRED","FIRED"),
    ("bid",[q(symbol="B",bid=D("1.49"),ask=D("1.60"))],"NONE","ARMED"),
    ("bid",[q(symbol="B",bid=D("1.50"),ask=D("1.60"))],"FIRED","FIRED"),
    ("strategy",[trade("STRATEGY",gap_before=True)],"NONE","ARMED"),
    ("strategy",[q(phase="AUCTION"),trade("STRATEGY")],"NONE NONE","ARMED"),
],ids="E1 E2 E3 E4 E5 E6 E7 E7b E8 E9 E10 E11 E12 E13 E14 E15 E16 E17 E18 E19 E20 E21 E22".split())
def test_events(spec: str, events: list[ReplayEvent], outcomes: str, state: str) -> None:
    """Conduz o replay na ordem pública: foto antes do gatilho."""
    book=BookView()
    start=SPEC
    if spec=="bid":
        start=SPEC.model_copy(update=dict(symbol="B", source=Source.BID,
            direction=Direction.AT_OR_ABOVE, threshold=D("1.50")))
        initial=q(symbol="B",bid=D("1.45"),ask=D("1.60"))
    else:
        initial=q()
        if spec in {"strategy","simple"}:
            source=Source.STRATEGY_TRADE if spec=="strategy" else Source.SIMPLE_TRADE
            start=SPEC.model_copy(update=dict(source=source,threshold=D(".50"),min_size=1))
    book.advance(initial.model_copy(update={"ts":NOW}))
    trigger=Trigger(start)
    trigger.arm(book,NOW)
    if spec=="disarm":
        trigger.disarm()
    for event,want in zip(events,outcomes.split(),strict=True):
        book.advance(event)
        assert trigger.on_event(event,book) == Outcome(want)
    assert trigger.state == TriggerState(state)
    if state != "ARMED":
        with pytest.raises(TriggerRefusal):
            trigger.arm(book,NOW)
        with pytest.raises(TriggerRefusal):
            trigger.disarm()


@pytest.mark.parametrize("changed", [
    dict(symbol="B"), dict(source=Source.BID), dict(direction=Direction.AT_OR_ABOVE),
    dict(threshold=D("1.01")), dict(min_size=11), dict(armed_until=UNTIL+timedelta(seconds=1)),
])
def test_digest_fields(changed: dict[str, object]) -> None:
    """Cada campo entra no resumo da especificação."""
    assert spec_digest(SPEC) != spec_digest(SPEC.model_copy(update=changed))


def test_canonical_digest() -> None:
    """Escala e offset equivalentes preservam o SHA-256."""
    alternate=UNTIL.astimezone(timezone(timedelta(hours=-3)))
    digest=spec_digest(SPEC)
    assert len(bytes.fromhex(digest))==32
    equivalent = SPEC.model_copy(update=dict(threshold=D("1.0"), armed_until=alternate))
    assert digest == spec_digest(equivalent)


@pytest.mark.parametrize("changed", [dict(threshold=D("0")),dict(threshold=D(".001")),
                                     dict(min_size=0),dict(armed_until=NOW.replace(tzinfo=None))])
def test_spec_fields_validated(changed: dict[str, object]) -> None:
    """A condição só admite preço positivo em ticks, tamanho mínimo e prazo com fuso."""
    with pytest.raises(ValidationError):
        TriggerSpec.model_validate(dict(SPEC) | changed)


def test_initial_state_and_empty_book_on_event() -> None:
    """Um evento antes de armar ou sem foto no livro apresentado não dispara."""
    book = BookView()
    book.advance(q())
    trigger = Trigger(SPEC)
    assert trigger.on_event(q(ask=D(".99")), book) == Outcome.NONE
    with pytest.raises(TriggerRefusal):
        trigger.disarm()
    with pytest.raises(TriggerRefusal, match="tempo inválido"):
        trigger.arm(book, NOW.replace(tzinfo=None))
    trigger.arm(book, NOW)
    assert trigger.on_event(q(ask=D(".99")), BookView()) == Outcome.NONE
    assert trigger.state == TriggerState.ARMED


@pytest.mark.parametrize(("source", "kind"), [(Source.SIMPLE_TRADE, "SIMPLE"),
                                              (Source.STRATEGY_TRADE, "STRATEGY")])
def test_trade_size_threshold(source: Source, kind: str) -> None:
    """Preço e fonte corretos só disparam com tamanho suficiente no próprio negócio."""
    book = BookView()
    book.advance(q().model_copy(update={"ts": NOW}))
    trigger = Trigger(SPEC.model_copy(update={"source": source}))
    trigger.arm(book, NOW)
    for size, expected in [(9, Outcome.NONE), (10, Outcome.FIRED)]:
        event = trade(kind, size=size)
        book.advance(event)
        assert trigger.on_event(event, book) == expected
