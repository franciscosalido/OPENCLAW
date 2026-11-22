"""Eventos imutáveis e leitura estrita de uma sessão sintética."""
import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationError, model_validator

from backend.derivatives.ticket.models import Instant, Money, Text, _Frozen

type Price = Annotated[Money, Field(gt=0)]
type Size = Annotated[int, Field(ge=0)]
type Phase = Literal["CONTINUOUS", "AUCTION", "SUSPENDED"]


class ReplayError(ValueError):
    """Arquivo inválido ou eventos fora de ordem."""


class _Event(_Frozen):
    seq: int
    ts: Instant
    gap_before: bool = False


class QuoteEvent(_Event):
    """Livro agregado observado em uma fase de negociação."""
    type: Literal["quote"]
    symbol: Text
    bid: Price | None
    bid_size: Size
    ask: Price | None
    ask_size: Size
    phase: Phase

    @model_validator(mode="after")
    def _empty_sides(self) -> Self:
        if (self.bid is None and self.bid_size) or (self.ask is None and self.ask_size):
            raise ValueError("tamanho inválido para lado vazio")
        return self


class AuctionFill(_Event):
    """Quantidade disponível a um preço de leilão."""
    type: Literal["auction_fill"]
    symbol: Text
    price: Price
    size: Size


class TradeEvent(_Event):
    """Negócio simples ou de estratégia, sem liquidez ofertada."""
    type: Literal["trade"]
    symbol: Text
    price: Price
    size: Size
    kind: Literal["SIMPLE", "STRATEGY"]


class CancelRejected(_Event):
    """Recusa explícita de um pedido de cancelamento."""
    type: Literal["cancel_rejected"]
    order: Text


class VenueTimeout(_Event):
    """Resultado oculto da próxima tentativa de envio."""
    type: Literal["timeout"]
    call: Literal["submit"]
    registered: bool


type ReplayEvent = QuoteEvent | TradeEvent | AuctionFill | CancelRejected | VenueTimeout


class Replay(_Frozen):
    """Sessão ordenada com validade nativa de dia."""
    session_close: Instant
    events: tuple[Annotated[ReplayEvent, Field(discriminator="type")], ...]


def _unique(items: list[tuple[str, object]]) -> dict[str, object]:
    data = dict(items)
    if len(data) != len(items) or "gap_before" in data:
        raise ReplayError("formato inválido")
    return data


def load_replay(path: Path) -> Replay:
    """Lê JSON sem chaves duplicadas e identifica saltos na sequência."""
    try:
        raw = json.loads(path.read_bytes(), object_pairs_hook=_unique)
        replay = Replay.model_validate_json(json.dumps(raw, allow_nan=False))
    except ValidationError as exc:
        error = exc.errors()[0]
        field = error["loc"][-1] if error["loc"] else ""
        reasons = {"bid": "preço inválido", "ask": "preço inválido", "price": "preço inválido",
                   "ts": "tempo inválido", "session_close": "tempo inválido",
                   "bid_size": "tamanho inválido", "ask_size": "tamanho inválido",
                   "size": "tamanho inválido", "quote": "tamanho inválido"}
        if error["type"] in {"extra_forbidden", "missing"}:
            field = ""
        reason = reasons.get(str(field), "formato inválido")
        raise ReplayError(f"{reason}: {error['msg']}") from exc
    except (ValueError, OSError) as exc:
        raise ReplayError("formato inválido") from exc
    events = list(replay.events)
    for i, (prev, curr) in enumerate(zip(events, events[1:]), 1):
        if curr.seq <= prev.seq or curr.ts < prev.ts:
            raise ReplayError("sequência inválida" if curr.seq <= prev.seq else "tempo inválido")
        events[i] = curr.model_copy(update={"gap_before": curr.seq > prev.seq + 1})
    return replay.model_copy(update={"events": tuple(events)})
