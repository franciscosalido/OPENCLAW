from __future__ import annotations

import json
import os
import subprocess

import pytest

pytestmark = pytest.mark.integration


def test_pr09_pg_stat_report_live_parseable() -> None:
    if not (os.getenv("QUIMERA_POSTGRES_DSN") or os.getenv("TEST_POSTGRES_DSN")):
        pytest.skip("Postgres DSN not configured")

    result = subprocess.run(
        ["uv", "run", "python", "-m", "infra.postgres.pg_stat_report", "--json"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "quimera-pg-stat-report-v1"
    assert "pg_stat_statements" in payload
    assert "top_queries" in payload
    assert "query" not in json.dumps(payload["top_queries"]).lower()
