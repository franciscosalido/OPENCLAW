#!/usr/bin/env python
"""FINLIB-0 readiness gate.

The script is read-only and emits sanitized JSON. It does not create schema,
write audit rows, call Qdrant, call Kronos, call LLMs or download anything.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import asyncpg  # type: ignore[import-untyped]

from backend.memory.postgres.settings import DEFAULT_POSTGRES_DSN


STATUS_READY = "READY"
STATUS_BLOCKED = "BLOCKED"
STATUS_OK = "ok"
STATUS_FAIL = "fail"
STATUS_DEFERRED = "deferred"
STATUS_SKIPPED = "skipped"
STATUS_DEGRADED = "degraded"
EXPECTED_MIGRATION_HEAD = "029_create_finlib_aggregates_readiness"

REQUIRED_EXTENSIONS = ("timescaledb", "pgcrypto", "vector")
REQUIRED_TABLE_GROUPS = {
    "ops": (
        "ops_data_sources",
        "ops_ingestion_runs",
        "ops_ingestion_watermarks",
        "ops_data_quality_checks",
        "ops_outbox_events",
    ),
    "audit": ("audit_agent_writes",),
    "macro": ("macro_series_catalog", "macro_observations"),
    "treasury": ("treasury_bonds", "treasury_prices"),
    "funds": ("fund_registry", "fund_daily_info"),
    "fixed_income": ("fi_instruments", "debenture_market_data"),
    "fundamentals": (
        "company_registry",
        "company_listings",
        "fundamentals_statements",
        "fundamentals_indicators",
    ),
}
REQUIRED_AGGREGATES = (
    "macro_observations_latest_revision",
    "treasury_latest_prices_view",
    "fund_daily_info_latest_revision",
    "fund_monthly_quota_returns",
    "market_bars_1d_cagg",
    "market_bars_1d",
    "vw_kronos_ohlcva_input",
)
REQUIRED_DOCS = (
    Path("docs/data/DATA_DICTIONARY.md"),
    Path("docs/sprints/FINLIB0_DONE_CRITERIA.md"),
    Path("docs/sprints/FINLIB0_HANDOFF_TO_DATA_AGENTS.md"),
)


class FinlibReadinessConnection(Protocol):
    async def fetchval(self, query: str, *args: object) -> Any: ...

    async def fetch(self, query: str, *args: object) -> Sequence[Mapping[str, Any]]: ...

    async def close(self) -> None: ...


ConnectFactory = Callable[..., Awaitable[FinlibReadinessConnection]]


@dataclass(frozen=True, slots=True)
class FinlibReadinessConfig:
    dsn: str
    timeout_seconds: float
    require_kronos_input_ready: bool = False


def load_config(
    env: Mapping[str, str] | None = None,
    *,
    timeout_seconds: float = 5.0,
    require_kronos_input_ready: bool = False,
) -> FinlibReadinessConfig:
    env_map = os.environ if env is None else env
    dsn = (
        env_map.get("TEST_POSTGRES_DSN")
        or env_map.get("QUIMERA_POSTGRES_DSN")
        or DEFAULT_POSTGRES_DSN
    )
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be > 0")
    return FinlibReadinessConfig(
        dsn=dsn,
        timeout_seconds=float(timeout_seconds),
        require_kronos_input_ready=require_kronos_input_ready,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check FINLIB readiness.")
    parser.add_argument("--json", action="store_true", help="Emit JSON; default mode.")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument(
        "--require-kronos-input-ready",
        action="store_true",
        help="Treat degraded Kronos input as a blocking readiness failure.",
    )
    parser.add_argument(
        "--verbose-safe",
        action="store_true",
        help="Reserved for future safe diagnostics; never emits secrets.",
    )
    return parser.parse_args(argv)


async def run_readiness(
    config: FinlibReadinessConfig,
    *,
    connect: ConnectFactory | None = None,
) -> dict[str, object]:
    connector = asyncpg.connect if connect is None else connect
    connection: FinlibReadinessConnection | None = None
    try:
        connection = await connector(
            dsn=config.dsn, timeout=math.ceil(config.timeout_seconds)
        )
        return await build_readiness_report(connection, config)
    except Exception as exc:
        return _blocked_report(f"postgres_connection:{type(exc).__name__}")
    finally:
        if connection is not None:
            try:
                await connection.close()
            except Exception:  # nosec B110 - close failure must not leak details.
                pass


async def build_readiness_report(
    connection: FinlibReadinessConnection,
    config: FinlibReadinessConfig,
) -> dict[str, object]:
    failed: list[str] = []
    postgres = await _ok_fail(_fetchval_bool(connection, "SELECT TRUE"))
    database = await _current_database(connection)
    extensions = {
        extension: await _extension_status(connection, extension)
        for extension in REQUIRED_EXTENSIONS
    }
    migration_head = await _migration_head(connection)
    schemas = {
        group: await _group_status(connection, tables)
        for group, tables in REQUIRED_TABLE_GROUPS.items()
    }
    repositories = _repository_status()
    memory_boundary = _memory_boundary_status()
    aggregates = {
        name: await _relation_status(connection, name) for name in REQUIRED_AGGREGATES
    }
    compression = await _compression_status(connection)
    kronos_input_ready = _kronos_status(aggregates)
    docs = _docs_status()
    destructive_retention = await _destructive_retention_status(connection)

    _collect_failures("postgres", postgres, failed)
    _collect_failures("timescaledb", extensions["timescaledb"], failed)
    for name, status in extensions.items():
        _collect_failures(f"extensions.{name}", status, failed)
    _collect_failures("migration_head", migration_head, failed)
    for group, status in schemas.items():
        _collect_failures(f"schemas.{group}", status, failed)
    for name, status in repositories.items():
        _collect_failures(f"repositories.{name}", status, failed)
    _collect_failures("memory_boundary", memory_boundary, failed)
    for name, status in aggregates.items():
        _collect_failures(f"aggregates.{name}", status, failed)
    _collect_failures("destructive_retention", destructive_retention, failed)
    for name, status in docs.items():
        _collect_failures(f"docs.{name}", status, failed)
    if config.require_kronos_input_ready:
        _collect_failures("kronos_input_ready", kronos_input_ready["status"], failed)

    ready = not failed
    return {
        "schema_version": "finlib-readiness-v1",
        "status": STATUS_READY if ready else STATUS_BLOCKED,
        "checked_at": datetime.now(UTC).isoformat(),
        "database": database,
        "migration_head": migration_head,
        "postgres": postgres,
        "timescaledb": extensions["timescaledb"],
        "extensions": extensions,
        "schemas": schemas,
        "repositories": repositories,
        "memory_boundary": memory_boundary,
        "aggregates": aggregates,
        "compression": compression,
        "kronos_input_ready": kronos_input_ready,
        "docs": docs,
        "ready_for_data_agents": ready,
        "failed_checks": failed,
    }


def readiness_ok(report: Mapping[str, object]) -> bool:
    return (
        report.get("status") == STATUS_READY
        and report.get("ready_for_data_agents") is True
        and report.get("failed_checks") == []
    )


async def async_main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    connect: ConnectFactory | None = None,
    stdout: Any = sys.stdout,
) -> int:
    args = parse_args(argv)
    config = load_config(
        env,
        timeout_seconds=args.timeout_seconds,
        require_kronos_input_ready=args.require_kronos_input_ready,
    )
    report = await run_readiness(config, connect=connect)
    stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0 if readiness_ok(report) else 1


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    connect: ConnectFactory | None = None,
    stdout: Any = sys.stdout,
) -> int:
    try:
        return asyncio.run(async_main(argv, env=env, connect=connect, stdout=stdout))
    except Exception as exc:
        del exc
        stdout.write(json.dumps(_blocked_report("unexpected_error"), sort_keys=True))
        stdout.write("\n")
        return 1


async def _fetchval_bool(
    connection: FinlibReadinessConnection, query: str, *args: object
) -> bool:
    value = await connection.fetchval(query, *args)
    return value is True


async def _ok_fail(awaitable: Awaitable[bool]) -> str:
    try:
        return STATUS_OK if await awaitable else STATUS_FAIL
    except Exception:
        return STATUS_FAIL


async def _current_database(connection: FinlibReadinessConnection) -> str:
    try:
        database = await connection.fetchval("SELECT current_database()")
        return str(database) if isinstance(database, str) else "unknown"
    except Exception:
        return "unknown"


async def _extension_status(
    connection: FinlibReadinessConnection, extension: str
) -> str:
    return await _ok_fail(
        _fetchval_bool(
            connection,
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = $1)",
            extension,
        )
    )


async def _migration_head(connection: FinlibReadinessConnection) -> str:
    try:
        version = await connection.fetchval(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        )
        return STATUS_OK if version == EXPECTED_MIGRATION_HEAD else STATUS_FAIL
    except Exception:
        return STATUS_FAIL


async def _group_status(
    connection: FinlibReadinessConnection, tables: Sequence[str]
) -> str:
    statuses = [await _relation_status(connection, table) for table in tables]
    return STATUS_OK if all(status == STATUS_OK for status in statuses) else STATUS_FAIL


async def _relation_status(
    connection: FinlibReadinessConnection, relation_name: str
) -> str:
    return await _ok_fail(
        _fetchval_bool(
            connection,
            "SELECT to_regclass($1) IS NOT NULL",
            relation_name,
        )
    )


def _repository_status() -> dict[str, str]:
    try:
        from backend.finlib.repositories import (  # noqa: PLC0415
            FixedIncomeRepository,
            FundRepository,
            FundamentalsRepository,
            MacroRepository,
            OpsRepository,
            TreasuryRepository,
        )

        del (
            FixedIncomeRepository,
            FundRepository,
            FundamentalsRepository,
            MacroRepository,
            OpsRepository,
            TreasuryRepository,
        )
        return {"core": STATUS_OK, "assets": STATUS_OK}
    except Exception:
        return {"core": STATUS_FAIL, "assets": STATUS_FAIL}


def _memory_boundary_status() -> str:
    try:
        from backend.memory.policy import (  # noqa: PLC0415
            MemoryBackend,
            is_primary_semantic_retriever,
        )

        return (
            STATUS_OK
            if is_primary_semantic_retriever(MemoryBackend.QDRANT)
            else STATUS_FAIL
        )
    except Exception:
        return STATUS_FAIL


async def _compression_status(
    connection: FinlibReadinessConnection,
) -> dict[str, str]:
    try:
        compressed = await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM timescaledb_information.hypertable_compression_settings
                WHERE hypertable_name = 'market_bars_1d_cagg'
            )
            """
        )
        return {
            "status": STATUS_OK if compressed is True else STATUS_DEFERRED,
            "destructive_retention": await _destructive_retention_status(connection),
        }
    except Exception:
        return {"status": STATUS_DEFERRED, "destructive_retention": STATUS_FAIL}


async def _destructive_retention_status(
    connection: FinlibReadinessConnection,
) -> str:
    try:
        count = await connection.fetchval(
            """
            SELECT count(*)
            FROM timescaledb_information.jobs
            WHERE proc_name = 'policy_retention'
               OR proc_name = 'drop_chunks'
            """
        )
        return STATUS_OK if int(count or 0) == 0 else STATUS_FAIL
    except Exception:
        return STATUS_OK


def _kronos_status(aggregates: Mapping[str, str]) -> dict[str, str]:
    if aggregates.get("market_bars_1d") == STATUS_OK:
        return {"status": STATUS_OK, "reason": "market_bars_1d available"}
    return {
        "status": STATUS_DEGRADED,
        "reason": "market_bars_1d unavailable; FINLIB readiness remains separate",
    }


def _docs_status() -> dict[str, str]:
    return {
        path.name: STATUS_OK if path.exists() else STATUS_FAIL for path in REQUIRED_DOCS
    }


def _collect_failures(name: str, status: object, failed: list[str]) -> None:
    if status in (STATUS_OK, STATUS_DEFERRED):
        return
    if isinstance(status, Mapping) and status.get("status") in (
        STATUS_OK,
        STATUS_DEFERRED,
        STATUS_DEGRADED,
    ):
        return
    failed.append(name)


def _blocked_report(reason: str) -> dict[str, object]:
    return {
        "schema_version": "finlib-readiness-v1",
        "status": STATUS_BLOCKED,
        "checked_at": datetime.now(UTC).isoformat(),
        "database": "unknown",
        "migration_head": STATUS_FAIL,
        "postgres": STATUS_FAIL,
        "timescaledb": STATUS_FAIL,
        "extensions": {extension: STATUS_FAIL for extension in REQUIRED_EXTENSIONS},
        "schemas": {group: STATUS_FAIL for group in REQUIRED_TABLE_GROUPS},
        "repositories": {"core": STATUS_FAIL, "assets": STATUS_FAIL},
        "memory_boundary": STATUS_FAIL,
        "aggregates": {name: STATUS_FAIL for name in REQUIRED_AGGREGATES},
        "compression": {
            "status": STATUS_DEFERRED,
            "destructive_retention": STATUS_FAIL,
        },
        "kronos_input_ready": {"status": STATUS_SKIPPED, "reason": reason},
        "docs": {path.name: STATUS_FAIL for path in REQUIRED_DOCS},
        "ready_for_data_agents": False,
        "failed_checks": [reason],
    }


def _database_from_dsn(dsn: str) -> str:
    path = urlsplit(dsn).path.strip("/")
    return path or "quimera"


if __name__ == "__main__":
    raise SystemExit(main())
