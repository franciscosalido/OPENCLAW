"""Ollama keep-alive and warmup configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Self


DEFAULT_ENV_FILE = Path(__file__).with_name("ollama_config.env")


@dataclass(frozen=True, slots=True, kw_only=True)
class OllamaConfig:
    """Validated local Ollama tuning configuration."""

    base_url: str = "http://127.0.0.1:11434"
    keep_alive: int | str = -1
    num_parallel: int = 2
    max_loaded_models: int = 2
    embed_model: str = "nomic-embed-text:latest"
    chat_model: str = "qwen3:14b"
    warmup_timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("base_url cannot be empty")
        _validate_keep_alive(self.keep_alive)
        if self.num_parallel <= 0:
            raise ValueError("num_parallel must be > 0")
        if self.max_loaded_models < 2:
            raise ValueError("max_loaded_models must be >= 2")
        if not self.embed_model.strip():
            raise ValueError("embed_model cannot be empty")
        if not self.chat_model.strip():
            raise ValueError("chat_model cannot be empty")
        if self.warmup_timeout_seconds <= 0:
            raise ValueError("warmup_timeout_seconds must be > 0")

    @classmethod
    def from_mapping(cls, values: dict[str, str]) -> Self:
        return cls(
            base_url=values.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            keep_alive=_parse_keep_alive(values.get("OLLAMA_KEEP_ALIVE", "-1")),
            num_parallel=int(values.get("OLLAMA_NUM_PARALLEL", "2")),
            max_loaded_models=int(values.get("OLLAMA_MAX_LOADED_MODELS", "2")),
            embed_model=values.get(
                "QUIMERA_OLLAMA_EMBED_MODEL",
                "nomic-embed-text:latest",
            ),
            chat_model=values.get("QUIMERA_OLLAMA_CHAT_MODEL", "qwen3:14b"),
            warmup_timeout_seconds=float(
                values.get("QUIMERA_OLLAMA_WARMUP_TIMEOUT_SECONDS", "120")
            ),
        )


def load_ollama_config(env_file: Path | None = None) -> OllamaConfig:
    """Load config from an optional env file, with real environment winning."""

    resolved_env_file = DEFAULT_ENV_FILE if env_file is None else env_file
    values = _read_env_file(resolved_env_file)
    for key in (
        "OLLAMA_BASE_URL",
        "OLLAMA_KEEP_ALIVE",
        "OLLAMA_NUM_PARALLEL",
        "OLLAMA_MAX_LOADED_MODELS",
        "QUIMERA_OLLAMA_EMBED_MODEL",
        "QUIMERA_OLLAMA_CHAT_MODEL",
        "QUIMERA_OLLAMA_WARMUP_TIMEOUT_SECONDS",
    ):
        if key in os.environ:
            values[key] = os.environ[key]
    return OllamaConfig.from_mapping(values)


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _parse_keep_alive(value: str) -> int | str:
    clean = value.strip()
    if not clean:
        raise ValueError("keep_alive cannot be empty")
    try:
        return int(clean)
    except ValueError:
        return clean


def _validate_keep_alive(value: int | str) -> None:
    if isinstance(value, int):
        return
    if not value.strip():
        raise ValueError("keep_alive cannot be empty")
