"""Typed DTOs for FINLIB asset repositories."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Mapping
from uuid import UUID

from backend.finlib.repositories.models import JsonMap
from backend.finlib.rate_spec import RateSpec


@dataclass(frozen=True, slots=True)
class FundRegistryInput:
    """Input row for fund_registry."""

    fund_cnpj: str
    legal_name: str
    source_id: str
    cvm_class: str | None = None
    fund_type: str | None = None
    status: str = "unknown"
    registered_at: date | str | None = None
    is_active: bool = True
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FundDailyInfoInput:
    """Input row for fund_daily_info."""

    fund_cnpj: str
    ts: datetime | str
    quota_value: Decimal | str
    net_worth: Decimal | str
    shareholders: int
    source_id: str
    run_id: UUID | str
    lineage_hash: str
    total_portfolio_value: Decimal | str | None = None
    inflow: Decimal | str | None = None
    outflow: Decimal | str | None = None
    schema_version: int = 1
    quality_flags: JsonMap = field(default_factory=dict)
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FixedIncomeInstrumentInput:
    """Input row for fi_instruments."""

    kind: str
    issuer_cnpj: str
    issuer_name: str
    indexer: str
    rate_spec: Mapping[str, object] | RateSpec
    fgc_covered: bool
    source_id: str
    lineage_hash: str
    instrument_name: str | None = None
    isin: str | None = None
    issue_date: date | str | None = None
    maturity_date: date | str | None = None
    run_id: UUID | str | None = None
    schema_version: int = 1
    quality_flags: JsonMap = field(default_factory=dict)
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DebentureMarketDataInput:
    """Input row for debenture_market_data."""

    fi_id: UUID | str
    ts: datetime | str
    source_id: str
    run_id: UUID | str
    lineage_hash: str
    indicative_rate: Decimal | str | None = None
    pu: Decimal | str | None = None
    duration: int | None = None
    schema_version: int = 1
    quality_flags: JsonMap = field(default_factory=dict)
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CompanyRegistryInput:
    """Input row for company_registry."""

    cnpj: str
    cnpj_base: str
    legal_name: str
    source_id: str
    lineage_hash: str
    trade_name: str | None = None
    sector_ibge: str | None = None
    cvm_code: str | None = None
    cvm_category: str | None = None
    listing_status: str = "listed"
    schema_version: int = 1
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CompanyListingInput:
    """Input row for company_listings."""

    company_id: UUID | str
    exchange: str
    ticker: str
    share_class: str
    source_id: str
    lineage_hash: str
    isin: str | None = None
    lot_size: int = 100
    active: bool = True
    listed_at: date | str | None = None
    delisted_at: date | str | None = None
    schema_version: int = 1
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FundamentalsStatementInput:
    """Input row for fundamentals_statements."""

    company_id: UUID | str
    period_type: str
    period_kind: str
    statement_scope: str
    fiscal_year: int
    period_end: date | str
    filing_date: date | str
    statements_json: JsonMap
    source_id: str
    run_id: UUID | str
    lineage_hash: str
    fiscal_quarter: int | None = None
    restatement_reason: str | None = None
    currency: str = "BRL"
    unit_multiplier: int = 1000
    schema_version: int = 1
    quality_flags: JsonMap = field(default_factory=dict)
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FundamentalsIndicatorInput:
    """Input row for fundamentals_indicators."""

    company_id: UUID | str
    ts: datetime | str
    indicator_set: str
    source_statement_id: UUID | str
    indicators_json: JsonMap
    computation_hash: str
    run_id: UUID | str
    lineage_hash: str
    schema_version: int = 1
    quality_flags: JsonMap = field(default_factory=dict)
    metadata: JsonMap = field(default_factory=dict)
