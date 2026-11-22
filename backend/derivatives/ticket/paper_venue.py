"""Venue local determinística com liquidez consumida por ordem de chegada."""
from dataclasses import dataclass
from datetime import datetime

from backend.derivatives.ticket.models import Side
from backend.derivatives.ticket.replay import (
    AuctionFill, CancelRejected, QuoteEvent, ReplayEvent, VenueTimeout,
)
from backend.derivatives.ticket.state import Event as E, OrderState as S
from backend.derivatives.ticket.venue import OrderSnapshot, VenueOrder, VenueRefusal, VenueReport


@dataclass
class _Entry:
    order: VenueOrder
    state: S = S.LIVE
    filled: int = 0
    cancel: bool = False

    @property
    def remaining(self) -> int:
        return self.order.quantity - self.filled if self.state in (S.LIVE, S.PARTIAL) else 0


class PaperVenue:
    """Sessão síncrona limitada ao fechamento do replay."""
    def __init__(self, session_close: datetime) -> None:
        self._close = session_close
        self._orders: dict[str, _Entry] = {}
        self._timeout: bool | None = None
        self._phases: dict[str, str] = {}

    def accepts_validity(self, valid_until: datetime) -> bool:
        """Garante somente a validade nativa até o fechamento."""
        return valid_until == self._close

    def submit(self, order: VenueOrder, now: datetime) -> VenueReport:
        """Abre uma tentativa independente sem consumir liquidez anterior."""
        order = VenueOrder.model_validate(order)
        timeout, self._timeout = self._timeout, None
        if (not self.accepts_validity(order.valid_until) or order.quantity % order.lot_size
                or order.order_id in self._orders or now >= self._close):
            event = E.VENUE_REJECTED
        else:
            if timeout is not False:
                self._orders[order.order_id] = _Entry(order)
            event = E.VENUE_LIVE if timeout is None else E.UNCERTAIN
        return VenueReport(order.order_id, event, None, None, now)

    def request_cancel(self, order_id: str, now: datetime) -> None:
        """Registra pedido humano sem alterar o saldo vivo."""
        entry = self._orders.get(order_id)
        if entry is None or not entry.remaining:
            raise VenueRefusal("ordem desconhecida ou terminal")
        entry.cancel = True

    def poll(self, order_id: str) -> OrderSnapshot | None:
        """Consulta o estado efetivo da ordem registrada na venue."""
        e = self._orders.get(order_id)
        return None if e is None else OrderSnapshot(e.state, e.filled, e.remaining)

    def advance(self, event: ReplayEvent) -> tuple[VenueReport, ...]:
        """Processa um evento, priorizando expiração, execução e confirmação de cancelamento."""
        ts = event.ts
        reports: list[VenueReport] = []
        if ts >= self._close:
            for oid, entry in self._orders.items():
                if entry.remaining:
                    entry.state, entry.cancel = S.EXPIRED, False
                    reports.append(VenueReport(oid, E.VENUE_EXPIRED, None, None, ts))
        elif isinstance(event, VenueTimeout):
            self._timeout = event.registered
        elif isinstance(event, CancelRejected):
            pending = self._orders.get(event.order)
            if pending is None or not pending.cancel:
                raise VenueRefusal("recusa sem pedido de cancelamento")
            pending.cancel = False
            kind = (E.VENUE_CANCEL_REJECTED_PARTIAL if pending.filled
                    else E.VENUE_CANCEL_REJECTED_LIVE)
            reports.append(VenueReport(event.order, kind, None, None, ts))
        elif isinstance(event, (AuctionFill, QuoteEvent)):
            if isinstance(event, QuoteEvent):
                self._phases[event.symbol] = event.phase
                if event.phase != "CONTINUOUS":
                    return ()
            elif self._phases.get(event.symbol) not in ("AUCTION", "SUSPENDED"):
                return ()
            liquidity: dict[Side | None, int] = (
                {None: event.size} if isinstance(event, AuctionFill)
                else {Side.BUY: event.ask_size, Side.SELL: event.bid_size})
            for oid, entry in self._orders.items():
                order = entry.order
                if not entry.remaining or order.symbol != event.symbol:
                    continue
                buy = order.side is Side.BUY
                pool = None if isinstance(event, AuctionFill) else order.side
                price = event.price if isinstance(event, AuctionFill) else (
                    event.ask if buy else event.bid)
                qty = min(entry.remaining, liquidity[pool])
                if qty and price is not None and (
                        price <= order.limit_price if buy else price >= order.limit_price):
                    entry.filled += qty
                    entry.state = S.PARTIAL if entry.remaining else S.FILLED
                    liquidity[pool] -= qty
                    kind = E.VENUE_PARTIAL if entry.remaining else E.VENUE_FILL
                    reports.append(VenueReport(oid, kind, qty, price, ts))
                if not entry.remaining:
                    entry.cancel = False
                elif entry.cancel and isinstance(event, QuoteEvent):
                    entry.state, entry.cancel = S.CANCELLED, False
                    reports.append(VenueReport(oid, E.VENUE_CANCELLED, None, None, ts))
        return tuple(reports)
