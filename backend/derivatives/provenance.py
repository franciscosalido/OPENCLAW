"""Procedencia e proposito dos dados do Laboratorio de Derivativos.

Contratos da barreira deterministica anti-fixture (ADR-0023): a procedencia e
atribuida pelo adaptador de transporte, nunca pelo payload externo, e o
proposito herda worst-of — qualquer entrada de teste contamina o derivado como
teste; a promocao inversa e proibida.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Provenance(StrEnum):
    """Origem de uma captura de dados, atribuida pelo adaptador."""

    DOCUMENTAL = "documental"
    SYNTHETIC = "synthetic"
    OBSERVED = "observed"
    REPLAY = "replay"


class Purpose(StrEnum):
    """Destino permitido dos dados: teste ou producao."""

    TEST = "test"
    PRODUCTION = "production"


class Readiness(StrEnum):
    """Estados de prontidao da Fase 1 (ADR-0023): A offline, B homologado, C promovido."""

    A_OFFLINE_VERIFIED = "A"
    B_HOMOLOGATED = "B"
    C_PROMOTED = "C"


def purpose_of(provenance: Provenance) -> Purpose:
    """Proposito canonico de uma procedencia: so OBSERVED habilita producao."""
    if provenance is Provenance.OBSERVED:
        return Purpose.PRODUCTION
    return Purpose.TEST


def inherit_purpose(*purposes: Purpose) -> Purpose:
    """Heranca worst-of: qualquer TEST contamina o resultado como TEST.

    Raises:
        ValueError: se chamada sem nenhum ``Purpose``.
    """
    if not purposes:
        raise ValueError("inherit_purpose exige ao menos um Purpose")
    if Purpose.TEST in purposes:
        return Purpose.TEST
    return Purpose.PRODUCTION


@dataclass(frozen=True, slots=True)
class ProvenanceStamp:
    """Carimbo imutavel de procedencia de uma captura.

    O proposito nunca promove: ou e o canonico da procedencia
    (``purpose_of``), ou e rebaixado explicitamente para ``TEST``.
    """

    provenance: Provenance
    purpose: Purpose
    source: str
    captured_at: datetime
    note: str | None = None

    def __post_init__(self) -> None:
        """Rejeita ``captured_at`` sem fuso e promocao de proposito."""
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at deve ser datetime com fuso (tz-aware)")
        canonical = purpose_of(self.provenance)
        if self.purpose is not canonical and self.purpose is not Purpose.TEST:
            raise ValueError(
                "purpose nao pode promover procedencia "
                f"{self.provenance.value!r} para {self.purpose.value!r}"
            )
