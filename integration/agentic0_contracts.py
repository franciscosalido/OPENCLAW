"""Safe contracts for the PR-08 Agentic0 integration smoke."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

SMOKE_SCHEMA_VERSION = "quimera-agentic0-smoke-v1"
DEFAULT_ALLOWED_TOOLS: tuple[str, ...] = (
    "postgres_memory_health",
    "postgres_recent_turns_get",
    "postgres_agent_state_get",
    "qdrant_memory_health",
    "qdrant_collection_list",
    "qdrant_scroll_safe",
)
WRITE_TOOL = "postgres_agent_state_upsert"


def new_run_id() -> str:
    return f"pr08-{uuid4().hex}"


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Agentic0SmokeConfig:
    litellm_base_url: str = "http://127.0.0.1:4000"
    litellm_model: str = "qwen3-local"
    embedding_model: str = "nomic-embed-text"
    qdrant_collection: str = "quimera_pr08_hybrid_smoke"
    session_id: str = field(default_factory=lambda: uuid4().hex)
    agent_id: str = "agentic0"
    timeout_seconds: float = 120.0
    allowed_tools: tuple[str, ...] = DEFAULT_ALLOWED_TOOLS
    virtual_key_name: str = "agentic0-smoke"
    require_mcp_via_litellm: bool = True
    autonomous_tool_use_enabled: bool = False
    write_smoke_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.litellm_base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("litellm_base_url must be local-only")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not self.allowed_tools:
            raise ValueError("allowed_tools cannot be empty")
        if "*" in self.allowed_tools:
            raise ValueError("allowed_tools cannot contain wildcard")
        if any("delete" in tool or "recreate" in tool or "admin" in tool for tool in self.allowed_tools):
            raise ValueError("allowed_tools cannot contain destructive tools")

    @classmethod
    def with_write_smoke(cls) -> Agentic0SmokeConfig:
        return cls(allowed_tools=DEFAULT_ALLOWED_TOOLS + (WRITE_TOOL,), write_smoke_enabled=True)


@dataclass(frozen=True, slots=True)
class ToolCallSummary:
    server_name: str
    tool_name: str
    status: Literal["ok", "fail", "skipped", "degraded"]
    latency_ms: float
    sanitized_result_keys: tuple[str, ...] = ()
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalSummary:
    collection: str
    quality_mode: str
    quality_evidence: str
    retrieval_backend: str
    live_quality_checked: bool
    live_quality_required: bool
    quality_warning: str | None
    dense_ok: bool
    sparse_ok: bool
    hybrid_ok: bool
    hybrid_recall_at_5: float
    dense_recall_at_5: float
    result_count: int


@dataclass(frozen=True, slots=True)
class PostgresMemorySummary:
    session_persistence_ok: bool
    agent_state_roundtrip_ok: bool


@dataclass(frozen=True, slots=True)
class LLMCallSummary:
    model: str
    completion_ok: bool
    autonomous_tool_use_attempted: bool = False
    autonomous_tool_use_ok: bool | None = None


@dataclass(frozen=True, slots=True)
class LatencySummary:
    total_ms: float
    measurement_mode: str = "live_probe"
    sample_count: int = 1
    p95_warning: str | None = None
    embed_ms: float = 0.0
    retrieval_ms: float = 0.0
    pg_ms: float = 0.0
    mcp_ms: float = 0.0
    llm_ms: float = 0.0
    p50_ms: float | None = None
    p95_ms: float | None = None


@dataclass(frozen=True, slots=True)
class SafetySummary:
    forbidden_fields_seen: tuple[str, ...] = ()
    secrets_seen: bool = False
    vectors_seen: bool = False
    raw_chunks_seen: bool = False


@dataclass(frozen=True, slots=True)
class Agentic0SmokeResult:
    schema_version: str
    status: Literal["pass", "fail", "skipped"]
    run_id: str
    started_at: datetime
    finished_at: datetime
    correlation_id: str
    services: dict[str, str]
    tool_calls: list[ToolCallSummary]
    retrieval: RetrievalSummary
    postgres_memory: PostgresMemorySummary
    llm: LLMCallSummary
    final_answer_ok: bool
    latency: LatencySummary
    safety: SafetySummary
    trace_ids: list[str]
    warnings: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            "Agentic0SmokeResult("
            f"schema_version={self.schema_version!r}, status={self.status!r}, "
            f"run_id={self.run_id!r}, correlation_id={self.correlation_id!r})"
        )

    def to_jsonable(self) -> dict[str, object]:
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        data["finished_at"] = self.finished_at.isoformat()
        return data


def skipped_result(config: Agentic0SmokeConfig, *, reason: str) -> Agentic0SmokeResult:
    now = utc_now()
    return Agentic0SmokeResult(
        schema_version=SMOKE_SCHEMA_VERSION,
        status="skipped",
        run_id=new_run_id(),
        started_at=now,
        finished_at=now,
        correlation_id=uuid4().hex,
        services={},
        tool_calls=[],
        retrieval=RetrievalSummary(
            config.qdrant_collection,
            "not_checked",
            "skipped_before_retrieval",
            "none",
            False,
            True,
            "live_nomic_hybrid_validation_required",
            False,
            False,
            False,
            0.0,
            0.0,
            0,
        ),
        postgres_memory=PostgresMemorySummary(False, False),
        llm=LLMCallSummary(config.litellm_model, False),
        final_answer_ok=False,
        latency=LatencySummary(0.0, measurement_mode="not_measured", sample_count=0, p95_warning="not_measured_stack_unavailable"),
        safety=SafetySummary(),
        trace_ids=[],
        warnings=[reason],
    )
