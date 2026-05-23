"""Offline tests for governed local Qdrant collection reset."""

from __future__ import annotations

import ast
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts import qdrant_reset_local_collections as reset

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts/qdrant_reset_local_collections.py"
POLICY_PATH = ROOT / "docs/specs/qdrant-1-18-upgrade/reset_policy.md"


class FakeResetClient:
    def __init__(self, collections: Sequence[str]) -> None:
        self.collections = list(collections)
        self.deleted: list[str] = []
        self.created: list[str] = []
        self.delete_failures: set[str] = set()
        self.closed = False

    async def get_collections(self) -> Sequence[str]:
        return list(self.collections)

    async def delete_collection(self, collection_name: str) -> None:
        if collection_name in self.delete_failures:
            raise RuntimeError("fake delete failure with sensitive details")
        self.deleted.append(collection_name)
        self.collections = [name for name in self.collections if name != collection_name]

    async def create_benchmark_collection(self, collection_name: str) -> None:
        self.created.append(collection_name)
        if collection_name not in self.collections:
            self.collections.append(collection_name)

    async def close(self) -> None:
        self.closed = True


def _env_enabled() -> dict[str, str]:
    return {reset.LOCAL_RESET_ENV_VAR: reset.LOCAL_RESET_REQUIRED_VALUE}


def test_ensure_localhost_accepts_localhost_127_and_ipv6_loopback() -> None:
    assert reset.ensure_localhost(" localhost ") == "localhost"
    assert reset.ensure_localhost("127.0.0.1") == "127.0.0.1"
    assert reset.ensure_localhost("::1") == "::1"


@pytest.mark.parametrize(
    "host",
    [
        "0.0.0.0",
        "192.168.1.10",
        "10.0.0.2",
        "qdrant.internal",
        "https://localhost:6333",
        "qdrant.cloud.example",
        "prod-qdrant",
        "staging-qdrant",
    ],
)
def test_ensure_localhost_rejects_0_0_0_0_private_ip_domain_and_cloud_url(
    host: str,
) -> None:
    with pytest.raises(reset.ResetRefused):
        reset.ensure_localhost(host)


def test_ensure_env_flag_requires_exact_value() -> None:
    reset.ensure_env_flag(_env_enabled())

    for env in ({}, {reset.LOCAL_RESET_ENV_VAR: "true"}, {reset.LOCAL_RESET_ENV_VAR: "0"}):
        with pytest.raises(reset.ResetRefused):
            reset.ensure_env_flag(env)


def test_destructive_reset_requires_env_flag_and_long_confirmation() -> None:
    with pytest.raises(reset.ResetRefused, match=reset.LOCAL_RESET_ENV_VAR):
        reset.assert_destructive_reset_allowed(
            env={},
            confirmed=True,
            host="localhost",
        )
    with pytest.raises(reset.ResetRefused, match="confirmation"):
        reset.assert_destructive_reset_allowed(
            env=_env_enabled(),
            confirmed=False,
            host="localhost",
        )


@pytest.mark.asyncio
async def test_dry_run_does_not_require_env_flag_but_still_requires_localhost() -> None:
    client = FakeResetClient(["quimera_knowledge"])
    report = await reset.run_reset(
        client=client,
        host="localhost",
        dry_run=True,
        confirmed=False,
        recreate_benchmark=False,
        benchmark_collection=None,
        env={},
    )

    assert report.dry_run is True
    assert client.deleted == []
    with pytest.raises(reset.ResetRefused):
        await reset.run_reset(
            client=client,
            host="qdrant.cloud.example",
            dry_run=True,
            confirmed=False,
            recreate_benchmark=False,
            benchmark_collection=None,
            env={},
        )


def test_is_deletable_exact_allowed_names() -> None:
    assert reset.is_deletable_collection("openclaw_knowledge")
    assert reset.is_deletable_collection("quimera_knowledge")
    assert reset.is_deletable_collection("quimera_knowledge_v2")


def test_is_deletable_allowed_prefixes() -> None:
    for prefix in reset.PREFIX_DELETE_ALLOWED:
        assert reset.is_deletable_collection(f"{prefix}abc")


def test_is_deletable_rejects_substring_match() -> None:
    assert not reset.is_deletable_collection("my_quimera_knowledge_copy")
    assert not reset.is_deletable_collection("archive_q18_benchmark_old")
    assert not reset.is_deletable_collection("contains_smoke_inside")


def test_collection_with_null_byte_rejected_in_is_deletable() -> None:
    with pytest.raises(ValueError, match="null bytes"):
        reset.is_deletable_collection("q18_smoke_\x00bad")


def test_prod_prefixed_benchmark_not_deletable() -> None:
    assert not reset.is_deletable_collection("prod_q18_benchmark_x")


def test_allowed_reset_collections_contract_is_explicit() -> None:
    assert reset.EXPLICIT_DELETE_ALLOWED == frozenset(
        {
            "openclaw_knowledge",
            "quimera_knowledge",
            "quimera_knowledge_v2",
        }
    )


def test_prefix_delete_allowed_contract_is_explicit() -> None:
    assert reset.PREFIX_DELETE_ALLOWED == (
        "q18_benchmark_",
        "q18_smoke_",
        "quimera_benchmark_",
        "quimera_hybrid_smoke_",
        "gw07_synthetic_rag_",
    )


def test_no_wildcard_allowed() -> None:
    assert "*" not in reset.EXPLICIT_DELETE_ALLOWED
    assert "*" not in reset.PREFIX_DELETE_ALLOWED
    assert not reset.is_deletable_collection("*")


def test_plan_reset_uses_only_existing_allowed_collections() -> None:
    plan = reset.plan_reset(
        host="localhost",
        existing_collections=["quimera_knowledge", "not_allowed", "q18_smoke_a"],
        dry_run=True,
        confirmed=False,
        recreate_benchmark=False,
        benchmark_collection=None,
    )

    assert plan.delete_targets == ("q18_smoke_a", "quimera_knowledge")


def test_plan_reset_sorts_deterministically() -> None:
    plan = reset.plan_reset(
        host="localhost",
        existing_collections=["quimera_knowledge_v2", "q18_benchmark_b", "q18_benchmark_a"],
        dry_run=True,
        confirmed=False,
        recreate_benchmark=False,
        benchmark_collection=None,
    )

    assert plan.collections_before == (
        "q18_benchmark_a",
        "q18_benchmark_b",
        "quimera_knowledge_v2",
    )
    assert plan.delete_targets == plan.collections_before


def test_plan_reset_skips_unknown_collections() -> None:
    plan = reset.plan_reset(
        host="localhost",
        existing_collections=["important_manual_collection", "quimera_knowledge"],
        dry_run=True,
        confirmed=False,
        recreate_benchmark=False,
        benchmark_collection=None,
    )

    assert plan.delete_targets == ("quimera_knowledge",)


def test_plan_reset_only_uses_collection_names_no_schema_payload() -> None:
    plan = reset.plan_reset(
        host="localhost",
        existing_collections=[" q18_smoke_a ", "manual"],
        dry_run=True,
        confirmed=False,
        recreate_benchmark=False,
        benchmark_collection=None,
    )

    assert plan.collections_before == ("manual", "q18_smoke_a")
    assert not hasattr(plan, "payload")
    assert not hasattr(plan, "vectors")


@pytest.mark.asyncio
async def test_run_reset_dry_run_does_not_call_delete() -> None:
    client = FakeResetClient(["quimera_knowledge", "manual"])

    await reset.run_reset(
        client=client,
        host="localhost",
        dry_run=True,
        confirmed=False,
        recreate_benchmark=False,
        benchmark_collection=None,
        env={},
    )

    assert client.deleted == []


@pytest.mark.asyncio
async def test_dry_run_report_lists_would_delete() -> None:
    client = FakeResetClient(["quimera_knowledge", "manual"])
    report = await reset.run_reset(
        client=client,
        host="localhost",
        dry_run=True,
        confirmed=False,
        recreate_benchmark=False,
        benchmark_collection=None,
        env={},
    )

    assert report.delete_targets == ("quimera_knowledge",)
    assert report.deleted == ()
    assert report.skipped == ("manual",)


def test_dry_run_is_default_in_parse_args() -> None:
    args = reset.parse_args([])

    assert args.dry_run is True
    assert args.confirmed is False


def test_execute_flag_switches_dry_run_false() -> None:
    args = reset.parse_args(["--execute"])

    assert args.dry_run is False


def test_parse_args_confirmed_defaults_false() -> None:
    args = reset.parse_args([])

    assert args.confirmed is False


@pytest.mark.asyncio
async def test_dry_run_outputs_safe_json(capsys: pytest.CaptureFixture[str]) -> None:
    client = FakeResetClient(["quimera_knowledge", "manual"])
    exit_code = await reset.async_main([], client=client, env={})
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert payload["dry_run"] is True
    assert payload["delete_targets"] == ["quimera_knowledge"]


@pytest.mark.asyncio
async def test_execute_deletes_only_allowed_existing_collections() -> None:
    client = FakeResetClient(["manual", "quimera_knowledge", "q18_smoke_a"])

    report = await reset.run_reset(
        client=client,
        host="localhost",
        dry_run=False,
        confirmed=True,
        recreate_benchmark=False,
        benchmark_collection=None,
        env=_env_enabled(),
    )

    assert report.deleted == ("q18_smoke_a", "quimera_knowledge")
    assert client.collections == ["manual"]


@pytest.mark.asyncio
async def test_execute_requires_both_env_and_flag() -> None:
    client = FakeResetClient(["quimera_knowledge"])

    with pytest.raises(reset.ResetRefused):
        await reset.run_reset(
            client=client,
            host="localhost",
            dry_run=False,
            confirmed=True,
            recreate_benchmark=False,
            benchmark_collection=None,
            env={},
        )
    with pytest.raises(reset.ResetRefused):
        await reset.run_reset(
            client=client,
            host="localhost",
            dry_run=False,
            confirmed=False,
            recreate_benchmark=False,
            benchmark_collection=None,
            env=_env_enabled(),
        )


@pytest.mark.asyncio
async def test_execute_remote_host_blocked_even_with_env_and_flag() -> None:
    client = FakeResetClient(["quimera_knowledge"])

    with pytest.raises(reset.ResetRefused):
        await reset.run_reset(
            client=client,
            host="qdrant.cloud.example",
            dry_run=False,
            confirmed=True,
            recreate_benchmark=False,
            benchmark_collection=None,
            env=_env_enabled(),
        )


@pytest.mark.asyncio
async def test_execute_with_no_deletable_collections_is_ok() -> None:
    client = FakeResetClient(["manual"])
    report = await reset.run_reset(
        client=client,
        host="localhost",
        dry_run=False,
        confirmed=True,
        recreate_benchmark=False,
        benchmark_collection=None,
        env=_env_enabled(),
    )

    assert report.deleted == ()
    assert report.collections_after == ("manual",)


@pytest.mark.asyncio
async def test_reset_is_idempotent_with_fake_client() -> None:
    client = FakeResetClient(["quimera_knowledge"])

    first = await reset.run_reset(
        client=client,
        host="localhost",
        dry_run=False,
        confirmed=True,
        recreate_benchmark=False,
        benchmark_collection=None,
        env=_env_enabled(),
    )
    second = await reset.run_reset(
        client=client,
        host="localhost",
        dry_run=False,
        confirmed=True,
        recreate_benchmark=False,
        benchmark_collection=None,
        env=_env_enabled(),
    )

    assert first.deleted == ("quimera_knowledge",)
    assert second.deleted == ()


def test_validate_benchmark_collection_requires_q18_prefix() -> None:
    assert (
        reset.validate_benchmark_collection_name("q18_benchmark_hybrid_local")
        == "q18_benchmark_hybrid_local"
    )
    with pytest.raises(ValueError, match="q18_benchmark_"):
        reset.validate_benchmark_collection_name("quimera_benchmark_wrong")
    with pytest.raises(ValueError, match="unsafe"):
        reset.validate_benchmark_collection_name("q18_benchmark_bad/name")


def test_recreate_benchmark_requires_explicit_flag() -> None:
    plan = reset.plan_reset(
        host="localhost",
        existing_collections=[],
        dry_run=True,
        confirmed=False,
        recreate_benchmark=False,
        benchmark_collection=reset.DEFAULT_BENCHMARK_COLLECTION,
    )

    assert plan.recreate_benchmark is False


def test_recreate_benchmark_uses_only_validated_name() -> None:
    plan = reset.plan_reset(
        host="localhost",
        existing_collections=[],
        dry_run=True,
        confirmed=False,
        recreate_benchmark=True,
        benchmark_collection="q18_benchmark_valid",
    )

    assert plan.benchmark_collection == "q18_benchmark_valid"


@pytest.mark.asyncio
async def test_recreate_benchmark_dry_run_does_not_create() -> None:
    client = FakeResetClient([])
    await reset.run_reset(
        client=client,
        host="localhost",
        dry_run=True,
        confirmed=False,
        recreate_benchmark=True,
        benchmark_collection="q18_benchmark_valid",
        env={},
    )

    assert client.created == []


@pytest.mark.asyncio
async def test_recreate_benchmark_execute_creates_once() -> None:
    client = FakeResetClient(["q18_benchmark_valid"])
    report = await reset.run_reset(
        client=client,
        host="localhost",
        dry_run=False,
        confirmed=True,
        recreate_benchmark=True,
        benchmark_collection="q18_benchmark_valid",
        env=_env_enabled(),
    )

    assert client.deleted == ["q18_benchmark_valid"]
    assert client.created == ["q18_benchmark_valid"]
    assert report.recreated == ("q18_benchmark_valid",)


def test_reset_report_to_safe_dict_exact_keys() -> None:
    report = reset.ResetReport(
        schema_version=reset.RESET_REPORT_SCHEMA_VERSION,
        dry_run=True,
        host="localhost",
        confirmed=False,
        env_flag_present=False,
        collections_before=("manual",),
        delete_targets=(),
        deleted=(),
        skipped=("manual",),
        collections_after=("manual",),
        recreated=(),
        errors=(),
    )

    assert tuple(report.to_safe_dict()) == (
        "schema_version",
        "dry_run",
        "host",
        "confirmed",
        "env_flag_present",
        "collections_before",
        "delete_targets",
        "deleted",
        "skipped",
        "collections_after",
        "recreated",
        "errors",
    )


@pytest.mark.asyncio
async def test_report_contains_before_targets_deleted_skipped_after() -> None:
    client = FakeResetClient(["manual", "quimera_knowledge"])
    report = await reset.run_reset(
        client=client,
        host="localhost",
        dry_run=False,
        confirmed=True,
        recreate_benchmark=False,
        benchmark_collection=None,
        env=_env_enabled(),
    )
    as_dict = report.to_safe_dict()

    assert as_dict["collections_before"] == ["manual", "quimera_knowledge"]
    assert as_dict["delete_targets"] == ["quimera_knowledge"]
    assert as_dict["deleted"] == ["quimera_knowledge"]
    assert as_dict["skipped"] == ["manual"]
    assert as_dict["collections_after"] == ["manual"]


def test_report_has_no_payload_vector_embedding_text() -> None:
    keys = reset.ResetReport(
        schema_version=reset.RESET_REPORT_SCHEMA_VERSION,
        dry_run=True,
        host="localhost",
        confirmed=False,
        env_flag_present=False,
        collections_before=(),
        delete_targets=(),
        deleted=(),
        skipped=(),
        collections_after=(),
        recreated=(),
        errors=(),
    ).to_safe_dict()

    forbidden = {
        "documents",
        "embedding",
        "payload",
        "points",
        "schema",
        "secrets",
        "text",
        "vector",
        "vectors",
    }
    assert forbidden.isdisjoint(keys)


def test_report_forbidden_terms_extended() -> None:
    keys = reset.ResetReport(
        schema_version=reset.RESET_REPORT_SCHEMA_VERSION,
        dry_run=True,
        host="localhost",
        confirmed=False,
        env_flag_present=False,
        collections_before=(),
        delete_targets=(),
        deleted=(),
        skipped=(),
        collections_after=(),
        recreated=(),
        errors=(),
    ).to_safe_dict()

    forbidden = {"points", "documents", "secrets"}
    assert forbidden.isdisjoint(keys)


def test_report_json_parseable() -> None:
    report = reset.ResetReport(
        schema_version=reset.RESET_REPORT_SCHEMA_VERSION,
        dry_run=True,
        host="localhost",
        confirmed=False,
        env_flag_present=False,
        collections_before=(),
        delete_targets=(),
        deleted=(),
        skipped=(),
        collections_after=(),
        recreated=(),
        errors=(),
    )

    assert json.loads(json.dumps(report.to_safe_dict()))["dry_run"] is True


def test_error_stderr_is_sanitized_class_name_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = reset.main(["--host", "qdrant.cloud.example"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.err == "qdrant local reset failed: ResetRefused\n"
    assert "qdrant.cloud.example" not in captured.err


def test_stdout_empty_on_error(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = reset.main(["--host", "https://localhost:6333"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""


def test_script_has_no_hardcoded_delete_collection_names_outside_allowlist() -> None:
    assert reset.EXPLICIT_DELETE_ALLOWED == frozenset(
        {
            "openclaw_knowledge",
            "quimera_knowledge",
            "quimera_knowledge_v2",
        }
    )


def test_script_does_not_delete_by_substring() -> None:
    assert not reset.is_deletable_collection("before_quimera_knowledge_after")
    assert not reset.is_deletable_collection("before_q18_smoke_after")


def test_script_has_no_wildcard_delete() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "delete_collection(\"*\")" not in source
    assert "delete_collection('*')" not in source


def test_script_does_not_call_recreate_collection() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr != "recreate_collection"


def test_script_does_not_touch_payload_schema_vectors() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    forbidden_calls = {
        "create_collection",
        "create_payload_index",
        "delete_payload",
        "delete_payload_index",
        "delete_vectors",
        "get_collection",
        "query_points",
        "retrieve",
        "scroll",
        "set_payload",
        "update_collection",
        "upload_collection",
        "upsert",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden_calls


def test_script_does_not_reference_remote_qdrant_urls() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "https://cloud.qdrant.io" not in source
    assert "qdrant.io" not in source


def test_script_does_not_import_qdrant_client_at_module_level() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))

    for node in tree.body:
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] != "qdrant_client" for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module.split(".")[0] != "qdrant_client"


@pytest.mark.asyncio
async def test_main_dry_run_default_with_fake_client_if_dependency_injection_available(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakeResetClient(["quimera_knowledge"])
    exit_code = await reset.async_main([], client=client, env={})
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out)["dry_run"] is True
    assert client.closed is True


@pytest.mark.asyncio
async def test_main_execute_requires_env_and_flag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakeResetClient(["quimera_knowledge"])

    with pytest.raises(reset.ResetRefused):
        await reset.async_main(["--execute"], client=client, env={})

    assert capsys.readouterr().out == ""


def test_main_legacy_free_error_message(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = reset.main(["--host", "prod-qdrant"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "quimera_knowledge" not in captured.err
    assert "openclaw_knowledge" not in captured.err


def test_reset_policy_document_exists_and_lists_required_gates() -> None:
    text = POLICY_PATH.read_text(encoding="utf-8")

    assert "QDRANT_LOCAL_RESET=1" in text
    assert reset.DESTRUCTIVE_CONFIRMATION_FLAG in text
    assert "Dry-run" in text
