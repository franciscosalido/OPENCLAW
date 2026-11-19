"""Termos vigentes por série (DL2-PR01), independentes da chain da Fase 01."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from backend.derivatives.domain.models import ExerciseStyle


class RefusalCode(StrEnum):
    MISSING_CONTRACT_SIZE = "missing_contract_size"
    MISSING_QUOTATION_FORM = "missing_quotation_form"
    UNKNOWN_EXERCISE_STYLE = "unknown_exercise_style"
    UNKNOWN_CURRENCY = "unknown_currency"


class TermsRefusal(Exception):
    def __init__(self, code: RefusalCode) -> None:
        self.code = code
        super().__init__(code.value)


class AdjustmentPolicy(StrEnum):
    PROTECTED = "PROTECTED"
    UNPROTECTED = "UNPROTECTED"
    UNKNOWN = "UNKNOWN"


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
TERMS_CONFIG = ConfigDict(strict=True, frozen=True, extra="forbid")


class AdjustmentEvidence(BaseModel):
    """Declaração documental fornecida pelo chamador; não consulta o emissor."""

    model_config = TERMS_CONFIG
    issuer: Literal["B3"]
    document: Text
    version: Text
    published_on: date
    symbol: Text
    effective_on: date
    policy: AdjustmentPolicy


class SeriesTerms(BaseModel):
    """Uma observação por série e data de vigência explícita."""

    model_config = TERMS_CONFIG
    symbol: Text
    effective_on: date
    source: Text
    strike: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    contract_size: int
    quotation_form: Literal[1, 1000]
    currency: Literal["BRL"]
    exercise_style: ExerciseStyle
    adjustment_policy: AdjustmentPolicy
    evidence: AdjustmentEvidence | None = None

    @model_validator(mode="before")
    @classmethod
    def require_series_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            lot = data.get("contract_size")
            if type(lot) is not int or lot <= 0:
                raise TermsRefusal(RefusalCode.MISSING_CONTRACT_SIZE)
            factor = data.get("quotation_form")
            if type(factor) is not int or factor not in (1, 1000):
                raise TermsRefusal(RefusalCode.MISSING_QUOTATION_FORM)
            style = data.get("exercise_style")
            if style not in (ExerciseStyle.AMERICAN, ExerciseStyle.EUROPEAN):
                raise TermsRefusal(RefusalCode.UNKNOWN_EXERCISE_STYLE)
            if data.get("currency") != "BRL":
                raise TermsRefusal(RefusalCode.UNKNOWN_CURRENCY)
            return {**data, "exercise_style": ExerciseStyle(style)}
        return data

    @field_validator("strike", mode="before")
    @classmethod
    def require_decimal(cls, value: object) -> Decimal:
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError("strike deve ser Decimal finito")
        return value

    @model_validator(mode="after")
    def require_applicable_evidence(self) -> Self:
        doc = self.evidence
        if doc is None:
            if self.adjustment_policy != AdjustmentPolicy.UNKNOWN:
                raise ValueError("política conclusiva exige documento B3")
        elif (doc.symbol, doc.effective_on, doc.policy) != (
            self.symbol, self.effective_on, self.adjustment_policy
        ):
            raise ValueError("evidência incompatível com série, vigência ou política")
        return self
