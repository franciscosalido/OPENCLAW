from __future__ import annotations

import json
from io import StringIO
from typing import Any

import pytest

from scripts import check_postgres_readiness as readiness


class FakeReadinessConnection:
    def __init__(
        self,
        *,
        database: str = "quimera",
        extensions: set[str] | None = None,
        migration_head: str = "018_enable_library_extensions",
        readonly_role_exists: bool = True,
        fail_write: bool = False,
    ) -> None:
        self.database = database
        self.extensions = extensions or set(readiness.REQUIRED_EXTENSIONS)
        self.migration_head = migration_head
        self.readonly_role_exists = readonly_role_exists
        self.fail_write = fail_write
        self.closed = False

    async def fetchval(self, query: str, *args: object) -> Any:
        if "current_database()" in query:
            return self.database
        if "pg_extension" in query:
            return args[0] in self.extensions
        if "schema_migrations" in query:
            return self.migration_head
        if "count(*) FROM quimera_readiness_write_test" in query:
            return 1
        if "pg_roles" in query:
            return self.readonly_role_exists
        raise AssertionError(f"unexpected query: {query}")

    async def execute(self, query: str, *args: object) -> str:
        del args
        if self.fail_write and "INSERT INTO quimera_readiness_write_test" in query:
            raise RuntimeError("write failed")
        return "OK"

    async def close(self) -> None:
        self.closed = True


async def _connect_ok(**_kwargs: object) -> FakeReadinessConnection:
    return FakeReadinessConnection()


def _run_main(
    *,
    connect: readiness.ConnectFactory = _connect_ok,
    env: dict[str, str] | None = None,
    argv: list[str] | None = None,
) -> tuple[int, dict[str, str], str]:
    stdout = StringIO()
    code = readiness.main(
        ["--json"] if argv is None else argv,
        env=env or {"QUIMERA_POSTGRES_DSN": "postgresql://user:secret@db/quimera"},
        connect=connect,
        stdout=stdout,
    )
    output = stdout.getvalue()
    return code, json.loads(output), output


def test_success_json_contract_has_exact_required_fields() -> None:
    code, report, output = _run_main()

    assert code == 0
    assert tuple(report) == readiness.READINESS_FIELDS
    assert set(report.values()) == {"ok"}
    assert output.strip().startswith("{")


@pytest.mark.parametrize("missing_extension", ["pg_trgm", "btree_gin"])
def test_missing_library_extension_fails_exit_one(missing_extension: str) -> None:
    async def connect(**_kwargs: object) -> FakeReadinessConnection:
        return FakeReadinessConnection(
            extensions={str(name) for name in readiness.REQUIRED_EXTENSIONS}
            - {missing_extension}
        )

    code, report, _ = _run_main(connect=connect)

    assert code == 1
    assert report[missing_extension] == "fail"


def test_migration_head_below_018_fails() -> None:
    async def connect(**_kwargs: object) -> FakeReadinessConnection:
        return FakeReadinessConnection(migration_head="017_enable_vector_extension")

    code, report, _ = _run_main(connect=connect)

    assert code == 1
    assert report["migration_head"] == "fail"


def test_missing_readonly_role_fails() -> None:
    async def connect(**_kwargs: object) -> FakeReadinessConnection:
        return FakeReadinessConnection(readonly_role_exists=False)

    code, report, _ = _run_main(connect=connect)

    assert code == 1
    assert report["readonly_role"] == "fail"


def test_write_probe_failure_is_critical() -> None:
    async def connect(**_kwargs: object) -> FakeReadinessConnection:
        return FakeReadinessConnection(fail_write=True)

    code, report, _ = _run_main(connect=connect)

    assert code == 1
    assert report["write_test"] == "fail"


def test_connection_error_does_not_leak_dsn_password_host_or_traceback() -> None:
    async def connect(**_kwargs: object) -> FakeReadinessConnection:
        raise RuntimeError(
            "could not connect to postgresql://user:secret@private-host/quimera\n"
            "Traceback (most recent call last)"
        )

    code, report, output = _run_main(connect=connect)

    assert code == 1
    assert set(report.values()) == {"fail"}
    assert "secret" not in output
    assert "private-host" not in output
    assert "postgresql://" not in output
    assert "Traceback" not in output


def test_database_name_is_derived_from_existing_dsn_env() -> None:
    config = readiness.load_config(
        {"TEST_POSTGRES_DSN": "postgresql://user:secret@127.0.0.1:5432/finlib"}
    )

    assert config.expected_database == "finlib"


@pytest.mark.parametrize("head", ["018_enable_library_extensions", "019_next"])
def test_migration_head_018_or_newer_is_ready(head: str) -> None:
    assert readiness._migration_number(head) >= readiness.MINIMUM_MIGRATION_HEAD
