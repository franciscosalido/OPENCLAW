from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from backend.finlib.repositories import (
    AuditContext,
    BatchWriteResult,
    FundDailyInfoInput,
    FundRegistryInput,
    FundRepository,
)


SOURCE = Path("backend/finlib/repositories/fund_repository.py")


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_fund_repository_public_methods_are_async() -> None:
    assert inspect.iscoroutinefunction(FundRepository.upsert_registry_batch)
    assert inspect.iscoroutinefunction(FundRepository.upsert_daily_info_batch)


async def test_fund_empty_batches_are_noop_without_audit() -> None:
    repo = FundRepository(object())

    assert (
        await repo.upsert_registry_batch([], audit=_audit()) == BatchWriteResult.empty()
    )
    assert (
        await repo.upsert_daily_info_batch([], audit=_audit())
        == BatchWriteResult.empty()
    )


def test_fund_repository_uses_dtos_not_tuple_batches() -> None:
    registry = FundRegistryInput(
        fund_cnpj="00000000000001",
        legal_name="Synthetic Fund",
        source_id="cvm_informes_diarios",
    )
    daily = FundDailyInfoInput(
        fund_cnpj=registry.fund_cnpj,
        ts="2026-01-02T00:00:00+00:00",
        quota_value="1.23",
        net_worth="1000.00",
        shareholders=10,
        source_id="cvm_informes_diarios",
        run_id="00000000-0000-7000-8000-000000000001",
        lineage_hash="sha256:fund-daily",
    )

    assert registry.fund_cnpj == daily.fund_cnpj


def test_fund_repository_sql_contracts() -> None:
    source = _source()

    assert "ON CONFLICT (fund_cnpj)" in source
    assert "pg_advisory_xact_lock" in source
    assert "MAX(revision)" in source
    assert "UPDATE fund_daily_info" not in source
    assert "::jsonb" not in source.replace("::text::jsonb", "")


async def test_fund_repository_rejects_level0_before_db() -> None:
    repo = FundRepository(object())

    with pytest.raises(ValueError, match="Level 0"):
        await repo.upsert_daily_info_batch(
            [
                FundDailyInfoInput(
                    fund_cnpj="00000000000001",
                    ts="2026-01-02T00:00:00+00:00",
                    quota_value="1.23",
                    net_worth="1000.00",
                    shareholders=10,
                    source_id="cvm_informes_diarios",
                    run_id="00000000-0000-7000-8000-000000000001",
                    lineage_hash="sha256:fund-daily-level0",
                    metadata={"cpf": "00000000000"},
                )
            ],
            audit=_audit(),
        )


def test_fund_repository_has_no_remote_client_or_parser() -> None:
    source = _source().lower()
    for forbidden in ("httpx", "requests", "qdrant", "openai", "litellm", "csv"):
        assert forbidden not in source


def _audit() -> AuditContext:
    return AuditContext(
        trace_id="00000000-0000-7000-8000-000000000010",
        agent_id="finlib-test",
        batch_hash="sha256:fund-test",
    )
