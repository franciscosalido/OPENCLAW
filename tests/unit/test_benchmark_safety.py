from __future__ import annotations

import pytest

from evaluation.benchmark_safety import (
    BenchmarkSafetyError,
    assert_no_forbidden_keys,
    litellm_cache_bypass_headers,
    require_cache_disabled,
    validate_benchmark_collection_name,
)


def test_benchmark_requires_cache_disabled() -> None:
    with pytest.raises(RuntimeError, match="QUIMERA_CACHE_ENABLED=0"):
        require_cache_disabled({})


def test_litellm_cache_bypass_header() -> None:
    assert litellm_cache_bypass_headers() == {"x-litellm-cache": "no-cache"}


def test_benchmark_blocks_sensitive_keys() -> None:
    with pytest.raises(BenchmarkSafetyError):
        assert_no_forbidden_keys({"safe": {"api_key": "nope"}})


def test_benchmark_collection_name_must_be_synthetic() -> None:
    assert validate_benchmark_collection_name("quimera_benchmark_session_context_abc123")
    with pytest.raises(BenchmarkSafetyError):
        validate_benchmark_collection_name("quimera_knowledge")
