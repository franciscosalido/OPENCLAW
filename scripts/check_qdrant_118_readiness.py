"""Qdrant 1.18 readiness check for local Quimera development.

This script is intentionally non-destructive. It only probes REST/gRPC
reachability and version parity. It does not create, delete, update, upload or
inspect project collections.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml
from qdrant_client import AsyncQdrantClient

READINESS_SCHEMA_VERSION = "qdrant-readiness-v1"
DEFAULT_HOST = "localhost"
DEFAULT_TIMEOUT_S = 5.0
DEFAULT_VERSION_CONTRACT_PATH = (
    Path(__file__).resolve().parents[1] / "infra/qdrant/version_contract.yaml"
)


@dataclass(frozen=True, slots=True)
class QdrantVersionContract:
    """Version contract for Qdrant server/client readiness."""

    server_target_version: str
    client_target_version: str
    version_family: str
    rest_port: int
    grpc_port: int


@dataclass(frozen=True, slots=True)
class QdrantReadiness:
    """Safe readiness summary for the local Qdrant 1.18 service."""

    schema_version: str
    checked_at_utc: str
    target_server_version: str
    target_client_version: str
    qdrant_client_version: str
    qdrant_server_version: str | None
    version_family: str
    version_family_ok: bool
    version_exact_parity_ok: bool
    rest_port: int
    grpc_port: int
    rest_ok: bool
    grpc_ok: bool
    ready: bool

    def to_dict(self) -> dict[str, object]:
        """Return a stable, JSON-friendly readiness mapping."""

        return {
            "schema_version": self.schema_version,
            "checked_at_utc": self.checked_at_utc,
            "target_server_version": self.target_server_version,
            "target_client_version": self.target_client_version,
            "qdrant_client_version": self.qdrant_client_version,
            "qdrant_server_version": self.qdrant_server_version,
            "version_family": self.version_family,
            "version_family_ok": self.version_family_ok,
            "version_exact_parity_ok": self.version_exact_parity_ok,
            "rest_port": self.rest_port,
            "grpc_port": self.grpc_port,
            "rest_ok": self.rest_ok,
            "grpc_ok": self.grpc_ok,
            "ready": self.ready,
        }


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _client_version() -> str:
    return importlib.metadata.version("qdrant-client")


def load_version_contract(path: Path = DEFAULT_VERSION_CONTRACT_PATH) -> QdrantVersionContract:
    """Load the local Qdrant version contract from YAML."""

    with path.open("r", encoding="utf-8") as contract_file:
        raw = yaml.safe_load(contract_file)
    if not isinstance(raw, dict):
        raise ValueError("version contract must be a mapping")
    qdrant = raw.get("qdrant")
    if not isinstance(qdrant, dict):
        raise ValueError("version contract must contain qdrant mapping")

    server_target_version = qdrant.get("server_target_version")
    client_target_version = qdrant.get("client_target_version")
    version_family = qdrant.get("version_family")
    rest_port = qdrant.get("rest_port")
    grpc_port = qdrant.get("grpc_port")
    if not isinstance(server_target_version, str) or not server_target_version:
        raise ValueError("server_target_version must be a non-empty string")
    if not isinstance(client_target_version, str) or not client_target_version:
        raise ValueError("client_target_version must be a non-empty string")
    if not isinstance(version_family, str) or not version_family:
        raise ValueError("version_family must be a non-empty string")
    if not isinstance(rest_port, int):
        raise TypeError("rest_port must be an integer")
    if not isinstance(grpc_port, int):
        raise TypeError("grpc_port must be an integer")
    return QdrantVersionContract(
        server_target_version=server_target_version,
        client_target_version=client_target_version,
        version_family=version_family,
        rest_port=_validate_port(rest_port, "rest_port"),
        grpc_port=_validate_port(grpc_port, "grpc_port"),
    )


def _validate_port(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1 or value > 65535:
        raise ValueError(f"{field_name} must be between 1 and 65535")
    return value


def _validate_timeout(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("timeout_s must be numeric")
    clean = float(value)
    if not math.isfinite(clean) or clean <= 0.0:
        raise ValueError("timeout_s must be finite and > 0")
    return clean


async def check_rest_health(host: str, port: int, timeout_s: float) -> bool:
    """Return whether Qdrant REST health responds successfully."""

    clean_port = _validate_port(port, "rest_port")
    clean_timeout = _validate_timeout(timeout_s)
    url = f"http://{host}:{clean_port}/healthz"
    try:
        async with httpx.AsyncClient(timeout=clean_timeout) as client:
            response = await client.get(url)
            return 200 <= response.status_code < 300
    except (httpx.HTTPError, OSError):
        return False


async def fetch_server_version(host: str, port: int, timeout_s: float) -> str | None:
    """Fetch Qdrant server version from a non-destructive REST endpoint."""

    clean_port = _validate_port(port, "rest_port")
    clean_timeout = _validate_timeout(timeout_s)
    url = f"http://{host}:{clean_port}/"
    try:
        async with httpx.AsyncClient(timeout=clean_timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except (ValueError, httpx.HTTPError, OSError):
        return None

    if not isinstance(payload, dict):
        return None
    version = payload.get("version")
    # Returns None if the field is absent, for example behind a proxy response.
    # That keeps ready=False as the safe default instead of assuming parity.
    return version if isinstance(version, str) and version else None


async def check_grpc_probe(host: str, grpc_port: int, timeout_s: float) -> bool:
    """Return whether Qdrant gRPC can answer a non-destructive collections probe."""

    clean_port = _validate_port(grpc_port, "grpc_port")
    clean_timeout = _validate_timeout(timeout_s)
    client = AsyncQdrantClient(
        host=host,
        grpc_port=clean_port,
        prefer_grpc=True,
        timeout=max(1, math.ceil(clean_timeout)),
    )
    try:
        await client.get_collections()
        return True
    except (Exception, OSError):
        return False
    finally:
        await client.close()


def build_readiness_report(
    *,
    target_server_version: str,
    target_client_version: str,
    version_family: str,
    qdrant_client_version: str,
    qdrant_server_version: str | None,
    rest_port: int,
    grpc_port: int,
    rest_ok: bool,
    grpc_ok: bool,
    checked_at_utc: str | None = None,
) -> QdrantReadiness:
    """Build a readiness report from already-collected probe values."""

    clean_rest_port = _validate_port(rest_port, "rest_port")
    clean_grpc_port = _validate_port(grpc_port, "grpc_port")
    version_exact_parity_ok = (
        qdrant_server_version is not None
        and qdrant_client_version == qdrant_server_version
    )
    version_family_ok = (
        qdrant_server_version is not None
        and qdrant_server_version.startswith(f"{version_family}.")
        and qdrant_client_version.startswith(f"{version_family}.")
    )
    ready = bool(
        rest_ok
        and grpc_ok
        and version_family_ok
        and qdrant_server_version == target_server_version
        and qdrant_client_version == target_client_version
    )
    return QdrantReadiness(
        schema_version=READINESS_SCHEMA_VERSION,
        checked_at_utc=checked_at_utc if checked_at_utc is not None else _utc_now_iso(),
        target_server_version=target_server_version,
        target_client_version=target_client_version,
        qdrant_client_version=qdrant_client_version,
        qdrant_server_version=qdrant_server_version,
        version_family=version_family,
        version_family_ok=version_family_ok,
        version_exact_parity_ok=version_exact_parity_ok,
        rest_port=clean_rest_port,
        grpc_port=clean_grpc_port,
        rest_ok=rest_ok,
        grpc_ok=grpc_ok,
        ready=ready,
    )


def assert_qdrant_118_ready(report: QdrantReadiness) -> None:
    """Raise RuntimeError if the local Qdrant 1.18 readiness contract is not met."""

    if report.qdrant_client_version != report.target_client_version:
        raise RuntimeError("unexpected qdrant client version")
    if report.qdrant_server_version != report.target_server_version:
        raise RuntimeError("unexpected qdrant server version")
    if not report.version_family_ok:
        raise RuntimeError("qdrant client/server version family mismatch")
    if not report.rest_ok:
        raise RuntimeError("qdrant REST probe failed")
    if not report.grpc_ok:
        raise RuntimeError("qdrant gRPC probe failed")
    if not report.ready:
        raise RuntimeError("qdrant readiness contract failed")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check local Qdrant 1.18 readiness.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--rest-port", type=int, default=None)
    parser.add_argument("--grpc-port", type=int, default=None)
    parser.add_argument("--target-server-version", default=None)
    parser.add_argument("--target-client-version", default=None)
    parser.add_argument("--version-family", default=None)
    parser.add_argument(
        "--version-contract",
        type=Path,
        default=DEFAULT_VERSION_CONTRACT_PATH,
    )
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    return parser


async def async_main(argv: Sequence[str] | None = None) -> int:
    """Run the async readiness probes and emit safe JSON to stdout."""

    args = _build_parser().parse_args(argv)
    contract = load_version_contract(args.version_contract)
    timeout_s = _validate_timeout(args.timeout_s)
    rest_port = _validate_port(
        contract.rest_port if args.rest_port is None else args.rest_port,
        "rest_port",
    )
    grpc_port = _validate_port(
        contract.grpc_port if args.grpc_port is None else args.grpc_port,
        "grpc_port",
    )
    target_server_version = (
        contract.server_target_version
        if args.target_server_version is None
        else args.target_server_version
    )
    target_client_version = (
        contract.client_target_version
        if args.target_client_version is None
        else args.target_client_version
    )
    version_family = (
        contract.version_family if args.version_family is None else args.version_family
    )

    rest_ok, server_version, grpc_ok = await asyncio.gather(
        check_rest_health(args.host, rest_port, timeout_s),
        fetch_server_version(args.host, rest_port, timeout_s),
        check_grpc_probe(args.host, grpc_port, timeout_s),
    )
    report = build_readiness_report(
        target_server_version=target_server_version,
        target_client_version=target_client_version,
        version_family=version_family,
        qdrant_client_version=_client_version(),
        qdrant_server_version=server_version,
        rest_port=rest_port,
        grpc_port=grpc_port,
        rest_ok=rest_ok,
        grpc_ok=grpc_ok,
    )
    sys.stdout.write(json.dumps(report.to_dict(), indent=2, ensure_ascii=False, sort_keys=True))
    sys.stdout.write("\n")
    return 0 if report.ready else 2


def main(argv: Sequence[str] | None = None) -> int:
    """Synchronous CLI entrypoint."""

    try:
        return asyncio.run(async_main(argv))
    except Exception as exc:
        sys.stderr.write(f"qdrant readiness failed: {type(exc).__name__}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
