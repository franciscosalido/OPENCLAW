"""Typed DTOs for FINLIB asyncpg repositories."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


JsonMap = dict[str, object]


@dataclass(frozen=True, slots=True)
class AuditContext:
    """Audit metadata required for one logical repository write."""

    trace_id: UUID | str
    agent_id: str
    batch_hash: str
    run_id: UUID | str | None = None
    metadata: JsonMap | None = None


@dataclass(frozen=True, slots=True)
class BatchWriteResult:
    """Summary returned by audited batch writes."""

    attempted: int
    inserted: int
    updated: int
    skipped: int
    audit_id: UUID | None

    @classmethod
    def empty(cls) -> "BatchWriteResult":
        """Return the canonical no-op batch result."""

        return cls(attempted=0, inserted=0, updated=0, skipped=0, audit_id=None)


@dataclass(frozen=True, slots=True)
class DataSourceInput:
    """Input row for ops_data_sources."""

    source_id: str
    kind: str
    methodology_limitations: str
    base_url: str | None = None
    license_note: str | None = None
    enabled: bool = True
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IngestionRunInput:
    """Input row for ops_ingestion_runs."""

    source_id: str
    agent_id: str
    trace_id: UUID | str
    mode: str = "dry_run"
    status: str = "created"
    source_snapshot_hash: str | None = None
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WatermarkInput:
    """Input row for ops_ingestion_watermarks."""

    source_id: str
    dataset: str
    watermark_value: str
    watermark_ts: datetime | str | None = None
    source_snapshot_hash: str | None = None
    run_id: UUID | str | None = None
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DataQualityCheckInput:
    """Input row for ops_data_quality_checks."""

    run_id: UUID | str
    check_name: str
    target_table: str
    severity: str
    passed: bool
    observed: JsonMap = field(default_factory=dict)
    expected: JsonMap = field(default_factory=dict)
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OutboxEventInput:
    """Input row for ops_outbox_events."""

    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: JsonMap = field(default_factory=dict)
    run_id: UUID | str | None = None
    trace_id: UUID | str | None = None
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QueuedEvent:
    """Claimed outbox event returned by OpsRepository.poll_events."""

    event_id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: JsonMap
    attempts: int
    locked_by: str
    locked_at: datetime
    run_id: UUID | None
    trace_id: UUID | None
    metadata: JsonMap


@dataclass(frozen=True, slots=True)
class MacroSeriesInput:
    """Input row for macro_series_catalog."""

    series_code: str
    display_name: str
    provider: str
    provider_code: str
    source_id: str
    unit: str
    periodicity: str
    value_type: str
    methodology_note: str
    provider_code_status: str = "planning_reference"
    original_source: str | None = None
    requires_live_verification: bool = True
    enabled: bool = True
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MacroObservationInput:
    """Input row for macro_observations."""

    series_code: str
    ref_ts: datetime | str
    value: Decimal | str
    source_id: str
    run_id: UUID | str
    lineage_hash: str
    schema_version: int = 1
    quality_flags: JsonMap = field(default_factory=dict)
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TreasuryBondInput:
    """Input row for treasury_bonds."""

    bond_type: str
    maturity_date: date | str
    display_name: str
    source_id: str
    security_family: str | None = None
    is_active: bool = True
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TreasuryPriceInput:
    """Input row for treasury_prices."""

    bond_id: UUID | str
    ts: datetime | str
    source_id: str
    run_id: UUID | str
    lineage_hash: str
    price_bid: Decimal | str | None = None
    price_ask: Decimal | str | None = None
    rate_bid: Decimal | str | None = None
    rate_ask: Decimal | str | None = None
    base_value: Decimal | str | None = None
    schema_version: int = 1
    quality_flags: JsonMap = field(default_factory=dict)
    metadata: JsonMap = field(default_factory=dict)
