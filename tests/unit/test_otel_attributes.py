from __future__ import annotations

from backend.observability import attributes as attrs


def test_attribute_sets_have_no_duplicates() -> None:
    all_values = [*attrs.GENAI_ATTRS, *attrs.MCP_ATTRS, *attrs.QUIMERA_ATTRS]

    assert len(all_values) == len(set(all_values))


def test_required_semantic_attributes_are_declared() -> None:
    assert "gen_ai.operation.name" in attrs.GENAI_ATTRS
    assert "gen_ai.provider.name" in attrs.GENAI_ATTRS
    assert "gen_ai.response.model" in attrs.GENAI_ATTRS
    assert "db.system.name" in attrs.DB_ATTRS
    assert "db.operation.name" in attrs.DB_ATTRS
    assert "mcp.method.name" in attrs.MCP_ATTRS
    assert "retrieval.cache_hit" in attrs.QUIMERA_ATTRS
    assert "latency.llm_ms" in attrs.QUIMERA_ATTRS


def test_allowed_attribute_constants_do_not_contain_sensitive_keys() -> None:
    forbidden = attrs.PII_FORBIDDEN_ATTRS

    assert attrs.SAFE_ATTRS.isdisjoint(forbidden)


def test_attribute_names_are_lowercase_dotted_tokens() -> None:
    for key in attrs.SAFE_ATTRS:
        assert key == key.lower()
        assert " " not in key
        assert "." in key
