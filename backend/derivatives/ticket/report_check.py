"""Conferência pura compartilhada pela recepção e pela conciliação da fita da venue."""
from collections.abc import Mapping
from datetime import UTC
from typing import NamedTuple

from backend.derivatives.ticket.state import Event, InvalidTransition, OrderState, transition
from backend.derivatives.ticket.venue import VenueReport


class ReportCheck(NamedTuple):
    """Destino para fato aplicável, motivo para contradição; ambos ausentes em duplicata."""
    destination: OrderState | None = None
    reason: str | None = None


def check_report(r: VenueReport, state: OrderState, filled: int, requested: int,
                 facts: Mapping[str, VenueReport]) -> ReportCheck:
    """Classifica a mensagem contra o estado observado ou projetado, sem efeitos."""
    if r.corrects is not None:
        known = r.corrects in facts
        return ReportCheck(reason="correção oficial" if known else "correção sem fato original")
    prior = None if r.fact is None else facts.get(r.fact)
    if prior is not None:
        if (prior.order_id == r.order_id and prior.event == r.event
                and prior.corrects == r.corrects
                and type(prior.quantity) is type(r.quantity) and prior.quantity == r.quantity
                and str(prior.price) == str(r.price)
                and prior.ts.astimezone(UTC) == r.ts.astimezone(UTC)):
            return ReportCheck()
        return ReportCheck(reason="fato repetido com conteúdo diferente")
    try:
        destination = transition(state, r.event)
    except InvalidTransition:
        if not isinstance(r.event, Event):
            raise
        return ReportCheck(reason="relato impossível para o estado da ordem")
    if r.event in (Event.VENUE_FILL, Event.VENUE_PARTIAL):
        if type(r.quantity) is not int or r.quantity <= 0 or r.price is None:
            return ReportCheck(reason="execução malformada")
        if filled + r.quantity > requested:
            return ReportCheck(reason="execução acima da quantidade da ordem")
    assert isinstance(destination, OrderState)
    return ReportCheck(destination)
