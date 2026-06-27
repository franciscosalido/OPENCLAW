from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from asyncpg.exceptions import CheckViolationError  # type: ignore[import-untyped]

from backend.finlib.repositories import (
    AuditContext,
    DataQualityCheckInput,
    DataSourceInput,
    IngestionRunInput,
    MacroObservationInput,
    MacroRepository,
    MacroSeriesInput,
    OpsRepository,
    OutboxEventInput,
    RunAlreadyFinishedError,
    TreasuryBondInput,
    TreasuryPriceInput,
    TreasuryRepository,
    WatermarkInput,
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
    async with isolated_postgres_client(dsn, prefix="finlib_repositories") as client:
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
        agent_id="finlib-repository-test",
        batch_hash=batch_hash or f"sha256:{token}",
        metadata={"test": "finlib-repositories-core"},
    )


async def _audit_count(client: PostgresClient) -> int:
    return int(await client.pool.fetchval("SELECT count(*) FROM audit_agent_writes"))


async def _macro_count(client: PostgresClient, series_code: str) -> int:
    return int(
        await client.pool.fetchval(
            "SELECT count(*) FROM macro_observations WHERE series_code = $1",
            series_code,
        )
    )


async def _treasury_price_count(client: PostgresClient, bond_id: UUID) -> int:
    return int(
        await client.pool.fetchval(
            "SELECT count(*) FROM treasury_prices WHERE bond_id = $1",
            bond_id,
        )
    )


async def test_finlib_repositories_core_flow_and_atomicity(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    ops = OpsRepository(postgres_client)
    macro = MacroRepository(postgres_client)
    treasury = TreasuryRepository(postgres_client)

    await ops.register_source(
        DataSourceInput(
            source_id="repo_test_source",
            kind="internal",
            methodology_limitations="synthetic repository integration source",
            metadata={"scope": "test"},
        ),
        audit=_audit(suffix="register-source"),
    )
    run_id = await ops.start_run(
        IngestionRunInput(
            source_id="repo_test_source",
            agent_id="finlib-repository-test",
            trace_id=uuid4(),
            mode="dry_run",
        ),
        audit=_audit(suffix="start-run"),
    )

    await macro.upsert_series_catalog(
        [
            MacroSeriesInput(
                series_code="repo_ipca",
                display_name="Repository IPCA",
                provider="bcb_sgs",
                provider_code="433",
                source_id="bcb_sgs",
                unit="percent",
                periodicity="monthly",
                value_type="rate_percent",
                methodology_note="synthetic repository test series",
            )
        ],
        audit=_audit(run_id=run_id, suffix="macro-catalog"),
    )
    first_macro = MacroObservationInput(
        series_code="repo_ipca",
        ref_ts="2026-01-01T00:00:00+00:00",
        value="0.42",
        source_id="bcb_sgs",
        run_id=run_id,
        lineage_hash="sha256:repo-ipca-v0",
    )
    repeated_macro = await macro.upsert_observations_batch(
        [first_macro],
        audit=_audit(run_id=run_id, suffix="macro-observation-v0"),
    )
    duplicate_macro = await macro.upsert_observations_batch(
        [first_macro],
        audit=_audit(run_id=run_id, suffix="macro-observation-duplicate"),
    )
    revised_macro = await macro.upsert_observations_batch(
        [
            MacroObservationInput(
                series_code="repo_ipca",
                ref_ts="2026-01-01T00:00:00+00:00",
                value="0.43",
                source_id="bcb_sgs",
                run_id=run_id,
                lineage_hash="sha256:repo-ipca-v1",
            )
        ],
        audit=_audit(run_id=run_id, suffix="macro-observation-v1"),
    )

    assert repeated_macro.inserted == 1
    assert duplicate_macro.skipped == 1
    assert revised_macro.inserted == 1
    revisions = await postgres_client.pool.fetch(
        """
        SELECT revision, value
        FROM macro_observations
        WHERE series_code = 'repo_ipca'
        ORDER BY revision
        """
    )
    assert [(row["revision"], str(row["value"])) for row in revisions] == [
        (0, "0.42"),
        (1, "0.43"),
    ]

    bond_result = await treasury.upsert_bonds_batch(
        [
            TreasuryBondInput(
                bond_type="Tesouro_Selic",
                maturity_date="2029-03-01",
                display_name="Tesouro Selic 2029",
                source_id="tesouro_transparente",
            )
        ],
        audit=_audit(run_id=run_id, suffix="treasury-bond"),
    )
    assert bond_result.inserted == 1
    bond_id = UUID(
        str(
            await postgres_client.pool.fetchval(
                """
                SELECT bond_id
                FROM treasury_bonds
                WHERE bond_type = 'Tesouro_Selic'
                  AND maturity_date = '2029-03-01'
                """
            )
        )
    )
    price = TreasuryPriceInput(
        bond_id=bond_id,
        ts="2026-01-02T00:00:00+00:00",
        price_bid="1000.00",
        price_ask="1001.00",
        source_id="tesouro_transparente",
        run_id=run_id,
        lineage_hash="sha256:treasury-price-v0",
    )
    price_result = await treasury.upsert_prices_batch(
        [price],
        audit=_audit(run_id=run_id, suffix="treasury-price-v0"),
    )
    price_duplicate = await treasury.upsert_prices_batch(
        [price],
        audit=_audit(run_id=run_id, suffix="treasury-price-duplicate"),
    )
    assert price_result.inserted == 1
    assert price_duplicate.skipped == 1

    await ops.record_quality_check(
        DataQualityCheckInput(
            run_id=run_id,
            check_name="repo-flow",
            target_table="macro_observations",
            severity="info",
            passed=True,
        ),
        audit=_audit(run_id=run_id, suffix="quality"),
    )
    await ops.set_watermark(
        WatermarkInput(
            source_id="repo_test_source",
            dataset="repo-flow",
            watermark_value="2026-01-02",
            watermark_ts="2026-01-02T00:00:00+00:00",
            run_id=run_id,
        ),
        audit=_audit(run_id=run_id, suffix="watermark-forward"),
    )
    regressed = await ops.set_watermark(
        WatermarkInput(
            source_id="repo_test_source",
            dataset="repo-flow",
            watermark_value="2026-01-01",
            watermark_ts="2026-01-01T00:00:00+00:00",
            run_id=run_id,
        ),
        audit=_audit(run_id=run_id, suffix="watermark-regress"),
    )
    watermark = await ops.get_watermark(
        source_id="repo_test_source",
        dataset="repo-flow",
    )
    assert regressed.skipped == 1
    assert watermark is not None
    assert watermark["watermark_value"] == "2026-01-02"

    for index in range(2):
        await ops.enqueue_event(
            OutboxEventInput(
                event_type="finlib.repo.test",
                aggregate_type="ingestion_run",
                aggregate_id=f"run-{index}",
                payload={"index": index},
                run_id=run_id,
                trace_id=uuid4(),
            ),
            audit=_audit(run_id=run_id, suffix=f"event-{index}"),
        )

    first, second = await asyncio.gather(
        ops.poll_events(
            limit=1,
            locked_by="worker-a",
            audit=_audit(run_id=run_id, suffix="poll-a"),
            event_types=["finlib.repo.test"],
        ),
        ops.poll_events(
            limit=1,
            locked_by="worker-b",
            audit=_audit(run_id=run_id, suffix="poll-b"),
            event_types=["finlib.repo.test"],
        ),
    )
    first_ids = {event.event_id for event in first}
    second_ids = {event.event_id for event in second}
    assert first_ids
    assert second_ids
    assert first_ids.isdisjoint(second_ids)
    assert {event.locked_by for event in [*first, *second]} == {"worker-a", "worker-b"}

    await ops.finish_run(
        run_id,
        status="completed",
        records_seen=3,
        records_inserted=3,
        audit=_audit(run_id=run_id, suffix="finish-run"),
    )
    with pytest.raises(RunAlreadyFinishedError):
        await ops.finish_run(
            run_id,
            status="completed",
            audit=_audit(run_id=run_id, suffix="finish-run-again"),
        )

    assert await _audit_count(postgres_client) == 17

    before_macro = await _macro_count(postgres_client, "repo_ipca")
    before_audit = await _audit_count(postgres_client)
    with pytest.raises(CheckViolationError):
        await macro.upsert_observations_batch(
            [
                MacroObservationInput(
                    series_code="repo_ipca",
                    ref_ts="2026-02-01T00:00:00+00:00",
                    value="0.44",
                    source_id="bcb_sgs",
                    run_id=run_id,
                    lineage_hash="\t",
                )
            ],
            audit=_audit(run_id=run_id, suffix="macro-invalid"),
        )
    assert await _macro_count(postgres_client, "repo_ipca") == before_macro
    assert await _audit_count(postgres_client) == before_audit

    with pytest.raises(ValueError, match="batch_hash"):
        await macro.upsert_observations_batch(
            [
                MacroObservationInput(
                    series_code="repo_ipca",
                    ref_ts="2026-03-01T00:00:00+00:00",
                    value="0.45",
                    source_id="bcb_sgs",
                    run_id=run_id,
                    lineage_hash="sha256:repo-ipca-audit-fail",
                )
            ],
            audit=_audit(run_id=run_id, batch_hash="\t"),
        )
    assert await _macro_count(postgres_client, "repo_ipca") == before_macro
    assert await _audit_count(postgres_client) == before_audit

    before_prices = await _treasury_price_count(postgres_client, bond_id)
    with pytest.raises(CheckViolationError):
        await treasury.upsert_prices_batch(
            [
                TreasuryPriceInput(
                    bond_id=bond_id,
                    ts=datetime(2026, 1, 3, tzinfo=timezone.utc),
                    price_bid="1000.00",
                    source_id="tesouro_transparente",
                    run_id=run_id,
                    lineage_hash="sha256:treasury-price-valid-rollback",
                ),
                TreasuryPriceInput(
                    bond_id=bond_id,
                    ts=datetime(2026, 1, 4, tzinfo=timezone.utc),
                    price_bid="-1.00",
                    source_id="tesouro_transparente",
                    run_id=run_id,
                    lineage_hash="sha256:treasury-price-invalid-rollback",
                ),
            ],
            audit=_audit(run_id=run_id, suffix="treasury-invalid"),
        )
    assert await _treasury_price_count(postgres_client, bond_id) == before_prices
    assert await _audit_count(postgres_client) == before_audit


async def test_outbox_payload_rejects_level0_before_write(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    ops = OpsRepository(postgres_client)

    with pytest.raises(ValueError, match="Level 0"):
        await ops.enqueue_event(
            OutboxEventInput(
                event_type="finlib.repo.test",
                aggregate_type="position",
                aggregate_id="private",
                payload={"cpf": "00000000000"},
            ),
            audit=_audit(suffix="level0-event"),
        )
    assert await _audit_count(postgres_client) == 0
