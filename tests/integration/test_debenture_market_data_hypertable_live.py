from __future__ import annotations

import hashlib
import json
import os
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from asyncpg.exceptions import (  # type: ignore[import-untyped]
    CheckViolationError,
    ForeignKeyViolationError,
    PostgresError,
    UniqueViolationError,
)

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.timescale import is_hypertable, is_timescale_available
from tests.integration.postgres_isolated_db import isolated_postgres_client


pytestmark = pytest.mark.integration

LINEAGE_FIELDS = (
    "fi_id",
    "ts",
    "indicative_rate",
    "pu",
    "duration",
    "source_id",
    "schema_version",
)


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    async with isolated_postgres_client(dsn, prefix="finlib_debenture") as client:
        yield client


async def _migrate(client: PostgresClient) -> None:
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for FINLIB debenture tests")
    try:
        version = await client.pool.fetchval("SELECT uuid_extract_version(uuidv7())")
    except Exception as exc:
        raise AssertionError("PostgreSQL 18 uuidv7() is required") from exc
    assert version == 7
    await run_migrations(client)


async def _create_run(
    client: PostgresClient,
    *,
    source_id: str = "anbima_debentures",
    snapshot_hash: str = "sha256:anbima-debenture-snapshot",
) -> UUID:
    run_id = await client.pool.fetchval(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, trace_id, source_snapshot_hash
        )
        VALUES($1, 'finlib-debenture-test', 'execute', 'completed', uuidv7(), $2)
        RETURNING run_id
        """,
        source_id,
        snapshot_hash,
    )
    return UUID(str(run_id))


async def _create_instrument(
    client: PostgresClient,
    *,
    kind: str = "debenture",
    issuer_cnpj: str = "11222333000181",
    instrument_name: str = "Synthetic Debenture IPCA 2032",
    source_id: str = "anbima_debentures",
    lineage_hash: str = "sha256:fi-debenture-synthetic",
    fgc_covered: bool = False,
) -> UUID:
    rate_spec = {
        "indexer": "ipca",
        "rate_model": "inflation_plus_coupon",
        "coupon": "0.0625",
        "day_count": 252,
        "payment_frequency": "annual",
    }
    if kind == "cdb":
        source_id = "local_fixed_income_input"
        rate_spec = {
            "indexer": "cdi",
            "rate_model": "percent_of_indexer",
            "percent": "1.02",
            "day_count": 252,
            "payment_frequency": "none",
        }
    instrument_id = await client.pool.fetchval(
        """
        INSERT INTO fi_instruments(
            kind, issuer_cnpj, issuer_name, instrument_name, isin, indexer,
            rate_spec, fgc_covered, issue_date, maturity_date, source_id,
            lineage_hash
        )
        VALUES(
            $1, $2, 'Synthetic Issuer SA', $3, NULL, 'ipca',
            $4::text::jsonb, $5, '2026-01-01', '2032-01-01', $6, $7
        )
        RETURNING instrument_id
        """,
        kind,
        issuer_cnpj,
        instrument_name,
        json.dumps(rate_spec, sort_keys=True),
        fgc_covered,
        source_id,
        lineage_hash,
    )
    return UUID(str(instrument_id))


async def _insert_market_data(
    client: PostgresClient,
    *,
    fi_id: UUID,
    run_id: UUID,
    ts: str = "2026-06-11 00:00:00+00",
    revision: int = 0,
    indicative_rate: str | None = "0.0715",
    pu: str | None = "984.12",
    duration: int | None = 842,
    source_id: str = "anbima_debentures",
    lineage_hash: str | None = None,
) -> str:
    ref_ts = _timestamp(ts)
    computed_hash = lineage_hash or _lineage_hash(
        {
            "fi_id": str(fi_id),
            "ts": ref_ts.isoformat(),
            "indicative_rate": indicative_rate,
            "pu": pu,
            "duration": duration,
            "source_id": source_id,
            "schema_version": 1,
        }
    )
    return str(
        await client.pool.execute(
            """
            INSERT INTO debenture_market_data(
                fi_id, ts, revision, indicative_rate, pu, duration,
                source_id, run_id, lineage_hash
            )
            VALUES(
                $1, $2, $3, $4::numeric, $5::numeric, $6, $7, $8, $9
            )
            """,
            fi_id,
            ref_ts,
            revision,
            _maybe_decimal(indicative_rate),
            _maybe_decimal(pu),
            duration,
            source_id,
            run_id,
            computed_hash,
        )
    )


def _timestamp(value: str) -> datetime:
    normalized = value
    if normalized.endswith("+00"):
        normalized = f"{normalized}:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _maybe_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value)


def _lineage_hash(row: dict[str, Any]) -> str:
    payload = {field: row[field] for field in LINEAGE_FIELDS}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


async def test_debenture_migration_applies_idempotently(
    postgres_client: PostgresClient,
) -> None:
    async with postgres_client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for FINLIB debenture tests")

    first = await run_migrations(postgres_client)
    second = await run_migrations(postgres_client)

    assert "026_create_debenture_market_data" in first
    assert second == ()


async def test_debenture_market_data_hypertable_indexes_and_trigger_exist(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    assert (
        await postgres_client.pool.fetchval(
            "SELECT to_regclass('public.debenture_market_data')"
        )
        == "debenture_market_data"
    )
    async with postgres_client.pool.acquire() as conn:
        assert await is_hypertable(conn, "debenture_market_data")

    rows = await postgres_client.pool.fetch(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'debenture_market_data'
        """
    )
    index_names = {str(row["indexname"]) for row in rows}
    assert "debenture_market_data_pkey" in index_names
    assert "uq_debenture_market_data_lineage_ts" in index_names
    assert "idx_debenture_market_data_fi_ts_revision" in index_names
    assert "idx_debenture_market_data_run_id" in index_names

    trigger_name = await postgres_client.pool.fetchval(
        """
        SELECT tgname
        FROM pg_trigger
        WHERE tgrelid = 'debenture_market_data'::regclass
          AND tgname = 'trg_debenture_market_data_instrument_kind'
          AND NOT tgisinternal
        """
    )
    assert trigger_name == "trg_debenture_market_data_instrument_kind"


async def test_debenture_hypertable_dimension_and_unique_constraints_include_ts(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    dimension = await postgres_client.pool.fetchrow(
        """
        SELECT *
        FROM timescaledb_information.dimensions
        WHERE hypertable_schema = 'public'
          AND hypertable_name = 'debenture_market_data'
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
        WHERE con.conrelid = 'debenture_market_data'::regclass
          AND con.contype IN ('p', 'u')
        GROUP BY con.conname
        """
    )

    assert dimension is not None
    values = " ".join(str(value).lower() for value in dimension.values())
    assert "ts" in values
    assert "1 mon" in values or "1 month" in values or "30 days" in values
    for row in constraints:
        assert "ts" in {str(column) for column in row["columns"]}


async def test_debenture_valid_insert_and_kind_guard(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    debenture_id = await _create_instrument(postgres_client)
    cdb_id = await _create_instrument(
        postgres_client,
        kind="cdb",
        issuer_cnpj="99888777000166",
        instrument_name="Synthetic CDB CDI",
        lineage_hash="sha256:fi-cdb-synthetic",
        fgc_covered=True,
    )

    await _insert_market_data(postgres_client, fi_id=debenture_id, run_id=run_id)
    count = await postgres_client.pool.fetchval(
        "SELECT count(*) FROM debenture_market_data WHERE fi_id = $1",
        debenture_id,
    )
    with pytest.raises(PostgresError, match="requires a debenture instrument"):
        await _insert_market_data(
            postgres_client,
            fi_id=cdb_id,
            run_id=run_id,
            ts="2026-06-12 00:00:00+00",
            lineage_hash="sha256:non-debenture-rejected",
        )

    assert count == 1


async def test_debenture_rejects_missing_foreign_keys(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    debenture_id = await _create_instrument(postgres_client)

    with pytest.raises(ForeignKeyViolationError):
        await _insert_market_data(
            postgres_client,
            fi_id=UUID("00000000-0000-7000-8000-000000000001"),
            run_id=run_id,
            lineage_hash="sha256:missing-fi",
        )
    with pytest.raises(ForeignKeyViolationError):
        await _insert_market_data(
            postgres_client,
            fi_id=debenture_id,
            run_id=UUID("00000000-0000-7000-8000-000000000002"),
            ts="2026-06-12 00:00:00+00",
            lineage_hash="sha256:missing-run",
        )


@pytest.mark.parametrize(
    ("field_name", "field_value", "expected_error"),
    (
        pytest.param("pu", "0", CheckViolationError, id="zero-pu"),
        pytest.param("pu", "-1.00", CheckViolationError, id="negative-pu"),
        pytest.param("duration", -1, CheckViolationError, id="negative-duration"),
        pytest.param("revision", -1, CheckViolationError, id="negative-revision"),
        pytest.param("lineage_hash", "\t", CheckViolationError, id="tab-lineage"),
    ),
)
async def test_debenture_data_quality_constraints(
    postgres_client: PostgresClient,
    field_name: str,
    field_value: object,
    expected_error: type[Exception],
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    debenture_id = await _create_instrument(
        postgres_client,
        issuer_cnpj=f"11222333000{len(field_name):03d}",
        instrument_name=f"Synthetic Debenture {field_name}",
        lineage_hash=f"sha256:fi-debenture-{field_name}",
    )
    kwargs: dict[str, Any] = {
        "fi_id": debenture_id,
        "run_id": run_id,
        "ts": "2026-07-01 00:00:00+00",
        "lineage_hash": f"sha256:bad-{field_name}",
    }
    kwargs[field_name] = field_value

    with pytest.raises(expected_error):
        await _insert_market_data(postgres_client, **kwargs)


async def test_debenture_rejects_all_null_measurements_and_bad_json(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    debenture_id = await _create_instrument(postgres_client)

    with pytest.raises(CheckViolationError):
        await _insert_market_data(
            postgres_client,
            fi_id=debenture_id,
            run_id=run_id,
            ts="2026-08-01 00:00:00+00",
            indicative_rate=None,
            pu=None,
            duration=None,
            lineage_hash="sha256:all-null-measurements",
        )
    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO debenture_market_data(
                fi_id, ts, indicative_rate, source_id, run_id, lineage_hash,
                metadata
            )
            VALUES(
                $1, '2026-08-02 00:00:00+00'::timestamptz, 0.0715,
                'anbima_debentures', $2, 'sha256:bad-metadata', '[]'::jsonb
            )
            """,
            debenture_id,
            run_id,
        )
    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO debenture_market_data(
                fi_id, ts, indicative_rate, source_id, run_id, lineage_hash,
                quality_flags
            )
            VALUES(
                $1, '2026-08-03 00:00:00+00'::timestamptz, 0.0715,
                'anbima_debentures', $2, 'sha256:bad-quality-flags',
                '[]'::jsonb
            )
            """,
            debenture_id,
            run_id,
        )


async def test_debenture_identical_reingestion_is_noop_and_revision_preserves_history(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    first_run_id = await _create_run(postgres_client)
    second_run_id = await _create_run(
        postgres_client,
        snapshot_hash="sha256:anbima-debenture-snapshot-2",
    )
    debenture_id = await _create_instrument(postgres_client)

    await _insert_market_data(
        postgres_client,
        fi_id=debenture_id,
        run_id=first_run_id,
        lineage_hash="sha256:debenture-r0",
    )
    await postgres_client.pool.execute(
        """
        INSERT INTO debenture_market_data(
            fi_id, ts, revision, indicative_rate, pu, duration, source_id,
            run_id, lineage_hash
        )
        VALUES(
            $1, '2026-06-11 00:00:00+00'::timestamptz, 0, 0.0715,
            984.12, 842, 'anbima_debentures', $2, 'sha256:debenture-r0'
        )
        ON CONFLICT (lineage_hash, ts) DO NOTHING
        """,
        debenture_id,
        second_run_id,
    )
    await _insert_market_data(
        postgres_client,
        fi_id=debenture_id,
        run_id=second_run_id,
        revision=1,
        indicative_rate="0.0730",
        pu="985.00",
        duration=841,
        lineage_hash="sha256:debenture-r1",
    )
    with pytest.raises(UniqueViolationError):
        await _insert_market_data(
            postgres_client,
            fi_id=debenture_id,
            run_id=second_run_id,
            revision=0,
            indicative_rate="0.0740",
            lineage_hash="sha256:debenture-r0-duplicate-revision",
        )

    rows = await postgres_client.pool.fetch(
        """
        SELECT revision, indicative_rate, pu, duration
        FROM debenture_market_data
        WHERE fi_id = $1
          AND ts = '2026-06-11 00:00:00+00'::timestamptz
        ORDER BY revision
        """,
        debenture_id,
    )

    assert [
        (row["revision"], row["indicative_rate"], row["pu"], row["duration"])
        for row in rows
    ] == [
        (0, Decimal("0.0715"), Decimal("984.12"), 842),
        (1, Decimal("0.0730"), Decimal("985.00"), 841),
    ]


async def test_debenture_source_limitations_and_cross_sprint_tables(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    source = await postgres_client.pool.fetchrow(
        "SELECT * FROM ops_data_sources WHERE source_id = 'anbima_debentures'"
    )
    for table_name in (
        "ops_data_quality_checks",
        "audit_agent_writes",
        "fi_instruments",
    ):
        assert (
            await postgres_client.pool.fetchval(
                f"SELECT to_regclass('public.{table_name}')"
            )
            == table_name
        )

    assert source is not None
    limitations = str(source["methodology_limitations"]).lower()
    for expected in ("secundario", "amostra", "acesso", "historico", "retificacao"):
        assert expected in limitations
    assert "client_secret" not in limitations
    assert "api_key" not in limitations
    assert (
        await postgres_client.pool.fetchval("SELECT count(*) FROM audit_agent_writes")
        == 0
    )
