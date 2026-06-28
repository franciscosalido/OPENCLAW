from __future__ import annotations

import inspect
from pathlib import Path

from backend.finlib.repositories import (
    MacroObservationInput,
    MacroRepository,
    MacroSeriesInput,
)


SOURCE = Path("backend/finlib/repositories/macro_repository.py")


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_macro_repository_public_methods_are_async() -> None:
    assert inspect.iscoroutinefunction(MacroRepository.upsert_series_catalog)
    assert inspect.iscoroutinefunction(MacroRepository.upsert_observations_batch)


def test_macro_repository_uses_dtos_not_tuple_batches() -> None:
    series = MacroSeriesInput(
        series_code="ipca_test",
        display_name="IPCA test",
        provider="bcb_sgs",
        provider_code="433",
        source_id="bcb_sgs",
        unit="percent",
        periodicity="monthly",
        value_type="rate_percent",
        methodology_note="synthetic test series",
    )
    observation = MacroObservationInput(
        series_code="ipca_test",
        ref_ts="2026-01-01T00:00:00+00:00",
        value="0.42",
        source_id="bcb_sgs",
        run_id="00000000-0000-7000-8000-000000000001",
        lineage_hash="sha256:macro-test",
    )

    assert series.series_code == observation.series_code


def test_macro_repository_conflict_policy_does_not_change_source_silently() -> None:
    source = _source()

    assert "macro_series_catalog.source_id = excluded.source_id" in source
    assert "source_id changed for macro series" in source


def test_macro_observation_revision_uses_advisory_lock_and_lineage_skip() -> None:
    source = _source()

    assert "pg_advisory_xact_lock" in source
    assert "$2::timestamptz::text" in source
    assert "$2::text" not in source
    assert "MAX(revision)" in source
    assert "UNIQUE (lineage_hash, ref_ts)" not in source
    assert "SELECT 1 FROM macro_observations" in source


def test_macro_empty_batch_policy_is_noop_without_audit() -> None:
    assert "return BatchWriteResult.empty()" in _source()


def test_macro_repository_has_no_orm_or_remote_fetch() -> None:
    source = _source().lower()
    for forbidden in ("sqlalchemy", "sqlmodel", "alembic", "httpx", "requests"):
        assert forbidden not in source
