from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_pr09_run_smoke_quick_json_parseable(tmp_path: Path) -> None:
    summary_path = tmp_path / "rag_01b_pr09_smoke_summary.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    bootstrap = """
import sys
from pathlib import Path

import pytest

from integration import smoke_summary

output_path = Path(sys.argv[1])
with pytest.MonkeyPatch.context() as monkeypatch:
    monkeypatch.setattr(smoke_summary, "SMOKE_SUMMARY_PATH", output_path)
    monkeypatch.setattr(
        sys, "argv", ["integration.smoke_summary", *sys.argv[2:]]
    )
    raise SystemExit(smoke_summary.main())
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            bootstrap,
            str(summary_path),
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
    assert summary_path.exists()
    assert "down -v" not in result.stdout + result.stderr
