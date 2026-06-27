"""Deterministic company fundamentals helpers for FINLIB."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final, cast

from pydantic import BaseModel, ConfigDict


STATEMENT_ONLY_INDICATORS: Final[frozenset[str]] = frozenset(
    {
        "lpa",
        "vpa",
        "ebitda",
        "net_revenue",
        "net_income",
        "total_assets",
        "total_equity",
        "net_debt",
        "roe",
        "roa",
    }
)
MARKET_DEPENDENT_INDICATORS: Final[frozenset[str]] = frozenset(
    {
        "pe_ratio",
        "pb_ratio",
        "ev_ebitda",
        "dividend_yield",
        "market_cap",
        "market_price",
    }
)
LEVEL0_FORBIDDEN_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "quantity",
        "position_size",
        "acquisition_price",
        "yield_at_purchase",
        "custodian",
        "account_number",
        "cpf",
        "holder_id",
        "portfolio_id",
        "broker_id",
        "position_date",
        "cost_basis",
        "target_weight",
        "recommendation",
        "personal_notes",
        "user_id",
    }
)
NON_CONTENT_LINEAGE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "run_id",
        "ingested_at",
        "created_at",
        "updated_at",
        "metadata",
        "quality_flags",
    }
)


class FundamentalsIndicators(BaseModel):
    """Statement-only indicators allowed for FINLIB fundamentals persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    lpa: Decimal | None = None
    vpa: Decimal | None = None
    ebitda: Decimal | None = None
    net_revenue: Decimal | None = None
    net_income: Decimal | None = None
    total_assets: Decimal | None = None
    total_equity: Decimal | None = None
    net_debt: Decimal | None = None
    roe: Decimal | None = None
    roa: Decimal | None = None

    def canonical_payload(self) -> dict[str, str | None]:
        """Return a deterministic JSON-ready indicator payload."""

        return {
            key: _decimal_to_text(getattr(self, key))
            for key in sorted(STATEMENT_ONLY_INDICATORS)
        }


def compute_statement_only_indicators(
    statement_payload: Mapping[str, object],
) -> FundamentalsIndicators:
    """Derive only statement-only indicators from a normalized payload."""

    _reject_forbidden_fields(statement_payload)
    net_revenue = _decimal_or_none(statement_payload.get("net_revenue"))
    net_income = _decimal_or_none(statement_payload.get("net_income"))
    total_assets = _decimal_or_none(statement_payload.get("total_assets"))
    total_equity = _decimal_or_none(statement_payload.get("total_equity"))
    gross_debt = _decimal_or_none(statement_payload.get("gross_debt"))
    cash = _decimal_or_none(statement_payload.get("cash_and_equivalents"))
    operating_income = _decimal_or_none(statement_payload.get("operating_income"))
    depreciation = _decimal_or_none(statement_payload.get("depreciation_amortization"))
    shares = _decimal_or_none(statement_payload.get("shares_outstanding"))

    return FundamentalsIndicators(
        lpa=_divide(net_income, shares),
        vpa=_divide(total_equity, shares),
        ebitda=_add_if_present(operating_income, depreciation),
        net_revenue=net_revenue,
        net_income=net_income,
        total_assets=total_assets,
        total_equity=total_equity,
        net_debt=_subtract_if_present(gross_debt, cash),
        roe=_divide(net_income, total_equity),
        roa=_divide(net_income, total_assets),
    )


def compute_fundamentals_lineage_hash(payload: Mapping[str, object]) -> str:
    """Compute content idempotency hash for public fundamentals payloads."""

    _reject_forbidden_fields(payload)
    canonical_payload = {
        str(key): _canonical_value(value)
        for key, value in sorted(payload.items(), key=lambda item: str(item[0]))
        if str(key) not in NON_CONTENT_LINEAGE_FIELDS
    }
    return _sha256_prefixed(canonical_payload)


def compute_computation_hash(inputs: Mapping[str, object]) -> str:
    """Compute a deterministic hash for indicator computation inputs."""

    _reject_forbidden_fields(inputs)
    canonical_payload = {
        str(key): _canonical_value(value)
        for key, value in sorted(inputs.items(), key=lambda item: str(item[0]))
        if str(key) != "run_id"
    }
    return _sha256_prefixed(canonical_payload)


def _reject_forbidden_fields(payload: Mapping[str, object]) -> None:
    level0_keys = sorted(LEVEL0_FORBIDDEN_FIELDS.intersection(payload))
    if level0_keys:
        joined = ", ".join(level0_keys)
        raise ValueError(f"Level 0 fields are not valid fundamentals data: {joined}")


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | str):
        try:
            return Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"invalid decimal value: {value!r}") from exc
    raise ValueError(f"invalid decimal value: {value!r}")


def _divide(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _add_if_present(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return left + right


def _subtract_if_present(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return left - right


def _decimal_to_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _canonical_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, FundamentalsIndicators):
        return value.canonical_payload()
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(cast(object, mapped_value))
            for key, mapped_value in sorted(
                value.items(), key=lambda item: str(item[0])
            )
        }
    if isinstance(value, tuple | list):
        return [_canonical_value(item) for item in value]
    return value


def _sha256_prefixed(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
