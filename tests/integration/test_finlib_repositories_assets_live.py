from __future__ import annotations

import os
from dataclasses import replace
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from asyncpg.exceptions import CheckViolationError  # type: ignore[import-untyped]

from backend.finlib.repositories import (
    AuditContext,
    CompanyListingInput,
    CompanyRegistryInput,
    DebentureMarketDataInput,
    FixedIncomeInstrumentInput,
    FixedIncomeRepository,
    FundDailyInfoInput,
    FundRegistryInput,
    FundRepository,
    FundamentalsIndicatorInput,
    FundamentalsRepository,
    FundamentalsStatementInput,
    IngestionRunInput,
    OpsRepository,
)
from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.timescale import is_timescale_available
from tests.integration.postgres_isolated_db import isolated_postgres_client


pytestmark = pytest.mark.integration


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    async with isolated_postgres_client(dsn, prefix="finlib_assets") as client:
        yield client


async def _migrate(client: PostgresClient) -> None:
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required")
    await run_migrations(client)


def _audit(
    *,
    run_id: UUID | None = None,
    suffix: str | None = None,
    batch_hash: str | None = None,
) -> AuditContext:
    token = suffix or uuid4().hex
    return AuditContext(
        trace_id=uuid4(),
        run_id=run_id,
        agent_id="finlib-assets-test",
        batch_hash=batch_hash or f"sha256:{token}",
        metadata={"test": "finlib-repositories-assets"},
    )


async def _audit_count(client: PostgresClient) -> int:
    return int(await client.pool.fetchval("SELECT count(*) FROM audit_agent_writes"))


async def _count(client: PostgresClient, table: str) -> int:
    return int(await client.pool.fetchval(f"SELECT count(*) FROM {table}"))


async def _start_run(
    ops: OpsRepository,
    source_id: str,
) -> UUID:
    return await ops.start_run(
        IngestionRunInput(
            source_id=source_id,
            agent_id="finlib-assets-test",
            trace_id=uuid4(),
            mode="dry_run",
        ),
        audit=_audit(suffix=f"start-{source_id}"),
    )


async def test_finlib_asset_repositories_flow_idempotency_and_atomicity(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    ops = OpsRepository(postgres_client)
    funds = FundRepository(postgres_client)
    fixed_income = FixedIncomeRepository(postgres_client)
    fundamentals = FundamentalsRepository(postgres_client)

    fund_run_id = await _start_run(ops, "cvm_informes_diarios")
    fund_registry = await funds.upsert_registry_batch(
        [
            FundRegistryInput(
                fund_cnpj="00000000000001",
                legal_name="Synthetic Fund",
                source_id="cvm_informes_diarios",
                status="active",
                metadata={"scope": "integration"},
            )
        ],
        audit=_audit(run_id=fund_run_id, suffix="fund-registry"),
    )
    assert fund_registry.inserted == 1

    fund_daily_v0 = FundDailyInfoInput(
        fund_cnpj="00000000000001",
        ts="2026-01-02T00:00:00+00:00",
        total_portfolio_value="1000.00",
        quota_value="1.00",
        net_worth="900.00",
        inflow="10.00",
        outflow="0.00",
        shareholders=42,
        source_id="cvm_informes_diarios",
        run_id=fund_run_id,
        lineage_hash="sha256:fund-daily-v0",
    )
    assert (
        await funds.upsert_daily_info_batch(
            [fund_daily_v0],
            audit=_audit(run_id=fund_run_id, suffix="fund-daily-v0"),
        )
    ).inserted == 1
    assert (
        await funds.upsert_daily_info_batch(
            [fund_daily_v0],
            audit=_audit(run_id=fund_run_id, suffix="fund-daily-duplicate"),
        )
    ).skipped == 1
    assert (
        await funds.upsert_daily_info_batch(
            [
                replace(
                    fund_daily_v0,
                    quota_value="1.01",
                    lineage_hash="sha256:fund-daily-v1",
                )
            ],
            audit=_audit(run_id=fund_run_id, suffix="fund-daily-v1"),
        )
    ).inserted == 1
    fund_revisions = await postgres_client.pool.fetch(
        """
        SELECT revision, quota_value
        FROM fund_daily_info
        WHERE fund_cnpj = '00000000000001'
        ORDER BY revision
        """
    )
    assert [(row["revision"], str(row["quota_value"])) for row in fund_revisions] == [
        (0, "1.00"),
        (1, "1.01"),
    ]

    fi_run_id = await _start_run(ops, "local_fixed_income_input")
    debenture_run_id = await _start_run(ops, "anbima_debentures")
    instrument_result = await fixed_income.upsert_instruments_batch(
        [
            FixedIncomeInstrumentInput(
                kind="cdb",
                issuer_cnpj="00000000000002",
                issuer_name="Synthetic Bank",
                indexer="cdi",
                rate_spec={
                    "indexer": "cdi",
                    "rate_model": "percent_of_indexer",
                    "rate": "1.05",
                    "day_count": 252,
                    "payment_frequency": "bullet",
                },
                fgc_covered=True,
                source_id="local_fixed_income_input",
                run_id=fi_run_id,
                lineage_hash="sha256:cdb-instrument",
            ),
            FixedIncomeInstrumentInput(
                kind="debenture",
                issuer_cnpj="00000000000003",
                issuer_name="Synthetic Issuer",
                indexer="cdi",
                rate_spec={
                    "indexer": "cdi",
                    "rate_model": "indexer_plus_spread",
                    "spread": "0.02",
                    "day_count": 252,
                    "payment_frequency": "bullet",
                },
                fgc_covered=False,
                source_id="anbima_debentures",
                run_id=debenture_run_id,
                lineage_hash="sha256:debenture-instrument",
                maturity_date="2030-01-01",
            ),
        ],
        audit=_audit(run_id=fi_run_id, suffix="fi-instruments"),
    )
    assert instrument_result.inserted == 2
    debenture_id = UUID(
        str(
            await postgres_client.pool.fetchval(
                """
                SELECT instrument_id
                FROM fi_instruments
                WHERE lineage_hash = 'sha256:debenture-instrument'
                """
            )
        )
    )
    debenture_v0 = DebentureMarketDataInput(
        fi_id=debenture_id,
        ts="2026-01-02T00:00:00+00:00",
        indicative_rate="0.12",
        pu="980.00",
        duration=720,
        source_id="anbima_debentures",
        run_id=debenture_run_id,
        lineage_hash="sha256:debenture-market-v0",
    )
    assert (
        await fixed_income.upsert_debenture_market_data_batch(
            [debenture_v0],
            audit=_audit(run_id=debenture_run_id, suffix="debenture-market-v0"),
        )
    ).inserted == 1
    assert (
        await fixed_income.upsert_debenture_market_data_batch(
            [debenture_v0],
            audit=_audit(run_id=debenture_run_id, suffix="debenture-market-duplicate"),
        )
    ).skipped == 1
    assert (
        await fixed_income.upsert_debenture_market_data_batch(
            [
                replace(
                    debenture_v0,
                    pu="981.00",
                    lineage_hash="sha256:debenture-market-v1",
                )
            ],
            audit=_audit(run_id=debenture_run_id, suffix="debenture-market-v1"),
        )
    ).inserted == 1

    fundamentals_run_id = await _start_run(ops, "cvm_dfp")
    company_result = await fundamentals.upsert_company_registry_batch(
        [
            CompanyRegistryInput(
                cnpj="00000000000004",
                cnpj_base="00000000",
                legal_name="Synthetic Company",
                source_id="cvm_cia_aberta_cadastro",
                lineage_hash="sha256:company-v0",
                cvm_code="999999",
            )
        ],
        audit=_audit(run_id=fundamentals_run_id, suffix="company-registry"),
    )
    assert company_result.inserted == 1
    company_id = UUID(
        str(
            await postgres_client.pool.fetchval(
                "SELECT company_id FROM company_registry WHERE cnpj = '00000000000004'"
            )
        )
    )
    listings_result = await fundamentals.upsert_company_listings_batch(
        [
            CompanyListingInput(
                company_id=company_id,
                exchange="B3",
                ticker="PETR3",
                share_class="ON",
                source_id="b3_listings",
                lineage_hash="sha256:petr3",
            ),
            CompanyListingInput(
                company_id=company_id,
                exchange="B3",
                ticker="PETR4",
                share_class="PN",
                source_id="b3_listings",
                lineage_hash="sha256:petr4",
            ),
        ],
        audit=_audit(run_id=fundamentals_run_id, suffix="company-listings"),
    )
    assert listings_result.inserted == 2

    statement_v0 = FundamentalsStatementInput(
        company_id=company_id,
        period_type="DFP",
        period_kind="annual",
        statement_scope="consolidated",
        fiscal_year=2025,
        period_end="2025-12-31",
        filing_date="2026-03-31",
        statements_json={"net_income": "100", "total_equity": "1000"},
        source_id="cvm_dfp",
        run_id=fundamentals_run_id,
        lineage_hash="sha256:statement-v0",
    )
    assert (
        await fundamentals.upsert_statements_batch(
            [statement_v0],
            audit=_audit(run_id=fundamentals_run_id, suffix="statement-v0"),
        )
    ).inserted == 1
    assert (
        await fundamentals.upsert_statements_batch(
            [statement_v0],
            audit=_audit(run_id=fundamentals_run_id, suffix="statement-duplicate"),
        )
    ).skipped == 1
    assert (
        await fundamentals.upsert_statements_batch(
            [
                replace(
                    statement_v0,
                    statements_json={
                        "net_income": "101",
                        "total_equity": "1000",
                    },
                    lineage_hash="sha256:statement-v1",
                    restatement_reason="corrected filing",
                )
            ],
            audit=_audit(run_id=fundamentals_run_id, suffix="statement-v1"),
        )
    ).inserted == 1
    statements = await postgres_client.pool.fetch(
        """
        SELECT statement_id, version
        FROM fundamentals_statements
        WHERE company_id = $1
        ORDER BY version
        """,
        company_id,
    )
    assert [row["version"] for row in statements] == [1, 2]

    assert (
        await fundamentals.upsert_indicators_batch(
            [
                FundamentalsIndicatorInput(
                    company_id=company_id,
                    ts="2025-12-31T00:00:00+00:00",
                    indicator_set="annual",
                    source_statement_id=UUID(str(statements[0]["statement_id"])),
                    indicators_json={"net_income": "100", "roe": "0.10"},
                    computation_hash="sha256:indicator-computation-v0",
                    run_id=fundamentals_run_id,
                    lineage_hash="sha256:indicator-v0",
                ),
                FundamentalsIndicatorInput(
                    company_id=company_id,
                    ts="2026-01-01T00:00:00+00:00",
                    indicator_set="annual",
                    source_statement_id=UUID(str(statements[1]["statement_id"])),
                    indicators_json={"net_income": "101", "roe": "0.101"},
                    computation_hash="sha256:indicator-computation-v1",
                    run_id=fundamentals_run_id,
                    lineage_hash="sha256:indicator-v1",
                ),
            ],
            audit=_audit(run_id=fundamentals_run_id, suffix="indicators"),
        )
    ).inserted == 2

    assert await _audit_count(postgres_client) == 18

    before_fund_daily = await _count(postgres_client, "fund_daily_info")
    before_audit = await _audit_count(postgres_client)
    with pytest.raises(CheckViolationError):
        await funds.upsert_daily_info_batch(
            [
                replace(
                    fund_daily_v0,
                    ts=datetime(2026, 1, 3, tzinfo=timezone.utc),
                    lineage_hash="sha256:fund-valid-rollback",
                ),
                replace(
                    fund_daily_v0,
                    ts=datetime(2026, 1, 4, tzinfo=timezone.utc),
                    quota_value="-1",
                    lineage_hash="sha256:fund-invalid-rollback",
                ),
            ],
            audit=_audit(run_id=fund_run_id, suffix="fund-rollback"),
        )
    assert await _count(postgres_client, "fund_daily_info") == before_fund_daily
    assert await _audit_count(postgres_client) == before_audit

    with pytest.raises(ValueError, match="Level 0"):
        await fixed_income.upsert_instruments_batch(
            [
                FixedIncomeInstrumentInput(
                    kind="cdb",
                    issuer_cnpj="00000000000005",
                    issuer_name="Synthetic Bank 2",
                    indexer="cdi",
                    rate_spec={
                        "indexer": "cdi",
                        "rate_model": "percent_of_indexer",
                        "rate": "1.00",
                        "day_count": 252,
                        "payment_frequency": "bullet",
                    },
                    fgc_covered=True,
                    source_id="local_fixed_income_input",
                    run_id=fi_run_id,
                    lineage_hash="sha256:fi-level0",
                    metadata={"portfolio_id": "private"},
                )
            ],
            audit=_audit(run_id=fi_run_id, suffix="fi-level0"),
        )
    assert await _audit_count(postgres_client) == before_audit

    with pytest.raises(ValueError, match="Level 0"):
        await fundamentals.upsert_statements_batch(
            [
                replace(
                    statement_v0,
                    period_end="2026-12-31",
                    filing_date="2027-03-31",
                    fiscal_year=2026,
                    statements_json={"cpf": "00000000000"},
                    lineage_hash="sha256:statement-level0",
                )
            ],
            audit=_audit(run_id=fundamentals_run_id, suffix="statement-level0"),
        )
    assert await _audit_count(postgres_client) == before_audit

    before_registry = await _count(postgres_client, "fund_registry")
    with pytest.raises(ValueError, match="batch_hash"):
        await funds.upsert_registry_batch(
            [
                FundRegistryInput(
                    fund_cnpj="00000000000009",
                    legal_name="Audit Failure Fund",
                    source_id="cvm_informes_diarios",
                )
            ],
            audit=_audit(run_id=fund_run_id, batch_hash="\t"),
        )
    assert await _count(postgres_client, "fund_registry") == before_registry
    assert await _audit_count(postgres_client) == before_audit
