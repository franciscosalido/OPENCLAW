"""Safe pg_stat_statements report generation."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg  # type: ignore[import-untyped]

from infra.postgres.backup_manifest import sanitize_dsn

REPORT_SCHEMA_VERSION = "quimera-pg-stat-report-v1"
_LITERAL_RE = re.compile(r"('(?:''|[^'])*'|\\b\\d+(?:\\.\\d+)?\\b)")


def build_degraded_report(*, warning: str) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "pg_stat_statements": {
            "available": False,
            "installed": False,
            "track": "unknown",
            "max": 0,
            "track_io_timing": "unknown",
        },
        "top_queries": [],
        "warnings": [warning],
    }


def redact_query_text(query: str) -> str:
    return _LITERAL_RE.sub("?", query)


async def build_report(*, include_query_text: bool = False, strict: bool = False) -> dict[str, Any]:
    dsn = os.getenv("QUIMERA_POSTGRES_DSN") or os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        return build_degraded_report(warning="postgres DSN not configured")
    try:
        conn = await asyncpg.connect(dsn)
    except Exception as exc:  # pragma: no cover - environment dependent
        warning = f"postgres connection unavailable: {type(exc).__name__}"
        if strict:
            raise RuntimeError(warning) from exc
        return build_degraded_report(warning=warning)
    try:
        return await _report_from_connection(conn, include_query_text=include_query_text)
    finally:
        await conn.close()


async def _report_from_connection(conn: asyncpg.Connection, *, include_query_text: bool) -> dict[str, Any]:
    available_row = await conn.fetchrow(
        "SELECT default_version, installed_version FROM pg_available_extensions WHERE name = 'pg_stat_statements'"
    )
    installed_row = await conn.fetchrow("SELECT extversion FROM pg_extension WHERE extname = 'pg_stat_statements'")
    settings = await _settings(conn)
    warnings: list[str] = []
    if settings["track"] != "all":
        warnings.append("pg_stat_statements.track is not all")
    if settings["max"] < 10000:
        warnings.append("pg_stat_statements.max below 10000")
    if settings["track_io_timing"] != "on":
        warnings.append("track_io_timing is not on")
    top_queries: list[dict[str, Any]] = []
    if installed_row:
        rows = await conn.fetch(
            """
            SELECT queryid, calls, total_exec_time, mean_exec_time, rows,
                   shared_blk_read_time, shared_blk_write_time, query
            FROM pg_stat_statements(showtext := $1)
            ORDER BY mean_exec_time DESC
            LIMIT 10
            """,
            include_query_text,
        )
        for row in rows:
            item = {
                "queryid": str(row["queryid"]),
                "calls": int(row["calls"]),
                "mean_exec_time_ms": float(row["mean_exec_time"]),
                "total_exec_time_ms": float(row["total_exec_time"]),
                "rows": int(row["rows"]),
                "shared_blk_read_time_ms": float(row["shared_blk_read_time"]),
                "shared_blk_write_time_ms": float(row["shared_blk_write_time"]),
            }
            if include_query_text and row["query"]:
                item["query_text_redacted"] = redact_query_text(str(row["query"]))
            top_queries.append(item)
    else:
        warnings.append("pg_stat_statements extension is not installed")
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "pg_stat_statements": {
            "available": bool(available_row),
            "installed": bool(installed_row),
            "track": settings["track"],
            "max": settings["max"],
            "track_io_timing": settings["track_io_timing"],
        },
        "top_queries": top_queries,
        "warnings": warnings,
    }


async def _settings(conn: asyncpg.Connection) -> dict[str, Any]:
    async def setting(name: str) -> str:
        try:
            return str(await conn.fetchval("SELECT current_setting($1, true)", name) or "unknown")
        except asyncpg.PostgresError:
            return "unknown"

    max_value = await setting("pg_stat_statements.max")
    try:
        max_int = int(max_value)
    except ValueError:
        max_int = 0
    return {
        "track": await setting("pg_stat_statements.track"),
        "max": max_int,
        "track_io_timing": await setting("track_io_timing"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--include-query-text", action="store_true")
    args = parser.parse_args()
    try:
        report = asyncio.run(build_report(include_query_text=args.include_query_text, strict=args.strict))
    except RuntimeError as exc:
        print(json.dumps(build_degraded_report(warning=sanitize_dsn(str(exc))), sort_keys=True))
        return 1 if args.strict else 0
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(f"pg_stat_report: installed={report['pg_stat_statements']['installed']} top_queries={len(report['top_queries'])}")
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
