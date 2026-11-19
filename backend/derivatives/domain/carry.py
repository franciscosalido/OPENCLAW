"""Esqueleto para o RED da dupla contagem (DL2-PR02)."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from backend.derivatives.domain.series_terms import SeriesTerms, Text, _CivilDate, _TermsModel


class CarryKind(StrEnum):
    """Forma declarada do rendimento do ativo-objeto."""

    NONE = "NONE"
    CONTINUOUS_YIELD = "CONTINUOUS_YIELD"
    DISCRETE_DIVIDENDS = "DISCRETE_DIVIDENDS"


class CarryRefusalCode(StrEnum):
    """Motivos de recusa da premissa de carry."""

    DIVIDEND_DOUBLE_COUNT = "dividend_double_count"


class CarryRefusal(Exception):
    """Recusa de domínio com código estável."""

    def __init__(self, code: CarryRefusalCode) -> None:
        self.code = code
        super().__init__(code.value)


class CarryAssumption(_TermsModel):
    """Premissa por série e vigência."""

    symbol: Text
    effective_on: _CivilDate
    source: Text
    kind: CarryKind
    dividend_yield: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ResolvedCarry:
    """Premissa e rendimento entregue ao modelo."""

    terms: SeriesTerms
    assumption: CarryAssumption
    dividend_yield: float


def resolve_carry(terms: SeriesTerms, carry: CarryAssumption) -> ResolvedCarry:
    """Esqueleto deliberadamente sem trava para observar a dupla contagem."""
    return ResolvedCarry(terms, carry, float(carry.dividend_yield or 0))
