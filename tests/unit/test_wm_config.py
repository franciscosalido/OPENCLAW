from __future__ import annotations

from typing import Any, cast

import pytest

from backend.working_memory.config import WorkingMemorySettings


def test_wm_settings_defaults() -> None:
    settings = WorkingMemorySettings()

    assert settings.enabled is True
    assert settings.qdrant_url == "http://127.0.0.1:6333"
    assert settings.collection_name == "quimera_working_memory"
    assert settings.vector_name == "work-dense"
    assert settings.vector_size == 768
    assert settings.distance == "Cosine"
    assert settings.default_ttl_seconds == 3600
    assert settings.max_points_per_session == 512
    assert settings.snapshot_every_writes == 20
    assert settings.snapshot_interval_seconds == 300
    assert settings.restore_enabled is False
    assert settings.cleanup_enabled is False


def test_wm_settings_reads_quimera_wm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUIMERA_WM_ENABLED", "0")
    monkeypatch.setenv("QUIMERA_WM_COLLECTION", "quimera_working_memory_test_a")
    monkeypatch.setenv("QUIMERA_WM_VECTOR_SIZE", "16")
    monkeypatch.setenv("QUIMERA_WM_DEFAULT_TTL_SECONDS", "30")

    settings = WorkingMemorySettings()

    assert settings.enabled is False
    assert settings.collection_name == "quimera_working_memory_test_a"
    assert settings.vector_size == 16
    assert settings.default_ttl_seconds == 30


@pytest.mark.parametrize(
    "field,value",
    [
        ("qdrant_url", "https://example.com"),
        ("qdrant_url", "http://10.0.0.2:6333"),
        ("collection_name", "quimera_query_cache"),
        ("collection_name", "working_memory"),
        ("vector_name", " "),
        ("vector_size", 0),
        ("default_ttl_seconds", 0),
        ("max_points_per_session", 0),
        ("snapshot_every_writes", 0),
        ("snapshot_interval_seconds", 0),
    ],
)
def test_wm_settings_validation(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        WorkingMemorySettings(**cast(Any, {field: value}))


def test_wm_settings_forbids_cache_and_hybrid_collections() -> None:
    for collection in ("quimera_knowledge", "quimera_query_cache", "quimera_llm_cache"):
        with pytest.raises(ValueError):
            WorkingMemorySettings(collection_name=collection)
