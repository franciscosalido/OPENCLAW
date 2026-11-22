"""Avaliação do livro sintético e dos prazos assinados."""
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Literal, NamedTuple, Sequence

from backend.derivatives.ticket.models import Leg, Side, TicketDraft
from backend.derivatives.ticket.replay import Phase, QuoteEvent, ReplayEvent
from backend.derivatives.ticket.sequencing import _exact
from backend.derivatives.ticket.venue import ExecutionVenue
from config.ticket_sim_config_model import TicketSimConfig


class BookSnapshot(NamedTuple):
    """Última foto da série e integridade da sequência global."""
    symbol: str
    bid: Decimal | None
    bid_size: int
    ask: Decimal | None
    ask_size: int
    phase: Phase
    ts: datetime
    sequence_ok: bool


class BookView:
    """Acumula cotações e conserva falhas de sequência até o fim da sessão."""
    def __init__(self) -> None:
        self._quotes: dict[str, QuoteEvent] = {}
        self._ok = True

    def advance(self, event: ReplayEvent) -> None:
        """Incorpora um evento antes da próxima avaliação."""
        self._ok = self._ok and not event.gap_before
        if isinstance(event, QuoteEvent):
            self._quotes[event.symbol] = event

    def snapshot(self, symbol: str) -> BookSnapshot | None:
        """Consulta a foto na sequência atual do replay."""
        q = self._quotes.get(symbol)
        return None if q is None else BookSnapshot(symbol, q.bid, q.bid_size, q.ask, q.ask_size,
                                  q.phase, q.ts, self._ok)


class GuardResult(NamedTuple):
    """Pior nível e razões ordenadas por perna."""
    level: Literal["OK", "CAUTION", "BLOCKED"]
    reasons: tuple[str, ...]


def assess(legs: Sequence[Leg], book: BookView, now: datetime, config: TicketSimConfig
           ) -> GuardResult:
    """Confere as travas na ordem da tabela aprovada."""
    reasons: list[str] = []
    blocked = False
    for leg in legs:
        q = book.snapshot(leg.symbol)
        if q is None:
            reasons.append("sem cotação")
            blocked = True
            continue
        age = (now - q.ts).total_seconds()
        price, size = (q.ask, q.ask_size) if leg.side is Side.BUY else (q.bid, q.bid_size)
        with localcontext(_exact()):
            spread = q.ask - q.bid if q.ask is not None and q.bid is not None else None
            wide = spread is not None and spread > Decimal(".01") * config.max_spread_ticks
        for condition, reason, block in (
            (age > config.max_quote_age_s, "cotação vencida", True),
            (q.phase == "AUCTION", "leilão", True), (q.phase == "SUSPENDED", "suspensão", True),
            (spread is not None and spread <= 0, "livro inválido", True),
            (price is None, "livro incompleto", True),
            (not q.sequence_ok, "perda de sequência", True), (wide, "spread aberto", False),
            (price is not None and size < leg.quantity, "pouca profundidade", False),
            (age < 0, "tempo inválido", True),
        ):
            if condition:
                reasons.append(reason)
                blocked |= block
    return GuardResult("BLOCKED" if blocked else "CAUTION" if reasons else "OK", tuple(reasons))


class DeadlineRefusal(ValueError):
    """O envio ultrapassa o prazo ou a validade nativa."""


def check_deadlines(draft: TicketDraft, now: datetime, venue: ExecutionVenue) -> None:
    """Confere o último instante de envio e a validade garantida."""
    if now > draft.send_deadline:
        raise DeadlineRefusal("prazo de envio vencido")
    if draft.send_deadline > draft.order_validity:
        raise DeadlineRefusal("prazo de envio depois da validade")
    if now >= draft.order_validity:
        raise DeadlineRefusal("validade encerrada")
    if not venue.accepts_validity(draft.order_validity):
        raise DeadlineRefusal("validade que a venue não garante")
