from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


REMOTE_PROVIDER_PREFIXES = (
    "openai/",
    "anthropic/",
    "gemini/",
    "google/",
    "openrouter/",
    "xai/",
    "azure/",
)
REMOTE_KEY_MARKERS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENROUTER_API_KEY",
    "XAI_API_KEY",
    "AZURE_API_KEY",
)
ALLOWED_ENV_REFS = {
    "OLLAMA_API_BASE",
    "OLLAMA_BASE_URL",
    "LITELLM_LOCAL_CHAT_MODEL",
    "LITELLM_LOCAL_EMBED_MODEL",
    "LITELLM_MASTER_KEY",
    "QDRANT_API_BASE",
}
ENV_DEFAULTS = {
    "OLLAMA_API_BASE": "http://127.0.0.1:11434",
    "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
    "LITELLM_LOCAL_CHAT_MODEL": "ollama_chat/qwen3:14b",
    "LITELLM_LOCAL_EMBED_MODEL": "ollama/nomic-embed-text:latest",
    "QDRANT_API_BASE": "http://127.0.0.1:6333",
}


class ConfigValidationError(ValueError):
    """Raised when the host LiteLLM configuration violates local policy."""


def _env_value(value: str, env: Mapping[str, str]) -> str:
    prefix = "os.environ/"
    if not value.startswith(prefix):
        return value
    key = value.removeprefix(prefix)
    if key not in ALLOWED_ENV_REFS:
        raise ConfigValidationError(f"unsupported environment reference: {key}")
    return env.get(key, ENV_DEFAULTS.get(key, value))


def _is_loopback_http(url: str, *, expected_port: int | None = None) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "http":
        return False
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return False
    if expected_port is not None and parsed.port != expected_port:
        return False
    return True


class LiteLLMParams(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    api_base: str
    timeout: int = Field(gt=0)
    stream_timeout: int = Field(gt=0)
    max_retries: int = Field(ge=0, le=3)

    @field_validator("model")
    @classmethod
    def model_must_be_local_or_env_ref(cls, value: str) -> str:
        lowered = value.lower()
        if lowered.startswith(REMOTE_PROVIDER_PREFIXES):
            raise ValueError("remote provider model is forbidden")
        if value.startswith("os.environ/"):
            key = value.removeprefix("os.environ/")
            if key not in {"LITELLM_LOCAL_CHAT_MODEL", "LITELLM_LOCAL_EMBED_MODEL"}:
                raise ValueError(f"unsupported model environment reference: {key}")
        elif not lowered.startswith(("ollama/", "ollama_chat/")):
            raise ValueError("LiteLLM model must use local Ollama provider")
        return value

    @field_validator("api_base")
    @classmethod
    def api_base_must_be_loopback_or_env_ref(cls, value: str) -> str:
        if value.startswith("os.environ/"):
            key = value.removeprefix("os.environ/")
            if key not in {"OLLAMA_API_BASE", "OLLAMA_BASE_URL"}:
                raise ValueError(f"unsupported api_base environment reference: {key}")
            return value
        if not _is_loopback_http(value, expected_port=11434):
            raise ValueError("api_base must be local loopback Ollama")
        return value


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    provider: str
    purpose: str

    @field_validator("provider")
    @classmethod
    def provider_must_be_ollama(cls, value: str) -> str:
        if value != "ollama":
            raise ValueError("provider must be ollama")
        return value


class ModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str
    litellm_params: LiteLLMParams
    model_info: ModelInfo


class CacheParams(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    qdrant_api_base: str | None = None
    qdrant_collection_name: str | None = None
    qdrant_semantic_cache_embedding_model: str | None = None
    qdrant_semantic_cache_vector_size: int | None = None
    similarity_threshold: float | None = None

    @model_validator(mode="after")
    def qdrant_semantic_policy(self) -> "CacheParams":
        if self.type != "qdrant-semantic":
            return self
        if self.qdrant_collection_name != "quimera_llm_cache":
            raise ValueError("qdrant semantic cache must use quimera_llm_cache")
        if self.qdrant_collection_name == "quimera_query_cache":
            raise ValueError("LLM cache collection must differ from retrieval cache")
        if self.qdrant_semantic_cache_embedding_model != "quimera_embed":
            raise ValueError("semantic cache embedding model must be quimera_embed")
        if self.qdrant_semantic_cache_vector_size != 768:
            raise ValueError("semantic cache vector size must be 768")
        if self.similarity_threshold is None or not 0.0 < self.similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must be between 0 and 1")
        return self


class LiteLLMSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    cache: bool = False
    cache_params: CacheParams | None = None
    drop_params: bool = True
    set_verbose: bool = False
    json_logs: bool = True
    turn_off_message_logging: bool = True
    redact_user_api_key_info: bool = True
    num_retries: int = Field(default=1, ge=0, le=3)
    request_timeout: int = Field(default=130, gt=0)

    @model_validator(mode="after")
    def cache_requires_params(self) -> "LiteLLMSettings":
        if self.cache and self.cache_params is None:
            raise ValueError("cache_params is required when cache is enabled")
        return self


class GeneralSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    master_key: str
    disable_spend_logs: bool = True

    @field_validator("master_key")
    @classmethod
    def master_key_must_be_env_ref(cls, value: str) -> str:
        if value != "os.environ/LITELLM_MASTER_KEY":
            raise ValueError("master_key must use os.environ/LITELLM_MASTER_KEY")
        return value


class ConfigRoot(BaseModel):
    model_config = ConfigDict(extra="allow")

    model_list: list[ModelEntry]
    litellm_settings: LiteLLMSettings
    general_settings: GeneralSettings

    @model_validator(mode="after")
    def required_aliases_present(self) -> "ConfigRoot":
        names = {entry.model_name for entry in self.model_list}
        required = {
            "local_chat",
            "local_think",
            "local_rag",
            "local_json",
            "quimera_embed",
            "local_embed",
        }
        missing = sorted(required - names)
        if missing:
            raise ValueError(f"missing required LiteLLM aliases: {missing}")
        return self


def load_raw_config(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigValidationError(f"{path} must contain a YAML mapping")
    return raw


def validate_no_literal_secrets(raw_text: str) -> None:
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "master_key:" in stripped and "os.environ/LITELLM_MASTER_KEY" not in stripped:
            raise ConfigValidationError("literal secret found in LiteLLM master_key")
        for marker in REMOTE_KEY_MARKERS:
            if marker in stripped:
                raise ConfigValidationError(f"remote provider key marker is forbidden: {marker}")


def assert_host_local_qdrant_url(url: str) -> None:
    if not _is_loopback_http(url, expected_port=6333):
        raise ConfigValidationError("Qdrant URL must be local loopback HTTP on port 6333")


def validate_provider_safety(config: ConfigRoot, env: Mapping[str, str]) -> None:
    for model in config.model_list:
        params = model.litellm_params
        resolved_model = _env_value(params.model, env)
        if resolved_model.lower().startswith(REMOTE_PROVIDER_PREFIXES):
            raise ConfigValidationError("remote provider model is forbidden")
        if not resolved_model.lower().startswith(("ollama/", "ollama_chat/")):
            raise ConfigValidationError("model must resolve to local Ollama provider")
        resolved_api_base = _env_value(params.api_base, env)
        if not _is_loopback_http(resolved_api_base, expected_port=11434):
            raise ConfigValidationError("Ollama API base must resolve to local loopback")

    cache_params = config.litellm_settings.cache_params
    if cache_params and cache_params.type == "qdrant-semantic":
        qdrant_url = _env_value(cache_params.qdrant_api_base or "os.environ/QDRANT_API_BASE", env)
        if qdrant_url.startswith("os.environ/"):
            qdrant_url = "http://127.0.0.1:6333"
        assert_host_local_qdrant_url(qdrant_url)


def validate_litellm_config(path: Path, env: Mapping[str, str] | None = None) -> ConfigRoot:
    env_map = os.environ if env is None else env
    raw_text = path.read_text(encoding="utf-8")
    validate_no_literal_secrets(raw_text)
    raw = load_raw_config(path)
    try:
        config = ConfigRoot.model_validate(raw)
    except ValueError as exc:
        raise ConfigValidationError(str(exc)) from exc
    validate_provider_safety(config, env_map)
    return config


async def smoke_test_qdrant(url: str, timeout_seconds: float = 2.0) -> bool:
    assert_host_local_qdrant_url(url)
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(f"{url.rstrip('/')}/healthz")
        return response.status_code < 400
    except httpx.HTTPError:
        return False


def smoke_test_qdrant_sync(url: str, timeout_seconds: float = 2.0) -> bool:
    try:
        return asyncio.run(smoke_test_qdrant(url, timeout_seconds=timeout_seconds))
    except RuntimeError:
        return False


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else Path("infra/litellm/litellm_config.yaml")
    config = validate_litellm_config(path)
    cache_params = config.litellm_settings.cache_params
    cache_backend = cache_params.type if cache_params else "disabled"
    sys.stdout.write(f"path={path}\n")
    sys.stdout.write(f"models={len(config.model_list)}\n")
    sys.stdout.write(f"cache_backend={cache_backend}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
