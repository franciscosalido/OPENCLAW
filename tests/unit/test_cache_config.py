from __future__ import annotations

from typing import Any, cast

import pytest

from backend.rag.cache.cache_config import CacheSettings


def test_cache_settings_defaults() -> None:
    settings = CacheSettings()

    assert settings.enabled is True
    assert settings.collection_name == "quimera_query_cache"
    assert settings.threshold == 0.92
    assert settings.vector_size == 1024
    assert settings.distance == "Cosine"
    assert settings.similarity_threshold == settings.threshold


def test_cache_settings_reads_quimera_cache_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUIMERA_CACHE_ENABLED", "0")
    monkeypatch.setenv("QUIMERA_CACHE_COLLECTION_NAME", "cache_test")
    monkeypatch.setenv("QUIMERA_CACHE_THRESHOLD", "0.7")
    monkeypatch.setenv("QUIMERA_CACHE_VECTOR_SIZE", "768")
    monkeypatch.setenv("QUIMERA_CACHE_DEFAULT_TTL_SECONDS", "60")
    monkeypatch.setenv("QUIMERA_CACHE_MAX_RESULT_DOCS", "10")

    settings = CacheSettings()

    assert settings.enabled is False
    assert settings.collection_name == "cache_test"
    assert settings.threshold == 0.7
    assert settings.vector_size == 768
    assert settings.default_ttl_seconds == 60
    assert settings.max_result_docs == 10


def test_cache_settings_ignores_unprefixed_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENABLED", "0")

    assert CacheSettings().enabled is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("threshold", -0.1),
        ("threshold", 1.1),
        ("vector_size", 0),
        ("collection_name", " "),
        ("embedding_model", " "),
        ("profile_name", " "),
        ("source_collection", " "),
        ("corpus_epoch", " "),
        ("default_ttl_seconds", 0),
        ("max_result_docs", 0),
        ("hot_entries_oversample_factor", 0),
    ],
)
def test_cache_settings_validation(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        CacheSettings(**cast(Any, {field: value}))


def test_cache_settings_rejects_cache_collection_as_source_collection() -> None:
    with pytest.raises(
        ValueError,
        match="collection_name and source_collection must differ",
    ):
        CacheSettings(
            collection_name="quimera_query_cache",
            source_collection="quimera_query_cache",
        )


def test_cache_settings_does_not_use_field_aliases() -> None:
    fields = CacheSettings.model_fields

    assert all(field.alias is None for field in fields.values())
