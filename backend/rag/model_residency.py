"""Configurable local RAG model residency controls."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


LOCAL_RAG_ALIAS = "local_rag"
ALLOWED_MODEL_RESIDENCY_ALIASES = frozenset({LOCAL_RAG_ALIAS})
ALLOWED_KEEP_ALIVE_VALUES = frozenset({"0", "30s", "1m", "5m", "10m", "30m", "-1"})
DEFAULT_KEEP_ALIVE = "5m"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAG_CONFIG_PATH = REPO_ROOT / "config" / "rag_config.yaml"


@dataclass(frozen=True)
class ModelResidencyConfig:
    """Rollback-safe model residency config for ``local_rag``."""

    enabled: bool = False
    apply_to_aliases: tuple[str, ...] = (LOCAL_RAG_ALIAS,)
    keep_alive: str = DEFAULT_KEEP_ALIVE

    def validated(self) -> ModelResidencyConfig:
        """Return normalized config or raise a clear validation error."""
        if not isinstance(self.enabled, bool):
            raise TypeError("rag.model_residency.enabled must be boolean")
        aliases = tuple(
            _validate_model_residency_alias(alias)
            for alias in self.apply_to_aliases
        )
        if not aliases:
            raise ValueError("rag.model_residency.apply_to_aliases cannot be empty")
        keep_alive = _validate_keep_alive(self.keep_alive)
        return ModelResidencyConfig(
            enabled=self.enabled,
            apply_to_aliases=aliases,
            keep_alive=keep_alive,
        )


@dataclass(frozen=True)
class ModelResidencyDecision:
    """Per-call local RAG model residency decision."""

    enabled: bool
    keep_alive: str | None

    @property
    def keep_alive_applied(self) -> bool:
        """Return whether keep_alive should be forwarded to generation."""
        return self.keep_alive is not None


def decide_model_residency(
    config: ModelResidencyConfig,
    *,
    alias: str | None,
) -> ModelResidencyDecision:
    """Return the model residency decision for one model alias."""
    if (
        not config.enabled
        or alias is None
        or alias not in config.apply_to_aliases
    ):
        return ModelResidencyDecision(enabled=False, keep_alive=None)
    return ModelResidencyDecision(enabled=True, keep_alive=config.keep_alive)


def load_model_residency_config(
    config_path: str | Path = DEFAULT_RAG_CONFIG_PATH,
) -> ModelResidencyConfig:
    """Load ``rag.model_residency`` from the RAG config file."""
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("rag_config.yaml must contain a mapping")
    rag = raw.get("rag")
    if not isinstance(rag, Mapping):
        raise ValueError("rag_config.yaml must contain rag mapping")
    model_residency = rag.get("model_residency", {})
    if model_residency is None:
        model_residency = {}
    if not isinstance(model_residency, Mapping):
        raise ValueError("rag.model_residency must be a mapping")
    return ModelResidencyConfig(
        enabled=_bool_value(model_residency, "enabled", False),
        apply_to_aliases=_alias_tuple(
            model_residency,
            "apply_to_aliases",
            (LOCAL_RAG_ALIAS,),
        ),
        keep_alive=_string_value(
            model_residency,
            "keep_alive",
            DEFAULT_KEEP_ALIVE,
        ),
    ).validated()


def _bool_value(mapping: Mapping[str, Any], key: str, default: bool) -> bool:
    value = mapping.get(key, default)
    if not isinstance(value, bool):
        raise TypeError(f"rag.model_residency.{key} must be boolean")
    return value


def _string_value(mapping: Mapping[str, Any], key: str, default: str) -> str:
    value = mapping.get(key, default)
    if not isinstance(value, str):
        raise TypeError(f"rag.model_residency.{key} must be a string")
    return value


def _alias_tuple(
    mapping: Mapping[str, Any],
    key: str,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    value = mapping.get(key, default)
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError(f"rag.model_residency.{key} must be a sequence")
    return tuple(_validate_model_residency_alias(alias) for alias in value)


def _validate_model_residency_alias(alias: object) -> str:
    if not isinstance(alias, str):
        raise TypeError("rag.model_residency aliases must be strings")
    value = alias.strip()
    if not value:
        raise ValueError("rag.model_residency aliases cannot be empty")
    if value not in ALLOWED_MODEL_RESIDENCY_ALIASES:
        raise ValueError(
            "rag.model_residency.apply_to_aliases supports only "
            f"{sorted(ALLOWED_MODEL_RESIDENCY_ALIASES)} in G2-05"
        )
    return value


def _validate_keep_alive(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("rag.model_residency.keep_alive must be a string")
    clean = value.strip()
    if clean not in ALLOWED_KEEP_ALIVE_VALUES:
        raise ValueError(
            "rag.model_residency.keep_alive must be one of "
            f"{sorted(ALLOWED_KEEP_ALIVE_VALUES)}"
        )
    return clean
