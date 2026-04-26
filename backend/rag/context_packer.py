"""Context packing primitives for the local RAG pipeline.

The packer is deterministic and network-free: it deduplicates retrieved chunks,
keeps the highest-scoring candidate for near-duplicate text, and trims the final
context to a token budget.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


DEFAULT_MAX_CONTEXT_TOKENS = 8000
DEFAULT_DEDUP_SIMILARITY_THRESHOLD = 0.92
DEFAULT_SECURITY_LEVEL = "Level 2"

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class RetrievedChunk:
    """A retrieved text chunk ready for context packing and prompting."""

    id: str
    score: float
    doc_id: str
    chunk_index: int
    text: str
    token_count: int
    rank: int = 0
    security_level: str = DEFAULT_SECURITY_LEVEL
    payload: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        rank: int = 0,
    ) -> RetrievedChunk:
        """Build a retrieved chunk from a vector-store result dictionary."""

        payload = _payload_from_mapping(data)
        doc_id = _string_field(data, payload, "doc_id")
        chunk_index = _integer_field(data, payload, "chunk_index")
        text = _string_field(data, payload, "text")
        token_count = _token_count_field(data, payload, text)
        security_level = _optional_string_field(
            data,
            payload,
            "security_level",
            DEFAULT_SECURITY_LEVEL,
        )

        chunk_id = str(data.get("id") or f"{doc_id}#{chunk_index}")
        return cls(
            id=chunk_id,
            score=float(data.get("score", 0.0)),
            doc_id=doc_id,
            chunk_index=chunk_index,
            text=text,
            token_count=token_count,
            rank=rank,
            security_level=security_level,
            payload=payload,
        )

    @property
    def citation_id(self) -> str:
        """Return the stable source citation id for prompt builders."""

        return f"{self.doc_id}#{self.chunk_index}"


@dataclass(frozen=True)
class ContextPacker:
    """Deduplicate and trim retrieved chunks for prompt construction."""

    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS
    dedup_similarity_threshold: float = DEFAULT_DEDUP_SIMILARITY_THRESHOLD

    def __post_init__(self) -> None:
        if self.max_context_tokens <= 0:
            raise ValueError("max_context_tokens must be greater than zero")
        if not 0.0 <= self.dedup_similarity_threshold <= 1.0:
            raise ValueError(
                "dedup_similarity_threshold must be between 0.0 and 1.0"
            )

    def pack(self, chunks: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
        """Return deduplicated chunks that fit the configured token budget.

        Selection is score-first: near-duplicates lose to the higher-scoring
        chunk. The final output is reordered by document position so the local
        model receives a readable context.
        """

        if not chunks:
            return []

        deduplicated = self._deduplicate(chunks)
        limited = self._apply_token_limit(deduplicated)
        return sorted(limited, key=lambda chunk: (chunk.doc_id, chunk.chunk_index))

    def _deduplicate(
        self,
        chunks: Sequence[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        ordered = sorted(chunks, key=lambda chunk: (-chunk.score, chunk.rank))
        kept: list[RetrievedChunk] = []

        for candidate in ordered:
            if not any(
                _jaccard_similarity(candidate.text, existing.text)
                >= self.dedup_similarity_threshold
                for existing in kept
            ):
                kept.append(candidate)

        return kept

    def _apply_token_limit(
        self,
        chunks: Sequence[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        selected: list[RetrievedChunk] = []
        total_tokens = 0

        for chunk in chunks:
            if total_tokens + chunk.token_count > self.max_context_tokens:
                continue
            selected.append(chunk)
            total_tokens += chunk.token_count

        return selected


def _payload_from_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    payload = data.get("payload", {})
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping when provided")
    return dict(payload)


def _string_field(
    data: Mapping[str, Any],
    payload: Mapping[str, Any],
    key: str,
) -> str:
    raw_value = data.get(key, payload.get(key))
    if not isinstance(raw_value, str):
        raise TypeError(f"{key} must be a string")
    value = raw_value.strip()
    if not value:
        raise ValueError(f"{key} cannot be empty")
    return value


def _optional_string_field(
    data: Mapping[str, Any],
    payload: Mapping[str, Any],
    key: str,
    default: str,
) -> str:
    raw_value = data.get(key, payload.get(key, default))
    if not isinstance(raw_value, str):
        raise TypeError(f"{key} must be a string")
    value = raw_value.strip()
    if not value:
        raise ValueError(f"{key} cannot be empty")
    return value


def _integer_field(
    data: Mapping[str, Any],
    payload: Mapping[str, Any],
    key: str,
) -> int:
    raw_value = data.get(key, payload.get(key))
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise TypeError(f"{key} must be an integer")
    if raw_value < 0:
        raise ValueError(f"{key} cannot be negative")
    return int(raw_value)


def _token_count_field(
    data: Mapping[str, Any],
    payload: Mapping[str, Any],
    text: str,
) -> int:
    raw_value = data.get("token_count", payload.get("token_count"))
    if raw_value is None:
        return _count_tokens(text)
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise TypeError("token_count must be an integer")
    if raw_value <= 0:
        raise ValueError("token_count must be greater than zero")
    return int(raw_value)


def _count_tokens(text: str) -> int:
    return len(_TOKEN_RE.findall(text))


def _jaccard_similarity(left: str, right: str) -> float:
    left_tokens = set(_TOKEN_RE.findall(left.casefold()))
    right_tokens = set(_TOKEN_RE.findall(right.casefold()))

    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0

    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
