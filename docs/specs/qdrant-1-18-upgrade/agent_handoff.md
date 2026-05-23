# Q18-01 Agent Handoff

Status: draft
Scope: Qdrant 1.18 docs-only planning pack

## Roles

- Perplexity: research/docs verification and source freshness.
- Codex: docs implementation only in Q18-01.
- Cowork: scope, safety and consistency review.
- Human: approve destructive scope before Q18-03.

## Memory Files to Read

- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `docs/04_MEM/AGENT_CONTEXT.md`
- `docs/04_MEM/current_state.md`
- `docs/04_MEM/decisions.md`
- `docs/ADR/*`
- `docs/rag/*`

## Non-negotiables

- Q18-01 is docs-only.
- No runtime mutation.
- No Docker changes.
- No dependency changes.
- No benchmark execution.
- No live Qdrant calls.
- No protected collection mutation.
- No real portfolio, brokerage, credential or private document data.

## Handoff to Q18-02

Before touching Docker or dependencies:

1. Review `proposal.md`, `spec.md`, `design.md`, `tasks.md` and the ADR.
2. Confirm official Qdrant 1.18 sources are sufficient.
3. Confirm rollback path to 1.13.x.
4. Confirm protected collection names.
5. Open a separate implementation PR for version changes.

## Q18-02 Result

- Client pin target: `qdrant-client==1.18.0`.
- Server image target: `qdrant/qdrant:v1.18.0`.
- Version contract path: `infra/qdrant/version_contract.yaml`.
- Local config path: `infra/qdrant/config.yaml`.
- Readiness script path: `scripts/check_qdrant_118_readiness.py`.
- Unit test path: `tests/unit/test_qdrant_118_config.py`.
- REST port: `6333`.
- gRPC port: `6334`.
- Schema changes: none.
- Collection mutations: none.
- Strict mode, quantization and low-memory mode: not enabled in Q18-02.

## Q18-03 Result

- Reset policy path: `docs/specs/qdrant-1-18-upgrade/reset_policy.md`.
- Reset script path: `scripts/qdrant_reset_local_collections.py`.
- Unit test path: `tests/unit/test_qdrant_reset_local_collections.py`.
- Dry-run is default.
- Destructive execution requires:
  - local host only
  - `QDRANT_LOCAL_RESET=1`
  - `--execute`
  - `--i-understand-this-deletes-local-qdrant-collections`
- Delete targets use exact names or explicit prefixes only.
- Wildcards, substring deletion and remote hosts are blocked.
- Benchmark recreation is protocol/fake-supported, but real schema creation is
  deferred to Q18-04.
- Schema changes: none.
