from __future__ import annotations

import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.integration


def test_pr08_integration_health_json_parseable() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "integration.check_integration_health", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert data["schema_version"] == "quimera-pr08-integration-health-v1"
    assert {"ollama", "litellm", "qdrant", "postgres"}.issubset(data["services"])
    assert "secret" not in result.stdout.lower()
    assert "dsn" not in result.stdout.lower()
