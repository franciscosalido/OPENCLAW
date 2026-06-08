"""Collect a safe, read-only Qdrant metrics snapshot for Q18 benchmarks."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

SNAPSHOT_SCHEMA_VERSION = "qdrant-metrics-snapshot-v1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6333
DEFAULT_COLLECTION = "quimera_benchmark_hybrid_118_qwen3"
FORBIDDEN_OUTPUT_TOKENS = (
    "query_text",
    "chunk_text",
    "document_text",
    "payload",
    "dense_vector",
    "sparse_vector",
    "vectors_raw",
    "embedding",
    "prompt",
    "answer",
)
_METRIC_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{(?P<labels>[^}]*)\})?\s+"
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)$"
)
_LABEL_RE = re.compile(r'(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)="(?P<value>[^"]*)"')


@dataclass(frozen=True, slots=True)
class QdrantMetricsSnapshot:
    """Safe Qdrant metrics summary without payloads, vectors or query text."""

    schema_version: str
    snapshot_at_utc: str
    collection: str
    qdrant_server_version: str | None
    memory_resident_bytes: int | None
    collection_vectors: int | None
    collection_points: int | None
    metrics_endpoint: str
    telemetry_endpoint: str
    notes: tuple[str, ...] = ()

    def to_safe_dict(self) -> dict[str, object]:
        """Return a JSON-safe snapshot mapping."""

        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "snapshot_at_utc": self.snapshot_at_utc,
            "collection": self.collection,
            "qdrant_server_version": self.qdrant_server_version,
            "memory_resident_bytes": self.memory_resident_bytes,
            "collection_vectors": self.collection_vectors,
            "collection_points": self.collection_points,
            "metrics_endpoint": self.metrics_endpoint,
            "telemetry_endpoint": self.telemetry_endpoint,
            "notes": list(self.notes),
        }
        _assert_safe_payload(payload)
        return payload


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_collection_name(collection: str) -> str:
    if not isinstance(collection, str):
        raise TypeError("collection must be a string")
    clean = collection.strip()
    if not clean:
        raise ValueError("collection cannot be empty")
    if "\x00" in clean:
        raise ValueError("collection cannot contain null byte")
    return clean


def _assert_safe_payload(payload: Mapping[str, object]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True).lower()
    for token in FORBIDDEN_OUTPUT_TOKENS:
        if token in serialized:
            raise ValueError(f"forbidden output token: {token}")


def _parse_labels(raw: str | None) -> dict[str, str]:
    if raw is None:
        return {}
    return {
        match.group("key"): match.group("value") for match in _LABEL_RE.finditer(raw)
    }


def _parse_metric_lines(metrics_text: str) -> list[tuple[str, dict[str, str], float]]:
    parsed: list[tuple[str, dict[str, str], float]] = []
    for line in metrics_text.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        match = _METRIC_RE.match(clean)
        if match is None:
            continue
        value = float(match.group("value"))
        if not math.isfinite(value):
            continue
        parsed.append(
            (match.group("name"), _parse_labels(match.group("labels")), value)
        )
    return parsed


def parse_metrics_snapshot(
    *,
    collection: str,
    metrics_text: str,
    telemetry: Mapping[str, object] | None = None,
    snapshot_at_utc: str | None = None,
) -> QdrantMetricsSnapshot:
    """Parse Qdrant `/metrics?per_collection=true` into a safe snapshot."""

    clean_collection = _validate_collection_name(collection)
    metrics = _parse_metric_lines(metrics_text)
    server_version = _server_version_from_metrics(metrics)
    if server_version is None and telemetry is not None:
        server_version = _server_version_from_telemetry(telemetry)

    return QdrantMetricsSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        snapshot_at_utc=snapshot_at_utc or _utc_now_iso(),
        collection=clean_collection,
        qdrant_server_version=server_version,
        memory_resident_bytes=_resident_memory_from_metrics(metrics),
        collection_vectors=_collection_metric_sum(
            metrics, "collection_vectors", clean_collection
        ),
        collection_points=_collection_metric_sum(
            metrics, "collection_points", clean_collection
        ),
        metrics_endpoint="/metrics?per_collection=true",
        telemetry_endpoint="/telemetry",
        notes=(
            "read_only_metrics_snapshot",
            "no_sensitive_text_or_raw_vectors",
        ),
    )


def _server_version_from_metrics(
    metrics: Sequence[tuple[str, dict[str, str], float]],
) -> str | None:
    for name, labels, value in metrics:
        if name in {"app_info", "qdrant_app_info"} and value == 1.0:
            version = labels.get("version")
            if version:
                return version
    return None


def _server_version_from_telemetry(telemetry: Mapping[str, object]) -> str | None:
    result = telemetry.get("result")
    if isinstance(result, Mapping):
        nested = _server_version_from_telemetry(result)
        if nested is not None:
            return nested
    app = telemetry.get("app")
    if isinstance(app, Mapping):
        version = app.get("version")
        return version if isinstance(version, str) and version else None
    app_info = telemetry.get("app_info")
    if isinstance(app_info, Mapping):
        version = app_info.get("version")
        return version if isinstance(version, str) and version else None
    return None


def _resident_memory_from_metrics(
    metrics: Sequence[tuple[str, dict[str, str], float]],
) -> int | None:
    for wanted in (
        "memory_resident_bytes",
        "qdrant_memory_resident_bytes",
        "process_resident_memory_bytes",
    ):
        for name, _labels, value in metrics:
            if name == wanted:
                return max(0, int(value))
    return None


def _collection_metric_sum(
    metrics: Sequence[tuple[str, dict[str, str], float]],
    metric_name: str,
    collection: str,
) -> int | None:
    values = [
        int(value)
        for name, labels, value in metrics
        if name in {metric_name, f"qdrant_{metric_name}"}
        and labels.get("collection", labels.get("id")) == collection
    ]
    return sum(values) if values else None


async def collect_snapshot(
    *,
    host: str,
    port: int,
    collection: str,
    timeout_s: float,
) -> QdrantMetricsSnapshot:
    """Fetch Qdrant metrics and telemetry without mutating collections."""

    clean_collection = _validate_collection_name(collection)
    base_url = f"http://{host}:{port}"
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout_s) as client:
        metrics_response, telemetry_response = await asyncio.gather(
            client.get("/metrics", params={"per_collection": "true"}),
            client.get("/telemetry"),
        )
    metrics_response.raise_for_status()
    telemetry: Mapping[str, object] | None
    try:
        raw_telemetry = telemetry_response.json()
        telemetry = raw_telemetry if isinstance(raw_telemetry, Mapping) else None
    except ValueError:
        telemetry = None
    return parse_metrics_snapshot(
        collection=clean_collection,
        metrics_text=metrics_response.text,
        telemetry=telemetry,
    )


def write_snapshot(snapshot: QdrantMetricsSnapshot, output: Path) -> None:
    """Write a safe snapshot JSON file."""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            snapshot.to_safe_dict(), indent=2, ensure_ascii=False, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect a safe Qdrant metrics snapshot."
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--timeout-s", type=float, default=5.0)
    parser.add_argument("--output", type=Path, default=None)
    return parser


async def async_main(argv: Sequence[str] | None = None) -> int:
    """Collect and emit a read-only metrics snapshot."""

    args = _build_parser().parse_args(argv)
    snapshot = await collect_snapshot(
        host=args.host,
        port=args.port,
        collection=args.collection,
        timeout_s=args.timeout_s,
    )
    if args.output is not None:
        write_snapshot(snapshot, args.output)
    sys.stdout.write(
        json.dumps(
            snapshot.to_safe_dict(), indent=2, ensure_ascii=False, sort_keys=True
        )
    )
    sys.stdout.write("\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Synchronous CLI entrypoint."""

    try:
        return asyncio.run(async_main(argv))
    except Exception as exc:
        sys.stderr.write(f"qdrant metrics snapshot failed: {type(exc).__name__}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
