from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_pr09_health_report_live_outputs_files(tmp_path: Path) -> None:
    json_path = tmp_path / "health.json"
    md_path = tmp_path / "health.md"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    bootstrap = """
import sys
from pathlib import Path

import pytest

from integration import health_report

output_path = Path(sys.argv[1])
with pytest.MonkeyPatch.context() as monkeypatch:
    monkeypatch.setattr(health_report, "HEALTH_REPORT_PATH", output_path)
    monkeypatch.setattr(
        sys, "argv", ["integration.health_report", *sys.argv[2:]]
    )
    raise SystemExit(health_report.main())
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            bootstrap,
            str(tmp_path / "rag_01b_pr09_health_report.json"),
            "--json",
            str(json_path),
            "--markdown",
            str(md_path),
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")
    assert payload["schema_version"] == "quimera-health-report-v1"
    assert "services" in payload
    assert "Backup" in markdown
    assert "postgresql://" not in markdown
