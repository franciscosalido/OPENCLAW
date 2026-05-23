"""Offline tests for Qdrant 1.18 hybrid benchmark schema."""

from __future__ import annotations

import ast
import importlib
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

import backend.rag.qdrant_hybrid_118 as schema_module
from backend.rag.qdrant_hybrid_118 import (
    BENCHMARK_COLLECTION,
    CANDIDATE_COLLECTION,
    LEGACY_COLLECTION,
    HybridCollectionSnapshot,
    HybridCollectionSpec118,
    HybridSchemaError,
    QdrantHybridSchemaClient118,
    build_collection_create_payload,
    build_payload_index_specs,
    build_metrics_probe_config,
    build_sparse_vectors_config,
    build_vectors_config,
    default_hybrid_collection_spec_118,
    ensure_benchmark_collection_118,
    schema_snapshot_from_collection_info,
    validate_collection_info_against_spec,
    validate_spec_118,
    write_schema_snapshot,
)
from scripts import qdrant_create_hybrid_schema_118 as schema_cli

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "backend/rag/qdrant_hybrid_118.py"
SCRIPT_PATH = ROOT / "scripts/qdrant_create_hybrid_schema_118.py"


class FakeHybridSchemaClient:
    def __init__(self, *, exists: bool = False) -> None:
        self.exists = exists
        self.created: list[str] = []
        self.indexes: list[str] = []
        self.deleted: list[str] = []
        self.upserts: list[str] = []
        self.info = _valid_collection_info()

    async def collection_exists(self, collection_name: str) -> bool:
        return self.exists

    async def create_collection(self, spec: HybridCollectionSpec118) -> None:
        self.created.append(spec.collection_name)
        self.exists = True

    async def create_payload_indexes(self, spec: HybridCollectionSpec118) -> None:
        self.indexes.extend(spec.payload_indexes)

    async def get_collection_info(self, collection_name: str) -> Mapping[str, object]:
        return self.info

    async def get_qdrant_versions(self) -> Mapping[str, str | None]:
        return {
            "qdrant_server_version": "1.18.0",
            "qdrant_client_version": "1.18.0",
        }


class FakeInfoClient:
    async def info(self) -> Mapping[str, object]:
        return {"version": "1.18.0", "title": "qdrant"}


def _valid_collection_info() -> dict[str, object]:
    spec = default_hybrid_collection_spec_118()
    return {
        "vectors": {
            spec.dense_vector_name: {
                "size": spec.dense_dimensions,
                "distance": "Cosine",
            }
        },
        "sparse_vectors": {spec.sparse_vector_name: {}},
        "payload_indexes": list(spec.payload_indexes),
        "optimizer_config": {},
        "quantization_config": {},
    }


def test_hybrid_spec_118_contract_exact_values() -> None:
    spec = default_hybrid_collection_spec_118()

    assert spec.collection_name == "quimera_benchmark_hybrid_118"
    assert spec.dense_vector_name == "dense"
    assert spec.sparse_vector_name == "sparse"
    assert spec.dense_dimensions == 1024
    assert spec.dense_distance == "COSINE"
    assert spec.embedding_model == "Qwen/Qwen3-Embedding-0.6B"
    assert spec.embedding_provider == "local"
    assert spec.embedding_dimensions == 1024
    assert spec.embedding_version == "qwen3-embedding-0.6b@benchmark"


def test_spec_uses_benchmark_not_candidate_or_legacy() -> None:
    spec = default_hybrid_collection_spec_118()

    assert spec.collection_name == BENCHMARK_COLLECTION
    assert spec.collection_name != CANDIDATE_COLLECTION
    assert spec.collection_name != LEGACY_COLLECTION


def test_dense_and_sparse_names_are_distinct() -> None:
    spec = default_hybrid_collection_spec_118()

    assert spec.dense_vector_name != spec.sparse_vector_name


def test_schema_version_exact() -> None:
    assert default_hybrid_collection_spec_118().schema_version == "qdrant-hybrid-118-v1"


def test_payload_index_contract_exact_fields_and_types() -> None:
    spec = default_hybrid_collection_spec_118()

    assert spec.payload_index_types == {
        "doc_id": "keyword",
        "chunk_id": "keyword",
        "chunk_index": "integer",
        "source": "keyword",
        "schema_version": "keyword",
        "embedding_model": "keyword",
        "embedding_provider": "keyword",
        "embedding_dimensions": "integer",
        "embedding_version": "keyword",
        "corpus_id": "keyword",
        "security_level": "keyword",
    }
    assert set(spec.payload_indexes) == set(spec.payload_index_types)


def test_required_embedding_metadata_fields_present() -> None:
    fields = default_hybrid_collection_spec_118().required_payload_fields()

    assert "embedding_model" in fields
    assert "embedding_provider" in fields
    assert "embedding_dimensions" in fields
    assert "embedding_version" in fields


def test_build_vectors_config_dense_1024_cosine() -> None:
    spec = default_hybrid_collection_spec_118()

    assert build_vectors_config(spec) == {"dense": {"size": 1024, "distance": "Cosine"}}


def test_build_sparse_vectors_config_contains_sparse() -> None:
    assert build_sparse_vectors_config(default_hybrid_collection_spec_118()) == {
        "sparse": {}
    }


def test_build_collection_create_payload_has_dense_and_sparse() -> None:
    payload = build_collection_create_payload(default_hybrid_collection_spec_118())

    assert payload["vectors"] == {"dense": {"size": 1024, "distance": "Cosine"}}
    assert payload["sparse_vectors"] == {"sparse": {}}


def test_build_payload_index_specs_all_fields() -> None:
    spec = default_hybrid_collection_spec_118()
    indexes = build_payload_index_specs(spec)

    assert tuple(index.field_name for index in indexes) == spec.payload_indexes
    assert tuple(index.field_schema for index in indexes) == tuple(
        spec.payload_index_types[name] for name in spec.payload_indexes
    )


def test_to_safe_dict_has_no_forbidden_fields() -> None:
    as_dict = default_hybrid_collection_spec_118().to_safe_dict()

    forbidden = {"text", "chunk_text", "payload", "vector", "embedding"}
    assert forbidden.isdisjoint(as_dict)


def test_config_builders_are_pure_and_idempotent() -> None:
    spec = default_hybrid_collection_spec_118()

    assert build_collection_create_payload(spec) == build_collection_create_payload(spec)
    assert spec == default_hybrid_collection_spec_118()


def test_spec_is_hashable_for_future_set_usage() -> None:
    spec = default_hybrid_collection_spec_118()

    assert hash(spec) == hash(default_hybrid_collection_spec_118())
    assert {spec} == {default_hybrid_collection_spec_118()}


def test_validate_spec_rejects_legacy_collection() -> None:
    with pytest.raises(ValueError, match="quimera_benchmark_hybrid_118"):
        HybridCollectionSpec118(collection_name=LEGACY_COLLECTION)


def test_validate_spec_rejects_candidate_collection() -> None:
    with pytest.raises(ValueError, match="quimera_benchmark_hybrid_118"):
        HybridCollectionSpec118(collection_name=CANDIDATE_COLLECTION)


def test_validate_spec_rejects_null_byte_collection_name() -> None:
    with pytest.raises(ValueError, match="null bytes"):
        HybridCollectionSpec118(collection_name=f"{BENCHMARK_COLLECTION}\x00")


def test_validate_spec_rejects_vector_name_collision() -> None:
    with pytest.raises(ValueError, match="must differ"):
        HybridCollectionSpec118(sparse_vector_name="dense")


def test_validate_spec_rejects_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="embedding_dimensions"):
        HybridCollectionSpec118(embedding_dimensions=768)


def test_validate_spec_rejects_missing_index_type() -> None:
    with pytest.raises(ValueError, match="cover exactly"):
        HybridCollectionSpec118(payload_index_types={"doc_id": "keyword"})


def test_validate_collection_detects_wrong_dense_dimension() -> None:
    info = _valid_collection_info()
    vectors = info["vectors"]
    assert isinstance(vectors, dict)
    dense = vectors["dense"]
    assert isinstance(dense, dict)
    dense["size"] = 768

    with pytest.raises(HybridSchemaError, match="dimension"):
        validate_collection_info_against_spec(info, default_hybrid_collection_spec_118())


def test_validate_collection_detects_missing_sparse_vector() -> None:
    info = _valid_collection_info()
    info["sparse_vectors"] = {}

    with pytest.raises(HybridSchemaError, match="sparse"):
        validate_collection_info_against_spec(info, default_hybrid_collection_spec_118())


def test_validate_collection_detects_missing_payload_index() -> None:
    info = _valid_collection_info()
    info["payload_indexes"] = ["doc_id"]

    with pytest.raises(HybridSchemaError, match="payload indexes"):
        validate_collection_info_against_spec(info, default_hybrid_collection_spec_118())


@pytest.mark.asyncio
async def test_ensure_creates_only_benchmark_collection() -> None:
    client = FakeHybridSchemaClient(exists=False)
    spec = default_hybrid_collection_spec_118()

    await ensure_benchmark_collection_118(client, spec)

    assert client.created == [BENCHMARK_COLLECTION]


@pytest.mark.asyncio
async def test_ensure_never_touches_legacy_or_candidate() -> None:
    client = FakeHybridSchemaClient(exists=False)

    await ensure_benchmark_collection_118(client, default_hybrid_collection_spec_118())

    assert CANDIDATE_COLLECTION not in client.created
    assert LEGACY_COLLECTION not in client.created


@pytest.mark.asyncio
async def test_ensure_creates_payload_indexes() -> None:
    client = FakeHybridSchemaClient(exists=False)
    spec = default_hybrid_collection_spec_118()

    await ensure_benchmark_collection_118(client, spec)

    assert tuple(client.indexes) == spec.payload_indexes


@pytest.mark.asyncio
async def test_ensure_existing_collection_validates_without_create() -> None:
    client = FakeHybridSchemaClient(exists=True)

    snapshot = await ensure_benchmark_collection_118(
        client,
        default_hybrid_collection_spec_118(),
    )

    assert client.created == []
    assert snapshot.collection_name == BENCHMARK_COLLECTION


@pytest.mark.asyncio
async def test_ensure_fail_if_exists_raises() -> None:
    client = FakeHybridSchemaClient(exists=True)

    with pytest.raises(HybridSchemaError, match="already exists"):
        await ensure_benchmark_collection_118(
            client,
            default_hybrid_collection_spec_118(),
            fail_if_exists=True,
        )


@pytest.mark.asyncio
async def test_ensure_does_not_delete_or_upsert() -> None:
    client = FakeHybridSchemaClient(exists=False)

    await ensure_benchmark_collection_118(client, default_hybrid_collection_spec_118())

    assert client.deleted == []
    assert client.upserts == []


def test_schema_snapshot_contains_key_fields() -> None:
    snapshot = schema_snapshot_from_collection_info(
        _valid_collection_info(),
        default_hybrid_collection_spec_118(),
        server_version="1.18.0",
        client_version="1.18.0",
    )

    assert snapshot.collection_name == BENCHMARK_COLLECTION
    assert snapshot.dense_vector_name == "dense"
    assert snapshot.sparse_vector_name == "sparse"
    assert snapshot.dense_dimensions == 1024


@pytest.mark.asyncio
async def test_adapter_reads_server_version_from_info_endpoint() -> None:
    adapter = QdrantHybridSchemaClient118(FakeInfoClient())

    versions = await adapter.get_qdrant_versions()

    assert versions["qdrant_server_version"] == "1.18.0"
    assert versions["qdrant_client_version"] == "1.18.0"


def test_schema_snapshot_has_no_points_payload_vectors_embeddings() -> None:
    snapshot = schema_snapshot_from_collection_info(
        _valid_collection_info(),
        default_hybrid_collection_spec_118(),
    )
    as_dict = snapshot.to_safe_dict()

    forbidden = {"points", "payload", "vectors", "embeddings", "text"}
    assert forbidden.isdisjoint(as_dict)


def test_write_schema_snapshot_json_parseable(tmp_path: Path) -> None:
    snapshot = schema_snapshot_from_collection_info(
        _valid_collection_info(),
        default_hybrid_collection_spec_118(),
    )
    path = tmp_path / "snapshot.json"

    write_schema_snapshot(snapshot, path, allow_any_path=True)

    assert json.loads(path.read_text(encoding="utf-8"))["collection_name"] == BENCHMARK_COLLECTION


def test_snapshot_path_default_is_under_docs_specs() -> None:
    root = (ROOT / "docs/specs/qdrant-1-18-upgrade").resolve()
    resolved = (ROOT / schema_cli.DEFAULT_SNAPSHOT_PATH).resolve()

    assert root in resolved.parents
    assert resolved.name == "benchmark_schema_snapshot.json"


def test_metrics_probe_config_points_to_metrics_and_telemetry() -> None:
    config = build_metrics_probe_config(BENCHMARK_COLLECTION)

    assert config["metrics_endpoint"] == "/metrics?per_collection=true"
    assert config["telemetry_endpoint"] == "/telemetry"
    assert config["collection"] == BENCHMARK_COLLECTION


def test_metrics_probe_config_makes_no_network_call() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    target = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "build_metrics_probe_config"
    )
    forbidden_calls = {"get", "post", "connect", "request", "send"}

    for node in ast.walk(target):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden_calls
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls


def test_schema_module_import_is_side_effect_free() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    top_level_calls = [
        node
        for node in tree.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
    ]

    assert top_level_calls == []
    assert importlib.import_module("backend.rag.qdrant_hybrid_118") is schema_module


def test_no_retrieval_functions_in_schema_module() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert "search" not in node.name
            assert "retrieve" not in node.name
            assert "query" not in node.name


def test_schema_module_does_not_import_hybrid_retriever() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "hybrid_retriever" not in source


def test_schema_module_does_not_import_fusion() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all("fusion" not in alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            assert "fusion" not in node.module


def test_schema_module_forbidden_call_denylist() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden = {
        "delete_collection",
        "recreate_collection",
        "upsert",
        "set_payload",
        "delete_payload",
        "update_collection",
        "upload_collection",
        "delete_vectors",
        "scroll",
        "search",
        "search_batch",
        "retrieve",
        "query_points",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden


def test_script_requires_env_for_execute() -> None:
    assert schema_cli.main(["--execute"]) == 2


def test_script_refuses_candidate_and_legacy_collection_names() -> None:
    assert schema_cli.main(["--collection", CANDIDATE_COLLECTION]) == 2
    assert schema_cli.main(["--collection", LEGACY_COLLECTION]) == 2


def test_parse_args_defaults_to_dry_run() -> None:
    args = schema_cli.parse_args([])

    assert args.dry_run is True


def test_execute_flag_switches_dry_run_false() -> None:
    args = schema_cli.parse_args(["--execute"])

    assert args.dry_run is False


@pytest.mark.asyncio
async def test_execute_requires_env_var() -> None:
    client = FakeHybridSchemaClient(exists=False)

    with pytest.raises(RuntimeError, match="RUN_QDRANT_SCHEMA_118"):
        await schema_cli.async_main(["--execute"], client=client, env={})


@pytest.mark.asyncio
async def test_async_main_passes_grpc_port_to_real_client_builder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, int | str] = {}

    def fake_build_client(
        *,
        host: str,
        port: int,
        grpc_port: int,
    ) -> FakeHybridSchemaClient:
        captured["host"] = host
        captured["port"] = port
        captured["grpc_port"] = grpc_port
        return FakeHybridSchemaClient(exists=False)

    def fake_write_snapshot(
        snapshot: HybridCollectionSnapshot,
        path: Path,
    ) -> None:
        captured["snapshot_path"] = str(path)

    monkeypatch.setattr(schema_cli, "_build_client", fake_build_client)
    monkeypatch.setattr(schema_cli, "write_schema_snapshot", fake_write_snapshot)

    exit_code = await schema_cli.async_main(
        [
            "--execute",
            "--port",
            "7333",
            "--grpc-port",
            "7444",
            "--snapshot-path",
            str(tmp_path / "snapshot.json"),
        ],
        env={schema_cli.RUN_SCHEMA_ENV_VAR: schema_cli.RUN_SCHEMA_REQUIRED_VALUE},
    )

    assert exit_code == 0
    assert captured == {
        "host": "localhost",
        "port": 7333,
        "grpc_port": 7444,
        "snapshot_path": str(tmp_path / "snapshot.json"),
    }


@pytest.mark.asyncio
async def test_cli_dry_run_outputs_safe_json(capsys: pytest.CaptureFixture[str]) -> None:
    client = FakeHybridSchemaClient(exists=False)

    exit_code = await schema_cli.async_main([], client=client, env={})
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert payload["dry_run"] is True
    assert payload["collection_name"] == BENCHMARK_COLLECTION


def test_cli_error_stdout_empty_and_stderr_sanitized(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = schema_cli.main(["--host", "https://localhost:6333"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "qdrant hybrid schema failed: ValueError\n"


def test_script_does_not_delete_recreate_or_upsert() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    forbidden = {"delete_collection", "recreate_collection", "upsert"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden
