from __future__ import annotations

import pytest

from backend.rag.cache.cache_fingerprint import (
    build_retrieval_fingerprint,
    sha256_hex,
    stable_json_dumps,
)


def test_stable_json_dumps_is_deterministic() -> None:
    assert stable_json_dumps({"b": 2, "a": 1}) == stable_json_dumps({"a": 1, "b": 2})


def test_sha256_hex_shape() -> None:
    digest = sha256_hex("hello")

    assert len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)


def test_retrieval_fingerprint_is_stable_and_sensitive_to_versions() -> None:
    first = build_retrieval_fingerprint(
        embedding_model="qwen3",
        embedding_dim=1024,
        source_collection="knowledge",
        corpus_epoch="dev",
        profile_name="default",
        extra={"b": 2, "a": 1},
    )
    second = build_retrieval_fingerprint(
        embedding_model="qwen3",
        embedding_dim=1024,
        source_collection="knowledge",
        corpus_epoch="dev",
        profile_name="default",
        extra={"a": 1, "b": 2},
    )
    changed = build_retrieval_fingerprint(
        embedding_model="qwen3-v2",
        embedding_dim=1024,
        source_collection="knowledge",
        corpus_epoch="dev2",
        profile_name="default",
    )

    assert first == second
    assert first != changed
    assert len(first) == 64


@pytest.mark.parametrize("key", ["prompt", "query_text", "answer", "chunks", "secret"])
def test_retrieval_fingerprint_rejects_sensitive_extra(key: str) -> None:
    with pytest.raises(ValueError, match="sensitive"):
        build_retrieval_fingerprint(
            embedding_model="qwen3",
            embedding_dim=1024,
            source_collection="knowledge",
            corpus_epoch="dev",
            profile_name="default",
            extra={key: "bad"},
        )
