#!/usr/bin/env python
"""Agent-0 local readiness checks."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import httpx
from qdrant_client import QdrantClient

from backend.agent0.golden_questions import load_all_golden_questions
from backend.gateway.config import REQUIRED_ALIASES, load_gateway_config
from backend.gateway.health import REQUIRED_CHAT_MODEL, REQUIRED_EMBED_MODEL
from backend.gateway.routing_policy import load_routing_policy
from backend.ingestion.bootstrap import manifest_path_for_corpus
from backend.ingestion.commit_store import DUAL_CORPUS_COLLECTIONS
from backend.ingestion.manifest import load_manifest
from backend.ingestion.report import assert_report_is_sanitized


REPO_ROOT = Path(__file__).resolve().parents[1]
RAG_CONFIG_PATH = REPO_ROOT / "config" / "rag_config.yaml"
LITELLM_CONFIG_PATH = REPO_ROOT / "config" / "litellm_config.yaml"
READINESS_FORBIDDEN_KEYS = frozenset(
    {
        "query",
        "question",
        "text",
        "answer",
        "prompt",
        "chunk",
        "chunks",
        "vector",
        "vectors",
        "embedding",
        "embeddings",
        "payload",
        "headers",
        "api_key",
        "authorization",
        "secret",
        "raw_exception",
        "traceback",
    }
)


class CollectionClient(Protocol):
    def collection_exists(self, collection_name: str) -> bool:
        """Return whether a Qdrant collection exists."""
        ...


@dataclass(frozen=True)
class ReadinessCheck:
    """One sanitized readiness check result."""

    name: str
    passed: bool
    reason_code: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "reason_code": self.reason_code,
        }


def run_readiness(
    *,
    qdrant_client_factory: Callable[[], CollectionClient] | None = None,
    http_get: Callable[..., httpx.Response] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run idempotent Agent-0 readiness checks without mutating Qdrant."""

    checks: list[ReadinessCheck] = []
    qdrant_client = (qdrant_client_factory or _default_qdrant_client_factory)()
    try:
        for collection in DUAL_CORPUS_COLLECTIONS.values():
            checks.append(
                _check_bool(
                    f"qdrant_collection_{collection}",
                    qdrant_client.collection_exists(collection),
                    "collection_exists",
                    "collection_missing",
                )
            )
    except Exception:
        checks.append(ReadinessCheck("qdrant_reachable", False, "qdrant_unreachable"))

    checks.extend(_check_gateway_config())
    checks.extend(_check_remote_disabled())
    checks.extend(_check_manifests())
    checks.extend(_check_golden_questions())
    checks.extend(_check_live_services(http_get or httpx.get, env=env))

    passed = sum(1 for check in checks if check.passed)
    report: dict[str, Any] = {
        "run_id": uuid4().hex,
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "total_checks": len(checks),
        "passed": passed,
        "failed": len(checks) - passed,
        "checks": [check.to_dict() for check in checks],
    }
    assert_readiness_report_sanitized(report)
    return report


def assert_readiness_report_sanitized(report: Mapping[str, Any]) -> None:
    assert_report_is_sanitized(dict(report))
    hits = _forbidden_key_hits(report)
    if hits:
        raise ValueError(f"readiness report contains forbidden keys: {hits}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Agent-0 local readiness.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_readiness()
    if args.json:
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(
            f"Agent-0 readiness: {report['passed']}/{report['total_checks']} passed\n"
        )
    return 0 if report["failed"] == 0 else 1


def _default_qdrant_client_factory() -> CollectionClient:
    return QdrantClient(host="localhost", port=6333)


def _check_gateway_config() -> list[ReadinessCheck]:
    try:
        config = load_gateway_config(LITELLM_CONFIG_PATH)
        missing = REQUIRED_ALIASES - config.alias_names
        return [
            _check_bool(
                "gateway_aliases",
                not missing,
                "aliases_present",
                "aliases_missing",
            )
        ]
    except Exception:
        return [ReadinessCheck("gateway_aliases", False, "config_invalid")]


def _check_remote_disabled() -> list[ReadinessCheck]:
    try:
        policy = load_routing_policy(RAG_CONFIG_PATH)
        return [
            _check_bool(
                "remote_routing_disabled",
                not policy.remote_enabled,
                "remote_disabled",
                "remote_enabled",
            )
        ]
    except Exception:
        return [ReadinessCheck("remote_routing_disabled", False, "config_invalid")]


def _check_manifests() -> list[ReadinessCheck]:
    checks: list[ReadinessCheck] = []
    for corpus in ("internal", "financial"):
        try:
            manifest = load_manifest(manifest_path_for_corpus(corpus))
            checks.append(
                _check_bool(
                    f"{corpus}_manifest",
                    bool(manifest.documents),
                    "manifest_loaded",
                    "manifest_empty",
                )
            )
        except Exception:
            checks.append(ReadinessCheck(f"{corpus}_manifest", False, "manifest_invalid"))
    return checks


def _check_golden_questions() -> list[ReadinessCheck]:
    try:
        questions = load_all_golden_questions()
        return [_check_bool("golden_questions", len(questions) == 6, "loaded", "invalid")]
    except Exception:
        return [ReadinessCheck("golden_questions", False, "invalid")]


def _check_live_services(
    http_get: Callable[..., httpx.Response],
    *,
    env: Mapping[str, str] | None,
) -> list[ReadinessCheck]:
    del env
    return [
        _check_litellm(http_get),
        _check_ollama_models(http_get),
    ]


def _check_litellm(http_get: Callable[..., httpx.Response]) -> ReadinessCheck:
    try:
        response = http_get("http://127.0.0.1:4000/v1/models", timeout=3.0)
        return _check_bool(
            "litellm_local_reachable",
            response.status_code < 500,
            "reachable",
            "unreachable",
        )
    except Exception:
        return ReadinessCheck("litellm_local_reachable", False, "unreachable")


def _check_ollama_models(http_get: Callable[..., httpx.Response]) -> ReadinessCheck:
    try:
        response = http_get("http://localhost:11434/api/tags", timeout=3.0)
        raw = response.json()
        if not isinstance(raw, Mapping):
            return ReadinessCheck("ollama_models", False, "invalid_response")
        models = raw.get("models")
        if not isinstance(models, list):
            return ReadinessCheck("ollama_models", False, "models_missing")
        names = {str(model.get("name", "")) for model in models if isinstance(model, Mapping)}
        base_names = {name.split(":")[0] for name in names}
        chat_ok = REQUIRED_CHAT_MODEL in names or REQUIRED_CHAT_MODEL.split(":")[0] in base_names
        embed_ok = REQUIRED_EMBED_MODEL in names or REQUIRED_EMBED_MODEL.split(":")[0] in base_names
        return _check_bool("ollama_models", chat_ok and embed_ok, "models_present", "models_missing")
    except Exception:
        return ReadinessCheck("ollama_models", False, "unreachable")


def _check_bool(name: str, value: bool, ok: str, fail: str) -> ReadinessCheck:
    return ReadinessCheck(name=name, passed=value, reason_code=ok if value else fail)


def _forbidden_key_hits(value: object, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            next_path = f"{path}.{key_text}"
            if key_text in READINESS_FORBIDDEN_KEYS:
                hits.append(next_path)
            hits.extend(_forbidden_key_hits(nested, next_path))
    elif isinstance(value, list | tuple):
        for index, nested in enumerate(value):
            hits.extend(_forbidden_key_hits(nested, f"{path}[{index}]"))
    return hits


if __name__ == "__main__":
    raise SystemExit(main())
