"""Visão de leitura da boleta: traduz fatos do motor, sem decidir nem recalcular guardas."""
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final, Literal

from backend.derivatives.pricing.expiry_payoff import ExpiryLeg, PayoffRefusal, expiry_profile
from backend.derivatives.ticket.engine import CONFIRMABLE, Reading
from backend.derivatives.ticket.guards import BookSnapshot, GuardResult
from backend.derivatives.ticket.models import Instant, Money, Preview, Side, _Frozen
from backend.derivatives.ticket.replay import Phase
from backend.derivatives.ticket.session import ReplaySession
from backend.derivatives.ticket.state import TicketState

VIEW_FORMAT: Final = 1
NOTICE = "SIMULADO — dados sintéticos em replay; nenhuma ordem real."
SIDE_LABELS_PT = {Side.BUY: "Compra", Side.SELL: "Venda"}
_CENT = Decimal("0.01")
_MAX_ADJUSTED = 15


class Advance(StrEnum):
    """Situação da confirmação humana neste instante."""

    CAN_CONFIRM = "PODE_CONFIRMAR"
    BLOCKED = "BLOQUEADA"
    NOT_APPLICABLE = "NAO_SE_APLICA"


class Nature(StrEnum):
    """Sentido do líquido assinado."""

    DEBIT = "DEBITO"
    CREDIT = "CREDITO"
    ZERO = "ZERO"


class GuardView(_Frozen):
    """Nível e motivos literais da guarda do motor."""

    nivel: Literal["OK", "CAUTION", "BLOCKED"]
    motivos: tuple[str, ...]


class QuoteView(_Frozen):
    """Última cotação da série e sua idade no instante da visão."""

    compra: Money | None
    compra_qtd: int
    venda: Money | None
    venda_qtd: int
    fase: Phase
    instante: Instant
    idade_s: float


class LegView(_Frozen):
    """Perna assinada, identidade da série na foto, cotação e guarda próprias."""

    serie: str
    lado: Side
    lado_rotulo: str
    quantidade: int
    lote: int
    preco_limite: Money
    ativo: str
    tipo: Literal["CALL", "PUT"]
    strike: Money
    vencimento: date
    cotacao: QuoteView | None
    guarda: GuardView


class CostView(_Frozen):
    """Limites em reais da versão exibida; o líquido conserva o sinal do motor."""

    liquido_assinado: Money
    natureza: Nature
    bruto_teto: Money


class ExpiryView(_Frozen):
    """Extremos com sinal do resultado no vencimento, aos preços-limite da versão."""

    pior_resultado: Money | None
    perda_ilimitada: bool
    melhor_resultado: Money | None
    ganho_ilimitado: bool


class RiskView(_Frozen):
    """Duas grandezas distintas: desembolso da montagem e resultado no vencimento."""

    exposicao_montagem: Money
    vencimento: ExpiryView | None
    vencimento_indisponivel: str | None


class AdvanceView(_Frozen):
    """Situação e recusa literal que a confirmação receberia agora."""

    situacao: Advance
    motivo: str | None


class TicketView(_Frozen):
    """Modelo de tela versionado de uma boleta em replay."""

    formato: Literal[1]
    aviso: str
    boleta: str
    conta: str
    instante: Instant
    estado: TicketState
    rotulo: str
    pausada: bool
    versao: int
    resumo: str
    foto_cotacao: str
    prazo_envio: Instant
    validade_ordens: Instant
    pernas: tuple[LegView, ...]
    custo: CostView
    risco: RiskView
    mercado: GuardView
    avanco: AdvanceView


def _guard(result: GuardResult) -> GuardView:
    return GuardView(nivel=result.level, motivos=result.reasons)


def _quote(snapshot: BookSnapshot | None, now: datetime) -> QuoteView | None:
    if snapshot is None:
        return None
    return QuoteView(compra=snapshot.bid, compra_qtd=snapshot.bid_size, venda=snapshot.ask,
                     venda_qtd=snapshot.ask_size, fase=snapshot.phase, instante=snapshot.ts,
                     idade_s=(now - snapshot.ts).total_seconds())


def _expiry(preview: Preview, reading: Reading) -> tuple[ExpiryView | None, str | None]:
    rows = {row.symbol: row for row in reading.position.holdings}
    held = [rows[leg.symbol] for leg in preview.legs]
    if preview.coverage:
        return None, "cobertura cedida por outra boleta"
    if any(row.balance for row in held):
        return None, "posição inicial não nula"
    if len({(row.underlying, row.expiry) for row in held}) != 1:
        return None, "séries de ativos ou vencimentos diferentes"
    if any(row.multiplier != 1 for row in held):
        return None, "multiplicador diferente de 1"
    amounts = [v for leg, row in zip(preview.legs, held, strict=True)
               for v in (row.strike, leg.limit_price)]
    if any(v.adjusted() > _MAX_ADJUSTED for v in amounts):
        return None, "valores fora da escala do perfil"
    try:
        profile = expiry_profile([
            ExpiryLeg(row.kind, leg.side.value, row.strike.quantize(_CENT), leg.quantity,
                      leg.limit_price.quantize(_CENT))
            for leg, row in zip(preview.legs, held, strict=True)], max_legs=len(held))
    except PayoffRefusal as exc:
        return None, str(exc)
    return ExpiryView(pior_resultado=profile.max_loss, perda_ilimitada=profile.loss_unlimited,
                      melhor_resultado=profile.max_gain,
                      ganho_ilimitado=profile.gain_unlimited), None


def ticket_view(session: ReplaySession, ticket: str, now: datetime) -> TicketView:
    """Projeta a boleta aberta no instante do replay; não altera sessão, motor nem recibo."""
    session.check_time(now)
    engine = session.engine(ticket)
    reading = engine.reading(now)
    preview = engine.preview
    assert preview is not None
    rows = {row.symbol: row for row in reading.position.holdings}
    legs = tuple(
        LegView(serie=leg.symbol, lado=leg.side, lado_rotulo=SIDE_LABELS_PT[leg.side],
                quantidade=leg.quantity, lote=leg.lot_size, preco_limite=leg.limit_price,
                ativo=rows[leg.symbol].underlying, tipo=rows[leg.symbol].kind,
                strike=rows[leg.symbol].strike, vencimento=rows[leg.symbol].expiry,
                cotacao=_quote(quote, now), guarda=_guard(guard))
        for leg, quote, guard in zip(preview.legs, reading.quotes, reading.guards, strict=True))
    net = preview.net_limit
    nature = Nature.DEBIT if net > 0 else Nature.CREDIT if net < 0 else Nature.ZERO
    profile, unavailable = _expiry(preview, reading)
    if engine.state not in CONFIRMABLE:
        advance = AdvanceView(situacao=Advance.NOT_APPLICABLE, motivo=None)
    elif reading.refusal is None:
        advance = AdvanceView(situacao=Advance.CAN_CONFIRM, motivo=None)
    else:
        advance = AdvanceView(situacao=Advance.BLOCKED, motivo=reading.refusal)
    return TicketView(
        formato=VIEW_FORMAT, aviso=NOTICE, boleta=ticket, conta=reading.position.account,
        instante=now, estado=engine.state, rotulo=engine.label, pausada=engine.paused,
        versao=preview.version, resumo=preview.digest, foto_cotacao=preview.quote_snapshot_id,
        prazo_envio=preview.send_deadline, validade_ordens=preview.order_validity, pernas=legs,
        custo=CostView(liquido_assinado=net, natureza=nature, bruto_teto=preview.gross_cap),
        risco=RiskView(exposicao_montagem=preview.partial_exposure, vencimento=profile,
                       vencimento_indisponivel=unavailable),
        mercado=_guard(reading.market), avanco=advance)
