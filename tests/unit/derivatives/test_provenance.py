"""Contratos de procedencia e proposito do Laboratorio de Derivativos."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.derivatives.provenance import (
    Provenance,
    ProvenanceStamp,
    Purpose,
    Readiness,
    inherit_purpose,
    purpose_of,
)

_NOW = datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC)


def test_provenance_values() -> None:
    assert [p.value for p in Provenance] == [
        "documental",
        "synthetic",
        "observed",
        "replay",
    ]


def test_purpose_values() -> None:
    assert [p.value for p in Purpose] == ["test", "production"]


def test_readiness_values() -> None:
    assert [r.value for r in Readiness] == ["A", "B", "C"]


def test_purpose_of_only_observed_is_production() -> None:
    assert purpose_of(Provenance.OBSERVED) is Purpose.PRODUCTION
    for prov in (Provenance.DOCUMENTAL, Provenance.SYNTHETIC, Provenance.REPLAY):
        assert purpose_of(prov) is Purpose.TEST


def test_inherit_purpose_worst_of() -> None:
    assert (
        inherit_purpose(Purpose.PRODUCTION, Purpose.PRODUCTION) is Purpose.PRODUCTION
    )
    assert inherit_purpose(Purpose.PRODUCTION, Purpose.TEST) is Purpose.TEST
    assert inherit_purpose(Purpose.TEST, Purpose.PRODUCTION) is Purpose.TEST
    assert inherit_purpose(Purpose.TEST) is Purpose.TEST


def test_inherit_purpose_empty_raises() -> None:
    with pytest.raises(ValueError, match="ao menos um"):
        inherit_purpose()


def test_stamp_rejects_naive_captured_at() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        ProvenanceStamp(
            provenance=Provenance.DOCUMENTAL,
            purpose=Purpose.TEST,
            source="doc",
            captured_at=datetime(2026, 11, 5),  # noqa: DTZ001 — naive de proposito
        )


def test_stamp_rejects_promotion_of_documental() -> None:
    with pytest.raises(ValueError, match="promover"):
        ProvenanceStamp(
            provenance=Provenance.DOCUMENTAL,
            purpose=Purpose.PRODUCTION,
            source="doc",
            captured_at=_NOW,
        )


def test_stamp_allows_canonical_and_demotion() -> None:
    observed = ProvenanceStamp(
        provenance=Provenance.OBSERVED,
        purpose=Purpose.PRODUCTION,
        source="api",
        captured_at=_NOW,
    )
    demoted = ProvenanceStamp(
        provenance=Provenance.OBSERVED,
        purpose=Purpose.TEST,
        source="api",
        captured_at=_NOW,
        note="rebaixado para replay de teste",
    )
    assert observed.purpose is Purpose.PRODUCTION
    assert demoted.purpose is Purpose.TEST
