from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import datetime
from decimal import Decimal
from uuid import UUID

import pytest
from asyncpg.exceptions import (  # type: ignore[import-untyped]
    CheckViolationError,
    ForeignKeyViolationError,
    UniqueViolationError,
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
    async with isolated_postgres_client(dsn, prefix="finlib_macro_revision") as client:
        yield client


async def _migrate(client: PostgresClient) -> None:
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for FINLIB macro tests")
    try:
        version = await client.pool.fetchval("SELECT uuid_extract_version(uuidv7())")
    except Exception as exc:
        raise AssertionError("PostgreSQL 18 uuidv7() is required") from exc
    assert version == 7
    await run_migrations(client)


async def _create_run(client: PostgresClient) -> UUID:
    run_id = await client.pool.fetchval(
        """
        INSERT INTO ops_ingestion_runs(source_id, agent_id, mode, status, trace_id)
        VALUES('bcb_sgs', 'finlib-macro-test', 'dry_run', 'created', uuidv7())
        RETURNING run_id
        """
    )
    return UUID(str(run_id))


async def _insert_observation(
    client: PostgresClient,
    *,
    run_id: UUID,
    series_code: str,
    ref_ts: str,
    revision: int,
    value: str,
    lineage_hash: str,
) -> str:
    normalized_ref_ts = ref_ts
    if normalized_ref_ts.endswith("+00"):
        normalized_ref_ts = f"{normalized_ref_ts}:00"
    ref_dt = datetime.fromisoformat(normalized_ref_ts)
    status = await client.pool.execute(
        """
        INSERT INTO macro_observations(
            series_code, ref_ts, revision, value, source_id, run_id, lineage_hash
        )
        VALUES($1, $2::timestamptz, $3, $4::numeric, 'bcb_sgs', $5, $6)
        """,
        series_code,
        ref_dt,
        revision,
        value,
        run_id,
        lineage_hash,
    )
    return str(status)


async def test_identical_reingestion_is_idempotent_and_revision_is_append_only(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)

    await _insert_observation(
        postgres_client,
        run_id=run_id,
        series_code="ipca",
        ref_ts="2026-01-01 00:00:00+00",
        revision=0,
        value="0.42",
        lineage_hash="sha256:ipca-2026-01-r0",
    )
    await postgres_client.pool.execute(
        """
        INSERT INTO macro_observations(
            series_code, ref_ts, revision, value, source_id, run_id, lineage_hash
        )
        VALUES(
            'ipca', '2026-01-01 00:00:00+00'::timestamptz, 0,
            0.42, 'bcb_sgs', $1, 'sha256:ipca-2026-01-r0'
        )
        ON CONFLICT (lineage_hash, ref_ts) DO NOTHING
        """,
        run_id,
    )
    await _insert_observation(
        postgres_client,
        run_id=run_id,
        series_code="ipca",
        ref_ts="2026-01-01 00:00:00+00",
        revision=1,
        value="0.43",
        lineage_hash="sha256:ipca-2026-01-r1",
    )

    rows = await postgres_client.pool.fetch(
        """
        SELECT revision, value
        FROM macro_observations
        WHERE series_code = 'ipca'
          AND ref_ts = '2026-01-01 00:00:00+00'::timestamptz
        ORDER BY revision
        """
    )

    assert [(row["revision"], row["value"]) for row in rows] == [
        (0, Decimal("0.42")),
        (1, Decimal("0.43")),
    ]


async def test_revision_and_lineage_constraints_are_enforced(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)

    with pytest.raises(CheckViolationError):
        await _insert_observation(
            postgres_client,
            run_id=run_id,
            series_code="ipca",
            ref_ts="2026-01-01 00:00:00+00",
            revision=-1,
            value="0.42",
            lineage_hash="sha256:negative-revision",
        )

    await _insert_observation(
        postgres_client,
        run_id=run_id,
        series_code="ipca",
        ref_ts="2026-02-01 00:00:00+00",
        revision=0,
        value="0.44",
        lineage_hash="sha256:duplicate-lineage",
    )
    with pytest.raises(UniqueViolationError):
        await _insert_observation(
            postgres_client,
            run_id=run_id,
            series_code="igpm",
            ref_ts="2026-02-01 00:00:00+00",
            revision=0,
            value="0.55",
            lineage_hash="sha256:duplicate-lineage",
        )


async def test_unknown_source_and_run_fail_foreign_keys(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)

    with pytest.raises(ForeignKeyViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO macro_observations(
                series_code, ref_ts, revision, value, source_id, run_id, lineage_hash
            )
            VALUES(
                'ipca', '2026-01-01'::timestamptz, 0, 0.42,
                'missing_source', $1, 'sha256:missing-source'
            )
            """,
            run_id,
        )

    with pytest.raises(ForeignKeyViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO macro_observations(
                series_code, ref_ts, revision, value, source_id, run_id, lineage_hash
            )
            VALUES(
                'ipca', '2026-01-01'::timestamptz, 0, 0.42,
                'bcb_sgs', '00000000-0000-7000-8000-000000000001'::uuid,
                'sha256:missing-run'
            )
            """
        )


async def test_vw_fx_brlusd_derives_from_ptax_pair_and_latest_revision(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)

    await _insert_observation(
        postgres_client,
        run_id=run_id,
        series_code="ptax_usdbrl_compra",
        ref_ts="2026-01-02 00:00:00+00",
        revision=0,
        value="5.00",
        lineage_hash="sha256:ptax-compra-2026-01-02-r0",
    )
    await _insert_observation(
        postgres_client,
        run_id=run_id,
        series_code="ptax_usdbrl_compra",
        ref_ts="2026-01-02 00:00:00+00",
        revision=1,
        value="5.10",
        lineage_hash="sha256:ptax-compra-2026-01-02-r1",
    )
    await _insert_observation(
        postgres_client,
        run_id=run_id,
        series_code="ptax_usdbrl_venda",
        ref_ts="2026-01-02 00:00:00+00",
        revision=0,
        value="5.20",
        lineage_hash="sha256:ptax-venda-2026-01-02-r0",
    )
    await _insert_observation(
        postgres_client,
        run_id=run_id,
        series_code="ptax_usdbrl_venda",
        ref_ts="2026-01-02 00:00:00+00",
        revision=1,
        value="5.30",
        lineage_hash="sha256:ptax-venda-2026-01-02-r1",
    )
    await _insert_observation(
        postgres_client,
        run_id=run_id,
        series_code="ptax_usdbrl_compra",
        ref_ts="2026-01-03 00:00:00+00",
        revision=0,
        value="5.50",
        lineage_hash="sha256:ptax-compra-2026-01-03-r0",
    )

    row = await postgres_client.pool.fetchrow(
        """
        SELECT *
        FROM vw_fx_brlusd
        WHERE ref_ts = '2026-01-02 00:00:00+00'::timestamptz
        """
    )
    missing_pair_count = await postgres_client.pool.fetchval(
        """
        SELECT count(*)
        FROM vw_fx_brlusd
        WHERE ref_ts = '2026-01-03 00:00:00+00'::timestamptz
        """
    )

    assert row is not None
    assert row["usdbrl_bid"] == Decimal("5.10")
    assert row["usdbrl_ask"] == Decimal("5.30")
    assert row["usdbrl_mid"] == Decimal("5.20")
    assert row["brlusd_bid"].quantize(Decimal("0.000001")) == Decimal("0.188679")
    assert row["brlusd_ask"].quantize(Decimal("0.000001")) == Decimal("0.196078")
    assert row["brlusd_mid"].quantize(Decimal("0.000001")) == Decimal("0.192308")
    assert row["revision_bid"] == 1
    assert row["revision_ask"] == 1
    assert missing_pair_count == 0


async def test_brlusd_is_not_stored_as_catalog_or_observation(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    stored_catalog = await postgres_client.pool.fetchval(
        """
        SELECT count(*)
        FROM macro_series_catalog
        WHERE series_code IN (
            'brlusd', 'brl_usd', 'fx_brlusd', 'brlusd_mid', 'usdbrl_mid'
        )
        """
    )
    stored_observations = await postgres_client.pool.fetchval(
        """
        SELECT count(*)
        FROM macro_observations
        WHERE series_code IN (
            'brlusd', 'brl_usd', 'fx_brlusd', 'brlusd_mid', 'usdbrl_mid'
        )
        """
    )

    assert stored_catalog == 0
    assert stored_observations == 0
