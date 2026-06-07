"""Safe MCP-callable helpers for working memory."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from backend.mcp.mcp_models import HealthResponse, ToolResponse
from backend.mcp.mcp_safety import (
    validate_limit,
    validate_non_empty_text,
    validate_uuid,
)
from backend.working_memory.cleanup import CleanupService
from backend.working_memory.config import WorkingMemorySettings
from backend.working_memory.models import WorkingMemoryPoint
from backend.working_memory.restore_service import RestoreService
from backend.working_memory.safety import sanitize_metadata, validate_safe_summary
from backend.working_memory.snapshot_service import SnapshotService


class WorkingMemoryStoreLike(Protocol):
    async def upsert_memory_point(self, point: WorkingMemoryPoint) -> str: ...
    async def query_working_memory(
        self,
        *,
        agent_id: str,
        session_id: str,
        query_vector: list[float],
        limit: int = 10,
    ) -> list[dict[str, Any]]: ...


def build_working_memory_health(settings: WorkingMemorySettings) -> dict[str, object]:
    return HealthResponse(
        status="ok" if settings.enabled else "skipped",
        backend="working_memory",
        details={
            "collection": settings.collection_name,
            "vector_name": settings.vector_name,
            "vector_size": settings.vector_size,
            "restore_enabled": settings.restore_enabled,
            "cleanup_enabled": settings.cleanup_enabled,
        },
    ).model_dump()


async def working_memory_upsert(
    *,
    agent_id: str,
    session_id: str,
    memory_kind: str,
    vector: list[float],
    metadata: dict[str, object] | None = None,
    safe_summary: str | None = None,
    settings: WorkingMemorySettings,
    store: WorkingMemoryStoreLike | None,
    task_id: str | None = None,
    topic: str | None = None,
    importance: float = 0.5,
) -> dict[str, object]:
    validate_non_empty_text(agent_id, "agent_id")
    clean_session = validate_uuid(session_id, "session_id")
    if memory_kind not in (
        "turn_summary",
        "agent_state",
        "scratchpad",
        "handoff",
        "tool_observation",
    ):
        raise ValueError("memory_kind is unsupported")
    if len(vector) != settings.vector_size:
        raise ValueError("working memory vector dimension mismatch")
    now = datetime.now(UTC)
    point = WorkingMemoryPoint(
        point_id=f"wm-{uuid4().hex}",
        agent_id=agent_id,
        session_id=UUID(clean_session),
        memory_kind=memory_kind,  # type: ignore[arg-type]
        vector=tuple(vector),
        vector_dim=settings.vector_size,
        recency_ts=now,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(seconds=settings.default_ttl_seconds),
        ttl_seconds=settings.default_ttl_seconds,
        embedding_model="nomic-embed-text",
        task_id=task_id,
        topic=topic,
        importance=importance,
        safe_summary=validate_safe_summary(safe_summary),
        metadata=sanitize_metadata(metadata),
    )
    point_id = (
        await store.upsert_memory_point(point) if store is not None else point.point_id
    )
    return ToolResponse(
        ok=True,
        data={"point_ids": [point_id], "count": 1, "checksum": point.payload_checksum},
    ).model_dump()


async def working_memory_query(
    agent_id: str,
    session_id: str,
    query_vector: list[float],
    *,
    limit: int,
    settings: WorkingMemorySettings,
    store: WorkingMemoryStoreLike | None,
) -> dict[str, object]:
    validate_non_empty_text(agent_id, "agent_id")
    clean_session = validate_uuid(session_id, "session_id")
    validate_limit(limit, maximum=50)
    if len(query_vector) != settings.vector_size:
        raise ValueError("working memory vector dimension mismatch")
    results = (
        await store.query_working_memory(
            agent_id=agent_id,
            session_id=clean_session,
            query_vector=query_vector,
            limit=limit,
        )
        if store is not None
        else []
    )
    return ToolResponse(
        ok=True,
        data={"results": results, "count": len(results), "vectors_exposed": False},
    ).model_dump()


async def working_memory_snapshot(
    agent_id: str,
    session_id: str,
    *,
    snapshot_service: SnapshotService | None,
) -> dict[str, object]:
    validate_non_empty_text(agent_id, "agent_id")
    clean_session = validate_uuid(session_id, "session_id")
    if snapshot_service is None:
        return ToolResponse(
            ok=False, error="working memory snapshot unavailable"
        ).model_dump()
    result = await snapshot_service.create_session_snapshot(
        agent_id=agent_id, session_id=clean_session
    )
    return ToolResponse(ok=True, data=result).model_dump()


async def working_memory_restore(
    agent_id: str,
    session_id: str,
    *,
    settings: WorkingMemorySettings,
    restore_service: RestoreService | None,
) -> dict[str, object]:
    validate_non_empty_text(agent_id, "agent_id")
    clean_session = validate_uuid(session_id, "session_id")
    if not settings.restore_enabled:
        return ToolResponse(
            ok=False, error="working memory restore disabled"
        ).model_dump()
    if restore_service is None:
        return ToolResponse(
            ok=False, error="working memory restore unavailable"
        ).model_dump()
    report = await restore_service.restore_latest_snapshot(
        agent_id=agent_id, session_id=clean_session
    )
    return ToolResponse(
        ok=report.status in {"ok", "warn"}, data=report.to_dict()
    ).model_dump()


async def working_memory_cleanup_expired(
    *,
    settings: WorkingMemorySettings,
    cleanup_service: CleanupService | None,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, object]:
    if not settings.cleanup_enabled:
        return ToolResponse(
            ok=False, error="working memory cleanup disabled"
        ).model_dump()
    if cleanup_service is None:
        return ToolResponse(
            ok=False, error="working memory cleanup unavailable"
        ).model_dump()
    if agent_id is not None:
        validate_non_empty_text(agent_id, "agent_id")
    if session_id is not None:
        validate_uuid(session_id, "session_id")
    result = await cleanup_service.cleanup_expired(
        agent_id=agent_id, session_id=session_id
    )
    return ToolResponse(
        ok=result.status == "ok",
        data={"deleted_count": result.deleted_count, "status": result.status},
    ).model_dump()
