"""Contrato síncrono de ordens limitadas do simulador."""
from datetime import datetime
from decimal import Decimal
from typing import NamedTuple, Protocol

from backend.derivatives.ticket.models import Instant, PositiveInt, Side, Text, _Frozen
from backend.derivatives.ticket.replay import Price
from backend.derivatives.ticket.state import Event, OrderState


class VenueOrder(_Frozen):
    """Tentativa de envio com preço e validade nativos."""
    order_id: Text
    symbol: Text
    side: Side
    quantity: PositiveInt
    limit_price: Price
    lot_size: PositiveInt
    valid_until: Instant


class VenueReport(NamedTuple):
    """Fato da venue, com quantidade e preço apenas em execução."""
    order_id: str
    event: Event
    quantity: int | None
    price: Decimal | None
    ts: datetime
    fact: str | None = None
    corrects: str | None = None


class OrderSnapshot(NamedTuple):
    """Último estado registrado e saldo ainda vivo."""
    state: OrderState
    filled: int
    remaining: int


class VenueRefusal(ValueError):
    """Pedido impossível na sessão simulada."""


class ExecutionVenue(Protocol):
    """Operações permitidas pelo motor em uma sessão."""
    def accepts_validity(self, valid_until: datetime) -> bool:
        """Consulta a validade garantida."""
        ...
    def submit(self, order: VenueOrder, now: datetime) -> VenueReport:
        """Tenta registrar uma nova ordem."""
        ...
    def request_cancel(self, order_id: str, now: datetime) -> None:
        """Solicita cancelamento do saldo."""
        ...
    def poll(self, order_id: str) -> OrderSnapshot | None:
        """Consulta a ordem registrada."""
        ...
