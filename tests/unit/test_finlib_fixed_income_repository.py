from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from backend.finlib.repositories import (
    AuditContext,
    BatchWriteResult,
    DebentureMarketDataInput,
    FixedIncomeInstrumentInput,
    FixedIncomeRepository,
)


SOURCE = Path("backend/finlib/repositories/fixed_income_repository.py")


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def _rate_spec() -> dict[str, object]:
    return {
        "indexer": "cdi",
        "rate_model": "percent_of_indexer",
        "rate": "1.05",
        "day_count": 252,
        "payment_frequency": "bullet",
    }


def test_fixed_income_repository_public_methods_are_async() -> None:
    assert inspect.iscoroutinefunction(FixedIncomeRepository.upsert_instruments_batch)
    assert inspect.iscoroutinefunction(
        FixedIncomeRepository.upsert_debenture_market_data_batch
    )


async def test_fixed_income_empty_batches_are_noop_without_audit() -> None:
    repo = FixedIncomeRepository(object())

    assert (
        await repo.upsert_instruments_batch([], audit=_audit())
        == BatchWriteResult.empty()
    )
    assert (
        await repo.upsert_debenture_market_data_batch([], audit=_audit())
        == BatchWriteResult.empty()
    )


def test_fixed_income_repository_uses_dtos_not_tuple_batches() -> None:
    instrument = FixedIncomeInstrumentInput(
        kind="cdb",
        issuer_cnpj="00000000000001",
        issuer_name="Synthetic Bank",
        indexer="cdi",
        rate_spec=_rate_spec(),
        fgc_covered=True,
        source_id="local_fixed_income_input",
        lineage_hash="sha256:fi-instrument",
    )
    market = DebentureMarketDataInput(
        fi_id="00000000-0000-7000-8000-000000000001",
        ts="2026-01-02T00:00:00+00:00",
        source_id="anbima_debentures",
        run_id="00000000-0000-7000-8000-000000000002",
        lineage_hash="sha256:debenture-market",
        pu="1000.00",
    )

    assert instrument.lineage_hash.startswith("sha256:")
    assert market.pu == "1000.00"


def test_fixed_income_repository_sql_contracts() -> None:
    source = _source()

    assert "ON CONFLICT (lineage_hash) DO NOTHING" in source
    assert "ON CONFLICT (lineage_hash, ts) DO NOTHING" in source
    assert "pg_advisory_xact_lock" in source
    assert "$1::uuid::text" in source
    assert "$2::timestamptz::text" in source
    assert "MAX(revision)" in source
    assert "::jsonb" not in source.replace("::text::jsonb", "")


async def test_fixed_income_rejects_level0_before_db() -> None:
    repo = FixedIncomeRepository(object())

    with pytest.raises(ValueError, match="Level 0"):
        await repo.upsert_instruments_batch(
            [
                FixedIncomeInstrumentInput(
                    kind="cdb",
                    issuer_cnpj="00000000000001",
                    issuer_name="Synthetic Bank",
                    indexer="cdi",
                    rate_spec={**_rate_spec(), "cpf": "00000000000"},
                    fgc_covered=True,
                    source_id="local_fixed_income_input",
                    lineage_hash="sha256:fi-level0",
                )
            ],
            audit=_audit(),
        )


def test_fixed_income_repository_has_no_downloader_or_remote_client() -> None:
    source = _source().lower()
    for forbidden in ("httpx", "requests", "qdrant", "openai", "litellm", "anbima"):
        assert forbidden not in source


def _audit() -> AuditContext:
    return AuditContext(
        trace_id="00000000-0000-7000-8000-000000000020",
        agent_id="finlib-test",
        batch_hash="sha256:fixed-income-test",
    )
