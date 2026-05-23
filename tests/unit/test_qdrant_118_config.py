"""Offline tests for the Qdrant 1.18 upgrade contract."""

from __future__ import annotations

import ast
import json
import tomllib
from pathlib import Path

import pytest
import yaml
from qdrant_client import AsyncQdrantClient

from scripts import check_qdrant_118_readiness as readiness

ROOT = Path(__file__).resolve().parents[2]
VERSION_CONTRACT_PATH = ROOT / "infra/qdrant/version_contract.yaml"
PYPROJECT_PATH = ROOT / "pyproject.toml"
COMPOSE_PATH = ROOT / "docker/docker-compose.qdrant.yml"
CONFIG_PATH = ROOT / "infra/qdrant/config.yaml"
READINESS_SCRIPT_PATH = ROOT / "scripts/check_qdrant_118_readiness.py"
TEST_PATH = Path(__file__).resolve()


def _load_yaml(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _contract() -> dict[str, object]:
    raw = _load_yaml(VERSION_CONTRACT_PATH)
    qdrant = raw["qdrant"]
    assert isinstance(qdrant, dict)
    return qdrant


def _pyproject_dependencies() -> list[str]:
    raw = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    deps = raw["project"]["dependencies"]
    assert isinstance(deps, list)
    return [item for item in deps if isinstance(item, str)]


def _compose_service() -> dict[str, object]:
    raw = _load_yaml(COMPOSE_PATH)
    services = raw["services"]
    assert isinstance(services, dict)
    service = services["qdrant"]
    assert isinstance(service, dict)
    return service


def test_version_contract_targets_118() -> None:
    contract = _contract()

    assert contract["target_version"] == "1.18.0"
    assert contract["server_image"] == "qdrant/qdrant:v1.18.0"
    assert contract["client_dependency"] == "qdrant-client==1.18.0"
    assert contract["rest_port"] == 6333
    assert contract["grpc_port"] == 6334
    assert contract["config_schema_version"] == "qdrant-local-config-v1"


def test_pyproject_pins_qdrant_client_118() -> None:
    assert "qdrant-client==1.18.0" in _pyproject_dependencies()


def test_compose_pins_qdrant_server_118() -> None:
    assert _compose_service()["image"] == "qdrant/qdrant:v1.18.0"


def test_no_qdrant_latest_tag_anywhere() -> None:
    service = _compose_service()
    image = service["image"]

    assert isinstance(image, str)
    assert image.startswith("qdrant/qdrant:")
    assert not image.endswith(":latest")


def test_no_qdrant_legacy_version_in_any_compose_file() -> None:
    for compose in (ROOT / "docker").glob("*.yml"):
        text = compose.read_text(encoding="utf-8")
        assert "qdrant/qdrant:latest" not in text, (
            f"{compose.name}: uses qdrant latest"
        )
        assert "v1.13" not in text or "# legacy" in text, (
            f"{compose.name}: references v1.13.x without justification"
        )


def test_server_and_client_versions_match_contract() -> None:
    contract = _contract()
    image = _compose_service()["image"]

    assert contract["client_dependency"] in _pyproject_dependencies()
    assert image == contract["server_image"]
    assert str(contract["target_version"]) in str(contract["client_dependency"])
    assert str(contract["target_version"]) in str(contract["server_image"])


def test_qdrant_ports_6333_and_6334_exposed() -> None:
    ports = _compose_service()["ports"]

    assert isinstance(ports, list)
    assert "6333:6333" in ports
    assert "6334:6334" in ports


def test_qdrant_healthcheck_exists() -> None:
    healthcheck = _compose_service()["healthcheck"]

    assert isinstance(healthcheck, dict)
    assert healthcheck["test"] == [
        "CMD-SHELL",
        "curl -fsS http://localhost:6333/healthz || exit 1",
    ]
    assert healthcheck["retries"] == 10


def test_qdrant_mounts_config_if_compose_uses_external_config() -> None:
    volumes = _compose_service()["volumes"]

    assert isinstance(volumes, list)
    assert "../infra/qdrant/config.yaml:/qdrant/config/production.yaml:ro" in volumes


def test_qdrant_image_has_explicit_version_tag() -> None:
    image = _compose_service()["image"]

    assert isinstance(image, str)
    assert image.count(":") == 1
    assert image.rsplit(":", maxsplit=1)[1] == "v1.18.0"


def test_qdrant_config_yaml_exists() -> None:
    assert CONFIG_PATH.exists()


def test_qdrant_config_ports_match_contract() -> None:
    config = _load_yaml(CONFIG_PATH)
    service = config["service"]
    contract = _contract()

    assert isinstance(service, dict)
    assert service["http_port"] == contract["rest_port"]
    assert service["grpc_port"] == contract["grpc_port"]


def test_qdrant_config_max_request_size_present() -> None:
    service = _load_yaml(CONFIG_PATH)["service"]

    assert isinstance(service, dict)
    assert service["max_request_size_mb"] == 32
    assert service["max_workers"] == 0


def test_qdrant_config_does_not_enable_strict_mode() -> None:
    config = _load_yaml(CONFIG_PATH)

    assert "strict_mode_config" not in config


def test_qdrant_config_does_not_enable_quantization_or_schema() -> None:
    config = _load_yaml(CONFIG_PATH)

    forbidden_keys = {
        "collections",
        "vectors",
        "sparse_vectors",
        "quantization_config",
        "strict_mode_config",
        "low_memory_mode",
    }
    assert forbidden_keys.isdisjoint(config)


def test_qdrant_config_no_collection_names() -> None:
    config_text = CONFIG_PATH.read_text(encoding="utf-8")

    assert "quimera_knowledge" not in config_text
    assert "quimera_knowledge_v2" not in config_text
    assert "openclaw_knowledge" not in config_text


def _ready_report(**overrides: object) -> readiness.QdrantReadiness:
    values: dict[str, object] = {
        "target_version": "1.18.0",
        "qdrant_client_version": "1.18.0",
        "qdrant_server_version": "1.18.0",
        "rest_port": 6333,
        "grpc_port": 6334,
        "rest_ok": True,
        "grpc_ok": True,
        "checked_at_utc": "2026-05-23T00:00:00Z",
    }
    values.update(overrides)
    target_version = values["target_version"]
    qdrant_client_version = values["qdrant_client_version"]
    qdrant_server_version = values["qdrant_server_version"]
    rest_port = values["rest_port"]
    grpc_port = values["grpc_port"]
    rest_ok = values["rest_ok"]
    grpc_ok = values["grpc_ok"]
    checked_at_utc = values["checked_at_utc"]

    assert isinstance(target_version, str)
    assert isinstance(qdrant_client_version, str)
    assert isinstance(qdrant_server_version, (str, type(None)))
    assert isinstance(rest_port, int)
    assert isinstance(grpc_port, int)
    assert isinstance(rest_ok, bool)
    assert isinstance(grpc_ok, bool)
    assert isinstance(checked_at_utc, str)
    return readiness.build_readiness_report(
        target_version=target_version,
        qdrant_client_version=qdrant_client_version,
        qdrant_server_version=qdrant_server_version,
        rest_port=rest_port,
        grpc_port=grpc_port,
        rest_ok=rest_ok,
        grpc_ok=grpc_ok,
        checked_at_utc=checked_at_utc,
    )


def test_readiness_to_dict_shape() -> None:
    as_dict = _ready_report().to_dict()

    assert as_dict == {
        "schema_version": "qdrant-readiness-v1",
        "checked_at_utc": "2026-05-23T00:00:00Z",
        "target_version": "1.18.0",
        "qdrant_client_version": "1.18.0",
        "qdrant_server_version": "1.18.0",
        "version_parity_ok": True,
        "rest_port": 6333,
        "grpc_port": 6334,
        "rest_ok": True,
        "grpc_ok": True,
        "ready": True,
    }


def test_assert_ready_passes_for_118() -> None:
    readiness.assert_qdrant_118_ready(_ready_report())


def test_assert_ready_fails_for_client_mismatch() -> None:
    with pytest.raises(RuntimeError, match="client version"):
        readiness.assert_qdrant_118_ready(
            _ready_report(qdrant_client_version="1.13.2"),
        )


def test_assert_ready_fails_for_server_mismatch() -> None:
    with pytest.raises(RuntimeError, match="server version"):
        readiness.assert_qdrant_118_ready(
            _ready_report(qdrant_server_version="1.13.2"),
        )


def test_assert_ready_fails_when_server_version_is_none() -> None:
    with pytest.raises(RuntimeError, match="server version"):
        readiness.assert_qdrant_118_ready(
            _ready_report(qdrant_server_version=None),
        )


def test_assert_ready_fails_for_future_patch_version() -> None:
    """Version parity requires exact match; 1.18.1 is not 1.18.0."""

    with pytest.raises(RuntimeError, match="server version"):
        readiness.assert_qdrant_118_ready(
            _ready_report(qdrant_server_version="1.18.1"),
        )


def test_assert_ready_fails_when_rest_false() -> None:
    with pytest.raises(RuntimeError, match="REST probe"):
        readiness.assert_qdrant_118_ready(_ready_report(rest_ok=False))


def test_assert_ready_fails_when_grpc_false() -> None:
    with pytest.raises(RuntimeError, match="gRPC probe"):
        readiness.assert_qdrant_118_ready(_ready_report(grpc_ok=False))


def test_readiness_json_is_parseable() -> None:
    encoded = json.dumps(_ready_report().to_dict(), sort_keys=True)

    assert json.loads(encoded)["ready"] is True


@pytest.mark.asyncio
async def test_readiness_script_output_is_valid_json_on_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_rest_health(host: str, port: int, timeout_s: float) -> bool:
        return host == "localhost" and port == 6333 and timeout_s == 5.0

    async def fake_server_version(
        host: str,
        port: int,
        timeout_s: float,
    ) -> str:
        assert host == "localhost"
        assert port == 6333
        assert timeout_s == 5.0
        return "1.18.0"

    async def fake_grpc_probe(host: str, grpc_port: int, timeout_s: float) -> bool:
        return host == "localhost" and grpc_port == 6334 and timeout_s == 5.0

    monkeypatch.setattr(readiness, "check_rest_health", fake_rest_health)
    monkeypatch.setattr(readiness, "fetch_server_version", fake_server_version)
    monkeypatch.setattr(readiness, "check_grpc_probe", fake_grpc_probe)
    monkeypatch.setattr(readiness, "_client_version", lambda: "1.18.0")

    exit_code = await readiness.async_main([])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert payload["schema_version"] == "qdrant-readiness-v1"
    assert payload["ready"] is True
    assert payload["qdrant_client_version"] == "1.18.0"
    assert payload["qdrant_server_version"] == "1.18.0"


def test_readiness_script_has_no_collection_mutation_calls() -> None:
    tree = ast.parse(READINESS_SCRIPT_PATH.read_text(encoding="utf-8"))
    forbidden_calls = {
        "create_collection",
        "recreate_collection",
        "delete_collection",
        "upsert",
        "delete",
        "upload_collection",
        "update_collection",
        "create_payload_index",
        "delete_payload_index",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden_calls


def test_readiness_script_does_not_reference_legacy_collections() -> None:
    source = READINESS_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "quimera_knowledge" not in source
    assert "quimera_knowledge_v2" not in source
    assert "openclaw_knowledge" not in source


def test_async_qdrant_client_importable() -> None:
    assert AsyncQdrantClient is not None


def test_async_qdrant_client_has_methods_used_by_pr08_pr10() -> None:
    for method_name in (
        "query_points",
        "upsert",
        "get_collections",
        "create_collection",
        "delete_collection",
    ):
        assert hasattr(AsyncQdrantClient, method_name)


def test_async_qdrant_client_118_removed_legacy_search_methods() -> None:
    """Q18 code must use query_points; 1.18 no longer exposes old search APIs."""

    assert not hasattr(AsyncQdrantClient, "search")
    assert not hasattr(AsyncQdrantClient, "search_batch")


def test_unit_tests_do_not_require_qdrant_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.delenv("RUN_HYBRID_SMOKE", raising=False)

    assert _contract()["target_version"] == "1.18.0"


def test_unit_tests_do_not_import_docker_sdk() -> None:
    tree = ast.parse(TEST_PATH.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots = {alias.name.split(".")[0] for alias in node.names}
            assert "docker" not in imported_roots
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module.split(".")[0] != "docker"


def test_unit_tests_do_not_call_network() -> None:
    tree = ast.parse(TEST_PATH.read_text(encoding="utf-8"))
    forbidden_calls = {"get", "post", "put", "delete", "request", "connect"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden_calls
