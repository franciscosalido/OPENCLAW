"""Tela estática da boleta: só formata a visão; não calcula, não decide, não lê o motor."""
from datetime import datetime
from decimal import MAX_EMAX, MAX_PREC, MIN_EMIN, ROUND_HALF_EVEN, Context, Decimal
from html import escape

from backend.derivatives.ticket.screen_draw import curve, ruler
from backend.derivatives.ticket.view import (
    Advance, ExpiryView, GuardView, LegView, Nature, TicketView, UnitPriceView,
)

_CENT = Decimal("0.01")
_EXACT = Context(prec=MAX_PREC, Emin=MIN_EMIN, Emax=MAX_EMAX, capitals=1,
                 rounding=ROUND_HALF_EVEN, clamp=0, flags=[], traps=[])
_MAX_ADJUSTED = 15
LEVEL_LABELS_PT = {"OK": "Sem aviso", "CAUTION": "Cautela", "BLOCKED": "Bloqueado"}
PHASE_LABELS_PT = {"CONTINUOUS": "Contínuo", "AUCTION": "Leilão", "SUSPENDED": "Suspenso"}
KIND_LABELS_PT = {"CALL": "Call", "PUT": "Put"}
STYLE_LABELS_PT = {"AMERICAN": ("🇺🇸", "Americana"), "EUROPEAN": ("🇪🇺", "Europeia")}
DESTINATIONS_PT = {"SIMULATED": ("Simulador local", "D0 · nenhuma ordem sai desta máquina")}
STALE = "cotação vencida"
ABSENT = "—"
_STYLE = (
    "body{font:15px/1.45 system-ui,sans-serif;color:#1a1d21;background:#f5f6f4;"
    "margin:1.2rem auto;max-width:92rem;padding:0 1.2rem;font-variant-numeric:tabular-nums}"
    "h1{font-size:1.4rem;margin:0}h2{font-size:.95rem;margin:0 0 .5rem}"
    ".aviso{margin:0 0 1rem;padding:.4rem .7rem;border-left:4px solid #1a1d21;"
    "background:#fff;font-weight:700}"
    ".topo{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem}"
    ".topo>div:first-child{flex:1;min-width:0}"
    ".meta{display:flex;flex-wrap:wrap;gap:.2rem 1.4rem;margin:.4rem 0 1rem;padding:0;"
    "color:#5e6670;font-size:.87rem}.meta dt,.meta dd{display:inline;margin:0}"
    ".meta dd{color:#1a1d21;font-weight:600}"
    ".destino{display:grid;padding:.5rem .9rem;border:2px dashed #5e6670;background:#fff;"
    "min-width:15rem}.destino strong{font-size:1.05rem}.destino span{font-size:.8rem;color:#5e6670}"
    ".veredito{padding:.9rem 1.1rem;margin:0 0 1.1rem;background:#fff;"
    "border:1px solid #b9c0c6;border-left:8px solid #1a1d21}"
    ".veredito p{margin:0}.avanco{font-size:1.35rem;font-weight:700}"
    ".painel{display:grid;grid-template-columns:repeat(auto-fit,minmax(22rem,1fr));gap:1.1rem;"
    "margin:0 0 1rem}.painel>div,.rolagem{background:#fff;border:1px solid #dce0e3}"
    ".painel>div{padding:.8rem 1rem}.rolagem{overflow-x:auto}"
    "svg{display:block;width:100%;height:auto}.trilho,.zero{stroke:#b9c0c6;stroke-width:2}"
    ".marco{stroke:#1a1d21;stroke-width:2}.linha{fill:none;stroke:#1a1d21;stroke-width:2}"
    ".eq{stroke:#5e6670;stroke-dasharray:3 3}.t{font-size:11px;fill:#5e6670}"
    ".v{font-size:13px;font-weight:700;fill:#1a1d21}.v.neg{fill:#b42318}"
    "table{border-collapse:collapse;width:100%;font-size:.9rem}"
    "caption{text-align:left;padding:.5rem .7rem;color:#5e6670;border-bottom:1px solid #dce0e3}"
    "caption strong{color:#1a1d21}th,td{padding:.42rem .6rem;border-bottom:1px solid #dce0e3;"
    "text-align:left;white-space:nowrap}th{font-size:.8rem;color:#5e6670}"
    ".num{text-align:right}.quebra{white-space:normal;min-width:12rem}"
    ".lado{display:inline-block;min-width:4rem;text-align:center;padding:.1rem .5rem;"
    "font-weight:700;border-radius:3px}.compra{color:#156c45;background:#e2f2e9}"
    ".venda{color:#a8231a;background:#fbe6e3}.mod{font-size:1.1rem}"
    ".neg{color:#b42318}.alerta{background:#ffee8a}.cautela{background:#ffd9a3}"
    ".resumo{display:grid;grid-template-columns:repeat(auto-fit,minmax(19rem,1fr));"
    "gap:0 2.5rem;margin:1.2rem 0 0}"
    ".resumo dl{display:grid;grid-template-columns:1fr auto;margin:0 0 .9rem;"
    "border-top:1px solid #dce0e3}.resumo dt,.resumo dd{margin:0;padding:.38rem 0;"
    "border-bottom:1px solid #dce0e3}.resumo dd{text-align:right;font-weight:600}"
    ".nota,small{color:#5e6670;font-size:.82rem}.nota{margin:.4rem 0 0}"
)


def num(value: Decimal) -> str:
    """Número pt-BR exato, com ao menos duas casas; fora da escala, o texto do motor."""
    if value.is_zero():
        return "0,00"
    sign = "-" if value.is_signed() else ""
    magnitude = value.copy_abs()
    if value.adjusted() > _MAX_ADJUSTED:
        return sign + _EXACT.to_sci_string(magnitude)
    exponent = magnitude.as_tuple().exponent
    if isinstance(exponent, int) and exponent > -2:
        magnitude = magnitude.quantize(_CENT, context=_EXACT)
    whole, fraction = format(magnitude, "f").split(".")
    return f"{sign}{int(whole):,}".replace(",", ".") + "," + fraction


def brl(value: Decimal) -> str:
    """Reais em pt-BR com sinal; fora da escala exibível, o texto decimal do motor."""
    if value.is_zero():
        return "R$ 0,00"
    sign = "-" if value.is_signed() else ""
    magnitude = value.copy_abs()
    if value.adjusted() > _MAX_ADJUSTED:
        return f"{sign}R$ {_EXACT.to_sci_string(magnitude)}"
    return f"{sign}R$ {num(magnitude.quantize(_CENT, context=_EXACT))}"


def clock(value: datetime) -> str:
    """Dia e hora UTC, como a visão guarda."""
    return value.strftime("%d/%m/%Y %H:%M:%S UTC")


def seconds(value: float) -> str:
    """Idade em segundos com uma casa e vírgula decimal."""
    return f"{value:.1f}".replace(".", ",") + " s"


def _tag(tag: str, field: str, text: str, classes: str = "") -> str:
    attr = f' class="{classes}"' if classes else ""
    return f'<{tag} data-campo="{field}"{attr}>{escape(text)}</{tag}>'


def _cell(field: str, text: str, classes: str = "") -> str:
    return _tag("td", field, text, classes)


def _item(field: str, label: str, text: str, classes: str = "") -> str:
    return f"<dt>{escape(label)}</dt>" + _tag("dd", field, text, classes)


def _guard_text(guard: GuardView) -> str:
    label = LEVEL_LABELS_PT[guard.nivel]
    return label if not guard.motivos else f"{label}: {', '.join(guard.motivos)}"


def _guard_class(guard: GuardView) -> str:
    return {"OK": "", "CAUTION": "cautela", "BLOCKED": "alerta"}[guard.nivel]


def _side(price: Decimal | None, size: int) -> str:
    return ABSENT if price is None else f"{num(price)} × {size}"


def _leg_row(index: int, leg: LegView) -> str:
    prefix, quote, mark = f"pernas.{index}", leg.cotacao, _guard_class(leg.guarda)
    side = "compra" if leg.lado == "BUY" else "venda"
    flag, style = STYLE_LABELS_PT.get(leg.modalidade or "", (ABSENT, "não informada"))
    cells = [f'<td><span data-campo="{prefix}.lado" class="lado {side}">'
             f"{escape(leg.lado_rotulo)}</span></td>",
             _cell(f"{prefix}.quantidade", str(leg.quantidade), "num"),
             _cell(f"{prefix}.serie", leg.serie),
             _cell(f"{prefix}.tipo", f"{KIND_LABELS_PT[leg.tipo]} {leg.ativo}"),
             f'<td><span data-campo="{prefix}.modalidade" class="mod" title="{style}" '
             f'aria-label="{style}">{flag}</span></td>',
             _cell(f"{prefix}.strike", num(leg.strike), "num"),
             _cell(f"{prefix}.vencimento", leg.vencimento.strftime("%d/%m/%Y")),
             _cell(f"{prefix}.preco_limite", num(leg.preco_limite), "num")]
    if quote is None:
        cells.append(f'<td data-campo="{prefix}.cotacao" class="alerta" colspan="7">'
                     "sem cotação</td>")
    else:
        stale = mark if STALE in leg.guarda.motivos else ""
        cells += [_cell(f"{prefix}.cotacao.compra", _side(quote.compra, quote.compra_qtd), "num"),
                  _cell(f"{prefix}.cotacao.venda", _side(quote.venda, quote.venda_qtd), "num"),
                  _cell(f"{prefix}.cotacao.meio",
                        ABSENT if quote.meio is None else num(quote.meio), "num"),
                  _cell(f"{prefix}.cotacao.data", quote.instante.strftime("%d/%m/%Y")),
                  _cell(f"{prefix}.cotacao.hora", quote.instante.strftime("%H:%M:%S")),
                  _cell(f"{prefix}.cotacao.idade_s", seconds(quote.idade_s),
                        f"num {stale}".strip()),
                  _cell(f"{prefix}.cotacao.fase", PHASE_LABELS_PT[quote.fase])]
    cells.append(_cell(f"{prefix}.guarda", _guard_text(leg.guarda), f"quebra {mark}".strip()))
    return "<tr>" + "".join(cells) + "</tr>"


def _unit_panel(unit: UnitPriceView | None, reason: str | None) -> str:
    if unit is None:
        return _tag("p", "preco_unidade", f"indisponível: {reason}", "cautela")
    marks = [("Meio", unit.meio, num(unit.meio)), ("Limite", unit.limite, num(unit.limite)),
             ("Natural", unit.natural, num(unit.natural))]
    gap = unit.acima_do_meio
    where = ("no meio" if gap.is_zero() else
             f"{brl(gap.copy_abs())} {'pior' if gap > 0 else 'melhor'} que o meio")
    return (ruler(marks, "; ".join(f"{name} {shown}" for name, _, shown in marks))
            + '<dl class="meta">'
            + "".join(_item(f"preco_unidade.{name.lower()}", name, shown)
                      for name, _, shown in marks)
            + _item("preco_unidade.acima_do_meio", f"Limite nas {unit.quantidade} unidades", where)
            + '</dl><p class="nota">Positivo é débito por unidade; negativo é crédito. '
            "Natural: compra no ask e venda no bid. À direita é pior para você.</p>")


def _extreme(value: Decimal | None, unlimited: bool) -> tuple[str, str]:
    if value is None:
        return ("ilimitado" if unlimited else ABSENT), ""
    return brl(value), ("neg" if value < 0 else "")


def _expiry_panel(expiry: ExpiryView | None, reason: str | None) -> str:
    if expiry is None:
        return _tag("p", "risco.curva", f"indisponível: {reason}", "cautela")
    label = "; ".join(f"ativo em {num(p.preco)}: {brl(p.resultado)}" for p in expiry.curva)
    return curve([(p.preco, p.resultado, num(p.preco), brl(p.resultado)) for p in expiry.curva],
                 expiry.inclinacao_final, [(v, num(v)) for v in expiry.equilibrios], label)


def _risk_items(view: TicketView) -> str:
    risk = view.risco
    first = _item("risco.exposicao_montagem", "Desembolso se só a compra executar",
                  brl(risk.exposicao_montagem))
    if risk.vencimento is None:
        return first + _item("risco.vencimento", "Resultado no vencimento",
                             f"indisponível: {risk.vencimento_indisponivel}", "cautela")
    worst, worst_class = _extreme(risk.vencimento.pior_resultado, risk.vencimento.perda_ilimitada)
    best, best_class = _extreme(risk.vencimento.melhor_resultado,
                                risk.vencimento.ganho_ilimitado)
    even = ", ".join(num(v) for v in risk.vencimento.equilibrios) or "não há"
    return (first
            + _item("risco.vencimento.pior_resultado", "Pior resultado no vencimento",
                    worst, worst_class)
            + _item("risco.vencimento.melhor_resultado", "Melhor resultado no vencimento",
                    best, best_class)
            + _item("risco.vencimento.equilibrios", "Ponto de equilíbrio (preço do ativo)", even))


def render_ticket(view: TicketView) -> str:
    """Documento HTML autocontido da boleta, sem script, rede nem recurso externo."""
    cost, advance = view.custo, view.avanco
    net = {Nature.DEBIT: "Paga no máximo ", Nature.CREDIT: "Recebe no mínimo ",
           Nature.ZERO: "Líquido zero: "}[cost.natureza] + brl(cost.liquido_assinado.copy_abs())
    if advance.situacao is Advance.CAN_CONFIRM:
        status, status_class = "Pode confirmar", "avanco"
    elif advance.situacao is Advance.BLOCKED:
        status, status_class = f"Não avança: {advance.motivo}", "avanco alerta"
    else:
        status, status_class = f"Não se aplica: {view.rotulo}", "avanco"
    place, place_note = DESTINATIONS_PT[view.ambiente]
    legs = "; ".join(f"{leg.lado_rotulo} {leg.serie}: {_guard_text(leg.guarda)}"
                     for leg in view.pernas)
    head = "<tr>" + "".join(
        f'<th class="num">{h[1:]}</th>' if h.startswith(">") else f"<th>{h}</th>" for h in (
            "Lado", ">Qtd", "Ticker", "Tipo", "Mod", ">Strike", "Venc.", ">Limite", ">Bid × qtd",
            ">Ask × qtd", ">Meio", "Data", "Hora", ">Idade", "Fase", "Guarda da perna")) + "</tr>"
    rows = "".join(_leg_row(i, leg) for i, leg in enumerate(view.pernas))
    title = f"Boleta {view.boleta} · {view.rotulo}"
    return "".join((
        '<!DOCTYPE html>\n<html lang="pt-BR"><head><meta charset="utf-8">',
        '<meta http-equiv="Content-Security-Policy" ',
        "content=\"default-src 'none'; style-src 'unsafe-inline'\">",
        f"<title>{escape(title)}</title><style>{_STYLE}</style></head><body>",
        _tag("p", "aviso", view.aviso, "aviso"),
        f'<div class="topo"><div><h1>{escape(title)}</h1><dl class="meta">',
        _item("boleta", "Boleta", view.boleta),
        _item("rotulo", "Estado", view.rotulo + (" · pausada" if view.pausada else "")),
        _item("versao", "Versão", str(view.versao)),
        _item("resumo", "Resumo da versão", view.resumo[:12]),
        _item("conta", "Conta", view.conta),
        _item("prazo_envio", "Prazo de envio", clock(view.prazo_envio)),
        _item("validade_ordens", "Validade das ordens", clock(view.validade_ordens)),
        '</dl></div><div class="destino"><span>Destino</span>',
        _tag("strong", "ambiente", place), f"<span>{escape(place_note)}</span></div></div>",
        '<div class="veredito"><h2>Pode confirmar agora?</h2>',
        _tag("p", "avanco", status, status_class),
        "<p>Mercado para esta boleta: ",
        _tag("span", "mercado", _guard_text(view.mercado), _guard_class(view.mercado)),
        "</p>", _tag("p", "veredito.pernas", legs, "nota"), "</div>",
        '<div class="painel"><div><h2>Preço da estrutura, por unidade</h2>',
        _unit_panel(view.preco_unidade, view.preco_unidade_indisponivel),
        "</div><div><h2>Resultado no vencimento, aos preços-limite</h2>",
        _expiry_panel(view.risco.vencimento, view.risco.vencimento_indisponivel),
        '</div></div><div class="rolagem"><table><caption>Cotações da foto ',
        _tag("strong", "foto_cotacao", view.foto_cotacao), ", vistas em ",
        _tag("strong", "instante", clock(view.instante)), ". Limite de idade da guarda: ",
        _tag("strong", "limite_idade_s", seconds(view.limite_idade_s)), ".</caption>",
        f"{head}{rows}</table></div>",
        '<div class="resumo"><div><h2>Custo</h2><dl>',
        _item("custo.liquido_assinado", "Líquido", net),
        _item("custo.bruto_teto", "Teto bruto", brl(cost.bruto_teto)),
        "</dl></div><div><h2>Risco</h2><dl>", _risk_items(view), "</dl></div></div>",
        "<p><small>Preços por unidade na tabela e na régua; reais no Custo e no Risco. ",
        "Tela gerada do replay. Não envia, não altera e não cancela ordem.",
        "</small></p></body></html>\n"))
