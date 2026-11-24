"""Contrato de transições, integridade e leitura do recibo simulado."""
import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

from backend.derivatives.ticket import receipt as wire
from backend.derivatives.ticket.models import Leg, Preview, Side
from backend.derivatives.ticket.receipt import Receipt, ReceiptError
from backend.derivatives.ticket.state import (
    ORDER_TRANSITIONS, TICKET_TRANSITIONS, Event, InvalidTransition, OrderState, TicketState,
    reconcile, transition,
)

NOW = datetime(2026, 11, 21, tzinfo=UTC)


def test_matrix() -> None:
    """Cada par enum/evento segue estritamente a tabela publicada."""
    for states, table in ((TicketState, TICKET_TRANSITIONS), (OrderState, ORDER_TRANSITIONS)):
        for state in states:
            for event in Event:
                expected = table.get((state, event))
                if expected is None:
                    with pytest.raises(InvalidTransition):
                        transition(state, event)
                else:
                    assert transition(state, event) is expected


def test_terminal_and_uncertain() -> None:
    """Só reconciliação com evidência tira um estado da incerteza."""
    with pytest.raises(InvalidTransition):
        transition(OrderState.UNCERTAIN, Event.VENUE_FILL)
    with pytest.raises(InvalidTransition):
        reconcile(OrderState.UNCERTAIN, OrderState.FILLED, evidence="")
    with pytest.raises(InvalidTransition):
        reconcile(OrderState.CANCELLED, OrderState.FILLED, evidence="exec-1")
    with pytest.raises(InvalidTransition):
        reconcile(OrderState.UNCERTAIN, TicketState.STOPPED, evidence="exec-1")
    assert reconcile(OrderState.UNCERTAIN, OrderState.FILLED, evidence="exec-1") is (
        OrderState.FILLED
    )


def test_late_fill_is_not_lost() -> None:
    """Pedido de cancelamento e execução tardia subsistem em ordem de registro."""
    receipt = Receipt()
    ordered = transition(OrderState.LIVE, Event.REQUEST_CANCEL)
    assert ordered is OrderState.CANCEL_REQUESTED
    with pytest.raises(InvalidTransition):
        transition(ordered, Event.REQUEST_CANCEL)
    assert transition(ordered, Event.VENUE_CANCELLED) is OrderState.CANCELLED
    assert transition(ordered, Event.VENUE_FILL) is OrderState.FILLED
    first = receipt.append(NOW, Event.REQUEST_CANCEL, {"order": "sim-1"})
    second = receipt.append(NOW, Event.VENUE_FILL, {"qty": 10})
    assert receipt.events == (first, second) and receipt.verify()
    assert not receipt.verify((first, replace(second, payload=b'{"qty":11}')))
    assert not receipt.verify((second, first))
    assert not receipt.verify((first,), expected_head=second.hash)


def test_preview_round_trip_and_defensive_payload() -> None:
    """Recibo conserva versão e lote e não referencia o objeto do chamador."""
    receipt = Receipt()
    source = {"nested": [1]}
    event = receipt.append(NOW, Event.REQUEST_CANCEL, source)
    source["nested"].append(2)
    assert event.payload == b'{"nested":[1]}'
    preview = Preview(
        legs=(Leg(symbol="SYN", side=Side.BUY, quantity=20,
                  limit_price=Decimal("2.00"), lot_size=10),),
        net_limit=Decimal("40"), gross_cap=Decimal("40"),
        partial_exposure=Decimal("40"), send_deadline=NOW,
        order_validity=NOW, quote_snapshot_id="sim-q", version=4,
    )
    stored = receipt.append_preview(NOW, preview)
    assert stored.read_preview() == preview
    assert stored.read_preview().digest == preview.digest
    assert stored.read_preview().version == 4 and stored.read_preview().legs[0].lot_size == 10
    forged = replace(stored, payload=stored.payload.replace(b'"2.00"', b'"2.01"'))
    with pytest.raises(ReceiptError, match="digest"):
        forged.read_preview()
    assert receipt.verify()


@pytest.mark.parametrize("state", [
    TicketState.COMPLETED, TicketState.STOPPED, TicketState.DENIED, TicketState.EXPIRED,
    OrderState.FILLED, OrderState.CANCELLED, OrderState.EXPIRED, OrderState.REJECTED,
    TicketState.UNCERTAIN, OrderState.UNCERTAIN,
])
def test_no_ordinary_exit_from_terminal_or_uncertain(state: TicketState | OrderState) -> None:
    """Invariantes independentes da tabela, inclusive para detectar novas arestas."""
    for event in Event:
        with pytest.raises(InvalidTransition):
            transition(state, event)


def test_cancel_rejection_and_native_expiry_keep_provenance() -> None:
    """Recusar cancelamento mantém saldo; expiração da venue é evento distinto."""
    pending = OrderState.CANCEL_REQUESTED
    assert transition(pending, Event.VENUE_PARTIAL) is pending
    assert transition(pending, Event.VENUE_CANCEL_REJECTED_PARTIAL) is OrderState.PARTIAL
    assert transition(pending, Event.VENUE_CANCEL_REJECTED_LIVE) is OrderState.LIVE
    assert transition(pending, Event.VENUE_EXPIRED) is OrderState.EXPIRED
    with pytest.raises(InvalidTransition):
        transition(pending, Event.EXPIRE)


def test_receipt_rejects_bad_event_without_consuming_sequence() -> None:
    """Payload não finito, tempo ingênuo e prévia genérica não entram na cadeia."""
    receipt = Receipt()
    with pytest.raises(ReceiptError):
        receipt.append(NOW, Event.VENUE_FILL, {"amount": float("nan")})
    with pytest.raises(ReceiptError):
        receipt.append(NOW.replace(tzinfo=None), Event.VENUE_FILL, {})
    with pytest.raises(ReceiptError):
        receipt.append(NOW, Event.PREVIEW, {"digest": "inventado"})
    assert receipt.events == ()
    assert receipt.append(NOW, Event.VENUE_FILL, {"units": 10}).seq == 1


def canonical(value: object) -> str:
    """Representação usada nos esperados do envelope de disco."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@pytest.fixture(scope="module")
def replay_outputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Produz as três sessões oficiais pela interface pública do script."""
    from scripts.derivatives_ticket_replay import main
    from tests.unit.derivatives.ticket.test_session import FIXTURES

    root = tmp_path_factory.mktemp("formato")
    for name in ("calmo", "leilao", "rapido"):
        assert main(["--replay", str(FIXTURES / f"{name}.replay.json"),
                     "--roteiro", str(FIXTURES / f"{name}.roteiro.json"),
                     "--out", str(root / name)]) == 0
    return root


@pytest.mark.parametrize(("name", "ticket", "anchor"), [
    ("calmo", "T1", "1d50bba66aa2db714bf7006da415c39f083bc9e4374ebdbc9b94305b3356236b"),
    ("leilao", "T1", "8592cd742d265332eddf75ea0f0cb9166e53f4db47dbfdd29901e166a43e7bbe"),
    ("rapido", "T1", "9ebc9cd5b584f12b7e67be1ba7ba9a7da94c7a42a531c0d0105409404ba60344"),
    ("rapido", "T2", "fbcaafa8eb7934ed7fe77a9f497b676904c5cc1647d42e0b8f5a77da4df3e2b5"),
])
def test_v2_round_trip_and_truncation(replay_outputs: Path, name: str, ticket: str,
                                      anchor: str) -> None:
    """Prefixo precisa de um evento; a âncora distingue prefixo de recibo completo."""
    folder = replay_outputs / name
    summary = json.loads((folder / "resumo.json").read_bytes())
    assert type(summary["formato"]) is int and summary["formato"] == 1
    lines = (folder / f"recibo_{ticket}.jsonl").read_text().splitlines(keepends=True)
    events = wire.load_rows(iter(lines), expected_head=anchor)
    assert isinstance(events, tuple) and len(events) == summary["boletas"][ticket]["recibo_eventos"]
    assert events[-1].hash == anchor
    assert events[0].read_preview().digest == json.loads(events[0].payload)["digest"]
    with pytest.raises(ReceiptError, match="recibo vazio, adulterado ou incompleto"):
        wire.load_rows(lines[:-1], expected_head=anchor)
    if len(events) == 1:
        with pytest.raises(ReceiptError, match="recibo vazio, adulterado ou incompleto"):
            wire.load_rows(lines[:-1])
    else:
        assert wire.load_rows(lines[:-1]) == events[:-1]


@pytest.mark.parametrize("version", [2, 0, "1", True, 1.0, None])
def test_v3_unknown_version_in_any_row(replay_outputs: Path, version: object) -> None:
    """Cada mensagem carrega a própria versão, de tipo inteiro estrito."""
    lines = (replay_outputs / "calmo/recibo_T1.jsonl").read_text().splitlines()
    for index in (0, 1):
        changed = lines.copy()
        changed[index] = canonical(json.loads(lines[index]) | {"formato": version})
        with pytest.raises(ReceiptError, match="formato de recibo desconhecido"):
            wire.load_rows(changed)


@pytest.mark.parametrize("change", [
    "missing", "extra", "trailing", "space", "array", "broken", "blank", "duplicate", "kind",
    "timestamp", "seq_text", "seq_bool", "payload_type", "timestamp_alias",
    "hash_type", "link_type",
])
def test_v3_invalid_row(replay_outputs: Path, change: str) -> None:
    """O leitor distingue erro de representação de adulteração da cadeia."""
    lines = (replay_outputs / "calmo/recibo_T1.jsonl").read_text().splitlines()
    row = json.loads(lines[1])
    missing = row.copy()
    missing.pop("formato", None)
    invalid = {
        "missing": canonical(missing), "extra": canonical(row | {"extra": 1}),
        "trailing": lines[1] + " ", "space": lines[1].replace('"formato":', '"formato": '),
        "array": "[]", "broken": "{", "blank": "",
        "duplicate": lines[1].replace('"formato":1', '"formato":1,"formato":1'),
        "kind": canonical(row | {"kind": "nope"}), "timestamp": canonical(row | {"ts": "ontem"}),
        "seq_text": canonical(row | {"seq": "2"}), "seq_bool": canonical(row | {"seq": True}),
        "payload_type": canonical(row | {"payload": 3}),
        "hash_type": canonical(row | {"hash": 0}),
        "link_type": canonical(row | {"prev_hash": None}),
        "timestamp_alias": canonical(row | {"ts": row["ts"].replace("+00:00", "Z")}),
    }
    lines[1] = invalid[change]
    with pytest.raises(ReceiptError, match="linha de recibo inválida"):
        wire.load_rows(lines)


@pytest.mark.parametrize("change", [
    "seq", "ts", "kind", "link", "payload", "empty", "swap", "naive", "forged_preview",
])
def test_v3_chain_or_preview_mismatch(replay_outputs: Path, change: str) -> None:
    """Inclui prévia com conteúdo editado e hash externo da linha recalculado."""
    lines = (replay_outputs / "calmo/recibo_T1.jsonl").read_text().splitlines()
    first, second = map(json.loads, lines[:2])
    if change == "empty":
        lines = []
    elif change == "swap":
        lines[:2] = reversed(lines[:2])
    elif change == "naive":
        lines[0] = canonical(first | {"ts": first["ts"].removesuffix("+00:00")})
    elif change == "forged_preview":
        payload = json.loads(first["payload"])
        payload["preview"]["quote_snapshot_id"] += "-alterada"
        first["payload"] = canonical(payload)
        body = [first[k] for k in ("seq", "ts", "kind", "payload", "prev_hash")]
        first["hash"] = sha256(canonical(body).encode()).hexdigest()
        lines = [canonical(first)]
    else:
        altered = {"seq": 5, "ts": "2026-11-23T14:00:03+00:00", "kind": "stop",
                   "link": "0" * 64, "payload": second["payload"].replace("T1", "T2")}
        key = "prev_hash" if change == "link" else change
        assert second[key] != altered[change]
        lines[1] = canonical(second | {key: altered[change]})
    with pytest.raises(ReceiptError, match="recibo vazio, adulterado ou incompleto"):
        wire.load_rows(lines)


def test_v4_only_version_added_to_canonical_event(replay_outputs: Path) -> None:
    """Cada evento conserva o envelope anterior ao retirar a chave de versão."""
    lines = (replay_outputs / "rapido/recibo_T1.jsonl").read_text().splitlines()
    events = wire.load_rows(lines)
    for line, event in zip(lines, events, strict=True):
        previous = {"seq": event.seq, "ts": event.ts.isoformat(), "kind": event.kind.value,
                    "payload": event.payload.decode(), "prev_hash": event.prev_hash,
                    "hash": event.hash}
        assert line.startswith('{"formato":1,"hash":"')
        assert line.removeprefix('{"formato":1,') == canonical(previous)[1:]


def test_v2_external_fact_uses_same_format_and_anchor(tmp_path: Path) -> None:
    """O fato de exercício também pode ser lido diretamente do arquivo gravado."""
    from tests.unit.derivatives.test_ticket_replay_script import external_scenario, run_external

    assert run_external(external_scenario(), tmp_path) == 0
    out = tmp_path / "out"
    summary = json.loads((out / "resumo.json").read_bytes())
    with (out / "fatos_externos.jsonl").open(encoding="utf-8") as stream:
        event, = wire.load_rows(stream, expected_head=summary["fatos_externos"]["hash"])
    assert event.kind is Event.EXTERNAL and json.loads(event.payload)["kind"] == "exercise"
