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
from backend.derivatives.ticket.sequencing import Position
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
