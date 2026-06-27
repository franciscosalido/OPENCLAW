from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from uuid import UUID

import pytest
from asyncpg.exceptions import CheckViolationError  # type: ignore[import-untyped]

from backend.finlib.fundamentals import (
    compute_computation_hash,
    compute_fundamentals_lineage_hash,
    compute_statement_only_indicators,
)
from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.timescale import is_hypertable, is_timescale_available
from tests.integration.postgres_isolated_db import isolated_postgres_client


pytestmark = pytest.mark.integration


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    async with isolated_postgres_client(dsn, prefix="finlib_fundamentals") as client:
        yield client


async def _migrate(client: PostgresClient) -> tuple[str, ...]:
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required")
    return await run_migrations(client)


async def _create_company(client: PostgresClient) -> UUID:
    company_id = await client.pool.fetchval(
        """
        INSERT INTO company_registry(
            cnpj, cnpj_base, legal_name, trade_name, cvm_code, source_id,
            lineage_hash
        )
        VALUES(
            '33000167000101', '33000167',
            'PETROLEO BRASILEIRO S.A. PETROBRAS', 'PETROBRAS', '9512',
            'cvm_cia_aberta_cadastro', 'sha256:company-petrobras'
        )
        RETURNING company_id
        """
    )
    return UUID(str(company_id))


async def _create_run(client: PostgresClient, source_id: str = "cvm_dfp") -> UUID:
    run_id = await client.pool.fetchval(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, trace_id, source_snapshot_hash
        )
        VALUES(
            $1, 'finlib-fundamentals-test', 'execute', 'completed',
            uuidv7(), 'sha256:cvm-fundamentals-snapshot'
        )
        RETURNING run_id
        """,
        source_id,
    )
    return UUID(str(run_id))


def _statement_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "company_id": "petrobras",
        "period_end": "2026-12-31",
        "net_revenue": "1000",
        "net_income": "120",
        "total_assets": "2400",
        "total_equity": "800",
        "gross_debt": "300",
        "cash_and_equivalents": "50",
        "operating_income": "160",
        "depreciation_amortization": "40",
        "shares_outstanding": "100",
    }
    payload.update(overrides)
    return payload


async def _insert_statement(
    client: PostgresClient,
    *,
    company_id: UUID,
    run_id: UUID,
    version: int = 1,
    prior_version_id: UUID | None = None,
    restatement_reason: str | None = None,
    payload: dict[str, object] | None = None,
    lineage_hash: str | None = None,
) -> UUID:
    statement_payload = payload or _statement_payload()
    statement_id = await client.pool.fetchval(
        """
        INSERT INTO fundamentals_statements(
            company_id, period_type, period_kind, statement_scope,
            fiscal_year, fiscal_quarter, period_end, filing_date, version,
            restatement_reason, prior_version_id, statements_json, source_id,
            run_id, lineage_hash
        )
        VALUES(
            $1, 'DFP', 'annual', 'consolidated', 2026, NULL,
            '2026-12-31', '2027-03-31', $2, $3, $4, $5::text::jsonb,
            'cvm_dfp', $6, $7
        )
        RETURNING statement_id
        """,
        company_id,
        version,
        restatement_reason,
        prior_version_id,
        json.dumps(statement_payload, sort_keys=True),
        run_id,
        lineage_hash or compute_fundamentals_lineage_hash(statement_payload),
    )
    return UUID(str(statement_id))


async def _insert_indicators(
    client: PostgresClient,
    *,
    company_id: UUID,
    run_id: UUID,
    statement_id: UUID,
    payload: dict[str, object],
    lineage_hash: str,
) -> None:
    indicators = compute_statement_only_indicators(payload)
    canonical = indicators.canonical_payload()
    await client.pool.execute(
        """
        INSERT INTO fundamentals_indicators(
            company_id, ts, indicator_set, source_statement_id,
            indicators_json, computation_hash, run_id, lineage_hash
        )
        VALUES(
            $1, $2, 'annual', $3, $4::text::jsonb, $5, $6, $7
        )
        """,
        company_id,
        datetime(2026, 12, 31, tzinfo=timezone.utc),
        statement_id,
        json.dumps(canonical, sort_keys=True),
        compute_computation_hash(canonical),
        run_id,
        lineage_hash,
    )


async def test_fundamentals_restatement_preserves_history_and_indicators(
    postgres_client: PostgresClient,
) -> None:
    applied = await _migrate(postgres_client)
    assert "028_create_company_fundamentals" in applied
    assert await run_migrations(postgres_client) == ()

    company_id = await _create_company(postgres_client)
    run_id = await _create_run(postgres_client)
    v1_payload = _statement_payload()
    v2_payload = _statement_payload(net_income="121")

    v1 = await _insert_statement(
        postgres_client,
        company_id=company_id,
        run_id=run_id,
        payload=v1_payload,
        lineage_hash="sha256:statement-v1",
    )
    await _insert_indicators(
        postgres_client,
        company_id=company_id,
        run_id=run_id,
        statement_id=v1,
        payload=v1_payload,
        lineage_hash="sha256:indicators-v1",
    )
    v2 = await _insert_statement(
        postgres_client,
        company_id=company_id,
        run_id=run_id,
        version=2,
        prior_version_id=v1,
        restatement_reason="DFP reapresentada pela companhia",
        payload=v2_payload,
        lineage_hash="sha256:statement-v2",
    )
    await _insert_indicators(
        postgres_client,
        company_id=company_id,
        run_id=run_id,
        statement_id=v2,
        payload=v2_payload,
        lineage_hash="sha256:indicators-v2",
    )

    rows = await postgres_client.pool.fetch(
        """
        SELECT statement_id, version, prior_version_id, restatement_reason
        FROM fundamentals_statements
        WHERE company_id = $1
        ORDER BY version
        """,
        company_id,
    )
    indicator_count = await postgres_client.pool.fetchval(
        """
        SELECT count(*)
        FROM fundamentals_indicators
        WHERE company_id = $1
          AND ts = '2026-12-31 00:00:00+00'::timestamptz
        """,
        company_id,
    )

    assert [(row["version"], row["prior_version_id"]) for row in rows] == [
        (1, None),
        (2, v1),
    ]
    assert rows[1]["restatement_reason"] == "DFP reapresentada pela companhia"
    assert indicator_count == 2


async def test_fundamentals_statement_constraints(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    company_id = await _create_company(postgres_client)
    run_id = await _create_run(postgres_client)
    v1 = await _insert_statement(
        postgres_client,
        company_id=company_id,
        run_id=run_id,
        lineage_hash="sha256:statement-v1",
    )

    invalid_sql = """
        INSERT INTO fundamentals_statements(
            company_id, period_type, period_kind, statement_scope, fiscal_year,
            fiscal_quarter, period_end, filing_date, version,
            restatement_reason, prior_version_id, statements_json, source_id,
            run_id, lineage_hash
        )
        VALUES(
            $1, $2, $3, 'consolidated', 2026, $4, '2026-12-31',
            '2027-03-31', $5, $6, $7, $8::jsonb, 'cvm_dfp', $9, $10
        )
    """
    cases = (
        ("DFP", "annual", 4, 1, None, None, "{}", "sha256:bad-dfp-quarter"),
        ("ITR", "quarterly", None, 1, None, None, "{}", "sha256:bad-itr-quarter"),
        ("DFP", "annual", None, 0, None, None, "{}", "sha256:bad-version-zero"),
        ("DFP", "annual", None, 2, None, v1, "{}", "sha256:missing-reason"),
        ("DFP", "annual", None, 2, "retificada", None, "{}", "sha256:missing-prior"),
        ("DFP", "annual", None, 1, None, None, "[]", "sha256:bad-json"),
        ("DFP", "annual", None, 1, None, None, "{}", "\t"),
    )

    for case in cases:
        (
            period_type,
            period_kind,
            fiscal_quarter,
            version,
            restatement_reason,
            prior_version_id,
            statements_json,
            lineage_hash,
        ) = case
        with pytest.raises(CheckViolationError):
            await postgres_client.pool.execute(
                invalid_sql,
                company_id,
                period_type,
                period_kind,
                fiscal_quarter,
                version,
                restatement_reason,
                prior_version_id,
                statements_json,
                run_id,
                lineage_hash,
            )


async def test_fundamentals_indicators_hypertable_and_cross_sprint_tables(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    async with postgres_client.pool.acquire() as conn:
        assert await is_hypertable(conn, "fundamentals_indicators")
    for table_name in (
        "ops_data_sources",
        "ops_ingestion_runs",
        "audit_agent_writes",
        "fi_instruments",
        "debenture_market_data",
    ):
        assert (
            await postgres_client.pool.fetchval(
                f"SELECT to_regclass('public.{table_name}')"
            )
            == table_name
        )
    sources = await postgres_client.pool.fetch(
        """
        SELECT source_id
        FROM ops_data_sources
        WHERE source_id IN (
            'cvm_cia_aberta_cadastro', 'cvm_dfp', 'cvm_itr', 'b3_listings'
        )
        """
    )
    constraints = await postgres_client.pool.fetch(
        """
        SELECT conname, array_agg(att.attname ORDER BY ord.ordinality) AS columns
        FROM pg_constraint AS con
        JOIN unnest(con.conkey) WITH ORDINALITY AS ord(attnum, ordinality)
          ON TRUE
        JOIN pg_attribute AS att
          ON att.attrelid = con.conrelid
         AND att.attnum = ord.attnum
        WHERE con.conrelid = 'fundamentals_indicators'::regclass
          AND con.contype IN ('p', 'u')
        GROUP BY con.conname
        """
    )

    assert {str(row["source_id"]) for row in sources} == {
        "cvm_cia_aberta_cadastro",
        "cvm_dfp",
        "cvm_itr",
        "b3_listings",
    }
    assert (
        await postgres_client.pool.fetchval("SELECT count(*) FROM audit_agent_writes")
        == 0
    )
    for row in constraints:
        assert "ts" in {str(column) for column in row["columns"]}
