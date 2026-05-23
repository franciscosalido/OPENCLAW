# Qdrant 1.18.0 Research Notes

Status: draft
Snapshot date: 2026-05-23
Scope: curated evidence for Q18 planning, not a full vendor mirror

## Sources

| Source | URL | Retrieval date | Notes |
|---|---|---:|---|
| Qdrant 1.18 release blog | https://qdrant.tech/blog/qdrant-1.18.x/ | 2026-05-23 | TurboQuant, memory monitoring, named vector schema update, audit/tracing, strict guardrails |
| Collections docs | https://qdrant.tech/documentation/manage-data/collections/ | 2026-05-23 | update vector schema in v1.18 |
| Quantization docs | https://qdrant.tech/documentation/manage-data/quantization/ | 2026-05-23 | TurboQuant and scalar quantization |
| Administration docs | https://qdrant.tech/documentation/operations/administration/ | 2026-05-23 | low memory mode and strict mode |
| Optimization docs | https://qdrant.tech/documentation/operations/optimize/ | 2026-05-23 | memory/speed/precision tuning profiles |
| Security docs | https://qdrant.tech/documentation/operations/security/ | 2026-05-23 | tracing IDs in audit logs |
| Hybrid queries docs | https://qdrant.tech/documentation/search/hybrid-queries/ | 2026-05-23 | RRF and DBSF |
| Delete vectors API | https://api.qdrant.tech/api-reference/points/delete-vectors | 2026-05-23 | point-level vector deletion |
| qdrant-client PyPI | https://pypi.org/project/qdrant-client/ | 2026-05-23 | qdrant-client 1.18.0 distribution metadata |
| Qdrant GitHub release | https://github.com/qdrant/qdrant/releases/tag/v1.18.0 | 2026-05-23 | full release/changelog entry |

## Feature Matrix

| Feature | Source | Since | Category | Relevance | Migration Risk | Quimera Use Case | Risk | Mitigation | Future PR |
|---|---|---:|---|---|---|---|---|---|---|
| TurboQuant | release blog, quantization docs | 1.18 | quantization | high | medium | reduce dense vector memory footprint | recall/latency regression | benchmark against scalar and full precision | Q18-05/Q18-07 |
| Scalar quantization comparison | quantization docs | 1.1 | quantization | high | low | baseline compression profile | recall loss | keep baseline_ram and scalar_quant profiles | Q18-05 |
| Quantization rescoring | quantization docs | current | quantization/search | high | medium | preserve recall after compressed candidate search | rescoring can add disk reads/latency | benchmark rescore true/false per profile | Q18-05/Q18-07 |
| Optimization profiles | optimization docs | current | tuning | high | medium | define memory/speed/precision trade-off profiles | profile drift can bias benchmark | pin profile config in artifacts | Q18-05 |
| Add/delete named vectors | collections docs | 1.18 | schema evolution | high | high | add candidate dense vector without recreating collection | delete is destructive | prefix-only guard and human approval | Q18-03/Q18-04 |
| Deep memory reporting | release blog | 1.18 | observability | high | low | compare memory footprint by component | API shape may differ | record raw snapshot in benchmark artifact | Q18-05/Q18-07 |
| Low memory mode | administration docs | 1.18 | operations | medium | medium | recover local node under RAM pressure | slower startup/search profile possible | use as recovery/tuning profile, not default | Q18-05 |
| Strict mode `max_resident_memory_percent` | administration docs | 1.18 | guardrail | high | medium | reject memory-heavy writes under pressure | ingest failures if threshold too low | typed operational errors and benchmark profile | Q18-04/Q18-05 |
| Dynamic CPU pool | GitHub changelog | 1.18 | performance | medium | low | improve search workers under I/O wait | not directly configurable yet | measure, do not tune blindly | Q18-07 |
| Audit log API method path | release blog/security docs | 1.18 | audit | medium | low | correlate operations during destructive reset PRs | local-only logs still need sanitization | no query/chunk payloads in logs | Q18-03/Q18-07 |
| Tracing ID in audit logs | security docs | 1.18 | audit | medium | low | connect client request IDs to Qdrant audit trail | header propagation bugs | reuse PR-12 correlation fields | Q18-07 |
| Weighted RRF native | hybrid queries docs | 1.10+ | fusion | medium | medium | compare Qdrant native fusion against Python RRF | formula/default k divergence | Python RRFFusion remains source of truth | Q18-06 |
| DBSF | hybrid queries docs | 1.11+ | fusion | low/medium | medium | research score-normalized fusion | different behavior from RRF | research-only until benchmark | Q18-06 |
| HNSW deterministic subgraph | GitHub changelog | 1.18 | determinism | medium | low | reduce index-build nondeterminism | not enough without benchmark | record build config and run IDs | Q18-07 |
| Web UI memory/disk inspector | release blog | 1.18 | observability | medium | low | human inspection during local tuning | manual-only evidence | prefer API artifact for ADR | Q18-05 |
| qdrant-client 1.18 support | PyPI | 1.18 | client | high | medium | access 1.18 server APIs from Python | deprecated API removals | compatibility adapter tests | Q18-02 |

## 1.13.x -> 1.18 Matrix

| Area | 1.13.x Current | 1.18 Candidate | Quimera Impact | Action |
|---|---|---|---|---|
| Python client | `qdrant-client==1.13.2` | `qdrant-client==1.18.0` available | API compatibility must be rechecked | Q18-02 |
| Server image | baseline `qdrant/qdrant:v1.13.2` | target `qdrant/qdrant:v1.18.0` | Docker pin change only in future PR | Q18-02 |
| Named vector schema | defined at collection create | add/remove named vector schema | easier embedding migration | Q18-04 |
| Hybrid fusion | Python RRF source of truth | native RRF/DBSF available | comparison opportunity, not default | Q18-06 |
| Memory visibility | mostly external/rough | collection memory monitoring | better local tuning artifacts | Q18-05 |
| Strict mode | available baseline controls | new memory and batch guardrails | safer local ingest/search caps | Q18-05 |
| Quantization | scalar/binary/product families | TurboQuant candidate | memory footprint experiment | Q18-05/Q18-07 |
| Audit/tracing | limited/no tracing ID in audit trail | query audit logs and tracing IDs | better multi-agent observability | Q18-07 |
| Low-memory startup | not target baseline | low memory mode | recovery mode for constrained hosts | Q18-05 |

## Feature Triage

### Use Now

- version reporting
- memory reporting for benchmark visibility
- strict mode evaluation

### Research

- TurboQuant
- low memory mode
- dynamic CPU pool
- native Weighted RRF
- DBSF

### Do Not Use Yet

- named vector delete outside benchmark collections
- TurboQuant as default
- native RRF as default
- PostgreSQL backend

## Risks

1. Qdrant 1.18 can remove deprecated API paths used indirectly by old code.
2. Quantization can reduce recall even if memory improves.
3. Strict mode can reject writes/searches that previously succeeded.
4. Named vector deletion is schema-level destructive behavior.
5. Native fusion defaults may differ from Quimera Python RRFFusion.
6. Local RAM pressure is shared with Ollama and LiteLLM.

## Open Questions

1. Which exact deprecated search methods, if any, are still used in this repo?
2. Does qdrant-client 1.18 preserve all async APIs used by PR-08/PR-10?
3. What is the memory report API response shape for local Docker 1.18?
4. What strict-mode profile is safe for local benchmark collections?
5. Does TurboQuant help 1024-dimensional Quimera embeddings without Recall@10 loss?
6. What k/weight defaults does Qdrant native RRF use compared with Python RRFFusion?

## Local Rollback

Rollback is local-only and should be implemented in a future PR:

1. Stop Qdrant 1.18 container.
2. Re-pin server/client to 1.13.x.
3. Delete only `q18_*` temporary collections.
4. Keep `quimera_knowledge` and `quimera_knowledge_v2` untouched.
5. Re-run existing unit tests and opt-in smoke/benchmark gates.
