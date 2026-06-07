from __future__ import annotations

import json
from pathlib import Path

from infra.litellm.audit import AUDIT_SCHEMA_VERSION, build_litellm_audit, write_audit_report


def _fake_http_getter(url: str, _timeout: float) -> tuple[int | None, dict[str, str]]:
    if url.endswith("/api/version"):
        return 200, {"version": "0.test"}
    return 200, {"status": "ok"}


def test_audit_schema_and_contracts_are_present(tmp_path: Path) -> None:
    report = build_litellm_audit(
        env={"LITELLM_MASTER_KEY": "local-dev-key"},
        runtime_config_path=tmp_path / "missing-runtime.yaml",
    )

    assert report.data["schema_version"] == AUDIT_SCHEMA_VERSION
    assert set(report.data["contracts"]) == {f"RC-{index:02d}" for index in range(1, 25)}
    assert report.status in {"pass", "warn"}
    assert report.data["cache"]["collection"] == "quimera_llm_cache"
    assert report.data["cache"]["rag_cache_collision"] is False


def test_audit_report_does_not_contain_sensitive_markers(tmp_path: Path) -> None:
    report = build_litellm_audit(env={"LITELLM_MASTER_KEY": "local-dev-key"})
    text = report.to_json()

    for marker in ("Authorization:", "Bearer ", "sk-", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        assert marker not in text


def test_audit_writes_json_and_markdown(tmp_path: Path) -> None:
    report = build_litellm_audit(env={"LITELLM_MASTER_KEY": "local-dev-key"})
    json_path = tmp_path / "litellm_audit.json"
    markdown_path = tmp_path / "litellm_audit.md"

    write_audit_report(report, json_path=json_path, markdown_path=markdown_path)

    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == AUDIT_SCHEMA_VERSION
    assert "LiteLLM Host Audit" in markdown_path.read_text(encoding="utf-8")


def test_litellm_audit_is_not_a_start_quimera_subcommand() -> None:
    text = Path("scripts/start_quimera.sh").read_text(encoding="utf-8")

    assert "litellm-audit)" not in text
    assert "python -m infra.litellm.audit" not in text
    assert "Accepted commands: --start, --stop, --status" in text or "--status) _status ;;" in text
