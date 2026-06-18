from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Literal, Mapping, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, model_validator

FI_KINDS = ("cdb", "lca", "lci", "cri", "cra", "debenture")
FI_INDEXERS = ("cdi", "ipca", "prefixado", "selic", "igpm")
FI_LINEAGE_FIELDS = (
    "isin",
    "kind",
    "issuer_cnpj",
    "indexer",
    "rate_spec_canonical",
    "maturity_date",
    "issue_date",
    "source_id",
    "schema_version",
)
LEVEL0_POSITION_FIELDS = frozenset(
    {
        "quantity",
        "face_value_held",
        "acquisition_price",
        "yield_at_purchase",
        "custodian",
        "account_number",
        "cpf",
        "holder_id",
        "portfolio_id",
        "broker_id",
    }
)

FIKind: TypeAlias = Literal["cdb", "lca", "lci", "cri", "cra", "debenture"]
FIIndexer: TypeAlias = Literal["cdi", "ipca", "prefixado", "selic", "igpm"]
RateModel: TypeAlias = Literal[
    "prefixado",
    "percent_of_indexer",
    "indexer_plus_spread",
    "inflation_plus_coupon",
]
PaymentFrequency: TypeAlias = Literal["bullet", "monthly", "semiannual", "annual"]
Amortization: TypeAlias = Literal["bullet", "custom"]


class RateSpec(BaseModel):
    """Semantic contract for private fixed-income rate specifications."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    indexer: FIIndexer
    rate_model: RateModel
    rate: Decimal | None = None
    spread: Decimal | None = None
    coupon: Decimal | None = None
    day_count: Literal[252, 360, 365]
    payment_frequency: PaymentFrequency
    amortization: Amortization = "bullet"

    @model_validator(mode="after")
    def _validate_rate_model_semantics(self) -> RateSpec:
        if self.rate_model == "prefixado":
            self._require_indexer("prefixado")
            self._require_only("rate")
            self._validate_range("rate", self.rate, lower=Decimal("-1"))
        elif self.rate_model == "percent_of_indexer":
            self._require_indexer("cdi", "selic")
            self._require_only("rate")
            self._validate_range("rate", self.rate, lower=Decimal("0"))
        elif self.rate_model == "indexer_plus_spread":
            self._require_indexer("cdi", "selic")
            self._require_only("spread")
            self._validate_range("spread", self.spread, lower=Decimal("-1"))
        elif self.rate_model == "inflation_plus_coupon":
            self._require_indexer("ipca", "igpm")
            self._require_only("coupon")
            self._validate_range("coupon", self.coupon, lower=Decimal("-1"))
        return self

    def canonical_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "indexer": self.indexer,
            "rate_model": self.rate_model,
            "day_count": self.day_count,
            "payment_frequency": self.payment_frequency,
            "amortization": self.amortization,
        }
        if self.rate is not None:
            payload["rate"] = str(self.rate)
        if self.spread is not None:
            payload["spread"] = str(self.spread)
        if self.coupon is not None:
            payload["coupon"] = str(self.coupon)
        return payload

    def _require_indexer(self, *allowed: FIIndexer) -> None:
        if self.indexer not in allowed:
            allowed_text = ", ".join(allowed)
            raise ValueError(
                f"{self.rate_model} requires indexer in ({allowed_text}); "
                f"got {self.indexer}"
            )

    def _require_only(self, required: Literal["rate", "spread", "coupon"]) -> None:
        values = {
            "rate": self.rate,
            "spread": self.spread,
            "coupon": self.coupon,
        }
        if values[required] is None:
            raise ValueError(f"{self.rate_model} requires {required}")
        for field_name, value in values.items():
            if field_name != required and value is not None:
                raise ValueError(f"{self.rate_model} must not set {field_name}")

    @staticmethod
    def _validate_range(
        field_name: str,
        value: Decimal | None,
        *,
        lower: Decimal,
    ) -> None:
        if value is None:
            return
        if not lower < value < Decimal("5"):
            raise ValueError(f"{field_name} must be > {lower} and < 5")


def validate_rate_spec_for_instrument(
    *,
    kind: str,
    indexer: str,
    rate_spec: Mapping[str, object] | RateSpec,
) -> RateSpec:
    if kind not in FI_KINDS:
        raise ValueError(f"unsupported private fixed-income kind: {kind}")
    if indexer not in FI_INDEXERS:
        raise ValueError(f"unsupported private fixed-income indexer: {indexer}")

    spec = (
        rate_spec
        if isinstance(rate_spec, RateSpec)
        else RateSpec.model_validate(rate_spec)
    )
    if spec.indexer != indexer:
        raise ValueError(f"indexer mismatch: column={indexer} rate_spec={spec.indexer}")
    return spec


def compute_quality_flags(kind: str, indexer: str) -> dict[str, object]:
    if (kind, indexer) in {("lci", "prefixado"), ("lca", "prefixado")}:
        return {"warnings": [f"uncommon_{kind}_{indexer}"]}
    return {}


def compute_fi_lineage_hash(payload: Mapping[str, object]) -> str:
    level0_keys = sorted(LEVEL0_POSITION_FIELDS.intersection(payload))
    if level0_keys:
        joined = ", ".join(level0_keys)
        raise ValueError(
            f"Level 0 position fields are not part of fi_instruments: {joined}"
        )

    canonical_payload = {
        field: _canonical_value(payload.get(field)) for field in FI_LINEAGE_FIELDS
    }
    encoded = json.dumps(
        canonical_payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, RateSpec):
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
