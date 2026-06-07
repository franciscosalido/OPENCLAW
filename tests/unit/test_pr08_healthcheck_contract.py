from __future__ import annotations

import json

import pytest

from integration import check_integration_health


def test_integration_health_json_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        check_integration_health,
        "build_status_report",
        lambda: {
            "services": {
                "ollama": {"status": "ok"},
                "litellm": {"status": "ok"},
                "qdrant": {"status": "ok"},
                "postgres": {"status": "ok"},
            }
        },
    )
    monkeypatch.setattr(check_integration_health, "_litellm_models", lambda: {"status": "ok", "aliases": ["qwen3-local", "nomic-embed-text"], "required_aliases_present": True})

    report = check_integration_health.build_integration_health_report()
    encoded = json.dumps(report)

    assert report["schema_version"] == "quimera-pr08-integration-health-v1"
    assert report["overall"] in {"ok", "degraded", "fail"}
    assert {"ollama", "litellm", "qdrant", "postgres"}.issubset(report["services"])
    assert "dsn" not in encoded.lower()
    assert "secret" not in encoded.lower()
    assert report["mcp_servers"]["quimera_postgres_memory"]["gateway_introspection_skipped"] is True
