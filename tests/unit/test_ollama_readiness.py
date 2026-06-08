from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from backend.rag.ollama_embedding_bakeoff import (
    OLLAMA_KNOWN_PRERELEASES,
    NOMIC_MODEL_ID,
    OLLAMA_LEGACY_EMBEDDINGS_PATH,
    OLLAMA_READINESS_SCHEMA_VERSION,
    OLLAMA_VERSION_CONTRACT_LAST_VERIFIED,
    QWEN3_4B_DEFAULT_DIMENSIONS,
    QWEN3_4B_MODEL_ID,
    QWEN3_4B_OLLAMA_MODEL_ID,
    OllamaReadiness,
    build_embed_payload,
    parse_ollama_version,
    select_latest_stable,
)
from scripts import check_ollama_readiness as readiness
from scripts import upgrade_ollama_local


def test_ollama_version_parse() -> None:
    assert parse_ollama_version("ollama version is 0.24.0") == "0.24.0"
    assert parse_ollama_version("v0.24.0") == "0.24.0"


def test_latest_stable_ignores_prerelease_by_default() -> None:
    assert select_latest_stable(("v0.24.0", "v0.30.0-rc1")) == "0.24.0"


def test_latest_stable_ignores_known_prerelease_without_markers() -> None:
    assert select_latest_stable(("0.24.0", "0.30.0")) == "0.24.0"


def test_select_latest_stable_uses_known_prereleases_param() -> None:
    assert (
        select_latest_stable(("0.24.0", "0.30.0"), known_prereleases=frozenset())
        == "0.30.0"
    )


def test_ollama_known_prereleases_excludes_0_30_0() -> None:
    assert "0.30.0" in OLLAMA_KNOWN_PRERELEASES
    assert select_latest_stable(("0.24.0", "0.30.0")) != "0.30.0"


def test_ollama_version_contract_has_last_verified_date() -> None:
    assert OLLAMA_VERSION_CONTRACT_LAST_VERIFIED == "2026-05-28"


def test_ollama_version_contract_file_pins_gate4_versions() -> None:
    text = Path("infra/ollama/version_contract.yaml").read_text(encoding="utf-8")
    assert 'target_version: "0.24.0"' in text
    assert 'qwen3_4b_ollama_model_id: "qwen3-embedding:4b"' in text
    assert 'default_embedding_baseline: "nomic-embed-text"' in text
    assert "known_prereleases:" in text
    assert '    - "0.30.0"' in text


def test_readiness_accepts_official_ollama_qwen3_4b_tag() -> None:
    assert readiness._has_any_model(
        (QWEN3_4B_OLLAMA_MODEL_ID,), (QWEN3_4B_MODEL_ID, QWEN3_4B_OLLAMA_MODEL_ID)
    )


def test_allow_prerelease_requires_flag() -> None:
    assert upgrade_ollama_local.main(["--target-version", "0.30.0"]) == 2
    plan = upgrade_ollama_local.build_upgrade_plan(
        execute=False,
        target_version="0.30.0",
        allow_prerelease=True,
        known_releases=("0.24.0", "0.30.0-rc1"),
    )
    assert plan.allow_prerelease is True


def test_api_embed_endpoint_configured() -> None:
    payload = build_embed_payload(
        model=NOMIC_MODEL_ID,
        inputs=("probe",),
        dimensions=None,
        keep_alive="30m",
    )
    assert payload["model"] == NOMIC_MODEL_ID
    assert payload["input"] == ["probe"]


def test_no_api_embeddings_legacy_default() -> None:
    assert OLLAMA_LEGACY_EMBEDDINGS_PATH == "/api/embeddings"
    assert readiness.__file__
    source = Path(readiness.__file__).read_text(encoding="utf-8")
    assert "/api/embeddings" not in source


def test_keep_alive_sent_to_embed_request() -> None:
    payload = build_embed_payload(
        model=QWEN3_4B_MODEL_ID,
        inputs=("probe",),
        dimensions=QWEN3_4B_DEFAULT_DIMENSIONS,
        keep_alive="30m",
    )
    assert payload["keep_alive"] == "30m"
    assert payload["dimensions"] == 2560


def test_batch_input_sent_to_api_embed() -> None:
    payload = build_embed_payload(
        model=NOMIC_MODEL_ID,
        inputs=("a", "b"),
        dimensions=None,
        keep_alive=None,
    )
    assert payload["input"] == ["a", "b"]


def test_model_unload_not_called_by_default() -> None:
    plan = upgrade_ollama_local.build_upgrade_plan(
        execute=False,
        target_version="0.24.0",
        allow_prerelease=False,
    )
    text = json.dumps(plan.to_safe_dict())
    assert "unload" not in text.lower()


@pytest.mark.asyncio
async def test_readiness_builds_safe_report_with_mocked_ollama() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.24.0"})
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": NOMIC_MODEL_ID},
                        {"name": QWEN3_4B_MODEL_ID},
                    ]
                },
            )
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"model_info": {}})
        if request.url.path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost:11434"
    ) as client:
        assert await readiness._show_model(client, QWEN3_4B_MODEL_ID) is True
        assert await readiness._embed_probe(client, NOMIC_MODEL_ID, None) is True

    report = OllamaReadiness(
        schema_version=OLLAMA_READINESS_SCHEMA_VERSION,
        ollama_available=True,
        ollama_version="0.24.0",
        target_version="0.24.0",
        latest_stable_known="0.24.0",
        pre_release_available="0.30.0",
        api_version_ok=True,
        embed_endpoint_ok=True,
        running_models=(NOMIC_MODEL_ID, QWEN3_4B_MODEL_ID),
        qwen3_4b_available=True,
        nomic_available=True,
        ready_for_bakeoff=True,
    )
    assert report.schema_version == "ollama-readiness-v1"
    assert "query_text" not in json.dumps(report.to_safe_dict())
