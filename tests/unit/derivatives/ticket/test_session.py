"""Contrato público da sessão sintética de replay."""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from backend.derivatives.ticket.engine import EngineRefusal
from backend.derivatives.ticket.models import TicketDraft
from backend.derivatives.ticket.replay import load_replay
from backend.derivatives.ticket.sequencing import Position
from backend.derivatives.ticket.session import ReplaySession, SessionRefusal
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
