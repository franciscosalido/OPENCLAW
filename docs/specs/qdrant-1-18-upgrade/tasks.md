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

## Q18-02 Gate Draft

Q18-02 may begin only after:

- this SDD pack is reviewed
- Qdrant 1.18 official sources are accepted as sufficient
- rollback path to 1.13.x is explicit
- protected collection names are confirmed
- no direct production/personal data path is involved
