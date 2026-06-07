from __future__ import annotations

from integration.working_memory_smoke import SCHEMA_VERSION, build_skipped_smoke


def test_working_memory_smoke_report_is_safe() -> None:
    report = build_skipped_smoke(reason="unit")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["status"] == "skipped"
    assert "vector" not in str(report).lower()
    assert "prompt" not in str(report).lower()
    assert "secret" not in str(report).lower()
