from __future__ import annotations

import pytest

from backend.mcp.mcp_safety import (
    McpSafetyError,
    validate_collection_name,
    validate_limit,
    validate_safe_mapping,
    validate_uuid,
)


def test_mcp_safety_validates_uuid_and_limit() -> None:
    assert validate_uuid("00000000-0000-0000-0000-000000000001", "session_id")
    assert validate_limit(10) == 10


def test_mcp_safety_rejects_bad_values() -> None:
    with pytest.raises(McpSafetyError):
        validate_uuid("bad", "session_id")
    with pytest.raises(McpSafetyError):
        validate_limit(101)
    with pytest.raises(McpSafetyError):
        validate_safe_mapping({"prompt": "raw"})


def test_qdrant_collection_names_are_restricted() -> None:
    assert validate_collection_name("quimera_query_cache") == "quimera_query_cache"
    with pytest.raises(McpSafetyError):
        validate_collection_name("../quimera_query_cache")

