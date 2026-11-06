from __future__ import annotations

import ast
import json
from io import StringIO
from pathlib import Path
from typing import Any

from scripts import check_finlib_readiness as readiness


SCRIPT = Path("scripts/check_finlib_readiness.py")


class FakeFinlibReadinessConnection:
    def __init__(
        self,
        *,
        migration_head: str = readiness.EXPECTED_MIGRATION_HEAD,
        missing_relations: set[str] | None = None,
        retention_jobs: int = 0,
    ) -> None:
        self.migration_head = migration_head
        self.missing_relations = missing_relations or set()
        self.retention_jobs = retention_jobs
        self.closed = False

    async def fetchval(self, query: str, *args: object) -> Any:
        if "SELECT TRUE" in query:
            return True
        if "current_database()" in query:
            return "quimera_test"
        if "pg_extension" in query:
            return True
        if "schema_migrations" in query:
            return self.migration_head
        if "to_regclass" in query:
            return str(args[0]) not in self.missing_relations
        if "timescaledb_information.hypertable_compression_settings" in query:
            return True
        if "timescaledb_information.jobs" in query:
            return self.retention_jobs
        raise AssertionError(f"unexpected query: {query}")

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        del query, args
        return []

    async def close(self) -> None:
        self.closed = True


async def _connect_ok(**_kwargs: object) -> FakeFinlibReadinessConnection:
    return FakeFinlibReadinessConnection()


def _run(
    *,
    connect: readiness.ConnectFactory = _connect_ok,
    argv: list[str] | None = None,
) -> tuple[int, dict[str, object], str]:
    stdout = StringIO()
    code = readiness.main(
        ["--json"] if argv is None else argv,
        env={"TEST_POSTGRES_DSN": "postgresql://user:secret@private-host/db"},
        connect=connect,
        stdout=stdout,
    )
    output = stdout.getvalue()
    return code, json.loads(output), output


def test_readiness_success_emits_ready_json_contract() -> None:
    code, report, output = _run()

    assert code == 0
    assert report["status"] == "READY"
    assert report["ready_for_data_agents"] is True
    assert report["failed_checks"] == []
    assert "kronos_input_ready" in report
    assert output.strip().startswith("{")


def test_readiness_failure_is_exit_one_and_sanitized() -> None:
    async def connect(**_kwargs: object) -> FakeFinlibReadinessConnection:
        raise RuntimeError(
            "postgresql://user:secret@private-host/db Traceback real failure"
        )

    code, report, output = _run(connect=connect)

    assert code == 1
    assert report["status"] == "BLOCKED"
    assert "secret" not in output
    assert "private-host" not in output
    assert "postgresql://" not in output
    assert "Traceback" not in output


def test_critical_missing_table_blocks_readiness() -> None:
    async def connect(**_kwargs: object) -> FakeFinlibReadinessConnection:
        return FakeFinlibReadinessConnection(missing_relations={"audit_agent_writes"})

    code, report, _ = _run(connect=connect)

    assert code == 1
    assert report["status"] == "BLOCKED"
    failed_checks = report["failed_checks"]
    assert isinstance(failed_checks, list)
    assert "schemas.audit" in failed_checks


def test_destructive_retention_blocks_readiness() -> None:
    async def connect(**_kwargs: object) -> FakeFinlibReadinessConnection:
        return FakeFinlibReadinessConnection(retention_jobs=1)

    code, report, _ = _run(connect=connect)

    assert code == 1
    failed_checks = report["failed_checks"]
    assert isinstance(failed_checks, list)
    assert "destructive_retention" in failed_checks


def test_script_has_required_cli_flags() -> None:
    parsed = readiness.parse_args(
        ["--json", "--timeout-seconds", "1", "--require-kronos-input-ready"]
    )

    assert parsed.json is True
    assert parsed.timeout_seconds == 1
    assert parsed.require_kronos_input_ready is True


def test_script_static_contract_is_read_only_and_local_only() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()
    forbidden_tokens = (
        "delete from",
        "truncate",
        "drop table",
        "qdrant_client",
        "kronos",
        "openai",
        "anthropic",
        "litellm",
        "requests",
        "httpx",
    )

    for token in forbidden_tokens:
        if token == "kronos":
            assert '"kronos_input_ready"' in text
            continue
        assert token not in text
    assert "timescaledb_information.jobs" in text
    assert "proc_name = 'policy_retention'" in text
    assert "proc_name = 'drop_chunks'" in text


def test_script_does_not_import_qdrant_kronos_or_llm_clients() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert not any(name.startswith("qdrant") for name in imports)
    assert not any("kronos" in name for name in imports)
    assert imports.isdisjoint({"openai", "anthropic", "litellm", "httpx", "requests"})
