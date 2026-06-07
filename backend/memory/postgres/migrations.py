"""Async SQL migration runner for Quimera PostgreSQL memory."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, Self, cast


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
SCHEMA_MIGRATIONS_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    checksum    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""
ADVISORY_LOCK_SQL = (
    "SELECT pg_advisory_xact_lock(hashtext('quimera_postgres_migrations'))"
)


class MigrationPool(Protocol):
    """Asyncpg pool shape consumed by the migration runner."""

    def acquire(self) -> "MigrationAcquireContext":
        """Return async context manager yielding a connection."""
        ...


class MigrationAcquireContext(Protocol):
    """Async context manager returned by asyncpg pool.acquire."""

    async def __aenter__(self) -> "MigrationConnection": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


class MigrationTransaction(Protocol):
    """Async context manager returned by asyncpg connection.transaction."""

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


class MigrationConnection(Protocol):
    """Connection methods used by the migration runner."""

    def transaction(self) -> MigrationTransaction: ...

    async def execute(self, query: str, *args: object) -> str: ...

    async def fetch(self, query: str, *args: object) -> Sequence[Mapping[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class MigrationFile:
    """One migration file with its content checksum."""

    version: str
    path: Path
    sql: str
    checksum: str


def compute_checksum(sql: str) -> str:
    """Compute SHA-256 hex checksum for a migration body."""

    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def list_migration_files(
    migrations_dir: Path = MIGRATIONS_DIR,
) -> tuple[MigrationFile, ...]:
    """Return SQL migrations in lexicographic order."""

    files = sorted(migrations_dir.glob("*.sql"))
    return tuple(
        MigrationFile(
            version=path.stem,
            path=path,
            sql=path.read_text(encoding="utf-8"),
            checksum=compute_checksum(path.read_text(encoding="utf-8")),
        )
        for path in files
    )


def check_applied_checksum(migration: MigrationFile, *, applied_checksum: str) -> None:
    """Raise if an already-applied migration no longer matches its file."""

    if applied_checksum != migration.checksum:
        raise RuntimeError(
            "migration checksum drift detected "
            f"for {migration.version}: applied={applied_checksum} current={migration.checksum}"
        )


def plan_pending_migrations(
    migrations: Sequence[MigrationFile],
    *,
    applied_checksums: Mapping[str, str],
) -> tuple[MigrationFile, ...]:
    """Return migrations that still need to be applied after checksum validation."""

    pending: list[MigrationFile] = []
    for migration in migrations:
        applied_checksum = applied_checksums.get(migration.version)
        if applied_checksum is None:
            pending.append(migration)
            continue
        check_applied_checksum(migration, applied_checksum=applied_checksum)
    return tuple(pending)


async def run_migrations(
    client_or_pool: object,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> tuple[str, ...]:
    """Apply pending SQL migrations and return applied versions.

    The runner uses one transaction and a PostgreSQL advisory lock. It records
    each applied migration checksum and fails if a migration file changes after
    being applied.
    """

    pool = _pool_from(client_or_pool)
    migrations = list_migration_files(migrations_dir)
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(ADVISORY_LOCK_SQL)
            await connection.execute(SCHEMA_MIGRATIONS_BOOTSTRAP_SQL)
            rows = await connection.fetch(
                "SELECT version, checksum FROM schema_migrations"
            )
            applied_checksums = {
                str(row["version"]): str(row["checksum"]) for row in rows
            }
            pending = plan_pending_migrations(
                migrations,
                applied_checksums=applied_checksums,
            )
            for migration in pending:
                await connection.execute(migration.sql)
                await connection.execute(
                    """
                    INSERT INTO schema_migrations(version, checksum)
                    VALUES($1, $2)
                    ON CONFLICT(version) DO NOTHING
                    """,
                    migration.version,
                    migration.checksum,
                )
    return tuple(migration.version for migration in pending)


def _pool_from(client_or_pool: object) -> MigrationPool:
    pool = getattr(client_or_pool, "pool", client_or_pool)
    return cast(MigrationPool, pool)
