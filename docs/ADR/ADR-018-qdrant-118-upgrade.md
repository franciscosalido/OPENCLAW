# ADR-D2P-018: Qdrant 1.18.1 Local-First Upgrade

Status: Accepted-D2P

Decision Type: D2P / Two-Way Door / Reversible

## Context

Q18 evaluated Qdrant 1.18 as the next local-first vector backend for Quimera
after RAG-1A established dense+sparse hybrid retrieval and Python Weighted RRF.
The previous Q18-07 benchmark artifacts were produced against Qdrant Server
1.18.0 and recorded regressions, so they do not automatically promote a new
default profile.

Qdrant Server 1.18.1 is a patch release with fixes that matter for local-first
benchmarking: async update safety, empty vector handling, TurboQuant memory
reporting, payload index/filter correctness, worker/optimizer behavior and
snapshot/resharding stability. The lockfile currently resolves
`qdrant-client==1.18.0`, so this ADR intentionally accepts a documented
server/client patch mismatch while the project dependency requires
`qdrant-client>=1.18` to prevent rollback to legacy 1.13.x clients.

## Decision

Target Qdrant Server `qdrant/qdrant:v1.18.1` for local-first runtime
evaluation.

Keep Python client dependency `qdrant-client>=1.18`; the current lockfile
resolution remains `1.18.0`.

Python Weighted RRF remains the ground truth. Native Qdrant RRF remains
experimental. TurboQuant remains experimental and is not a default. PostgreSQL/GraphRAG remain outside Q18.

## Why D2P

This is a two-way-door decision because it is reversible and scoped to local
development/benchmark runtime:

- Reversion is cheap: change the Docker tag and `infra/qdrant/version_contract.yaml`.
- There is no production migration.
- Benchmark collections can be recreated from source corpus.
- `quimera_knowledge` and `quimera_knowledge_v2` remain protected by existing
  governance.
- The Python client contract remains in the `1.18` family or newer, with the
  current lockfile resolved at `1.18.0`.

## Evidence

Evidence is recorded in `docs/rag/qdrant_118_upgrade_results.md` and generated
artifacts under `evaluation/results/` when present.

This ADR does not reinterpret Qdrant 1.18.0 benchmark conclusions as 1.18.1
results. It accepts 1.18.1 as a reversible local target because the patch fixes
reduce operational risk and can be rolled back if readiness, smoke or benchmark
results regress.

## Server/Client Version Policy

- Server target: `1.18.1`.
- Docker image: `qdrant/qdrant:v1.18.1`.
- Client target: `1.18.0`.
- Client dependency: `qdrant-client>=1.18`.
- Version family: `1.18`.

Readiness requires exact server target, current lockfile client target and same
`1.18` family. Exact server/client patch parity is recorded as diagnostic
`version_exact_parity_ok=false`, but it does not block readiness while the
lockfile resolves `qdrant-client==1.18.0`.

## YAML Configuration Policy

`infra/qdrant/config.yaml` is local-first and conservative:

- REST `6333` and gRPC `6334` remain enabled.
- `on_disk_payload=true` saves RAM for non-indexed payload values.
- CPU/search workers use Qdrant auto mode (`0`) for local machine variability.
- HNSW remains RAM-first (`on_disk=false`) for the reversible baseline.
- Collection-level vector `on_disk` and quantization defaults remain `null`.
- Strict mode is documented but not enabled globally.
- TLS, API keys, cluster mode and audit logs are not enabled in local YAML.
- TurboQuant and low-memory behavior remain benchmark decisions, not defaults.

## Alternatives Considered

1. Keep Qdrant Server 1.18.0.
2. Target Qdrant Server 1.18.1 with `qdrant-client>=1.18`.
3. Revert to Qdrant 1.13.2 immediately.
4. Promote TurboQuant or native RRF as part of the patch upgrade.
5. Move PostgreSQL/GraphRAG into this cycle.

Option 2 is selected because it preserves the Q18 architecture while allowing
patch-level server fixes to be evaluated without a production migration.

## Consequences

Positive:

- Bugfix server release is evaluated locally.
- Python client remains on the latest available PyPI release.
- Readiness output explicitly records target server, target client, family
  compatibility and patch mismatch.
- Rollback path remains simple.

Negative:

- Q18-07 benchmark conclusions for 1.18.0 must be repeated for 1.18.1.
- Patch mismatch can expose subtle API compatibility issues.
- Local YAML needs to stay conservative until benchmark evidence is refreshed.

## Rollback

1. Stop Qdrant 1.18.1 container.
2. Change `server_image` in `infra/qdrant/version_contract.yaml`.
3. Change compose image to `qdrant/qdrant:v1.18.0` or `qdrant/qdrant:v1.13.2`.
4. Start Qdrant and run readiness.
5. Re-run smoke/benchmark before any default promotion.

Rollback targets:

- `qdrant/qdrant:v1.18.0`
- `qdrant/qdrant:v1.13.2`

## Conditions for Reversal

- Readiness fails.
- Qdrant 1.18.1 fails smoke.
- p95 latency regression exceeds the agreed threshold.
- NDCG/Recall regression persists with Qwen3 benchmark.
- Memory reporting indicates higher local footprint.
- Client/server incompatibility becomes blocking.

## Follow-ups

- Save 1.18.1 readiness output in `evaluation/results/qdrant_1181_readiness.json`.
- Repeat Qwen3 benchmark with server version `1.18.1` recorded.
- Keep Python Weighted RRF as default until native RRF earns benchmark evidence.
- Keep TurboQuant experimental until quality, latency and memory evidence pass
  thresholds.

## Machine-readable block

<!-- machine-readable: adr-d2p-qdrant-upgrade-v1 -->
```json
{
  "schema_version": "adr-d2p-qdrant-upgrade-v1",
  "decision_type": "D2P",
  "reversible": true,
  "server_target_version": "1.18.1",
  "client_target_version": "1.18.0",
  "client_dependency": "qdrant-client>=1.18",
  "client_patch_version_note": "uv.lock currently resolves qdrant-client 1.18.0",
  "docker_image": "qdrant/qdrant:v1.18.1",
  "python_rrf_default": true,
  "native_rrf_default": false,
  "turboquant_default": false,
  "postgresql_scope": "out_of_scope",
  "rollback_targets": [
    "qdrant/qdrant:v1.18.0",
    "qdrant/qdrant:v1.13.2"
  ]
}
```
