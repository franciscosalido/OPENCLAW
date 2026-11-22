"""Gatilho de aviso de uso único dirigido pelo replay."""
import json
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256

from backend.derivatives.ticket.digest import _money
from backend.derivatives.ticket.guards import BookSnapshot, BookView
from backend.derivatives.ticket.models import Instant, PositiveInt, Text, _Frozen
from backend.derivatives.ticket.replay import Price, QuoteEvent, ReplayEvent, TradeEvent


class Source(StrEnum):
    """Campo do livro ou espécie de negócio que alimenta a condição."""
    BID = "BID"
    ASK = "ASK"
    SIMPLE_TRADE = "SIMPLE_TRADE"
    STRATEGY_TRADE = "STRATEGY_TRADE"


class Direction(StrEnum):
    """Comparação inclusiva do preço com o limiar."""
    AT_OR_ABOVE = "AT_OR_ABOVE"
    AT_OR_BELOW = "AT_OR_BELOW"


class TriggerSpec(_Frozen):
    """Condição assinável com fonte, tamanho mínimo e prazo explícitos."""
    symbol: Text
    source: Source
    direction: Direction
    threshold: Price
    min_size: PositiveInt
    armed_until: Instant


def spec_digest(spec: TriggerSpec) -> str:
    """Resume os seis campos usando preço canônico e instante UTC."""
    spec = TriggerSpec.model_validate(spec)
    payload = (spec.symbol, spec.source, spec.direction, _money(spec.threshold),
               spec.min_size, spec.armed_until.isoformat())
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


class TriggerState(StrEnum):
    """Estado após a primeira armação bem-sucedida."""
    ARMED = "ARMED"
    FIRED = "FIRED"
    EXPIRED = "EXPIRED"
    DISARMED = "DISARMED"


class Outcome(StrEnum):
    """Resultado observável de um evento do replay."""
    NONE = "NONE"
    FIRED = "FIRED"
    EXPIRED = "EXPIRED"


class TriggerRefusal(ValueError):
    """Operação incompatível com o prazo, a foto ou o estado do gatilho."""


def _invalid(q: BookSnapshot | None) -> str | None:
    if q is None:
        return "sem cotação"
    if not q.sequence_ok:
        return "perda de sequência"
    if q.phase != "CONTINUOUS":
        return "fora do contínuo"
    if q.bid is not None and q.ask is not None and q.bid >= q.ask:
        return "livro inválido"
    return None


class Trigger:
    """Vigia uma única condição; o estado inicial precede a armação."""
    def __init__(self, spec: TriggerSpec) -> None:
        self._spec = TriggerSpec.model_validate(spec)
        self._state: TriggerState | None = None

    @property
    def state(self) -> TriggerState | None:
        """Último estado; vazio antes de armar."""
        return self._state

    def _matches(self, price: Decimal | None, size: int) -> bool:
        s = self._spec
        return price is not None and size >= s.min_size and (
            price <= s.threshold if s.direction == Direction.AT_OR_BELOW else price >= s.threshold)

    def _quote(self, q: BookSnapshot | QuoteEvent) -> bool:
        if self._spec.source == Source.BID:
            return self._matches(q.bid, q.bid_size)
        return self._spec.source == Source.ASK and self._matches(q.ask, q.ask_size)

    def arm(self, book: BookView, now: datetime) -> None:
        """Arma somente em foto válida, com condição de cotação ainda falsa."""
        if self._state is not None:
            raise TriggerRefusal("gatilho já utilizado")
        if now.utcoffset() is None:
            raise TriggerRefusal("tempo inválido")
        if now.astimezone(UTC) >= self._spec.armed_until:
            raise TriggerRefusal("prazo vencido")
        q = book.snapshot(self._spec.symbol)
        if reason := _invalid(q):
            raise TriggerRefusal(reason)
        if q is not None and self._quote(q):
            raise TriggerRefusal("condição já verdadeira")
        self._state = TriggerState.ARMED

    def on_event(self, event: ReplayEvent, book: BookView) -> Outcome:
        """Avalia um evento após a atualização do livro pelo chamador."""
        if self._state != TriggerState.ARMED:
            return Outcome.NONE
        if event.ts > self._spec.armed_until:
            self._state = TriggerState.EXPIRED
            return Outcome.EXPIRED
        if not isinstance(event, (QuoteEvent, TradeEvent)) or event.symbol != self._spec.symbol:
            return Outcome.NONE
        if _invalid(book.snapshot(self._spec.symbol)):
            return Outcome.NONE
        if isinstance(event, QuoteEvent):
            hit = self._quote(event)
        else:
            source = Source.SIMPLE_TRADE if event.kind == "SIMPLE" else Source.STRATEGY_TRADE
            hit = source == self._spec.source and self._matches(event.price, event.size)
        if hit:
            self._state = TriggerState.FIRED
            return Outcome.FIRED
        return Outcome.NONE

    def disarm(self) -> None:
        """Encerra um gatilho armado sem emitir aviso."""
        if self._state != TriggerState.ARMED:
            raise TriggerRefusal("gatilho não armado")
        self._state = TriggerState.DISARMED
