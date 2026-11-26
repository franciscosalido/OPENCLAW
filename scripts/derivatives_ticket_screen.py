"""Gera a tela HTML estática de uma boleta num ponto de um replay D0."""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger
from pydantic import ValidationError

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.derivatives.ticket.engine import EngineRefusal
from backend.derivatives.ticket.gate import DecisionRefusal
from backend.derivatives.ticket.guards import DeadlineRefusal
from backend.derivatives.ticket.replay import load_replay
from backend.derivatives.ticket.screen import render_ticket
from backend.derivatives.ticket.sequencing import SequenceRefusal
from backend.derivatives.ticket.session import ReplaySession, SessionRefusal
from backend.derivatives.ticket.trigger import TriggerRefusal
from backend.derivatives.ticket.view import ticket_view
from config.ticket_sim_config_model import load_ticket_sim_config
from scripts.derivatives_ticket_replay import _act, _External, _Open, _read, _Script

_REFUSALS = (EngineRefusal, DecisionRefusal, SequenceRefusal, DeadlineRefusal, TriggerRefusal)


def _play(session: ReplaySession, script: _Script, steps: int) -> None:
    """Executa os primeiros passos como o roteiro oficial, sem consumir o resto da fita."""
    if not 0 < steps <= len(script.steps):
        raise ValueError("número de passos fora do roteiro")
    positions = {p.account: p for p in script.positions}
    for n, step in enumerate(script.steps[:steps], 1):
        session.advance_to(step.after_seq)
        session.check_time(step.at)
        if isinstance(step, _External):
            session.external(step.account, step.symbol, step.fact, step.kind,
                             step.quantity, step.at)
        elif isinstance(step, _Open):
            session.open(step.ticket, positions[step.account], step.draft, step.at)
        else:
            try:
                _act(session.engine(step.ticket), step, n, script.decision_ttl_s)
            except _REFUSALS:
                continue


def main(argv: list[str] | None = None) -> int:
    """Projeta a boleta no instante pedido e grava um único arquivo novo."""
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("replay", "roteiro", "out"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--passos", type=int, required=True)
    parser.add_argument("--avanca-ate", type=int, required=True)
    parser.add_argument("--boleta", required=True)
    parser.add_argument("--instante", required=True)
    args = parser.parse_args(argv)
    try:
        try:
            script = _read(args.roteiro)
            session = ReplaySession(load_replay(args.replay), config=load_ticket_sim_config())
            now = datetime.fromisoformat(args.instante)
            _play(session, script, args.passos)
            session.advance_to(args.avanca_ate)
            page = render_ticket(ticket_view(session, args.boleta, now))
            with args.out.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(page)
        except KeyError as exc:
            raise ValueError("boleta não aberta neste ponto do roteiro") from exc
        except (OSError, OverflowError) as exc:
            raise ValueError(str(exc)) from exc
    except ValueError as exc:
        reason = exc.errors()[0]["type"] if isinstance(exc, ValidationError) else str(exc)
        logger.error("Tela não gerada: {}", reason)
        return 2
    logger.info("Tela gravada em {}", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
