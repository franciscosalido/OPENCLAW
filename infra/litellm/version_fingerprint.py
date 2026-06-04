from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit, urlunsplit

import httpx


CommandRunner = Callable[[list[str], float], tuple[int, str, str]]
HttpGetter = Callable[[str, float], tuple[int | None, dict[str, Any] | str]]

HTTP_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class Fingerprint:
    schema_version: str
    values: dict[str, Any]
    warnings: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "values": self.values,
            "warnings": self.warnings,
        }


def sanitize_dsn(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return "<redacted-dsn>"
    host = parsed.hostname or "unknown"
    port = f":{parsed.port}" if parsed.port else ""
    user = parsed.username or "user"
    return urlunsplit((parsed.scheme, f"{user}:***@{host}{port}", parsed.path, "", ""))


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _default_command_runner(command: list[str], timeout: float) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", exc.__class__.__name__
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _default_http_getter(url: str, timeout: float) -> tuple[int | None, dict[str, Any] | str]:
    try:
        result = httpx.get(url, timeout=timeout)
    except httpx.HTTPError as exc:
        return None, exc.__class__.__name__
    try:
        body: dict[str, Any] | str = result.json()
    except json.JSONDecodeError:
        body = result.text[:120]
    return result.status_code, body


def _safe_http_probe(
    name: str,
    url: str,
    http_getter: HttpGetter,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    status_code, body = http_getter(url, HTTP_TIMEOUT_SECONDS)
    if status_code is None or status_code >= 400:
        warnings.append({"component": name, "message": f"{name} unavailable"})
        return {"status": "warn", "status_code": status_code}
    if isinstance(body, dict):
        if "version" in body:
            return {"status": "ok", "status_code": status_code, "version": str(body["version"])}
        if "result" in body:
            return {"status": "ok", "status_code": status_code, "result_shape": "mapping"}
    return {"status": "ok", "status_code": status_code}


async def _postgres_versions(dsn: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    warnings: list[dict[str, str]] = []
    try:
        import asyncpg  # type: ignore[import-untyped]
    except ImportError:
        return {}, [{"component": "postgresql", "message": "asyncpg unavailable"}]
    try:
        conn = await asyncpg.connect(dsn, timeout=2)
        try:
            postgres = await conn.fetchval("SHOW server_version")
            timescale = await conn.fetchval(
                "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"
            )
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001 - sanitized diagnostic only
        return {}, [{"component": "postgresql", "message": exc.__class__.__name__}]
    return {"postgresql": postgres, "timescaledb": timescale}, warnings


def build_version_fingerprint(
    *,
    env: Mapping[str, str] | None = None,
    command_runner: CommandRunner | None = None,
    http_getter: HttpGetter | None = None,
    config_path: Path = Path("infra/litellm/litellm_config.yaml"),
    runtime_config_path: Path = Path("infra/litellm/generated/litellm_config.runtime.yaml"),
) -> Fingerprint:
    env_map = os.environ if env is None else env
    runner = command_runner or _default_command_runner
    getter = http_getter or _default_http_getter
    warnings: list[dict[str, str]] = []

    values: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "litellm": _package_version("litellm"),
        "pydantic": _package_version("pydantic"),
        "httpx": _package_version("httpx"),
        "qdrant_client": _package_version("qdrant-client"),
        "config_path": str(config_path),
        "runtime_config_path": str(runtime_config_path),
    }

    code, stdout, stderr = runner(["docker", "compose", "version", "--short"], 2.0)
    if code == 0:
        values["docker_compose"] = stdout
    else:
        values["docker_compose"] = None
        warnings.append({"component": "docker_compose", "message": stderr or "unavailable"})

    ollama_base = env_map.get("OLLAMA_BASE_URL", env_map.get("OLLAMA_API_BASE", "http://127.0.0.1:11434")).rstrip("/")
    qdrant_base = env_map.get("QDRANT_API_BASE", "http://127.0.0.1:6333").rstrip("/")
    litellm_base = env_map.get("LITELLM_BASE_URL", "http://127.0.0.1:4000").rstrip("/")

    values["ollama"] = _safe_http_probe("ollama", f"{ollama_base}/api/version", getter, warnings)
    values["qdrant_ready"] = _safe_http_probe("qdrant_ready", f"{qdrant_base}/readyz", getter, warnings)
    values["qdrant_collections"] = _safe_http_probe("qdrant_collections", f"{qdrant_base}/collections", getter, warnings)
    values["litellm_readiness"] = _safe_http_probe("litellm_readiness", f"{litellm_base}/health/readiness", getter, warnings)

    dsn = env_map.get("TEST_POSTGRES_DSN") or env_map.get("QUIMERA_POSTGRES_DSN")
    if dsn:
        values["postgres_dsn"] = sanitize_dsn(dsn)
        postgres_values, postgres_warnings = asyncio.run(_postgres_versions(dsn))
        values.update(postgres_values)
        warnings.extend(postgres_warnings)
    else:
        values["postgresql"] = None
        values["timescaledb"] = None
        warnings.append({"component": "postgresql", "message": "dsn unavailable"})

    return Fingerprint(
        schema_version="quimera-litellm-version-fingerprint-v1",
        values=values,
        warnings=warnings,
    )


def main() -> int:
    fingerprint = build_version_fingerprint()
    sys.stdout.write(json.dumps(fingerprint.to_dict(), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
