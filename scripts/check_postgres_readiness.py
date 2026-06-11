#!/usr/bin/env python
"""PostgreSQL readiness gate for FINLIB-0.

The script emits a small JSON contract with only ok/fail fields. It does not
create roles, mutate durable tables, or echo DSNs, hosts, passwords or raw
tracebacks.
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
from typing import Any, Protocol
from urllib.parse import urlsplit

import asyncpg  # type: ignore[import-untyped]

from backend.memory.postgres.settings import DEFAULT_POSTGRES_DSN


READINESS_FIELDS = (
    "postgres",
    "database",
    "timescaledb",
    "vector",
    "pgcrypto",
    "pg_trgm",
    "btree_gin",
    "pg_stat_statements",
    "migration_head",
    "write_test",
    "readonly_role",
)
REQUIRED_EXTENSIONS = (
    "timescaledb",
    "vector",
    "pgcrypto",
    "pg_trgm",
    "btree_gin",
    "pg_stat_statements",
)
MINIMUM_MIGRATION_HEAD = 18
DEFAULT_READONLY_ROLE = "quimera_readonly"
DEFAULT_TIMEOUT_S = 5.0
STATUS_OK = "ok"
STATUS_FAIL = "fail"


class ReadinessConnection(Protocol):
    """Small asyncpg-compatible surface used by the readiness gate."""

    async def fetchval(self, query: str, *args: object) -> Any:
        """Return a single scalar value."""
        ...

    async def execute(self, query: str, *args: object) -> str:
        """Execute a statement."""
        ...

    async def close(self) -> None:
        """Close the connection."""
        ...


ConnectFactory = Callable[..., Awaitable[ReadinessConnection]]


@dataclass(frozen=True, slots=True)
class PostgresReadinessConfig:
    """Runtime configuration for the FINLIB PostgreSQL readiness gate."""

    dsn: str
    expected_database: str
    readonly_role: str
    timeout_s: float = DEFAULT_TIMEOUT_S


def load_config(
    env: Mapping[str, str] | None = None,
    *,
    readonly_role: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> PostgresReadinessConfig:
    """Load readiness settings from the existing Quimera Postgres env names."""

    env_map = os.environ if env is None else env
    dsn = (
        env_map.get("TEST_POSTGRES_DSN")
        or env_map.get("QUIMERA_POSTGRES_DSN")
        or DEFAULT_POSTGRES_DSN
    )
    expected_database = env_map.get("QUIMERA_POSTGRES_DATABASE") or _database_from_dsn(
        dsn
    )
    configured_role = (
        readonly_role
        or env_map.get("QUIMERA_POSTGRES_READONLY_ROLE")
        or DEFAULT_READONLY_ROLE
    )
    return PostgresReadinessConfig(
        dsn=dsn,
        expected_database=expected_database,
        readonly_role=configured_role,
        timeout_s=_validate_timeout(timeout_s),
    )


async def run_readiness(
    config: PostgresReadinessConfig,
    *,
    connect: ConnectFactory | None = None,
) -> dict[str, str]:
    """Return the sanitized readiness report for a live PostgreSQL database."""

    connector = asyncpg.connect if connect is None else connect
    report = _empty_report()
    connection: ReadinessConnection | None = None
    try:
        connection = await connector(
            dsn=config.dsn, timeout=math.ceil(config.timeout_s)
        )
        report["postgres"] = STATUS_OK
        return await build_readiness_report(connection, config, report=report)
    except Exception:
        return report
    finally:
        if connection is not None:
            try:
                await connection.close()
            except Exception:  # nosec B110 - intentional: avoid leaking DSN details.
                pass


async def build_readiness_report(
    connection: ReadinessConnection,
    config: PostgresReadinessConfig,
    *,
    report: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build a readiness report using an already-open safe connection."""

    result = _empty_report() if report is None else dict(report)
    result["database"] = await _status_for_database(connection, config)
    for extension in REQUIRED_EXTENSIONS:
        result[extension] = await _status_for_extension(connection, extension)
    result["migration_head"] = await _status_for_migration_head(connection)
    result["write_test"] = await _status_for_write_test(connection)
    result["readonly_role"] = await _status_for_readonly_role(connection, config)
    return _ordered_report(result)


def readiness_ok(report: Mapping[str, str]) -> bool:
    """Return whether every required readiness field is ok."""

    return all(report.get(field) == STATUS_OK for field in READINESS_FIELDS)


def sanitized_exception_label(exc: BaseException) -> str:
    """Return a low-information label safe for logs/tests."""

    return type(exc).__name__


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="Check FINLIB PostgreSQL readiness.")
    parser.add_argument("--json", action="store_true", help="Emit JSON; default mode.")
    parser.add_argument(
        "--readonly-role",
        default=None,
        help="Role expected to exist for future read-only FINLIB access.",
    )
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    return parser.parse_args(argv)


async def async_main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    connect: ConnectFactory | None = None,
    stdout: Any = sys.stdout,
) -> int:
    """Async CLI entrypoint, parameterized for unit tests."""

    args = parse_args(argv)
    config = load_config(
        env,
        readonly_role=args.readonly_role,
        timeout_s=args.timeout_s,
    )
    report = await run_readiness(config, connect=connect)
    stdout.write(json.dumps(report) + "\n")
    return 0 if readiness_ok(report) else 1


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    connect: ConnectFactory | None = None,
    stdout: Any = sys.stdout,
) -> int:
    """Synchronous CLI entrypoint."""

    try:
        return asyncio.run(async_main(argv, env=env, connect=connect, stdout=stdout))
    except Exception as exc:
        del exc
        stdout.write(json.dumps(_empty_report()) + "\n")
        return 1


async def _status_for_database(
    connection: ReadinessConnection, config: PostgresReadinessConfig
) -> str:
    try:
        database = await connection.fetchval("SELECT current_database()")
        return STATUS_OK if database == config.expected_database else STATUS_FAIL
    except Exception:
        return STATUS_FAIL


async def _status_for_extension(
    connection: ReadinessConnection, extension_name: str
) -> str:
    try:
        installed = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = $1)",
            extension_name,
        )
        return STATUS_OK if installed is True else STATUS_FAIL
    except Exception:
        return STATUS_FAIL


async def _status_for_migration_head(connection: ReadinessConnection) -> str:
    try:
        version = await connection.fetchval(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        )
        return (
            STATUS_OK
            if isinstance(version, str)
            and _migration_number(version) >= MINIMUM_MIGRATION_HEAD
            else STATUS_FAIL
        )
    except Exception:
        return STATUS_FAIL


async def _status_for_write_test(connection: ReadinessConnection) -> str:
    try:
        await connection.execute(
            "CREATE TEMP TABLE quimera_readiness_write_test(value INTEGER)"
        )
        await connection.execute(
            "INSERT INTO quimera_readiness_write_test(value) VALUES($1)",
            1,
        )
        count = await connection.fetchval(
            "SELECT count(*) FROM quimera_readiness_write_test"
        )
        return STATUS_OK if count == 1 else STATUS_FAIL
    except Exception:
        return STATUS_FAIL
    finally:
        try:
            await connection.execute(
                "DROP TABLE IF EXISTS pg_temp.quimera_readiness_write_test"
            )
        except Exception:  # nosec B110 - intentional: temp cleanup must not leak.
            pass


async def _status_for_readonly_role(
    connection: ReadinessConnection, config: PostgresReadinessConfig
) -> str:
    try:
        exists = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)",
            config.readonly_role,
        )
        return STATUS_OK if exists is True else STATUS_FAIL
    except Exception:
        return STATUS_FAIL


def _empty_report() -> dict[str, str]:
    return {field: STATUS_FAIL for field in READINESS_FIELDS}


def _ordered_report(report: Mapping[str, str]) -> dict[str, str]:
    return {field: report.get(field, STATUS_FAIL) for field in READINESS_FIELDS}


def _migration_number(version: str) -> int:
    prefix = version.split("_", maxsplit=1)[0]
    try:
        return int(prefix)
    except ValueError:
        return -1


def _database_from_dsn(dsn: str) -> str:
    path = urlsplit(dsn).path.strip("/")
    return path or "quimera"


def _validate_timeout(value: float) -> float:
    clean = float(value)
    if clean <= 0.0:
        raise ValueError("timeout_s must be > 0")
    return clean


if __name__ == "__main__":
    raise SystemExit(main())
