"""Executa uma sessão D0 a partir de uma fita e de decisões humanas roteirizadas."""
import argparse
import ctypes
import json
import os
import sys
from datetime import timedelta
from functools import partial
from itertools import pairwise
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal

from loguru import logger
from pydantic import Field, ValidationError

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.derivatives.ticket.engine import EngineRefusal, TicketEngine
from backend.derivatives.ticket.gate import Action, DecisionRefusal, issue
from backend.derivatives.ticket.guards import DeadlineRefusal
from backend.derivatives.ticket.models import PositiveInt, TicketDraft, _Frozen
from backend.derivatives.ticket.replay import Timestamp, load_replay
from backend.derivatives.ticket.sequencing import Position, SequenceRefusal
from backend.derivatives.ticket.session import ReplaySession, SessionRefusal
from backend.derivatives.ticket.state import TICKET_LABELS_PT
from backend.derivatives.ticket.trigger import TriggerRefusal, TriggerSpec, spec_digest
from config.ticket_sim_config_model import load_ticket_sim_config


class _Step(_Frozen):
    after_seq: Annotated[int, Field(ge=0)]
    at: Timestamp
    ticket: str


class _Open(_Step):
    do: Literal["open"]
    account: str
    draft: TicketDraft


class _Arm(_Step):
    do: Literal["arm"]
    spec: TriggerSpec


class _Order(_Step):
    do: Literal["cancel", "reconcile"]
    order_id: str


class _Simple(_Step):
    do: Literal["confirm", "pause", "resume"]


type Step = Annotated[_Open | _Arm | _Order | _Simple, Field(discriminator="do")]


class _Script(_Frozen):
    decision_ttl_s: PositiveInt
    positions: tuple[Position, ...]
    steps: tuple[Step, ...]


def _unique(items: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(items)
    if len(result) != len(items):
        raise ValueError("chave duplicada no roteiro")
    return result


def _read(path: Path) -> _Script:
    raw = path.read_bytes()
    json.loads(raw, object_pairs_hook=_unique)
    script = _Script.model_validate_json(raw)
    accounts = {p.account for p in script.positions}
    if len(accounts) != len(script.positions):
        raise ValueError("conta repetida")
    opened = set()
    if any(a.after_seq > b.after_seq for a, b in pairwise(script.steps)):
        raise ValueError("sequência de passos decrescente")
    for step in script.steps:
        if isinstance(step, _Open):
            if step.account not in accounts:
                raise ValueError("conta ausente")
            opened.add(step.ticket)
        elif step.ticket not in opened:
            raise ValueError("passo antes da abertura da boleta")
    return script


def _act(engine: TicketEngine, step: _Arm | _Order | _Simple, n: int, ttl: int) -> None:
    at = step.at
    if step.do == "pause":
        engine.pause(at)
        return
    if isinstance(step, _Order) and step.do == "reconcile":
        engine.reconcile(step.order_id, at)
        return
    decide = partial(issue, ticket=step.ticket, nonce=f"n{n}", issued_at=at,
                     expires_at=at + timedelta(seconds=ttl))
    if isinstance(step, _Arm):
        decision = decide(Action.ARM, preview=engine.preview, spec_digest=spec_digest(step.spec))
        engine.arm(step.spec, decision, at)
    elif isinstance(step, _Order):
        engine.cancel(step.order_id, decide(Action.CANCEL_ORDER, order_id=step.order_id), at)
    elif step.do == "confirm":
        engine.confirm(decide(Action.EXECUTE, preview=engine.preview), at)
    else:
        engine.resume(decide(Action.RESUME), at)


def _run(session: ReplaySession, script: _Script) -> list[dict[str, object]]:
    positions = {p.account: p for p in script.positions}
    refusals: list[dict[str, object]] = []
    for n, step in enumerate(script.steps, 1):
        session.advance_to(step.after_seq)
        session.check_time(step.at)
        if isinstance(step, _Open):
            try:
                session.open(step.ticket, positions[step.account], step.draft, step.at)
            except ValueError as exc:
                raise SessionRefusal(f"abertura recusada no passo {n}: {exc}") from exc
        else:
            try:
                _act(session.engine(step.ticket), step, n, script.decision_ttl_s)
            except OverflowError as exc:
                raise SessionRefusal(f"prazo fora do intervalo no passo {n}") from exc
            except (EngineRefusal, DecisionRefusal, SequenceRefusal, DeadlineRefusal,
                    TriggerRefusal) as exc:
                refusals.append({"passo": n, "acao": step.do, "boleta": step.ticket,
                                 "erro": type(exc).__name__})
    session.finish()
    return refusals


def _publish(staged: Path, out: Path) -> None:
    """Renomeia sem substituir nem mesmo um diretório vazio surgido durante a execução."""
    libc = ctypes.CDLL(None, use_errno=True)
    src, dst = os.fsencode(staged), os.fsencode(out)
    if sys.platform == "darwin":
        status = libc.renamex_np(src, dst, 0x4)  # RENAME_EXCL
    elif sys.platform == "linux" and hasattr(libc, "renameat2"):
        status = libc.renameat2(-100, src, -100, dst, 1)  # AT_FDCWD, RENAME_NOREPLACE
    else:
        raise OSError("destino sem suporte a rename exclusivo")
    if status:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno), out)


def _write(out: Path, target: Path, session: ReplaySession, tickets: list[str],
           summary: dict[str, object]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=target.parent) as staging:
        staged = Path(staging)
        if ".." in out.parts:
            # O próprio volume decide se um ancestral ausente é um alias do destino final.
            marker = staged / target.name
            marker.touch()
            for parent in reversed(out.parents):
                if parent.is_dir():
                    continue
                physical = Path(os.path.realpath(parent))
                if physical.parent.is_dir() and physical.parent.samefile(target.parent):
                    if (staged / physical.name).exists():
                        continue
                physical.mkdir(exist_ok=True)
            marker.unlink()
        for ticket in tickets:
            with (staged / f"recibo_{ticket}.jsonl").open("x", encoding="utf-8") as stream:
                for event in session.receipt(ticket).events:
                    row = {"seq": event.seq, "ts": event.ts.isoformat(), "kind": event.kind.value,
                           "payload": event.payload.decode("utf-8"), "prev_hash": event.prev_hash,
                           "hash": event.hash}
                    stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False,
                                            separators=(",", ":")) + "\n")
        formatted = json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=False)
        (staged / "resumo.json").write_text(formatted + "\n", encoding="utf-8")
        _publish(staged, target)


def main(argv: list[str] | None = None) -> int:
    """Valida e executa o roteiro inteiro antes de publicar os arquivos de saída."""
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("replay", "roteiro", "out"):
        parser.add_argument("--" + option, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        try:
            out = args.out.absolute()
            target = Path(os.path.realpath(out.parent)) / out.name
            if out.name == ".." or os.path.lexists(target):
                raise ValueError("destino já existe")
            if any(p.is_symlink() and not p.is_dir() for p in out.parents):
                raise ValueError("link de diretório sem destino acessível")
            script = _read(args.roteiro)
            session = ReplaySession(load_replay(args.replay), config=load_ticket_sim_config())
        except (OSError, OverflowError) as exc:
            raise ValueError(str(exc)) from exc
        refusals = _run(session, script)
        tickets = [step.ticket for step in script.steps if isinstance(step, _Open)]
        summary = session.summary() | {"recusas": refusals}
        try:
            _write(out, target, session, tickets, summary)
        except OSError as exc:
            raise ValueError(str(exc)) from exc
    except ValueError as exc:
        reason = exc.errors()[0]["type"] if isinstance(exc, ValidationError) else str(exc)
        logger.error("Replay interrompido: {}", reason)
        return 2
    logger.info("{}", summary["aviso"])
    for ticket in tickets:
        state = session.engine(ticket).state
        logger.info("{}: {} ({})", ticket, TICKET_LABELS_PT[state], state.value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
