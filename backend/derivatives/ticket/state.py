"""Máquinas de estados puras da boleta e das ordens simuladas."""
from enum import StrEnum
from types import MappingProxyType


class TicketState(StrEnum):
    """Estado do conjunto, independente dos estados de cada perna."""

    DRAFT = "DRAFT"
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"
    CONFIRMED = "CONFIRMED"
    WORKING = "WORKING"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    UNCERTAIN = "UNCERTAIN"


class OrderState(StrEnum):
    """Estado de uma ordem conforme eventos do simulador da venue."""

    PENDING_SEND = "PENDING_SEND"
    LIVE = "LIVE"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    UNCERTAIN = "UNCERTAIN"


class Event(StrEnum):
    """Evento de replay aceito por uma máquina ou registrado no recibo."""

    DIVERGENCE = "divergence"
    PAUSE = "pause"
    RESUME = "resume"
    PREVIEW = "preview"
    ARM = "arm"
    TRIGGER = "trigger"
    CONFIRM = "confirm"
    DENY = "deny"
    START = "start"
    COMPLETE = "complete"
    STOP = "stop"
    EXPIRE = "expire"
    UNCERTAIN = "uncertain"
    RECONCILE = "reconcile"
    REQUEST_CANCEL = "request_cancel"
    VENUE_LIVE = "venue_live"
    VENUE_PARTIAL = "venue_partial"
    VENUE_FILL = "venue_fill"
    VENUE_CANCELLED = "venue_cancelled"
    VENUE_CANCEL_REJECTED_LIVE = "venue_cancel_rejected_live"
    VENUE_CANCEL_REJECTED_PARTIAL = "venue_cancel_rejected_partial"
    VENUE_EXPIRED = "venue_expired"
    VENUE_REJECTED = "venue_rejected"


class InvalidTransition(ValueError):
    """O evento ou a reconciliação não autoriza o destino solicitado."""


type State = TicketState | OrderState
_T, _O, _E = TicketState, OrderState, Event
TICKET_TRANSITIONS = MappingProxyType({
    (_T.DRAFT, _E.ARM): _T.ARMED,
    (_T.DRAFT, _E.CONFIRM): _T.CONFIRMED,
    (_T.DRAFT, _E.DENY): _T.DENIED,
    (_T.DRAFT, _E.EXPIRE): _T.EXPIRED,
    (_T.ARMED, _E.TRIGGER): _T.TRIGGERED,
    (_T.ARMED, _E.DENY): _T.DENIED,
    (_T.ARMED, _E.EXPIRE): _T.EXPIRED,
    (_T.TRIGGERED, _E.CONFIRM): _T.CONFIRMED,
    (_T.TRIGGERED, _E.DENY): _T.DENIED,
    (_T.TRIGGERED, _E.EXPIRE): _T.EXPIRED,
    (_T.CONFIRMED, _E.START): _T.WORKING,
    (_T.CONFIRMED, _E.STOP): _T.STOPPED,
    (_T.CONFIRMED, _E.EXPIRE): _T.EXPIRED,
    (_T.CONFIRMED, _E.UNCERTAIN): _T.UNCERTAIN,
    (_T.WORKING, _E.COMPLETE): _T.COMPLETED,
    (_T.WORKING, _E.STOP): _T.STOPPED,
    (_T.WORKING, _E.UNCERTAIN): _T.UNCERTAIN,
})
ORDER_TRANSITIONS = MappingProxyType({
    (_O.PENDING_SEND, _E.VENUE_LIVE): _O.LIVE,
    (_O.PENDING_SEND, _E.VENUE_PARTIAL): _O.PARTIAL,
    (_O.PENDING_SEND, _E.VENUE_FILL): _O.FILLED,
    (_O.PENDING_SEND, _E.VENUE_REJECTED): _O.REJECTED,
    (_O.PENDING_SEND, _E.UNCERTAIN): _O.UNCERTAIN,
    (_O.LIVE, _E.REQUEST_CANCEL): _O.CANCEL_REQUESTED,
    (_O.LIVE, _E.VENUE_PARTIAL): _O.PARTIAL,
    (_O.LIVE, _E.VENUE_FILL): _O.FILLED,
    (_O.LIVE, _E.VENUE_EXPIRED): _O.EXPIRED,
    (_O.LIVE, _E.UNCERTAIN): _O.UNCERTAIN,
    (_O.PARTIAL, _E.REQUEST_CANCEL): _O.CANCEL_REQUESTED,
    (_O.PARTIAL, _E.VENUE_PARTIAL): _O.PARTIAL,
    (_O.PARTIAL, _E.VENUE_FILL): _O.FILLED,
    (_O.PARTIAL, _E.VENUE_EXPIRED): _O.EXPIRED,
    (_O.PARTIAL, _E.UNCERTAIN): _O.UNCERTAIN,
    (_O.CANCEL_REQUESTED, _E.VENUE_PARTIAL): _O.CANCEL_REQUESTED,
    (_O.CANCEL_REQUESTED, _E.VENUE_FILL): _O.FILLED,
    (_O.CANCEL_REQUESTED, _E.VENUE_CANCELLED): _O.CANCELLED,
    (_O.CANCEL_REQUESTED, _E.VENUE_CANCEL_REJECTED_LIVE): _O.LIVE,
    (_O.CANCEL_REQUESTED, _E.VENUE_CANCEL_REJECTED_PARTIAL): _O.PARTIAL,
    (_O.CANCEL_REQUESTED, _E.VENUE_EXPIRED): _O.EXPIRED,
    (_O.CANCEL_REQUESTED, _E.UNCERTAIN): _O.UNCERTAIN,
})
LABELS_PT = MappingProxyType({
    **dict(zip(_T, ("Proposta", "Engatilhada", "Gatilho atingido", "Confirmada", "Em execução",
                    "Concluída", "Parada", "Negada", "Expirada", "Estado incerto"), strict=True)),
    **dict(zip(_O, ("Envio pendente", "Viva", "Parcial", "Executada",
                    "Cancelamento solicitado", "Cancelada", "Expirada",
                    "Recusada pela venue", "Estado incerto"), strict=True)),
})


def transition(state: State, event: Event) -> State:
    """Aplica uma única aresta normal, sem tratar evidência de reconciliação."""
    if isinstance(event, Event):
        next_state: State | None = None
        if isinstance(state, TicketState):
            next_state = TICKET_TRANSITIONS.get((state, event))
        elif isinstance(state, OrderState):
            next_state = ORDER_TRANSITIONS.get((state, event))
        if next_state is not None:
            return next_state
    raise InvalidTransition(f"transição inválida: {state!s} / {event!s}")


def reconcile(state: State, resolved: State, *, evidence: str) -> State:
    """Resolve incerteza do mesmo tipo com uma referência de evidência não vazia."""
    if type(evidence) is str and evidence.strip() and type(state) is type(resolved):
        if state is _T.UNCERTAIN and resolved in (_T.WORKING, _T.COMPLETED, _T.STOPPED):
            return resolved
        if state is _O.UNCERTAIN and resolved in (
            _O.LIVE, _O.PARTIAL, _O.FILLED, _O.CANCEL_REQUESTED, _O.CANCELLED, _O.EXPIRED,
            _O.REJECTED,
        ):
            return resolved
    raise InvalidTransition(f"reconciliação inválida: {state!s} / {resolved!s}")
