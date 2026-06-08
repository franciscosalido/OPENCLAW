from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4
from urllib.parse import urlsplit, urlunsplit

import asyncpg  # type: ignore[import-untyped]

from backend.memory.postgres.client import PostgresClient


def database_dsn(base_dsn: str, database: str) -> str:
    parts = urlsplit(base_dsn)
    return urlunsplit(
        (parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment)
    )


def isolated_database_name(prefix: str) -> str:
    suffix = uuid4().hex
    return f"quimera_test_{prefix}_{suffix}"


@asynccontextmanager
async def isolated_postgres_client(
    base_dsn: str,
    *,
    prefix: str,
) -> AsyncIterator[PostgresClient]:
    database = isolated_database_name(prefix)
    if not database.startswith("quimera_test_"):
        raise ValueError("unsafe test database name")

    admin_dsn = database_dsn(base_dsn, "postgres")
    test_dsn = database_dsn(base_dsn, database)
    admin = await asyncpg.connect(dsn=admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{database}"')
    finally:
        await admin.close()

    client = await PostgresClient.create(dsn=test_dsn)
    try:
        yield client
    finally:
        await client.close()
        cleanup = await asyncpg.connect(dsn=admin_dsn)
        try:
            await cleanup.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        finally:
            await cleanup.close()
