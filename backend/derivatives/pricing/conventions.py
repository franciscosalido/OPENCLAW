"""Convencoes temporais (DL-PR02): fracao de ano, taxa continua e tempo ate o
vencimento. Nao decide hora de exercicio nem fracao intradiaria de dia."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.derivatives.pricing.calendar import TradingCalendar, business_days_between
from config.derivatives_config_model import Conventions, RateCompounding, YearBasis


def year_fraction(business_days: int, *, basis: YearBasis) -> float:
    """Converte contagem de dias uteis em fracao de ano na base declarada."""
    if business_days < 0:
        raise ValueError(f"business_days negativo: {business_days}")
    return business_days / basis


def continuous_rate(value_pct_aa: Decimal, *, compounding: RateCompounding) -> float:
    """Converte % a.a. em taxa continua: ``annual_exp_252`` -> ``ln(1 + i/100)``
    (padrao CDI/Selic, hipotese ADR-0023); ``continuous`` -> ``i/100``."""
    fraction = float(value_pct_aa) / 100.0
    return math.log(1.0 + fraction) if compounding == "annual_exp_252" else fraction


@dataclass(frozen=True, slots=True)
class TimeToExpiry:
    """Tempo ate o vencimento em dias uteis e fracao de ano, com a convencao usada.
    Hora de exercicio e fracao intradiaria NAO sao decididas aqui (fora do DL-PR02)."""

    business_days: int
    year_fraction: float
    convention: str
    calendar_id: str
    basis: int
    is_expiry_day: bool


def time_to_expiry(cal: TradingCalendar, *, valuation_date: date, expiry: date, cfg: Conventions) -> TimeToExpiry:
    """Calcula o tempo ate o vencimento com a convencao de intervalo do contrato."""
    days = business_days_between(cal, valuation_date, expiry, convention=cfg.interval_convention)
    return TimeToExpiry(
        business_days=days,
        year_fraction=year_fraction(days, basis=cfg.year_basis),
        convention=cfg.interval_convention,
        calendar_id=cal.calendar_id.value,
        basis=cfg.year_basis,
        is_expiry_day=days == 0 and valuation_date == expiry,
    )


def model_assumptions(cfg: Conventions, cal: TradingCalendar) -> dict[str, str | float | bool]:
    """Chaves de hipoteses que ``Chain.model_assumptions`` (DL-PR01) carrega."""
    return {
        "calendar_id": cal.calendar_id.value,
        "calendar_versions": ",".join(cal.version_ids),
        "day_count_calendar": cfg.day_count_calendar,
        "day_count_calendar_assumed": cfg.day_count_calendar_assumed,
        "interval_convention": cfg.interval_convention,
        "interval_convention_assumed": cfg.interval_convention_assumed,
        "year_basis": float(cfg.year_basis),
        "rate_compounding": cfg.rate_compounding,
        "rate_compounding_assumed": cfg.rate_compounding_assumed,
        "dividend_yield": cfg.dividend_yield,
        "strike_adjusted_by_exchange_assumed": cfg.strike_adjusted_by_exchange_assumed,
    }
