from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_pr09_run_smoke_quick_json_parseable() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "integration.smoke_summary",
            "--mode",
            "quick",
            "--json",
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=90,
    )

    assert result.returncode in {0, 2}
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "quimera-pr09-smoke-summary-v1"
    assert payload["status"] == payload["overall"]
    assert Path("evaluation/results/rag_01b_pr09_smoke_summary.json").exists()
    assert "down -v" not in result.stdout + result.stderr
