"""Modelos do fornecedor OpLab v3, espelho literal da doc; ``extra="allow"`` (DL-PR01)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict

VENDOR_MODEL_CONFIG = ConfigDict(extra="allow", frozen=True)

class VendorPayloadError(ValueError):
    """Forma inesperada de payload; a mensagem nunca inclui o payload bruto."""

class VendorOption(BaseModel):
    """Linha documental de ``GET /market/options/{symbol}`` (OpLab v3)."""
    model_config = VENDOR_MODEL_CONFIG
    symbol: str
    strike: float
    due_date: date
    category: Literal["CALL", "PUT"]
    type: Literal["CALL", "PUT"] | None = None
    maturity_type: Literal["AMERICAN", "EUROPEAN"] | None = None
    contract_size: int | None = None
    bid: float | None = None
    ask: float | None = None
    close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    bid_volume: int | None = None
    ask_volume: int | None = None
    volume: int | None = None
    trades: int | None = None
    financial_volume: float | None = None
    spot_price: float | None = None
    time: int | None = None
    last_trade_at: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    block_date: datetime | None = None
    market_maker: bool | None = None
    days_to_maturity: int | None = None
    isin: str | None = None
    cnpj: str | None = None
    exchange_id: str | None = None
    name: str | None = None
    parent_symbol: str | None = None
    security_category: int | None = None
    strike_eod: float | None = None
    variation: float | None = None

class VendorStock(BaseModel):
    """Resposta documental de ``GET /market/stocks/{symbol}`` (OpLab v3)."""
    model_config = VENDOR_MODEL_CONFIG
    symbol: str
    bid: float | None = None
    ask: float | None = None
    close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    previous_close: float | None = None
    bid_volume: int | None = None
    ask_volume: int | None = None
    volume: int | None = None
    trades: int | None = None
    time: int | None = None
    last_trade_at: int | None = None
    contract_size: int | None = None
    quotation_form: int | None = None
    type: str | None = None
    category: str | None = None
    name: str | None = None
    isin: str | None = None
    cnpj: str | None = None
    has_options: bool | None = None
    iv_current: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

class VendorInterestRate(BaseModel):
    """Item documental de ``GET /market/interest_rates`` (OpLab v3)."""
    model_config = VENDOR_MODEL_CONFIG
    name: str
    uid: str
    value: float
    updated_at: datetime | None = None

class VendorMarketStatus(BaseModel):
    """Resposta documental de ``GET /market/status`` (OpLab v3)."""
    model_config = VENDOR_MODEL_CONFIG
    market_status: str
    server_time: datetime | None = None

def unknown_fields(model: BaseModel) -> tuple[str, ...]:
    """Chaves do payload fora do schema do fornecedor, em ordem alfabetica."""
    return tuple(sorted(model.model_extra or {}))

def parse_vendor_options(payload: object) -> tuple[VendorOption, ...]:
    """Parseia a lista de opcoes; forma errada levanta erro sanitizado."""
    if not isinstance(payload, list):
        raise VendorPayloadError(f"options: esperada lista JSON, veio {type(payload).__name__}")
    return tuple(VendorOption.model_validate(item) for item in payload)

def parse_vendor_stock(payload: object) -> VendorStock:
    """Parseia a resposta de ativo; forma errada levanta erro sanitizado."""
    if not isinstance(payload, dict):
        raise VendorPayloadError(f"stocks: esperado objeto JSON, veio {type(payload).__name__}")
    return VendorStock.model_validate(payload)

def parse_vendor_interest_rates(payload: object) -> tuple[VendorInterestRate, ...]:
    """Parseia a lista de taxas; forma errada levanta erro sanitizado."""
    if not isinstance(payload, list):
        raise VendorPayloadError(f"interest_rates: esperada lista JSON, veio {type(payload).__name__}")
    return tuple(VendorInterestRate.model_validate(item) for item in payload)

def parse_vendor_market_status(payload: object) -> VendorMarketStatus:
    """Parseia o estado do mercado; forma errada levanta erro sanitizado."""
    if not isinstance(payload, dict):
        raise VendorPayloadError(f"status: esperado objeto JSON, veio {type(payload).__name__}")
    return VendorMarketStatus.model_validate(payload)
