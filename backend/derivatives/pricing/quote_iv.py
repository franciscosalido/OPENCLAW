"""Ponte cotacao -> IVs (DL-PR04): ``bid``, ``ask`` e ``mid`` invertidos em separado.
A cotacao nunca e alterada; lado ausente vira ``None`` (nunca um status disfarcado);
``mid`` e indicativo — nao pressupoe execucao."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from backend.derivatives.domain.models import OptionContract, Quote
from backend.derivatives.pricing.conventions import TimeToExpiry
from backend.derivatives.pricing.implied_vol import IvResult, IvStatus, implied_vol
from config.derivatives_config_model import Iv

PRICE_SOURCE_NOTE = "mid e indicativo; nao pressupoe execucao"


class IvDiagnosticModel(BaseModel):
    """Diagnostico serializavel; ``status`` e ``StrEnum`` e serializa como ``str``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: IvStatus
    iterations: int
    bracket_lo: float | None
    bracket_hi: float | None
    residual_price: float | None
    residual_vol: float | None
    vega_at_solution: float | None
    expansions: int
    message: str


class IvResultModel(BaseModel):
    """Versao pydantic de ``IvResult``: sigma opcional + diagnostico completo."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sigma: float | None
    diagnostic: IvDiagnosticModel


class QuoteIv(BaseModel):
    """IVs por lado da cotacao; lado ausente e ``None``, com a nota sobre o ``mid``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bid: IvResultModel | None
    ask: IvResultModel | None
    mid: IvResultModel | None
    price_source_note: str = PRICE_SOURCE_NOTE


def _as_model(result: IvResult) -> IvResultModel:
    """Converte o dataclass puro na versao serializavel."""
    return IvResultModel(sigma=result.sigma,
                         diagnostic=IvDiagnosticModel(**asdict(result.diagnostic)))


def iv_for_quote(
    quote: Quote,
    contract: OptionContract,
    *,
    spot: Decimal,
    rate_cont: float,
    tte: TimeToExpiry,
    cfg: Iv,
    dividend_yield: float,
) -> QuoteIv:
    """Inverte IV para ``bid``, ``ask`` e ``mid`` existentes, sem tocar na cotacao.

    Mercado cruzado (``bid > ask``) continua calculado nos tres lados; sinalizar
    ``crossed_market`` e responsabilidade de ``QualityFlags`` (DL-PR01), nao daqui.
    ``Decimal`` vira ``float`` apenas aqui, sem arredondamento previo.
    """

    def invert(side_price: Decimal | None) -> IvResultModel | None:
        if side_price is None:
            return None
        result = implied_vol(float(side_price), kind=contract.kind, spot=float(spot),
                             strike=float(contract.strike),
                             time_years=tte.year_fraction, rate_cont=rate_cont,
                             dividend_yield=dividend_yield, cfg=cfg)
        return _as_model(result)

    return QuoteIv(bid=invert(quote.bid), ask=invert(quote.ask),
                   mid=invert(quote.mid))
