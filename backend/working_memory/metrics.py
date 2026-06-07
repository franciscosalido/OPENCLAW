"""Safe metric names for working memory instrumentation."""

from __future__ import annotations


WM_STAGE = "working_memory"
WM_UPSERT_SPAN = "working_memory.upsert"
WM_QUERY_SPAN = "working_memory.query"
WM_SNAPSHOT_SPAN = "working_memory.snapshot"
WM_RESTORE_SPAN = "working_memory.restore"
WM_CLEANUP_SPAN = "working_memory.cleanup"

SAFE_WORKING_MEMORY_ATTRIBUTES = frozenset(
    {
        "quimera.agent_id",
        "quimera.session_id",
        "quimera.stage",
        "cache.collection",
        "working_memory.point_count",
        "working_memory.snapshot_id",
        "working_memory.restore_count",
        "latency.total_ms",
    }
)
