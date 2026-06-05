from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_pr09_run_smoke_quick_json_parseable() -> None:
    result = subprocess.run(["bash", "run_smoke.sh", "--quick", "--json", "--no-build", "--timeout", "5", "--allow-degraded"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=90)

    assert result.returncode in {0, 2}
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "quimera-pr09-smoke-summary-v1"
    assert Path("evaluation/results/rag_01b_pr09_smoke_summary.json").exists()
    assert "down -v" not in result.stdout + result.stderr
