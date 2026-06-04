from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

BenchmarkWinner = Literal["postgres", "qdrant", "hybrid", "capability_gap"]


@dataclass(frozen=True, slots=True)
class BackendStats:
    p50_ms: float
    p95_ms: float
    p99_ms: float
    errors: int = 0


@dataclass(frozen=True, slots=True)
class BenchmarkScenario:
    scenario: str
    samples: int
    postgres: BackendStats
    qdrant: BackendStats
    winner: BenchmarkWinner
    reason: str


@dataclass(frozen=True, slots=True)
class BenchmarkRow:
    scenario: str
    backend: str
    sample_index: int
    latency_ms: float
    error: str
    cache_enabled: str
    cache_bypass: bool
    git_commit: str
    timestamp: str


DECISIONS: dict[str, str] = {
    "sessions": "postgres",
    "turns": "postgres",
    "agent_states": "postgres",
    "entity_mentions": "postgres",
    "vectors": "qdrant",
    "semantic_cache": "qdrant",
    "llm_response_cache": "qdrant",
    "qlib_projection": "postgres_timescale_manifest",
    "kronos_forecasts": "postgres_timescale",
}


def to_jsonable_scenario(scenario: BenchmarkScenario) -> dict[str, object]:
    return {
        "scenario": scenario.scenario,
        "samples": scenario.samples,
        "postgres": asdict(scenario.postgres),
        "qdrant": asdict(scenario.qdrant),
        "winner": scenario.winner,
        "reason": scenario.reason,
    }
