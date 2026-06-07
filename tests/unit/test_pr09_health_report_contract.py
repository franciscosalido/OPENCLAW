from __future__ import annotations

from integration.health_report import build_health_report, render_markdown


def test_health_report_schema_and_markdown_are_safe() -> None:
    report = build_health_report()
    markdown = render_markdown(report)

    assert report["schema_version"] == "quimera-health-report-v1"
    assert "services" in report
    assert "table_sizes" in report
    assert "active_sessions_24h" in report
    assert "top_queries" in report
    assert "backup" in report
    assert "baseline_comparison" in report
    assert "Top Queries" in markdown
    assert "Backup" in markdown
    for forbidden in ("Authorization", "api_key", "password", "postgresql://"):
        assert forbidden not in markdown
