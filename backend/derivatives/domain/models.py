"""Modelos de dominio imutaveis (DL-PR01): ``extra="forbid"``, congelados, ``Decimal``
em precos/strikes e ``AwareDatetime`` como validador comum — nenhum naive entra."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from backend.derivatives.provenance import ProvenanceStamp, Purpose, inherit_purpose

DOMAIN_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)

class OptionKind(StrEnum):
    """Lado da opcao."""
    CALL = "CALL"
    PUT = "PUT"

class ExerciseStyle(StrEnum):
    """Estilo de exercicio; ausencia no fornecedor vira ``UNKNOWN``, nunca default."""
    AMERICAN = "AMERICAN"
    EUROPEAN = "EUROPEAN"
    UNKNOWN = "UNKNOWN"

class SpotSource(StrEnum):
    """Origem da observacao de spot."""
    STOCK_ENDPOINT = "STOCK_ENDPOINT"
    OPTION_LAST_TRADE = "OPTION_LAST_TRADE"

class OptionContract(BaseModel):
    """Identidade imutavel de um contrato de opcao."""
    model_config = DOMAIN_MODEL_CONFIG
    symbol: str
    underlying: str
    kind: OptionKind
    exercise_style: ExerciseStyle
    strike: Decimal
    expiry: date
    contract_size: int | None
    quotation_form: int | None
    isin: str | None

class Quote(BaseModel):
    """Cotacao normalizada; ``None`` e ausencia, nunca zero disfarcado."""
    model_config = DOMAIN_MODEL_CONFIG
    bid: Decimal | None
    ask: Decimal | None
    last: Decimal | None
    bid_size: int | None
    ask_size: int | None
    volume: int | None
    trades: int | None
    last_trade_at: AwareDatetime | None
    source_time: AwareDatetime | None
    received_at: AwareDatetime

    @property
    def mid(self) -> Decimal | None:
        """Ponto medio bid/ask; so existe quando ambos os lados existem."""
        return None if self.bid is None or self.ask is None else (self.bid + self.ask) / 2

class QualityFlags(BaseModel):
    """Flags deterministicas de qualidade; mercado cruzado e flag, nao excecao."""
    model_config = DOMAIN_MODEL_CONFIG
    stale: bool
    age_s: float | None
    missing_bid: bool
    missing_ask: bool
    missing_last: bool
    zero_volume: bool
    crossed_market: bool
    spot_not_synchronous: bool
    spot_source: SpotSource | None
    missing_metadata: tuple[str, ...]

class SpotObservation(BaseModel):
    """Observacao de spot com origem e instante explicitos."""
    model_config = DOMAIN_MODEL_CONFIG
    price: Decimal
    source: SpotSource
    observed_at: AwareDatetime | None

class RateObservation(BaseModel):
    """Taxa em % a.a.; capitalizacao exponencial base 252 e hipotese (ADR-0023)."""
    model_config = DOMAIN_MODEL_CONFIG
    uid: str
    value_pct_aa: Decimal
    observed_at: AwareDatetime | None
    compounding_assumed: bool

class OptionRow(BaseModel):
    """Linha da chain: contrato, cotacao e qualidade."""
    model_config = DOMAIN_MODEL_CONFIG
    contract: OptionContract
    quote: Quote
    quality: QualityFlags

class Chain(BaseModel):
    """Chain normalizada; ``ProvenanceStamp`` e dataclass validado nativamente pelo pydantic."""
    model_config = DOMAIN_MODEL_CONFIG
    schema_version: Literal["quimera-derivatives-chain-v1"] = "quimera-derivatives-chain-v1"
    underlying: str
    expiry: date
    spot: SpotObservation | None
    rate: RateObservation | None
    rows: tuple[OptionRow, ...]
    stamp: ProvenanceStamp
    purpose: Purpose
    acquired_at: AwareDatetime
    model_assumptions: dict[str, str | float | bool]

    @model_validator(mode="after")
    def _purpose_matches_stamp(self) -> Chain:
        """Proposito da chain e exatamente o herdado worst-of do carimbo."""
        if self.purpose is not inherit_purpose(self.stamp.purpose):
            raise ValueError("purpose da chain nao pode divergir do herdado do carimbo")
        return self
