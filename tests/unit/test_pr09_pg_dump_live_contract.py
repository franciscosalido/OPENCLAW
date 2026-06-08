from __future__ import annotations

from tests.integration.test_pr09_pg_dump_restore_verify_live import (
    _postgres_unavailable_output,
)


def test_pg_dump_live_contract_treats_unreachable_postgres_as_sandbox_skip() -> None:
    output = (
        'pg_dump: error: connection to server at "host.docker.internal" '
        "(192.168.65.2), port 5432 failed: Connection refused\n"
        "Is the server running on that host and accepting TCP/IP connections?"
    )

    assert _postgres_unavailable_output(output) is True


def test_pg_dump_live_contract_does_not_hide_version_mismatch() -> None:
    output = (
        "pg_dump: error: server version: 18.4; "
        "pg_dump version: 15.18\n"
        "pg_dump: error: aborting because of server version mismatch"
    )

    assert _postgres_unavailable_output(output) is False
