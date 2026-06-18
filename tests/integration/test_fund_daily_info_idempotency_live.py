from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from typing import Any
from uuid import UUID

import pytest
from asyncpg.exceptions import (  # type: ignore[import-untyped]
    CheckViolationError,
    ForeignKeyViolationError,
    NotNullViolationError,
    UniqueViolationError,
)

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.timescale import is_timescale_available
from tests.integration.postgres_isolated_db import isolated_postgres_client


pytestmark = pytest.mark.integration

CSV_SAMPLE = """CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST
12.345.678/0001-90;2026-06-11;1500000000.00;15.432100;1498000000.00;50000.00;25000.00;12500
"""
LINEAGE_FIELDS = (
    "fund_cnpj",
    "ts",
    "total_portfolio_value",
    "quota_value",
    "net_worth",
    "inflow",
    "outflow",
    "shareholders",
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
    async with isolated_postgres_client(
        dsn, prefix="finlib_fund_idempotency"
    ) as client:
        yield client


async def _migrate(client: PostgresClient) -> None:
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for FINLIB fund tests")
    try:
        version = await client.pool.fetchval("SELECT uuid_extract_version(uuidv7())")
    except Exception as exc:
        raise AssertionError("PostgreSQL 18 uuidv7() is required") from exc
    assert version == 7
    await run_migrations(client)


async def _create_run(client: PostgresClient) -> UUID:
    run_id = await client.pool.fetchval(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, trace_id, source_snapshot_hash
        )
        VALUES(
            'cvm_informes_diarios', 'finlib-fund-test', 'execute',
            'completed', uuidv7(), 'sha256:cvm-fund-snapshot'
        )
        RETURNING run_id
        """
    )
    return UUID(str(run_id))


async def _create_fund(
    client: PostgresClient,
    *,
    fund_cnpj: str = "12345678000190",
    legal_name: str = "Synthetic Fundo de Investimento",
) -> str:
    await client.pool.execute(
        """
        INSERT INTO fund_registry(
            fund_cnpj, legal_name, cvm_class, fund_type, status, source_id
        )
        VALUES($1, $2, 'Classe CVM Sintetica', 'FI', 'active', 'cvm_informes_diarios')
        ON CONFLICT (fund_cnpj) DO UPDATE SET
            legal_name = excluded.legal_name,
            cvm_class = excluded.cvm_class,
            fund_type = excluded.fund_type,
            status = excluded.status,
            source_id = excluded.source_id
        """,
        fund_cnpj,
        legal_name,
    )
    return fund_cnpj


async def _insert_daily_info(
    client: PostgresClient,
    *,
    run_id: UUID,
    fund_cnpj: str = "12345678000190",
    ts: str = "2026-06-11 00:00:00+00",
    revision: int = 0,
    total_portfolio_value: str | None = "1500000000.00",
    quota_value: str | None = "15.432100",
    net_worth: str | None = "1498000000.00",
    inflow: str | None = "50000.00",
    outflow: str | None = "25000.00",
    shareholders: int | None = 12500,
    source_id: str = "cvm_informes_diarios",
    lineage_hash: str = "sha256:cvm-fund-2026-06-11-r0",
) -> str:
    return str(
        await client.pool.execute(
            """
            INSERT INTO fund_daily_info(
                fund_cnpj, ts, revision, total_portfolio_value, quota_value,
                net_worth, inflow, outflow, shareholders, source_id, run_id,
                lineage_hash
            )
            VALUES(
                $1, $2::timestamptz, $3, $4::numeric, $5::numeric,
                $6::numeric, $7::numeric, $8::numeric, $9, $10, $11, $12
            )
            """,
            fund_cnpj,
            _timestamp(ts),
            revision,
            _maybe_decimal(total_portfolio_value),
            _maybe_decimal(quota_value),
            _maybe_decimal(net_worth),
            _maybe_decimal(inflow),
            _maybe_decimal(outflow),
            shareholders,
            source_id,
            run_id,
            lineage_hash,
        )
    )


async def _insert_bad_daily_info_value(
    client: PostgresClient,
    *,
    run_id: UUID,
    field_name: str,
    field_value: object,
) -> str:
    lineage_hash = f"sha256:bad-{field_name}-{field_value}"
    if field_name == "quota_value":
        return await _insert_daily_info(
            client,
            run_id=run_id,
            quota_value=None if field_value is None else str(field_value),
            lineage_hash=lineage_hash,
        )
    if field_name == "net_worth":
        return await _insert_daily_info(
            client,
            run_id=run_id,
            net_worth=None if field_value is None else str(field_value),
            lineage_hash=lineage_hash,
        )
    if field_name == "shareholders":
        if not isinstance(field_value, int):
            raise TypeError("shareholders test value must be int")
        return await _insert_daily_info(
            client,
            run_id=run_id,
            shareholders=field_value,
            lineage_hash=lineage_hash,
        )
    if field_name == "inflow":
        return await _insert_daily_info(
            client,
            run_id=run_id,
            inflow=None if field_value is None else str(field_value),
            lineage_hash=lineage_hash,
        )
    if field_name == "outflow":
        return await _insert_daily_info(
            client,
            run_id=run_id,
            outflow=None if field_value is None else str(field_value),
            lineage_hash=lineage_hash,
        )
    raise AssertionError(f"unsupported field: {field_name}")


def _normalize_cnpj(value: str) -> str:
    return re.sub(r"\D", "", value)


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
    payload = {field: str(row[field]) for field in LINEAGE_FIELDS}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _sample_row() -> dict[str, Any]:
    parsed = next(csv.DictReader(StringIO(CSV_SAMPLE), delimiter=";"))
    ref_ts = _timestamp(parsed["DT_COMPTC"])
    row: dict[str, Any] = {
        "fund_cnpj": _normalize_cnpj(parsed["CNPJ_FUNDO"]),
        "ts": ref_ts.isoformat(),
        "total_portfolio_value": Decimal(parsed["VL_TOTAL"]),
        "quota_value": Decimal(parsed["VL_QUOTA"]),
        "net_worth": Decimal(parsed["VL_PATRIM_LIQ"]),
        "inflow": Decimal(parsed["CAPTC_DIA"]),
        "outflow": Decimal(parsed["RESG_DIA"]),
        "shareholders": int(parsed["NR_COTST"]),
        "source_id": "cvm_informes_diarios",
        "schema_version": 1,
    }
    row["lineage_hash"] = _lineage_hash(row)
    return row


async def test_identical_fund_daily_info_reingestion_is_noop(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    await _create_fund(postgres_client)

    await _insert_daily_info(postgres_client, run_id=run_id)
    await postgres_client.pool.execute(
        """
        INSERT INTO fund_daily_info(
            fund_cnpj, ts, revision, total_portfolio_value, quota_value,
            net_worth, inflow, outflow, shareholders, source_id, run_id,
            lineage_hash
        )
        VALUES(
            '12345678000190', '2026-06-11 00:00:00+00'::timestamptz,
            0, 1500000000.00, 15.432100, 1498000000.00, 50000.00,
            25000.00, 12500, 'cvm_informes_diarios', $1,
            'sha256:cvm-fund-2026-06-11-r0'
        )
        ON CONFLICT (lineage_hash, ts) DO NOTHING
        """,
        run_id,
    )

    count = await postgres_client.pool.fetchval("SELECT count(*) FROM fund_daily_info")

    assert count == 1


async def test_fund_daily_info_reapresentacao_preserves_history(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    await _create_fund(postgres_client)

    await _insert_daily_info(postgres_client, run_id=run_id)
    await _insert_daily_info(
        postgres_client,
        run_id=run_id,
        revision=1,
        quota_value="15.500000",
        lineage_hash="sha256:cvm-fund-2026-06-11-r1",
    )
    with pytest.raises(UniqueViolationError):
        await _insert_daily_info(
            postgres_client,
            run_id=run_id,
            revision=0,
            quota_value="15.600000",
            lineage_hash="sha256:cvm-fund-2026-06-11-r0-duplicate-revision",
        )

    rows = await postgres_client.pool.fetch(
        """
        SELECT revision, quota_value
        FROM fund_daily_info
        WHERE fund_cnpj = '12345678000190'
          AND ts = '2026-06-11 00:00:00+00'::timestamptz
        ORDER BY revision
        """
    )

    assert [(row["revision"], row["quota_value"]) for row in rows] == [
        (0, Decimal("15.432100")),
        (1, Decimal("15.500000")),
    ]


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    (
        pytest.param("quota_value", None, id="null-quota"),
        pytest.param("quota_value", "0", id="zero-quota"),
        pytest.param("quota_value", "-0.01", id="negative-quota"),
        pytest.param("net_worth", None, id="null-net-worth"),
        pytest.param("shareholders", -1, id="negative-shareholders"),
        pytest.param("inflow", "-0.01", id="negative-inflow"),
        pytest.param("outflow", "-0.01", id="negative-outflow"),
    ),
)
async def test_fund_daily_info_quality_checks_reject_bad_values(
    postgres_client: PostgresClient,
    field_name: str,
    field_value: object,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    await _create_fund(postgres_client)

    with pytest.raises((CheckViolationError, NotNullViolationError)):
        await _insert_bad_daily_info_value(
            postgres_client,
            run_id=run_id,
            field_name=field_name,
            field_value=field_value,
        )


async def test_fund_daily_info_allows_negative_net_worth_and_null_flows(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    await _create_fund(postgres_client)

    await _insert_daily_info(
        postgres_client,
        run_id=run_id,
        net_worth="-1000.00",
        inflow=None,
        outflow=None,
        lineage_hash="sha256:negative-net-worth-null-flows",
    )

    row = await postgres_client.pool.fetchrow(
        """
        SELECT net_worth, inflow, outflow
        FROM fund_daily_info
        WHERE lineage_hash = 'sha256:negative-net-worth-null-flows'
        """
    )

    assert row is not None
    assert row["net_worth"] == Decimal("-1000.00")
    assert row["inflow"] is None
    assert row["outflow"] is None


async def test_fund_daily_info_rejects_missing_fk_and_lineage(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    await _create_fund(postgres_client)

    with pytest.raises(ForeignKeyViolationError):
        await _insert_daily_info(
            postgres_client,
            run_id=run_id,
            source_id="missing_source",
            lineage_hash="sha256:missing-source",
        )

    with pytest.raises(ForeignKeyViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO fund_daily_info(
                fund_cnpj, ts, quota_value, net_worth, shareholders, source_id,
                run_id, lineage_hash
            )
            VALUES(
                '12345678000190', '2026-06-11 00:00:00+00'::timestamptz,
                15.432100, 1498000000.00, 12500, 'cvm_informes_diarios',
                '00000000-0000-7000-8000-000000000001'::uuid,
                'sha256:missing-run'
            )
            """
        )

    with pytest.raises(NotNullViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO fund_daily_info(
                fund_cnpj, ts, quota_value, net_worth, shareholders, source_id,
                run_id
            )
            VALUES(
                '12345678000190', '2026-06-11 00:00:00+00'::timestamptz,
                15.432100, 1498000000.00, 12500, 'cvm_informes_diarios', $1
            )
            """,
            run_id,
        )

    with pytest.raises(CheckViolationError):
        await _insert_daily_info(
            postgres_client,
            run_id=run_id,
            lineage_hash="\t",
        )


async def test_fund_daily_info_rejects_json_arrays(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    await _create_fund(postgres_client)

    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO fund_daily_info(
                fund_cnpj, ts, quota_value, net_worth, shareholders, source_id,
                run_id, lineage_hash, quality_flags
            )
            VALUES(
                '12345678000190', '2026-06-11 00:00:00+00'::timestamptz,
                15.432100, 1498000000.00, 12500, 'cvm_informes_diarios',
                $1, 'sha256:bad-quality-flags', '[]'::jsonb
            )
            """,
            run_id,
        )
    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO fund_daily_info(
                fund_cnpj, ts, quota_value, net_worth, shareholders, source_id,
                run_id, lineage_hash, metadata
            )
            VALUES(
                '12345678000190', '2026-06-11 00:00:00+00'::timestamptz,
                15.432100, 1498000000.00, 12500, 'cvm_informes_diarios',
                $1, 'sha256:bad-metadata', '[]'::jsonb
            )
            """,
            run_id,
        )


async def test_ops_data_quality_check_accepts_fund_run(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)

    check_id = await postgres_client.pool.fetchval(
        """
        INSERT INTO ops_data_quality_checks(
            run_id, check_name, target_table, severity, passed, observed, expected
        )
        VALUES(
            $1, 'fund_daily_info_sample_contract', 'fund_daily_info', 'info',
            true, '{}'::jsonb, '{}'::jsonb
        )
        RETURNING check_id
        """,
        run_id,
    )
    audit_count = await postgres_client.pool.fetchval(
        "SELECT count(*) FROM audit_agent_writes"
    )

    assert UUID(str(check_id))
    assert audit_count == 0


async def test_csv_sample_normalizes_and_inserts_fund_rows(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    row = _sample_row()
    run_id = await _create_run(postgres_client)
    await _create_fund(
        postgres_client,
        fund_cnpj=str(row["fund_cnpj"]),
        legal_name="Synthetic CVM Fund",
    )

    await _insert_daily_info(
        postgres_client,
        run_id=run_id,
        fund_cnpj=str(row["fund_cnpj"]),
        ts=str(row["ts"]),
        total_portfolio_value=str(row["total_portfolio_value"]),
        quota_value=str(row["quota_value"]),
        net_worth=str(row["net_worth"]),
        inflow=str(row["inflow"]),
        outflow=str(row["outflow"]),
        shareholders=int(row["shareholders"]),
        lineage_hash=str(row["lineage_hash"]),
    )

    stored = await postgres_client.pool.fetchrow(
        "SELECT * FROM fund_daily_info WHERE fund_cnpj = $1 AND ts = $2::timestamptz",
        row["fund_cnpj"],
        _timestamp(str(row["ts"])),
    )

    assert stored is not None
    assert stored["quota_value"] == Decimal("15.432100")
    assert stored["net_worth"] == Decimal("1498000000.00")
    assert stored["shareholders"] == 12500
    assert stored["lineage_hash"] == row["lineage_hash"]
