"""Oráculos literais de três sessões D0 e da fronteira de arquivos."""
import json
import socket
from datetime import datetime
from pathlib import Path

import pytest

from backend.derivatives.ticket.receipt import Receipt, ReceiptEvent
from backend.derivatives.ticket.session import ReplaySession
from backend.derivatives.ticket.state import Event
from loguru import logger

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
         "1d50bba66aa2db714bf7006da415c39f083bc9e4374ebdbc9b94305b3356236b", CALMO)], []),
    "leilao": (11, [
        ("T1", "STOPPED", [("A", "EXPIRED", 4), ("B", "FILLED", 3)], 12,
         "8592cd742d265332eddf75ea0f0cb9166e53f4db47dbfdd29901e166a43e7bbe", LEILAO)],
        [(2, "T1", "EngineRefusal")]),
    "rapido": (8, [
        ("T1", "STOPPED", [("B", "CANCELLED", 4), ("A", "FILLED", 4)], 15,
         "9ebc9cd5b584f12b7e67be1ba7ba9a7da94c7a42a531c0d0105409404ba60344", RAPIDO),
        ("T2", "DRAFT", [], 1,
         "fbcaafa8eb7934ed7fe77a9f497b676904c5cc1647d42e0b8f5a77da4df3e2b5", "preview")],
        [(4, "T2", "EngineRefusal"), (6, "T2", "SequenceRefusal"), (9, "T2", "EngineRefusal")]),
}


def progress_row(symbol: str, side: str, executed: int, live: int,
                 average: str | None) -> dict[str, object]:
    """Linha literal das sessões oficiais; todas as pernas têm dez unidades assinadas."""
    return {"serie": symbol, "lado": side, "assinado": 10, "executado": executed,
            "vivo": live, "preco_medio": average}


OPENING = [progress_row("A", "BUY", 0, 0, None), progress_row("B", "SELL", 0, 0, None)]
CLOSING = [progress_row("A", "SELL", 0, 0, None), progress_row("B", "BUY", 0, 0, None)]
PROGRESS = {
    ("calmo", "T1"): ("Concluída", [progress_row("A", "BUY", 10, 0, "1.0000"),
                                    progress_row("B", "SELL", 10, 0, "1.5000")]),
    ("leilao", "T1"): ("Parada · montagem parcial", [progress_row("A", "BUY", 4, 0, "1.0000"),
                                                     progress_row("B", "SELL", 3, 0, "1.5000")]),
    ("rapido", "T1"): ("Parada · desmontagem parcial", [progress_row("A", "SELL", 4, 0, "1.0000"),
                                                       progress_row("B", "BUY", 4, 0, "1.5000")]),
    ("rapido", "T2"): ("Proposta", CLOSING),
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
    # B4: oráculos do resumo e das linhas que ganham gross ou protection.
    totals = {"calmo": ("25.00", "25.00"), "leilao": ("8.50", "8.50"),
              "rapido": ("10.00", "10.00")}
    gross_rows = {
        "calmo": {8: ("10.00", "25.00"), 11: ("25.00", "25.00"), 12: ("25.00", "25.00")},
        "leilao": {5: ("3.00", "25.00"), 7: ("7.50", "25.00"), 9: ("8.50", "14.50"),
                   12: ("8.50", "8.50")},
        "rapido": {7: ("6.00", "25.00"), 12: ("10.00", "25.00"), 15: ("10.00", "10.00")},
    }
    protection = {"calmo": {10: "A"}, "leilao": {6: "A"}, "rapido": {11: "B"}}
    boletas = {}
    for ticket, state, orders, n, head, sequence in tickets:
        ex, proj = totals[case] if ticket == "T1" else ("0.00", "25.00")
        label, legs = PROGRESS[case, ticket]
        boletas[ticket] = {"conta": "sim", "estado": state, "pausada": False,
                           "rotulo": label, "pernas": legs,
                           "bruto": {"assinado": "25.00", "executado": ex, "projetado": proj},
                           "ordens": {f"{ticket}:{sym}:1": {"estado": st, "executado": qty}
                                      for sym, st, qty in orders},
                           "recibo_eventos": n, "recibo_hash": head}
        rows = a[f"recibo_{ticket}.jsonl"].splitlines(keepends=True)
        events = []
        for line in rows:
            row = json.loads(line)
            assert set(row) == {"seq", "ts", "kind", "payload", "prev_hash", "hash", "formato"}
            assert type(row["formato"]) is int and row["formato"] == 1
            assert line == (json.dumps(row, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")) + "\n").encode()
            events.append(ReceiptEvent(row["seq"], datetime.fromisoformat(row["ts"]),
                                       Event(row["kind"]), row["payload"].encode(),
                                       row["prev_hash"], row["hash"]))
        payloads = {r.seq: json.loads(r.payload) for r in events}
        assert {n: d["gross"] for n, d in payloads.items() if "gross" in d} == {
            n: {"signed": "25.00", "executed": ex, "projected": proj}
            for n, (ex, proj) in (gross_rows[case] if ticket == "T1" else {}).items()}
        assert {n: d["protection"] for n, d in payloads.items() if "protection" in d} == (
            protection[case] if ticket == "T1" else {})
        assert [r.kind.value for r in events] == sequence.split()
        assert Receipt().verify(events, expected_head=head)
    expected = {"formato": 1, "aviso": AVISO, "eventos": count, "contas_bloqueadas": [],
                "boletas": boletas,
                "recusas": [{"passo": n, "acao": "confirm", "boleta": t, "erro": err}
                            for n, t, err in refusals]}
    assert a["resumo.json"] == (json.dumps(expected, ensure_ascii=False, sort_keys=True,
                                           indent=2) + "\n").encode()


@pytest.mark.parametrize("case", ["N3", "N4", "N5", "N6", "N7", "N8", "N9", "N10",
                                  "ttl", "account", "duplicada", "fuso", "chave", "decimal"])
def test_invalid_input_publishes_nothing(case: str, tmp_path: Path) -> None:
    """V11: após qualquer erro, o pai contém somente as duas entradas."""
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
    assert main(args(tape_path, script_path, out)) == 2
    assert set(tmp_path.iterdir()) == {tape_path, script_path}


def _official(case: str, out: Path) -> list[str]:
    return args(FIXTURES / f"{case}.replay.json", FIXTURES / f"{case}.roteiro.json", out)


@pytest.mark.parametrize("case", ["V1", "V2", "V6", "V7", "V13"])
def test_invalid_addendum_cases(case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Uma recusa do roteiro ou da fita deixa o destino inexistente."""
    raw = (FIXTURES / "calmo.roteiro.json").read_text()
    plan = json.loads(raw)
    tape = json.loads((FIXTURES / "calmo.replay.json").read_bytes())
    steps = plan["steps"]
    if case == "V1":
        steps.insert(1, dict(steps[0], ticket="t1"))
    elif case == "V2":
        for event in tape["events"]:
            event["seq"] -= 1
        plan["steps"] = [dict(steps[0], after_seq=0, at="2026-11-23T14:00:00Z")]
    elif case == "V6":
        key = '"decision_ttl_s":60,'
        assert raw.count(key) == 1
        raw = raw.replace(key, key * 2)
    elif case == "V7":
        steps[0]["after_seq"] = -1
    else:
        steps[0]["account"] = "ausente"
    script, replay, out = (tmp_path / p for p in ("script", "replay", "out"))
    if case in {"V6", "V7", "V13"}:
        def unexpected_advance(*args: object) -> None:
            pytest.fail("roteiro inválido chegou à execução de um passo")

        monkeypatch.setattr(ReplaySession, "advance_to", unexpected_advance)
    script.write_text(raw if case == "V6" else json.dumps(plan))
    replay.write_text(json.dumps(tape))
    assert main(args(replay, script, out)) == 2
    assert set(tmp_path.iterdir()) == {script, replay}


@pytest.mark.parametrize("case", ["V3", "V4", "V5"])
def test_session_cut_at_hand_verified_step(case: str, tmp_path: Path) -> None:
    """Verifica estados intermediários, recusas e âncoras independentes."""
    name = "rapido" if case == "V4" else "calmo"
    plan = json.loads((FIXTURES / f"{name}.roteiro.json").read_bytes())
    if case == "V3":
        op = dict(plan["steps"][0], after_seq=0, at="2026-11-23T13:59:59Z")
        plan["steps"] = [op, {"do": "confirm", "after_seq": 0, "ticket": "T1", "at": op["at"]}]
        expected = [("T1", "DRAFT", {}, "preview",
                     "474a8476f8851b9ee8314a7060198405a5413fef1258ef52768a20cf8995aabc")]
        refused = [(2, "T1")]
    elif case == "V4":
        plan["steps"] = plan["steps"][:4]
        expected = [
            ("T1", "UNCERTAIN", {"T1:B:1": {"estado": "UNCERTAIN", "executado": 4}},
             "preview confirm start uncertain uncertain",
             "6bf3c975f168427df88334f84ee736801339f7403e5ded0f408f9afd5fcf9ead"),
            ("T2", "DRAFT", {}, "preview",
             "fbcaafa8eb7934ed7fe77a9f497b676904c5cc1647d42e0b8f5a77da4df3e2b5")]
        refused = [(4, "T2")]
    else:
        plan["steps"] = plan["steps"][:4]
        expected = [("T1", "STOPPED", {"T1:A:1": {"estado": "FILLED", "executado": 10}},
                     "preview arm trigger confirm start venue_live pause venue_fill stop",
                     "9cb640c966b1cb040a61ac0bdb8665fe890784a14773424bd01b8ce95af48f99")]
        refused = []
    script, out = tmp_path / "script", tmp_path / "out"
    script.write_text(json.dumps(plan))
    assert main(args(FIXTURES / f"{name}.replay.json", script, out)) == 0
    report = json.loads((out / "resumo.json").read_bytes())
    assert report["eventos"] == (8 if case == "V4" else 9)
    assert report["contas_bloqueadas"] == (["sim"] if case == "V4" else [])
    assert report["recusas"] == [{"passo": n, "acao": "confirm", "boleta": t,
                                  "erro": "EngineRefusal"} for n, t in refused]
    assert set(report["boletas"]) == {row[0] for row in expected}
    for ticket, state, orders, sequence, head in expected:
        # B5: o poll em V4 já mostra quatro, mas o motor ainda aguarda a conciliação.
        ex, proj = ("10.00", "10.00") if case == "V5" else ("0.00", "25.00")
        kinds = sequence.split()
        progress = {
            ("V3", "T1"): ("Proposta", OPENING),
            ("V4", "T1"): ("Boleta em estado incerto",
                           [CLOSING[0], progress_row("B", "BUY", 0, 10, None)]),
            ("V4", "T2"): ("Proposta", CLOSING),
            ("V5", "T1"): ("Parada · montagem parcial",
                           [progress_row("A", "BUY", 10, 0, "1.0000"), OPENING[1]]),
        }
        label, legs = progress[case, ticket]
        assert report["boletas"][ticket] == {
            "rotulo": label, "pernas": legs,
            "conta": "sim", "estado": state, "ordens": orders, "pausada": case == "V5",
            "bruto": {"assinado": "25.00", "executado": ex, "projetado": proj},
            "recibo_eventos": len(kinds), "recibo_hash": head}
        rows = [json.loads(line) for line in (out / f"recibo_{ticket}.jsonl").read_bytes()
                .splitlines()]
        assert [r["kind"] for r in rows] == kinds and rows[-1]["hash"] == head


def test_v8_previous_output_is_preserved(tmp_path: Path) -> None:
    """Reutilizar destino preserva cada byte da primeira sessão."""
    out = tmp_path / "out"
    assert main(_official("calmo", out)) == 0
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    assert main(_official("leilao", out)) == 2
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before


@pytest.mark.parametrize("kind", ["directory", "file", "dangling-link"])
def test_v9_existing_output_is_refused_before_reading(kind: str, tmp_path: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """Até diretório vazio e link quebrado têm identidade que deve ser preservada."""
    out = tmp_path / "out"
    if kind == "directory":
        out.mkdir()
    elif kind == "file":
        out.write_bytes(b"anterior")
    else:
        out.symlink_to(tmp_path / "missing")

    def unexpected(*args: object) -> None:
        pytest.fail("entrada lida antes de recusar destino")

    monkeypatch.setattr(Path, "read_bytes", unexpected)
    assert main(_official("calmo", out)) == 2
    assert list(tmp_path.iterdir()) == [out]
    if kind == "directory":
        assert not list(out.iterdir())
    elif kind == "file":
        assert out.read_text() == "anterior"
    else:
        assert out.readlink() == tmp_path / "missing"


def test_v10_publish_whole_directory_under_new_parents(tmp_path: Path) -> None:
    """O resultado publicado não deixa resíduos nos pais novos."""
    out = tmp_path / "a/b/c"
    assert main(_official("calmo", out)) == 0
    assert list(out.parent.iterdir()) == [out]
    assert {p.name for p in out.iterdir()} == {"resumo.json", "recibo_T1.jsonl"}


@pytest.mark.parametrize("fault", [RuntimeError, OSError, OverflowError])
def test_v12_unexpected_open_fault_propagates(fault: type[Exception], tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """Somente erros de domínio de abertura viram recusa de entrada."""
    def broken(*args: object) -> None:
        raise fault("falha interna")

    monkeypatch.setattr(ReplaySession, "open", broken)
    with pytest.raises(fault, match="falha interna"):
        main(_official("calmo", tmp_path / "out"))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("fault", ["write", "destination-appears"])
def test_publication_fault_leaves_no_partial_receipts(fault: str, tmp_path: Path,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    """Uma falha tardia remove o estágio e preserva um destino criado por terceiro."""
    out = tmp_path / "out"
    original = Path.write_text

    def interrupt(path: Path, data: str, **kwargs: object) -> int:
        assert path.name == "resumo.json" and not out.exists()
        assert (path.parent / "recibo_T1.jsonl").is_file()
        if fault == "write":
            raise OSError("falha de escrita")
        out.mkdir()
        return original(path, data, **kwargs)

    monkeypatch.setattr(Path, "write_text", interrupt)
    assert main(_official("calmo", out)) == 2
    if fault == "write":
        assert not list(tmp_path.iterdir())
    else:
        assert list(tmp_path.iterdir()) == [out] and not list(out.iterdir())


@pytest.mark.parametrize("path", [
    "a/../a", "A/../a", "intermediario/../resultado", "link/../resultado",
])
def test_parent_creation_with_dotdot_preserves_destination(path: str, tmp_path: Path) -> None:
    """O nome solicitado permanece utilizável e '..' segue os links do sistema de arquivos."""
    if path.startswith("link/"):
        (tmp_path / "real/sub").mkdir(parents=True)
        (tmp_path / "link").symlink_to(tmp_path / "real/sub", target_is_directory=True)
    out = tmp_path / path
    assert main(_official("calmo", out)) == 0
    assert {p.name for p in out.iterdir()} == {"resumo.json", "recibo_T1.jsonl"}
    if path.startswith("link/"):
        assert (tmp_path / "real/resultado").samefile(out)
        assert not (tmp_path / "resultado").exists()


def test_destination_cannot_be_its_own_required_subdirectory(tmp_path: Path) -> None:
    """A pasta final não pode conter um ancestral extra para tornar o caminho navegável."""
    out = tmp_path / "a/sub/../../a"
    assert main(_official("calmo", out)) == 2
    assert not (tmp_path / "a").exists()


def test_unusable_output_parent_is_a_cli_refusal(tmp_path: Path) -> None:
    """Um componente longo demais deve recusar a saída sem criar resíduos."""
    out = tmp_path / ("x" * 256) / "resultado"
    assert main(_official("calmo", out)) == 2
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(("case", "lines"), [
    ("calmo", ["T1: Concluída (COMPLETED)"]),
    ("leilao", ["T1: Parada · montagem parcial (STOPPED)"]),
    ("rapido", ["T1: Parada · desmontagem parcial (STOPPED)", "T2: Proposta (DRAFT)"]),
])
def test_l4_summary_log_names_ticket_state(case: str, lines: list[str], tmp_path: Path) -> None:
    """O log exibe a descrição portuguesa junto do código estável."""
    messages: list[str] = []
    sink = logger.add(lambda msg: messages.append(msg.record["message"]), format="{message}")
    try:
        assert main(_official(case, tmp_path / "out")) == 0
    finally:
        logger.remove(sink)
    assert messages == [AVISO, *lines]


def test_h3a_missing_parent_followed_by_dotdot(tmp_path: Path) -> None:
    """A recusa do destino final preserva o pai vazio."""
    assert main(_official("calmo", tmp_path / "x/..")) == 2
    assert not list(tmp_path.iterdir())


def test_h3b_broken_parent_link(tmp_path: Path) -> None:
    """A recusa mantém só o link quebrado original."""
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "missing", target_is_directory=True)
    assert main(_official("calmo", link / "novo")) == 2
    assert list(tmp_path.iterdir()) == [link] and link.is_symlink()


def test_h3c_unrepresentable_decision_lifetime(tmp_path: Path) -> None:
    """A validade irrepresentável interrompe o roteiro antes de publicar."""
    script = tmp_path / "roteiro"
    data = json.loads((FIXTURES / "calmo.roteiro.json").read_bytes())
    data["decision_ttl_s"] = 10**18
    script.write_text(json.dumps(data))
    assert main(args(FIXTURES / "calmo.replay.json", script, tmp_path / "out")) == 2
    assert list(tmp_path.iterdir()) == [script]


def external_scenario() -> dict:
    """Compõe o F8 em memória a partir dos modelos do roteiro calmo."""
    plan = json.loads((FIXTURES / "calmo.roteiro.json").read_bytes())
    pos = plan["positions"][0]
    for row in pos["holdings"]:
        row["balance"] = {"A": 10, "B": -10}[row["symbol"]]
    plan["positions"].append(dict(pos, account="outra"))
    opening = plan["steps"][0]
    confirm = dict(after_seq=2, at=opening["at"], do="confirm", ticket="T1")
    fact = dict(after_seq=4, at="2026-11-23T14:00:07Z", do="external", account="sim",
                symbol="B", fact="f1", kind="exercise", quantity=4)
    later = dict(after_seq=4, at="2026-11-23T14:00:08Z", ticket="T4")
    plan["steps"] = [opening, dict(opening, ticket="T3", account="outra"), confirm,
                     dict(confirm, ticket="T3"), fact, opening | later, confirm | later]
    return plan


def run_external(plan: dict, tmp_path: Path) -> int:
    """Executa pela entrada pública que publica os JSON e JSONL."""
    path = tmp_path / "roteiro.json"
    path.write_text(json.dumps(plan))
    return main(args(FIXTURES / "calmo.replay.json", path, tmp_path / "out"))


def test_f8_script_publishes_account_fact_and_refuses_late_confirmation(tmp_path: Path) -> None:
    assert run_external(external_scenario(), tmp_path) == 0
    out = tmp_path / "out"
    assert {p.name for p in out.iterdir()} == {
        "fatos_externos.jsonl", "recibo_T1.jsonl", "recibo_T3.jsonl", "recibo_T4.jsonl",
        "resumo.json",
    }
    line, = (out / "fatos_externos.jsonl").read_bytes().splitlines()
    row = json.loads(line)
    assert (row["seq"], row["kind"], row["ts"]) == (1, "external", "2026-11-23T14:00:07+00:00")
    assert json.loads(row["payload"]) == {
        "account": "sim", "symbol": "B", "fact": "f1", "kind": "exercise", "quantity": 4,
    }
    event = ReceiptEvent(row["seq"], datetime.fromisoformat(row["ts"]), Event.EXTERNAL,
                         row["payload"].encode(), row["prev_hash"], row["hash"])
    assert Receipt().verify([event])
    summary = json.loads((out / "resumo.json").read_bytes())
    assert summary["fatos_externos"] == {"eventos": 1, "hash": row["hash"]}
    assert summary["recusas"] == [
        {"passo": 7, "acao": "confirm", "boleta": "T4", "erro": "SequenceRefusal"},
    ]
    tickets = summary["boletas"]
    assert [tickets[t]["estado"] for t in ("T1", "T3", "T4")] == ["STOPPED", "COMPLETED", "DRAFT"]
    assert tickets["T1"]["bruto"] == {
        "assinado": "25.00", "executado": "10.00", "projetado": "10.00",
    }


@pytest.mark.parametrize(("field", "value"), [
    ("account", "ausente"), ("symbol", "Z"), ("symbol", "B:1"), ("kind", "assignment"),
    ("quantity", 0), ("quantity", "4"), ("quantity", 1.5), ("quantity", True),
    ("fact", "f 1"), ("ticket", "T1"),
])
def test_f9_invalid_external_script_never_publishes(tmp_path: Path, field: str, value: object
                                                    ) -> None:
    plan = external_scenario()
    plan["steps"][4][field] = value
    assert run_external(plan, tmp_path) == 2
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("conflict", [True, False])
def test_f10_duplicate_external_script(tmp_path: Path, conflict: bool) -> None:
    plan = external_scenario()
    fact = plan["steps"][4]
    plan["steps"].insert(5, dict(fact, quantity=5 if conflict else 4))
    code = run_external(plan, tmp_path)
    if conflict:
        assert code == 2 and not (tmp_path / "out").exists()
    else:
        assert code == 0
        assert len((tmp_path / "out/fatos_externos.jsonl").read_bytes().splitlines()) == 1


def test_f11_official_session_omits_external_artifacts(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main(_official("calmo", out)) == 0
    assert {p.name for p in out.iterdir()} == {"recibo_T1.jsonl", "resumo.json"}
    assert "fatos_externos" not in json.loads((out / "resumo.json").read_bytes())


def test_external_only_script_has_a_verifiable_session_record(tmp_path: Path) -> None:
    plan = external_scenario()
    plan["steps"] = [plan["steps"][4]]
    assert run_external(plan, tmp_path) == 0
    out = tmp_path / "out"
    assert {p.name for p in out.iterdir()} == {"fatos_externos.jsonl", "resumo.json"}
    summary = json.loads((out / "resumo.json").read_bytes())
    assert summary["boletas"] == {} and summary["fatos_externos"]["eventos"] == 1


def test_external_script_checks_instrument_in_its_own_photo(tmp_path: Path) -> None:
    plan = external_scenario()
    other = plan["positions"][1]
    other["holdings"] = [dict(other["holdings"][0], symbol="X")]
    other["pairs"] = []
    plan["steps"] = [dict(plan["steps"][4], symbol="X")]
    assert run_external(plan, tmp_path) == 2 and not (tmp_path / "out").exists()


@pytest.mark.parametrize("second", ["05", "11"])
def test_external_step_obeys_tape_time_window(tmp_path: Path, second: str) -> None:
    plan = external_scenario()
    plan["steps"] = [dict(plan["steps"][4], at=f"2026-11-23T14:00:{second}Z")]
    assert run_external(plan, tmp_path) == 2 and not (tmp_path / "out").exists()
