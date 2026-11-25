"""Tela estática da boleta: só formata a visão; não calcula, não decide, não lê o motor."""
from datetime import datetime
from decimal import MAX_EMAX, MAX_PREC, MIN_EMIN, Context, Decimal
from html import escape

from backend.derivatives.ticket.view import (
    Advance, GuardView, LegView, Nature, QuoteView, TicketView,
)

_CENT = Decimal("0.01")
_EXACT = Context(prec=MAX_PREC, Emin=MIN_EMIN, Emax=MAX_EMAX)
_MAX_ADJUSTED = 15
LEVEL_LABELS_PT = {"OK": "Sem aviso", "CAUTION": "Cautela", "BLOCKED": "Bloqueado"}
PHASE_LABELS_PT = {"CONTINUOUS": "Contínuo", "AUCTION": "Leilão", "SUSPENDED": "Suspenso"}
KIND_LABELS_PT = {"CALL": "Call", "PUT": "Put"}
ABSENT = "—"
_STYLE = (
    "body{font:16px/1.45 system-ui,sans-serif;color:#000;background:#fff;margin:1.5rem auto;"
    "max-width:76rem;padding:0 1rem}h1{font-size:1.3rem;margin:0 0 .3rem}"
    "h2{font-size:1.05rem;margin:1.4rem 0 .4rem}"
    "table{border-collapse:collapse;width:100%;font-size:.9rem}"
    "th,td{border:1px solid #999;padding:.3rem .5rem;text-align:left;vertical-align:top}"
    "th{background:#eee}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}"
    ".neg{color:#b00020}.alerta{background:#fff59d}.cautela{background:#ffe0b2}"
    ".aviso{border:2px solid #000;padding:.4rem .6rem;font-weight:700}"
    ".avanco{font-size:1.2rem;font-weight:700;padding:.5rem .7rem;border:2px solid #000}"
    "dl{display:grid;grid-template-columns:max-content 1fr;gap:.2rem 1rem;margin:0}"
    "dt{font-weight:600}dd{margin:0}small{color:#444}"
)


def brl(value: Decimal) -> str:
    """Reais em pt-BR com sinal; fora da escala exibível, o texto decimal do motor."""
    if value.adjusted() > _MAX_ADJUSTED:
        return f"R$ {value}"
    whole, cents = format(value.copy_abs().quantize(_CENT, context=_EXACT), "f").split(".")
    groups = f"{int(whole):,}".replace(",", ".")
    return f"{'-' if value.is_signed() and value else ''}R$ {groups},{cents}"


def clock(value: datetime) -> str:
    """Dia e hora UTC, como a visão guarda."""
    return value.strftime("%d/%m/%Y %H:%M:%S UTC")


def seconds(value: float) -> str:
    """Idade em segundos com uma casa e vírgula decimal."""
    return f"{value:.1f}".replace(".", ",") + " s"


def _cell(field: str, text: str, classes: str = "") -> str:
    attr = f' class="{classes}"' if classes else ""
    return f'<td data-campo="{field}"{attr}>{escape(text)}</td>'


def _item(field: str, label: str, text: str, classes: str = "") -> str:
    attr = f' class="{classes}"' if classes else ""
    return f'<dt>{escape(label)}</dt><dd data-campo="{field}"{attr}>{escape(text)}</dd>'


def _guard_text(guard: GuardView) -> str:
    label = LEVEL_LABELS_PT[guard.nivel]
    return label if not guard.motivos else f"{label}: {', '.join(guard.motivos)}"


def _guard_class(guard: GuardView) -> str:
    return {"OK": "", "CAUTION": "cautela", "BLOCKED": "alerta"}[guard.nivel]


def _quote_cells(prefix: str, quote: QuoteView | None) -> str:
    if quote is None:
        return _cell(f"{prefix}.cotacao", "sem cotação", "alerta") + "<td></td>" * 3
    def side(price: Decimal | None, size: int) -> str:
        return ABSENT if price is None else f"{brl(price)} × {size}"
    return (_cell(f"{prefix}.cotacao.compra", side(quote.compra, quote.compra_qtd), "num")
            + _cell(f"{prefix}.cotacao.venda", side(quote.venda, quote.venda_qtd), "num")
            + _cell(f"{prefix}.cotacao.fase", PHASE_LABELS_PT[quote.fase])
            + _cell(f"{prefix}.cotacao.idade_s", seconds(quote.idade_s), "num"))


def _leg_row(index: int, leg: LegView) -> str:
    prefix = f"pernas.{index}"
    return ("<tr>" + _cell(f"{prefix}.lado", leg.lado_rotulo)
            + _cell(f"{prefix}.quantidade", str(leg.quantidade), "num")
            + _cell(f"{prefix}.serie", leg.serie)
            + _cell(f"{prefix}.tipo", f"{KIND_LABELS_PT[leg.tipo]} {leg.ativo}")
            + _cell(f"{prefix}.strike", brl(leg.strike), "num")
            + _cell(f"{prefix}.vencimento", leg.vencimento.strftime("%d/%m/%Y"))
            + _cell(f"{prefix}.preco_limite", brl(leg.preco_limite), "num")
            + _quote_cells(prefix, leg.cotacao)
            + _cell(f"{prefix}.guarda", _guard_text(leg.guarda), _guard_class(leg.guarda))
            + "</tr>")


def _extreme(value: Decimal | None, unlimited: bool) -> tuple[str, str]:
    if value is None:
        return ("ilimitado" if unlimited else ABSENT), ""
    return brl(value), ("neg" if value < 0 else "")


def render_ticket(view: TicketView) -> str:
    """Documento HTML autocontido da boleta, sem script, rede nem recurso externo."""
    cost, risk, advance = view.custo, view.risco, view.avanco
    net = {Nature.DEBIT: "Paga no máximo ", Nature.CREDIT: "Recebe no mínimo ",
           Nature.ZERO: "Líquido zero: "}[cost.natureza] + brl(cost.liquido_assinado.copy_abs())
    if advance.situacao is Advance.CAN_CONFIRM:
        status, status_class = "Pode confirmar", "avanco"
    elif advance.situacao is Advance.BLOCKED:
        status, status_class = f"Não avança: {advance.motivo}", "avanco alerta"
    else:
        status, status_class = f"Não se aplica: {view.rotulo}", "avanco"
    if risk.vencimento is None:
        expiry = _item("risco.vencimento", "Resultado no vencimento",
                       f"indisponível: {risk.vencimento_indisponivel}", "cautela")
    else:
        worst, worst_class = _extreme(risk.vencimento.pior_resultado,
                                      risk.vencimento.perda_ilimitada)
        best, best_class = _extreme(risk.vencimento.melhor_resultado,
                                    risk.vencimento.ganho_ilimitado)
        expiry = (_item("risco.vencimento.pior_resultado", "Pior resultado no vencimento",
                        worst, worst_class)
                  + _item("risco.vencimento.melhor_resultado", "Melhor resultado no vencimento",
                          best, best_class))
    head = ("<tr>" + "".join(f"<th>{escape(h)}</th>" for h in (
        "Lado", "Qtd", "Série", "Tipo", "Strike", "Vencimento", "Preço-limite",
        "Compra × qtd", "Venda × qtd", "Fase", "Idade", "Guarda da perna")) + "</tr>")
    rows = "".join(_leg_row(i, leg) for i, leg in enumerate(view.pernas))
    title = f"Boleta {view.boleta} · {view.rotulo}"
    return "".join((
        '<!DOCTYPE html>\n<html lang="pt-BR"><head><meta charset="utf-8">',
        '<meta http-equiv="Content-Security-Policy" ',
        "content=\"default-src 'none'; style-src 'unsafe-inline'\">",
        f"<title>{escape(title)}</title><style>{_STYLE}</style></head><body>",
        f'<p class="aviso" data-campo="aviso">{escape(view.aviso)}</p>',
        f"<h1>{escape(title)}</h1><dl>",
        _item("boleta", "Boleta", view.boleta), _item("conta", "Conta", view.conta),
        _item("instante", "Instante da tela", clock(view.instante)),
        _item("rotulo", "Estado", view.rotulo + (" · pausada" if view.pausada else "")),
        _item("versao", "Versão", str(view.versao)),
        _item("resumo", "Resumo da versão", view.resumo[:12]),
        _item("foto_cotacao", "Foto da proposta", view.foto_cotacao),
        _item("prazo_envio", "Prazo de envio", clock(view.prazo_envio)),
        _item("validade_ordens", "Validade das ordens", clock(view.validade_ordens)),
        "</dl><h2>Pode confirmar agora?</h2>",
        f'<p class="{status_class}" data-campo="avanco">{escape(status)}</p>',
        f"<h2>Pernas</h2><table>{head}{rows}</table>",
        "<h2>Custo</h2><dl>", _item("custo.liquido_assinado", "Líquido", net),
        _item("custo.bruto_teto", "Teto bruto", brl(cost.bruto_teto)),
        "</dl><h2>Risco</h2><dl>",
        _item("risco.exposicao_montagem", "Desembolso se só a compra executar",
              brl(risk.exposicao_montagem)), expiry,
        "</dl><h2>Mercado para esta boleta</h2>",
        f'<p data-campo="mercado" class="{_guard_class(view.mercado)}">'
        f"{escape(_guard_text(view.mercado))}</p>",
        "<p><small>Tela gerada do replay. Não envia, não altera e não cancela ordem.",
        "</small></p></body></html>\n"))
