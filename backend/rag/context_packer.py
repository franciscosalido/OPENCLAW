"""Context packing primitives for the local RAG pipeline.

The packer is deterministic and network-free: it deduplicates retrieved chunks,
keeps the highest-scoring candidate for near-duplicate text, and trims the final
context to a token budget.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml


DEFAULT_MAX_CONTEXT_TOKENS = 8000
DEFAULT_DEDUP_SIMILARITY_THRESHOLD = 0.92
DEFAULT_SECURITY_LEVEL = "Level 2"
DEFAULT_CONTEXT_BUDGET_MAX_CHUNKS = 3
CONTEXT_BUDGET_MODE: Literal["whole_chunks"] = "whole_chunks"
LOCAL_RAG_ALIAS = "local_rag"
ALLOWED_CONTEXT_BUDGET_ALIASES = frozenset({LOCAL_RAG_ALIAS})
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAG_CONFIG_PATH = REPO_ROOT / "config" / "rag_config.yaml"

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class ContextBudgetConfig:
    """Configurable final context cap for local RAG prompt construction."""

    enabled: bool = False
    max_context_chunks: int | None = DEFAULT_CONTEXT_BUDGET_MAX_CHUNKS
    mode: Literal["whole_chunks"] = CONTEXT_BUDGET_MODE
    apply_to_aliases: tuple[str, ...] = (LOCAL_RAG_ALIAS,)

    def validated(self) -> ContextBudgetConfig:
        """Return normalized budget config or raise a clear configuration error."""

        if not isinstance(self.enabled, bool):
            raise TypeError("rag.context_budget.enabled must be boolean")
        if self.max_context_chunks is not None:
            if isinstance(self.max_context_chunks, bool) or not isinstance(
                self.max_context_chunks,
                int,
            ):
                raise TypeError(
                    "rag.context_budget.max_context_chunks must be an integer"
                )
            if self.max_context_chunks <= 0:
                raise ValueError(
                    "rag.context_budget.max_context_chunks must be greater than zero"
                )
        if self.mode != CONTEXT_BUDGET_MODE:
            raise ValueError('rag.context_budget.mode must be "whole_chunks"')
        aliases = tuple(_validate_budget_alias(alias) for alias in self.apply_to_aliases)
        if not aliases:
            raise ValueError("rag.context_budget.apply_to_aliases cannot be empty")
        return ContextBudgetConfig(
            enabled=self.enabled,
            max_context_chunks=self.max_context_chunks,
            mode=self.mode,
            apply_to_aliases=aliases,
        )


@dataclass(frozen=True)
class ContextBudgetResult:
    """Safe metadata about the final context budget application."""

    enabled: bool
    applied: bool
    chunks_retrieved: int
    chunks_used: int
    chunks_dropped: int
    max_context_chunks: int | None
    estimated_tokens_used: int


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
    context_budget: ContextBudgetConfig = field(
        default_factory=lambda: load_context_budget_config()
    )
    active_alias: str = LOCAL_RAG_ALIAS
    last_budget_result: ContextBudgetResult = field(init=False)

    def __post_init__(self) -> None:
        if self.max_context_tokens <= 0:
            raise ValueError("max_context_tokens must be greater than zero")
        if not 0.0 <= self.dedup_similarity_threshold <= 1.0:
            raise ValueError(
                "dedup_similarity_threshold must be between 0.0 and 1.0"
            )
        budget = self.context_budget.validated()
        object.__setattr__(self, "context_budget", budget)
        object.__setattr__(self, "active_alias", _validate_budget_alias(self.active_alias))
        object.__setattr__(
            self,
            "last_budget_result",
            ContextBudgetResult(
                enabled=False,
                applied=False,
                chunks_retrieved=0,
                chunks_used=0,
                chunks_dropped=0,
                max_context_chunks=budget.max_context_chunks,
                estimated_tokens_used=0,
            ),
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
        ordered = sorted(limited, key=lambda chunk: (chunk.doc_id, chunk.chunk_index))
        return self._apply_context_budget(ordered)

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

    def _apply_context_budget(
        self,
        chunks: Sequence[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        input_chunks = list(chunks)
        enabled = (
            self.context_budget.enabled
            and self.active_alias in self.context_budget.apply_to_aliases
            and self.context_budget.max_context_chunks is not None
        )
        if enabled and self.context_budget.max_context_chunks is not None:
            used_chunks = input_chunks[: self.context_budget.max_context_chunks]
        else:
            used_chunks = input_chunks
        result = ContextBudgetResult(
            enabled=enabled,
            applied=enabled and len(input_chunks) > len(used_chunks),
            chunks_retrieved=len(input_chunks),
            chunks_used=len(used_chunks),
            chunks_dropped=len(input_chunks) - len(used_chunks),
            max_context_chunks=self.context_budget.max_context_chunks,
            estimated_tokens_used=sum(chunk.token_count for chunk in used_chunks),
        )
        object.__setattr__(self, "last_budget_result", result)
        return list(used_chunks)


def load_context_budget_config(
    config_path: str | Path = DEFAULT_RAG_CONFIG_PATH,
) -> ContextBudgetConfig:
    """Load the optional context budget config from ``config/rag_config.yaml``."""

    path = Path(config_path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("rag_config.yaml must contain a mapping")
    rag = raw.get("rag")
    if not isinstance(rag, Mapping):
        raise ValueError("rag_config.yaml must contain rag mapping")
    budget = rag.get("context_budget", {})
    if budget is None:
        budget = {}
    if not isinstance(budget, Mapping):
        raise ValueError("rag.context_budget must be a mapping")
    return ContextBudgetConfig(
        enabled=_bool_value(budget, "enabled", False),
        max_context_chunks=_optional_int_value(
            budget,
            "max_context_chunks",
            DEFAULT_CONTEXT_BUDGET_MAX_CHUNKS,
        ),
        mode=_mode_value(budget, "mode", CONTEXT_BUDGET_MODE),
        apply_to_aliases=_alias_tuple(
            budget,
            "apply_to_aliases",
            (LOCAL_RAG_ALIAS,),
        ),
    ).validated()


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


def _bool_value(
    mapping: Mapping[str, Any],
    key: str,
    default: bool,
) -> bool:
    value = mapping.get(key, default)
    if not isinstance(value, bool):
        raise TypeError(f"rag.context_budget.{key} must be boolean")
    return value


def _optional_int_value(
    mapping: Mapping[str, Any],
    key: str,
    default: int | None,
) -> int | None:
    value = mapping.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"rag.context_budget.{key} must be an integer")
    return int(value)


def _mode_value(
    mapping: Mapping[str, Any],
    key: str,
    default: Literal["whole_chunks"],
) -> Literal["whole_chunks"]:
    value = mapping.get(key, default)
    if value != CONTEXT_BUDGET_MODE:
        raise ValueError('rag.context_budget.mode must be "whole_chunks"')
    return CONTEXT_BUDGET_MODE


def _alias_tuple(
    mapping: Mapping[str, Any],
    key: str,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    value = mapping.get(key, default)
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError(f"rag.context_budget.{key} must be a sequence of aliases")
    return tuple(_validate_budget_alias(alias) for alias in value)


def _validate_budget_alias(alias: object) -> str:
    if not isinstance(alias, str):
        raise TypeError("rag.context_budget aliases must be strings")
    value = alias.strip()
    if not value:
        raise ValueError("rag.context_budget aliases cannot be empty")
    if value not in ALLOWED_CONTEXT_BUDGET_ALIASES:
        raise ValueError(
            "rag.context_budget.apply_to_aliases supports only "
            f"{sorted(ALLOWED_CONTEXT_BUDGET_ALIASES)} in G2-02"
        )
    return value
