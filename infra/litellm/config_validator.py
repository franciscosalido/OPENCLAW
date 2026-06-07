from __future__ import annotations

import asyncio
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping
from urllib.parse import urlparse

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


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
CANONICAL_EMBED_DIM = 768
MINIMUM_EMBED_DIM = 64
CANONICAL_LITELLM_HOST = "127.0.0.1"
CANONICAL_LITELLM_PORT = 4000
CANONICAL_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
CANONICAL_QDRANT_BASE_URL = "http://127.0.0.1:6333"
CANONICAL_LLM_CACHE_COLLECTION = "quimera_llm_cache"
CANONICAL_RAG_CACHE_COLLECTION = "quimera_query_cache"
MCP_ALLOWED_PORTS = {8811, 8812, 8813}
MCP_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
AGENTIC0_ALLOWED_TOOLS = {
    "postgres_memory_health",
    "postgres_recent_turns_get",
    "postgres_agent_state_get",
    "qdrant_memory_health",
    "qdrant_collection_list",
    "qdrant_scroll_safe",
    "working_memory_health",
    "working_memory_points_query",
}
AGENTIC0_OPTIONAL_WRITE_TOOLS = {
    "postgres_agent_state_upsert",
    "working_memory_point_upsert",
    "working_memory_session_snapshot",
}
DESTRUCTIVE_TOOL_PARTS = ("delete", "recreate", "drop", "truncate", "admin", "store")
CHAT_TIMEOUT_SECONDS = 120
CHAT_STREAM_TIMEOUT_SECONDS = 45
EMBED_TIMEOUT_SECONDS = 5
EMBED_STREAM_TIMEOUT_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 165
ALLOWED_ENV_REFS = {
    "OLLAMA_API_BASE",
    "OLLAMA_BASE_URL",
    "LITELLM_LOCAL_CHAT_MODEL",
    "LITELLM_LOCAL_EMBED_MODEL",
    "LITELLM_MASTER_KEY",
    "QDRANT_API_BASE",
}
ENV_DEFAULTS = {
    "OLLAMA_API_BASE": CANONICAL_OLLAMA_BASE_URL,
    "OLLAMA_BASE_URL": CANONICAL_OLLAMA_BASE_URL,
    "LITELLM_LOCAL_CHAT_MODEL": "ollama_chat/qwen3:14b",
    "LITELLM_LOCAL_EMBED_MODEL": "ollama/nomic-embed-text:latest",
    "QDRANT_API_BASE": CANONICAL_QDRANT_BASE_URL,
}


class ConfigValidationError(ValueError):
    """Raised when the host LiteLLM configuration violates local policy."""


@dataclass(frozen=True)
class ContractViolation:
    rule_id: str
    message: str


@dataclass(frozen=True)
class ValidationWarning:
    rule_id: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    config_path: Path
    model_count: int
    cache_backend: str
    warnings: tuple[ValidationWarning, ...]


CacheBackend = Literal["qdrant-semantic", "local", "in-memory"]


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


def is_local_url(value: str, *, allowed_ports: set[int]) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost"}
        and parsed.port in allowed_ports
    )


class LiteLLMParams(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    api_base: str
    timeout: int = Field(gt=0)
    stream_timeout: int = Field(gt=0)
    max_retries: int = Field(ge=0, le=3)

    @model_validator(mode="after")
    def stream_timeout_within_timeout(self) -> "LiteLLMParams":
        if self.stream_timeout > self.timeout:
            raise ValueError("stream_timeout must be <= timeout")
        return self

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
        if self.type not in {"qdrant-semantic", "local", "in-memory"}:
            raise ValueError("cache backend must be qdrant-semantic, local, or in-memory")
        if self.type != "qdrant-semantic":
            return self
        if self.qdrant_collection_name != CANONICAL_LLM_CACHE_COLLECTION:
            raise ValueError(f"qdrant semantic cache must use {CANONICAL_LLM_CACHE_COLLECTION}")
        if self.qdrant_collection_name == CANONICAL_RAG_CACHE_COLLECTION:
            raise ValueError("LLM cache collection must differ from retrieval cache")
        if self.qdrant_semantic_cache_embedding_model not in {"nomic-embed-text", "quimera_embed"}:
            raise ValueError("semantic cache embedding model must be a local embedding alias")
        if self.qdrant_semantic_cache_vector_size is None:
            raise ValueError("semantic cache vector size is required")
        if self.qdrant_semantic_cache_vector_size < MINIMUM_EMBED_DIM:
            raise ValueError(
                f"semantic cache vector size must be >= {MINIMUM_EMBED_DIM}"
            )
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
    request_timeout: int = Field(default=REQUEST_TIMEOUT_SECONDS, gt=0)

    @model_validator(mode="after")
    def cache_requires_params(self) -> "LiteLLMSettings":
        if self.cache and self.cache_params is None:
            raise ValueError("cache_params is required when cache is enabled")
        return self

    @model_validator(mode="after")
    def logging_safety_policy(self) -> "LiteLLMSettings":
        if self.set_verbose:
            raise ValueError("set_verbose must be false")
        if not self.json_logs:
            raise ValueError("json_logs must be true")
        if not self.turn_off_message_logging:
            raise ValueError("turn_off_message_logging must be true")
        if not self.redact_user_api_key_info:
            raise ValueError("redact_user_api_key_info must be true")
        return self


class GeneralSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    master_key: str
    disable_spend_logs: bool = True
    set_verbose: bool | None = None

    @field_validator("master_key")
    @classmethod
    def master_key_must_be_env_ref(cls, value: str) -> str:
        if value != "os.environ/LITELLM_MASTER_KEY":
            raise ValueError("master_key must use os.environ/LITELLM_MASTER_KEY")
        return value

    @model_validator(mode="after")
    def verbose_must_stay_disabled(self) -> "GeneralSettings":
        if self.set_verbose:
            raise ValueError("general_settings.set_verbose must be false")
        return self


class McpServerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    transport: str
    available_on_public_internet: bool = False

    @field_validator("url")
    @classmethod
    def url_must_be_loopback_mcp(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "http":
            raise ValueError("MCP server URL must use http")
        if parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("MCP server URL must be loopback")
        if parsed.port not in MCP_ALLOWED_PORTS:
            raise ValueError("MCP server URL must use approved local MCP ports")
        if parsed.path != "/mcp":
            raise ValueError("MCP server path must be /mcp")
        return value

    @field_validator("transport")
    @classmethod
    def transport_must_be_streamable_http(cls, value: str) -> str:
        if value not in {"streamable_http", "streamable-http"}:
            raise ValueError("MCP transport must be streamable_http")
        return value

    @model_validator(mode="after")
    def mcp_must_not_be_public(self) -> "McpServerEntry":
        if self.available_on_public_internet:
            raise ValueError("MCP server must not be public internet")
        return self


class Agentic0ToolPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    virtual_key_name: str = "agentic0-smoke"
    allowed_tools: tuple[str, ...]
    optional_write_tools: tuple[str, ...] = ()
    destructive_tools_allowed: bool = False

    @model_validator(mode="after")
    def validate_agentic0_tools(self) -> "Agentic0ToolPolicy":
        tools = set(self.allowed_tools)
        if "*" in tools:
            raise ValueError("Agentic0 allowed_tools cannot contain wildcard")
        if any(any(part in tool for part in DESTRUCTIVE_TOOL_PARTS) for tool in tools):
            raise ValueError("Agentic0 allowed_tools cannot contain destructive tools")
        if not AGENTIC0_ALLOWED_TOOLS.issubset(tools):
            missing = sorted(AGENTIC0_ALLOWED_TOOLS - tools)
            raise ValueError(f"Agentic0 allowed_tools missing required tools: {missing}")
        if any(tool not in AGENTIC0_OPTIONAL_WRITE_TOOLS for tool in self.optional_write_tools):
            raise ValueError("Agentic0 optional write tools must be explicitly approved")
        if self.destructive_tools_allowed:
            raise ValueError("Agentic0 destructive tools must remain disabled")
        return self


class ConfigRoot(BaseModel):
    model_config = ConfigDict(extra="allow")

    model_list: list[ModelEntry]
    litellm_settings: LiteLLMSettings
    general_settings: GeneralSettings
    mcp_servers: dict[str, McpServerEntry] = Field(default_factory=dict)
    agentic0_tool_policy: Agentic0ToolPolicy | None = None

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

    @model_validator(mode="after")
    def mcp_servers_are_local_first(self) -> "ConfigRoot":
        for name in self.mcp_servers:
            if not MCP_NAME_RE.fullmatch(name):
                raise ValueError("MCP server names must be lowercase SEP-986-safe hyphenated identifiers")
        return self

    @model_validator(mode="after")
    def canonical_timeouts_present(self) -> "ConfigRoot":
        for entry in self.model_list:
            params = entry.litellm_params
            if entry.model_name in {"local_chat", "local_think", "local_rag", "qwen3-local", "qwen3:14b"}:
                if params.timeout != CHAT_TIMEOUT_SECONDS:
                    raise ValueError("chat model timeout must be 120 seconds")
                if params.stream_timeout != CHAT_STREAM_TIMEOUT_SECONDS:
                    raise ValueError("chat model stream_timeout must be 45 seconds")
            if entry.model_name in {"quimera_embed", "local_embed", "nomic-embed-text"}:
                if params.timeout != EMBED_TIMEOUT_SECONDS:
                    raise ValueError("embedding model timeout must be 5 seconds")
                if params.stream_timeout != EMBED_STREAM_TIMEOUT_SECONDS:
                    raise ValueError("embedding model stream_timeout must be 5 seconds")
        if self.litellm_settings.request_timeout != REQUEST_TIMEOUT_SECONDS:
            raise ValueError("request_timeout must be 165 seconds")
        return self

    @model_validator(mode="after")
    def request_timeout_covers_local_slow_start(self) -> "ConfigRoot":
        if not self.model_list:
            return self
        max_budget = max(
            alias.litellm_params.timeout + alias.litellm_params.stream_timeout
            for alias in self.model_list
            if alias.litellm_params.model != "os.environ/LITELLM_LOCAL_EMBED_MODEL"
        )
        if self.litellm_settings.request_timeout < max_budget:
            raise ValueError(
                f"request_timeout must be at least {max_budget} seconds "
                "to cover local chat timeout plus stream slow-start budget"
            )
        return self


def load_raw_config(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigValidationError(f"{path} contains invalid YAML") from exc
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
        if "api_key:" in stripped and "os.environ/" not in stripped:
            raise ConfigValidationError("literal api_key found in LiteLLM config")
        if "sk-" in stripped:
            raise ConfigValidationError("literal API key marker found in LiteLLM config")
        for marker in REMOTE_KEY_MARKERS:
            if marker in stripped:
                raise ConfigValidationError(f"remote provider key marker is forbidden: {marker}")


def assert_host_local_qdrant_url(url: str) -> None:
    if not _is_loopback_http(url, expected_port=6333):
        raise ConfigValidationError("Qdrant URL must be local loopback HTTP on port 6333")


def validate_no_cache_collision(config: ConfigRoot) -> None:
    cache_params = config.litellm_settings.cache_params
    if not cache_params or not cache_params.qdrant_collection_name:
        return
    if cache_params.qdrant_collection_name == CANONICAL_RAG_CACHE_COLLECTION:
        raise ConfigValidationError("LiteLLM cache collection must not collide with RAG cache")


def validate_host_only_runtime(config: ConfigRoot, env: Mapping[str, str]) -> None:
    validate_provider_safety(config, env)


def validate_no_forbidden_docker_litellm_paths(repo_root: Path) -> None:
    docker_container_key = "container_name:"
    docker_litellm_name = " quimera-" + "litellm"
    forbidden = (
        "berriai/" + "litellm",
        "docker." + "litellm.ai",
        docker_container_key + docker_litellm_name,
    )
    scan_paths = [
        repo_root / "infra",
        repo_root / "scripts",
        repo_root / "docker-compose.yml",
        repo_root / "docker-compose.yaml",
    ]
    for path in scan_paths:
        candidates: Iterable[Path]
        if path.is_dir():
            candidates = path.rglob("*")
        elif path.exists():
            candidates = (path,)
        else:
            continue
        for candidate in candidates:
            if candidate.is_dir() or candidate.suffix in {".pyc", ".png", ".jpg", ".jpeg"}:
                continue
            if any(part in {".venv", "__pycache__", "generated"} for part in candidate.parts):
                continue
            try:
                text = candidate.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            lowered = text.lower()
            if any(token in lowered for token in forbidden):
                raise ConfigValidationError(f"forbidden Docker LiteLLM reference in {candidate}")


def validate_semantic_cache_policy(
    config: ConfigRoot,
    env: Mapping[str, str],
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    cache_params = config.litellm_settings.cache_params
    if not cache_params or cache_params.type != "qdrant-semantic":
        return warnings
    if env.get("QUIMERA_LITELLM_QDRANT_SEMANTIC_EXPERIMENTAL") != "1":
        warnings.append(
            ValidationWarning(
                rule_id="RC-09",
                message="qdrant-semantic is disabled by policy unless experimental flag is set",
            )
        )
    if cache_params.qdrant_semantic_cache_vector_size != CANONICAL_EMBED_DIM:
        reason = env.get("QUIMERA_LITELLM_EMBED_DIM_OVERRIDE_REASON", "").strip()
        if reason:
            warnings.append(
                ValidationWarning(
                    rule_id="RC-11",
                    message="semantic cache vector size differs from canonical dimension with documented override",
                )
            )
        else:
            warnings.append(
                ValidationWarning(
                    rule_id="RC-11",
                    message="semantic cache vector size differs from canonical dimension without override reason",
                )
            )
    return warnings


def validate_provider_safety(config: ConfigRoot, env: Mapping[str, str]) -> None:
    for model in config.model_list:
        params = model.litellm_params
        resolved_model = _env_value(params.model, env)
        if resolved_model.lower().startswith(REMOTE_PROVIDER_PREFIXES):
            raise ConfigValidationError("remote provider model is forbidden")
        if not resolved_model.lower().startswith(("ollama/", "ollama_chat/")):
            raise ConfigValidationError("model must resolve to local Ollama provider")
        resolved_api_base = _env_value(params.api_base, env)
        if not is_local_url(resolved_api_base, allowed_ports={11434}):
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
    except (ValidationError, ValueError) as exc:
        raise ConfigValidationError(str(exc)) from exc
    validate_host_only_runtime(config, env_map)
    validate_no_cache_collision(config)
    return config


def validate_config(
    path: Path,
    *,
    env: Mapping[str, str] | None = None,
    strict: bool = True,
) -> ConfigRoot:
    config = validate_litellm_config(path, env=env)
    if strict:
        warnings = validate_semantic_cache_policy(config, os.environ if env is None else env)
        hard_warnings = [warning for warning in warnings if warning.rule_id == "RC-11"]
        if hard_warnings:
            raise ConfigValidationError(hard_warnings[0].message)
    return config


def validate_config_report(
    path: Path,
    *,
    env: Mapping[str, str] | None = None,
) -> ValidationReport:
    env_map = os.environ if env is None else env
    config = validate_litellm_config(path, env=env_map)
    cache_params = config.litellm_settings.cache_params
    return ValidationReport(
        config_path=path,
        model_count=len(config.model_list),
        cache_backend=cache_params.type if cache_params else "disabled",
        warnings=tuple(validate_semantic_cache_policy(config, env_map)),
    )


async def smoke_test_qdrant(url: str, timeout_seconds: float = 2.0) -> bool:
    assert_host_local_qdrant_url(url)
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            for endpoint in ("/readyz", "/healthz"):
                result = await client.get(f"{url.rstrip('/')}{endpoint}")
                if result.status_code < 400:
                    return True
        return False
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
    try:
        report = validate_config_report(path)
    except ConfigValidationError as exc:
        sys.stderr.write(f"validation=failed\nmessage={exc}\n")
        return 1
    sys.stdout.write(f"path={report.config_path}\n")
    sys.stdout.write(f"models={report.model_count}\n")
    sys.stdout.write(f"cache_backend={report.cache_backend}\n")
    sys.stdout.write(f"warnings={len(report.warnings)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
