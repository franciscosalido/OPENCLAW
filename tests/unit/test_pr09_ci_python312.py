from __future__ import annotations

from pathlib import Path

import yaml


WORKFLOW = Path(".github/workflows/pr09-python312.yml")


def test_pr09_ci_runs_required_suites_on_python312_venv() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)

    assert workflow["jobs"]["pr09-python312"]["runs-on"] == "ubuntu-latest"
    assert 'python-version: "3.12"' in text
    assert "astral-sh/setup-uv@v7" in text
    assert "uv venv --python 3.12 .venv" in text
    assert "uv sync --python .venv/bin/python --frozen" in text
    assert ".venv/bin/python -m pytest" in text
    for path in (
        "tests/unit/test_pr09_backup_manifest.py",
        "tests/unit/test_pr09_pg_stat_report.py",
        "tests/unit/test_pr09_health_report_contract.py",
        "tests/unit/test_pr09_latency_baseline.py",
    ):
        assert path in text
