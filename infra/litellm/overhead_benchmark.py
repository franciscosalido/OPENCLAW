from __future__ import annotations

import json
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import httpx


BENCHMARK_SCHEMA_VERSION = "quimera-litellm-overhead-v1"
DEFAULT_SAMPLE_COUNT = 20
OVERHEAD_P95_BUDGET_MS = 50.0
SYNTHETIC_MESSAGE = "ping"


@dataclass(frozen=True)
class OverheadStats:
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    samples: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "mean_ms": self.mean_ms,
            "samples": self.samples,
        }


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        raise ValueError("at least one sample is required")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def calculate_overhead_stats(values_ms: Iterable[float]) -> OverheadStats:
    values = sorted(float(value) for value in values_ms)
    if not values:
        raise ValueError("at least one sample is required")
    return OverheadStats(
        p50_ms=round(_percentile(values, 0.50), 3),
        p95_ms=round(_percentile(values, 0.95), 3),
        p99_ms=round(_percentile(values, 0.99), 3),
        mean_ms=round(statistics.fmean(values), 3),
        samples=len(values),
    )


def skipped_report(reason: str = "QUIMERA_LITELLM_BENCHMARK is not 1") -> dict[str, Any]:
    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "status": "SKIPPED_VALID",
        "skipped": True,
        "reason": reason,
        "overhead_ms": None,
    }


def _post_json(client: httpx.Client, url: str, payload: dict[str, Any], headers: dict[str, str]) -> float:
    started = time.perf_counter()
    result = client.post(url, json=payload, headers=headers)
    duration_ms = (time.perf_counter() - started) * 1000.0
    if result.status_code >= 400:
        raise RuntimeError(f"HTTP {result.status_code}")
    return duration_ms


def run_live_benchmark(
    *,
    env: Mapping[str, str] | None = None,
    samples: int = DEFAULT_SAMPLE_COUNT,
) -> dict[str, Any]:
    env_map = os.environ if env is None else env
    if env_map.get("QUIMERA_LITELLM_BENCHMARK") != "1":
        return skipped_report()

    ollama_base = env_map.get("OLLAMA_BASE_URL", env_map.get("OLLAMA_API_BASE", "http://127.0.0.1:11434")).rstrip("/")
    litellm_base = env_map.get("LITELLM_BASE_URL", "http://127.0.0.1:4000").rstrip("/")
    api_key = env_map.get("QUIMERA_LLM_API_KEY") or env_map.get("LITELLM_MASTER_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    timeout = httpx.Timeout(connect=1.0, read=130.0, write=2.0, pool=1.0)
    overhead_values: list[float] = []

    ollama_payload = {
        "model": env_map.get("QWEN_MODEL", "qwen3:14b"),
        "messages": [{"role": "user", "content": SYNTHETIC_MESSAGE}],
        "stream": False,
        "keep_alive": -1,
        "options": {"num_predict": 4},
    }
    litellm_payload = {
        "model": "qwen3-local",
        "messages": [{"role": "user", "content": SYNTHETIC_MESSAGE}],
        "max_tokens": 4,
        "stream": False,
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            for _ in range(samples):
                direct_ms = _post_json(client, f"{ollama_base}/api/chat", ollama_payload, {})
                gateway_ms = _post_json(
                    client,
                    f"{litellm_base}/v1/chat/completions",
                    litellm_payload,
                    headers,
                )
                overhead_values.append(gateway_ms - direct_ms)
    except (httpx.HTTPError, RuntimeError) as exc:
        return {
            "schema_version": BENCHMARK_SCHEMA_VERSION,
            "status": "diagnostic_warning",
            "skipped": False,
            "diagnostic_warning": exc.__class__.__name__,
            "overhead_ms": None,
        }

    stats = calculate_overhead_stats(overhead_values)
    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "status": "pass" if stats.p95_ms < OVERHEAD_P95_BUDGET_MS else "warn",
        "skipped": False,
        "budget": {"p95_overhead_ms_lt": OVERHEAD_P95_BUDGET_MS},
        "overhead_ms": stats.to_dict(),
    }


def main() -> int:
    report = run_live_benchmark()
    output = Path(os.environ.get("QUIMERA_LITELLM_OVERHEAD_REPORT", ".runtime/reports/litellm_overhead.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
