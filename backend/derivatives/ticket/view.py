"""Visão de leitura da boleta: traduz fatos do motor, sem decidir nem recalcular guardas."""
from datetime import date, datetime
from decimal import MAX_EMAX, MAX_PREC, MIN_EMIN, Context, Decimal
from enum import StrEnum
from fractions import Fraction
from typing import Annotated, Final, Literal

from pydantic import BeforeValidator

from backend.derivatives.pricing.expiry_payoff import (
    ExpiryLeg, PayoffRefusal, expiry_profile, expiry_result,
)
from backend.derivatives.ticket.engine import CONFIRMABLE, Reading
from backend.derivatives.ticket.guards import BookSnapshot, GuardResult
from backend.derivatives.ticket.models import (
    Environment, Instant, Money, Preview, Side, _Frozen,
)
from backend.derivatives.ticket.replay import Phase
from backend.derivatives.ticket.session import ReplaySession
from backend.derivatives.ticket.state import TicketState

VIEW_FORMAT: Final = 2
NOTICE = "SIMULADO — dados sintéticos em replay; nenhuma ordem real."
SIDE_LABELS_PT = {Side.BUY: "Compra", Side.SELL: "Venda"}
_CENT = Decimal("0.01")
_MAX_ADJUSTED = 15
_EXACT = Context(prec=MAX_PREC, Emin=MIN_EMIN, Emax=MAX_EMAX)


def _tidy(value: Decimal) -> Decimal:
    """Duas casas quando o valor cabe em centavos; senão, o valor exato."""
    cents = value.quantize(_CENT, context=_EXACT)
    return cents if cents == value else value


def _integer_only(value: object) -> object:
    if type(value) is not int:
        raise ValueError("formato exige inteiro")
    return value


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
    meio: Decimal | None
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
    modalidade: Literal["AMERICAN", "EUROPEAN"] | None
    strike: Money
    vencimento: date
    cotacao: QuoteView | None
    guarda: GuardView


class CostView(_Frozen):
    """Limites em reais da versão exibida; o líquido conserva o sinal do motor."""

    liquido_assinado: Money
    natureza: Nature
    bruto_teto: Money


class UnitPriceView(_Frozen):
    """Preço da estrutura por unidade: compras somam, vendas subtraem; positivo é débito."""

    quantidade: int
    limite: Decimal
    natural: Decimal
    meio: Decimal
    acima_do_meio: Decimal


class CurvePoint(_Frozen):
    """Resultado no vencimento com o ativo neste preço."""

    preco: Money
    resultado: Money


class ExpiryView(_Frozen):
    """Extremos, equilíbrios e quebras do resultado no vencimento, aos preços-limite."""

    pior_resultado: Money | None
    perda_ilimitada: bool
    melhor_resultado: Money | None
    ganho_ilimitado: bool
    equilibrios: tuple[Money, ...]
    curva: tuple[CurvePoint, ...]
    inclinacao_final: Money


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

    formato: Annotated[Literal[2], BeforeValidator(_integer_only)]
    aviso: str
    ambiente: Environment
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
    limite_idade_s: float
    pernas: tuple[LegView, ...]
    preco_unidade: UnitPriceView | None
    preco_unidade_indisponivel: str | None
    custo: CostView
    risco: RiskView
    mercado: GuardView
    avanco: AdvanceView


def _guard(result: GuardResult) -> GuardView:
    return GuardView(nivel=result.level, motivos=result.reasons)


def _quote(snapshot: BookSnapshot | None, now: datetime) -> QuoteView | None:
    if snapshot is None:
        return None
    middle = None
    if snapshot.bid is not None and snapshot.ask is not None:
        middle = _tidy(_EXACT.divide(_EXACT.add(snapshot.bid, snapshot.ask), Decimal(2)))
    return QuoteView(compra=snapshot.bid, compra_qtd=snapshot.bid_size, venda=snapshot.ask,
                     venda_qtd=snapshot.ask_size, meio=middle, fase=snapshot.phase,
                     instante=snapshot.ts, idade_s=(now - snapshot.ts).total_seconds())


def _unit_price(legs: tuple[LegView, ...]) -> tuple[UnitPriceView | None, str | None]:
    if len({leg.quantidade for leg in legs}) != 1:
        return None, "quantidades diferentes por perna"
    limit = natural = middle = Decimal(0)
    for leg in legs:
        quote = leg.cotacao
        if quote is None or quote.compra is None or quote.venda is None or quote.meio is None:
            return None, "cotação incompleta"
        buy = leg.lado is Side.BUY
        taken = quote.venda if buy else quote.compra
        step = _EXACT.add if buy else _EXACT.subtract
        limit = step(limit, leg.preco_limite)
        natural = step(natural, taken)
        middle = step(middle, quote.meio)
    quantity = legs[0].quantidade
    above = _EXACT.multiply(_EXACT.subtract(limit, middle), quantity)
    return UnitPriceView(quantidade=quantity, limite=_tidy(limit), natural=_tidy(natural),
                         meio=_tidy(middle), acima_do_meio=_tidy(above)), None


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
    legs = [ExpiryLeg(row.kind, leg.side.value, row.strike.quantize(_CENT, context=_EXACT),
                      leg.quantity, leg.limit_price.quantize(_CENT, context=_EXACT))
            for leg, row in zip(preview.legs, held, strict=True)]
    spots = sorted({Decimal("0.00"), *(leg.strike for leg in legs)})
    beyond = _EXACT.add(spots[-1], Decimal("1.00"))
    try:
        profile = expiry_profile(legs, max_legs=len(legs))
        curve = tuple(CurvePoint(preco=spot, resultado=expiry_result(
            legs, spot, max_legs=len(legs))) for spot in spots)
        slope = _EXACT.subtract(expiry_result(legs, beyond, max_legs=len(legs)),
                                curve[-1].resultado)
    except PayoffRefusal as exc:
        return None, str(exc)
    return ExpiryView(pior_resultado=profile.max_loss, perda_ilimitada=profile.loss_unlimited,
                      melhor_resultado=profile.max_gain, ganho_ilimitado=profile.gain_unlimited,
                      equilibrios=tuple(_cents(root) for root in profile.breakevens),
                      curva=curve, inclinacao_final=slope), None


def _cents(value: Fraction) -> Decimal:
    """Arredonda ao centavo, meio para o par, sem divisão decimal."""
    return Decimal(round(value * 100)).scaleb(-2, context=_EXACT)


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
                modalidade=rows[leg.symbol].style,
                strike=rows[leg.symbol].strike, vencimento=rows[leg.symbol].expiry,
                cotacao=_quote(quote, now), guarda=_guard(guard))
        for leg, quote, guard in zip(preview.legs, reading.quotes, reading.guards, strict=True))
    net = preview.net_limit
    nature = Nature.DEBIT if net > 0 else Nature.CREDIT if net < 0 else Nature.ZERO
    profile, unavailable = _expiry(preview, reading)
    unit, unit_unavailable = _unit_price(legs)
    if engine.state not in CONFIRMABLE:
        advance = AdvanceView(situacao=Advance.NOT_APPLICABLE, motivo=None)
    elif reading.refusal is None:
        advance = AdvanceView(situacao=Advance.CAN_CONFIRM, motivo=None)
    else:
        advance = AdvanceView(situacao=Advance.BLOCKED, motivo=reading.refusal)
    return TicketView(
        formato=VIEW_FORMAT, aviso=NOTICE, ambiente=preview.environment, boleta=ticket,
        conta=reading.position.account, limite_idade_s=reading.quote_age_limit_s,
        preco_unidade=unit, preco_unidade_indisponivel=unit_unavailable,
        instante=now, estado=engine.state, rotulo=engine.label, pausada=engine.paused,
        versao=preview.version, resumo=preview.digest, foto_cotacao=preview.quote_snapshot_id,
        prazo_envio=preview.send_deadline, validade_ordens=preview.order_validity, pernas=legs,
        custo=CostView(liquido_assinado=net, natureza=nature, bruto_teto=preview.gross_cap),
        risco=RiskView(exposicao_montagem=preview.partial_exposure, vencimento=profile,
                       vencimento_indisponivel=unavailable),
        mercado=_guard(reading.market), avanco=advance)
