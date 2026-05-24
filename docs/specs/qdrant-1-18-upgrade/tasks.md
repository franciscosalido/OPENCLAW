# Qdrant 1.18.0 Upgrade - Tasks

Status: draft
Scope: Q18 mini-sprint planning

## Task DAG Summary

```text
T01 -> T02 -> T04 -> T05 -> T06 -> T08 -> Q18-02
       T03 ->              T07 ->/
```

Legend:

| DAG node | Concrete tasks |
|---|---|
| T01 | T-A01 |
| T02 | T-A02, T-A03, T-A04 |
| T03 | T-C02 |
| T04 | T-B01, T-B02, T-B03, T-B04 |
| T05 | T-C01, T-C04 |
| T06 | T-C03, T-E02 |
| T07 | T-E01, T-E03, T-E04, T-E05, T-E06 |
| T08 | `agent_handoff.md` review |

## Track A - Research & Documentation

| Task | Description | Owner | Risk | Scope | Depends on |
|---|---|---|---|---|---|
| T-A01 | Snapshot selected Qdrant 1.18 docs as curated links, not full docs. | Codex | low | docs | none |
| T-A02 | Map 1.13.x -> 1.18 differences. | Codex | low | docs | T-A01 |
| T-A03 | Build feature assessment matrix. | Codex | low | docs | T-A02 |
| T-A04 | Draft `qdrant_1_18_research.md`. | Codex | low | docs | T-A03 |

## Track B - SDD Artifacts

| Task | Description | Owner | Risk | Scope | Depends on |
|---|---|---|---|---|---|
| T-B01 | Draft `proposal.md`. | Codex | low | docs | T-A01 |
| T-B02 | Draft `spec.md`. | Codex | low | docs | T-B01 |
| T-B03 | Draft `design.md`. | Codex | low | docs | T-A03, T-B02 |
| T-B04 | Draft `tasks.md`. | Codex | low | docs | T-B03 |

## Track C - ADR

| Task | Description | Owner | Risk | Scope | Depends on |
|---|---|---|---|---|---|
| T-C01 | Draft ADR-0XX. | Codex | low | docs | T-B03 |
| T-C02 | Document PostgreSQL deferral. | Codex | medium | docs/architecture | T-C01 |
| T-C03 | Document rollback local. | Codex | medium | docs/ops | T-C01 |
| T-C04 | Document alternatives considered. | Codex | low | docs | T-C01 |

## Track D - Feature Tracks

| Task | Description | Owner | Risk | Scope | Depends on |
|---|---|---|---|---|---|
| T-D01 | Schema and named vectors. | Codex/Cowork | medium | future | T-A02 |
| T-D02 | Quantization and TurboQuant. | Perplexity/Codex | medium | future | T-A03 |
| T-D03 | Low-memory mode. | Codex/Cowork | medium | future | T-A03 |
| T-D04 | Strict mode. | Codex/Cowork | medium | future | T-A03 |
| T-D05 | Memory reporting. | Codex | low | future | T-A03 |
| T-D06 | Audit/tracing. | Codex | low | future | T-A03 |
| T-D07 | Native Weighted RRF. | Codex/Cowork | medium | future | T-A03 |

## Track E - Future PR Handoff

| Task | Description | Owner | Risk | Scope | Depends on |
|---|---|---|---|---|---|
| T-E01 | Define Q18-02 acceptance gates. | Codex | medium | future | T-C01 |
| T-E02 | Define Q18-03 destructive reset guard. | Human/Codex | high | future | T-C03 |
| T-E03 | Define Q18-04 schema refactor scope. | Codex/Cowork | medium | future | T-D01 |
| T-E04 | Define Q18-05 tuning profile scope. | Codex/Cowork | medium | future | T-D02, T-D03 |
| T-E05 | Define Q18-06 native fusion experiment. | Codex/Cowork | medium | future | T-D07 |
| T-E06 | Define Q18-07 benchmark/ADR outcome. | Human/Codex | medium | future | T-E01..T-E05 |

## Q18-03 Result Draft

Q18-03 adds destructive local reset governance:

- reset policy: `docs/specs/qdrant-1-18-upgrade/reset_policy.md`
- script: `scripts/qdrant_reset_local_collections.py`
- unit tests: `tests/unit/test_qdrant_reset_local_collections.py`
- default behavior: dry-run
- destructive gates: local host + `QDRANT_LOCAL_RESET=1` + long confirmation flag
- deletion policy: exact names or approved prefixes only
- schema changes: none
- benchmark recreation: protocol/fake support only; real schema creation remains Q18-04

## Q18-04 Result Draft

Q18-04 adds the Qdrant 1.18 hybrid benchmark schema contract:

- schema module: `backend/rag/qdrant_hybrid_118.py`
- CLI: `scripts/qdrant_create_hybrid_schema_118.py`
- unit tests: `tests/unit/test_qdrant_hybrid_118_schema.py`
- benchmark collection: `quimera_benchmark_hybrid_118`
- dense vector: `dense`, 1024 dimensions, Cosine
- sparse vector: `sparse`
- payload index contract: explicit keyword/integer fields
- snapshot path for live opt-in: `docs/specs/qdrant-1-18-upgrade/benchmark_schema_snapshot.json`
- retrieval, ingest, tuning and benchmark changes: none

## Q18-05 Result Draft

Q18-05 adds local-first Qdrant tuning profile contracts:

- tuning module: `backend/rag/qdrant_tuning.py`
- tuning docs: `docs/specs/qdrant-1-18-upgrade/tuning_profiles.md`
- unit tests: `tests/unit/test_qdrant_tuning_profiles.py`
- default profile: `balanced_local`
- profiles: `baseline_ram`, `balanced_local`, `low_memory`,
  `turboquant_experimental`, `high_precision_disk`
- TurboQuant policy: experimental only, benchmark required, never default
- monitoring handoff: `/metrics?per_collection=true`, `/telemetry`, and
  OpenTelemetry-compatible attribute keys without importing OpenTelemetry
- benchmark handoff: `QdrantTuningRunSummary`
- Qdrant mutation, benchmark execution and retrieval changes: none

## Q18-06 Result Draft

Q18-06 adds an experimental Python RRF vs Qdrant native RRF comparison adapter:

- native fusion module: `backend/rag/qdrant_native_fusion.py`
- native RRF docs: `docs/specs/qdrant-1-18-upgrade/native_rrf_adapter.md`
- unit tests: `tests/unit/test_qdrant_native_fusion.py`
- default behavior: disabled; Python `RRFFusion` remains source of truth
- modeled native paths: `qdrant_rrf` and `qdrant_weighted_rrf`
- future MCP profiles: `neutral`, `semantic_hybrid`, `lexical_hybrid`
- future MCP recommendation: one MCP server with two tools, not two mandatory
  TCP ports
- comparison metrics: overlap, Jaccard, order equality, set equality, rank delta
  and tie-break notes
- observability: OTel-compatible dicts only, with query hash/id and no query text
- Qdrant mutation, MCP live server, benchmark execution and retrieval default
  changes: none

## Q18-07 Result Draft

Q18-07 adds the final benchmark comparison and decision artifact contract:

- comparator module: `evaluation/compare_qdrant_113_vs_118.py`
- unit tests: `tests/unit/test_compare_qdrant_113_vs_118.py`
- decision report: `docs/rag/qdrant_118_upgrade_results.md`
- final ADR: `docs/ADR/ADR-0XX-qdrant-118-upgrade.md`
- generated artifact paths:
  - `evaluation/results/qdrant_118_benchmark_summary.json`
  - `evaluation/results/qdrant_118_benchmark_rows.csv`
  - `evaluation/results/qdrant_118_benchmark_report.md`
  - `evaluation/results/qdrant_118_benchmark_charts.svg`
- default mode: artifact-only, no Qdrant calls
- live benchmark gate: `RUN_QDRANT_118_BENCHMARK=1 --execute-live-benchmark`
- official scenarios: 1.13 vs 1.18 baseline, baseline vs balanced, Python RRF
  vs native RRF, no quantization vs TurboQuant, dense-only vs hybrid
- current decision without live artifacts: `inconclusive_missing_evidence`
- Python RRFFusion remains default; TurboQuant remains experimental; PostgreSQL
  and GraphRAG remain outside Q18

## Q18-02 Gate Draft

Q18-02 may begin only after:

- this SDD pack is reviewed
- Qdrant 1.18 official sources are accepted as sufficient
- rollback path to 1.13.x is explicit
- protected collection names are confirmed
- no direct production/personal data path is involved
