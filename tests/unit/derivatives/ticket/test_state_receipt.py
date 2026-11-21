"""Contrato de transições, integridade e leitura do recibo simulado."""
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from backend.derivatives.ticket.models import Leg, Preview, Side
from backend.derivatives.ticket.receipt import Receipt, ReceiptError
from backend.derivatives.ticket.state import (
    ORDER_TRANSITIONS, TICKET_TRANSITIONS, Event, InvalidTransition, OrderState, TicketState,
    reconcile, transition,
)

NOW = datetime(2026, 11, 21, tzinfo=UTC)


def test_matrix() -> None:
    """Cada par enum/evento segue estritamente a tabela publicada."""
    for states, table in ((TicketState, TICKET_TRANSITIONS), (OrderState, ORDER_TRANSITIONS)):
        for state in states:
            for event in Event:
                expected = table.get((state, event))
                if expected is None:
                    with pytest.raises(InvalidTransition):
                        transition(state, event)
                else:
                    assert transition(state, event) is expected


def test_terminal_and_uncertain() -> None:
    """Só reconciliação com evidência tira um estado da incerteza."""
    with pytest.raises(InvalidTransition):
        transition(OrderState.UNCERTAIN, Event.VENUE_FILL)
    with pytest.raises(InvalidTransition):
        reconcile(OrderState.UNCERTAIN, OrderState.FILLED, evidence="")
    with pytest.raises(InvalidTransition):
        reconcile(OrderState.CANCELLED, OrderState.FILLED, evidence="exec-1")
    with pytest.raises(InvalidTransition):
        reconcile(OrderState.UNCERTAIN, TicketState.STOPPED, evidence="exec-1")
    assert reconcile(OrderState.UNCERTAIN, OrderState.FILLED, evidence="exec-1") is (
        OrderState.FILLED
    )


def test_late_fill_is_not_lost() -> None:
    """Pedido de cancelamento e execução tardia subsistem em ordem de registro."""
    receipt = Receipt()
    ordered = transition(OrderState.LIVE, Event.REQUEST_CANCEL)
    assert ordered is OrderState.CANCEL_REQUESTED
    with pytest.raises(InvalidTransition):
        transition(ordered, Event.REQUEST_CANCEL)
    assert transition(ordered, Event.VENUE_CANCELLED) is OrderState.CANCELLED
    assert transition(ordered, Event.VENUE_FILL) is OrderState.FILLED
    first = receipt.append(NOW, Event.REQUEST_CANCEL, {"order": "sim-1"})
    second = receipt.append(NOW, Event.VENUE_FILL, {"qty": 10})
    assert receipt.events == (first, second) and receipt.verify()
    assert not receipt.verify((first, replace(second, payload=b'{"qty":11}')))
    assert not receipt.verify((second, first))
    assert not receipt.verify((first,), expected_head=second.hash)


def test_preview_round_trip_and_defensive_payload() -> None:
    """Recibo conserva versão e lote e não referencia o objeto do chamador."""
    receipt = Receipt()
    source = {"nested": [1]}
    event = receipt.append(NOW, Event.REQUEST_CANCEL, source)
    source["nested"].append(2)
    assert event.payload == b'{"nested":[1]}'
    preview = Preview(
        legs=(Leg(symbol="SYN", side=Side.BUY, quantity=20,
                  limit_price=Decimal("2.00"), lot_size=10),),
        net_limit=Decimal("40"), gross_cap=Decimal("40"),
        partial_exposure=Decimal("40"), send_deadline=NOW,
        order_validity=NOW, quote_snapshot_id="sim-q", version=4,
    )
    stored = receipt.append_preview(NOW, preview)
    assert stored.read_preview() == preview
    assert stored.read_preview().digest == preview.digest
    assert stored.read_preview().version == 4 and stored.read_preview().legs[0].lot_size == 10
    forged = replace(stored, payload=stored.payload.replace(b'"2.00"', b'"2.01"'))
    with pytest.raises(ReceiptError, match="digest"):
        forged.read_preview()
    assert receipt.verify()
