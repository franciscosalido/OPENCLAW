from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_start_quimera_status_json_live_shape() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/quimera_status.py"),
            "status",
            "--json",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.stdout.strip().startswith("{"), result.stderr or result.stdout
    data = json.loads(result.stdout)

    assert data["schema_version"] == "quimera-status-v1"
    assert data["overall"] in {"ok", "fail"}
    assert isinstance(data["services"], dict)
    for service_name in ("postgres", "qdrant", "litellm", "ollama"):
        service = data["services"][service_name]
        assert isinstance(service, dict)
        assert service["status"] in {
            "ok",
            "fail",
            "skipped",
            "loaded",
            "missing",
            "unknown",
        }
