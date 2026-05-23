"""Governed local reset for Qdrant development collections.

This script is intentionally hard to run destructively. Deletes require a local
host, an environment flag, a long confirmation flag and an exact allowlist or
safe prefix. Dry-run is the default.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import inspect
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

RESET_REPORT_SCHEMA_VERSION = "qdrant-local-reset-v1"
LOCAL_RESET_ENV_VAR = "QDRANT_LOCAL_RESET"
LOCAL_RESET_REQUIRED_VALUE = "1"
LOCALHOST_ALLOWED = frozenset({"localhost", "127.0.0.1", "::1"})
EXPLICIT_DELETE_ALLOWED = frozenset(
    {
        "openclaw_knowledge",
        "quimera_knowledge",
        "quimera_knowledge_v2",
    }
)
PREFIX_DELETE_ALLOWED = (
    "q18_benchmark_",
    "q18_smoke_",
    "quimera_benchmark_",
    "quimera_hybrid_smoke_",
    "gw07_synthetic_rag_",
)
DEFAULT_BENCHMARK_COLLECTION = "q18_benchmark_hybrid_local"
BENCHMARK_COLLECTION_PREFIX = "q18_benchmark_"
FORBIDDEN_REMOTE_HINTS = ("cloud", "prod", "production", "staging")
DESTRUCTIVE_CONFIRMATION_FLAG = (
    "--i-understand-this-deletes-local-qdrant-collections"
)
_SAFE_COLLECTION_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class ResetRefused(RuntimeError):
    """Raised when local reset safety gates are not satisfied."""


class QdrantResetClientProtocol(Protocol):
    """Minimal client contract for local collection reset."""

    async def get_collections(self) -> Sequence[str]:
        """Return collection names only."""
        ...

    async def delete_collection(self, collection_name: str) -> None:
        """Delete one collection by exact name."""
        ...

    async def create_benchmark_collection(self, collection_name: str) -> None:
        """Create a benchmark collection, if supported by the concrete adapter."""
        ...


@dataclass(frozen=True, slots=True)
class ResetPlan:
    """Planned local collection reset without side effects."""

    host: str
    dry_run: bool
    confirmed: bool
    recreate_benchmark: bool
    benchmark_collection: str | None
    collections_before: tuple[str, ...]
    delete_targets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResetReport:
    """Safe JSON-friendly report for local collection reset."""

    schema_version: str
    dry_run: bool
    host: str
    confirmed: bool
    env_flag_present: bool
    collections_before: tuple[str, ...]
    delete_targets: tuple[str, ...]
    deleted: tuple[str, ...]
    skipped: tuple[str, ...]
    collections_after: tuple[str, ...]
    recreated: tuple[str, ...]
    errors: tuple[str, ...]

    def to_safe_dict(self) -> dict[str, object]:
        """Return a parseable report without payloads, vectors or schema data."""

        return {
            "schema_version": self.schema_version,
            "dry_run": self.dry_run,
            "host": self.host,
            "confirmed": self.confirmed,
            "env_flag_present": self.env_flag_present,
            "collections_before": list(self.collections_before),
            "delete_targets": list(self.delete_targets),
            "deleted": list(self.deleted),
            "skipped": list(self.skipped),
            "collections_after": list(self.collections_after),
            "recreated": list(self.recreated),
            "errors": list(self.errors),
        }


class QdrantResetClientAdapter:
    """Real Qdrant adapter for governed local reset.

    Benchmark collection creation is intentionally refused here because Q18-03
    does not own schema creation. Q18-04 should wire the real schema-aware
    creation path.
    """

    def __init__(self, *, host: str, port: int) -> None:
        from qdrant_client import AsyncQdrantClient

        self._client = AsyncQdrantClient(host=host, port=port)

    async def get_collections(self) -> Sequence[str]:
        response = await self._client.get_collections()
        return tuple(collection.name for collection in response.collections)

    async def delete_collection(self, collection_name: str) -> None:
        await self._client.delete_collection(collection_name=collection_name)

    async def create_benchmark_collection(self, collection_name: str) -> None:
        raise ResetRefused("benchmark collection schema creation is reserved for Q18-04")

    async def close(self) -> None:
        await self._client.close()


def _validate_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if "\x00" in value:
        raise ValueError(f"{field_name} cannot contain null bytes")
    clean = value.strip()
    if not clean:
        raise ValueError(f"{field_name} cannot be empty")
    return clean


def _validate_port(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("port must be an integer")
    if value < 1 or value > 65535:
        raise ValueError("port must be between 1 and 65535")
    return value


def ensure_localhost(host: str) -> str:
    """Return a clean local host or refuse remote-looking targets."""

    clean = _validate_text(host, "host")
    folded = clean.casefold()
    if "://" in folded:
        raise ResetRefused("Qdrant reset refuses URL-style hosts")
    if any(hint in folded for hint in FORBIDDEN_REMOTE_HINTS):
        raise ResetRefused("Qdrant reset refuses remote environment hints")
    if folded not in LOCALHOST_ALLOWED:
        raise ResetRefused("Qdrant reset requires localhost, 127.0.0.1 or ::1")
    return folded


def ensure_env_flag(env: Mapping[str, str]) -> None:
    """Require the exact local destructive reset environment flag."""

    if env.get(LOCAL_RESET_ENV_VAR) != LOCAL_RESET_REQUIRED_VALUE:
        raise ResetRefused(f"{LOCAL_RESET_ENV_VAR}=1 is required")


def assert_destructive_reset_allowed(
    *,
    env: Mapping[str, str],
    confirmed: bool,
    host: str,
) -> None:
    """Validate all destructive gates without touching a client."""

    ensure_localhost(host)
    ensure_env_flag(env)
    if not confirmed:
        raise ResetRefused("explicit destructive confirmation flag is required")


def is_deletable_collection(name: str) -> bool:
    """Return whether a collection is explicitly allowed for local deletion."""

    clean_name = _validate_text(name, "collection_name")
    return clean_name in EXPLICIT_DELETE_ALLOWED or any(
        clean_name.startswith(prefix) for prefix in PREFIX_DELETE_ALLOWED
    )


def validate_benchmark_collection_name(name: str) -> str:
    """Validate a benchmark collection name for optional future recreation."""

    clean = _validate_text(name, "benchmark_collection")
    if clean in EXPLICIT_DELETE_ALLOWED:
        raise ValueError("benchmark collection cannot be a protected legacy name")
    if not clean.startswith(BENCHMARK_COLLECTION_PREFIX):
        raise ValueError("benchmark collection must start with q18_benchmark_")
    if not _SAFE_COLLECTION_RE.fullmatch(clean):
        raise ValueError("benchmark collection contains unsafe characters")
    return clean


def _sorted_unique_names(names: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({_validate_text(name, "collection_name") for name in names}))


def plan_reset(
    *,
    host: str,
    existing_collections: Sequence[str],
    dry_run: bool,
    confirmed: bool,
    recreate_benchmark: bool,
    benchmark_collection: str | None,
) -> ResetPlan:
    """Plan a local reset using only collection names."""

    clean_host = ensure_localhost(host)
    clean_existing = _sorted_unique_names(existing_collections)
    clean_benchmark = (
        None
        if benchmark_collection is None
        else validate_benchmark_collection_name(benchmark_collection)
    )
    delete_targets = tuple(
        name for name in clean_existing if is_deletable_collection(name)
    )
    return ResetPlan(
        host=clean_host,
        dry_run=dry_run,
        confirmed=confirmed,
        recreate_benchmark=recreate_benchmark,
        benchmark_collection=clean_benchmark,
        collections_before=clean_existing,
        delete_targets=delete_targets,
    )


async def fetch_existing_collections(
    client: QdrantResetClientProtocol,
) -> tuple[str, ...]:
    """Fetch collection names only, sorted deterministically."""

    return _sorted_unique_names(await client.get_collections())


def _skipped_collections(plan: ResetPlan) -> tuple[str, ...]:
    targets = set(plan.delete_targets)
    return tuple(name for name in plan.collections_before if name not in targets)


def _env_flag_present(env: Mapping[str, str]) -> bool:
    return env.get(LOCAL_RESET_ENV_VAR) == LOCAL_RESET_REQUIRED_VALUE


async def execute_reset_plan(
    *,
    client: QdrantResetClientProtocol,
    plan: ResetPlan,
    env: Mapping[str, str],
) -> ResetReport:
    """Execute or dry-run a reset plan.

    Operational failures raise ``ResetRefused`` and do not return a partial
    report. The ``errors`` report field is reserved for a future non-aborting
    mode and remains empty in Q18-03.
    """

    skipped = _skipped_collections(plan)
    if plan.dry_run:
        return ResetReport(
            schema_version=RESET_REPORT_SCHEMA_VERSION,
            dry_run=True,
            host=plan.host,
            confirmed=plan.confirmed,
            env_flag_present=_env_flag_present(env),
            collections_before=plan.collections_before,
            delete_targets=plan.delete_targets,
            deleted=(),
            skipped=skipped,
            collections_after=plan.collections_before,
            recreated=(),
            errors=(),
        )

    assert_destructive_reset_allowed(env=env, confirmed=plan.confirmed, host=plan.host)
    deleted: list[str] = []
    try:
        for collection_name in plan.delete_targets:
            await client.delete_collection(collection_name)
            deleted.append(collection_name)
        recreated: tuple[str, ...] = ()
        if plan.recreate_benchmark:
            if plan.benchmark_collection is None:
                raise ResetRefused("benchmark collection is required for recreation")
            await client.create_benchmark_collection(plan.benchmark_collection)
            recreated = (plan.benchmark_collection,)
    except Exception as exc:
        raise ResetRefused(f"local reset operation failed: {type(exc).__name__}") from exc

    collections_after = await fetch_existing_collections(client)
    return ResetReport(
        schema_version=RESET_REPORT_SCHEMA_VERSION,
        dry_run=False,
        host=plan.host,
        confirmed=plan.confirmed,
        env_flag_present=_env_flag_present(env),
        collections_before=plan.collections_before,
        delete_targets=plan.delete_targets,
        deleted=tuple(deleted),
        skipped=skipped,
        collections_after=collections_after,
        recreated=recreated,
        errors=(),
    )


async def run_reset(
    *,
    client: QdrantResetClientProtocol,
    host: str,
    dry_run: bool,
    confirmed: bool,
    recreate_benchmark: bool,
    benchmark_collection: str | None,
    env: Mapping[str, str],
) -> ResetReport:
    """Fetch collections, plan reset and execute or dry-run it."""

    clean_host = ensure_localhost(host)
    collections = await fetch_existing_collections(client)
    plan = plan_reset(
        host=clean_host,
        existing_collections=collections,
        dry_run=dry_run,
        confirmed=confirmed,
        recreate_benchmark=recreate_benchmark,
        benchmark_collection=benchmark_collection,
    )
    return await execute_reset_plan(client=client, plan=plan, env=env)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse reset CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Plan or execute a guarded local Qdrant collection reset.",
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6333)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true")
    mode.add_argument("--execute", dest="dry_run", action="store_false")
    parser.set_defaults(dry_run=True)
    parser.add_argument(
        DESTRUCTIVE_CONFIRMATION_FLAG,
        dest="confirmed",
        action="store_true",
    )
    parser.add_argument("--recreate-benchmark", action="store_true")
    parser.add_argument(
        "--benchmark-collection",
        default=DEFAULT_BENCHMARK_COLLECTION,
    )
    return parser.parse_args(argv)


def _build_client(*, host: str, port: int) -> QdrantResetClientAdapter:
    return QdrantResetClientAdapter(host=host, port=port)


async def async_main(
    argv: Sequence[str] | None = None,
    *,
    client: QdrantResetClientProtocol | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Async CLI entrypoint with injectable client for offline tests."""

    args = parse_args(argv)
    clean_port = _validate_port(args.port)
    clean_host = ensure_localhost(args.host)
    active_env = os.environ if env is None else env
    active_client = client if client is not None else _build_client(
        host=clean_host,
        port=clean_port,
    )

    try:
        report = await run_reset(
            client=active_client,
            host=clean_host,
            dry_run=args.dry_run,
            confirmed=args.confirmed,
            recreate_benchmark=args.recreate_benchmark,
            benchmark_collection=args.benchmark_collection,
            env=active_env,
        )
    finally:
        close = getattr(active_client, "close", None)
        if close is not None:
            close_result = close()
            if inspect.isawaitable(close_result):
                await close_result

    sys.stdout.write(json.dumps(report.to_safe_dict(), indent=2, sort_keys=True))
    sys.stdout.write("\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Synchronous CLI entrypoint."""

    try:
        return asyncio.run(async_main(argv))
    except Exception as exc:
        sys.stderr.write(f"qdrant local reset failed: {type(exc).__name__}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
