"""Check local Ollama readiness for Qwen3-Embedding-4B bakeoff.

The default mode is read-only and does not call ``/api/embed``. Use
``--allow-embed-probe`` to run a safe one-token embedding dimension probe.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from collections.abc import Sequence

import httpx

from backend.rag.ollama_embedding_bakeoff import (
    NOMIC_MODEL_ID,
    OLLAMA_KNOWN_PRERELEASES,
    OLLAMA_LATEST_STABLE_KNOWN,
    OLLAMA_READINESS_SCHEMA_VERSION,
    OLLAMA_VERSION_CONTRACT_LAST_VERIFIED,
    QWEN3_4B_DEFAULT_DIMENSIONS,
    QWEN3_4B_MODEL_ID,
    QWEN3_4B_OLLAMA_MODEL_ID,
    OllamaReadiness,
    build_embed_payload,
    parse_ollama_version,
)

LOCALHOST_ALLOWED = frozenset({"localhost", "127.0.0.1", "::1"})


def _ensure_localhost(host: str) -> str:
    clean = host.strip().casefold()
    if clean not in LOCALHOST_ALLOWED:
        raise ValueError(f"host must be localhost/127.0.0.1/::1, got {host!r}")
    return clean


def _ollama_cli_version() -> str | None:
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    return parse_ollama_version(result.stdout or result.stderr)


async def _get_json(client: httpx.AsyncClient, path: str) -> dict[str, object] | None:
    try:
        response = await client.get(path)
        if response.status_code != 200:
            return None
        data = response.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


async def _show_model(client: httpx.AsyncClient, model: str) -> bool:
    try:
        response = await client.post("/api/show", json={"model": model})
        return response.status_code == 200
    except Exception:
        return False


async def _embed_probe(client: httpx.AsyncClient, model: str, dimensions: int | None) -> bool:
    payload = build_embed_payload(
        model=model,
        inputs=("probe",),
        dimensions=dimensions,
        keep_alive="30m",
        truncate=True,
    )
    try:
        response = await client.post("/api/embed", json=payload)
        if response.status_code != 200:
            return False
        data = response.json()
        embeddings = data.get("embeddings") if isinstance(data, dict) else None
        return isinstance(embeddings, list) and bool(embeddings)
    except Exception:
        return False


def _model_names(tags: dict[str, object] | None) -> tuple[str, ...]:
    if not tags:
        return ()
    raw_models = tags.get("models", [])
    names: list[str] = []
    if isinstance(raw_models, list):
        for item in raw_models:
            if isinstance(item, dict):
                name = item.get("name")
                if isinstance(name, str) and name:
                    names.append(name)
    return tuple(sorted(names))


def _has_model(names: Sequence[str], target: str) -> bool:
    base = target.split(":", maxsplit=1)[0]
    return any(name == target or name.split(":", maxsplit=1)[0] == base for name in names)


def _has_any_model(names: Sequence[str], targets: Sequence[str]) -> bool:
    return any(_has_model(names, target) for target in targets)


async def build_readiness(
    *,
    host: str,
    port: int,
    target_version: str | None,
    allow_embed_probe: bool,
    probe_dimensions: int | None,
    timeout_s: float,
) -> OllamaReadiness:
    clean_host = _ensure_localhost(host)
    base_url = f"http://{clean_host}:{port}"
    cli_version = _ollama_cli_version()
    notes: list[str] = [f"version contract last verified: {OLLAMA_VERSION_CONTRACT_LAST_VERIFIED}"]
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout_s) as client:
        version_payload = await _get_json(client, "/api/version")
        tags_payload = await _get_json(client, "/api/tags")
        api_version = None
        if version_payload:
            raw_version = version_payload.get("version")
            if isinstance(raw_version, str):
                api_version = parse_ollama_version(raw_version)
        ollama_version = api_version or cli_version
        running_models = _model_names(tags_payload)
        qwen_targets = (QWEN3_4B_MODEL_ID, QWEN3_4B_OLLAMA_MODEL_ID)
        qwen_by_tag = _has_any_model(running_models, qwen_targets)
        nomic_by_tag = _has_model(running_models, NOMIC_MODEL_ID)
        qwen_by_show = any([await _show_model(client, target) for target in qwen_targets])
        nomic_by_show = await _show_model(client, NOMIC_MODEL_ID)
        embed_endpoint_ok = False
        if allow_embed_probe:
            embed_endpoint_ok = await _embed_probe(client, NOMIC_MODEL_ID, None)
        else:
            notes.append("embed probe skipped; pass --allow-embed-probe to test /api/embed")

    qwen_available = qwen_by_tag or qwen_by_show
    nomic_available = nomic_by_tag or nomic_by_show
    api_version_ok = ollama_version is not None
    ready = bool(api_version_ok and nomic_available and qwen_available and (embed_endpoint_ok or not allow_embed_probe))
    return OllamaReadiness(
        schema_version=OLLAMA_READINESS_SCHEMA_VERSION,
        ollama_available=ollama_version is not None,
        ollama_version=ollama_version,
        target_version=target_version,
        latest_stable_known=OLLAMA_LATEST_STABLE_KNOWN,
        pre_release_available=_known_prerelease_label(),
        api_version_ok=api_version_ok,
        embed_endpoint_ok=embed_endpoint_ok,
        running_models=running_models,
        qwen3_4b_available=qwen_available,
        nomic_available=nomic_available,
        ready_for_bakeoff=ready,
        notes=tuple(notes),
    )


def _known_prerelease_label() -> str | None:
    if not OLLAMA_KNOWN_PRERELEASES:
        return None
    return sorted(OLLAMA_KNOWN_PRERELEASES)[-1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=11434)
    parser.add_argument("--target-version", default=OLLAMA_LATEST_STABLE_KNOWN)
    parser.add_argument("--allow-embed-probe", action="store_true")
    parser.add_argument("--probe-dimensions", type=int, default=QWEN3_4B_DEFAULT_DIMENSIONS)
    parser.add_argument("--timeout-s", type=float, default=5.0)
    return parser


async def async_main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = await build_readiness(
            host=args.host,
            port=args.port,
            target_version=args.target_version,
            allow_embed_probe=args.allow_embed_probe,
            probe_dimensions=args.probe_dimensions,
            timeout_s=args.timeout_s,
        )
    except ValueError as exc:
        sys.stderr.write(f"ollama readiness failed: {exc}\n")
        return 2
    sys.stdout.write(json.dumps(report.to_safe_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0 if report.ready_for_bakeoff else 1


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
