from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from backend.finlib.repositories import (
    AuditContext,
    BatchWriteResult,
    DataSourceInput,
    OpsRepository,
    OutboxEventInput,
    RunAlreadyFinishedError,
)


SOURCE = Path("backend/finlib/repositories/ops_repository.py")
BASE = Path("backend/finlib/repositories/base.py")


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_ops_repository_public_methods_are_async() -> None:
    for method_name in (
        "register_source",
        "start_run",
        "finish_run",
        "get_watermark",
        "set_watermark",
        "record_quality_check",
        "enqueue_event",
        "poll_events",
    ):
        assert inspect.iscoroutinefunction(getattr(OpsRepository, method_name))


def test_ops_repository_uses_asyncpg_and_no_orm() -> None:
    combined = _source() + BASE.read_text(encoding="utf-8")
    assert "asyncpg" in combined
    for forbidden in ("sqlalchemy", "sqlmodel", "alembic"):
        assert forbidden not in combined.lower()


def test_ops_repository_uses_real_watermark_table_and_monotonic_upsert() -> None:
    source = _source()

    assert "ops_ingestion_watermarks" in source
    assert "ops_watermarks" not in source
    assert "excluded.watermark_ts >= ops_ingestion_watermarks.watermark_ts" in source


def test_poll_events_encapsulates_skip_locked_and_requires_limit() -> None:
    source = _source()

    assert "FOR UPDATE SKIP LOCKED" in source
    assert "status = 'processing'" in source
    with pytest.raises(ValueError, match="limit"):
        OpsRepository(object())._validate_poll_limit(0)


def test_enqueue_event_rejects_level0_payload() -> None:
    repo = OpsRepository(object())

    with pytest.raises(ValueError, match="Level 0"):
        repo._validate_event_payload({"cpf": "00000000000"})


async def test_empty_batch_result_has_no_audit() -> None:
    result = BatchWriteResult.empty()

    assert result == BatchWriteResult(
        attempted=0,
        inserted=0,
        updated=0,
        skipped=0,
        audit_id=None,
    )


def test_dtos_are_named_not_tuple_payloads() -> None:
    source_input = DataSourceInput(
        source_id="test_source",
        kind="internal",
        methodology_limitations="synthetic source for tests",
    )
    event_input = OutboxEventInput(
        event_type="finlib.test",
        aggregate_type="source",
        aggregate_id="test_source",
    )
    audit = AuditContext(
        trace_id="00000000-0000-7000-8000-000000000001",
        agent_id="finlib-test",
        batch_hash="sha256:test",
    )

    assert source_input.source_id == "test_source"
    assert event_input.payload == {}
    assert audit.run_id is None


def test_finish_run_error_type_is_public() -> None:
    assert issubclass(RunAlreadyFinishedError, RuntimeError)
