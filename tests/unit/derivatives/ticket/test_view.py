"""Contrato da visão de leitura da boleta: gabarito literal e equivalência com o motor."""
import json
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal as D, InvalidOperation, localcontext
from hashlib import sha256
from pathlib import Path

import pytest

from backend.derivatives.ticket.engine import EngineRefusal
from backend.derivatives.ticket.gate import DecisionRefusal
from backend.derivatives.ticket.guards import DeadlineRefusal
from backend.derivatives.ticket.models import TicketDraft
from backend.derivatives.ticket.receipt import dump_rows
from backend.derivatives.ticket.replay import Replay, load_replay
from backend.derivatives.ticket.sequencing import Position, SequenceRefusal
from backend.derivatives.ticket.session import ReplaySession, SessionRefusal
from backend.derivatives.ticket.view import TicketView, ticket_view
from config.ticket_sim_config_model import load_ticket_sim_config
from scripts.derivatives_ticket_replay import _act, _External, _Open, _read
from tests.unit.derivatives.ticket.test_session import FIXTURES

ROOT = Path(__file__).resolve().parents[4]
SCHEMA = ROOT / "docs/specs/derivatives/fase4/schemas/visao.schema.json"
REFUSALS = (EngineRefusal, DecisionRefusal, SequenceRefusal, DeadlineRefusal)
ANCHORS = {("calmo", "T1"): "1d50bba66aa2", ("leilao", "T1"): "8592cd742d26",
           ("rapido", "T1"): "9ebc9cd5b584", ("rapido", "T2"): "fbcaafa8eb79"}


def at(text: str) -> datetime:
    """Instante UTC do dia das fitas oficiais."""
    return datetime.fromisoformat(f"2026-11-23T{text}+00:00")


def official(name: str, steps: int, *, watch: bool = False) -> ReplaySession:
    """Executa os primeiros passos do roteiro oficial; com watch, projeta antes e depois."""
    script = _read(FIXTURES / f"{name}.roteiro.json")
    session = ReplaySession(load_replay(FIXTURES / f"{name}.replay.json"),
                            config=load_ticket_sim_config())
    positions = {p.account: p for p in script.positions}
    opened: list[str] = []
    for n, step in enumerate(script.steps[:steps], 1):
        session.advance_to(step.after_seq)
        if watch:
            for ticket in opened:
                ticket_view(session, ticket, step.at)
        if isinstance(step, _Open):
            session.open(step.ticket, positions[step.account], step.draft, step.at)
            opened.append(step.ticket)
        else:
            assert not isinstance(step, _External)
            try:
                _act(session.engine(step.ticket), step, n, script.decision_ttl_s)
            except REFUSALS:
                pass
        if watch:
            for ticket in opened:
                ticket_view(session, ticket, step.at)
    return session


Quote = tuple[int, str, str, str | None, int, str | None, int, str]


def custom(quotes: Sequence[Quote], legs: Sequence[tuple[str, str, int, str]], *, net: str,
           gross: str, holdings: Sequence[tuple[str, str, int]] | None = None,
           pairs: list[list[str]] | None = None, expiries: dict[str, str] | None = None,
           multiplier: int = 1, open_seq: int = 2,
           multipliers: dict[str, int] | None = None) -> ReplaySession:
    """Monta fita e boleta T1; cotação = (seq, hh:mm:ss, série, bid, qtd, ask, qtd, fase)."""
    events = [{"seq": seq, "ts": f"2026-11-23T{ts}Z", "type": "quote", "symbol": sym,
               "bid": bid, "bid_size": bn, "ask": ask, "ask_size": an, "phase": phase}
              for seq, ts, sym, bid, bn, ask, an, phase in quotes]
    replay = Replay.model_validate_json(json.dumps(
        {"session_close": "2026-11-23T21:00:00Z", "events": events}))
    rows = holdings or [("A", "10", 0), ("B", "11", 0)]
    position = Position.model_validate_json(json.dumps({
        "account": "sim", "pairs": [["A", "B"]] if pairs is None else pairs,
        "holdings": [{"symbol": s, "strike": k, "underlying": "ETF", "kind": "CALL",
                      "expiry": (expiries or {}).get(s, "2027-01-15"),
                      "multiplier": (multipliers or {}).get(s, multiplier), "balance": b}
                     for s, k, b in rows]}))
    draft = TicketDraft.model_validate_json(json.dumps({
        "legs": [{"symbol": s, "side": side, "quantity": q, "limit_price": p, "lot_size": 1}
                 for s, side, q, p in legs],
        "net_limit": net, "gross_cap": gross, "send_deadline": "2026-11-23T15:00:00Z",
        "order_validity": "2026-11-23T21:00:00Z", "quote_snapshot_id": "sintetico"}))
    session = ReplaySession(replay, config=load_ticket_sim_config())
    session.advance_to(open_seq)
    session.open("T1", position, draft, replay.events[min(open_seq, len(events)) - 1].ts)
    return session


CALM: list[Quote] = [(1, "14:00:00", "A", "0.95", 50, "1.02", 50, "CONTINUOUS"),
                     (2, "14:00:01", "B", "1.45", 50, "1.55", 50, "CONTINUOUS")]
CREDIT = [("A", "BUY", 10, "1.00"), ("B", "SELL", 10, "1.50")]
DEBIT = [("A", "BUY", 10, "1.50"), ("B", "SELL", 10, "1.00")]


def line(view: TicketView) -> tuple[object, ...]:
    """Resumo comparável: estado, avanço, mercado e guarda e idade por perna."""
    return (view.estado.value, view.rotulo, view.avanco.situacao.value, view.avanco.motivo,
            view.mercado.nivel, view.mercado.motivos,
            tuple((leg.guarda.nivel, leg.guarda.motivos,
                   None if leg.cotacao is None else leg.cotacao.idade_s) for leg in view.pernas))


OK2 = (("OK", (), 2.0), ("OK", (), 1.0))
V1 = [
    ("calmo", 1, "T1", "14:00:02", None,
     ("DRAFT", "Proposta", "PODE_CONFIRMAR", None, "OK", (), OK2)),
    ("calmo", 2, "T1", "14:00:02", None,
     ("ARMED", "Engatilhada", "NAO_SE_APLICA", None, "OK", (), OK2)),
    ("calmo", 2, "T1", "14:00:12", 6,
     ("TRIGGERED", "Gatilho atingido", "PODE_CONFIRMAR", None, "OK", (), OK2)),
    ("calmo", 5, "T1", "21:00:00", 9,
     ("COMPLETED", "Concluída", "NAO_SE_APLICA", None, "CAUTION", ("cotação antiga",),
      (("OK", (), 0.0), ("CAUTION", ("cotação antiga",), 25186.0)))),
    ("leilao", 1, "T1", "14:00:02", None,
     ("DRAFT", "Proposta", "BLOQUEADA", "leilão, leilão", "BLOCKED", ("leilão", "leilão"),
      (("BLOCKED", ("leilão",), 2.0), ("BLOCKED", ("leilão",), 1.0)))),
    ("leilao", 1, "T1", "14:00:07", None,
     ("DRAFT", "Proposta", "BLOQUEADA", "leilão, leilão", "BLOCKED", ("leilão", "leilão"),
      (("BLOCKED", ("leilão",), 7.0), ("BLOCKED", ("leilão",), 6.0)))),
    ("leilao", 1, "T1", "14:00:17", None,
     ("DRAFT", "Proposta", "BLOQUEADA", "cotação antiga, leilão, cotação antiga, leilão",
      "BLOCKED", ("cotação antiga", "leilão", "cotação antiga", "leilão"),
      (("BLOCKED", ("cotação antiga", "leilão"), 17.0),
       ("BLOCKED", ("cotação antiga", "leilão"), 16.0)))),
    ("leilao", 4, "T1", "14:05:06", None,
     ("WORKING", "Em execução", "NAO_SE_APLICA", None, "BLOCKED",
      ("leilão", "pouca profundidade"),
      (("BLOCKED", ("leilão",), 1.0), ("CAUTION", ("pouca profundidade",), 2.0)))),
    ("leilao", 4, "T1", "21:00:00", 11,
     ("STOPPED", "Parada · montagem parcial", "NAO_SE_APLICA", None, "CAUTION",
      ("cotação antiga",), (("CAUTION", ("cotação antiga",), 24600.0), ("OK", (), 0.0)))),
    ("rapido", 3, "T2", "14:00:02", None,
     ("DRAFT", "Proposta", "BLOQUEADA", "conta em estado incerto", "OK", (), OK2)),
    ("rapido", 3, "T1", "14:00:02", None,
     ("UNCERTAIN", "Boleta em estado incerto", "NAO_SE_APLICA", None, "OK", (), OK2)),
    ("rapido", 5, "T2", "14:00:03", None,
     ("DRAFT", "Proposta", "BLOQUEADA", "recompra excede a posição vendida disponível",
      "CAUTION", ("pouca profundidade",),
      (("OK", (), 3.0), ("CAUTION", ("pouca profundidade",), 0.0)))),
    ("rapido", 8, "T2", "14:00:06", None,
     ("DRAFT", "Proposta", "BLOQUEADA",
      "perda de sequência, pouca profundidade, perda de sequência", "BLOCKED",
      ("perda de sequência", "pouca profundidade", "perda de sequência"),
      (("BLOCKED", ("perda de sequência", "pouca profundidade"), 2.0),
       ("BLOCKED", ("perda de sequência",), 1.0)))),
    ("rapido", 9, "T1", "21:00:00", 9,
     ("STOPPED", "Parada · desmontagem parcial", "NAO_SE_APLICA", None, "BLOCKED",
      ("perda de sequência", "cotação antiga", "perda de sequência"),
      (("BLOCKED", ("perda de sequência",), 0.0),
       ("BLOCKED", ("cotação antiga", "perda de sequência"), 25193.0)))),
]


@pytest.mark.parametrize("name,steps,ticket,clock,seq,expected", V1)
def test_v1_official_sessions_literal(name: str, steps: int, ticket: str, clock: str,
                                      seq: int | None, expected: tuple[object, ...]) -> None:
    """Catorze fotos das três sessões oficiais, com estado, avanço e guardas literais."""
    session = official(name, steps)
    if seq is not None:
        session.advance_to(seq)
    assert line(ticket_view(session, ticket, at(clock))) == expected


def test_v2_view_predicts_every_scripted_confirmation() -> None:
    """Antes de cada confirmação dos roteiros, a visão diz o que o motor responde."""
    seen = []
    for name in ("calmo", "leilao", "rapido"):
        script = _read(FIXTURES / f"{name}.roteiro.json")
        for n, step in enumerate(script.steps, 1):
            if step.do != "confirm":
                continue
            session = official(name, n - 1)
            session.advance_to(step.after_seq)
            advance = ticket_view(session, step.ticket, step.at).avanco
            try:
                _act(session.engine(step.ticket), step, n, script.decision_ttl_s)
            except REFUSALS as exc:
                assert (advance.situacao.value, advance.motivo) == ("BLOQUEADA", str(exc))
            else:
                assert (advance.situacao.value, advance.motivo) == ("PODE_CONFIRMAR", None)
            seen.append((name, n, advance.situacao.value, advance.motivo))
    assert seen == [
        ("calmo", 3, "PODE_CONFIRMAR", None),
        ("leilao", 2, "BLOQUEADA", "leilão, leilão"),
        ("leilao", 3, "PODE_CONFIRMAR", None),
        ("rapido", 3, "PODE_CONFIRMAR", None),
        ("rapido", 4, "BLOQUEADA", "conta em estado incerto"),
        ("rapido", 6, "BLOQUEADA", "recompra excede a posição vendida disponível"),
        ("rapido", 9, "BLOQUEADA", "perda de sequência, pouca profundidade, perda de sequência"),
    ]


def test_v3_quote_age_boundary_is_per_leg_and_inclusive() -> None:
    """Idade igual ao limite passa sem aviso; acima, só a perna antiga avisa, sem bloquear."""
    session = official("calmo", 1)
    session.advance_to(8)
    edge = ticket_view(session, "T1", at("14:00:28"))
    assert line(edge)[2:] == ("PODE_CONFIRMAR", None, "OK", (),
                              (("OK", (), 15.0), ("OK", (), 14.0)))
    over = ticket_view(session, "T1", at("14:00:29"))
    assert line(over)[2:] == ("PODE_CONFIRMAR", None, "CAUTION", ("cotação antiga",),
                              (("CAUTION", ("cotação antiga",), 16.0), ("OK", (), 15.0)))
    assert ticket_view(session, "T1", at("14:00:28") + timedelta(microseconds=1)
                       ).pernas[0].guarda.motivos == ("cotação antiga",)


def test_v4_refusal_follows_the_engine_order() -> None:
    """Pausa precede prazo; prazo precede mercado; mercado precede limites."""
    session = official("calmo", 1)
    session.advance_to(8)
    last = ticket_view(session, "T1", at("15:00:00"))
    assert (last.avanco.situacao.value, last.avanco.motivo, last.mercado.nivel,
            last.mercado.motivos) == ("PODE_CONFIRMAR", None, "CAUTION",
                                      ("cotação antiga", "cotação antiga"))
    late = ticket_view(session, "T1", at("15:00:01"))
    assert late.avanco.motivo == "prazo de envio vencido" and late.mercado.nivel == "CAUTION"
    closed = [CALM[0], (2, "14:00:01", "B", "1.45", 50, "1.55", 50, "AUCTION")]
    halted = ticket_view(custom(closed, CREDIT, net="-5.00", gross="25.00"), "T1",
                         at("15:00:01"))
    assert halted.avanco.motivo == "prazo de envio vencido" and halted.mercado.nivel == "BLOCKED"
    session.engine("T1").pause(at("15:00:01"))
    paused = ticket_view(session, "T1", at("15:00:01"))
    assert paused.pausada and paused.avanco.motivo == "boleta pausada"
    tight = custom(CALM, CREDIT, net="-5.01", gross="25.00")
    view = ticket_view(tight, "T1", at("14:00:01"))
    assert (view.avanco.situacao.value, view.avanco.motivo, view.mercado.nivel) == (
        "BLOQUEADA", "limites assinados", "OK")
    auction = custom([CALM[0], (2, "14:00:01", "B", "1.45", 50, "1.55", 50, "AUCTION")],
                     CREDIT, net="-5.01", gross="25.00")
    assert ticket_view(auction, "T1", at("14:00:01")).avanco.motivo == "leilão"


def test_v5_absence_is_not_zero() -> None:
    """Série sem cotação e lado vazio aparecem como ausência, nunca como número."""
    missing = custom(CALM[:1], CREDIT, net="-5.00", gross="25.00", open_seq=1)
    view = ticket_view(missing, "T1", at("14:00:00"))
    assert view.pernas[1].cotacao is None
    assert view.pernas[1].guarda.model_dump() == {"nivel": "BLOCKED", "motivos": ("sem cotação",)}
    assert view.pernas[0].cotacao is not None and view.avanco.motivo == "sem cotação"
    data = json.loads(view.model_dump_json())
    assert data["pernas"][1]["cotacao"] is None and "cotacao" in data["pernas"][1]
    empty = custom([(1, "14:00:00", "A", "0.95", 50, None, 0, "CONTINUOUS"), CALM[1]],
                   CREDIT, net="-5.00", gross="25.00")
    quote = ticket_view(empty, "T1", at("14:00:01")).pernas[0]
    assert quote.cotacao is not None and (quote.cotacao.venda, quote.cotacao.venda_qtd) == (None, 0)
    assert quote.guarda.motivos == ("livro incompleto",)


def test_v6_caution_does_not_block() -> None:
    """Pouca profundidade e spread aberto avisam, e o motor confirma."""
    thin = [(1, "14:00:00", "A", "0.80", 50, "1.02", 3, "CONTINUOUS"), CALM[1]]
    session = custom(thin, CREDIT, net="-5.00", gross="25.00")
    view = ticket_view(session, "T1", at("14:00:01"))
    assert (view.mercado.nivel, view.mercado.motivos) == (
        "CAUTION", ("spread aberto", "pouca profundidade"))
    assert view.pernas[0].guarda.nivel == "CAUTION" and view.pernas[1].guarda.nivel == "OK"
    assert view.avanco.situacao.value == "PODE_CONFIRMAR"
    step = _read(FIXTURES / "calmo.roteiro.json").steps[2].model_copy(
        update={"at": at("14:00:01"), "after_seq": 2})
    _act(session.engine("T1"), step, 1, 60)  # type: ignore[arg-type]
    assert session.engine("T1").state.value == "WORKING"


def test_v7_two_risks_are_distinct_and_signed() -> None:
    """Desembolso da montagem e extremos do vencimento não se confundem."""
    credit = ticket_view(official("calmo", 1), "T1", at("14:00:02"))
    assert credit.custo.model_dump(mode="json") == {
        "liquido_assinado": "-5.00", "natureza": "CREDITO", "bruto_teto": "25.00"}
    assert credit.risco.model_dump(mode="json") == {
        "exposicao_montagem": "10.00", "vencimento_indisponivel": None,
        "vencimento": {"pior_resultado": "5.00", "perda_ilimitada": False,
                       "melhor_resultado": "15.00", "ganho_ilimitado": False,
                       "equilibrios": [], "inclinacao_final": "0.00", "curva": [
                           {"preco": "0.00", "resultado": "5.00"},
                           {"preco": "10.00", "resultado": "5.00"},
                           {"preco": "11.00", "resultado": "15.00"}]}}
    debit = ticket_view(custom(CALM, DEBIT, net="5.00", gross="25.00"), "T1", at("14:00:01"))
    assert debit.custo.model_dump(mode="json") == {
        "liquido_assinado": "5.00", "natureza": "DEBITO", "bruto_teto": "25.00"}
    assert debit.risco.model_dump(mode="json") == {
        "exposicao_montagem": "15.00", "vencimento_indisponivel": None,
        "vencimento": {"pior_resultado": "-5.00", "perda_ilimitada": False,
                       "melhor_resultado": "5.00", "ganho_ilimitado": False,
                       "equilibrios": ["10.50"], "inclinacao_final": "0.00", "curva": [
                           {"preco": "0.00", "resultado": "-5.00"},
                           {"preco": "10.00", "resultado": "-5.00"},
                           {"preco": "11.00", "resultado": "5.00"}]}}
    flat = ticket_view(custom(CALM, [("A", "BUY", 10, "1.00"), ("B", "SELL", 10, "1.00")],
                              net="0.00", gross="25.00"), "T1", at("14:00:01"))
    assert flat.custo.natureza.value == "ZERO"


def test_v8_expiry_profile_refuses_what_it_cannot_represent() -> None:
    """Cada motivo de indisponibilidade é literal e deixa o desembolso intacto."""
    closing = ticket_view(official("rapido", 2), "T1", at("14:00:02"))
    assert closing.risco.model_dump(mode="json") == {
        "exposicao_montagem": "15.00", "vencimento": None,
        "vencimento_indisponivel": "posição inicial não nula"}
    two = [("A", "BUY", 10, "1.00"), ("B", "BUY", 10, "1.50")]
    for session, reason in (
        (custom(CALM, CREDIT, net="-5.00", gross="25.00", multiplier=2),
         "multiplicador diferente de 1"),
        (custom(CALM, two, net="25.00", gross="25.00", expiries={"B": "2027-02-19"}, pairs=[]),
         "séries de ativos ou vencimentos diferentes"),
    ):
        view = ticket_view(session, "T1", at("14:00:01"))
        assert (view.risco.vencimento, view.risco.vencimento_indisponivel) == (None, reason)
    scale: tuple[tuple[str, str | None], ...] = (
        ("1E+15", None), ("1E+16", "valores fora da escala do perfil"))
    for price, why in scale:
        view = ticket_view(custom(CALM, [("A", "BUY", 1, price)], net="1E+17", gross="1E+17",
                                  pairs=[]), "T1", at("14:00:01"))
        assert view.risco.vencimento_indisponivel == why
        assert view.risco.exposicao_montagem == D(price)


def test_v9_single_leg_and_unlimited_gain() -> None:
    """Uma perna só: perda limitada ao prêmio e ganho sem teto, dito por extenso."""
    view = ticket_view(custom(CALM, [("A", "BUY", 10, "1.00")], net="10.00", gross="10.00",
                              pairs=[]), "T1", at("14:00:01"))
    assert len(view.pernas) == 1
    assert view.risco.model_dump(mode="json")["vencimento"] == {
        "pior_resultado": "-10.00", "perda_ilimitada": False,
        "melhor_resultado": None, "ganho_ilimitado": True, "equilibrios": ["11.00"],
        "inclinacao_final": "10.00", "curva": [{"preco": "0.00", "resultado": "-10.00"},
                                                {"preco": "10.00", "resultado": "-10.00"}]}


def test_v10_exponent_notation_and_money_identity() -> None:
    """Dinheiro do motor passa sem reescrita; o perfil não depende da grafia."""
    plain = ticket_view(custom(CALM, DEBIT, net="5.00", gross="25.00"), "T1", at("14:00:01"))
    odd = custom(CALM, [("A", "BUY", 10, "15E-1"), ("B", "SELL", 10, "1.0E+0")], net="5",
                 gross="1E+2", holdings=[("A", "1E+1", 0), ("B", "11.000", 0)])
    view = ticket_view(odd, "T1", at("14:00:01"))
    preview = odd.engine("T1").preview
    assert preview is not None
    assert view.risco.vencimento == plain.risco.vencimento
    assert json.loads(view.model_dump_json())["risco"]["vencimento"] == {
        "pior_resultado": "-5.00", "perda_ilimitada": False,
        "melhor_resultado": "5.00", "ganho_ilimitado": False, "equilibrios": ["10.50"],
        "inclinacao_final": "0.00", "curva": [{"preco": "0.00", "resultado": "-5.00"},
                                               {"preco": "10.00", "resultado": "-5.00"},
                                               {"preco": "11.00", "resultado": "5.00"}]}
    assert [str(leg.strike) for leg in view.pernas] == ["1E+1", "11.000"]
    assert json.loads(view.model_dump_json())["custo"] == {
        "liquido_assinado": "5", "natureza": "DEBITO", "bruto_teto": "1E+2"}
    assert [str(leg.preco_limite) for leg in view.pernas] == ["1.5", "1.0"]
    assert (view.custo.liquido_assinado, view.custo.bruto_teto, view.risco.exposicao_montagem,
            view.resumo, view.versao) == (preview.net_limit, preview.gross_cap,
                                          preview.partial_exposure, preview.digest, 1)


def test_v11_view_never_changes_session_engine_or_receipt() -> None:
    """Projetar em cada passo não muda resumo, recibos nem as quatro âncoras oficiais."""
    for name, steps in (("calmo", 5), ("leilao", 4), ("rapido", 9)):
        plain, watched = official(name, steps), official(name, steps, watch=True)
        plain.finish()
        watched.finish()
        assert watched.summary() == plain.summary()
        for ticket, body in plain.summary()["boletas"].items():  # type: ignore[attr-defined]
            assert list(dump_rows(watched.receipt(ticket))) == list(
                dump_rows(plain.receipt(ticket)))
            assert body["recibo_hash"].startswith(ANCHORS[name, ticket])
    shared = official("rapido", 2)
    for ticket in ("T2", "T1", "T2", "T1"):
        assert ticket_view(shared, ticket, at("14:00:02")).avanco.situacao.value == (
            "PODE_CONFIRMAR")
    session = official("calmo", 1)
    before = (session.summary(), list(dump_rows(session.receipt("T1"))))
    first = ticket_view(session, "T1", at("14:00:02"))
    assert ticket_view(session, "T1", at("14:00:02")) == first
    assert (session.summary(), list(dump_rows(session.receipt("T1")))) == before


def test_v12_clock_is_the_replay_clock() -> None:
    """Instante sem fuso ou fora da janela do cursor é recusado; fuso não muda a visão."""
    session = official("calmo", 1)
    for bad in (datetime(2026, 11, 23, 14, 0, 2), at("14:00:00"), at("14:00:06")):
        with pytest.raises(SessionRefusal):
            ticket_view(session, "T1", bad)
    with pytest.raises(KeyError):
        ticket_view(session, "T9", at("14:00:02"))
    local = datetime(2026, 11, 23, 11, 0, 2, tzinfo=timezone(timedelta(hours=-3)))
    assert ticket_view(session, "T1", local) == ticket_view(session, "T1", at("14:00:02"))
    assert json.loads(ticket_view(session, "T1", local).model_dump_json())["instante"] == (
        "2026-11-23T14:00:02Z")


def test_v13_market_guard_is_the_concatenation_of_leg_guards() -> None:
    """A guarda do conjunto é a do motor; as das pernas somam os mesmos motivos."""
    order = {"OK": 0, "CAUTION": 1, "BLOCKED": 2}
    for name, steps, ticket, clock, seq, _ in V1:
        session = official(name, steps)
        if seq is not None:
            session.advance_to(seq)
        view = ticket_view(session, ticket, at(clock))
        assert view.mercado.motivos == tuple(m for leg in view.pernas for m in leg.guarda.motivos)
        assert view.mercado.nivel == max((leg.guarda.nivel for leg in view.pernas),
                                         key=order.__getitem__)


def answers(data: dict[str, object]) -> list[str]:
    """Leitor independente: responde as seis perguntas só com o JSON, sem os modelos."""
    legs: list[dict[str, object]] = data["pernas"]  # type: ignore[assignment]
    cost: dict[str, str] = data["custo"]  # type: ignore[assignment]
    risk: dict[str, object] = data["risco"]  # type: ignore[assignment]
    advance: dict[str, str | None] = data["avanco"]  # type: ignore[assignment]
    market: dict[str, object] = data["mercado"]  # type: ignore[assignment]
    expiry: dict[str, object] | None = risk["vencimento"]  # type: ignore[assignment]
    reasons: list[str] = market["motivos"]  # type: ignore[assignment]
    verb = {"DEBITO": "paga no máximo", "CREDITO": "recebe no mínimo", "ZERO": "líquido zero"}
    ages = []
    for leg in legs:
        quote: dict[str, object] | None = leg["cotacao"]  # type: ignore[assignment]
        ages.append(f"{leg['serie']} " + ("sem cotação" if quote is None
                                          else f"{quote['idade_s']} s"))
    return [
        "; ".join(f"{leg['lado_rotulo']} {leg['quantidade']} {leg['serie']} "
                  f"({leg['tipo']} {leg['strike']}) a {leg['preco_limite']}" for leg in legs),
        f"{verb[cost['natureza']]} {cost['liquido_assinado'].lstrip('-')}; "
        f"bruto até {cost['bruto_teto']}",
        f"desembolso se só a compra executar {risk['exposicao_montagem']}; " + (
            f"vencimento indisponível: {risk['vencimento_indisponivel']}" if expiry is None
            else f"pior resultado no vencimento {expiry['pior_resultado']}"),
        f"{', '.join(ages)}; foto {data['foto_cotacao']}",
        f"{market['nivel']}: " + (", ".join(reasons) or "sem aviso"),
        {"PODE_CONFIRMAR": "pode confirmar", "BLOQUEADA": f"não avança: {advance['motivo']}",
         "NAO_SE_APLICA": f"não se aplica: {data['rotulo']}"}[str(advance["situacao"])],
    ]


def test_v14_six_answers_from_json_alone() -> None:
    """O contrato basta para as seis perguntas da prova de uso, nas três sessões."""
    def read(name: str, steps: int, ticket: str, clock: str) -> list[str]:
        text = ticket_view(official(name, steps), ticket, at(clock)).model_dump_json()
        return answers(json.loads(text))

    assert read("calmo", 1, "T1", "14:00:02") == [
        "Compra 10 A (CALL 10) a 1.00; Venda 10 B (CALL 11) a 1.50",
        "recebe no mínimo 5.00; bruto até 25.00",
        "desembolso se só a compra executar 10.00; pior resultado no vencimento 5.00",
        "A 2.0 s, B 1.0 s; foto calmo-2",
        "OK: sem aviso",
        "pode confirmar",
    ]
    assert read("leilao", 1, "T1", "14:00:07") == [
        "Compra 10 A (CALL 10) a 1.00; Venda 10 B (CALL 11) a 1.50",
        "recebe no mínimo 5.00; bruto até 25.00",
        "desembolso se só a compra executar 10.00; pior resultado no vencimento 5.00",
        "A 7.0 s, B 6.0 s; foto leilao-2",
        "BLOCKED: leilão, leilão",
        "não avança: leilão, leilão",
    ]
    assert read("rapido", 3, "T2", "14:00:02") == [
        "Venda 10 A (CALL 10) a 1.00; Compra 10 B (CALL 11) a 1.50",
        "paga no máximo 5.00; bruto até 25.00",
        "desembolso se só a compra executar 15.00; "
        "vencimento indisponível: posição inicial não nula",
        "A 2.0 s, B 1.0 s; foto rapido-2",
        "OK: sem aviso",
        "não avança: conta em estado incerto",
    ]
    assert read("calmo", 2, "T1", "14:00:02")[5] == "não se aplica: Engatilhada"


def test_v15_json_round_trip_and_published_schema() -> None:
    """A saída relê igual, recusa campo extra e o esquema gerado é o arquivo publicado."""
    view = ticket_view(official("calmo", 1), "T1", at("14:00:02"))
    text = view.model_dump_json()
    assert TicketView.model_validate_json(text) == view
    data = json.loads(text)
    assert list(data) == [
        "formato", "aviso", "ambiente", "boleta", "conta", "instante", "estado", "rotulo",
        "pausada", "versao", "resumo", "foto_cotacao", "prazo_envio", "validade_ordens",
        "limite_idade_s", "pernas", "preco_unidade", "preco_unidade_indisponivel", "custo",
        "risco", "mercado", "avanco"]
    assert (data["formato"], data["aviso"]) == (
        2, "SIMULADO — dados sintéticos em replay; nenhuma ordem real.")
    for change in ({"extra": 1}, {"formato": 1}, {"formato": 3}):
        with pytest.raises(ValueError):
            TicketView.model_validate_json(json.dumps(data | change))
    schema = TicketView.model_json_schema(mode="serialization")
    assert schema["additionalProperties"] is False
    assert all(body["additionalProperties"] is False for body in schema["$defs"].values()
               if body.get("type") == "object")
    generated = (json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    assert SCHEMA.read_bytes() == generated
    assert sha256(generated).hexdigest() == (
        "0655d7ef91caec03e35c573901854b4a2fe8c26c9232b4e0cf9230991e556e4f")


def test_v16_view_is_independent_of_the_callers_decimal_context() -> None:
    """A visão completa conserva os bytes sob precisão reduzida, com e sem armadilha."""
    session = official("calmo", 1)
    now = at("14:00:02")
    with localcontext(Context()):
        expected = ticket_view(session, "T1", now).model_dump_json().encode()
    expiry = json.loads(expected)["risco"]["vencimento"]
    assert (expiry["pior_resultado"], expiry["melhor_resultado"]) == ("5.00", "15.00")
    for trap in (True, False):
        with localcontext(Context(prec=3)) as context:
            context.traps[InvalidOperation] = trap
            assert ticket_view(session, "T1", now).model_dump_json().encode() == expected


def test_w1_format_two_is_an_integer_and_nothing_else() -> None:
    """O formato só aceita o inteiro 2, em Python e em JSON."""
    view = ticket_view(official("calmo", 1), "T1", at("14:00:02"))
    assert view.formato == 2 and type(view.formato) is int
    data = view.model_dump()
    for bad in (True, 2.0, "2", 1, 3, None, D(2)):
        with pytest.raises(ValueError):
            TicketView.model_validate(data | {"formato": bad})
    text = view.model_dump_json()
    assert text.startswith('{"formato":2,')
    for bad_json in ("true", "2.0", '"2"', "1", "3", "null", "2e0"):
        with pytest.raises(ValueError):
            TicketView.model_validate_json(
                text.replace('"formato":2,', f'"formato":{bad_json},', 1))


def test_w2_environment_and_age_limit_come_from_the_engine() -> None:
    """O ambiente é o da prévia; o limite de idade é o da configuração que a guarda usa."""
    view = ticket_view(official("bova_calmo", 1), "T1",
                       datetime.fromisoformat("2026-11-25T14:00:02+00:00"))
    assert (view.ambiente.value, view.limite_idade_s) == ("SIMULATED", 15.0)
    strict = bova("bova_vencida", 3, "14:00:20")
    assert (strict["limite_idade_s"], strict["mercado"]) == (
        15.0, {"nivel": "CAUTION", "motivos": ["cotação antiga"]})
    script = _read(FIXTURES / "bova_vencida.roteiro.json")
    config = load_ticket_sim_config().model_copy(update={"max_quote_age_s": 30.0})
    session = ReplaySession(load_replay(FIXTURES / "bova_vencida.replay.json"), config=config)
    session.advance_to(3)
    opening = script.steps[0]
    assert isinstance(opening, _Open)
    session.open("T1", script.positions[0], opening.draft, opening.at)
    loose = ticket_view(session, "T1", datetime.fromisoformat("2026-11-25T14:00:20+00:00"))
    assert (loose.limite_idade_s, loose.mercado.nivel, loose.mercado.motivos) == (30.0, "OK", ())


def bova(name: str, seq: int, clock: str) -> dict[str, object]:
    """JSON da visão da T1 de uma sessão BOVA depois da abertura."""
    session = official(name, 1)
    session.advance_to(seq)
    view = ticket_view(session, "T1", datetime.fromisoformat(f"2026-11-25T{clock}+00:00"))
    data: dict[str, object] = json.loads(view.model_dump_json())
    return data


def test_w3_exercise_style_comes_from_the_position() -> None:
    """A modalidade é a da foto; sem informação, fica nula."""
    styles = {}
    for name, seq, clock in (("bova_calmo", 2, "14:00:02"), ("bova_vencida", 3, "14:00:20"),
                             ("bova_adverso", 2, "14:00:02")):
        legs: list[dict[str, object]] = bova(name, seq, clock)["pernas"]  # type: ignore[assignment]
        styles[name] = [leg["modalidade"] for leg in legs]
    assert styles == {"bova_calmo": ["AMERICAN", "EUROPEAN"],
                      "bova_vencida": ["EUROPEAN", "EUROPEAN"],
                      "bova_adverso": ["EUROPEAN", "AMERICAN"]}
    plain = ticket_view(official("calmo", 1), "T1", at("14:00:02"))
    assert [leg.modalidade for leg in plain.pernas] == [None, None]
    row = {"symbol": "A", "strike": "10", "underlying": "ETF", "kind": "CALL",
           "expiry": "2027-01-15", "multiplier": 1, "balance": 0}
    for bad in ("BERMUDAN", "american", ""):
        with pytest.raises(ValueError):
            Position.model_validate_json(json.dumps(
                {"account": "sim", "pairs": [], "holdings": [row | {"style": bad}]}))


UNIT = {
    "bova_calmo": (["4.175", "2.125"], {"quantidade": 100, "limite": "2.10", "natural": "2.10",
                                        "meio": "2.05", "acima_do_meio": "5.00"}),
    "bova_vencida": (["1.875", "3.925"], {"quantidade": 200, "limite": "-2.00",
                                          "natural": "-2.00", "meio": "-2.05",
                                          "acima_do_meio": "10.00"}),
    "bova_adverso": (["1.975", "0.975"], {"quantidade": 200, "limite": "1.20", "natural": "1.20",
                                          "meio": "1.00", "acima_do_meio": "40.00"}),
}


def test_w4_mid_and_unit_price_by_hand() -> None:
    """Meio por perna e preço por unidade: compra soma, venda subtrai; natural cruza o livro."""
    for name, seq, clock in (("bova_calmo", 2, "14:00:02"), ("bova_vencida", 3, "14:00:20"),
                             ("bova_adverso", 2, "14:00:02")):
        data = bova(name, seq, clock)
        mids = [leg["cotacao"]["meio"] for leg in data["pernas"]]  # type: ignore[attr-defined]
        assert (mids, data["preco_unidade"], data["preco_unidade_indisponivel"]) == (
            *UNIT[name], None)
    apart = json.loads(ticket_view(official("calmo", 1), "T1", at("14:00:02")).model_dump_json())
    assert apart["preco_unidade"] == {"quantidade": 10, "limite": "-0.50", "natural": "-0.43",
                                      "meio": "-0.515", "acima_do_meio": "0.15"}
    closing = ticket_view(official("rapido", 2), "T1", at("14:00:02")).preco_unidade
    assert closing is not None and closing.acima_do_meio == D("-0.15")
    half = [(1, "14:00:00", "A", "0.95", 50, "1.00", 50, "CONTINUOUS"), CALM[1]]
    one = ticket_view(custom(half, [("A", "BUY", 1, "1.00")], net="1.00", gross="1.00",
                             pairs=[]), "T1", at("14:00:01"))
    assert json.loads(one.model_dump_json())["preco_unidade"] == {
        "quantidade": 1, "limite": "1.00", "natural": "1.00", "meio": "0.975",
        "acima_do_meio": "0.025"}
    auction = ticket_view(official("leilao", 1), "T1", at("14:00:02"))
    assert auction.avanco.situacao.value == "BLOQUEADA" and auction.preco_unidade is not None


def test_w5_unit_price_unavailable_is_said_in_words() -> None:
    """Sem as duas pontas em toda perna, ou com quantidades diferentes, não há preço."""
    ratio = custom(CALM, [("A", "BUY", 3, "1.00"), ("B", "SELL", 1, "2.00")], net="1.00",
                   gross="5.00")
    empty = custom([(1, "14:00:00", "A", "0.95", 50, None, 0, "CONTINUOUS"), CALM[1]],
                   CREDIT, net="-5.00", gross="25.00")
    missing = custom(CALM[:1], CREDIT, net="-5.00", gross="25.00", open_seq=1)
    for session, clock, reason, mids in (
            (ratio, "14:00:01", "quantidades diferentes por perna", ["0.985", "1.50"]),
            (empty, "14:00:01", "cotação incompleta", [None, "1.50"]),
            (missing, "14:00:00", "cotação incompleta", ["0.985", None])):
        data = json.loads(ticket_view(session, "T1", at(clock)).model_dump_json())
        assert (data["preco_unidade"], data["preco_unidade_indisponivel"]) == (None, reason)
        assert [leg["cotacao"] and leg["cotacao"]["meio"] for leg in data["pernas"]] == mids


def test_w6_breakevens_curve_and_final_slope() -> None:
    """Equilíbrios ao centavo, quebras da curva nos strikes e inclinação depois do último."""
    expected = {
        "bova_calmo": (["152.10"], [("0.00", "-210.00"), ("150.00", "-210.00"),
                                    ("155.00", "290.00")]),
        "bova_vencida": (["148.00"], [("0.00", "-600.00"), ("145.00", "-600.00"),
                                      ("150.00", "400.00")]),
        "bova_adverso": (["156.20"], [("0.00", "-240.00"), ("155.00", "-240.00"),
                                      ("160.00", "760.00")]),
    }
    for name, seq, clock in (("bova_calmo", 2, "14:00:02"), ("bova_vencida", 3, "14:00:20"),
                             ("bova_adverso", 2, "14:00:02")):
        expiry = bova(name, seq, clock)["risco"]["vencimento"]  # type: ignore[index]
        assert (expiry["equilibrios"], [(p["preco"], p["resultado"]) for p in expiry["curva"]],
                expiry["inclinacao_final"]) == (*expected[name], "0.00")
    ratio = ticket_view(custom(CALM, [("A", "BUY", 3, "1.00"), ("B", "SELL", 1, "2.00")],
                               net="1.00", gross="5.00"), "T1", at("14:00:01"))
    third = json.loads(ratio.model_dump_json())["risco"]["vencimento"]
    assert (third["equilibrios"], third["inclinacao_final"], third["ganho_ilimitado"]) == (
        ["10.33"], "2.00", True)
    assert [(p["preco"], p["resultado"]) for p in third["curva"]] == [
        ("0.00", "-1.00"), ("10.00", "-1.00"), ("11.00", "2.00")]


def test_w7_new_fields_ignore_the_callers_decimal_context() -> None:
    """Meio, preço por unidade, equilíbrios e curva saem iguais sob precisão reduzida."""
    # O contexto privado é criado ao importar view. Isole esse instante do pytest.
    probe = """
from decimal import Context, DefaultContext, Inexact, Rounded, localcontext
DefaultContext.traps[Inexact] = DefaultContext.traps[Rounded] = True
with localcontext(Context(prec=28, traps=[])):
    from tests.unit.derivatives.ticket.test_view import bova
    import json
    print(json.dumps(bova("bova_vencida", 3, "14:00:20")))
"""
    run = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == bova("bova_vencida", 3, "14:00:20")
    for name, seq, clock in (("bova_calmo", 2, "14:00:02"), ("bova_vencida", 3, "14:00:20"),
                             ("bova_adverso", 2, "14:00:02")):
        plain = bova(name, seq, clock)
        for trap in (True, False):
            with localcontext(Context(prec=3)) as context:
                context.traps[InvalidOperation] = trap
                assert bova(name, seq, clock) == plain
    wide = [(1, "14:00:00", "A", "1234.55", 50, "1234.57", 50, "CONTINUOUS"),
            (2, "14:00:01", "B", "0.01", 50, "0.03", 50, "CONTINUOUS")]
    session = custom(wide, [("A", "BUY", 10, "1234.57"), ("B", "SELL", 10, "0.01")],
                     net="12345.60", gross="12345.80",
                     holdings=[("A", "1234.56", 0), ("B", "2345.67", 0)])
    plain_view = ticket_view(session, "T1", at("14:00:01")).model_dump_json()
    with localcontext(Context(prec=3)) as context:
        context.traps[InvalidOperation] = True
        assert ticket_view(session, "T1", at("14:00:01")).model_dump_json() == plain_view
    lone = custom(wide, [("A", "BUY", 10, "1234.57")], net="12345.70", gross="12345.70",
                  holdings=[("A", "1234.56", 0), ("B", "2345.67", 0)], pairs=[])
    with localcontext(Context(prec=3)) as context:
        context.traps[InvalidOperation] = False
        tail = ticket_view(lone, "T1", at("14:00:01")).risco.vencimento
    assert tail is not None and str(tail.inclinacao_final) == "10.00"
    data = json.loads(plain_view)
    assert data["preco_unidade"] == {"quantidade": 10, "limite": "1234.56",
                                     "natural": "1234.56", "meio": "1234.54",
                                     "acima_do_meio": "0.20"}
    assert data["risco"]["vencimento"]["equilibrios"] == []
    assert data["risco"]["vencimento"]["curva"][-1] == {"preco": "2345.67",
                                                         "resultado": "-1234.50"}


def test_w8_unit_price_refuses_a_contract_multiplier() -> None:
    """Com multiplicador diferente de 1 não há preço por unidade nem distância em reais."""
    data = json.loads(ticket_view(custom(CALM, CREDIT, net="-5.00", gross="25.00", multiplier=100),
                                  "T1", at("14:00:01")).model_dump_json())
    assert (data["preco_unidade"], data["preco_unidade_indisponivel"]) == (
        None, "multiplicador diferente de 1")
    ratio = custom(CALM, [("A", "BUY", 3, "1.00"), ("B", "SELL", 1, "2.00")], net="1.00",
                   gross="5.00", multiplier=100)
    assert ticket_view(ratio, "T1", at("14:00:01")).preco_unidade_indisponivel == (
        "quantidades diferentes por perna")
    plain = ticket_view(custom(CALM, CREDIT, net="-5.00", gross="25.00"), "T1", at("14:00:01"))
    assert plain.preco_unidade is not None and plain.preco_unidade_indisponivel is None
    two = [("A", "BUY", 10, "1.00"), ("B", "BUY", 10, "1.50")]
    for mixed in ({"A": 100}, {"B": 100}):
        view = ticket_view(custom(CALM, two, net="25.00", gross="25.00", pairs=[],
                                  multipliers=mixed), "T1", at("14:00:01"))
        assert (view.preco_unidade, view.preco_unidade_indisponivel) == (
            None, "multiplicador diferente de 1"), mixed


@pytest.mark.parametrize("paid,expected", [("1.01", "11.00"), ("1.02", "11.02")])
def test_w9_breakeven_on_the_half_cent_rounds_to_even(paid: str, expected: str) -> None:
    """Equilíbrio em 11,005 sai 11,00 e em 11,015 sai 11,02: meio centavo vai para o par."""
    quotes: list[Quote] = [(1, "14:00:00", "A", "0.95", 50, paid, 50, "CONTINUOUS"),
                           (2, "14:00:01", "B", "0.01", 50, "1.55", 50, "CONTINUOUS")]
    session = custom(quotes, [("A", "BUY", 2, paid), ("B", "SELL", 1, "0.01")],
                     net=str(2 * D(paid) - D("0.01")), gross=str(2 * D(paid) + D("0.01")),
                     holdings=[("A", "10", 0), ("B", "12", 0)])
    data = json.loads(ticket_view(session, "T1", at("14:00:01")).model_dump_json())
    assert data["risco"]["vencimento"]["equilibrios"] == [expected]
