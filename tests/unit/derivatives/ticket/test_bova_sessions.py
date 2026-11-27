"""Roteiros sintéticos de trava de BOVA11 e gabarito da prova de uso do M1."""
import json
from datetime import date, datetime
from decimal import Context, Decimal as D, InvalidOperation, localcontext
from hashlib import sha256
from pathlib import Path

import pytest

from backend.derivatives.ticket.replay import QuoteEvent, load_replay
from backend.derivatives.ticket.view import ticket_view
from scripts.derivatives_ticket_replay import _act, _Open, _read, main
from tests.unit.derivatives.ticket.test_session import FIXTURES
from tests.unit.derivatives.ticket.test_view import REFUSALS, answers, official

SESSIONS = ("bova_calmo", "bova_vencida", "bova_adverso")
GABARITO = FIXTURES / "bova.gabarito.json"
GABARITO_SHA = "c0c3c72fa53a8237bc4cda0a7c9559def9a64244ea831fa8178af47d63abf82a"
FILES_SHA = {
    "bova_calmo.replay.json":
        "ff7494c11c1adc7b859c43768a4834f48ff12cda0013c49eb7a11bfc8d540cfa",
    "bova_calmo.roteiro.json":
        "6d956042f507f8efb0fdd501cedf2da1316f175923dc8b93b6a55d446d43db4b",
    "bova_vencida.replay.json":
        "c98ce2f12aff7b7efc67885734bf47f2b208f7139236293703fa5433eebf5bdf",
    "bova_vencida.roteiro.json":
        "d7ab707054788f64aff68fdc6b0f6041bce03f5d92339abd9f879805f1d1185c",
    "bova_adverso.replay.json":
        "70409a55ca91e06d3de77fb4cc37e0593aa5162a2708cd6296b12642fc5cbd48",
    "bova_adverso.roteiro.json":
        "bbf79b930c2591a822f12850ccba2f3166a46c4309e17c14b8b83b6017232606",
}
QUESTIONS = [
    "O que a boleta compra e o que vende, em que quantidade e a que preço-limite?",
    "Quanto paga ou recebe no líquido, e qual é o teto bruto?",
    "Quanto desembolsa se só a compra executar, e qual é o pior resultado no vencimento?",
    "Qual é a idade da cotação de cada perna, e de que foto veio a proposta?",
    "Como está o mercado para esta boleta?",
    "A boleta pode ser confirmada agora? Se não, por quê?",
]
ANSWERS = {
    "bova_calmo": [
        "Compra 100 BOVAA1500 (CALL 150.00) a 4.20; Venda 100 BOVAA1550 (CALL 155.00) a 2.10",
        "paga no máximo 210.00; bruto até 630.00",
        "desembolso se só a compra executar 420.00; pior resultado no vencimento -210.00",
        "BOVAA1500 2.0 s, BOVAA1550 1.0 s; foto bova-calmo-2",
        "OK: sem aviso",
        "pode confirmar",
    ],
    "bova_vencida": [
        "Compra 200 BOVAM1450 (PUT 145.00) a 1.90; Venda 200 BOVAM1500 (PUT 150.00) a 3.90",
        "recebe no mínimo 400.00; bruto até 1160.00",
        "desembolso se só a compra executar 380.00; pior resultado no vencimento -600.00",
        "BOVAM1450 20.0 s, BOVAM1500 1.0 s; foto bova-vencida-2",
        "CAUTION: cotação antiga",
        "pode confirmar",
    ],
    "bova_adverso": [
        "Compra 200 BOVAA1550 (CALL 155.00) a 2.15; Venda 200 BOVAA1600 (CALL 160.00) a 0.95",
        "paga no máximo 240.00; bruto até 620.00",
        "desembolso se só a compra executar 430.00; pior resultado no vencimento -240.00",
        "BOVAA1550 2.0 s, BOVAA1600 1.0 s; foto bova-adverso-2",
        "BLOCKED: spread aberto, pouca profundidade, leilão",
        "não avança: spread aberto, pouca profundidade, leilão",
    ],
}


def at(text: str) -> datetime:
    """Instante UTC do pregão sintético das fitas de BOVA11."""
    return datetime.fromisoformat(f"2026-11-25T{text}+00:00")


def shot(name: str, steps: int, seq: int, clock: str) -> dict[str, object]:
    """JSON da visão da T1 depois dos passos e do avanço indicados."""
    session = official(name, steps)
    session.advance_to(seq)
    data: dict[str, object] = json.loads(ticket_view(session, "T1", at(clock)).model_dump_json())
    return data


def series_code(underlying: str, kind: str, expiry: date, strike: D) -> str:
    """Código no formato B3: raiz, letra do mês (A-L call, M-X put) e strike vezes dez."""
    base = ord("A") if kind == "CALL" else ord("M")
    return f"{underlying[:4]}{chr(base + expiry.month - 1)}{int(strike * 10)}"


@pytest.mark.parametrize("name", SESSIONS)
def test_b1_fixtures_are_coherent_b3_like_synthetic_data(name: str) -> None:
    """Série, vencimento, lote, passo de preço e pregão coerentes com o contrato da B3."""
    script = _read(FIXTURES / f"{name}.roteiro.json")
    replay = load_replay(FIXTURES / f"{name}.replay.json")
    (position,) = script.positions
    opening = script.steps[0]
    assert isinstance(opening, _Open)
    assert {leg.symbol for leg in opening.draft.legs} == {h.symbol for h in position.holdings}
    for row in position.holdings:
        assert row.symbol == series_code(row.underlying, row.kind, row.expiry, row.strike)
        assert (row.underlying, row.multiplier, row.balance) == ("BOVA11", 1, 0)
        assert row.expiry.weekday() == 4 and 15 <= row.expiry.day <= 21
    for leg in opening.draft.legs:
        assert leg.lot_size == 100 and leg.quantity % 100 == 0
        assert leg.limit_price == leg.limit_price.quantize(D("0.01"))
    assert len({leg.quantity for leg in opening.draft.legs}) == 1
    assert opening.draft.environment.value == "SIMULATED"
    assert opening.draft.order_validity == replay.session_close
    assert not any(event.gap_before for event in replay.events)
    for event in replay.events:
        assert isinstance(event, QuoteEvent) and event.ts.date() == date(2026, 11, 25)
        assert event.bid is not None and event.ask is not None and event.bid < event.ask
        assert event.bid_size % 100 == 0 and event.ask_size % 100 == 0


def test_b2_files_and_answer_key_are_pinned() -> None:
    """Fitas, roteiros e gabarito têm bytes fixos; o gabarito é o deste arquivo."""
    for filename, digest in FILES_SHA.items():
        assert sha256((FIXTURES / filename).read_bytes()).hexdigest() == digest, filename
    raw = GABARITO.read_bytes()
    assert sha256(raw).hexdigest() == GABARITO_SHA
    def unique(items: list[tuple[str, object]]) -> dict[str, object]:
        assert len(dict(items)) == len(items), "chave duplicada no gabarito"
        return dict(items)

    key = json.loads(raw, object_pairs_hook=unique)
    assert list(key) == ["formato", "natureza", "aviso", "perguntas", "fotos"]
    assert (key["formato"], key["natureza"]) == (1, "SINTETICO")
    assert key["perguntas"] == QUESTIONS
    assert [(f["sessao"], f["passos"], f["avanca_ate"], f["boleta"], f["instante"])
            for f in key["fotos"]] == [
        ("bova_calmo", 1, 2, "T1", "2026-11-25T14:00:02Z"),
        ("bova_vencida", 1, 3, "T1", "2026-11-25T14:00:20Z"),
        ("bova_adverso", 1, 2, "T1", "2026-11-25T14:00:02Z")]
    assert {f["sessao"]: f["respostas"] for f in key["fotos"]} == ANSWERS
    assert sum(len(f["respostas"]) for f in key["fotos"]) == 18


def test_b3_view_gives_the_eighteen_answers() -> None:
    """Em cada foto do gabarito, o leitor independente devolve as seis respostas."""
    key = json.loads(GABARITO.read_bytes())
    for foto in key["fotos"]:
        session = official(foto["sessao"], foto["passos"])
        session.advance_to(foto["avanca_ate"])
        view = ticket_view(session, foto["boleta"], datetime.fromisoformat(foto["instante"]))
        assert answers(json.loads(view.model_dump_json())) == foto["respostas"]


def test_b4_risk_and_cost_numbers_by_hand() -> None:
    """Custo e os dois riscos conferem com a conta à mão de cada trava."""
    expected = {
        "bova_calmo": ("210.00", "DEBITO", "630.00", "420.00", "-210.00", "290.00"),
        "bova_vencida": ("-400.00", "CREDITO", "1160.00", "380.00", "-600.00", "400.00"),
        "bova_adverso": ("240.00", "DEBITO", "620.00", "430.00", "-240.00", "760.00"),
    }
    for name, numbers in expected.items():
        data = shot(name, 1, 2, "14:00:02")
        cost: dict[str, str] = data["custo"]  # type: ignore[assignment]
        risk: dict[str, object] = data["risco"]  # type: ignore[assignment]
        expiry: dict[str, object] = risk["vencimento"]  # type: ignore[assignment]
        assert (cost["liquido_assinado"], cost["natureza"], cost["bruto_teto"],
                risk["exposicao_montagem"], expiry["pior_resultado"],
                expiry["melhor_resultado"]) == numbers
        assert risk["vencimento_indisponivel"] is None
        assert (expiry["perda_ilimitada"], expiry["ganho_ilimitado"]) == (False, False)


def test_b5_view_predicts_every_scripted_confirmation() -> None:
    """Antes de cada confirmação, a visão diz o que o motor responde, com o mesmo texto."""
    seen = []
    for name in SESSIONS:
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
        ("bova_calmo", 2, "PODE_CONFIRMAR", None),
        ("bova_vencida", 2, "PODE_CONFIRMAR", None),
        ("bova_adverso", 2, "BLOQUEADA", "spread aberto, pouca profundidade, leilão"),
    ]


def test_b6_guards_per_leg_at_each_photo_and_after_the_market_changes() -> None:
    """A guarda diz qual perna tem o problema, e muda quando a fita muda."""
    def guards(name: str, steps: int, seq: int, clock: str) -> tuple[object, ...]:
        data = shot(name, steps, seq, clock)
        legs: list[dict[str, dict[str, object]]] = data["pernas"]  # type: ignore[assignment]
        advance: dict[str, object] = data["avanco"]  # type: ignore[assignment]
        market: dict[str, object] = data["mercado"]  # type: ignore[assignment]
        return (advance["situacao"], market["nivel"],
                [(leg["guarda"]["nivel"], leg["guarda"]["motivos"], leg["cotacao"]["idade_s"])
                 for leg in legs])

    assert guards("bova_calmo", 1, 2, "14:00:02") == (
        "PODE_CONFIRMAR", "OK", [("OK", [], 2.0), ("OK", [], 1.0)])
    assert guards("bova_vencida", 1, 3, "14:00:20") == (
        "PODE_CONFIRMAR", "CAUTION", [("CAUTION", ["cotação antiga"], 20.0), ("OK", [], 1.0)])
    assert guards("bova_vencida", 1, 4, "14:00:22") == (
        "PODE_CONFIRMAR", "OK", [("OK", [], 0.0), ("OK", [], 3.0)])
    assert guards("bova_adverso", 1, 2, "14:00:02") == (
        "BLOQUEADA", "BLOCKED", [("CAUTION", ["spread aberto", "pouca profundidade"], 2.0),
                                  ("BLOCKED", ["leilão"], 1.0)])
    assert guards("bova_adverso", 2, 3, "14:00:04") == (
        "PODE_CONFIRMAR", "CAUTION",
        [("CAUTION", ["spread aberto", "pouca profundidade"], 4.0), ("OK", [], 0.0)])


RUNS = {
    "bova_calmo": ("COMPLETED", "Concluída", [100, 100], ["4.2000", "2.1000"],
                   ("630.00", "630.00", "630.00"), 8,
                   "de7b45d3c7ed06b4c527a9cbc1036de57ad7a9d9126ce06740c353f0bf0da67e", []),
    "bova_vencida": ("COMPLETED", "Concluída", [200, 200], ["1.9000", "3.9000"],
                     ("1160.00", "1160.00", "1160.00"), 8,
                   "88908b798f830069c5c72169edc46dd00bf73a8bab349f2ccf939bcb170e1665", []),
    "bova_adverso": ("DRAFT", "Proposta", [0, 0], [None, None],
                     ("620.00", "0.00", "620.00"), 1,
                   "43c254c9e7975fa62d8e2c86a3b72a60ff25d5a8d8e69ada1e3d5edbd8d7137d",
                     [{"passo": 2, "acao": "confirm", "boleta": "T1", "erro": "EngineRefusal"}]),
}


@pytest.mark.parametrize("name", SESSIONS)
def test_b7_script_runs_each_session_to_a_pinned_receipt(name: str, tmp_path: Path) -> None:
    """O script oficial executa o roteiro inteiro; estado, execução e âncora são literais."""
    out = tmp_path / "out"
    assert main(["--replay", str(FIXTURES / f"{name}.replay.json"),
                 "--roteiro", str(FIXTURES / f"{name}.roteiro.json"), "--out", str(out)]) == 0
    summary = json.loads((out / "resumo.json").read_bytes())
    ticket = summary["boletas"]["T1"]
    state, label, executed, average, gross, events, anchor, refusals = RUNS[name]
    assert (ticket["estado"], ticket["rotulo"]) == (state, label)
    assert [leg["executado"] for leg in ticket["pernas"]] == executed
    assert [leg["preco_medio"] for leg in ticket["pernas"]] == average
    assert all(leg["vivo"] == 0 for leg in ticket["pernas"])
    assert tuple(ticket["bruto"][k] for k in ("assinado", "executado", "projetado")) == gross
    assert (ticket["recibo_eventos"], ticket["recibo_hash"]) == (events, anchor)
    assert summary["recusas"] == refusals and summary["contas_bloqueadas"] == []
    assert sorted(p.name for p in out.iterdir()) == ["recibo_T1.jsonl", "resumo.json"]
    lines = (out / "recibo_T1.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == events and json.loads(lines[-1])["hash"] == anchor


def test_b8_answers_do_not_depend_on_the_callers_decimal_context() -> None:
    """As dezoito respostas saem iguais sob precisão reduzida, com e sem armadilha."""
    key = json.loads(GABARITO.read_bytes())
    for trap in (True, False):
        with localcontext(Context(prec=3)) as context:
            context.traps[InvalidOperation] = trap
            for foto in key["fotos"]:
                data = shot(foto["sessao"], foto["passos"], foto["avanca_ate"],
                            foto["instante"][11:19])
                assert answers(data) == foto["respostas"]
