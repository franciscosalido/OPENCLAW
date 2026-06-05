from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_pr09_health_report_live_outputs_files(tmp_path: Path) -> None:
    json_path = tmp_path / "health.json"
    md_path = tmp_path / "health.md"
    result = subprocess.run(
        ["uv", "run", "python", "-m", "integration.health_report", "--json", str(json_path), "--markdown", str(md_path)],
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
