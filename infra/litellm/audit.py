from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import yaml

from infra.litellm.config_validator import (
    CANONICAL_LLM_CACHE_COLLECTION,
    CANONICAL_OLLAMA_BASE_URL,
    CANONICAL_QDRANT_BASE_URL,
    CANONICAL_RAG_CACHE_COLLECTION,
    CHAT_STREAM_TIMEOUT_SECONDS,
    CHAT_TIMEOUT_SECONDS,
    ConfigValidationError,
    EMBED_STREAM_TIMEOUT_SECONDS,
    EMBED_TIMEOUT_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    load_raw_config,
    validate_config_report,
    validate_litellm_config,
    validate_no_forbidden_docker_litellm_paths,
)
from infra.litellm.version_fingerprint import build_version_fingerprint


AUDIT_SCHEMA_VERSION = "quimera-litellm-audit-v1"
CONTRACT_IDS = tuple(f"RC-{index:02d}" for index in range(1, 25))
FORBIDDEN_VALUE_MARKERS = (
    "Authorization:",
    "Bearer ",
    "sk-",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "AZURE_API_KEY",
)


@dataclass(frozen=True)
class AuditReport:
    data: dict[str, Any]

    @property
    def status(self) -> str:
        return str(self.data["status"])

    def to_json(self) -> str:
        return json.dumps(self.data, indent=2, sort_keys=True) + "\n"

    def to_markdown(self) -> str:
        contracts = self.data["contracts"]
        lines = [
            "# LiteLLM Host Audit",
            "",
            f"- Schema: `{self.data['schema_version']}`",
            f"- Status: `{self.data['status']}`",
            f"- Config: `{self.data['config_path']}`",
            f"- Runtime config: `{self.data['runtime_config_path']}`",
            "",
            "## Contracts",
            "",
            "| Contract | Status | Message |",
            "|---|---|---|",
        ]
        for rule_id in CONTRACT_IDS:
            finding = contracts[rule_id]
            lines.append(f"| {rule_id} | {finding['status']} | {finding['message']} |")
        lines.extend(
            [
                "",
                "## Cache",
                "",
                f"- Backend source: `{self.data['cache']['backend_source']}`",
                f"- Backend runtime: `{self.data['cache']['backend_runtime']}`",
                f"- Collection: `{self.data['cache']['collection']}`",
                f"- Fallback active: `{self.data['cache']['fallback_active']}`",
                "",
                "## Versions",
                "",
            ]
        )
        for key, value in sorted(self.data["versions"].items()):
            lines.append(f"- `{key}`: `{value}`")
        if self.data["warnings"]:
            lines.extend(["", "## Warnings", ""])
            for warning in self.data["warnings"]:
                lines.append(f"- `{warning['component']}`: {warning['message']}")
        return "\n".join(lines) + "\n"


def _contract(status: str, message: str) -> dict[str, str]:
    return {"status": status, "message": message}


def _safe_status_from_contracts(contracts: Mapping[str, Mapping[str, str]]) -> str:
    statuses = {finding["status"] for finding in contracts.values()}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def _contains_forbidden_value(report: Mapping[str, Any]) -> bool:
    text = json.dumps(report, sort_keys=True)
    return any(marker in text for marker in FORBIDDEN_VALUE_MARKERS)


def _runtime_cache_backend(runtime_path: Path) -> tuple[str, bool]:
    if not runtime_path.exists():
        return "missing", False
    raw = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return "invalid", False
    settings = raw.get("litellm_settings") or {}
    cache_params = settings.get("cache_params") or {}
    policy = settings.get("cache_policy") or {}
    return str(cache_params.get("type", "disabled")), bool(policy.get("fallback_active", False))


def _script_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def build_litellm_audit(
    *,
    repo_root: Path = Path("."),
    config_path: Path = Path("infra/litellm/litellm_config.yaml"),
    runtime_config_path: Path = Path("infra/litellm/generated/litellm_config.runtime.yaml"),
    env: Mapping[str, str] | None = None,
) -> AuditReport:
    env_map = os.environ if env is None else env
    contracts: dict[str, dict[str, str]] = {rule_id: _contract("pass", "ok") for rule_id in CONTRACT_IDS}
    warnings: list[dict[str, str]] = []

    try:
        config = validate_litellm_config(config_path, env=env_map)
        validation_report = validate_config_report(config_path, env=env_map)
        warnings.extend({"component": warning.rule_id, "message": warning.message} for warning in validation_report.warnings)
    except ConfigValidationError as exc:
        config = None
        contracts["RC-01"] = _contract("fail", str(exc))

    raw = load_raw_config(config_path)
    settings = raw.get("litellm_settings", {})
    general = raw.get("general_settings", {})
    cache_params = settings.get("cache_params", {})
    model_list = raw.get("model_list", [])
    aliases = {item.get("model_name"): item for item in model_list if isinstance(item, dict)}

    if not {"local_chat", "local_think", "local_rag", "local_json", "quimera_embed", "local_embed"} <= set(aliases):
        contracts["RC-02"] = _contract("fail", "required legacy aliases missing")
    if cache_params.get("qdrant_collection_name") != CANONICAL_LLM_CACHE_COLLECTION:
        contracts["RC-03"] = _contract("fail", "LLM cache collection is not canonical")
    if cache_params.get("qdrant_collection_name") == CANONICAL_RAG_CACHE_COLLECTION:
        contracts["RC-04"] = _contract("fail", "LLM cache collides with RAG cache")
    if not 0.0 < float(cache_params.get("similarity_threshold", 0.0)) <= 1.0:
        contracts["RC-05"] = _contract("fail", "similarity threshold must be in (0, 1]")

    for alias in ("local_chat", "local_think", "local_rag", "qwen3-local", "qwen3:14b"):
        if alias in aliases:
            params = aliases[alias]["litellm_params"]
            if params.get("timeout") != CHAT_TIMEOUT_SECONDS or params.get("stream_timeout") != CHAT_STREAM_TIMEOUT_SECONDS:
                contracts["RC-06"] = _contract("fail", "chat timeout policy mismatch")
    for alias in ("nomic-embed-text", "quimera_embed", "local_embed"):
        if alias in aliases:
            params = aliases[alias]["litellm_params"]
            if params.get("timeout") != EMBED_TIMEOUT_SECONDS or params.get("stream_timeout") != EMBED_STREAM_TIMEOUT_SECONDS:
                contracts["RC-07"] = _contract("fail", "embedding timeout policy mismatch")

    if any((item.get("litellm_params", {}).get("max_retries", 99) > 2) for item in model_list):
        contracts["RC-08"] = _contract("fail", "max_retries exceeds local policy")
    if cache_params.get("type") == "qdrant-semantic" and env_map.get("QUIMERA_LITELLM_QDRANT_SEMANTIC_EXPERIMENTAL") != "1":
        contracts["RC-09"] = _contract("warn", "qdrant-semantic source will render to fallback unless experimental flag is set")
    if cache_params.get("qdrant_semantic_cache_embedding_model") not in {"nomic-embed-text", "quimera_embed"}:
        contracts["RC-10"] = _contract("fail", "semantic cache embedding model must be local")
    if int(cache_params.get("qdrant_semantic_cache_vector_size", 0)) != 768:
        contracts["RC-11"] = _contract("warn", "semantic cache vector size differs from canonical 768")
    if settings.get("request_timeout") != REQUEST_TIMEOUT_SECONDS:
        contracts["RC-12"] = _contract("fail", "request_timeout must be 165")
    if any(item.get("litellm_params", {}).get("api_base") not in {"os.environ/OLLAMA_BASE_URL", CANONICAL_OLLAMA_BASE_URL, "http://localhost:11434"} for item in model_list):
        contracts["RC-13"] = _contract("fail", "all models must use local OLLAMA_BASE_URL or loopback URL")
    if any(not str(item.get("litellm_params", {}).get("model", "")).startswith(("os.environ/", "ollama/", "ollama_chat/")) for item in model_list):
        contracts["RC-14"] = _contract("fail", "all models must use local Ollama provider")

    if settings.get("json_logs") is not True or settings.get("set_verbose") is not False:
        contracts["RC-15"] = _contract("fail", "logging settings are not safe")
    if settings.get("turn_off_message_logging") is not True or settings.get("redact_user_api_key_info") is not True:
        contracts["RC-15"] = _contract("fail", "message logging or key redaction policy mismatch")
    if general.get("master_key") != "os.environ/LITELLM_MASTER_KEY":
        contracts["RC-16"] = _contract("fail", "master_key must be environment reference")
    if any(item.get("litellm_params", {}).get("stream_timeout", 0) > item.get("litellm_params", {}).get("timeout", 0) for item in model_list):
        contracts["RC-17"] = _contract("fail", "stream_timeout exceeds timeout")

    start_script = _script_text(repo_root / "infra/litellm/start_litellm.sh")
    quimera_script = _script_text(repo_root / "scripts/start_quimera.sh")
    if "/health/readiness" not in start_script or "/health/liveliness" in start_script:
        contracts["RC-18"] = _contract("fail", "startup must use readiness probe only")
    for token in ("LITELLM_MODE=PRODUCTION", "LITELLM_LOG=ERROR", "--num_workers 1", "--host", "127.0.0.1", "--port", "4000"):
        if token not in start_script:
            contracts["RC-19"] = _contract("fail", f"start_litellm missing {token}")
    if "pkill" in quimera_script or "killall" in quimera_script:
        contracts["RC-20"] = _contract("fail", "stop lifecycle must not use pkill or killall")
    if not (repo_root / "infra/litellm/audit.py").exists():
        contracts["RC-21"] = _contract("fail", "litellm audit module missing")
    if any(token in quimera_script for token in ("litellm-audit)", "litellm-benchmark)")):
        contracts["RC-21"] = _contract("fail", "start_quimera must not expose LiteLLM audit subcommands")

    fingerprint = build_version_fingerprint(env=env_map, config_path=config_path, runtime_config_path=runtime_config_path)
    warnings.extend(fingerprint.warnings)
    runtime_backend, fallback_active = _runtime_cache_backend(runtime_config_path)

    if not fingerprint.values:
        contracts["RC-22"] = _contract("fail", "version fingerprint unavailable")
    if not (repo_root / "infra/litellm/overhead_benchmark.py").exists():
        contracts["RC-23"] = _contract("fail", "overhead benchmark missing")

    try:
        validate_no_forbidden_docker_litellm_paths(repo_root)
    except ConfigValidationError as exc:
        contracts["RC-01"] = _contract("fail", str(exc))

    data: dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "pass",
        "config_path": str(config_path),
        "runtime_config_path": str(runtime_config_path),
        "contracts": contracts,
        "versions": fingerprint.values,
        "endpoints": {
            "litellm_readiness": fingerprint.values.get("litellm_readiness"),
            "ollama_version": fingerprint.values.get("ollama"),
            "qdrant_ready": fingerprint.values.get("qdrant_ready"),
            "qdrant_collections": fingerprint.values.get("qdrant_collections"),
        },
        "cache": {
            "backend_source": cache_params.get("type", "disabled"),
            "backend_runtime": runtime_backend,
            "collection": cache_params.get("qdrant_collection_name"),
            "rag_cache_collision": cache_params.get("qdrant_collection_name") == CANONICAL_RAG_CACHE_COLLECTION,
            "qdrant_semantic_experimental": env_map.get("QUIMERA_LITELLM_QDRANT_SEMANTIC_EXPERIMENTAL") == "1",
            "fallback_active": fallback_active,
        },
        "timeouts": {
            "request_timeout": settings.get("request_timeout"),
            "chat": {"timeout": CHAT_TIMEOUT_SECONDS, "stream_timeout": CHAT_STREAM_TIMEOUT_SECONDS},
            "embedding": {"timeout": EMBED_TIMEOUT_SECONDS, "stream_timeout": EMBED_STREAM_TIMEOUT_SECONDS},
        },
        "security": {
            "host_only": True,
            "no_docker_litellm": contracts["RC-01"]["status"] != "fail",
            "no_literal_credentials": general.get("master_key") == "os.environ/LITELLM_MASTER_KEY",
            "message_logging_disabled": settings.get("turn_off_message_logging") is True,
        },
        "warnings": warnings,
        "safe_event_shape": {
            "event.name": "litellm.audit",
            "service.name": "quimera_litellm_host",
            "quimera.component": "litellm",
            "quimera.stage": "audit",
            "status": "pending",
            "duration_ms": None,
            "error.type": None,
            "error.message_sanitized": None,
            "endpoint.kind": "local",
        },
    }
    if _contains_forbidden_value(data):
        contracts["RC-24"] = _contract("fail", "audit report contains forbidden sensitive marker")
    data["status"] = _safe_status_from_contracts(contracts)
    data["safe_event_shape"]["status"] = data["status"]
    return AuditReport(data=data)


def write_audit_report(report: AuditReport, *, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(report.to_json(), encoding="utf-8")
    markdown_path.write_text(report.to_markdown(), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a safe local LiteLLM host audit report.")
    parser.add_argument("--json", dest="json_path", default=".runtime/reports/litellm_audit.json")
    parser.add_argument("--markdown", dest="markdown_path", default=".runtime/reports/litellm_audit.md")
    parser.add_argument("--config", default="infra/litellm/litellm_config.yaml")
    parser.add_argument("--runtime-config", default="infra/litellm/generated/litellm_config.runtime.yaml")
    args = parser.parse_args(argv)
    report = build_litellm_audit(
        config_path=Path(args.config),
        runtime_config_path=Path(args.runtime_config),
    )
    write_audit_report(report, json_path=Path(args.json_path), markdown_path=Path(args.markdown_path))
    sys.stdout.write(f"status={report.status}\n")
    sys.stdout.write(f"json={args.json_path}\n")
    sys.stdout.write(f"markdown={args.markdown_path}\n")
    return 0 if report.status in {"pass", "warn"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
