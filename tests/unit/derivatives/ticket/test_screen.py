"""Tela estática da boleta: cada campo vem da visão, com formato e ausência literais."""
import ast
import json
from datetime import datetime
import re
from decimal import Context, Decimal as D, InvalidOperation, localcontext
from html.parser import HTMLParser
from pathlib import Path

import pytest

from backend.derivatives.ticket.screen import DESTINATIONS_PT, brl, num, render_ticket, seconds
from backend.derivatives.ticket.view import TicketView, ticket_view
from scripts.derivatives_ticket_screen import main
from tests.unit.derivatives.ticket.test_session import FIXTURES
from tests.unit.derivatives.ticket.test_view import CALM, CREDIT, at, custom, official

ROOT = Path(__file__).resolve().parents[4]
GABARITO = FIXTURES / "bova.gabarito.json"


class Fields(HTMLParser):
    """Lê o texto e as classes de cada elemento marcado com data-campo."""

    def __init__(self) -> None:
        super().__init__()
        self.text: dict[str, str] = {}
        self.classes: dict[str, set[str]] = {}
        self.tags: list[str] = []
        self.policies: list[str | None] = []
        self._open: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        if tag == "meta" and dict(attrs).get("http-equiv") == "Content-Security-Policy":
            self.policies.append(dict(attrs).get("content"))
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
    """Desfaz o formato de reais ou de número da tela."""
    sign = -1 if text.startswith("-") else 1
    return sign * D(text.lstrip("-").removeprefix("R$ ").replace(".", "").replace(",", "."))


def shapes(page: str, css: str) -> list[str]:
    """Coordenadas dos elementos SVG de uma classe, na ordem do documento."""
    return [" ".join(re.findall(r'(?:x1|x2|points)="([^"]*)"', tag))
            for tag in re.findall(r"<(?:line|polyline)[^>]*>", page) if f'class="{css}"' in tag]


SCREENS = {
    "bova_calmo": [
        "Compra 100 BOVAA1500 Call BOVA11 150,00 a 4,20; "
        "Venda 100 BOVAA1550 Call BOVA11 155,00 a 2,10",
        "Paga no máximo R$ 210,00; teto bruto R$ 630,00",
        "desembolso R$ 420,00; pior resultado -R$ 210,00",
        "2,0 s e 1,0 s; foto bova-calmo-2",
        "Sem aviso",
        "Pode confirmar",
    ],
    "bova_vencida": [
        "Compra 200 BOVAM1450 Put BOVA11 145,00 a 1,90; "
        "Venda 200 BOVAM1500 Put BOVA11 150,00 a 3,90",
        "Recebe no mínimo R$ 400,00; teto bruto R$ 1.160,00",
        "desembolso R$ 380,00; pior resultado -R$ 600,00",
        "20,0 s e 1,0 s; foto bova-vencida-2",
        "Cautela: cotação antiga",
        "Pode confirmar",
    ],
    "bova_adverso": [
        "Compra 200 BOVAA1550 Call BOVA11 155,00 a 2,15; "
        "Venda 200 BOVAA1600 Call BOVA11 160,00 a 0,95",
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
                    "risco.vencimento.pior_resultado", "risco.vencimento.melhor_resultado",
                    "ambiente", "veredito.pernas", "limite_idade_s", "preco_unidade.meio",
                    "preco_unidade.limite", "preco_unidade.natural",
                    "preco_unidade.acima_do_meio", "risco.vencimento.equilibrios"}
        for i, leg in enumerate(view.pernas):
            expected |= {f"pernas.{i}.{k}" for k in (
                "lado", "quantidade", "serie", "tipo", "strike", "vencimento", "preco_limite",
                "cotacao.compra", "cotacao.venda", "cotacao.fase", "cotacao.idade_s", "guarda",
                "modalidade", "cotacao.meio", "cotacao.data", "cotacao.hora")}
            assert leg.cotacao is not None and leg.cotacao.meio is not None
            assert from_brl(text[f"pernas.{i}.cotacao.meio"]) == leg.cotacao.meio
            assert (text[f"pernas.{i}.cotacao.data"], text[f"pernas.{i}.cotacao.hora"]) == (
                leg.cotacao.instante.strftime("%d/%m/%Y"),
                leg.cotacao.instante.strftime("%H:%M:%S"))
            assert leg.cotacao is not None and leg.cotacao.compra is not None
            assert leg.cotacao.venda is not None
            assert (text[f"pernas.{i}.lado"], text[f"pernas.{i}.serie"]) == (
                leg.lado_rotulo, leg.serie)
            assert int(text[f"pernas.{i}.quantidade"]) == leg.quantidade
            assert from_brl(text[f"pernas.{i}.strike"]) == leg.strike
            assert from_brl(text[f"pernas.{i}.preco_limite"]) == leg.preco_limite
            assert text[f"pernas.{i}.vencimento"] == leg.vencimento.strftime("%d/%m/%Y")
            assert text[f"pernas.{i}.cotacao.compra"] == (
                f"{num(leg.cotacao.compra)} × {leg.cotacao.compra_qtd}")
            assert text[f"pernas.{i}.cotacao.venda"] == (
                f"{num(leg.cotacao.venda)} × {leg.cotacao.venda_qtd}")
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
        unit = view.preco_unidade
        assert unit is not None
        assert [from_brl(text[f"preco_unidade.{k}"]) for k in ("meio", "limite", "natural")] == [
            unit.meio, unit.limite, unit.natural]
        assert [from_brl(v) for v in text["risco.vencimento.equilibrios"].split(", ")] == list(
            view.risco.vencimento.equilibrios)
        assert text["limite_idade_s"] == seconds(view.limite_idade_s)


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
    view = view_at("bova_vencida", 1, 3, "2026-11-25T14:00:20+00:00")
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
        "—", "0,95 × 50")
    assert (page.text["pernas.0.cotacao.meio"], page.text["preco_unidade"]) == (
        "—", "indisponível: cotação incompleta")
    assert "cautela" in page.classes["preco_unidade"]
    assert not any(k.startswith("preco_unidade.") for k in page.text)
    halted = custom([CALM[0], (2, "14:00:01", "B", "1.45", 50, "1.55", 50, "SUSPENDED")],
                    CREDIT, net="-5.00", gross="25.00")
    page = read(render_ticket(ticket_view(
        halted, "T1", datetime.fromisoformat("2026-11-23T14:00:01+00:00"))))
    assert (page.text["pernas.0.cotacao.fase"], page.text["pernas.1.cotacao.fase"]) == (
        "Contínuo", "Suspenso")
    closing = read(render_ticket(view_at("rapido", 2, 2, "2026-11-23T14:00:02+00:00")))
    assert closing.text["risco.vencimento"] == "indisponível: posição inicial não nula"
    assert closing.text["risco.curva"] == "indisponível: posição inicial não nula"
    assert "cautela" in closing.classes["risco.curva"]
    assert "risco.vencimento.equilibrios" not in closing.text
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
    parsed = read(page)
    assert parsed.policies == ["default-src 'none'; style-src 'unsafe-inline'"]
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
    assert parsed.text["veredito.pernas"].startswith(f"Compra {hostile}: Cautela: {hostile}")
    assert "svg" in parsed.tags and "strong" in parsed.tags
    marks = ['<script>alert("x")</script>', "<b>", '"><img src=x onerror=1>', "&lt;b&gt;",
             "</td></tr></table>", "<svg onload=1>", "'><i>", "]]><b>"]
    safe = set(read(page).tags)
    for mark in marks:
        data = json.loads(view.model_dump_json())
        data.update(boleta=mark, resumo=mark, preco_unidade=None,
                    preco_unidade_indisponivel=mark)
        data["risco"].update(vencimento=None, vencimento_indisponivel=mark)
        for leg in data["pernas"]:
            leg["lado_rotulo"] = mark
        parsed = read(render_ticket(TicketView.model_validate_json(json.dumps(data))))
        assert set(parsed.tags) <= safe, mark
        assert parsed.text["boleta"] == mark and parsed.text["resumo"] == mark[:12]
        assert parsed.text["pernas.0.lado"] == mark and parsed.text["pernas.1.lado"] == mark
        assert parsed.text["preco_unidade"] == f"indisponível: {mark}"
        assert parsed.text["risco.curva"] == f"indisponível: {mark}"
        assert parsed.text["risco.vencimento"] == f"indisponível: {mark}"
        assert parsed.text["veredito.pernas"].startswith(f"{mark} BOVAA1550: ")
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
    assert modules == {"datetime", "decimal", "html", "backend.derivatives.ticket.view",
                       "backend.derivatives.ticket.screen_draw"}
    tree = ast.parse((ROOT / "backend/derivatives/ticket/screen_draw.py").read_text("utf-8"))
    drawn = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert drawn == {"collections.abc", "decimal", "fractions", "html"}
    assert not any(isinstance(node, ast.Import) for node in ast.walk(tree))


SHOT = ["--replay", str(FIXTURES / "bova_vencida.replay.json"),
        "--roteiro", str(FIXTURES / "bova_vencida.roteiro.json"),
        "--passos", "1", "--avanca-ate", "3", "--boleta", "T1",
        "--instante", "2026-11-25T14:00:20Z"]


def test_s9_script_writes_the_same_bytes_and_never_overwrites(tmp_path: Path) -> None:
    """O script grava exatamente a tela da visão e recusa destino existente."""
    out = tmp_path / "tela.html"
    assert main([*SHOT, "--out", str(out)]) == 0
    expected = render_ticket(view_at("bova_vencida", 1, 3, "2026-11-25T14:00:20+00:00"))
    assert out.read_bytes() == expected.encode("utf-8")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["tela.html"]
    out.write_text("intocado", encoding="utf-8")
    assert main([*SHOT, "--out", str(out)]) == 2
    assert out.read_text(encoding="utf-8") == "intocado"


@pytest.mark.parametrize("option,value", [
    ("--passos", "0"), ("--passos", "3"), ("--boleta", "T9"),
    ("--instante", "2026-11-25T14:00:20"), ("--instante", "2026-11-25T14:00:18Z"),
    ("--instante", "2026-11-25T14:00:23Z"), ("--instante", "ontem"),
    ("--avanca-ate", "1"),
])
def test_s10_script_refuses_bad_points_without_writing(option: str, value: str,
                                                       tmp_path: Path) -> None:
    """Passo, boleta, instante ou avanço inválido devolve 2 e não cria arquivo."""
    args = list(SHOT)
    args[args.index(option) + 1] = value
    assert main([*args, "--out", str(tmp_path / "tela.html")]) == 2
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("steps,seq,clock", [("3", "6", "14:00:25"), ("-1", "4", "14:00:22")])
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
                 "--passos", "2", "--avanca-ate", "6", "--boleta", "T1",
                 "--instante", "2026-11-25T14:00:25Z", "--out", str(out)]) == 0
    text = read(out.read_text(encoding="utf-8")).text
    assert (text["rotulo"], text["avanco"]) == ("Concluída", "Não se aplica: Concluída")


BOVA = [("bova_calmo", 2, "14:00:02"), ("bova_vencida", 3, "14:00:20"),
        ("bova_adverso", 2, "14:00:02")]


def bova_page(name: str, seq: int, clock: str) -> str:
    """Tela da foto do gabarito."""
    return render_ticket(view_at(name, 1, seq, f"2026-11-25T{clock}+00:00"))


def test_s12_destination_verdict_and_the_photo_beside_the_ages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Destino por extenso; o veredito repete cada perna; foto, instante e limite na tabela."""
    legs = {
        "bova_calmo": "Compra BOVAA1500: Sem aviso; Venda BOVAA1550: Sem aviso",
        "bova_vencida": "Compra BOVAM1450: Cautela: cotação antiga; "
                        "Venda BOVAM1500: Sem aviso",
        "bova_adverso": "Compra BOVAA1550: Cautela: spread aberto, pouca profundidade; "
                        "Venda BOVAA1600: Bloqueado: leilão",
    }
    for name, seq, clock in BOVA:
        raw = bova_page(name, seq, clock)
        page = read(raw)
        assert page.text["ambiente"] == "Simulador local"
        assert "D0 · nenhuma ordem sai desta máquina" in raw
        assert page.text["veredito.pernas"] == legs[name]
        assert page.text["limite_idade_s"] == "15,0 s"
        caption = raw[raw.index("<caption>"):raw.index("</caption>")]
        assert all(f'data-campo="{k}"' in caption
                   for k in ("foto_cotacao", "instante", "limite_idade_s"))
        assert raw.index("<caption>") < raw.index('data-campo="pernas.0.cotacao.idade_s"')
    # Um destino sentinela distingue a leitura da visão do único destino real do D0.
    view = view_at("bova_calmo", 1, 2, "2026-11-25T14:00:02+00:00")
    monkeypatch.setitem(DESTINATIONS_PT, "TESTE", ("Destino de teste", "Nota de teste"))
    raw = render_ticket(view.model_copy(update={"ambiente": "TESTE"}))
    assert read(raw).text["ambiente"] == "Destino de teste"
    assert "Nota de teste" in raw
    order = re.findall(r'data-campo="pernas\.0\.([^"]*)"', bova_page(*BOVA[0]))
    assert order == ["lado", "quantidade", "serie", "tipo", "modalidade", "strike", "vencimento",
                     "preco_limite", "cotacao.compra", "cotacao.venda", "cotacao.meio",
                     "cotacao.data", "cotacao.hora", "cotacao.idade_s", "cotacao.fase", "guarda"]
    head = re.findall(r"<th[^>]*>([^<]*)</th>", bova_page(*BOVA[0]))
    assert head == ["Lado", "Qtd", "Ticker", "Tipo", "Mod", "Strike", "Venc.", "Limite",
                    "Bid × qtd", "Ask × qtd", "Meio", "Data", "Hora", "Idade", "Fase",
                    "Guarda da perna"]


def test_s13_age_is_marked_only_by_the_guard_and_with_its_level() -> None:
    """A idade só ganha marca com «cotação antiga» na guarda da perna, no nível da guarda."""
    stale = read(bova_page(*BOVA[1]))
    assert stale.classes["pernas.0.cotacao.idade_s"] == {"num", "cautela"}
    assert stale.classes["pernas.0.guarda"] == {"quebra", "cautela"}
    assert stale.classes["pernas.1.cotacao.idade_s"] == {"num"}
    adverse = read(bova_page(*BOVA[2]))
    assert adverse.classes["pernas.0.cotacao.idade_s"] == {"num"}
    assert adverse.classes["pernas.1.cotacao.idade_s"] == {"num"}
    data = json.loads(view_at("bova_vencida", 1, 3, "2026-11-25T14:00:20+00:00").model_dump_json())
    data["pernas"][0]["guarda"]["nivel"] = "BLOCKED"
    barred = read(render_ticket(TicketView.model_validate_json(json.dumps(data))))
    assert barred.classes["pernas.0.cotacao.idade_s"] == {"num", "alerta"}
    data["pernas"][0]["guarda"] = {"nivel": "OK", "motivos": []}
    data["limite_idade_s"] = 0.5
    quiet = read(render_ticket(TicketView.model_validate_json(json.dumps(data))))
    assert quiet.classes["pernas.0.cotacao.idade_s"] == {"num"}
    assert (quiet.text["limite_idade_s"], quiet.text["pernas.0.cotacao.idade_s"]) == (
        "0,5 s", "20,0 s")


def test_s14_side_label_style_flag_and_number_format() -> None:
    """Etiqueta de lado, bandeira com texto e número exato com ao menos duas casas."""
    adverse = read(bova_page(*BOVA[2]))
    assert adverse.classes["pernas.0.lado"] == {"lado", "compra"}
    assert adverse.classes["pernas.1.lado"] == {"lado", "venda"}
    raw = bova_page(*BOVA[2])
    assert 'title="Europeia" aria-label="Europeia">🇪🇺</span>' in raw
    assert 'title="Americana" aria-label="Americana">🇺🇸</span>' in raw
    assert (adverse.text["pernas.0.cotacao.meio"], adverse.text["pernas.1.cotacao.meio"]) == (
        "1,975", "0,975")
    plain = read(render_ticket(view_at("calmo", 1, 2, "2026-11-23T14:00:02+00:00")))
    assert plain.text["pernas.0.modalidade"] == "—"
    cases = [("0", "0,00"), ("1.975", "1,975"), ("2.1", "2,10"), ("-0.515", "-0,515"),
             ("1234.5", "1.234,50"), ("1E+2", "100,00"), ("15E-1", "1,50"), ("-0.00", "0,00"),
             ("0.025", "0,025"), ("1234567.125", "1.234.567,125"), ("1E+16", "1E+16"),
             ("-1E+16", "-1E+16"), ("1E+15", "1.000.000.000.000.000,00")]
    for trap in (None, True, False):
        with localcontext(Context(prec=3) if trap is not None else None) as context:
            if trap is not None:
                context.traps[InvalidOperation] = trap
            for raw_value, shown in cases:
                assert num(D(raw_value)) == shown, raw_value


def test_s15_unit_price_in_words_and_on_the_ruler() -> None:
    """Meio, limite e natural por unidade; a distância ao meio dita em reais; régua exata."""
    expected = {
        "bova_calmo": (["2,05", "2,10", "2,10"], "R$ 5,00 pior que o meio",
                       ["60.0 60.0", "540.0 540.0"], ["Meio", "Limite = Natural"]),
        "bova_vencida": (["-2,05", "-2,00", "-2,00"], "R$ 10,00 pior que o meio",
                         ["60.0 60.0", "540.0 540.0"], ["Meio", "Limite = Natural"]),
        "bova_adverso": (["1,00", "1,20", "1,20"], "R$ 40,00 pior que o meio",
                         ["60.0 60.0", "540.0 540.0"], ["Meio", "Limite = Natural"]),
    }
    for name, seq, clock in BOVA:
        raw = bova_page(name, seq, clock)
        text = read(raw).text
        prices, gap, marks, names = expected[name]
        assert [text[f"preco_unidade.{k}"] for k in ("meio", "limite", "natural")] == prices
        assert text["preco_unidade.acima_do_meio"] == gap
        ruler = raw[raw.index("<svg"):raw.index("</svg>")]
        assert shapes(ruler, "marco") == marks
        assert re.findall(r'class="t" text-anchor="middle">([^<]*)<', ruler) == names
    three = render_ticket(view_at("calmo", 1, 2, "2026-11-23T14:00:02+00:00"))
    assert shapes(three[:three.index("</svg>")], "marco") == [
        "60.0 60.0", "144.7 144.7", "540.0 540.0"]
    assert 'aria-label="Meio -0,515; Limite -0,50; Natural -0,43"' in three
    better = read(render_ticket(view_at("rapido", 2, 2, "2026-11-23T14:00:02+00:00")))
    assert better.text["preco_unidade.acima_do_meio"] == "R$ 0,15 melhor que o meio"
    data = json.loads(view_at("bova_calmo", 1, 2, "2026-11-25T14:00:02+00:00").model_dump_json())
    data["preco_unidade"].update(limite="2.05", natural="2.05", acima_do_meio="0.00")
    level = render_ticket(TicketView.model_validate_json(json.dumps(data)))
    assert read(level).text["preco_unidade.acima_do_meio"] == "no meio"
    assert shapes(level[:level.index("</svg>")], "marco") == ["300.0 300.0"]
    ratio = custom(CALM, [("A", "BUY", 3, "1.00"), ("B", "SELL", 1, "2.00")], net="1.00",
                   gross="5.00")
    page = read(render_ticket(ticket_view(ratio, "T1", at("14:00:01"))))
    assert page.text["preco_unidade"] == "indisponível: quantidades diferentes por perna"


def test_s16_curve_is_drawn_from_the_view_points() -> None:
    """A curva liga as quebras da visão; a janela vai de um intervalo antes a um depois."""
    expected = {
        "bova_calmo": ("60.0,104.0 220.0,104.0 380.0,24.0 540.0,24.0", "70.4", "287.2",
                       ["150,00", "-R$ 210,00", "155,00", "R$ 290,00", "152,10"]),
        "bova_vencida": ("60.0,104.0 220.0,104.0 380.0,24.0 540.0,24.0", "56.0", "316.0",
                         ["145,00", "-R$ 600,00", "150,00", "R$ 400,00", "148,00"]),
        "bova_adverso": ("60.0,104.0 220.0,104.0 380.0,24.0 540.0,24.0", "84.8", "258.4",
                         ["155,00", "-R$ 240,00", "160,00", "R$ 760,00", "156,20"]),
    }
    for name, seq, clock in BOVA:
        raw = bova_page(name, seq, clock)
        chart = raw[raw.index("</svg>"):]
        chart = chart[chart.index("<svg"):chart.index("</svg>", 6)]
        line, zero, even, labels = expected[name]
        assert shapes(chart, "linha") == [line]
        assert re.findall(r'y1="([^"]*)"[^>]*class="zero"', chart) == [zero]
        assert shapes(chart, "eq") == [f"{even} {even}"]
        assert re.findall(r">([^<]+)</text>", chart) == labels
        assert chart.count('class="v neg"') == 1
    single = custom(CALM, [("A", "BUY", 10, "1.00")], net="10.00", gross="10.00", pairs=[])
    raw = render_ticket(ticket_view(single, "T1", at("14:00:01")))
    assert shapes(raw, "linha") == ["60.0,104.0 300.0,104.0 540.0,24.0"]
    assert shapes(raw, "eq") == ["540.0 540.0"]
    ratio = custom(CALM, [("A", "BUY", 3, "1.00"), ("B", "SELL", 1, "2.00")], net="1.00",
                   gross="5.00")
    raw = render_ticket(ticket_view(ratio, "T1", at("14:00:01")))
    assert shapes(raw, "linha") == ["60.0,104.0 220.0,104.0 380.0,56.0 540.0,24.0"]
    assert shapes(raw, "eq") == ["272.8 272.8"]
    assert read(raw).text["risco.vencimento.equilibrios"] == "10,33"
    raw = render_ticket(view_at("calmo", 1, 2, "2026-11-23T14:00:02+00:00"))
    assert read(raw).text["risco.vencimento.equilibrios"] == "não há"
    assert shapes(raw, "linha") == ["60.0,77.3 220.0,77.3 380.0,24.0 540.0,24.0"]
    assert re.findall(r'y1="([^"]*)"[^>]*class="zero"', raw) == ["104.0"]
    assert shapes(raw, "eq") == []
    far = custom(CALM, [("A", "BUY", 10, "5.00")], net="50.00", gross="50.00", pairs=[])
    raw = render_ticket(ticket_view(far, "T1", at("14:00:01")))
    assert read(raw).text["risco.vencimento.equilibrios"] == "15,00"
    assert shapes(raw, "eq") == [] and shapes(raw, "linha") == [
        "60.0,104.0 300.0,104.0 540.0,88.0"]


def test_s17_drawings_ignore_the_callers_decimal_context() -> None:
    """As três telas saem com os mesmos bytes sob precisão reduzida, com e sem armadilha."""
    for name, seq, clock in BOVA:
        view = view_at(name, 1, seq, f"2026-11-25T{clock}+00:00")
        plain = render_ticket(view)
        for trap in (True, False):
            with localcontext(Context(prec=3)) as context:
                context.traps[InvalidOperation] = trap
                assert render_ticket(view) == plain
