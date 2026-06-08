from __future__ import annotations

from integration.agentic0_contracts import Agentic0SmokeConfig, skipped_result
from integration.report_writer import smoke_summary_payload
from integration.safety_scan import (
    assert_no_forbidden_fields,
    find_forbidden_fields,
    is_safe_trace_id,
    json_has_no_forbidden_fields,
)


def test_report_payload_has_no_forbidden_content() -> None:
    result = skipped_result(Agentic0SmokeConfig(), reason="unit")
    payload = smoke_summary_payload(result)

    assert payload["safety"]["forbidden_fields_seen"] == ()
    assert find_forbidden_fields(payload) == []
    assert json_has_no_forbidden_fields(payload) is True
    assert is_safe_trace_id(result.correlation_id)
    assert_no_forbidden_fields(payload)


def test_report_scanner_catches_raw_content_keys() -> None:
    assert find_forbidden_fields(
        {"raw_prompt": "x", "safe": {"document_text": "y"}}
    ) == ["document_text", "raw_prompt"]
    assert json_has_no_forbidden_fields({"safe": {"raw_prompt": "x"}}) is False


def test_report_scanner_allows_audit_flags() -> None:
    payload = {
        "safety": {
            "secrets_seen": False,
            "vectors_seen": False,
            "raw_chunks_seen": False,
            "forbidden_fields_seen": (),
        }
    }

    assert find_forbidden_fields(payload) == []
    assert json_has_no_forbidden_fields(payload) is True
