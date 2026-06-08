from __future__ import annotations

import pytest

from backend.observability.safety import (
    assert_no_pii_keys,
    redact_mapping,
    sanitize_error_message,
    validate_attribute_key,
    validate_attribute_value,
    validate_attributes,
)


def test_validate_allows_official_response_model_attribute() -> None:
    assert validate_attribute_key("gen_ai.response.model") == "gen_ai.response.model"


@pytest.mark.parametrize(
    "key",
    ["prompt", "quimera.prompt", "chunk_text", "cache.raw_payload", "quimera.api_key"],
)
def test_validate_blocks_sensitive_attribute_keys(key: str) -> None:
    with pytest.raises(ValueError):
        validate_attribute_key(key)


def test_validate_blocks_secret_like_values() -> None:
    with pytest.raises(ValueError):
        validate_attribute_value("postgresql://user:secret@127.0.0.1:5432/db")


def test_validate_attributes_returns_sanitized_copy() -> None:
    assert validate_attributes({"retrieval.cache_hit": True}) == {
        "retrieval.cache_hit": True
    }


def test_sanitize_error_message_redacts_dsn() -> None:
    msg = sanitize_error_message("failed postgresql://user:secret@127.0.0.1/db")

    assert "secret" not in msg
    assert "[REDACTED]" in msg


def test_redact_mapping_recurses_sensitive_keys() -> None:
    redacted = redact_mapping({"safe": {"api_key": "secret"}, "prompt": "hello"})

    assert redacted["prompt"] == "[REDACTED]"
    assert redacted["safe"] == {"api_key": "[REDACTED]"}


def test_assert_no_pii_keys_rejects_nested_payload() -> None:
    with pytest.raises(ValueError):
        assert_no_pii_keys({"quimera.stage": "ok", "quimera.payload": "bad"})
