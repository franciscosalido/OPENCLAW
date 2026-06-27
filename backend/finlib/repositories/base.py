"""Base transaction and audit helpers for FINLIB repositories."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from types import TracebackType
from typing import Any, Protocol, TypeVar, cast
from uuid import UUID

from backend.finlib.fundamentals import LEVEL0_FORBIDDEN_FIELDS
from backend.finlib.repositories.models import AuditContext


T = TypeVar("T")


class RepositoryError(RuntimeError):
    """Base FINLIB repository error."""


class RunAlreadyFinishedError(RepositoryError):
    """Raised when attempting to finish an already final ingestion run."""


class RepositoryIntegrityError(RepositoryError):
    """Raised when a repository invariant would be violated."""


class TransactionContext(Protocol):
    """Async transaction context returned by asyncpg."""

    async def __aenter__(self) -> object: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


class RepositoryConnection(Protocol):
    """Connection subset consumed by FINLIB repositories."""

    def transaction(self) -> TransactionContext: ...

    async def execute(self, query: str, *args: object) -> str: ...

    async def fetch(self, query: str, *args: object) -> Sequence[Mapping[str, Any]]: ...

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, Any] | None: ...

    async def fetchval(self, query: str, *args: object) -> object: ...


class AcquireContext(Protocol):
    """Async acquire context returned by asyncpg pools."""

    async def __aenter__(self) -> RepositoryConnection: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


class RepositoryPool(Protocol):
    """Pool subset consumed by FINLIB repositories."""

    def acquire(self) -> AcquireContext: ...


AuditWork = Callable[[RepositoryConnection], Awaitable[T]]
RowCount = int | Callable[[T], int]


class BaseRepository:
    """Base class using an injected asyncpg pool-compatible object."""

    repository_name = "finlib"

    def __init__(self, client_or_pool: object) -> None:
        self._pool = cast(
            RepositoryPool, getattr(client_or_pool, "pool", client_or_pool)
        )

    async def _audited_transaction(
        self,
        *,
        audit: AuditContext,
        target_table: str,
        operation: str,
        row_count: RowCount[T],
        work: AuditWork[T],
    ) -> tuple[T, UUID]:
        """Run domain work and append audit_agent_writes in one transaction."""

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                result = await work(conn)
                audit_id = await self._append_audit_agent_write(
                    conn,
                    audit=audit,
                    target_table=target_table,
                    operation=operation,
                    row_count=_resolve_row_count(row_count, result),
                )
        return result, audit_id

    async def _append_audit_agent_write(
        self,
        conn: RepositoryConnection,
        *,
        audit: AuditContext,
        target_table: str,
        operation: str,
        row_count: int,
    ) -> UUID:
        """Append exactly one audit row for a logical write batch."""

        row = await conn.fetchrow(
            """
            INSERT INTO audit_agent_writes(
                trace_id, run_id, agent_id, repository, target_table,
                operation, row_count, batch_hash, metadata
            )
            VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9::text::jsonb)
            RETURNING audit_id
            """,
            _as_uuid(audit.trace_id, "trace_id"),
            _as_optional_uuid(audit.run_id, "run_id"),
            _require_non_empty(audit.agent_id, "agent_id"),
            self.repository_name,
            _require_non_empty(target_table, "target_table"),
            operation,
            row_count,
            _require_non_empty(audit.batch_hash, "batch_hash"),
            _json_dumps_canonical(audit.metadata or {}),
        )
        if row is None:
            raise RepositoryIntegrityError("audit insert returned no row")
        return _as_uuid(row["audit_id"], "audit_id")

    def _validate_non_empty_batch(self, rows: Sequence[object]) -> None:
        """Raise if a caller passes an empty batch to a required-batch helper."""

        if not rows:
            raise ValueError("batch cannot be empty")

    def _validate_no_level0_payload(self, payload: object) -> None:
        """Reject Level 0 keys recursively before payload persistence."""

        found = _find_level0_keys(payload)
        if found:
            raise ValueError(f"Level 0 fields are not allowed: {', '.join(found)}")


def _json_dumps_canonical(payload: Mapping[str, object]) -> str:
    """Serialize JSON deterministically for asyncpg JSONB parameters."""

    return json.dumps(
        _canonical_json(payload),
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_json(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical_json(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_json(mapped)
            for key, mapped in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, list | tuple):
        return [_canonical_json(item) for item in value]
    return value


def _as_uuid(value: object, field_name: str) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    raise TypeError(f"{field_name} must be UUID or UUID string")


def _as_optional_uuid(value: object, field_name: str) -> UUID | None:
    if value is None:
        return None
    return _as_uuid(value, field_name)


def _require_non_empty(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")
    return value


def _resolve_row_count(row_count: RowCount[T], result: T) -> int:
    if isinstance(row_count, int):
        return row_count
    return row_count(result)


def _find_level0_keys(value: object) -> list[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            if key_text in LEVEL0_FORBIDDEN_FIELDS:
                found.add(key_text)
            found.update(_find_level0_keys(nested))
    elif isinstance(value, list | tuple):
        for item in value:
            found.update(_find_level0_keys(item))
    return sorted(found)
