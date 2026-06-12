from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from asyncpg.exceptions import (  # type: ignore[import-untyped]
    CheckViolationError,
    ForeignKeyViolationError,
    InsufficientPrivilegeError,
    NotNullViolationError,
    RaiseError,
)

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.timescale import is_timescale_available
from tests.integration.postgres_isolated_db import isolated_postgres_client


pytestmark = pytest.mark.integration


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    async with isolated_postgres_client(dsn, prefix="finlib_audit") as client:
        yield client


async def _migrate(client: PostgresClient) -> None:
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for FINLIB audit tests")
    try:
        version = await client.pool.fetchval("SELECT uuid_extract_version(uuidv7())")
    except Exception as exc:
        raise AssertionError("PostgreSQL 18 uuidv7() is required") from exc
    assert version == 7
    await run_migrations(client)


async def _create_run(client: PostgresClient) -> UUID:
    run_id = await client.pool.fetchval(
        """
        INSERT INTO ops_ingestion_runs(source_id, agent_id, mode, status, trace_id)
        VALUES('b3_cotacoes_historicas', 'finlib-audit-test', 'dry_run', 'created', uuidv7())
        RETURNING run_id
        """
    )
    return UUID(str(run_id))


async def _insert_audit_write(
    client: PostgresClient,
    *,
    run_id: UUID | None,
    agent_id: str = "finlib-audit-test",
    repository: str = "MacroRepository",
    target_table: str = "macro_observations",
    operation: str = "bulk_upsert",
    row_count: int = 2,
    batch_hash: str = "sha256:synthetic-batch",
) -> UUID:
    audit_id = await client.pool.fetchval(
        """
        INSERT INTO audit_agent_writes(
            trace_id,
            run_id,
            agent_id,
            repository,
            target_table,
            operation,
            row_count,
            batch_hash,
            metadata
        )
        VALUES(uuidv7(), $1, $2, $3, $4, $5, $6, $7, '{}'::jsonb)
        RETURNING audit_id
        """,
        run_id,
        agent_id,
        repository,
        target_table,
        operation,
        row_count,
        batch_hash,
    )
    return UUID(str(audit_id))


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def test_audit_agent_writes_insert_works_and_uses_uuidv7(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    audit_id = await _insert_audit_write(postgres_client, run_id=run_id)

    row = await postgres_client.pool.fetchrow(
        """
        SELECT audit_id, run_id, operation, row_count, metadata
        FROM audit_agent_writes
        WHERE audit_id = $1
        """,
        audit_id,
    )

    assert row is not None
    assert UUID(str(row["audit_id"])) == audit_id
    assert UUID(str(row["run_id"])) == run_id
    assert row["operation"] == "bulk_upsert"
    assert row["row_count"] == 2
    assert row["metadata"] == {}
    assert (
        await postgres_client.pool.fetchval(
            "SELECT uuid_extract_version($1::uuid)",
            audit_id,
        )
        == 7
    )


async def test_audit_agent_writes_update_and_delete_are_blocked_by_trigger(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    audit_id = await _insert_audit_write(
        postgres_client,
        run_id=await _create_run(postgres_client),
    )

    with pytest.raises(RaiseError, match="append-only"):
        await postgres_client.pool.execute(
            """
            UPDATE audit_agent_writes
            SET row_count = row_count + 1
            WHERE audit_id = $1
            """,
            audit_id,
        )

    with pytest.raises(RaiseError, match="append-only"):
        await postgres_client.pool.execute(
            "DELETE FROM audit_agent_writes WHERE audit_id = $1",
            audit_id,
        )

    assert (
        await postgres_client.pool.fetchval(
            "SELECT count(*) FROM audit_agent_writes WHERE audit_id = $1",
            audit_id,
        )
        == 1
    )


async def test_audit_agent_writes_trigger_and_function_exist(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    trigger_exists = await postgres_client.pool.fetchval(
        """
        SELECT EXISTS(
            SELECT 1
            FROM pg_trigger
            WHERE tgname = 'trg_audit_agent_writes_append_only'
              AND NOT tgisinternal
        )
        """
    )
    function_exists = await postgres_client.pool.fetchval(
        """
        SELECT EXISTS(
            SELECT 1
            FROM pg_proc
            WHERE proname = 'prevent_audit_agent_writes_mutation'
        )
        """
    )

    assert trigger_exists is True
    assert function_exists is True


@pytest.mark.parametrize(
    "operation",
    ("insert", "update", "upsert", "bulk_insert", "bulk_upsert"),
)
async def test_audit_agent_writes_accepts_expected_operations(
    postgres_client: PostgresClient,
    operation: str,
) -> None:
    await _migrate(postgres_client)

    audit_id = await _insert_audit_write(
        postgres_client,
        run_id=None,
        operation=operation,
        row_count=0,
        batch_hash=f"sha256:{operation}",
    )

    assert audit_id


async def test_audit_agent_writes_rejects_invalid_and_delete_operations(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    for operation in ("delete", "merge"):
        with pytest.raises(CheckViolationError):
            await _insert_audit_write(
                postgres_client,
                run_id=None,
                operation=operation,
                batch_hash=f"sha256:{operation}",
            )


async def test_audit_agent_writes_rejects_bad_metadata_and_row_count(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO audit_agent_writes(
                trace_id, agent_id, repository, target_table, operation,
                row_count, batch_hash, metadata
            )
            VALUES(
                uuidv7(), 'agent', 'Repo', 'target_table', 'insert',
                1, 'sha256:bad-json', '[]'::jsonb
            )
            """
        )

    with pytest.raises(CheckViolationError):
        await _insert_audit_write(
            postgres_client,
            run_id=None,
            row_count=-1,
            batch_hash="sha256:negative-row-count",
        )


@pytest.mark.parametrize(
    ("field_name", "sql_value"),
    (
        pytest.param("agent_id", "E'\\t'", id="tab-agent-id"),
        pytest.param("repository", "E'\\n'", id="newline-repository"),
        pytest.param("target_table", "E'\\r'", id="carriage-return-target-table"),
        pytest.param("batch_hash", "'   '", id="space-batch-hash"),
    ),
)
async def test_audit_agent_writes_rejects_whitespace_only_identity_fields(
    postgres_client: PostgresClient,
    field_name: str,
    sql_value: str,
) -> None:
    await _migrate(postgres_client)

    values = {
        "agent_id": "'agent'",
        "repository": "'Repo'",
        "target_table": "'target_table'",
        "batch_hash": "'sha256:batch'",
    }
    values[field_name] = sql_value

    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            f"""
            INSERT INTO audit_agent_writes(
                trace_id, agent_id, repository, target_table, operation,
                row_count, batch_hash
            )
            VALUES(
                uuidv7(), {values["agent_id"]}, {values["repository"]},
                {values["target_table"]}, 'insert', 1, {values["batch_hash"]}
            )
            """
        )


async def test_audit_agent_writes_rejects_null_trace_id_and_unknown_run_id(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    with pytest.raises(NotNullViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO audit_agent_writes(
                trace_id, agent_id, repository, target_table, operation,
                row_count, batch_hash
            )
            VALUES(NULL, 'agent', 'Repo', 'target_table', 'insert', 1, 'sha256:null-trace')
            """
        )

    with pytest.raises(ForeignKeyViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO audit_agent_writes(
                trace_id, run_id, agent_id, repository, target_table,
                operation, row_count, batch_hash
            )
            VALUES(
                uuidv7(), uuidv7(), 'agent', 'Repo', 'target_table',
                'insert', 1, 'sha256:missing-run'
            )
            """
        )


async def test_public_acl_does_not_allow_update_or_delete(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    public_write_acl_exists = await postgres_client.pool.fetchval(
        """
        SELECT EXISTS(
            SELECT 1
            FROM pg_class AS c
            CROSS JOIN LATERAL aclexplode(
                coalesce(c.relacl, acldefault('r', c.relowner))
            ) AS acl
            WHERE c.oid = 'public.audit_agent_writes'::regclass
              AND acl.grantee = 0
              AND acl.privilege_type IN ('UPDATE', 'DELETE')
        )
        """
    )

    assert public_write_acl_exists is False


async def test_non_owner_role_update_delete_denied_when_role_creation_is_available(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    can_create_role = await postgres_client.pool.fetchval(
        """
        SELECT rolsuper OR rolcreaterole
        FROM pg_roles
        WHERE rolname = current_user
        """
    )
    if not can_create_role:
        pytest.skip(
            "non-owner application role not available; trigger enforcement is "
            "authoritative in current single-role setup"
        )

    role_name = f"quimera_test_audit_role_{uuid4().hex}"
    quoted_role = _quote_ident(role_name)
    current_user = str(await postgres_client.pool.fetchval("SELECT current_user"))
    quoted_current_user = _quote_ident(current_user)
    audit_id: UUID | None = None
    role_created = False
    try:
        await postgres_client.pool.execute(f"CREATE ROLE {quoted_role} NOLOGIN")
        role_created = True
        await postgres_client.pool.execute(
            f"GRANT {quoted_role} TO {quoted_current_user}"
        )
        await postgres_client.pool.execute(
            f"GRANT USAGE ON SCHEMA public TO {quoted_role}"
        )
        await postgres_client.pool.execute(
            f"GRANT SELECT, INSERT ON audit_agent_writes TO {quoted_role}"
        )

        async with postgres_client.pool.acquire() as conn:
            try:
                await conn.execute(f"SET ROLE {quoted_role}")
                audit_id_raw = await conn.fetchval(
                    """
                    INSERT INTO audit_agent_writes(
                        trace_id, agent_id, repository, target_table, operation,
                        row_count, batch_hash
                    )
                    VALUES(uuidv7(), 'agent', 'Repo', 'target_table', 'insert', 1, 'sha256:role')
                    RETURNING audit_id
                    """
                )
                audit_id = UUID(str(audit_id_raw))

                with pytest.raises(InsufficientPrivilegeError):
                    await conn.execute(
                        """
                        UPDATE audit_agent_writes
                        SET row_count = 2
                        WHERE audit_id = $1
                        """,
                        audit_id,
                    )
                with pytest.raises(InsufficientPrivilegeError):
                    await conn.execute(
                        "DELETE FROM audit_agent_writes WHERE audit_id = $1",
                        audit_id,
                    )
            finally:
                await conn.execute("RESET ROLE")
    finally:
        await postgres_client.pool.execute("RESET ROLE")
        if role_created:
            await postgres_client.pool.execute(f"DROP OWNED BY {quoted_role}")
            await postgres_client.pool.execute(
                f"REVOKE SELECT, INSERT ON audit_agent_writes FROM {quoted_role}"
            )
            await postgres_client.pool.execute(
                f"REVOKE USAGE ON SCHEMA public FROM {quoted_role}"
            )
            await postgres_client.pool.execute(
                f"REVOKE {quoted_role} FROM {quoted_current_user}"
            )
            await postgres_client.pool.execute(f"DROP ROLE IF EXISTS {quoted_role}")

    assert audit_id is not None
