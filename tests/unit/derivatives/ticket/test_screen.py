"""Tela estática da boleta: cada campo vem da visão, com formato e ausência literais."""
import ast
import json
from datetime import datetime
from decimal import Context, Decimal as D, InvalidOperation, localcontext
from html.parser import HTMLParser
from pathlib import Path

import pytest

from backend.derivatives.ticket.screen import brl, render_ticket, seconds
from backend.derivatives.ticket.view import TicketView, ticket_view
from scripts.derivatives_ticket_screen import main
from tests.unit.derivatives.ticket.test_session import FIXTURES
from tests.unit.derivatives.ticket.test_view import CALM, CREDIT, custom, official

ROOT = Path(__file__).resolve().parents[4]
GABARITO = FIXTURES / "bova.gabarito.json"


class Fields(HTMLParser):
    """Lê o texto e as classes de cada elemento marcado com data-campo."""

    def __init__(self) -> None:
        super().__init__()
        self.text: dict[str, str] = {}
        self.classes: dict[str, set[str]] = {}
        self.tags: list[str] = []
        self._open: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        found = dict(attrs)
        field = found.get("data-campo")
        if field is not None:
            assert field not in self.text, field
            self._open = field
            self.text[field] = ""
            self.classes[field] = set((found.get("class") or "").split())

    def handle_endtag(self, tag: str) -> None:
        self._open = None

    def handle_data(self, data: str) -> None:
        if self._open is not None:
            self.text[self._open] += data


def read(page: str) -> Fields:
    """Campos da página; falha se algum data-campo se repetir."""
    parser = Fields()
    parser.feed(page)
    parser.close()
    return parser


def view_at(name: str, steps: int, seq: int, instant: str) -> TicketView:
    """Visão da T1 depois dos passos e do avanço indicados."""
    session = official(name, steps)
    session.advance_to(seq)
    return ticket_view(session, "T1", datetime.fromisoformat(instant))


def from_brl(text: str) -> D:
    """Desfaz o formato de reais da tela."""
    sign = -1 if text.startswith("-") else 1
    return sign * D(text.lstrip("-").removeprefix("R$ ").replace(".", "").replace(",", "."))


SCREENS = {
    "bova_calmo": [
        "Compra 100 BOVAA1500 Call BOVA11 R$ 150,00 a R$ 4,20; "
        "Venda 100 BOVAA1550 Call BOVA11 R$ 155,00 a R$ 2,10",
        "Paga no máximo R$ 210,00; teto bruto R$ 630,00",
        "desembolso R$ 420,00; pior resultado -R$ 210,00",
        "2,0 s e 1,0 s; foto bova-calmo-2",
        "Sem aviso",
        "Pode confirmar",
    ],
    "bova_vencida": [
        "Compra 200 BOVAM1450 Put BOVA11 R$ 145,00 a R$ 1,90; "
        "Venda 200 BOVAM1500 Put BOVA11 R$ 150,00 a R$ 3,90",
        "Recebe no mínimo R$ 400,00; teto bruto R$ 1.160,00",
        "desembolso R$ 380,00; pior resultado -R$ 600,00",
        "10,0 s e 1,0 s; foto bova-vencida-2",
        "Bloqueado: cotação vencida",
        "Não avança: cotação vencida",
    ],
    "bova_adverso": [
        "Compra 200 BOVAA1550 Call BOVA11 R$ 155,00 a R$ 2,15; "
        "Venda 200 BOVAA1600 Call BOVA11 R$ 160,00 a R$ 0,95",
        "Paga no máximo R$ 240,00; teto bruto R$ 620,00",
        "desembolso R$ 430,00; pior resultado -R$ 240,00",
        "2,0 s e 1,0 s; foto bova-adverso-2",
        "Bloqueado: spread aberto, pouca profundidade, leilão",
        "Não avança: spread aberto, pouca profundidade, leilão",
    ],
}


def six(text: dict[str, str]) -> list[str]:
    """As seis respostas da prova de uso, lidas só do texto visível da tela."""
    legs = "; ".join(
        " ".join(text[f"pernas.{i}.{k}"] for k in ("lado", "quantidade", "serie", "tipo",
                                                     "strike"))
        + " a " + text[f"pernas.{i}.preco_limite"] for i in (0, 1))
    return [
        legs,
        f"{text['custo.liquido_assinado']}; teto bruto {text['custo.bruto_teto']}",
        f"desembolso {text['risco.exposicao_montagem']}; "
        f"pior resultado {text['risco.vencimento.pior_resultado']}",
        f"{text['pernas.0.cotacao.idade_s']} e {text['pernas.1.cotacao.idade_s']}; "
        f"foto {text['foto_cotacao']}",
        text["mercado"],
        text["avanco"],
    ]


def test_s1_eighteen_answers_are_on_the_screen() -> None:
    """Nas três fotos do gabarito, o texto visível responde as seis perguntas."""
    key = json.loads(GABARITO.read_bytes())
    assert [foto["sessao"] for foto in key["fotos"]] == list(SCREENS)
    for foto in key["fotos"]:
        view = view_at(foto["sessao"], foto["passos"], foto["avanca_ate"], foto["instante"])
        assert six(read(render_ticket(view)).text) == SCREENS[foto["sessao"]]


def test_s2_every_field_is_the_view_field() -> None:
    """Campo a campo: nada na tela vem de outra fonte, e o dinheiro desfaz para o da visão."""
    shots = [view_at(f["sessao"], f["passos"], f["avanca_ate"], f["instante"])
             for f in json.loads(GABARITO.read_bytes())["fotos"]]
    shots.append(view_at("bova_adverso", 2, 3, "2026-11-25T14:00:04+00:00"))
    for view in shots:
        page = read(render_ticket(view))
        text = page.text
        expected = {"aviso", "boleta", "conta", "instante", "rotulo", "versao", "resumo",
                    "foto_cotacao", "prazo_envio", "validade_ordens", "avanco", "mercado",
                    "custo.liquido_assinado", "custo.bruto_teto", "risco.exposicao_montagem",
                    "risco.vencimento.pior_resultado", "risco.vencimento.melhor_resultado"}
        for i, leg in enumerate(view.pernas):
            expected |= {f"pernas.{i}.{k}" for k in (
                "lado", "quantidade", "serie", "tipo", "strike", "vencimento", "preco_limite",
                "cotacao.compra", "cotacao.venda", "cotacao.fase", "cotacao.idade_s", "guarda")}
            assert leg.cotacao is not None and leg.cotacao.compra is not None
            assert leg.cotacao.venda is not None
            assert (text[f"pernas.{i}.lado"], text[f"pernas.{i}.serie"]) == (
                leg.lado_rotulo, leg.serie)
            assert int(text[f"pernas.{i}.quantidade"]) == leg.quantidade
            assert from_brl(text[f"pernas.{i}.strike"]) == leg.strike
            assert from_brl(text[f"pernas.{i}.preco_limite"]) == leg.preco_limite
            assert text[f"pernas.{i}.vencimento"] == leg.vencimento.strftime("%d/%m/%Y")
            assert text[f"pernas.{i}.cotacao.compra"] == (
                f"{brl(leg.cotacao.compra)} × {leg.cotacao.compra_qtd}")
            assert text[f"pernas.{i}.cotacao.venda"] == (
                f"{brl(leg.cotacao.venda)} × {leg.cotacao.venda_qtd}")
            assert text[f"pernas.{i}.cotacao.idade_s"] == seconds(leg.cotacao.idade_s)
            assert all(m in text[f"pernas.{i}.guarda"] for m in leg.guarda.motivos)
        assert set(text) == expected
        assert (text["aviso"], text["boleta"], text["conta"], text["foto_cotacao"]) == (
            view.aviso, view.boleta, view.conta, view.foto_cotacao)
        assert (text["rotulo"], text["versao"], text["resumo"]) == (
            view.rotulo, str(view.versao), view.resumo[:12])
        assert from_brl(text["custo.bruto_teto"]) == view.custo.bruto_teto
        assert from_brl(text["risco.exposicao_montagem"]) == view.risco.exposicao_montagem
        assert view.risco.vencimento is not None
        assert from_brl(text["risco.vencimento.pior_resultado"]) == (
            view.risco.vencimento.pior_resultado)
        assert from_brl(text["risco.vencimento.melhor_resultado"]) == (
            view.risco.vencimento.melhor_resultado)
        amount = from_brl(text["custo.liquido_assinado"].split(" ", 3)[3])
        assert amount == abs(view.custo.liquido_assinado)
        assert all(m in text["mercado"] for m in view.mercado.motivos)


def test_s3_brl_and_seconds_formats_at_the_edges() -> None:
    """Milhar, sinal, expoente e escala; o contexto decimal de quem chama não interfere."""
    cases = [("0", "R$ 0,00"), ("0.10", "R$ 0,10"), ("210", "R$ 210,00"),
             ("-210.00", "-R$ 210,00"), ("1234567.5", "R$ 1.234.567,50"),
             ("1E+2", "R$ 100,00"), ("15E-1", "R$ 1,50"), ("-0.00", "R$ 0,00"),
             ("999.99", "R$ 999,99"), ("1000", "R$ 1.000,00"),
             ("1E+15", "R$ 1.000.000.000.000.000,00"), ("1E+16", "R$ 1E+16"),
             ("-1E+16", "-R$ 1E+16"), ("0E+16", "R$ 0,00"), ("-0E+16", "R$ 0,00")]
    for trap in (None, True, False):
        with localcontext(Context(prec=3) if trap is not None else None) as context:
            if trap is not None:
                context.traps[InvalidOperation] = trap
            for raw, shown in cases:
                assert brl(D(raw)) == shown, raw
    assert [seconds(v) for v in (0.0, 1.0, 10.0, 4.96, 25186.0, 0.05)] == [
        "0,0 s", "1,0 s", "10,0 s", "5,0 s", "25186,0 s", "0,1 s"]
    view = view_at("bova_vencida", 1, 3, "2026-11-25T14:00:10+00:00")
    plain = render_ticket(view)
    with localcontext(Context(prec=3)) as context:
        context.traps[InvalidOperation] = True
        assert render_ticket(view) == plain


def test_s4_absence_unavailable_and_unlimited_are_said_in_words() -> None:
    """Sem cotação, lado vazio, perfil indisponível e ganho ilimitado nunca viram número."""
    missing = custom(CALM[:1], CREDIT, net="-5.00", gross="25.00", open_seq=1)
    page = read(render_ticket(ticket_view(
        missing, "T1", datetime.fromisoformat("2026-11-23T14:00:00+00:00"))))
    assert page.text["pernas.1.cotacao"] == "sem cotação"
    assert "alerta" in page.classes["pernas.1.cotacao"]
    assert not any(k.startswith("pernas.1.cotacao.") for k in page.text)
    assert page.text["pernas.1.guarda"] == "Bloqueado: sem cotação"
    empty = custom([(1, "14:00:00", "A", "0.95", 50, None, 0, "CONTINUOUS"), CALM[1]],
                   CREDIT, net="-5.00", gross="25.00")
    page = read(render_ticket(ticket_view(
        empty, "T1", datetime.fromisoformat("2026-11-23T14:00:01+00:00"))))
    assert (page.text["pernas.0.cotacao.venda"], page.text["pernas.0.cotacao.compra"]) == (
        "—", "R$ 0,95 × 50")
    halted = custom([CALM[0], (2, "14:00:01", "B", "1.45", 50, "1.55", 50, "SUSPENDED")],
                    CREDIT, net="-5.00", gross="25.00")
    page = read(render_ticket(ticket_view(
        halted, "T1", datetime.fromisoformat("2026-11-23T14:00:01+00:00"))))
    assert (page.text["pernas.0.cotacao.fase"], page.text["pernas.1.cotacao.fase"]) == (
        "Contínuo", "Suspenso")
    closing = read(render_ticket(view_at("rapido", 2, 2, "2026-11-23T14:00:02+00:00")))
    assert closing.text["risco.vencimento"] == "indisponível: posição inicial não nula"
    assert "risco.vencimento.pior_resultado" not in closing.text
    single = custom(CALM, [("A", "BUY", 10, "1.00")], net="10.00", gross="10.00", pairs=[])
    page = read(render_ticket(ticket_view(
        single, "T1", datetime.fromisoformat("2026-11-23T14:00:01+00:00"))))
    assert (page.text["risco.vencimento.pior_resultado"],
            page.text["risco.vencimento.melhor_resultado"]) == ("-R$ 10,00", "ilimitado")


def test_s5_highlight_for_alerts_red_only_for_negative_numbers() -> None:
    """Alerta é marca-texto; vermelho só em número negativo; o resto fica preto."""
    blocked = read(render_ticket(view_at("bova_adverso", 1, 2, "2026-11-25T14:00:02+00:00")))
    assert "alerta" in blocked.classes["avanco"] and "alerta" in blocked.classes["mercado"]
    assert "cautela" in blocked.classes["pernas.0.guarda"]
    assert "alerta" in blocked.classes["pernas.1.guarda"]
    assert "neg" in blocked.classes["risco.vencimento.pior_resultado"]
    assert blocked.text["pernas.1.cotacao.fase"] == "Leilão"
    for field, classes in blocked.classes.items():
        negative = blocked.text[field].startswith("-R$")
        assert ("neg" in classes) == negative, field
    calm = read(render_ticket(view_at("bova_calmo", 1, 2, "2026-11-25T14:00:02+00:00")))
    assert not {"alerta", "cautela"} & set().union(*(
        calm.classes[k] for k in calm.classes if k != "risco.vencimento.pior_resultado"))
    caution = read(render_ticket(view_at("bova_adverso", 2, 3, "2026-11-25T14:00:04+00:00")))
    assert caution.text["avanco"] == "Pode confirmar"
    assert "alerta" not in caution.classes["avanco"]
    assert (caution.text["mercado"], caution.classes["mercado"]) == (
        "Cautela: spread aberto, pouca profundidade", {"cautela"})


def test_s6_states_outside_confirmation_and_pause() -> None:
    """Fora da confirmação a tela diz o estado; a pausa aparece junto do estado."""
    done = read(render_ticket(view_at("calmo", 5, 9, "2026-11-23T21:00:00+00:00")))
    assert done.text["avanco"] == "Não se aplica: Concluída"
    assert "alerta" not in done.classes["avanco"]
    assert done.text["custo.liquido_assinado"] == "Recebe no mínimo R$ 5,00"
    assert done.text["risco.vencimento.pior_resultado"] == "R$ 5,00"
    session = official("bova_calmo", 1)
    session.engine("T1").pause(datetime.fromisoformat("2026-11-25T14:00:02+00:00"))
    paused = read(render_ticket(ticket_view(
        session, "T1", datetime.fromisoformat("2026-11-25T14:00:02+00:00"))))
    assert paused.text["rotulo"] == "Proposta · pausada"
    assert paused.text["avanco"] == "Não avança: boleta pausada"
    flat = custom(CALM, [("A", "BUY", 10, "1.00"), ("B", "SELL", 10, "1.00")],
                  net="0.00", gross="25.00")
    page = read(render_ticket(ticket_view(
        flat, "T1", datetime.fromisoformat("2026-11-23T14:00:01+00:00"))))
    assert page.text["custo.liquido_assinado"] == "Líquido zero: R$ 0,00"


def test_s7_page_is_inert_escaped_and_deterministic() -> None:
    """Sem script, rede ou recurso externo; texto hostil sai escapado; bytes estáveis."""
    calm = view_at("bova_calmo", 1, 2, "2026-11-25T14:00:02+00:00")
    data = json.loads(calm.model_dump_json())
    data["custo"]["bruto_teto"] = "1E+16"
    large = TicketView.model_validate_json(json.dumps(data))
    baseline = render_ticket(large).encode("utf-8")
    with localcontext() as context:
        context.capitals = 0
        assert render_ticket(large).encode("utf-8") == baseline
    view = view_at("bova_adverso", 1, 2, "2026-11-25T14:00:02+00:00")
    page = render_ticket(view)
    assert page == render_ticket(view)
    assert page.startswith('<!DOCTYPE html>\n<html lang="pt-BR">') and page.endswith("\n")
    assert "default-src 'none'; style-src 'unsafe-inline'" in page
    parsed = read(page)
    assert not {"script", "img", "link", "a", "iframe", "form", "input", "button", "object",
                "embed", "base"} & set(parsed.tags)
    assert not any(token in page.lower() for token in ("http:", "https:", "javascript:",
                                                       "url(", "@import", " on"))
    hostile = '<script>alert("x")</script>&<b>'
    data = json.loads(view.model_dump_json())
    data.update(rotulo=hostile, foto_cotacao=hostile, conta=hostile, aviso=hostile)
    data["avanco"]["motivo"] = hostile
    data["mercado"]["motivos"] = [hostile]
    data["pernas"][0]["guarda"]["motivos"] = [hostile]
    data["pernas"][0]["serie"] = hostile
    data["pernas"][0]["ativo"] = hostile
    evil = render_ticket(TicketView.model_validate_json(json.dumps(data)))
    parsed = read(evil)
    assert "script" not in parsed.tags and "b" not in parsed.tags
    assert parsed.text["avanco"] == f"Não avança: {hostile}"
    assert parsed.text["pernas.0.serie"] == hostile and parsed.text["conta"] == hostile
    assert evil.count("<script") == 0 and "&lt;script&gt;" in evil


def test_s8_screen_module_reads_only_the_view() -> None:
    """A tela importa a visão e a biblioteca padrão; nunca motor, sessão, guarda ou preço."""
    tree = ast.parse((ROOT / "backend/derivatives/ticket/screen.py").read_text("utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    assert modules == {"datetime", "decimal", "html", "backend.derivatives.ticket.view"}


SHOT = ["--replay", str(FIXTURES / "bova_vencida.replay.json"),
        "--roteiro", str(FIXTURES / "bova_vencida.roteiro.json"),
        "--passos", "1", "--avanca-ate", "3", "--boleta", "T1",
        "--instante", "2026-11-25T14:00:10Z"]


def test_s9_script_writes_the_same_bytes_and_never_overwrites(tmp_path: Path) -> None:
    """O script grava exatamente a tela da visão e recusa destino existente."""
    out = tmp_path / "tela.html"
    assert main([*SHOT, "--out", str(out)]) == 0
    expected = render_ticket(view_at("bova_vencida", 1, 3, "2026-11-25T14:00:10+00:00"))
    assert out.read_bytes() == expected.encode("utf-8")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["tela.html"]
    out.write_text("intocado", encoding="utf-8")
    assert main([*SHOT, "--out", str(out)]) == 2
    assert out.read_text(encoding="utf-8") == "intocado"


@pytest.mark.parametrize("option,value", [
    ("--passos", "0"), ("--passos", "4"), ("--boleta", "T9"),
    ("--instante", "2026-11-25T14:00:10"), ("--instante", "2026-11-25T14:00:08Z"),
    ("--instante", "2026-11-25T14:00:13Z"), ("--instante", "ontem"),
    ("--avanca-ate", "1"),
])
def test_s10_script_refuses_bad_points_without_writing(option: str, value: str,
                                                       tmp_path: Path) -> None:
    """Passo, boleta, instante ou avanço inválido devolve 2 e não cria arquivo."""
    args = list(SHOT)
    args[args.index(option) + 1] = value
    assert main([*args, "--out", str(tmp_path / "tela.html")]) == 2
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("steps,seq,clock", [("4", "6", "14:00:15"), ("-1", "4", "14:00:13")])
def test_s10b_script_refuses_step_counts_that_slicing_would_accept(
        steps: str, seq: str, clock: str, tmp_path: Path) -> None:
    """Passos além do roteiro ou negativos são recusados, mesmo num ponto válido da fita."""
    args = ["--replay", str(FIXTURES / "bova_vencida.replay.json"),
            "--roteiro", str(FIXTURES / "bova_vencida.roteiro.json"), "--passos", steps,
            "--avanca-ate", seq, "--boleta", "T1", "--instante", f"2026-11-25T{clock}Z"]
    assert main([*args, "--out", str(tmp_path / "tela.html")]) == 2
    assert list(tmp_path.iterdir()) == []


def test_s11_script_plays_confirmations_like_the_official_replay(tmp_path: Path) -> None:
    """Depois de uma confirmação aceita, a tela mostra o estado que o roteiro produz."""
    out = tmp_path / "tela.html"
    assert main(["--replay", str(FIXTURES / "bova_vencida.replay.json"),
                 "--roteiro", str(FIXTURES / "bova_vencida.roteiro.json"),
                 "--passos", "3", "--avanca-ate", "6", "--boleta", "T1",
                 "--instante", "2026-11-25T14:00:15Z", "--out", str(out)]) == 0
    text = read(out.read_text(encoding="utf-8")).text
    assert (text["rotulo"], text["avanco"]) == ("Concluída", "Não se aplica: Concluída")
