from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from backend.finlib.repositories import (
    AuditContext,
    BatchWriteResult,
    CompanyListingInput,
    CompanyRegistryInput,
    FundamentalsIndicatorInput,
    FundamentalsRepository,
    FundamentalsStatementInput,
)


SOURCE = Path("backend/finlib/repositories/fundamentals_repository.py")


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_fundamentals_repository_public_methods_are_async() -> None:
    for method_name in (
        "upsert_company_registry_batch",
        "upsert_company_listings_batch",
        "upsert_statements_batch",
        "upsert_indicators_batch",
    ):
        assert inspect.iscoroutinefunction(getattr(FundamentalsRepository, method_name))


async def test_fundamentals_empty_batches_are_noop_without_audit() -> None:
    repo = FundamentalsRepository(object())

    assert (
        await repo.upsert_company_registry_batch([], audit=_audit())
        == BatchWriteResult.empty()
    )
    assert (
        await repo.upsert_company_listings_batch([], audit=_audit())
        == BatchWriteResult.empty()
    )
    assert (
        await repo.upsert_statements_batch([], audit=_audit())
        == BatchWriteResult.empty()
    )
    assert (
        await repo.upsert_indicators_batch([], audit=_audit())
        == BatchWriteResult.empty()
    )


def test_fundamentals_repository_uses_dtos_not_tuple_batches() -> None:
    company = CompanyRegistryInput(
        cnpj="00000000000001",
        cnpj_base="00000000",
        legal_name="Synthetic Company",
        source_id="cvm_cia_aberta_cadastro",
        lineage_hash="sha256:company",
    )
    listing = CompanyListingInput(
        company_id="00000000-0000-7000-8000-000000000001",
        exchange="B3",
        ticker="PETR3",
        share_class="ON",
        source_id="b3_listings",
        lineage_hash="sha256:listing",
    )
    statement = FundamentalsStatementInput(
        company_id=listing.company_id,
        period_type="DFP",
        period_kind="annual",
        statement_scope="consolidated",
        fiscal_year=2025,
        period_end="2025-12-31",
        filing_date="2026-03-31",
        statements_json={"net_income": "1"},
        source_id="cvm_dfp",
        run_id="00000000-0000-7000-8000-000000000002",
        lineage_hash="sha256:statement",
    )
    indicator = FundamentalsIndicatorInput(
        company_id=listing.company_id,
        ts="2025-12-31T00:00:00+00:00",
        indicator_set="annual",
        source_statement_id="00000000-0000-7000-8000-000000000003",
        indicators_json={"net_income": "1"},
        computation_hash="sha256:computation",
        run_id=statement.run_id,
        lineage_hash="sha256:indicator",
    )

    assert company.cnpj_base == company.cnpj[:8]
    assert (
        indicator.indicators_json["net_income"]
        == statement.statements_json["net_income"]
    )


def test_fundamentals_repository_sql_contracts() -> None:
    source = _source()

    assert "ON CONFLICT (cnpj)" in source
    assert "ON CONFLICT (exchange, ticker)" in source
    assert "ON CONFLICT (lineage_hash, ts) DO NOTHING" in source
    assert "pg_advisory_xact_lock" in source
    assert "ORDER BY version DESC" in source
    assert "UPDATE fundamentals_statements" not in source
    assert "::jsonb" not in source.replace("::text::jsonb", "")


def test_company_listing_conflict_does_not_overwrite_company_id() -> None:
    conflict = _source().split("ON CONFLICT (exchange, ticker) DO UPDATE SET", 1)[1]
    update_set = conflict.split("RETURNING listing_id", 1)[0]

    assert "company_id" not in update_set


async def test_fundamentals_rejects_level0_before_db() -> None:
    repo = FundamentalsRepository(object())

    with pytest.raises(ValueError, match="Level 0"):
        await repo.upsert_statements_batch(
            [
                FundamentalsStatementInput(
                    company_id="00000000-0000-7000-8000-000000000001",
                    period_type="DFP",
                    period_kind="annual",
                    statement_scope="consolidated",
                    fiscal_year=2025,
                    period_end="2025-12-31",
                    filing_date="2026-03-31",
                    statements_json={"cpf": "00000000000"},
                    source_id="cvm_dfp",
                    run_id="00000000-0000-7000-8000-000000000002",
                    lineage_hash="sha256:statement-level0",
                )
            ],
            audit=_audit(),
        )


async def test_fundamentals_rejects_market_dependent_indicators() -> None:
    repo = FundamentalsRepository(object())

    with pytest.raises(ValueError, match="market-dependent"):
        await repo.upsert_indicators_batch(
            [
                FundamentalsIndicatorInput(
                    company_id="00000000-0000-7000-8000-000000000001",
                    ts="2025-12-31T00:00:00+00:00",
                    indicator_set="annual",
                    source_statement_id="00000000-0000-7000-8000-000000000003",
                    indicators_json={"pe_ratio": "10"},
                    computation_hash="sha256:computation",
                    run_id="00000000-0000-7000-8000-000000000002",
                    lineage_hash="sha256:indicator-market",
                )
            ],
            audit=_audit(),
        )


def test_fundamentals_repository_has_no_remote_client_or_calculation_engine() -> None:
    source = _source().lower()
    for forbidden in ("httpx", "requests", "qdrant", "openai", "litellm"):
        assert forbidden not in source
    assert "compute_statement_only_indicators" not in source


def _audit() -> AuditContext:
    return AuditContext(
        trace_id="00000000-0000-7000-8000-000000000030",
        agent_id="finlib-test",
        batch_hash="sha256:fundamentals-test",
    )
