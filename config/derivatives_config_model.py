"""Contrato YAML validado do Laboratorio de Derivativos (DL-PR00).

Modulo intencionalmente declarativo, no mesmo molde de
``config/rag_config_model.py``: carregar o contrato nao abre rede, nao le
token e nao instancia transporte. As convencoes numericas sao hipoteses
declaradas ate homologacao (ADR-0023).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

DayCount = Literal["business_252", "calendar_365"]
RateCompounding = Literal["annual_exp_252", "continuous"]
IntervalConvention = Literal["(D0,Dv]", "[D0,Dv)"]
YearBasis = Literal[252, 365]

STRICT_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)

_DEFAULT_ALLOWED_ROUTES: tuple[str, ...] = (
    "/market/options/{symbol}",
    "/market/stocks/{symbol}",
    "/market/interest_rates",
    "/market/status",
)


class Conventions(BaseModel):
    """Convencoes numericas declaradas como hipoteses ate homologacao."""

    model_config = STRICT_MODEL_CONFIG

    day_count: DayCount = "business_252"
    rate_compounding: RateCompounding = "annual_exp_252"
    dividend_yield: float = Field(default=0.0, ge=0.0)
    strike_adjusted_by_exchange_assumed: bool = True
    rate_compounding_assumed: bool = True
    calendars_dir: str = "config/calendars"
    trading_calendar_id: Literal["B3_LISTED_TRADING"] = "B3_LISTED_TRADING"
    financial_calendar_id: Literal["BR_ANBIMA_BUSINESS"] = "BR_ANBIMA_BUSINESS"
    day_count_calendar: Literal["trading", "financial"] = "trading"
    day_count_calendar_assumed: bool = True
    interval_convention: IntervalConvention = "(D0,Dv]"
    interval_convention_assumed: bool = True
    year_basis: YearBasis = 252


class Quality(BaseModel):
    """Limiares de qualidade das capturas."""

    model_config = STRICT_MODEL_CONFIG

    max_age_s: int = Field(default=60, gt=0)
    spot_sync_tolerance_s: int = Field(default=60, gt=0)


class Budget(BaseModel):
    """Orcamento de requisicoes do cliente OpLab (consumido no DL-PR04)."""

    model_config = STRICT_MODEL_CONFIG

    per_minute: int = Field(default=100, gt=0)
    per_second: int = Field(default=50, gt=0)
    timeout_s: float = Field(default=10.0, gt=0)
    max_retries: int = Field(default=0, ge=0)


class Oplab(BaseModel):
    """Host fixo e rotas permitidas; a allowlist e controle de seguranca."""

    model_config = STRICT_MODEL_CONFIG

    base_url: HttpUrl = HttpUrl("https://api.oplab.com.br/v3")
    allowed_routes: list[str] = Field(
        default_factory=lambda: list(_DEFAULT_ALLOWED_ROUTES)
    )

    @field_validator("allowed_routes")
    @classmethod
    def routes_must_be_market_only(cls, value: list[str]) -> list[str]:
        """Aceita apenas rotas ``/market/...``; dominio de ordens e proibido."""
        for route in value:
            if "/domain" in route:
                raise ValueError(f"rota proibida no Laboratorio: {route!r}")
            if not route.startswith("/market/"):
                raise ValueError(f"rota fora de /market/: {route!r}")
        return value


class Iv(BaseModel):
    """Parametros da bissecao protegida de volatilidade implicita."""

    model_config = STRICT_MODEL_CONFIG

    bracket_lo: float = Field(default=1e-4, gt=0)
    bracket_hi: float = Field(default=5.0, gt=0)
    bracket_hi_max: float = Field(default=20.0, gt=0)
    max_iterations: int = Field(default=200, gt=0)
    tol_price_rel: float = Field(default=1e-8, gt=0)
    tol_vol: float = Field(default=1e-8, gt=0)
    low_vega_threshold: float = Field(default=1e-4, gt=0)


class DerivativesConfig(BaseModel):
    """Raiz do contrato ``config/derivatives.yaml``."""

    model_config = STRICT_MODEL_CONFIG

    conventions: Conventions = Field(default_factory=Conventions)
    quality: Quality = Field(default_factory=Quality)
    budget: Budget = Field(default_factory=Budget)
    oplab: Oplab = Field(default_factory=Oplab)
    iv: Iv = Field(default_factory=Iv)


def load_derivatives_config(path: Path | None = None) -> DerivativesConfig:
    """Carrega e valida ``config/derivatives.yaml`` ou um caminho explicito.

    Raises:
        ValueError: YAML que nao e mapeamento, chave desconhecida ou rota
            fora da allowlist de ``/market/``.
        yaml.YAMLError: YAML improprio.
    """
    resolved = (
        path
        if path is not None
        else Path(__file__).resolve().parent / "derivatives.yaml"
    )
    raw_config = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw_config, dict):
        raise ValueError("derivatives.yaml deve conter um mapeamento YAML")
    return DerivativesConfig.model_validate(cast("dict[str, object]", raw_config))


__all__ = [
    "Budget",
    "Conventions",
    "DerivativesConfig",
    "IntervalConvention",
    "Iv",
    "Oplab",
    "Quality",
    "YearBasis",
    "load_derivatives_config",
]
