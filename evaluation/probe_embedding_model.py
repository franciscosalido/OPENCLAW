"""Embedding model probe for Q18 benchmarks.

Detects whether a given embedding provider/model is available locally and
reports the actual output dimension via a single safe probe text.

Security:
- No query text, document text, payload, or embeddings appear in output.
- Only aggregate metadata (provider, model, dimension, latency) is reported.
- Host must be localhost / 127.0.0.1 / ::1 for local providers.
- Output never contains raw vector values.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

PROBE_SAMPLE_TEXT = "probe"
LOCALHOST_ALLOWED = frozenset({"localhost", "127.0.0.1", "::1"})

Provider = Literal["ollama", "sentence-transformers", "tei", "openai-compatible"]

KNOWN_MODELS: dict[str, dict[str, object]] = {
    "Qwen/Qwen3-Embedding-0.6B": {
        "expected_dimensions": 1024,
        "provider_hint": "ollama",
    },
    "Qwen/Qwen3-Embedding-4B": {
        "expected_dimensions": 2560,
        "provider_hint": "ollama",
    },
    "Qwen/Qwen3-Embedding-8B": {
        "expected_dimensions": 4096,
        "provider_hint": "ollama",
    },
    "nomic-embed-text": {
        "expected_dimensions": 768,
        "provider_hint": "ollama",
    },
    "nomic-embed-text:latest": {
        "expected_dimensions": 768,
        "provider_hint": "ollama",
    },
}


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Safe probe output — no vectors, embeddings, or text in the report."""

    provider: str
    model: str
    available: bool
    dimensions: int | None
    expected_dimensions: int | None
    dimension_matches_expected: bool | None
    probe_latency_ms: float | None
    error: str | None
    probed_at_utc: str

    def to_safe_dict(self) -> dict[str, object]:
        """Return probe results as a safe JSON mapping."""
        return {
            "provider": self.provider,
            "model": self.model,
            "available": self.available,
            "dimensions": self.dimensions,
            "expected_dimensions": self.expected_dimensions,
            "dimension_matches_expected": self.dimension_matches_expected,
            "probe_latency_ms": self.probe_latency_ms,
            "error": self.error,
            "probed_at_utc": self.probed_at_utc,
        }


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_localhost(host: str) -> str:
    clean = host.strip().casefold()
    if clean not in LOCALHOST_ALLOWED:
        raise ValueError(f"host must be localhost/127.0.0.1/::1, got: {host!r}")
    return clean


def _probe_ollama(
    model: str,
    host: str,
    port: int,
    timeout_s: float,
    dimensions: int | None = None,
    keep_alive: str | None = None,
) -> tuple[int | None, float | None, str | None]:
    """Probe Ollama /api/embed. Returns (dimensions, latency_ms, error)."""
    url = f"http://{host}:{port}/api/embed"
    payload: dict[str, object] = {
        "model": model,
        "input": [PROBE_SAMPLE_TEXT],
        "truncate": True,
    }
    if dimensions is not None:
        payload["dimensions"] = dimensions
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    body = json.dumps(payload).encode("utf-8")
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=timeout_s)
        data = json.loads(resp.read().decode("utf-8"))
        latency_ms = (time.perf_counter() - t0) * 1000
        embeddings = data.get("embeddings", [])
        if not embeddings or not isinstance(embeddings[0], list):
            return None, latency_ms, "no_embeddings_in_response"
        dims = len(embeddings[0])
        return dims, round(latency_ms, 1), None
    except urllib.error.HTTPError as exc:
        latency_ms = (time.perf_counter() - t0) * 1000
        return None, round(latency_ms, 1), f"http_{exc.code}"
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000
        return None, round(latency_ms, 1), type(exc).__name__


def _probe_tei(model: str, host: str, port: int, timeout_s: float) -> tuple[int | None, float | None, str | None]:
    """Probe a TEI (text-embeddings-inference) compatible endpoint."""
    url = f"http://{host}:{port}/embed"
    body = json.dumps({"inputs": [PROBE_SAMPLE_TEXT]}).encode("utf-8")
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=timeout_s)
        data = json.loads(resp.read().decode("utf-8"))
        latency_ms = (time.perf_counter() - t0) * 1000
        if isinstance(data, list) and data and isinstance(data[0], list):
            return len(data[0]), round(latency_ms, 1), None
        return None, round(latency_ms, 1), "unexpected_tei_response_shape"
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000
        return None, round(latency_ms, 1), type(exc).__name__


def _probe_openai_compatible(
    model: str, host: str, port: int, timeout_s: float, path: str = "/v1/embeddings"
) -> tuple[int | None, float | None, str | None]:
    """Probe an OpenAI-compatible /v1/embeddings endpoint (e.g. LiteLLM)."""
    url = f"http://{host}:{port}{path}"
    body = json.dumps({"model": model, "input": [PROBE_SAMPLE_TEXT]}).encode("utf-8")
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=timeout_s)
        data = json.loads(resp.read().decode("utf-8"))
        latency_ms = (time.perf_counter() - t0) * 1000
        items = data.get("data", [])
        if items and isinstance(items[0], dict):
            emb = items[0].get("embedding", [])
            if isinstance(emb, list) and emb:
                return len(emb), round(latency_ms, 1), None
        return None, round(latency_ms, 1), "unexpected_openai_response_shape"
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000
        return None, round(latency_ms, 1), type(exc).__name__


def probe_embedding_model(
    provider: str,
    model: str,
    host: str = "localhost",
    port: int = 11434,
    timeout_s: float = 15.0,
    openai_path: str = "/v1/embeddings",
    dimensions: int | None = None,
    keep_alive: str | None = None,
) -> ProbeResult:
    """Run a single-text probe and return safe dimension/latency metadata."""
    clean_host = _ensure_localhost(host)
    known = KNOWN_MODELS.get(model, {})
    expected_dims: int | None = dimensions or known.get("expected_dimensions")  # type: ignore[assignment]

    dims: int | None
    latency_ms: float | None
    error: str | None

    if provider == "ollama":
        dims, latency_ms, error = _probe_ollama(
            model,
            clean_host,
            port,
            timeout_s,
            dimensions=dimensions,
            keep_alive=keep_alive,
        )
    elif provider == "tei":
        dims, latency_ms, error = _probe_tei(model, clean_host, port, timeout_s)
    elif provider == "openai-compatible":
        dims, latency_ms, error = _probe_openai_compatible(model, clean_host, port, timeout_s, openai_path)
    else:
        dims, latency_ms, error = None, None, f"unknown_provider:{provider}"

    available = dims is not None and error is None
    dim_match: bool | None = None
    if available and expected_dims is not None and dims is not None:
        dim_match = dims == expected_dims

    return ProbeResult(
        provider=provider,
        model=model,
        available=available,
        dimensions=dims,
        expected_dimensions=expected_dims,
        dimension_matches_expected=dim_match,
        probe_latency_ms=latency_ms,
        error=error,
        probed_at_utc=_utc_now_iso(),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--provider", default="ollama", choices=["ollama", "tei", "openai-compatible"],
                        help="Embedding provider type (default: ollama)")
    parser.add_argument("--model", default="Qwen/Qwen3-Embedding-4B",
                        help="Model name to probe (default: Qwen/Qwen3-Embedding-4B)")
    parser.add_argument("--host", default="localhost",
                        help="Host (must be localhost / 127.0.0.1 / ::1)")
    parser.add_argument("--port", type=int, default=11434,
                        help="Port (default: 11434 for Ollama)")
    parser.add_argument("--timeout-s", type=float, default=15.0,
                        help="Probe timeout in seconds (default: 15)")
    parser.add_argument("--openai-path", default="/v1/embeddings",
                        help="Path for openai-compatible provider (default: /v1/embeddings)")
    parser.add_argument("--dimensions", type=int, default=None,
                        help="Optional Ollama /api/embed dimensions request")
    parser.add_argument("--keep-alive", default=None,
                        help="Optional Ollama keep_alive value for the probe")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint — emits safe JSON to stdout."""
    args = _build_parser().parse_args(argv)
    try:
        result = probe_embedding_model(
            provider=args.provider,
            model=args.model,
            host=args.host,
            port=args.port,
            timeout_s=args.timeout_s,
            openai_path=args.openai_path,
            dimensions=args.dimensions,
            keep_alive=args.keep_alive,
        )
    except ValueError as exc:
        sys.stderr.write(f"probe failed: {exc}\n")
        return 2

    sys.stdout.write(json.dumps(result.to_safe_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0 if result.available else 1


if __name__ == "__main__":
    raise SystemExit(main())
