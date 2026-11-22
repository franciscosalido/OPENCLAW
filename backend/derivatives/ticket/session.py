"""Condutor determinístico de boletas sobre uma única fita sintética."""
from dataclasses import dataclass
from datetime import datetime

from backend.derivatives.ticket.engine import AccountHalts, TicketEngine
from backend.derivatives.ticket.gate import DecisionLedger
from backend.derivatives.ticket.guards import BookView
from backend.derivatives.ticket.models import TicketDraft
from backend.derivatives.ticket.paper_venue import PaperVenue
from backend.derivatives.ticket.receipt import Receipt
from backend.derivatives.ticket.replay import Replay
from backend.derivatives.ticket.sequencing import Position, ReservationBook
from backend.derivatives.ticket.venue import VenueRefusal
from config.ticket_sim_config_model import TicketSimConfig


class SessionRefusal(ValueError):
    """Fita ou roteiro incompatível com a sessão."""


@dataclass(frozen=True)
class _Ticket:
    account: str
    engine: TicketEngine
    receipt: Receipt


class ReplaySession:
    """Distribui os mesmos eventos, livro, venue e recursos de conta entre as boletas."""

    def __init__(self, replay: Replay, *, config: TicketSimConfig) -> None:
        if replay.events and replay.events[0].seq <= 0:
            raise SessionRefusal("after_seq=0 reservado para antes do primeiro evento")
        self._events = replay.events
        self._cursor = 0
        self._config = config
        self._book = BookView()
        self._venue = PaperVenue(replay.session_close)
        self._reservations = ReservationBook()
        self._ledger = DecisionLedger()
        self._halts = AccountHalts()
        self._tickets: dict[str, _Ticket] = {}

    def open(self, ticket: str, position: Position, draft: TicketDraft,
             now: datetime) -> TicketEngine:
        """Registra a boleta somente depois que a proposta gera a primeira prévia."""
        if any(name.casefold() == ticket.casefold() for name in self._tickets):
            raise SessionRefusal("boleta já aberta")
        receipt = Receipt()
        engine = TicketEngine(ticket, position, venue=self._venue, book=self._book,
                              reservations=self._reservations, ledger=self._ledger,
                              halts=self._halts, receipt=receipt, config=self._config)
        engine.propose(draft, now)
        self._tickets[ticket] = _Ticket(position.account, engine, receipt)
        return engine

    def engine(self, ticket: str) -> TicketEngine:
        """Motor de uma boleta aberta."""
        return self._tickets[ticket].engine

    def receipt(self, ticket: str) -> Receipt:
        """Recibo de uma boleta aberta."""
        return self._tickets[ticket].receipt

    def advance_to(self, seq: int) -> None:
        """Processa até a sequência inclusiva, respeitando lacunas da fita."""
        if self._cursor and seq < self._events[self._cursor - 1].seq:
            raise SessionRefusal("retrocesso de sequência")
        while self._cursor < len(self._events):
            ev = self._events[self._cursor]
            if ev.seq > seq:
                break
            self._book.advance(ev)
            try:
                reports = self._venue.advance(ev)
            except VenueRefusal as exc:
                raise SessionRefusal(str(exc)) from exc
            for ticket in self._tickets.values():
                engine = ticket.engine
                orders = engine.orders
                engine.on_reports([r for r in reports if r.order_id in orders], ev.ts)
                engine.on_market(ev)
            self._cursor += 1

    def finish(self) -> None:
        """Consome o restante da fita."""
        if self._events:
            self.advance_to(self._events[-1].seq)

    def check_time(self, at: datetime) -> None:
        """Valida o instante do passo entre os dois eventos que o delimitam."""
        if at.utcoffset() is None:
            raise SessionRefusal("instante sem fuso")
        if self._cursor and at < self._events[self._cursor - 1].ts:
            raise SessionRefusal("passo anterior ao último evento")
        if self._cursor < len(self._events) and at > self._events[self._cursor].ts:
            raise SessionRefusal("passo posterior ao próximo evento")

    def summary(self) -> dict[str, object]:
        """Apura os estados do motor e as quantidades confirmadas pela venue."""
        tickets = {}
        blocked = set()
        for name, ticket in self._tickets.items():
            engine = ticket.engine
            if self._halts.blocked(ticket.account):
                blocked.add(ticket.account)
            orders = {}
            for oid, state in engine.orders.items():
                snap = self._venue.poll(oid)
                orders[oid] = {"estado": state.value, "executado": snap.filled if snap else 0}
            events = ticket.receipt.events
            gross = engine.gross()
            bruto = {"assinado": f"{gross.signed:.2f}", "executado": f"{gross.executed:.2f}",
                     "projetado": f"{gross.projected:.2f}"}
            tickets[name] = {"conta": ticket.account, "estado": engine.state.value,
                             "pausada": engine.paused, "ordens": orders, "bruto": bruto,
                             "recibo_eventos": len(events), "recibo_hash": events[-1].hash}
        return {"aviso": "SIMULADO — resultado em papel é teto otimista, não previsão.",
                "eventos": self._cursor, "contas_bloqueadas": sorted(blocked), "boletas": tickets}
