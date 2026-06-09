"""Create or validate the Q18-04 Qdrant hybrid benchmark schema.

Dry-run is the default. Live execution requires RUN_QDRANT_SCHEMA_118=1 and
never deletes, recreates or upserts collections.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from backend.rag.qdrant_hybrid_118 import (
    BENCHMARK_COLLECTION,
    CANDIDATE_COLLECTION,
    LEGACY_COLLECTION,
    HybridCollectionSpec118,
    HybridSchemaClientProtocol,
    QdrantHybridSchemaClient118,
    build_collection_create_payload,
    build_payload_index_specs,
    default_hybrid_collection_spec_118,
    ensure_benchmark_collection_118,
    validate_spec_118,
    write_schema_snapshot,
)

SCHEMA_CREATE_REPORT_VERSION = "qdrant-hybrid-schema-118-create-v1"
RUN_SCHEMA_ENV_VAR = "RUN_QDRANT_SCHEMA_118"
RUN_SCHEMA_REQUIRED_VALUE = "1"
LOCALHOST_ALLOWED = frozenset({"localhost", "127.0.0.1", "::1"})
DEFAULT_SNAPSHOT_PATH = Path(
    "docs/specs/qdrant-1-18-upgrade/benchmark_schema_snapshot.json"
)


@dataclass(frozen=True, slots=True)
class SchemaCreateReport:
    """Safe JSON-friendly result for schema creation or dry-run."""

    schema_version: str
    dry_run: bool
    collection_name: str
    created: bool
    validated: bool
    snapshot_path: str | None
    payload_indexes: tuple[str, ...]
    dense_vector_name: str
    sparse_vector_name: str

    def to_safe_dict(self) -> dict[str, object]:
        """Return stable report mapping."""

        return {
            "schema_version": self.schema_version,
            "dry_run": self.dry_run,
            "collection_name": self.collection_name,
            "created": self.created,
            "validated": self.validated,
            "snapshot_path": self.snapshot_path,
            "payload_indexes": list(self.payload_indexes),
            "dense_vector_name": self.dense_vector_name,
            "sparse_vector_name": self.sparse_vector_name,
        }


def ensure_localhost(host: str) -> str:
    clean = host.strip()
    if not clean or "\x00" in clean:
        raise ValueError("host must be a non-empty string without null bytes")
    folded = clean.casefold()
    if "://" in folded:
        raise ValueError("URL-style hosts are not allowed")
    if folded not in LOCALHOST_ALLOWED:
        raise ValueError("host must be localhost, 127.0.0.1 or ::1")
    return folded


def ensure_execute_env(env: Mapping[str, str]) -> None:
    if env.get(RUN_SCHEMA_ENV_VAR) != RUN_SCHEMA_REQUIRED_VALUE:
        raise RuntimeError("RUN_QDRANT_SCHEMA_118=1 is required for execute")


def build_dry_run_report(
    *,
    spec: HybridCollectionSpec118,
    snapshot_path: Path,
) -> SchemaCreateReport:
    """Build a dry-run report from pure schema builders."""

    validate_spec_118(spec)
    build_collection_create_payload(spec)
    build_payload_index_specs(spec)
    return SchemaCreateReport(
        schema_version=SCHEMA_CREATE_REPORT_VERSION,
        dry_run=True,
        collection_name=spec.collection_name,
        created=False,
        validated=True,
        snapshot_path=str(snapshot_path),
        payload_indexes=spec.payload_indexes,
        dense_vector_name=spec.dense_vector_name,
        sparse_vector_name=spec.sparse_vector_name,
    )


async def run_schema_create(
    *,
    client: HybridSchemaClientProtocol,
    spec: HybridCollectionSpec118,
    dry_run: bool,
    snapshot_path: Path,
    fail_if_exists: bool,
) -> SchemaCreateReport:
    """Run schema dry-run or live ensure operation."""

    if dry_run:
        return build_dry_run_report(spec=spec, snapshot_path=snapshot_path)

    existed_before = await client.collection_exists(spec.collection_name)
    snapshot = await ensure_benchmark_collection_118(
        client,
        spec,
        fail_if_exists=fail_if_exists,
    )
    write_schema_snapshot(snapshot, snapshot_path)
    return SchemaCreateReport(
        schema_version=SCHEMA_CREATE_REPORT_VERSION,
        dry_run=False,
        collection_name=spec.collection_name,
        created=not existed_before,
        validated=True,
        snapshot_path=str(snapshot_path),
        payload_indexes=spec.payload_indexes,
        dense_vector_name=spec.dense_vector_name,
        sparse_vector_name=spec.sparse_vector_name,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Create or validate the Qdrant 1.18 hybrid benchmark schema.",
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6333)
    parser.add_argument("--grpc-port", type=int, default=6334)
    parser.add_argument("--collection", default=BENCHMARK_COLLECTION)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true")
    mode.add_argument("--execute", dest="dry_run", action="store_false")
    parser.set_defaults(dry_run=True)
    parser.add_argument("--snapshot-path", type=Path, default=DEFAULT_SNAPSHOT_PATH)
    parser.add_argument("--fail-if-exists", action="store_true")
    return parser.parse_args(argv)


def _spec_from_collection(collection_name: str) -> HybridCollectionSpec118:
    if collection_name in {CANDIDATE_COLLECTION, LEGACY_COLLECTION}:
        raise ValueError("candidate and legacy collections are forbidden in Q18-04")
    if collection_name != BENCHMARK_COLLECTION:
        raise ValueError("Q18-04 only creates quimera_benchmark_hybrid_118")
    return default_hybrid_collection_spec_118()


def _build_client(
    *, host: str, port: int, grpc_port: int
) -> QdrantHybridSchemaClient118:
    from qdrant_client import AsyncQdrantClient

    return QdrantHybridSchemaClient118(
        AsyncQdrantClient(host=host, port=port, grpc_port=grpc_port)
    )


async def async_main(
    argv: Sequence[str] | None = None,
    *,
    client: HybridSchemaClientProtocol | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Async CLI entrypoint with injectable client for unit tests."""

    args = parse_args(argv)
    clean_host = ensure_localhost(args.host)
    spec = _spec_from_collection(args.collection)
    active_env = os.environ if env is None else env
    if not args.dry_run:
        ensure_execute_env(active_env)
    active_client = client
    if active_client is None and not args.dry_run:
        active_client = _build_client(
            host=clean_host,
            port=args.port,
            grpc_port=args.grpc_port,
        )
    if active_client is None:
        active_client = _DryRunSchemaClient()
    report = await run_schema_create(
        client=active_client,
        spec=spec,
        dry_run=args.dry_run,
        snapshot_path=args.snapshot_path,
        fail_if_exists=args.fail_if_exists,
    )
    sys.stdout.write(json.dumps(report.to_safe_dict(), indent=2, sort_keys=True))
    sys.stdout.write("\n")
    return 0


class _DryRunSchemaClient:
    async def collection_exists(self, collection_name: str) -> bool:
        raise RuntimeError("dry-run client should not be used")

    async def create_collection(self, spec: HybridCollectionSpec118) -> None:
        raise RuntimeError("dry-run client should not be used")

    async def create_payload_indexes(self, spec: HybridCollectionSpec118) -> None:
        raise RuntimeError("dry-run client should not be used")

    async def get_collection_info(self, collection_name: str) -> Mapping[str, object]:
        raise RuntimeError("dry-run client should not be used")

    async def get_qdrant_versions(self) -> Mapping[str, str | None]:
        raise RuntimeError("dry-run client should not be used")


def main(argv: Sequence[str] | None = None) -> int:
    """Synchronous CLI entrypoint."""

    try:
        return asyncio.run(async_main(argv))
    except Exception as exc:
        sys.stderr.write(f"qdrant hybrid schema failed: {type(exc).__name__}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
