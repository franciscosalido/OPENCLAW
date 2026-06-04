from __future__ import annotations

import json
import subprocess

import pytest

pytestmark = pytest.mark.integration


def test_start_quimera_status_json_live_shape() -> None:
    result = subprocess.run(
        ["bash", "scripts/start_quimera.sh", "status", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert "postgres" in data["services"]
    assert "qdrant" in data["services"]
