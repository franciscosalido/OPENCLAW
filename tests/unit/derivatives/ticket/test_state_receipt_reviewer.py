"""Testes do revisor: tabela de estados fixada à mão e adulterações do recibo."""
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum

import pytest

from backend.derivatives.ticket import receipt as receipt_module
from backend.derivatives.ticket.models import Leg, Preview, Side, TicketDraft
from backend.derivatives.ticket.receipt import Receipt, ReceiptEvent
from backend.derivatives.ticket.state import (
    LABELS_PT, ORDER_TRANSITIONS, TICKET_TRANSITIONS, Event, InvalidTransition, OrderState,
    TicketState, reconcile,
)

NOW = datetime(2026, 11, 23, 14, tzinfo=UTC)

# Contrato escrito independentemente da tabela de produção: origem, evento, destino.
TICKET_CONTRACT = """
DRAFT arm ARMED | DRAFT confirm CONFIRMED | DRAFT deny DENIED | DRAFT expire EXPIRED
ARMED trigger TRIGGERED | ARMED deny DENIED | ARMED expire EXPIRED
TRIGGERED confirm CONFIRMED | TRIGGERED deny DENIED | TRIGGERED expire EXPIRED
CONFIRMED start WORKING | CONFIRMED stop STOPPED | CONFIRMED expire EXPIRED
CONFIRMED uncertain UNCERTAIN
WORKING complete COMPLETED | WORKING stop STOPPED | WORKING uncertain UNCERTAIN
"""
ORDER_CONTRACT = """
PENDING_SEND venue_live LIVE | PENDING_SEND venue_partial PARTIAL
PENDING_SEND venue_fill FILLED | PENDING_SEND venue_rejected REJECTED
PENDING_SEND uncertain UNCERTAIN
LIVE request_cancel CANCEL_REQUESTED | LIVE venue_partial PARTIAL | LIVE venue_fill FILLED
LIVE venue_expired EXPIRED | LIVE uncertain UNCERTAIN
PARTIAL request_cancel CANCEL_REQUESTED | PARTIAL venue_partial PARTIAL
PARTIAL venue_fill FILLED | PARTIAL venue_expired EXPIRED | PARTIAL uncertain UNCERTAIN
CANCEL_REQUESTED venue_partial CANCEL_REQUESTED | CANCEL_REQUESTED venue_fill FILLED
CANCEL_REQUESTED venue_cancelled CANCELLED
CANCEL_REQUESTED venue_cancel_rejected_live LIVE
CANCEL_REQUESTED venue_cancel_rejected_partial PARTIAL
CANCEL_REQUESTED venue_expired EXPIRED | CANCEL_REQUESTED uncertain UNCERTAIN
"""


def _rows(text: str) -> set[tuple[str, str, str]]:
    cells = [cell.split() for line in text.strip().splitlines() for cell in line.split("|")]
    return {(source, event, target) for source, event, target in cells}


@pytest.mark.parametrize(("table", "contract"), [
    (TICKET_TRANSITIONS, TICKET_CONTRACT), (ORDER_TRANSITIONS, ORDER_CONTRACT),
], ids=["ticket", "order"])
def test_reviewer_transition_table_is_pinned(
    table: Mapping[tuple[StrEnum, StrEnum], StrEnum], contract: str,
) -> None:
    """Um destino trocado na tabela não passa: o contrato está escrito fora dela."""
    published = {(str(s), str(e), str(t)) for (s, e), t in table.items()}
    assert published == _rows(contract)


def test_reviewer_reconcile_targets_are_exactly_the_verifiable_states() -> None:
    """A incerteza só resolve para estado que uma consulta à venue pode comprovar."""
    def allowed(source: TicketState | OrderState) -> set[str]:
        found = set()
        for target in type(source):
            try:
                found.add(str(reconcile(source, target, evidence="consulta-1")))
            except InvalidTransition:
                pass
        return found

    assert allowed(TicketState.UNCERTAIN) == {"WORKING", "COMPLETED", "STOPPED"}
    assert allowed(OrderState.UNCERTAIN) == {
        "LIVE", "PARTIAL", "FILLED", "CANCEL_REQUESTED", "CANCELLED", "EXPIRED", "REJECTED",
    }
    for source in (*TicketState, *OrderState):
        if source not in (TicketState.UNCERTAIN, OrderState.UNCERTAIN):
            assert allowed(source) == set()


def test_reviewer_labels_cover_both_enums_despite_equal_names() -> None:
    """EXPIRED e UNCERTAIN existem nos dois enums e comparam iguais como texto."""
    assert TicketState.EXPIRED == OrderState.EXPIRED
    for state in (*TicketState, *OrderState):
        assert LABELS_PT[state]
    assert len(LABELS_PT) == len(TicketState) + len(OrderState) - 2


def _receipt() -> tuple[Receipt, list[ReceiptEvent]]:
    draft = TicketDraft(
        legs=(Leg(symbol="A", side=Side.BUY, quantity=100, limit_price=Decimal("1.10"),
                  lot_size=100),),
        net_limit=Decimal("1.10"), gross_cap=Decimal("110"), send_deadline=NOW,
        order_validity=NOW + timedelta(hours=1), quote_snapshot_id="q",
    )
    receipt = Receipt()
    receipt.append_preview(NOW, Preview.from_draft(draft, partial_exposure=Decimal("110")))
    receipt.append(NOW, Event.CONFIRM, {"version": 1})
    receipt.append(NOW, Event.REQUEST_CANCEL, {"order": "1"})
    receipt.append(NOW, Event.VENUE_FILL, {"order": "1", "quantity": 100})
    return receipt, list(receipt.events)


@pytest.mark.parametrize("change", [
    {"ts": NOW + timedelta(seconds=1)}, {"kind": Event.DENY}, {"seq": 9},
    {"prev_hash": "f" * 64}, {"hash": "f" * 64},
], ids=["ts", "kind", "seq", "prev_hash", "hash"])
def test_reviewer_each_event_field_is_protected(change: dict[str, object]) -> None:
    """Alterar qualquer campo de um evento do meio invalida a cadeia."""
    receipt, events = _receipt()
    assert receipt.verify(events)
    events[1] = replace(events[1], **change)  # type: ignore[arg-type]
    assert not receipt.verify(events)


def _rehashed(payload: bytes, kind: Event) -> ReceiptEvent:
    genesis = "0" * 64
    digest = receipt_module._event_hash(1, NOW, kind, payload, genesis)
    return ReceiptEvent(1, NOW, kind, payload, genesis, digest)


def test_reviewer_forged_preview_with_recomputed_chain_fails() -> None:
    """Quem refaz os hashes da cadeia ainda esbarra no digest da prévia."""
    receipt, events = _receipt()
    forged = events[0].payload.replace(b'"net_limit":"1.10"', b'"net_limit":"9.99"')
    assert forged != events[0].payload
    assert not receipt.verify([_rehashed(forged, Event.PREVIEW)])
    assert receipt.verify([_rehashed(events[0].payload, Event.PREVIEW)])


def test_reviewer_duplicate_key_payload_fails_even_with_valid_hash() -> None:
    """Chave repetida esconderia um valor de quem lê só a última ocorrência."""
    assert not Receipt().verify([_rehashed(b'{"order":"1","order":"2"}', Event.STOP)])
    assert Receipt().verify([_rehashed(b'{"order":"1"}', Event.STOP)])


def test_reviewer_portuguese_labels_are_pinned_per_state() -> None:
    """Rótulo por estado escrito à mão; trocar a ordem do enum não passa."""
    ticket = {
        "DRAFT": "Proposta", "ARMED": "Engatilhada", "TRIGGERED": "Gatilho atingido",
        "CONFIRMED": "Confirmada", "WORKING": "Em execução", "COMPLETED": "Concluída",
        "STOPPED": "Parada", "DENIED": "Negada", "EXPIRED": "Expirada",
        "UNCERTAIN": "Estado incerto",
    }
    order = {
        "PENDING_SEND": "Envio pendente", "LIVE": "Viva", "PARTIAL": "Parcial",
        "FILLED": "Executada", "CANCEL_REQUESTED": "Cancelamento solicitado",
        "CANCELLED": "Cancelada", "EXPIRED": "Expirada", "REJECTED": "Recusada pela venue",
        "UNCERTAIN": "Estado incerto",
    }
    assert {str(state): LABELS_PT[state] for state in TicketState} == ticket
    assert {str(state): LABELS_PT[state] for state in OrderState} == order


def test_reviewer_append_stores_the_instant_in_utc() -> None:
    """Entrada às 09:00 de São Paulo fica gravada como 12:00 UTC, com o mesmo hash."""
    local = datetime(2026, 11, 23, 9, tzinfo=timezone(timedelta(hours=-3)))
    stored = Receipt().append(local, Event.STOP, {"order": "1"})
    assert stored.ts.tzinfo is UTC and stored.ts.hour == 12
    assert stored.hash == Receipt().append(local.astimezone(UTC), Event.STOP, {"order": "1"}).hash
