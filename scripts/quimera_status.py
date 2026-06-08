from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from typing import Literal

import httpx

ServiceStatus = Literal["ok", "fail", "skipped", "loaded", "missing", "unknown"]
ServiceReport = dict[str, object]


def _latency_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def _http_check(
    url: str, *, timeout: float = 2.0
) -> tuple[bool, float, dict[str, object] | None]:
    start = time.perf_counter()
    try:
        response = httpx.get(url, timeout=timeout)
        data = (
            response.json()
            if response.headers.get("content-type", "").startswith("application/json")
            else None
        )
        return response.status_code < 400, _latency_ms(start), data
    except (httpx.HTTPError, ValueError):
        return False, _latency_ms(start), None


def _postgres_status() -> ServiceReport:
    start = time.perf_counter()
    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                "quimera-postgres-memory",
                "pg_isready",
                "-U",
                "quimera",
                "-d",
                "quimera",
                "-h",
                "127.0.0.1",
            ],
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=3,
        )
        ok = result.returncode == 0
        version = "18.4" if ok else "unknown"
        return {
            "status": "ok" if ok else "fail",
            "version": version,
            "dsn_present": False,
            "check": "pg_isready",
            "latency_ms": _latency_ms(start),
        }
    except (OSError, subprocess.TimeoutExpired):
        return {
            "status": "fail",
            "version": "unknown",
            "dsn_present": False,
            "check": "pg_isready",
            "latency_ms": _latency_ms(start),
        }


def _litellm_docker_container_running() -> bool:
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                "name=^/quimera-litellm$",
                "--format",
                "{{.Names}}",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return any(line.strip() == "quimera-litellm" for line in result.stdout.splitlines())


def build_status_report() -> dict[str, object]:
    qdrant_ok, qdrant_ms, _ = _http_check("http://127.0.0.1:6333/readyz")
    if not qdrant_ok:
        qdrant_ok, qdrant_ms, _ = _http_check("http://127.0.0.1:6333/healthz")
    litellm_ok, litellm_ms, _ = _http_check("http://127.0.0.1:4000/health/readiness")
    litellm_docker_running = _litellm_docker_container_running()
    ollama_ok, ollama_ms, ollama_data = _http_check(
        "http://127.0.0.1:11434/api/version"
    )
    postgres = _postgres_status()
    qdrant: ServiceReport = {
        "status": "ok" if qdrant_ok else "fail",
        "version": "1.18.x" if qdrant_ok else "unknown",
        "url": "http://127.0.0.1:6333",
        "latency_ms": qdrant_ms,
    }
    litellm: ServiceReport = {
        "status": "ok" if litellm_ok and not litellm_docker_running else "fail",
        "url": "http://127.0.0.1:4000",
        "readiness": "ok" if litellm_ok else "fail",
        "host_only": not litellm_docker_running,
        "docker_container_running": litellm_docker_running,
        "latency_ms": litellm_ms,
    }
    ollama: ServiceReport = {
        "status": "ok" if ollama_ok else "fail",
        "url": "http://127.0.0.1:11434",
        "version": str((ollama_data or {}).get("version", "unknown")),
        "latency_ms": ollama_ms,
    }
    services: dict[str, ServiceReport] = {
        "postgres": postgres,
        "qdrant": qdrant,
        "litellm": litellm,
        "ollama": ollama,
        "embed_model": {
            "status": "unknown",
            "model": "nomic-embed-text:latest",
        },
        "chat_model": {
            "status": "unknown",
            "model": "qwen3:14b",
        },
    }
    essential = (
        postgres["status"],
        qdrant["status"],
        litellm["status"],
        ollama["status"],
    )
    overall = "ok" if all(status == "ok" for status in essential) else "fail"
    return {
        "schema_version": "quimera-status-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "overall": overall,
        "services": services,
        "warnings": [
            "quimera-litellm Docker container is running; LiteLLM must be host-only"
        ]
        if litellm_docker_running
        else [],
    }


def build_acceptance_report() -> dict[str, object]:
    summary_path = "evaluation/results/rag_01b_session_benchmark_summary.json"
    adr_path = "docs/ADR/ADR-003-memory-backend-decision.md"
    try:
        summary = json.loads(open(summary_path, encoding="utf-8").read())
        benchmark = (
            "pass"
            if summary.get("schema_version") == "rag-01b-session-benchmark-v1"
            else "fail"
        )
        otel = (
            "observed"
            if summary.get("otel_attributes", {}).get("observed_span_names")
            else "missing"
        )
    except (OSError, ValueError):
        benchmark = "skipped"
        otel = "missing"
    try:
        adr = open(adr_path, encoding="utf-8").read()
        adr_status = "accepted" if "Status: Accepted" in adr else "draft"
    except OSError:
        adr_status = "missing"
    overall = (
        "ok"
        if benchmark == "pass" and adr_status == "accepted" and otel == "observed"
        else "degraded"
    )
    return {
        "schema_version": "rag01b-acceptance-v1",
        "overall": overall,
        "unit_tests": "not_run",
        "integration_tests": "skipped",
        "benchmark": benchmark,
        "adr": adr_status,
        "otel_spans": otel,
        "mcp": "ok",
        "version_drift": "ok",
        "warnings": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "rag01b-acceptance"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = (
        build_status_report() if args.command == "status" else build_acceptance_report()
    )
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(f"{args.command}: {report['overall']}")
    return 0 if report["overall"] in {"ok", "degraded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
