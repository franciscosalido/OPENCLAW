# ADR-0XX: Qdrant 1.18 Upgrade for Local-First Hybrid RAG

## Status

Proposed.

## Date

2026-05-23

## Context

Quimera is local-first and security-first. RAG-1A established a hybrid retrieval
foundation with dense vectors, sparse vectors and Python-side Weighted RRF.

The current repository baseline pins `qdrant-client==1.13.2`. The historical
server baseline is Qdrant 1.13.x. Qdrant 1.18 introduces features that may help
the next retrieval iteration:

- schema-level add/delete named vectors
- TurboQuant
- collection memory monitoring
- low memory mode
- strict mode memory guardrails
- audit log query/tracing improvements
- per-collection metrics
- documented hybrid RRF/DBSF fusion paths

Q18-01 is docs-only. It does not change dependencies, Docker, code, schemas or
collections.

## Decision

Target Qdrant 1.18.0 as the experimental upgrade candidate for Q18.

Defer PostgreSQL/pgvector.

Python RRFFusion remains the retrieval fusion source of truth until Q18-06
compares native Qdrant fusion under benchmark conditions.

## Alternatives Considered

1. **Keep Qdrant 1.13.x.**
   - Good: lowest immediate risk.
   - Bad: no evaluation of newer named-vector lifecycle, memory visibility or
     quantization options.

2. **Upgrade to Qdrant 1.18.0.**
   - Good: same vector backend, better fit for local-first memory and schema
     experiments.
   - Bad: client/server compatibility and benchmark gates must be rerun.

3. **Migrate to PostgreSQL/pgvector now.**
   - Good: relational consistency and SQL integration.
   - Bad: new backend, new schema, new retrieval adapter, new benchmark, and
     higher sprint cost before Qdrant 1.18 is tested.

4. **Defer all storage decisions.**
   - Good: no immediate risk.
   - Bad: stalls RAG-1A follow-up and leaves memory/schema questions unanswered.

Chosen now: option 2 as experimental target. PostgreSQL remains a later
reconsideration path, not the Q18 target.

## Consequences

Good:

- modern named vector lifecycle can support embedding migration experiments
- memory and quantization experiments become first-class
- local-first observability can improve
- RAG-1A architecture is preserved
- protected collections can remain untouched

Bad:

- benchmark must be rerun
- configs can become complex
- quantization can regress recall
- native RRF may diverge from Python RRF
- strict mode can expose adapter assumptions

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| API incompatibility | medium | Q18-02 compatibility tests |
| protected collection mutation | high | Q18-03 prefix-only guard |
| recall regression | high | PR-11/Q18-07 benchmark |
| latency regression | medium | p50/p95 gates |
| memory profile worse than expected | medium | memory report artifact |
| native RRF mismatch | medium | Python RRFFusion remains source of truth |
| PostgreSQL deferral hides relational needs | medium | explicit reconsideration conditions |

## Rollback

Operational outline for a future runtime PR:

1. Stop Qdrant 1.18 container.
2. Re-pin image/client to 1.13.x in a future PR.
3. Delete only `q18_*` collections.
4. Keep `quimera_knowledge` untouched.
5. Keep `quimera_knowledge_v2` untouched unless a later human-approved ADR says
   otherwise.
6. Re-run existing smoke/benchmark gates.

## Conditions for PostgreSQL Reconsideration

Reconsider PostgreSQL/pgvector if any of these become true:

- ACID transactions across relational and vector state become required
- SQL joins/tenancy/governance become dominant requirements
- Qdrant no longer supports a critical named sparse vector workflow
- local single-node Qdrant cannot meet memory or latency gates
- pgvector exposes stable hybrid/RRF behavior competitive with Quimera's needs
- GraphRAG requires relational persistence as the primary memory substrate

## Follow-ups

1. Q18-02 upgrades Qdrant server/client pins in a separate PR.
2. Q18-03 implements destructive local reset governance.
3. Q18-04 validates 1.18 hybrid schema and named vector lifecycle.
4. Q18-05 benchmarks local tuning profiles.
5. Q18-06 compares Python RRF against Qdrant native Weighted RRF.
6. Q18-07 produces benchmark report and final ADR decision.

## Machine-readable summary

<!-- machine-readable: qdrant-118-upgrade-proposal-v1 -->
```json
{
  "schema_version": "qdrant-118-upgrade-proposal-v1",
  "status": "proposed",
  "target_qdrant_version": "1.18.0",
  "postgresql_decision": "defer",
  "protected_collections": [
    "quimera_knowledge",
    "quimera_knowledge_v2"
  ],
  "allowed_destructive_prefixes": [
    "q18_benchmark_",
    "q18_smoke_",
    "quimera_knowledge_v2_dev_"
  ],
  "destructive_local_reset_allowed_in_future_pr": true,
  "runtime_changes_in_this_pr": false
}
```
