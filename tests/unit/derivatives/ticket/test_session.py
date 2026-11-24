"""Contrato público da sessão sintética de replay."""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from backend.derivatives.ticket import session as session_module
from backend.derivatives.ticket.engine import EngineRefusal
from backend.derivatives.ticket.gate import Action, DecisionRefusal, issue
from backend.derivatives.ticket.models import TicketDraft
from backend.derivatives.ticket.replay import load_replay
from backend.derivatives.ticket.sequencing import Position, SequenceRefusal
from backend.derivatives.ticket.session import ReplaySession, SessionRefusal
from backend.derivatives.ticket.state import OrderState, TicketState
from config.ticket_sim_config_model import load_ticket_sim_config

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures/derivatives/synthetic/ticket/sessions"


def session_data() -> tuple[ReplaySession, Position, TicketDraft, datetime]:
    """Abre a fita calma e lê os modelos reais no modo JSON estrito."""
    plan = json.loads((FIXTURES / "calmo.roteiro.json").read_bytes())
    op = plan["steps"][0]
    return (ReplaySession(load_replay(FIXTURES / "calmo.replay.json"),
                          config=load_ticket_sim_config()),
            Position.model_validate_json(json.dumps(plan["positions"][0])),
            TicketDraft.model_validate_json(json.dumps(op["draft"])),
            datetime.fromisoformat(op["at"]))


def test_n1_ticket_id_unique_across_accounts() -> None:
    """A segunda abertura não toma a identidade nem o recibo da primeira."""
    s, pos, draft, now = session_data()
    first = s.open("T1", pos, draft, now)
    receipt = s.receipt("T1")
    with pytest.raises(SessionRefusal):
        s.open("T1", pos.model_copy(update={"account": "sim2"}), draft, now)
    assert s.engine("T1") is first and s.receipt("T1") is receipt


def test_failed_open_does_not_register_ticket() -> None:
    """Uma proposta recusada deixa o mesmo ID disponível para um plano válido."""
    s, pos, draft, now = session_data()
    bad = draft.legs[0].model_copy(update={"symbol": "X:A"})
    with pytest.raises(EngineRefusal):
        s.open("T1", pos, draft.model_copy(update={"legs": (bad, *draft.legs[1:])}), now)
    assert s.summary()["boletas"] == {}
    assert s.open("T1", pos, draft, now) is s.engine("T1")


def test_n2_cursor_boundaries_and_idempotent_finish() -> None:
    """Limites temporais são inclusivos e o cursor nunca reaplica um evento."""
    s, _, _, _ = session_data()
    tape = load_replay(FIXTURES / "calmo.replay.json")
    s.check_time(tape.events[0].ts - timedelta(days=2))
    s.advance_to(2)
    with pytest.raises(SessionRefusal):
        s.advance_to(1)
    s.advance_to(2)
    assert s.summary()["eventos"] == 2
    s.check_time(tape.events[1].ts)
    s.check_time(tape.events[2].ts)
    s.finish()
    s.check_time(tape.events[-1].ts + timedelta(days=2))
    s.finish()
    assert s.summary()["eventos"] == 9


def test_incompatible_venue_event_is_session_refusal() -> None:
    """O cancel_rejected da fita exige uma ordem com cancelamento pendente."""
    s = ReplaySession(load_replay(FIXTURES / "leilao.replay.json"),
                      config=load_ticket_sim_config())
    with pytest.raises(SessionRefusal):
        s.finish()


@pytest.mark.parametrize("second", ["t1", "T1"], ids=["U1", "U2"])
def test_open_preserves_first_spelling(second: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A sessão recusa as duas colisões e preserva a consulta por grafia original."""
    s, pos, draft, now = session_data()
    s.advance_to(2)
    first = s.open("T1", pos, draft, now)

    def unexpected_engine(*args: object, **kwargs: object) -> None:
        pytest.fail("construção do motor antes da recusa de identidade duplicada")

    monkeypatch.setattr(session_module, "TicketEngine", unexpected_engine)
    with pytest.raises(SessionRefusal):
        s.open(second, pos, draft, now)
    assert s.engine("T1") is first
    with pytest.raises(KeyError):
        s.engine("t1")


@pytest.mark.parametrize("delta", [1, 2], ids=["U3", "U4"])
def test_only_session_reserves_zero_for_before_first_event(delta: int, tmp_path: Path) -> None:
    """O leitor admite o replay com seq <= 0 e o construtor recusa a ambiguidade."""
    tape = json.loads((FIXTURES / "calmo.replay.json").read_bytes())
    for event in tape["events"]:
        event["seq"] -= delta
    source = tmp_path / "fita"
    source.write_text(json.dumps(tape))
    replay = load_replay(source)
    assert replay.events[0].seq == 1 - delta
    with pytest.raises(SessionRefusal, match="after_seq=0"):
        ReplaySession(replay, config=load_ticket_sim_config())


def test_empty_tape_can_finish() -> None:
    """Uma fita vazia tem zero eventos e nenhuma fronteira temporal."""
    replay = load_replay(FIXTURES / "calmo.replay.json").model_copy(update={"events": ()})
    session = ReplaySession(replay, config=load_ticket_sim_config())
    session.advance_to(0)
    session.finish()
    assert session.summary()["eventos"] == 0


def test_u5_nonce_used_by_first_ticket_is_spent_for_second() -> None:
    """O saldo de decisões pertence à sessão inteira."""
    s, pos, draft, now = session_data()
    s.advance_to(2)
    one = s.open("T1", pos, draft, now)
    two = s.open("T2", pos, draft, now)
    for name, engine in (("T1", one), ("T2", two)):
        decision = issue(Action.EXECUTE, ticket=name, nonce="x", preview=engine.preview,
                         issued_at=now, expires_at=now + timedelta(minutes=1))
        if name == "T1":
            one.confirm(decision, now)
        else:
            with pytest.raises(DecisionRefusal):
                two.confirm(decision, now)
    assert one.state is TicketState.WORKING and one.orders == {"T1:A:1": OrderState.LIVE}
    assert two.state is TicketState.DRAFT and not two.orders
    assert not hasattr(s, "ledger")


def test_u6_naive_time_is_refused_even_without_previous_event() -> None:
    """O tipo da recusa faz parte do contrato."""
    s, _, _, _ = session_data()
    with pytest.raises(SessionRefusal):
        s.check_time(datetime(2026, 11, 23, 14, 0, 2))


def fact_session() -> tuple[ReplaySession, Position, TicketDraft, datetime]:
    """Foto do cartão, com dez A cobrindo dez B vendidas."""
    session, pos, draft, now = session_data()
    raw = pos.model_dump(mode="json")
    for row in raw["holdings"]:
        row["balance"] = {"A": 10, "B": -10}[row["symbol"]]
    session.advance_to(2)
    return session, Position.model_validate_json(json.dumps(raw)), draft, now


def confirm_fact_ticket(s: ReplaySession, name: str, now: datetime) -> None:
    """Confirma com nonce exclusivo da boleta desta sessão."""
    engine = s.engine(name)
    decision = issue(Action.EXECUTE, ticket=name, nonce=name, preview=engine.preview,
                     issued_at=now, expires_at=now + timedelta(minutes=1))
    engine.confirm(decision, now)


def three_fact_tickets() -> tuple[ReplaySession, datetime]:
    """Abre duas boletas em sim e uma em outra, na ordem do cenário F1."""
    s, pos, draft, now = fact_session()
    for name, account in (("T1", "sim"), ("T2", "sim"), ("T3", "outra")):
        s.open(name, pos.model_copy(update={"account": account}), draft, now)
        confirm_fact_ticket(s, name, now)
        assert s.engine(name).orders == {f"{name}:A:1": OrderState.LIVE}
    return s, now


def fact_rows(s: ReplaySession, ticket: str) -> list[dict[str, object]]:
    """Lê os eventos públicos da boleta."""
    return [json.loads(e.payload) for e in s.receipt(ticket).events if e.kind.value == "external"]


def test_f1_external_reaches_both_tickets_in_affected_account() -> None:
    s, now = three_fact_tickets()
    s.advance_to(4)
    stamp = now.replace(second=7)
    s.external("sim", "B", "f1", "exercise", 4, stamp)
    for name in ("T1", "T2"):
        assert fact_rows(s, name) == [{"ticket": name, "fact": "f1", "series": ["B"]}]
    assert fact_rows(s, "T3") == []
    event, = s.facts.events
    assert event.kind.value == "external" and event.ts == stamp
    assert json.loads(event.payload) == {
        "account": "sim", "fact": "f1", "kind": "exercise", "symbol": "B", "quantity": 4,
    }
    assert s.facts.verify()
    s.finish()
    summary = s.summary()
    assert summary["fatos_externos"] == {"eventos": 1, "hash": event.hash}
    assert summary["contas_bloqueadas"] == []
    for name in ("T1", "T2"):
        engine = s.engine(name)
        assert engine.state is TicketState.STOPPED
        assert engine.orders == {f"{name}:A:1": OrderState.FILLED}
        assert summary["boletas"][name]["bruto"] == {
            "assinado": "25.00", "executado": "10.00", "projetado": "10.00",
        }
    assert s.engine("T3").state is TicketState.COMPLETED
    assert s.engine("T3").orders == {"T3:A:1": OrderState.FILLED, "T3:B:1": OrderState.FILLED}
    assert summary["boletas"]["T3"]["bruto"] == {
        "assinado": "25.00", "executado": "25.00", "projetado": "25.00",
    }


def test_f2_external_before_opening_freezes_one_account() -> None:
    s, pos, draft, now = fact_session()
    s.external("sim", "B", "f1", "compliance", -2, now)
    one = s.open("T1", pos, draft, now)
    with pytest.raises(SequenceRefusal, match="série com fato externo; foto nova necessária"):
        confirm_fact_ticket(s, "T1", now)
    assert one.state is TicketState.DRAFT and fact_rows(s, "T1") == []
    assert s.summary()["fatos_externos"] == {"eventos": 1, "hash": s.facts.events[0].hash}
    two = s.open("T2", pos.model_copy(update={"account": "outra"}), draft, now)
    confirm_fact_ticket(s, "T2", now)
    assert two.state is TicketState.WORKING


def test_f3_external_id_is_global_and_time_independent() -> None:
    s, now = three_fact_tickets()
    s.external("sim", "B", "f1", "exercise", 4, now.replace(second=3))
    before = s.facts.events
    s.external("sim", "B", "f1", "exercise", 4, now.replace(second=4))
    for account, symbol, kind, qty in (
        ("sim", "B", "exercise", 5), ("sim", "A", "exercise", 4),
        ("outra", "B", "exercise", 4), ("sim", "B", "compliance", 4),
    ):
        with pytest.raises(SessionRefusal, match="fato repetido com conteúdo diferente"):
            s.external(account, symbol, "f1", kind, qty, now.replace(second=4))
        assert s.facts.events == before and fact_rows(s, "T3") == []
    s.external("sim", "A", "f2", "exercise", -1, now.replace(second=4))
    first, second = s.facts.events
    assert first == before[0] and second.prev_hash == first.hash
    assert json.loads(second.payload)["quantity"] == -1
    assert s.facts.verify(expected_head=second.hash)
    assert s.summary()["fatos_externos"] == {"eventos": 2, "hash": second.hash}
    assert fact_rows(s, "T1") == [{"ticket": "T1", "fact": "f1", "series": ["B"]}]


@pytest.mark.parametrize(("field", "value", "reason"), [
    ("symbol", "B:1", "fora do alfabeto"), ("fact", "f 1", "fora do alfabeto"),
    ("account", "", "conta inválida"), ("account", None, "conta inválida"),
    ("kind", "assignment", "tipo de fato desconhecido"),
    ("quantity", 0, "quantidade do fato inválida"),
    ("quantity", True, "quantidade do fato inválida"),
    ("quantity", 1.0, "quantidade do fato inválida"),
    ("now", datetime(2026, 11, 23, 14, 0, 2), "instante sem fuso"),
])
def test_f4_invalid_external_leaves_no_effect(field: str, value: object, reason: str) -> None:
    s, pos, draft, now = fact_session()
    inputs = dict(account="sim", symbol="B", fact="f1", kind="exercise", quantity=4, now=now)
    inputs[field] = value
    with pytest.raises(SessionRefusal, match=reason):
        s.external(**inputs)
    assert s.facts.events == () and "fatos_externos" not in s.summary()
    e = s.open("T1", pos, draft, now)
    confirm_fact_ticket(s, "T1", now)
    assert e.state is TicketState.WORKING
    s.external("sim", "B", "f1", "exercise", 4, now)
    assert fact_rows(s, "T1") == [{"ticket": "T1", "fact": "f1", "series": ["B"]}]


def test_external_dispatch_observes_receipt_then_freeze_in_opening_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cada aviso observa o novo fato e o livro congelado, inclusive a boleta em rascunho."""
    s, pos, draft, now = fact_session()
    order = []
    for name, account in (("Z", "sim"), ("X", "outra"), ("A", "sim")):
        engine = s.open(name, pos.model_copy(update={"account": account}), draft, now)

        def observed(fact: str, at: datetime, ticket: str = name) -> None:
            assert fact == "f1" and at == now
            assert len(s.facts.events) == 1
            with pytest.raises(SequenceRefusal, match="série com fato externo"):
                confirm_fact_ticket(s, ticket, now)
            order.append(ticket)

        monkeypatch.setattr(engine, "on_external", observed)
    s.external("sim", "B", "f1", "exercise", 4, now)
    s.external("sim", "B", "f1", "exercise", 4, now.replace(second=3))
    assert order == ["Z", "A"]


def test_external_facts_snapshot_cannot_inject_event_or_suppress_freeze() -> None:
    """Modificar a foto consultada não cria fato na sessão nem consome seu ID."""
    from backend.derivatives.ticket.state import Event

    s, pos, draft, now = fact_session()
    forged = s.facts
    forged.append(now, Event.EXTERNAL, {"account": "sim", "symbol": "B", "fact": "f1",
                                        "kind": "exercise", "quantity": 4})
    assert forged.verify() and s.facts.events == () and "fatos_externos" not in s.summary()
    s.external("sim", "B", "f1", "exercise", 4, now)
    observed = s.facts
    observed.append(now, Event.EXTERNAL, {"fact": "f2"})
    assert len(observed.events) == 2 and len(s.facts.events) == 1
    s.open("T1", pos, draft, now)
    with pytest.raises(SequenceRefusal, match="série com fato externo"):
        confirm_fact_ticket(s, "T1", now)


def test_external_accepts_aware_datetime_subclass_in_both_receipts() -> None:
    """Uma subclasse com fuso descreve o mesmo instante no registro e na boleta."""
    class ReplayStamp(datetime):
        """Instante recebido de um consumidor Python do simulador."""

    s, now = three_fact_tickets()
    stamp = ReplayStamp.fromisoformat("2026-11-23T15:00:03.123456+01:00")
    s.external("sim", "B", "f1", "exercise", 4, stamp)
    expected = now.replace(second=3, microsecond=123456)
    assert s.facts.events[0].ts == s.receipt("T1").events[-1].ts == expected
    assert s.facts.verify() and s.receipt("T1").verify()


def test_external_unrepresentable_utc_is_typed_and_has_no_effect() -> None:
    """A cadeia UTC recusa um instante que não pode representar."""
    s, pos, draft, now = fact_session()
    early = datetime.fromisoformat("0001-01-01T00:00:00+01:00")
    with pytest.raises(SessionRefusal):
        s.external("sim", "B", "f1", "exercise", 4, early)
    assert s.facts.events == ()
    s.open("T1", pos, draft, now)
    confirm_fact_ticket(s, "T1", now)
    s.external("sim", "B", "f1", "exercise", 4, now)
    assert fact_rows(s, "T1") == [{"ticket": "T1", "fact": "f1", "series": ["B"]}]


def test_external_journal_is_committed_before_freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    """O livro recebe o congelamento depois de existir prova do fato na sessão."""
    from backend.derivatives.ticket.sequencing import ReservationBook

    s, _, _, now = fact_session()
    original = ReservationBook.freeze
    calls = []

    def observed(book: ReservationBook, account: str, symbol: str) -> None:
        entry, = s.facts.events
        assert json.loads(entry.payload)["fact"] == "f1" and s.facts.verify()
        calls.append((account, symbol))
        original(book, account, symbol)

    monkeypatch.setattr(ReservationBook, "freeze", observed)
    s.external("sim", "B", "f1", "exercise", 4, now)
    assert calls == [("sim", "B")]
