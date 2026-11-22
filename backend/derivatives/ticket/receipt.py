"""Recibo append-only local, independente das máquinas de estado."""
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from hmac import compare_digest
from typing import Never

from backend.derivatives.ticket.models import Preview
from backend.derivatives.ticket.state import Event

_GENESIS = "0" * 64


class ReceiptError(ValueError):
    """O recibo contém dados inválidos ou uma prévia adulterada."""


def _encode(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    fields = dict(items)
    if len(fields) != len(items):
        raise ReceiptError("chave duplicada")
    return fields


def _invalid_constant(_text: str) -> Never:
    raise ReceiptError("número não finito")


def _decode(raw: bytes) -> dict[str, object]:
    value: object = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
    if not isinstance(value, dict) or _encode(value) != raw:
        raise ReceiptError("payload deve ser objeto JSON canônico")
    return value


def _timestamp(ts: datetime) -> datetime:
    if type(ts) is not datetime or ts.utcoffset() is None:
        raise ReceiptError("timestamp sem fuso")
    return ts.astimezone(UTC)


def _event_hash(seq: int, ts: datetime, kind: Event, payload: bytes, prev_hash: str) -> str:
    body = [seq, _timestamp(ts).isoformat(), kind.value, payload.decode("utf-8"), prev_hash]
    return sha256(_encode(body)).hexdigest()


@dataclass(frozen=True, slots=True)
class ReceiptEvent:
    """Entrada imutável com bytes canônicos e vínculo ao hash da anterior."""

    seq: int
    ts: datetime
    kind: Event
    payload: bytes
    prev_hash: str
    hash: str

    def read_preview(self) -> Preview:
        """Valida o conteúdo completo e reavalia o digest de autorização."""
        if self.kind is not Event.PREVIEW:
            raise ReceiptError("evento não é prévia")
        try:
            envelope = _decode(self.payload)
            if set(envelope) != {"preview", "digest"}:
                raise ReceiptError("envelope da prévia inválido")
            body, claimed = envelope["preview"], envelope["digest"]
            preview = Preview.model_validate_json(_encode(body))
            if preview.model_dump(mode="json", exclude={"digest"}) != body:
                raise ReceiptError("conteúdo da prévia incompleto ou não canônico")
            if type(claimed) is not str or not compare_digest(preview.digest, claimed):
                raise ReceiptError("digest da prévia divergente")
            return preview
        except ReceiptError:
            raise
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise ReceiptError("prévia inválida") from exc


class Receipt:
    """Acumula eventos; só um hash externo conhecido detecta truncamento."""

    def __init__(self) -> None:
        self._events: list[ReceiptEvent] = []

    @property
    def events(self) -> tuple[ReceiptEvent, ...]:
        """Retorna foto imutável dos eventos registrados."""
        return tuple(self._events)

    def append(self, ts: datetime, kind: Event, payload: Mapping[str, object]) -> ReceiptEvent:
        """Registra evento sem mutar o payload do chamador."""
        if not isinstance(kind, Event) or kind is Event.PREVIEW:
            raise ReceiptError("tipo de evento inválido ou reservado")
        return self._append(ts, kind, payload)

    def append_preview(self, ts: datetime, preview: Preview) -> ReceiptEvent:
        """Registra corpo integral e digest separado; não confia em cópias forjadas."""
        try:
            validated = Preview.model_validate(preview)
            body = validated.model_dump(mode="json", exclude={"digest"})
            return self._append(ts, Event.PREVIEW, {"preview": body, "digest": validated.digest})
        except ReceiptError:
            raise
        except (TypeError, ValueError) as exc:
            raise ReceiptError("prévia inválida") from exc

    def _append(self, ts: datetime, kind: Event, payload: Mapping[str, object]) -> ReceiptEvent:
        try:
            raw = _encode(dict(payload))
            _decode(raw)
            seq = len(self._events) + 1
            prev = self._events[-1].hash if self._events else _GENESIS
            stamp = _timestamp(ts)
            event_hash = _event_hash(seq, stamp, kind, raw, prev)
            event = ReceiptEvent(seq, stamp, kind, raw, prev, event_hash)
        except ReceiptError:
            raise
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise ReceiptError("evento inválido") from exc
        self._events.append(event)
        return event

    def verify(self, events: Iterable[ReceiptEvent] | None = None, *,
               expected_head: str | None = None) -> bool:
        """Verifica sequência, links, payload, prévias e âncora opcional."""
        previous = _GENESIS
        try:
            for seq, event in enumerate(self._events if events is None else events, 1):
                if (type(event) is not ReceiptEvent or type(event.seq) is not int
                        or event.seq != seq or event.prev_hash != previous
                        or type(event.kind) is not Event or type(event.payload) is not bytes):
                    return False
                _decode(event.payload)
                if event.kind is Event.PREVIEW:
                    event.read_preview()
                actual = _event_hash(seq, event.ts, event.kind, event.payload, previous)
                if not compare_digest(actual, event.hash):
                    return False
                previous = actual
            return expected_head is None or compare_digest(previous, expected_head)
        except (TypeError, ValueError, OverflowError, RecursionError):
            return False
