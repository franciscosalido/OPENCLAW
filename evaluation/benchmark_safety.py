from __future__ import annotations

import os
import re
from collections.abc import Mapping

FORBIDDEN_BENCHMARK_KEYS = frozenset(
    {
        "prompt",
        "raw_prompt",
        "answer",
        "response",
        "chunk_text",
        "document_text",
        "vector",
        "embedding",
        "authorization",
        "api_key",
        "secret",
        "password",
        "dsn",
        "connection_string",
    }
)


class BenchmarkSafetyError(ValueError):
    pass


class BenchmarkBackendUnavailable(RuntimeError):
    pass


def require_cache_disabled(env: Mapping[str, str] | None = None) -> None:
    env_map = os.environ if env is None else env
    if env_map.get("QUIMERA_CACHE_ENABLED") != "0":
        raise RuntimeError("Benchmark requires QUIMERA_CACHE_ENABLED=0")


def litellm_cache_bypass_headers() -> dict[str, str]:
    return {"x-litellm-cache": "no-cache"}


def assert_no_forbidden_keys(mapping: Mapping[str, object]) -> None:
    for key, value in mapping.items():
        lowered = key.lower()
        if lowered in FORBIDDEN_BENCHMARK_KEYS or any(token in lowered for token in FORBIDDEN_BENCHMARK_KEYS):
            raise BenchmarkSafetyError(f"forbidden benchmark key: {key}")
        if isinstance(value, Mapping):
            assert_no_forbidden_keys(value)


def validate_benchmark_collection_name(name: str) -> str:
    if not re.fullmatch(r"quimera_benchmark_session_context_[a-z0-9_]+", name):
        raise BenchmarkSafetyError("benchmark collection name must use the PR-07 synthetic prefix")
    return name
