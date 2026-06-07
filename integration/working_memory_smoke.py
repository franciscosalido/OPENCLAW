"""Degraded-safe PR-10 working-memory smoke report."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


OUTPUT = Path("evaluation/results/rag_01b_pr10_working_memory_smoke.json")
SCHEMA_VERSION = "rag-01b-pr10-working-memory-smoke-v1"


def build_skipped_smoke(*, reason: str = "live stack not requested") -> dict[str, Any]:
    session_id = str(uuid4())
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "skipped",
        "collection": "quimera_working_memory",
        "agent_id": "agent-pr10-smoke",
        "session_id": session_id,
        "upserted_count": 0,
        "snapshot_id": None,
        "restored_count": 0,
        "checksum_ok": False,
        "query_before_restore_count": 0,
        "query_after_restore_count": 0,
        "generated_at": datetime.now(UTC).isoformat(),
        "warnings": [reason],
    }


def write_smoke_report(report: dict[str, Any], path: Path = OUTPUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    report = build_skipped_smoke()
    write_smoke_report(report)
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
