"""Termos vigentes por série (DL2-PR01)."""
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from backend.derivatives.domain.models import ExerciseStyle


class TermsRefusal(Exception):
    code: str


class AdjustmentPolicy(StrEnum):
    PROTECTED = "PROTECTED"
    UNPROTECTED = "UNPROTECTED"
    UNKNOWN = "UNKNOWN"


class SeriesTerms(BaseModel):
    model_config = ConfigDict(extra="allow")
    contract_size: int | None = None
    exercise_style: ExerciseStyle
