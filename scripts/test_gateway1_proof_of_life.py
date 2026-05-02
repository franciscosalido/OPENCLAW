#!/usr/bin/env python
"""Gateway-1 operational proof-of-life smoke.

The smoke is opt-in, local-only and writes a sanitized structured summary.
It never stores prompt text, answer text, chunks, vectors, payloads or secrets.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from backend.gateway.observability_contract import PROHIBITED_SIGNAL_KEYS
from backend.gateway.routing_policy import (
    FallbackReason,
    RemoteEscalationPolicy,
)
from scripts import run_local_agent


GUARD_ENV = "RUN_GATEWAY1_PROOF_OF_LIFE"
DEFAULT_OUTPUT_DIR = Path("reports/gateway1_smoke")
CRITERIA_MANIFEST_REF = "docs/sprints/GATEWAY1_DONE_CRITERIA.md"
GATEWAY_SPRINT = "Gateway-1"
DEFAULT_LITELLM_BASE_URL = "http://127.0.0.1:4000/v1"
DEFAULT_QDRANT_URL = "http://127.0.0.1:6333"
DEFAULT_OLLAMA_API_BASE = "http://127.0.0.1:11434"
PROBE_TIMEOUT_SECONDS = 5.0
REQUIRED_ALIASES = (
    "local_chat",
    "local_rag",
    "local_json",
    "local_think",
    "quimera_embed",
    "local_embed",
)
MANDATORY_CRITERIA = {
    "G1-01": True,
    "G1-02": True,
    "G1-03": True,
    "G1-04": True,
    "G1-05": True,
    "G1-06": True,
    "G1-07": True,
    "G1-08": True,
    "G1-09": True,
    "G1-10": True,
    "G1-11": True,
}
FAKE_SENSITIVE_VALUES = (
    "FAKE_API_KEY_SHOULD_NOT_APPEAR",
    "FAKE_AUTH_HEADER_SHOULD_NOT_APPEAR",
    "FAKE_PROMPT_SHOULD_NOT_APPEAR",
    "FAKE_CHUNK_SHOULD_NOT_APPEAR",
    "FAKE_VECTOR_SHOULD_NOT_APPEAR",
)


class FakeQdrantUnavailableError(RuntimeError):
    """Synthetic Qdrant-like exception used for deterministic degradation."""


@dataclass(frozen=True)
class ProbeResult:
    """Safe read-only service probe result."""

    service: str
    ok: bool
    latency_ms: float
    error_category: str | None = None
    missing_aliases: tuple[str, ...] = ()

    def to_json_dict(self) -> dict[str, object]:
        """Return explicit allowlisted probe metadata."""
        data: dict[str, object] = {
            "service": self.service,
            "ok": self.ok,
            "latency_ms": self.latency_ms,
        }
        if self.error_category is not None:
            data["error_category"] = self.error_category
        if self.missing_aliases:
            data["missing_aliases"] = list(self.missing_aliases)
        return data


@dataclass(frozen=True)
class RunnerSmokeResult:
    """Safe Agent-0 smoke result without answer text."""

    name: str
    ok: bool
    route: str | None
    alias: str | None
    used_rag: bool | None
    latency_ms: float
    decision_id: str | None
    estimated_remote_tokens_avoided: int | float | None
    answer_length_chars: int | None
    error_category: str | None = None
    fallback_applied: bool | None = None
    fallback_reason: str | None = None
    model_call_attempted: bool | None = None

    def to_json_dict(self) -> dict[str, object]:
        """Return explicit allowlisted runner smoke metadata."""
        data: dict[str, object] = {
            "name": self.name,
            "ok": self.ok,
            "latency_ms": self.latency_ms,
        }
        optional: dict[str, object | None] = {
            "route": self.route,
            "alias": self.alias,
            "used_rag": self.used_rag,
            "decision_id": self.decision_id,
            "estimated_remote_tokens_avoided": (
                self.estimated_remote_tokens_avoided
            ),
            "answer_length_chars": self.answer_length_chars,
            "error_category": self.error_category,
            "fallback_applied": self.fallback_applied,
            "fallback_reason": self.fallback_reason,
            "model_call_attempted": self.model_call_attempted,
        }
        for key, value in optional.items():
            if value is not None:
                data[key] = value
        return data


@dataclass(frozen=True)
class GatewayProofOfLifeSummary:
    """Sanitized proof-of-life report."""

    run_id: str
    timestamp_utc: str
    gateway_sprint: str
    criteria_manifest_ref: str
    service_probes: Mapping[str, ProbeResult]
    runner_tests: Mapping[str, RunnerSmokeResult]
    passed: tuple[str, ...]
    failed: tuple[str, ...]
    skipped: tuple[str, ...]
    criteria_met: Mapping[str, bool]
    overall_passed: bool

    def to_json_dict(self) -> dict[str, object]:
        """Return explicit allowlisted summary metadata."""
        return {
            "run_id": self.run_id,
            "timestamp_utc": self.timestamp_utc,
            "gateway_sprint": self.gateway_sprint,
            "criteria_manifest_ref": self.criteria_manifest_ref,
            "service_probes": {
                name: probe.to_json_dict()
                for name, probe in sorted(self.service_probes.items())
            },
            "runner_tests": {
                name: result.to_json_dict()
                for name, result in sorted(self.runner_tests.items())
            },
            "passed": list(self.passed),
            "failed": list(self.failed),
            "skipped": list(self.skipped),
            "criteria_met": dict(sorted(self.criteria_met.items())),
            "overall_passed": self.overall_passed,
        }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse proof-of-life smoke arguments."""
    parser = argparse.ArgumentParser(
        description="Run the opt-in Gateway-1 proof-of-life smoke.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for the sanitized summary JSON.",
    )
    return parser.parse_args(argv)


def require_guard_enabled() -> bool:
    """Return whether the live proof-of-life guard is enabled."""
    return os.environ.get(GUARD_ENV) == "1"


async def run_proof_of_life(
    *,
    output_dir: Path | str,
) -> tuple[GatewayProofOfLifeSummary, Path | None]:
    """Run the Gateway-1 proof-of-life smoke and write a summary if possible."""
    run_id = uuid4().hex[:12]
    criteria_met: dict[str, bool] = {criterion: False for criterion in MANDATORY_CRITERIA}
    skipped: set[str] = set()
    probes: dict[str, ProbeResult] = {}
    runner_tests: dict[str, RunnerSmokeResult] = {}

    dry_run = await run_dry_run_smoke()
    runner_tests["dry_run"] = dry_run
    criteria_met["G1-01"] = dry_run.ok

    urls = GatewayUrls.from_env()
    local_guard_ok = urls.are_local_only()
    criteria_met["G1-02"] = local_guard_ok

    if local_guard_ok:
        probes["ollama"] = probe_ollama(urls.ollama_api_base)
        probes["qdrant"] = probe_qdrant(urls.qdrant_url)
        probes["litellm"] = probe_litellm(
            urls.litellm_base_url,
            api_key=os.environ.get("QUIMERA_LLM_API_KEY"),
        )
        criteria_met["G1-03"] = probes["ollama"].ok
        criteria_met["G1-04"] = probes["qdrant"].ok
        criteria_met["G1-05"] = probes["litellm"].ok
    else:
        skipped.update({"G1-03", "G1-04", "G1-05", "G1-06", "G1-07"})

    live_ready = all(
        criteria_met[criterion] for criterion in ("G1-02", "G1-03", "G1-05")
    )
    if live_ready:
        local_chat = await run_local_chat_smoke()
        runner_tests["local_chat"] = local_chat
        criteria_met["G1-06"] = local_chat.ok
    elif "G1-06" not in skipped:
        skipped.add("G1-06")

    rag_ready = all(
        criteria_met[criterion]
        for criterion in ("G1-02", "G1-03", "G1-04", "G1-05")
    )
    if rag_ready:
        rag_smoke = await run_rag_smoke()
        runner_tests["rag"] = rag_smoke
        criteria_met["G1-07"] = rag_smoke.ok
    elif "G1-07" not in skipped:
        skipped.add("G1-07")

    forced_degradation = await run_forced_qdrant_degradation_smoke()
    runner_tests["forced_qdrant_degradation"] = forced_degradation
    criteria_met["G1-08"] = forced_degradation.ok

    policy_block = await run_policy_block_smoke()
    runner_tests["policy_block"] = policy_block
    criteria_met["G1-09"] = policy_block.ok

    try:
        provisional = _build_summary(
            run_id=run_id,
            probes=probes,
            runner_tests=runner_tests,
            criteria_met=criteria_met,
            skipped=skipped,
        )
        assert_sanitized(provisional.to_json_dict())
        criteria_met["G1-10"] = True
    except ValueError:
        criteria_met["G1-10"] = False

    summary = _build_summary(
        run_id=run_id,
        probes=probes,
        runner_tests=runner_tests,
        criteria_met=criteria_met,
        skipped=skipped,
    )

    summary_path: Path | None = None
    try:
        summary_path = write_summary(output_dir, summary)
        criteria_met["G1-11"] = True
    except OSError:
        criteria_met["G1-11"] = False
    summary = _build_summary(
        run_id=run_id,
        probes=probes,
        runner_tests=runner_tests,
        criteria_met=criteria_met,
        skipped=skipped,
    )
    if summary_path is not None:
        write_summary(output_dir, summary, path=summary_path)
    return summary, summary_path


@dataclass(frozen=True)
class GatewayUrls:
    """Local service URLs used by Gateway-1 smoke."""

    litellm_base_url: str
    qdrant_url: str
    ollama_api_base: str

    @classmethod
    def from_env(cls) -> GatewayUrls:
        """Build URLs from environment with local defaults."""
        return cls(
            litellm_base_url=os.environ.get(
                "QUIMERA_LLM_BASE_URL",
                DEFAULT_LITELLM_BASE_URL,
            ),
            qdrant_url=os.environ.get("QDRANT_URL", DEFAULT_QDRANT_URL),
            ollama_api_base=os.environ.get(
                "OLLAMA_API_BASE",
                DEFAULT_OLLAMA_API_BASE,
            ),
        )

    def are_local_only(self) -> bool:
        """Return true only when all service URLs are local."""
        return all(
            is_local_url(url)
            for url in (self.litellm_base_url, self.qdrant_url, self.ollama_api_base)
        )


def is_local_url(url: str) -> bool:
    """Return whether ``url`` is an allowed local HTTP URL."""
    return url.startswith("http://127.0.0.1:") or url.startswith("http://localhost:")


def probe_ollama(base_url: str) -> ProbeResult:
    """Probe Ollama tags endpoint without mutating state."""
    return _http_probe(
        service="ollama",
        url=f"{base_url.rstrip('/')}/api/tags",
        expected_json_mapping=True,
    )


def probe_qdrant(base_url: str) -> ProbeResult:
    """Probe Qdrant health endpoint without mutating state."""
    return _http_probe(
        service="qdrant",
        url=f"{base_url.rstrip('/')}/healthz",
        expected_json_mapping=False,
    )


def probe_litellm(base_url: str, *, api_key: str | None) -> ProbeResult:
    """Probe LiteLLM models endpoint and required aliases."""
    if not api_key:
        return ProbeResult(
            service="litellm",
            ok=False,
            latency_ms=0.0,
            error_category="authentication",
        )
    start = time.perf_counter()
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        aliases = _extract_model_aliases(payload)
        missing = tuple(alias for alias in REQUIRED_ALIASES if alias not in aliases)
        return ProbeResult(
            service="litellm",
            ok=not missing,
            latency_ms=_elapsed_ms(start),
            error_category="alias_missing" if missing else None,
            missing_aliases=missing,
        )
    except Exception as exc:
        return ProbeResult(
            service="litellm",
            ok=False,
            latency_ms=_elapsed_ms(start),
            error_category=categorize_probe_exception(exc),
        )


def _http_probe(
    *,
    service: str,
    url: str,
    expected_json_mapping: bool,
) -> ProbeResult:
    start = time.perf_counter()
    try:
        response = httpx.get(url, timeout=PROBE_TIMEOUT_SECONDS)
        response.raise_for_status()
        if expected_json_mapping and not isinstance(response.json(), Mapping):
            return ProbeResult(
                service=service,
                ok=False,
                latency_ms=_elapsed_ms(start),
                error_category="invalid_response",
            )
        return ProbeResult(service=service, ok=True, latency_ms=_elapsed_ms(start))
    except Exception as exc:
        return ProbeResult(
            service=service,
            ok=False,
            latency_ms=_elapsed_ms(start),
            error_category=categorize_probe_exception(exc),
        )


def categorize_probe_exception(exc: Exception) -> str:
    """Map probe exceptions to safe categories without raw messages."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        return "connection"
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in {401, 403}:
            return "authentication"
        return "invalid_response"
    if isinstance(exc, httpx.RequestError):
        return "connection"
    if isinstance(exc, (json.JSONDecodeError, ValueError, TypeError)):
        return "invalid_response"
    return "unknown"


async def run_dry_run_smoke() -> RunnerSmokeResult:
    """Run Agent-0 dry-run without live services."""
    result = await run_local_agent.run_agent(
        question="Pergunta sintetica de dry-run.",
        dry_run=True,
    )
    ok = (
        result.alias == run_local_agent.LOCAL_CHAT_ALIAS
        and result.latency_ms == 0.0
        and result.estimated_remote_tokens_avoided >= 0
    )
    return _runner_result("dry_run", result, ok=ok)


async def run_local_chat_smoke() -> RunnerSmokeResult:
    """Run one live Agent-0 default local_chat question."""
    result = await run_local_agent.run_agent(
        question="Explique de forma sintetica o que e diversificacao.",
        max_tokens=128,
        temperature=0.0,
    )
    ok = (
        result.route == "local"
        and result.alias == run_local_agent.LOCAL_CHAT_ALIAS
        and not result.used_rag
        and result.error_category is None
        and result.estimated_remote_tokens_avoided >= 0
    )
    return _runner_result("local_chat", result, ok=ok)


async def run_rag_smoke() -> RunnerSmokeResult:
    """Run live Agent-0 RAG and accept success or explicit local fallback."""
    result = await run_local_agent.run_agent(
        question="Use contexto sintetico para explicar uma politica de risco.",
        use_rag=True,
        max_tokens=160,
        temperature=0.0,
    )
    rag_success = (
        result.alias == run_local_agent.LOCAL_RAG_ALIAS
        and result.used_rag
        and result.error_category is None
        and not result.fallback_applied
    )
    explicit_fallback = (
        result.fallback_applied is True
        and result.fallback_reason is not None
        and result.fallback_reason.value in {reason.value for reason in FallbackReason}
        and result.alias == run_local_agent.LOCAL_CHAT_ALIAS
        and not result.used_rag
    )
    return _runner_result("rag", result, ok=rag_success or explicit_fallback)


async def run_forced_qdrant_degradation_smoke() -> RunnerSmokeResult:
    """Inject a Qdrant-like failure and verify one safe fallback."""
    rag_calls = 0
    chat_calls = 0

    async def rag_call(
        question: str,
        *,
        max_tokens: int | None,
        temperature: float | None,
    ) -> str:
        nonlocal rag_calls
        del question, max_tokens, temperature
        rag_calls += 1
        raise FakeQdrantUnavailableError("synthetic local unavailable")

    async def chat_call(
        question: str,
        *,
        alias: str,
        max_tokens: int | None,
        temperature: float | None,
        response_format: Mapping[str, object] | None,
    ) -> str:
        nonlocal chat_calls
        del question, alias, max_tokens, temperature, response_format
        chat_calls += 1
        return "Resposta sintetica de fallback local."

    result = await run_local_agent.run_agent(
        question="Pergunta sintetica para degradacao.",
        use_rag=True,
        chat_call=chat_call,
        rag_call=rag_call,
    )
    ok = (
        rag_calls == 1
        and chat_calls == 1
        and result.fallback_applied is True
        and result.fallback_reason
        in {FallbackReason.QDRANT_UNAVAILABLE, FallbackReason.RAG_UNAVAILABLE}
        and result.alias == run_local_agent.LOCAL_CHAT_ALIAS
        and not result.used_rag
        and result.error_category is None
    )
    return _runner_result("forced_qdrant_degradation", result, ok=ok)


async def run_policy_block_smoke() -> RunnerSmokeResult:
    """Verify budget policy block happens before model calls."""
    model_call_attempted = False

    async def chat_call(
        question: str,
        *,
        alias: str,
        max_tokens: int | None,
        temperature: float | None,
        response_format: Mapping[str, object] | None,
    ) -> str:
        nonlocal model_call_attempted
        del question, alias, max_tokens, temperature, response_format
        model_call_attempted = True
        return "should not run"

    result = await run_local_agent.run_agent(
        question="Pergunta sintetica bloqueada por orcamento.",
        chat_call=chat_call,
        policy_loader=lambda: RemoteEscalationPolicy(
            remote_enabled=False,
            per_request_token_limit=1,
        ),
    )
    ok = (
        result.route == "blocked"
        and result.error_category == "blocked"
        and result.latency_ms == 0.0
        and not result.fallback_applied
        and not model_call_attempted
    )
    return _runner_result(
        "policy_block",
        result,
        ok=ok,
        model_call_attempted=model_call_attempted,
    )


def assert_sanitized(value: object) -> None:
    """Recursively reject prohibited keys and known fake sensitive values."""
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key).lower()
            if key_text in PROHIBITED_SIGNAL_KEYS:
                raise ValueError(f"prohibited key in smoke output: {key_text}")
            assert_sanitized(nested)
        return
    if isinstance(value, list | tuple):
        for item in value:
            assert_sanitized(item)
        return
    if isinstance(value, str):
        for marker in FAKE_SENSITIVE_VALUES:
            if marker in value:
                raise ValueError("fake sensitive marker leaked into smoke output")


def write_summary(
    output_dir: Path | str,
    summary: GatewayProofOfLifeSummary,
    *,
    path: Path | None = None,
) -> Path:
    """Write one sanitized proof-of-life JSON summary."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = path or out_dir / f"gateway1_proof_of_life_{summary.run_id}.json"
    payload = summary.to_json_dict()
    assert_sanitized(payload)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


async def main_async(argv: Sequence[str] | None = None) -> int:
    """Async proof-of-life CLI entrypoint."""
    args = parse_args(argv)
    if not require_guard_enabled():
        sys.stdout.write(
            "Gateway-1 proof-of-life is opt-in. "
            "Set RUN_GATEWAY1_PROOF_OF_LIFE=1 to run.\n",
        )
        return 2
    summary, summary_path = await run_proof_of_life(output_dir=args.output_dir)
    if summary_path is not None:
        sys.stdout.write(f"summary_json={summary_path}\n")
    sys.stdout.write(
        f"overall_passed={str(summary.overall_passed).lower()} "
        f"passed={len(summary.passed)} failed={len(summary.failed)} "
        f"skipped={len(summary.skipped)}\n",
    )
    return 0 if summary.overall_passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    return asyncio.run(main_async(argv))


def _build_summary(
    *,
    run_id: str,
    probes: Mapping[str, ProbeResult],
    runner_tests: Mapping[str, RunnerSmokeResult],
    criteria_met: Mapping[str, bool],
    skipped: set[str],
) -> GatewayProofOfLifeSummary:
    passed = tuple(
        criterion for criterion, ok in sorted(criteria_met.items()) if ok
    )
    failed = tuple(
        criterion
        for criterion, mandatory in sorted(MANDATORY_CRITERIA.items())
        if mandatory and not criteria_met.get(criterion, False) and criterion not in skipped
    )
    overall_passed = not failed and all(
        criteria_met.get(criterion, False)
        for criterion, mandatory in MANDATORY_CRITERIA.items()
        if mandatory
    )
    return GatewayProofOfLifeSummary(
        run_id=run_id,
        timestamp_utc=_utc_now(),
        gateway_sprint=GATEWAY_SPRINT,
        criteria_manifest_ref=CRITERIA_MANIFEST_REF,
        service_probes=probes,
        runner_tests=runner_tests,
        passed=passed,
        failed=failed,
        skipped=tuple(sorted(skipped)),
        criteria_met=criteria_met,
        overall_passed=overall_passed,
    )


def _runner_result(
    name: str,
    result: run_local_agent.AgentRunResult,
    *,
    ok: bool,
    model_call_attempted: bool | None = None,
) -> RunnerSmokeResult:
    return RunnerSmokeResult(
        name=name,
        ok=ok,
        route=result.route,
        alias=result.alias,
        used_rag=result.used_rag,
        latency_ms=result.latency_ms,
        decision_id=result.decision_id,
        estimated_remote_tokens_avoided=result.estimated_remote_tokens_avoided,
        answer_length_chars=len(result.answer),
        error_category=result.error_category,
        fallback_applied=result.fallback_applied,
        fallback_reason=result.fallback_reason.value if result.fallback_reason else None,
        model_call_attempted=model_call_attempted,
    )


def _extract_model_aliases(payload: object) -> frozenset[str]:
    if not isinstance(payload, Mapping):
        raise ValueError("models response must be a mapping")
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("models response data must be a list")
    aliases: set[str] = set()
    for item in data:
        if isinstance(item, Mapping) and isinstance(item.get("id"), str):
            aliases.add(str(item["id"]))
    return frozenset(aliases)


def _elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
