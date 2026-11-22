"""Oráculos literais de três sessões D0 e da fronteira de arquivos."""
import json
import socket
from datetime import datetime
from pathlib import Path

import pytest

from backend.derivatives.ticket.receipt import Receipt, ReceiptEvent
from backend.derivatives.ticket.state import Event
from scripts.derivatives_ticket_replay import main
from tests.unit.derivatives.ticket.test_session import FIXTURES

AVISO = "SIMULADO — resultado em papel é teto otimista, não previsão."
CALMO = "preview arm trigger confirm start venue_live pause venue_fill resume venue_live " \
        "venue_fill complete"
LEILAO = "preview confirm start venue_live venue_partial venue_live venue_fill request_cancel " \
         "venue_partial venue_cancel_rejected_partial venue_expired stop"
RAPIDO = "preview confirm start uncertain uncertain reconcile venue_partial reconcile pause " \
         "resume venue_live venue_fill request_cancel venue_cancelled stop"
# Fita, eventos e tuplas (boleta, estado, ordens, contagem, âncora e sequência literal).
EXPECTED = {
    "calmo": (9, [
        ("T1", "COMPLETED", [("A", "FILLED", 10), ("B", "FILLED", 10)], 12,
         "050354936eae64e316000a2f1570845a489dfe87f87f2dc5e70a4ceb742642f7", CALMO)], []),
    "leilao": (11, [
        ("T1", "STOPPED", [("A", "EXPIRED", 4), ("B", "FILLED", 3)], 12,
         "96e50b071fa291d895b4a37a6ad56b460ae1fae33774a4b59290c2f79dc5bd52", LEILAO)],
        [(2, "T1", "EngineRefusal")]),
    "rapido": (8, [
        ("T1", "STOPPED", [("B", "CANCELLED", 4), ("A", "FILLED", 4)], 15,
         "a81c1cbea973dfd1db5b22b6e6a53ddb0242116442c1387f0cae55d545091cb6", RAPIDO),
        ("T2", "DRAFT", [], 1,
         "fbcaafa8eb7934ed7fe77a9f497b676904c5cc1647d42e0b8f5a77da4df3e2b5", "preview")],
        [(4, "T2", "EngineRefusal"), (6, "T2", "SequenceRefusal"), (9, "T2", "EngineRefusal")]),
}


def args(tape: Path, script: Path, out: Path) -> list[str]:
    """Monta a mesma interface usada pelo comando do operador."""
    return ["--replay", str(tape), "--roteiro", str(script), "--out", str(out)]


@pytest.mark.parametrize("case", EXPECTED)
def test_complete_replay(case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Duas execuções sem socket devem reproduzir todos os bytes e âncoras do cartão."""
    def no_socket(*args: object, **kwargs: object) -> None:
        raise AssertionError("o replay tentou criar um socket")

    monkeypatch.setattr(socket, "socket", no_socket)
    count, tickets, refusals = EXPECTED[case]
    tape, script = (FIXTURES / f"{case}.{ext}.json" for ext in ("replay", "roteiro"))
    first, second = tmp_path / "primeira", tmp_path / "segunda"
    for out in (first, second):
        assert main(args(tape, script, out)) == 0
    a = {p.name: p.read_bytes() for p in first.iterdir()}
    assert a == {p.name: p.read_bytes() for p in second.iterdir()}
    assert set(a) == {"resumo.json", *(f"recibo_{row[0]}.jsonl" for row in tickets)}
    boletas = {}
    for ticket, state, orders, n, head, sequence in tickets:
        boletas[ticket] = {"conta": "sim", "estado": state, "pausada": False,
                           "ordens": {f"{ticket}:{sym}:1": {"estado": st, "executado": qty}
                                      for sym, st, qty in orders},
                           "recibo_eventos": n, "recibo_hash": head}
        rows = a[f"recibo_{ticket}.jsonl"].splitlines(keepends=True)
        events = []
        for line in rows:
            row = json.loads(line)
            assert set(row) == {"seq", "ts", "kind", "payload", "prev_hash", "hash"}
            assert line == (json.dumps(row, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")) + "\n").encode()
            events.append(ReceiptEvent(row["seq"], datetime.fromisoformat(row["ts"]),
                                       Event(row["kind"]), row["payload"].encode(),
                                       row["prev_hash"], row["hash"]))
        assert [r.kind.value for r in events] == sequence.split()
        assert Receipt().verify(events, expected_head=head)
    expected = {"aviso": AVISO, "eventos": count, "contas_bloqueadas": [], "boletas": boletas,
                "recusas": [{"passo": n, "acao": "confirm", "boleta": t, "erro": err}
                            for n, t, err in refusals]}
    assert a["resumo.json"] == (json.dumps(expected, ensure_ascii=False, sort_keys=True,
                                           indent=2) + "\n").encode()


@pytest.mark.parametrize("case", ["N3", "N4", "N5", "N6", "N7", "N8", "N9", "N10",
                                  "ttl", "account", "duplicada", "fuso", "chave", "decimal"])
def test_invalid_input_publishes_nothing(case: str, tmp_path: Path) -> None:
    """Erros antes ou depois de passos válidos preservam inclusive saídas anteriores."""
    session = "leilao" if case == "N3" else "calmo"
    tape = json.loads((FIXTURES / f"{session}.replay.json").read_bytes())
    script = json.loads((FIXTURES / f"{session}.roteiro.json").read_bytes())
    steps = script["steps"]
    if case == "N3":
        del steps[3]
    elif case in ("N4", "N5"):
        steps[2]["at"] = "2026-11-23T14:" + ("00:10Z" if case == "N4" else "00:14Z")
    elif case == "N6":
        steps[2]["ticket"] = "T9"
    elif case == "N7":
        steps[3]["after_seq"] = 2
    elif case == "N8":
        steps[1]["extra"] = True
    elif case == "N9":
        tape["events"][1]["seq"] = tape["events"][0]["seq"]
    elif case == "N10":
        steps[0]["draft"]["legs"][0]["symbol"] = "X:A"
    elif case == "ttl":
        script["decision_ttl_s"] = True
    elif case == "account":
        steps[0]["account"] = "ausente"
    elif case == "duplicada":
        script["positions"] *= 2
    elif case == "fuso":
        steps[0]["at"] = "2026-11-23T14:00:02"
    elif case == "chave":
        del steps[1]["spec"]
    else:
        steps[0]["draft"]["net_limit"] = -5.0
    tape_path, script_path, out = (tmp_path / x for x in ("fita", "roteiro", "out"))
    tape_path.write_text(json.dumps(tape))
    script_path.write_text(json.dumps(script))
    out.mkdir()
    prior = out / "resumo.json"
    prior.write_bytes(b"anterior")
    assert main(args(tape_path, script_path, out)) == 2
    assert list(out.iterdir()) == [prior] and prior.read_bytes() == b"anterior"
