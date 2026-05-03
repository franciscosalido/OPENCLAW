"""Configurable local RAG generation budget controls."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


LOCAL_RAG_ALIAS = "local_rag"
ALLOWED_GENERATION_BUDGET_ALIASES = frozenset({LOCAL_RAG_ALIAS})
DEFAULT_GENERATION_BUDGET_MAX_TOKENS = 768
DEFAULT_TARGET_SENTENCES_MIN = 3
DEFAULT_TARGET_SENTENCES_MAX = 6
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAG_CONFIG_PATH = REPO_ROOT / "config" / "rag_config.yaml"


@dataclass(frozen=True)
class GenerationBudgetConfig:
    """Rollback-safe generation budget config for ``local_rag``."""

    enabled: bool = False
    apply_to_aliases: tuple[str, ...] = (LOCAL_RAG_ALIAS,)
    max_tokens: int | None = DEFAULT_GENERATION_BUDGET_MAX_TOKENS
    enforce_conciseness: bool = False
    target_sentences_min: int = DEFAULT_TARGET_SENTENCES_MIN
    target_sentences_max: int = DEFAULT_TARGET_SENTENCES_MAX

    def validated(self) -> GenerationBudgetConfig:
        """Return normalized config or raise a clear validation error."""
        if not isinstance(self.enabled, bool):
            raise TypeError("rag.generation_budget.enabled must be boolean")
        if self.max_tokens is not None:
            if isinstance(self.max_tokens, bool) or not isinstance(self.max_tokens, int):
                raise TypeError("rag.generation_budget.max_tokens must be an integer")
            if self.max_tokens <= 0:
                raise ValueError(
                    "rag.generation_budget.max_tokens must be greater than zero"
                )
        if not isinstance(self.enforce_conciseness, bool):
            raise TypeError(
                "rag.generation_budget.enforce_conciseness must be boolean"
            )
        if isinstance(self.target_sentences_min, bool) or not isinstance(
            self.target_sentences_min,
            int,
        ):
            raise TypeError(
                "rag.generation_budget.target_sentences_min must be an integer"
            )
        if isinstance(self.target_sentences_max, bool) or not isinstance(
            self.target_sentences_max,
            int,
        ):
            raise TypeError(
                "rag.generation_budget.target_sentences_max must be an integer"
            )
        if self.target_sentences_min < 1:
            raise ValueError(
                "rag.generation_budget.target_sentences_min must be at least 1"
            )
        if self.target_sentences_max < self.target_sentences_min:
            raise ValueError(
                "rag.generation_budget.target_sentences_max must be greater than "
                "or equal to target_sentences_min"
            )
        aliases = tuple(
            _validate_generation_budget_alias(alias)
            for alias in self.apply_to_aliases
        )
        if not aliases:
            raise ValueError("rag.generation_budget.apply_to_aliases cannot be empty")
        return GenerationBudgetConfig(
            enabled=self.enabled,
            apply_to_aliases=aliases,
            max_tokens=self.max_tokens,
            enforce_conciseness=self.enforce_conciseness,
            target_sentences_min=self.target_sentences_min,
            target_sentences_max=self.target_sentences_max,
        )


@dataclass(frozen=True)
class GenerationBudgetDecision:
    """Per-call local RAG generation budget decision."""

    enabled: bool
    max_tokens: int | None
    conciseness_instruction: str | None

    @property
    def max_tokens_applied(self) -> bool:
        """Return whether a token cap should be forwarded to generation."""
        return self.max_tokens is not None

    @property
    def conciseness_instruction_applied(self) -> bool:
        """Return whether prompt discipline should be added."""
        return self.conciseness_instruction is not None


def decide_generation_budget(
    config: GenerationBudgetConfig,
    *,
    alias: str | None,
) -> GenerationBudgetDecision:
    """Return the generation budget decision for one model alias."""
    normalized = config.validated()
    if (
        not normalized.enabled
        or alias is None
        or alias not in normalized.apply_to_aliases
    ):
        return GenerationBudgetDecision(
            enabled=False,
            max_tokens=None,
            conciseness_instruction=None,
        )
    instruction = (
        _conciseness_instruction(normalized)
        if normalized.enforce_conciseness
        else None
    )
    return GenerationBudgetDecision(
        enabled=True,
        max_tokens=normalized.max_tokens,
        conciseness_instruction=instruction,
    )


def load_generation_budget_config(
    config_path: str | Path = DEFAULT_RAG_CONFIG_PATH,
) -> GenerationBudgetConfig:
    """Load ``rag.generation_budget`` from the RAG config file."""
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("rag_config.yaml must contain a mapping")
    rag = raw.get("rag")
    if not isinstance(rag, Mapping):
        raise ValueError("rag_config.yaml must contain rag mapping")
    generation_budget = rag.get("generation_budget", {})
    if generation_budget is None:
        generation_budget = {}
    if not isinstance(generation_budget, Mapping):
        raise ValueError("rag.generation_budget must be a mapping")
    return GenerationBudgetConfig(
        enabled=_bool_value(generation_budget, "enabled", False),
        apply_to_aliases=_alias_tuple(
            generation_budget,
            "apply_to_aliases",
            (LOCAL_RAG_ALIAS,),
        ),
        max_tokens=_optional_int_value(
            generation_budget,
            "max_tokens",
            DEFAULT_GENERATION_BUDGET_MAX_TOKENS,
        ),
        enforce_conciseness=_bool_value(
            generation_budget,
            "enforce_conciseness",
            False,
        ),
        target_sentences_min=_int_value(
            generation_budget,
            "target_sentences_min",
            DEFAULT_TARGET_SENTENCES_MIN,
        ),
        target_sentences_max=_int_value(
            generation_budget,
            "target_sentences_max",
            DEFAULT_TARGET_SENTENCES_MAX,
        ),
    ).validated()


def _conciseness_instruction(config: GenerationBudgetConfig) -> str:
    return (
        "Responda de forma concisa, normalmente em "
        f"{config.target_sentences_min} a {config.target_sentences_max} frases. "
        "Preserve as evidencias mais relevantes e inclua citacoes quando o "
        "contexto estiver disponivel. Nao repita trechos recuperados na integra. "
        "Se o contexto for insuficiente, diga isso claramente."
    )


def _bool_value(mapping: Mapping[str, Any], key: str, default: bool) -> bool:
    value = mapping.get(key, default)
    if not isinstance(value, bool):
        raise TypeError(f"rag.generation_budget.{key} must be boolean")
    return value


def _int_value(mapping: Mapping[str, Any], key: str, default: int) -> int:
    value = mapping.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"rag.generation_budget.{key} must be an integer")
    return int(value)


def _optional_int_value(
    mapping: Mapping[str, Any],
    key: str,
    default: int | None,
) -> int | None:
    value = mapping.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"rag.generation_budget.{key} must be an integer")
    return int(value)


def _alias_tuple(
    mapping: Mapping[str, Any],
    key: str,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    value = mapping.get(key, default)
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError(f"rag.generation_budget.{key} must be a sequence")
    return tuple(_validate_generation_budget_alias(alias) for alias in value)


def _validate_generation_budget_alias(alias: object) -> str:
    if not isinstance(alias, str):
        raise TypeError("rag.generation_budget aliases must be strings")
    value = alias.strip()
    if not value:
        raise ValueError("rag.generation_budget aliases cannot be empty")
    if value not in ALLOWED_GENERATION_BUDGET_ALIASES:
        raise ValueError(
            "rag.generation_budget.apply_to_aliases supports only "
            f"{sorted(ALLOWED_GENERATION_BUDGET_ALIASES)} in G2-03"
        )
    return value
