# current_state.md — OPENCLAW Operational Memory

> Volatile project state for Codex, Claude Code, ChatGPT Thinking, and human
> review. Read after `docs/04_MEM/AGENT_CONTEXT.md`. Update at the end of
> meaningful sessions.

**Last updated:** 2026-06-06
**Updated by:** Codex — RAG-01B PR-10 working memory Qdrant + pgvector

---

## RAG-01B PR-10 — Working Memory Qdrant + pgvector Checkpoints

Current branch: `rag-01b/pr-10-working-memory-qdrant-pgvector`
Base branch: `rag-01b/pr-08-integration-smoke` after PR-09 merge commit
`a0870b14d441de9731c84cb3e027ae76fdbb787c`.

Implemented:

- Added accepted ADR-005 in both ADR trees:
  `docs/adr/ADR-005-qdrant-working-memory-pgvector-checkpoints.md` and
  `docs/ADR/ADR-005-qdrant-working-memory-pgvector-checkpoints.md`.
- Added PR-10 SDD and memory handoff:
  `docs/specs/rag-01b/pr-10-working-memory-qdrant-pgvector.md` and
  `docs/04_MEM/WORKING_MEMORY_QDRANT.md`.
- Added `backend/working_memory/` with settings, immutable models, safety
  gates, Qdrant hot store, pgvector checkpoint repository, snapshot service,
  restore service, cleanup and safe metric names.
- Added pgvector checkpoint SQL:
  `infra/postgres/sql/020_working_memory_checkpoints.sql`.
- Added working-memory MCP tools/server on loopback Streamable HTTP
  `127.0.0.1:8813/mcp`.
- Registered `quimera-working-memory` in host LiteLLM config and allowed only
  safe Agentic0 health/query tools by default. Upsert/snapshot are optional
  write tools; restore/cleanup remain disabled by default.
- Added degraded-safe working-memory smoke report:
  `integration/working_memory_smoke.py` and
  `evaluation/results/rag_01b_pr10_working_memory_smoke.json`.

Scope explicitly not changed:

- No Redis, Dragonfly or Python/RAM backend decision.
- No HybridRAG collection mutation.
- No `quimera_query_cache` or `quimera_llm_cache` mutation.
- No pgvector ANN index as hot path.
- No daemon/scheduler/dashboard/provider remoto/real data.
- No `delete_collection` flow for working memory.

Validation:

- PR-10 unit/integration block: 67 passed / 4 skipped.
- PR-10 + LiteLLM/MCP registration block: 75 passed / 4 skipped.
- `uv run mypy --strict` on PR-10 working-memory, MCP, LiteLLM config and
  tests: success.
- `uv run pyright` on the same scope: 0 errors.
- `uv run python -m infra.litellm.config_validator`: success with one expected
  qdrant-semantic fallback warning.
- `uv run python -m integration.working_memory_smoke`: generated skipped safe
  smoke artifact because live stack was not requested.
- `git diff --check`: clean.

Operational note:

- Live Qdrant/Postgres restore tests are opt-in and skip cleanly unless the
  human operator exports the explicit `QUIMERA_TEST_WM_*` variables and a
  test DSN.

### RAG-01B PR-10 RC-01 — Restore Integrity and Host Python 3.12 Gate

Implemented:

- Added `abort_on_checksum_fail` to `RestoreService`. Default remains
  availability-first warn-and-restore; strict operators can now abort restore
  before any point is written when checksum validation fails.
- Replaced module-level `count(1)` snapshot epochs in the real snapshot flow
  with PostgreSQL `MAX(snapshot_epoch) + 1` allocation under an advisory lock
  scoped to `(agent_id, session_id)`, avoiding restart-to-1 behavior and
  cross-process epoch races.
- Documented that `integration/hybrid_fixture.py` uses `delete_collection` only
  for synthetic HybridRAG fixture teardown and not in working-memory runtime.

Validation:

- `.venv/bin/python --version`: Python 3.12.13.
- Required host Python 3.12 unit block:
  68 passed.
- PR-10 focused unit/integration block:
  70 passed / 4 skipped.
- Full host Python 3.12 regression with `.venv/bin/python -m pytest`:
  1891 passed / 65 skipped.
- `uv run mypy --strict` on PR-10 working-memory/MCP/tests:
  success.
- `uv run pyright` on PR-10 working-memory/MCP/tests:
  0 errors / 0 warnings.

---

## RAG-01B PR-09 — Operational Hardening + Smoke CLI

Current branch: `rag-01b/pr-09-operational-hardening-smoke`
Base branch: `rag-01b/pr-08-integration-smoke`

Implemented:

- Added accepted working memory checkpoint ADR:
  `docs/ADR/ADR-004-working-memory-checkpoint-contract.md`.
- Added `docs/04_MEM/WORKING_MEMORY_CONTRACT.md`, explicitly deferring the
  fast working memory backend and accepting pgvector only as durable checkpoint.
- Added PR-09 SDD, recovery runbooks, PostgreSQL backup/restore runbook and
  15-minute agent onboarding doc.
- Added local PostgreSQL backup helpers:
  `infra/postgres/backup.sh`, `restore_verify.sh`, `backup_manifest.py` and
  `backup_config.env.example`.
- Added pg_stat_statements operational config and diagnostics:
  Postgres compose command settings, initdb extension bootstrap,
  `infra/postgres/sql/010_pg_stat_statements_diagnostics.sql` and
  `infra/postgres/pg_stat_report.py`.
- Added working memory checkpoint SQL contract:
  `infra/postgres/sql/011_working_memory_checkpoint_contract.sql`.
- Added PR-09 smoke CLI:
  `./run_smoke.sh` plus `scripts/start_quimera.sh smoke`.
- Added PR-09 smoke summary and manual health report:
  `integration/smoke_summary.py` and `integration/health_report.py`.
- Added conservative latency baseline:
  `baseline/rag01b_latency_baseline.json`.
- Generated PR-09 artifacts:
  `evaluation/results/rag_01b_pr09_smoke_summary.json`,
  `evaluation/results/rag_01b_pr09_health_report.json` and
  `evaluation/results/rag_01b_pr09_pg_stat_report.json`.

Scope explicitly not changed:

- No final fast working memory backend selected.
- No Redis implementation.
- No Qdrant in-memory implementation.
- No Python vector memory implementation.
- No cloud/offsite backup, PITR, replication or dashboard.
- No provider remoto.
- No `down -v`, `docker system prune` or volume deletion.
- No destructive schema migration.

Validation:

- PR-09 unit block: 21 passed.
- PR-09 integration block: 3 passed / 2 skipped.
- PR-08 + PR-09 focused block: 51 passed / 3 skipped.
- Full regression: 1816 passed / 60 skipped.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `bash -n run_smoke.sh infra/postgres/backup.sh infra/postgres/restore_verify.sh scripts/start_quimera.sh`: clean.
- `./run_smoke.sh --quick --json --no-build --timeout 5 --allow-degraded`:
  generated PR-09 smoke summary with `overall=degraded` because LiteLLM was
  unavailable while local Postgres/Qdrant/Ollama healthchecks were OK.

Operational note:

- Live backup/restore and live pg_stat integration tests skipped because no
  Postgres DSN was exported in the shell. The static contract, scripts,
  manifest logic and degraded reports are covered locally.

### RAG-01B PR-09 RC-01 — Integration + Diagnostic Final Closure

Implemented:

- Hardened `integration/smoke_summary.py::render_summary_table` so service
  values can be either strings (`"ok"`, `"fail"`) or dictionaries with
  `status`.
- Added `status` as a compatibility alias for the canonical smoke-summary
  `overall` field, and documented that contract in the PR-09 SDD.
- Refactored PR-09 live subprocess tests to invoke modules with
  `sys.executable` and explicit `PYTHONPATH`, avoiding `uv run` inside
  mounted review sandboxes.
- Added a PR-09 GitHub Actions workflow that runs the required unit contracts
  on Python 3.12 inside `.venv`.
- Added an explicit irreversible-data-loss warning around manual
  `docker volume rm` reset instructions in `infra/README.md`.
- Regenerated PR-09 health and smoke summary artifacts with the new
  `status == overall` contract.

Validation:

- PR-09 focused block: 28 passed / 2 skipped.
- Full regression: 1819 passed / 61 skipped.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `bash -n run_smoke.sh infra/postgres/backup.sh infra/postgres/restore_verify.sh scripts/start_quimera.sh`: clean.
- `git diff --check`: clean.

---

## RAG-01B PR-08 — Agentic0 End-to-End System Integration Smoke

Current branch: `rag-01b/pr-08-integration-smoke`

Implemented:

- Added deterministic PR-08 integration package under `integration/` with:
  Agentic0 smoke contracts, LiteLLM-only Agentic0 client, integration health
  report, synthetic HybridRAG fixture, safe report writer and CLI smoke runner.
- Added PR-08 documentation:
  `docs/specs/rag-01b/pr-08-agentic0-integration-smoke.md`,
  `docs/rag/rag_01b_pr08_integration_report.md`, and
  `docs/references/llm_harness_original_papers.md`.
- Updated `docs/04_MEM/AGENT_CONTEXT.md` with final RAG-01B integration state,
  service responsibility map, Level 0/local-only policy and PR-08 commands.
- Added Agentic0 virtual-key/tool policy to host LiteLLM config and validator.
  Allowed tools are explicit; wildcard and destructive tools are rejected.
- Extended `scripts/start_quimera.sh` with:
  `integration-health`, `mcp-status`, `agentic0-smoke`, `pr08-report`, and
  `rag01b-final-gate`.
- Added PR-08 unit and integration tests for Agentic0 contracts, health,
  HybridRAG, MCP registration, no direct backend shortcuts, safe artifacts,
  OTel trace safety, degraded-service behavior, latency reporting and final
  closeout docs.
- Generated PR-08 artifacts:
  `evaluation/results/rag_01b_pr08_agentic0_smoke_summary.json`,
  `evaluation/results/rag_01b_pr08_integration_health.json`, and
  `evaluation/results/rag_01b_pr08_latency_summary.json`.

Scope explicitly not changed:

- No LiteLLM Docker service.
- No remote provider fallback.
- No Agentic0 direct Qdrant/Postgres/Ollama access.
- No destructive Qdrant/Postgres operations outside guarded test-prefix
  cleanup helpers.
- No raw prompt, answer, chunk, document text, vector, embedding, secret or DSN
  stored in PR-08 artifacts.

Validation:

- `bash -n scripts/start_quimera.sh`: clean.
- `uv run python -m infra.litellm.config_validator`: success with one expected
  qdrant-semantic policy warning.
- PR-08 focused block: 23 passed / 1 skipped.
- Full regression: 1787 passed / 59 skipped.
- `uv run mypy --strict` on PR-08 modules/tests and LiteLLM validator:
  success.
- `uv run pyright` on PR-08 modules/tests and LiteLLM validator: 0 errors.
- `uv run python -m integration.run_agentic0_smoke_test --json --allow-degraded`:
  generated safe artifacts with status `skipped` because the local stack had
  LiteLLM/Qdrant/Postgres down while Ollama was OK.

Operational note:

- Live end-to-end Agentic0 synthesis should be rerun after starting the full
  local stack with LiteLLM host gateway, Qdrant and Postgres. The degraded
  result is intentional and safe; it verifies no shortcut path bypasses LiteLLM.

### RAG-01B PR-08 RC-01 — Reviewer Risk Closure

Implemented:

- HybridRAG artifacts now explicitly mark Recall@5 as
  `offline_synthetic_fixture`, require live local validation, and distinguish
  deterministic RRF fixture evidence from real `nomic-embed-text` quality.
- `json_has_no_forbidden_fields` now delegates to the AST-aware field scanner,
  so audit flags such as `secrets_seen` do not trigger false positives while
  unsafe field names remain blocked.
- `rag01b-final-gate` no longer interpolates JSON into a Python heredoc. It
  writes status, integration-health and smoke JSON to temporary files and loads
  them by path.
- Latency artifacts now include `measurement_mode`, `sample_count` and
  `p95_warning`. Offline/degraded runs set `p95_ms=null` with
  `not_measured_stack_unavailable`; live p95 over 500ms emits
  `p95_exceeds_500ms`.
- `scripts/quimera_status.py` now captures LiteLLM and Ollama healthcheck
  latency, and integration health includes safe per-service latency metadata.

Validation:

- PR-08 focused RC block: 27 passed / 1 skipped.
- Full regression: 1791 passed / 59 skipped.
- `uv run mypy --strict` on PR-08 modules/tests and status script: success.
- `uv run pyright` on PR-08 modules/tests and status script: 0 errors.
- `bash -n scripts/start_quimera.sh`: clean.
- `git diff --check`: clean.

---

## RAG-01B PR-07 — Benchmark + ADR + MCP Memory Gate

Current branch: `rag-01b/pr-07-benchmark-adr-mcp-memory`

Implemented:

- Added deterministic benchmark harness and artifacts:
  `evaluation/results/rag_01b_session_benchmark_summary.json` and
  `evaluation/results/rag_01b_session_benchmark_rows.csv`.
- Added accepted backend decision ADR:
  `docs/ADR/ADR-003-memory-backend-decision.md`.
- Added PR-07 SDD and benchmark result documentation.
- Added FastMCP-based local memory servers:
  `backend/mcp/postgres_memory_server.py` and
  `backend/mcp/qdrant_memory_server.py`, with loopback-only ports 8811/8812
  and guarded tool inputs.
- Registered MCP servers in host LiteLLM config and hardened the config
  validator for loopback URL, port and transport policy.
- Wired OTel decorators into embedding, retrieval, RRF, cache and selected
  Postgres repository paths, and added benchmark probes for embed, retrieval,
  RRF, rerank, cache, pg_read and pg_write spans.
- Added `scripts/quimera_status.py` plus `start_quimera.sh status --json` and
  `rag01b-acceptance --json`.
- Hardened LiteLLM host-only policy: `start_litellm.sh` refuses to reuse a
  running `quimera-litellm` Docker container, and status JSON reports that
  violation explicitly.
- Closed PR-01/PR-02 reviewer gaps with opt-in integration tests for
  concurrent agent-state/turn writes, market-bar concurrency, and real
  pg_indexes checks.
- Added `fastmcp` dependency for the local MCP memory layer.

Validation:

- PR-07 focused unit block: 35 passed.
- PR-07 focused integration block: 5 passed / 7 skipped.
- Full unit suite: 1739 passed.
- Full regression: 1763 passed / 58 skipped.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `uv run python -m infra.litellm.config_validator`: success with one expected
  qdrant-semantic policy warning.
- `./scripts/start_quimera.sh rag01b-acceptance --json`: `overall=ok`.
- `git diff --check`: clean.

Operational note:

- Local status currently reports `overall=fail` because Postgres and Qdrant are
  not running and a legacy `quimera-litellm` Docker container is active. This is
  now detected as a host-only violation instead of being silently reused.

---

## RAG-01B PR-07 RC-01 — Review Sandbox and Decision Hardening

Current branch: `rag-01b/pr-07-benchmark-adr-mcp-memory`

Implemented:

- Refactored `test_start_quimera_status_json.py` subprocess checks to invoke
  `scripts/quimera_status.py` with `sys.executable` and explicit `PYTHONPATH`,
  avoiding `uv run` in sandbox-mounted review environments.
- Added `degraded` to MCP `ToolResponse`; Postgres MCP read tools now mark
  responses as degraded when no DSN/backend is configured, and write-enabled
  calls fail explicitly with `postgres backend unavailable`.
- Added `sprint: RAG-01B` to benchmark summary JSON and regenerated benchmark
  JSON/CSV artifacts.
- Clarified `llm_response_cache` decision as `qdrant` in benchmark decisions,
  ADR-003 and benchmark docs. LiteLLM remains gateway/manager, not the
  canonical storage backend.
- Updated PR-07 SDD OTel notes to reflect real retrieval/RRF instrumentation.

Validation:

- RC focused tests: 15 passed.
- Full unit suite: 1740 passed.
- Full regression: 1764 passed / 58 skipped.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `./scripts/start_quimera.sh rag01b-acceptance --json`: `overall=ok`.

---

## RAG-01B PR-06 — OpenTelemetry Base Layer

Current branch: `rag-01b/pr-06-otel-base-layer`
Base branch: `rag-01b/pr-05b-litellm-host-audit` while PR-05B remains open.
Draft PR: <https://github.com/franciscosalido/OPENCLAW/pull/113>

Implemented:

- Added `backend/observability/` base package with OTel tracing setup,
  idempotent asyncpg instrumentation, safe attributes, PII/content guards,
  contextvars, events, metrics and async-only decorators.
- Added LiteLLM OTel callback guard and source YAML callback settings:
  `litellm_settings.callbacks: ["otel"]` plus
  `callback_settings.otel.message_logging: false`.
- Added `scripts/start_quimera.sh otel-doctor` and `otel-doctor --json`.
- Added `.env.observability.example` and PR-06 SDD.
- Added OTel dependencies:
  `opentelemetry-api`, `opentelemetry-sdk`,
  `opentelemetry-exporter-otlp-proto-http`,
  `opentelemetry-instrumentation-asyncpg`.

Scope explicitly not changed:

- No full RAG runtime instrumentation.
- No dashboard, collector, Grafana, Tempo, Jaeger or Prometheus service.
- No MCP server, FastAPI, REST API or gRPC.
- No PostgreSQL/Timescale schema change.
- No Qdrant collection change.
- No LiteLLM Docker service.

Validation:

- PR-06 focused OTel tests: 39 passed.
- LiteLLM/start-script compatibility block: 58 passed.
- Full unit suite: 1707 passed.
- Full regression: 1726 passed / 51 skipped.
- Focused post-typing block: 52 passed / 2 skipped.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `bash -n scripts/start_quimera.sh`: clean.
- `uv run python -m infra.litellm.config_validator`: success with one expected
  qdrant-semantic policy warning.
- `./scripts/start_quimera.sh otel-doctor --json`: status `ok`.
- `git diff --check`: clean.

Handoff to PR-07:

- Wire decorators into selected RAG/Gateway execution paths.
- Decide optional collector/profile strategy.
- Keep content capture disabled unless a future ADR explicitly changes the
  privacy boundary.

---

## RAG-01B PR-06 RC-01 — OTel SemConv and Test Marker Cleanup

Current branch: `rag-01b/pr-06-otel-base-layer`
Draft PR: <https://github.com/franciscosalido/OPENCLAW/pull/113>

Implemented:

- `traced_pg` now emits current OTel DB semconv attributes for PostgreSQL:
  `db.system.name=postgresql`, `db.operation.name` and `db.collection.name`,
  while preserving `quimera.pg_table`, `quimera.pg_operation` and
  `latency.pg_ms`.
- Added public metric name constants for the GenAI and retrieval histograms.
- Added `pytest.mark.integration` to all PR-06 OTel integration tests, so
  `pytest -m integration` includes them.
- Hardened `traced_mcp_tool`: validates low-cardinality tool/method names,
  stores tool name as `gen_ai.tool.name`, and keeps span name based on
  `mcp.method.name` rather than raw tool name.

Validation:

- RC focused block: 17 passed.
- `pytest -m integration` on OTel integration tests: 3 passed.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `uv run pytest`: 1730 passed / 51 skipped.
- `git diff --check`: clean.

---

## RAG-01B PR-05B — LiteLLM Host Audit and Hardening

Current branch: `rag-01b/pr-05b-litellm-host-audit`
Issue: <https://github.com/franciscosalido/OPENCLAW/issues/110>

Implemented:

- LiteLLM source config normalized to `os.environ/OLLAMA_BASE_URL`.
- Added canonical aliases `qwen3-local`, `qwen3:14b` and `nomic-embed-text`
  while preserving legacy Gateway/Agentic aliases.
- Embedding aliases now use timeout/stream timeout `5/5`; chat remains
  `120/45`; global request timeout remains `165`.
- Added `infra/litellm/audit.py` for safe JSON/Markdown audit reports.
- Added `infra/litellm/version_fingerprint.py` for best-effort local version
  collection with sanitized DSNs and structured warnings.
- Added `infra/litellm/overhead_benchmark.py`; live benchmark is opt-in via
  `QUIMERA_LITELLM_BENCHMARK=1`.
- Reworked `infra/litellm/start_litellm.sh` to start one host process,
  reuse readiness, write `.runtime/litellm.pid`, use `--num_workers 1`, and
  wait on `/health/readiness`.
- Added `scripts/start_quimera.sh` subcommands: `litellm-audit`,
  `litellm-fingerprint`, `litellm-benchmark`.
- Added PR-05B SDD at
  `docs/specs/rag-01b/pr-05b-litellm-host-audit.md`.

Scope explicitly not changed:

- No LiteLLM Docker service.
- No MCP server, FastAPI or gRPC.
- No HybridRAG mutation.
- No PostgreSQL/Timescale migrations or schema changes.
- No Qdrant collection deletion/recreate.
- No remote providers or model downloads.

Validation so far:

- PR-05B focused unit block: 58 passed.
- LiteLLM/Gateway/Agentic focused block: 160 passed / 95 subtests passed.
- All `tests/unit/test_litellm*.py` + start script tests: 78 passed /
  8 subtests passed.
- Full unit suite: 1669 passed / 256 subtests passed.
- Full regression: 1685 passed / 51 skipped / 259 subtests passed.
- `uv run mypy --strict` on `infra/litellm/*` PR-05B modules: success.
- `uv run pyright` on `infra/litellm/*` PR-05B modules: 0 errors.
- `bash -n` on `scripts/start_quimera.sh` and
  `infra/litellm/start_litellm.sh`: clean.
- `uv run python -m infra.litellm.config_validator`: success with one expected
  qdrant-semantic policy warning.
- `uv run python -m infra.litellm.render_config`: success, fallback local.
- `uv run python -m infra.litellm.audit`: generated JSON/Markdown, status
  `warn` due expected local-service/experimental warnings.
- `uv run python -m infra.litellm.overhead_benchmark`: `SKIPPED_VALID` without
  opt-in.

---

## RAG-01B PR-05B RC-01 — Residual Risk Cleanup

Current branch: `rag-01b/pr-05b-litellm-host-audit`
PR: <https://github.com/franciscosalido/OPENCLAW/pull/111>

Implemented RC-01 fixes:

- RC-09 audit `warn` remains intentional when source YAML declares
  `qdrant-semantic` and the experimental flag is not set; SDD/README now state
  that fallback local is valid runtime behavior.
- `local_json` keeps `timeout=60` and `stream_timeout=45`; SDD/README now
  document the first-chunk tradeoff and recommend concise JSON contexts.
- `version_fingerprint` now exposes `python_version` and `python_executable`
  directly from the running interpreter, independent of command probe failures.
- `overhead_benchmark` keeps `status=SKIPPED_VALID` and now also emits
  `skipped=true` for compatibility with reviewer expectations.

Validation:

- RC-01 focused tests: 19 passed.
- LiteLLM/start-script block: 80 passed / 8 subtests passed.
- Gateway/Agentic focused block: 92 passed / 87 subtests passed.
- PR-05B opt-in integrations without env flags: 5 skipped.
- Full unit suite: 1671 passed / 256 subtests passed.
- `uv run mypy --strict` on RC-01 touched LiteLLM modules: success.
- `uv run pyright` on RC-01 touched LiteLLM modules: 0 errors.
- `uv run python -m infra.litellm.version_fingerprint`: success; includes
  `python_version` and `python_executable`.
- `uv run python -m infra.litellm.overhead_benchmark`: `SKIPPED_VALID` with
  `skipped=true`.
- `uv run python -m infra.litellm.audit`: generated JSON/Markdown, status
  `warn` by design.

---

## RAG-01B PR-05 RC-01 — LiteLLM Host Hardening

Current branch: `rag-01b/pr-05-litellm-host-cache-timeout`
PR: <https://github.com/franciscosalido/OPENCLAW/pull/109>

Implemented RC-01 fixes:

- Raised chat alias `stream_timeout` from 15s to 45s for local Qwen slow-start
  safety.
- Raised global `request_timeout` to 165s so it covers 120s model timeout plus
  45s stream slow-start budget.
- Centralized embedding dimension in `CANONICAL_EMBED_DIM = 768` and validates
  the semantic-cache vector size against it.
- `start_quimera.sh` now warns when the local placeholder
  `LITELLM_MASTER_KEY=quimera-dev-key-change-me` is still used.
- `litellm-stop` sends SIGTERM to only the owned PID and escalates to SIGKILL
  only for that same PID after a grace loop.
- Runtime YAML render now uses `allow_unicode=True`.

Validation:

- RC focused tests: 33 passed.
- PR-05/Gateway focused block: 110 passed / 3 skipped / 65 subtests passed.
- Full unit suite: 1649 passed / 253 subtests passed.
- Full regression: 1666 passed / 47 skipped / 256 subtests passed.
- `bash -n` on changed shell scripts: clean.
- `./scripts/start_quimera.sh litellm-validate`: success.
- `uv run python -m infra.litellm.render_config`: success with
  `cache_backend=local`.
- Production scan: no LiteLLM Docker image/service, no Qdrant container URL,
  no `pkill litellm`, no `killall litellm`, no `down -v`.
- `git diff --check`: clean.

---

## RAG-01B PR-05 — LiteLLM Host Cache + Timeout Hardening

Current branch: `rag-01b/pr-05-litellm-host-cache-timeout`

Architectural correction:

- LiteLLM is a host Python process, not a Docker Compose service.
- Docker Compose manages only Postgres and Qdrant.
- `scripts/start_quimera.sh` reuses a ready host LiteLLM at
  `http://127.0.0.1:4000` or starts exactly one host process tracked by
  `.runtime/litellm.pid`.
- The PR-04 memory line saying Compose managed `quimera-litellm` is superseded
  by this PR-05 correction.

Implemented:

- Removed `litellm`/`quimera-litellm` from
  `infra/docker/compose.quimera.local.yml`.
- Added host LiteLLM commands to `scripts/start_quimera.sh`:
  `litellm-validate`, `litellm-render`, `litellm-start`, `litellm-stop`,
  `litellm-restart`, `litellm-smoke`.
- Added `infra/litellm/config_validator.py`,
  `infra/litellm/render_config.py` and `infra/litellm/smoke_test.py`.
- Added Qdrant semantic-cache source config with safe local fallback in the
  generated runtime config.
- Added tests guarding against LiteLLM returning to Compose.

Validation:

- Focused PR-05/Gateway block: 103 passed / 3 skipped / 65 subtests passed.
- Full unit suite: 1642 passed / 253 subtests passed.
- Full regression: 1659 passed / 47 skipped / 256 subtests passed.
- `docker compose -f infra/docker/compose.quimera.local.yml config --services`:
  `postgres-memory`, `qdrant`.
- `bash -n` on changed shell scripts: clean.
- `git diff --check`: clean.

---

## RAG-01B PR-04 RC-01 — Compose Env Guard + Volume Reset Docs

Current branch: `rag-01b/pr-04-ollama-tuning`
Draft PR: <https://github.com/franciscosalido/OPENCLAW/pull/108>

Implemented RC-01 fixes:

- `infra/docker/compose.quimera.local.yml` now requires `LITELLM_MASTER_KEY`
  through Docker Compose required interpolation and fails fast when missing.
- Added `.env.local.example` with a local placeholder key and Ollama defaults.
- Added `infra/README.md` documenting the local env contract and manual volume
  reset procedure.
- SDD now states that `restart` preserves volumes and corrupted-volume reset is
  manual/operator-owned via `docker volume rm`.

Validation:

- PR-04 unit tests: 28 passed.
- Compose config with placeholder key: success.
- Compose config without `LITELLM_MASTER_KEY`: fails as expected with an
  actionable message.
- Full unit suite: 1618 passed / 253 subtests passed.
- PR-04 optional integration: 1 passed / 2 skipped cleanly.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `git diff --check`: clean.

---

## RAG-01B PR-04 — Ollama Tuning + Keep-Alive Hardening

Current branch: `rag-01b/pr-04-ollama-tuning`
Base: `main` after PR-03 merge.

PR-03 was merged through GitHub:

- PR: <https://github.com/franciscosalido/OPENCLAW/pull/106>
- Merge commit: `3fe71d53460e00f68fbeb1df9821f4b8599a9ad6`
- `main...origin/main`: `0 0` after pull/prune.
- Local Git inconsistency fixed: `branch.main.rebase=false` and
  `pull.rebase=false` so `git pull --ff-only` no longer attempts rebase.

PR-04 implemented locally:

- `scripts/start_quimera.sh` controller with start/stop/restart/status/logs/
  doctor/test/warmup/release.
- Root `start_quimera.sh` and `scripts/star_quimera.sh` compatibility wrappers.
- `infra/ollama` config, warmup and shutdown/release hooks.
- `infra/docker/compose.quimera.local.yml` for `quimera-postgres-memory`,
  `quimera-qdrant` and `quimera-litellm`.
- `docs/specs/rag-01b/pr-04-ollama-tuning-keepalive.md`.

Validation:

- PR-04 unit tests: 25 passed.
- Controller self-test: 25 passed.
- Full unit suite: 1615 passed / 253 subtests passed.
- PR-04 optional integration: 1 passed / 2 skipped cleanly.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `bash -n` on shell wrappers: clean.
- YAML parse check: clean.
- `git diff --check`: clean.

Explicitly not implemented: schema SQL, HybridRAG changes, MCP/API/gRPC,
Kronos, Qlib, pgvector logic, model auto-pull or performance tests.

---

## RAG-01B PR-03 RC-02 — Corrupted Cache Payload Handling

Current branch: `rag-01b/pr-03-hybridrag-cache-qdrant`
PR: <https://github.com/franciscosalido/OPENCLAW/pull/106>

Implemented RC-02 fixes:

- `CacheLayer.lookup` now treats corrupted Qdrant cache payload as a safe cache
  miss, logs `cache_lookup_bad_payload_skipped` at DEBUG, and returns `None`.
- Added unit coverage proving corrupted cache payload does not raise
  `CachePayloadError` to callers.
- `hmac_query_hash` docstring now explicitly warns never to log `query_text`
  alongside the returned hash.

Validation:

- `test_cache_layer.py`: 9 passed.
- `test_cache_fingerprint.py`: 8 passed.
- PR-03 + observability focused tests: 52 passed.
- Full unit suite: 1590 passed / 253 subtests passed.
- Live Qdrant integration with `TEST_QDRANT_URL=http://127.0.0.1:6333`: 3 passed.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `git diff --check`: clean.
- Cache module scope scans: no forbidden imports or destructive collection calls.

---

## RAG-01B PR-03 Review Gate

Current branch: `rag-01b/pr-03-hybridrag-cache-qdrant`
PR: <https://github.com/franciscosalido/OPENCLAW/pull/106>
Status: ready for review, not merged.

Rito status:

- Local branch pulled with `--ff-only`: already up to date.
- Local Qdrant checked healthy at `http://127.0.0.1:6333`.
- Live Qdrant integration now executed with
  `TEST_QDRANT_URL=http://127.0.0.1:6333`: 3 passed.
- PR was converted from draft to ready for review.
- Merge/prune are blocked until COWORK/human approval.

---

## RAG-01B PR-03 RC-01 — Semantic Cache Hardening

Current branch: `rag-01b/pr-03-hybridrag-cache-qdrant`
Draft PR: <https://github.com/franciscosalido/OPENCLAW/pull/106>

Implemented RC-01 fixes:

- `CacheSettings` now rejects `collection_name == source_collection`.
- `invalidate_by_schema_version` rejects empty/blank version values.
- `invalidate_by_corpus_epoch` rejects empty/blank corpus epoch values.
- `test_rag_observability_config` no longer writes to a fixed file under
  `tests/`; it uses an isolated temporary directory, resolving the pre-existing
  PermissionError/carry-over artifact risk.
- `hmac_query_hash` is documented as a caller-side helper whose raw query input
  must never be persisted; only the returned hash may be stored.
- `record_hit` remains best-effort but now emits a safe DEBUG log on failure.

Validation:

- RC focused tests: 37 passed.
- PR-03 + observability focused tests: 51 passed.
- Full unit suite: 1589 passed / 253 subtests passed.
- Optional Qdrant integration tests: 3 skipped cleanly when live integration env
  is not set.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `git diff --check`: clean.

---

## RAG-01B PR-03 — HybridRAG Semantic Cache Layer (Qdrant)

Current branch: `rag-01b/pr-03-hybridrag-cache-qdrant`
Draft PR: <https://github.com/franciscosalido/OPENCLAW/pull/106>
Implementation series: `414bf28..HEAD` on the draft PR branch.

Local and remote branch are aligned (`HEAD...origin/rag-01b/pr-03-hybridrag-cache-qdrant`
is `0 0`).

Implemented:

- SDD for PR-03 semantic retrieval cache.
- `backend/rag/cache/*` settings, models, fingerprint helpers, Qdrant collection
  manager, async `CacheLayer`, errors and shared types.
- Unit tests with fake Qdrant clients.
- Optional live Qdrant integration tests guarded by environment configuration.

Validation:

- PR-03 focused unit tests: 44 passed.
- Optional Qdrant integration tests: 3 skipped cleanly when live integration env
  is not set.
- Full unit suite: 1587 passed / 253 subtests passed.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `git diff --check`: clean.

Explicitly not implemented in PR-03: response cache, raw query/prompt/final
answer/full chunk storage, LLM calls, embedding generation, MCP/API/gRPC,
PostgreSQL/TimescaleDB changes, Qdrant knowledge collection mutation or ORM.

---

## RAG-01B PR-01 RC-02 — PostgreSQL 18.4 Canonical Memory Base

Current branch: `rag-01b/pr-01-postgres-session-schema`

Local-only review state:

- ADR-0021 accepts PostgreSQL 18.4 as the canonical relational-temporal memory
  version.
- Docker Compose pins `postgres:18.4-trixie`.
- PostgreSQL local auth uses `POSTGRES_PASSWORD_FILE` with a non-versioned
  password file under `infra/postgres/secrets/`.
- PostgreSQL 18+ storage layout is explicit: volume mount
  `/var/lib/postgresql`, internal `PGDATA=/var/lib/postgresql/18/docker`.
- PKD-00X documents the QUIMERA MCP Memory Fabric over LiteLLM as the future
  memory access architecture. No MCP runtime was implemented in RC-02.
- PostgreSQL 16 was the previous blueprint reference and is superseded by
  ADR-0021.

No benchmark, migration, SQL schema change or version-selection test was added
for this decision.

## RAG-01B PR-01 RC-03 — Janus Temporal Memory Fabric

Current branch: `rag-01b/pr-01-postgres-session-schema`

Local-only review state:

- ADR-0021 now includes a TimescaleDB addendum.
- ADR-0022 accepts PostgreSQL 18.4 + TimescaleDB as the single temporal memory
  source of truth for agentic memory, financial time series, Qlib projections
  and Kronos forecasts.
- Qlib is a derived compatibility projection, not canonical storage.
- Kronos has no separate persistent memory.
- Blueprint V3.0 now includes the QUIMERA Janus Temporal Memory Fabric section.

No TimescaleDB runtime, Docker image change, SQL extension, hypertable, schema,
Qlib adapter, Kronos adapter or MCP tool was implemented in RC-03.

---

## Stack State — 2026-05-27

Stack local completamente verificado e funcional. Ver `docs/04_MEM/QUIMERA_STACK_RUNBOOK.md`.

| Serviço  | Status | Versão / Detalhe                              |
|----------|--------|-----------------------------------------------|
| Qdrant   | ✅ UP  | v1.18.1, 4 collections presentes              |
| Ollama   | ✅ UP  | nomic-embed-text:latest (0.27GB) + qwen3:14b (9.28GB) |
| LiteLLM  | ✅ UP  | 4 aliases chat saudáveis, embedding falso-positivo no health check (ver BUG 1) |

**Fixes aplicados em `start_quimera.sh`:**
1. `/health` → `/health/liveliness` em todas as verificações LiteLLM (3 ocorrências + modo `--status`)
2. Adicionado export de `LITELLM_LOCAL_CHAT_MODEL` e `LITELLM_LOCAL_EMBED_MODEL` no fallback sem iTerm2
3. iTerm2 path: variáveis derivadas incluídas no `LITELLM_TAB_CMD`

**Problema residual conhecido (não-bloqueante):** LiteLLM reporta `unhealthy_count: 2` para `quimera_embed`/`local_embed` porque o health check interno usa `/api/generate` mas `nomic-embed-text` só aceita `/api/embed`. Os embeddings reais funcionam perfeitamente (768d verificado). Ver BUG 1 no runbook.

---

---

## Active Sprint: Agent-0 / CLI and Readiness

**Goal:** expose the first stable public Agent-0 interface,
`OpenClaw.ask(question) -> Answer`, plus a local CLI, readiness checks,
opt-in E2E SLO gates, sanitized reports and rollback docs.

Current branch: `feat/agent0-cli-and-readiness`
Current issue: <https://github.com/franciscosalido/OPENCLAW/issues/82>

A0-PR05 starts after A0-PR04 and closes the Agent-0 MVP sprint surface. It
does not add multi-agent orchestration, FastAPI, MCP, UI, remote providers,
remote fallback, new ingestion, reindexing or Qdrant mutation in readiness.

```text
question
  -> OpenClaw.ask
  -> deterministic domain routing
  -> existing local RAG path when route == local_rag
  -> frozen Answer with metadata-only citations
  -> CLI / sanitized E2E report
```

Current runtime path:

```text
OpenClaw / runtime generation
  -> LiteLLM at http://127.0.0.1:4000/v1
  -> Ollama / Qwen local
```

Current controlled embedding path:

```text
RagEmbedder factory
  -> gateway_litellm
  -> GatewayEmbedClient
  -> LiteLLM at http://127.0.0.1:4000/v1/embeddings
  -> quimera_embed
  -> Ollama / nomic-embed-text local
```

Rollback embedding path:

```text
RagEmbedder factory
  -> direct_ollama
  -> OllamaEmbedder
  -> Ollama direct at http://127.0.0.1:11434/api/embed
```

GW-07 proves the current RAG E2E path without migrating embeddings:

```text
synthetic docs
  -> chunking
  -> OllamaEmbedder direct at http://127.0.0.1:11434/api/embed
  -> Qdrant temporary collection gw07_synthetic_rag_<short_uuid>
  -> Retriever / ContextPacker / PromptBuilder
  -> LocalGenerator / GatewayChatClient
  -> LiteLLM at http://127.0.0.1:4000/v1/chat/completions
  -> Ollama / Qwen local
```

Hard constraints remain:

- Local only.
- No remote providers.
- No FastAPI.
- No MCP.
- No quant tools.
- No secrets or real portfolio data.
- No `openclaw_knowledge` mutation in verify-only.
- No Qdrant mutation unless `--commit` is explicit and a future writer is wired.
- No arbitrary collection override for dual corpus bootstrap.
- No answer generation in A0-PR03 golden question harness or A0-PR04 routing.
- No LLM-as-judge.
- No Qdrant mutation or live Qdrant requirement in A0-PR03 unit tests.
- No LLM classifier, embeddings, rerankers, remote providers or live Qdrant
  dependency in A0-PR04 classifier/routing unit tests.
- No Qdrant mutation, reindexing or bootstrap in A0-PR05 readiness checks.
- A0-PR05 E2E is opt-in only via `RUN_AGENT0_E2E=1`; unit tests remain offline.
- A0-PR05 reports must not serialize prompt, question text, answer text, chunks,
  vectors, embeddings, payloads, headers, secrets, raw exceptions or tracebacks.
- No final local merge into `main`; GitHub PR approval is the integration path.

## A0-PR05 Current Work

A0-PR05 adds the final Agent-0 MVP public/readiness surface:

- `backend/agent0/openclaw.py` with `OpenClaw.ask(...)` and frozen `Answer`.
- `scripts/openclaw.py` with `ask` command and safe JSON/human output.
- `scripts/check_agent0_readiness.py` with idempotent local readiness checks.
- `backend/agent0/e2e_report.py` with sanitized E2E SLO report builder.
- `tests/e2e/test_agent0_e2e.py`, guarded by `RUN_AGENT0_E2E=1`.
- `docs/AGENT0_RUNBOOK.md` and `docs/AGENT0_ROLLBACK.md`.

Rules:

- `OpenClaw.ask` must reuse existing routing, citation and RAG components; do
  not duplicate the pipeline in the public API wrapper.
- CLI must call `OpenClaw.ask`, support `--json`, avoid tracebacks by default
  and never print prompt/chunks/vectors/payloads/secrets.
- Readiness checks verify Qdrant reachability/collections, local LiteLLM,
  Ollama models, aliases, remote routing disabled, corpus manifests and golden
  questions. They do not mutate Qdrant or bootstrap collections.
- E2E SLO gate is opt-in and expects already-bootstrapped
  `openclaw_internal` / `openclaw_financial`.
- Final SLOs: E2E p95 < 15s and citation hit rate >= 5/6 on the six golden
  questions when local services and corpora are available.
- Rollback deletes only `openclaw_internal` and `openclaw_financial`; never
  delete `openclaw_knowledge`.
- Validation on Python 3.12.13:
  `pytest -v` 561 passed / 9 skipped / 217 subtests passed,
  `mypy --strict .` 0 errors, `pyright` 0 errors, smoke 5 passed / 7 skipped.
- Optional live check status: CLI returns a sanitized local auth failure when
  local gateway credentials are absent; readiness reported 7/9 with only
  Agent-0 Qdrant collections missing in this local environment.

---

## Mandatory GitHub Workflow

For every tracked task:

1. Sync local `main` with GitHub.
2. Open or update a GitHub Issue before implementation.
3. Create a feature branch from updated `main`.
4. Implement locally.
5. Run validation locally.
6. Commit atomic changes.
7. Push the feature branch.
8. Open a GitHub PR to `main`.
9. Link the PR to the issue.
10. Address review on the same branch.
11. Merge only in GitHub after approval.
12. After merge, pull `main` with `--ff-only` and delete branches only when safe.

Do not push directly to `main`. Do not use `git push --force`; if a rebase is
unavoidable, use `git push --force-with-lease`.

---

## Gateway PR Tracking

| PR | Branch | Scope | Status |
|---|---|---|---|
| GW-01 | `feat/gateway-prep-contracts` | ADR, Blueprint V3.0, semantic aliases, config contracts | Done / merged |
| GW-02 | `feat/gateway-install-health` | Local-only LiteLLM operational setup | Done / merged |
| GW-03 | `feat/gateway-route-opencraw-litellm` | Runtime chat/generation through LiteLLM | Done / merged |
| GW-04 | `feat/gateway-runtime-smoke` | Shared message validation, optional smoke, observability | Done / merged |
| GW-05a | `feat/gateway-per-alias-timeouts` | Per-alias timeout configuration | Done / merged |
| GW-05b | `feat/gateway-live-smoke-timeouts` | Live smoke with effective timeout observability | Done / merged |
| GW-06 | `feat/gateway-local-embed-evaluation` | Evaluate embeddings via `local_embed` | Done / merged |
| GW06C | `feat/adr-openai-compatible-embeddings-contract` | OpenAI-compatible embeddings ADR and `quimera_embed` | Done / merged |
| GW-07 | `feat/gateway-rag-e2e-synthetic` | Synthetic RAG E2E through gateway path | Done / merged |
| GW-08 | `feat/rag-controlled-embedding-migration` | Controlled RAG embedding migration to `quimera_embed` | Done / merged |
| GW-09 | `feat/rag-collection-metadata-guard` | Collection metadata drift guard for embedding traceability | Done / merged |
| GW-10 | `feat/rag-run-trace-provenance` | Safe per-query RAG provenance trace | Done / merged |
| GW-11 | `feat/rag-observability-events` | Safe structured RAG lifecycle observability events | Done / merged |
| GW-12 | `feat/gateway-operational-readiness` | Final runbook, readiness checks, ADR boundary, handoff | Done / merged |
| GW-13 | `feat/gateway1-routing-policy-prelude` | Gateway-1 local-first routing policy and token economy prelude | Done / merged |
| GW-14 | `feat/gateway1-routing-audit-token-economy` | Config-driven routing audit and token economy calibration | Done / merged |
| GW-15 | `feat/agent0-local-runner` | Agent-0 local CLI runner MVP | Done / merged |
| GW-16 | `feat/agent0-runner-contract-hardening` | Agent-0 runner contract hardening | Done / merged |
| GW-17 | `feat/agent0-local-failsafe-degradation` | Explicit local fail-safe degradation for Agent-0 | Done / merged |
| GW-18 | `feat/agent0-golden-question-harness` | Golden question benchmark harness for Agent-0 | Done / merged |
| GW-19 | `feat/agent0-observability-signal-contract` | Agent-0 observability signal contract and sanitization tests | Done / merged |
| GW-20 | `feat/gateway1-proof-of-life-smoke` | Gateway-1 operational proof-of-life smoke | Done / merged |
| G2-PR01 | `feat/g2-rag-segment-timing-baseline` | Per-segment RAG latency baseline | Done / merged |
| G2-PR02 | `feat/g2-local-rag-context-budget-cap` | Configurable whole-chunk context budget cap | Done / merged |
| G2-PR03 | `feat/g2-local-rag-generation-budget` | Configurable local_rag generation budget | Done / merged |
| G2-PR04 | `feat/g2-warm-model-cold-start-separation` | Cold/warm/degraded latency separation and model residency measurement | Done / merged |
| G2-PR05 | `feat/g2-keep-alive-model-residency` | Configurable local_rag Ollama keep_alive model residency | Done / merged |
| G2-PR06 | `feat/g2-local-rag-alias-comparison` | Local-only local_rag candidate alias comparison harness | Current |

GW-05a issue: <https://github.com/franciscosalido/OPENCLAW/issues/25>
GW-05b issue: <https://github.com/franciscosalido/OPENCLAW/issues/28>
GW-06 issue: <https://github.com/franciscosalido/OPENCLAW/issues/30>
GW-07 issue: <https://github.com/franciscosalido/OPENCLAW/issues/38>
GW-08 issue: <https://github.com/franciscosalido/OPENCLAW/issues/40>
GW-09 issue: <https://github.com/franciscosalido/OPENCLAW/issues/42>
GW-10 issue: <https://github.com/franciscosalido/OPENCLAW/issues/44>
GW-11 issue: <https://github.com/franciscosalido/OPENCLAW/issues/46>
GW-12 issue: <https://github.com/franciscosalido/OPENCLAW/issues/48>
GW-13 issue: <https://github.com/franciscosalido/OPENCLAW/issues/51>
GW-15 issue: <https://github.com/franciscosalido/OPENCLAW/issues/55>
GW-16 issue: <https://github.com/franciscosalido/OPENCLAW/issues/57>
GW-17 issue: <https://github.com/franciscosalido/OPENCLAW/issues/59>
GW-18 issue: <https://github.com/franciscosalido/OPENCLAW/issues/61>
GW-19 issue: <https://github.com/franciscosalido/OPENCLAW/issues/63>

Gateway-0 sprint complete. GW-01 through GW-12 merged on `main`.
The next sprint must start from a new explicit issue, ADR if architecture
changes, and `git pull --ff-only origin main`.

## G2-PR06 Current Work

G2-PR06 adds an opt-in alias comparison harness for `local_rag` candidates.

Deliverables:

- `scripts/run_rag_alias_comparison.py`.
- `tests/unit/test_rag_alias_comparison.py`.
- `docs/RAG_ALIAS_COMPARISON.md`.

Rules:

- `local_rag` remains the default and comparison baseline.
- Candidate aliases must be semantic local LiteLLM aliases, never concrete
  model names.
- Candidate aliases must resolve to local Ollama config only.
- Remote provider prefixes are rejected.
- The same synthetic golden question fixture is used for baseline and
  candidates.
- Reports store `question_id`, fixture hash, alias metrics and citation flags,
  never question text, answer text, prompt text, chunks, vectors, payloads,
  headers, API keys or tracebacks.
- Warmup runs are discarded and marked only in summary metadata.
- No prompt, retrieval, Qdrant, context budget, generation budget, keep_alive,
  alias default or provider config is changed.
- Candidate promotion requires a separate future PR.

## GW-15 Current Work

GW-15 creates Agent-0, the first local MVP runner:

```text
question
  -> decide_route(...)
  -> local_chat | local_json | explicit local_rag
  -> safe answer metadata
```

Deliverables:

- `scripts/run_local_agent.py`.
- `scripts/test_agent0_local_runner.sh` optional smoke guarded by
  `RUN_AGENT0_LOCAL_SMOKE=1`.
- `docs/AGENT0_LOCAL_RUNNER.md`.
- `tests/unit/test_run_local_agent.py`.

Rules:

- Default execution uses `local_chat`.
- `--json` uses `local_json`.
- `--rag` explicitly opts into the existing local RAG path and `local_rag`.
- `--dry-run` works without live services.
- No remote providers, no remote calls, no API keys, no FastAPI, no MCP.
- No Qdrant mutation, no reindexing, no ingestion, no real data.
- Progressive fallback is handled by GW-17.
- Golden questions harness is handled by GW-18.

## GW-16 Current Work

GW-16 hardens the Agent-0 runner contract without adding new execution
features.

Rules:

- Alias matrix is frozen: default `local_chat`, `--json` `local_json`,
  `--rag` `local_rag`.
- Output schema remains stable across success, dry-run, blocked and failure
  states.
- Blocked and dry-run paths return `latency_ms=0.0`.
- Chat, JSON and RAG failures return safe error categories only.
- No fallback is added. RAG/JSON/chat failures do not silently try another
  alias.
- No remote providers, no remote calls, no Qdrant mutation, no live services
  required for tests.

## GW-17 Current Work

GW-17 adds the first explicit local fail-safe degradation layer.

Rules:

- Fallback reasons are enum-derived, not free-form strings.
- RAG/Qdrant unavailable can fallback once from `local_rag` to `local_chat`.
- Successful RAG fallback returns the chat answer, `alias=local_chat`, and
  `used_rag=false`.
- Policy blocks such as `budget_exceeded` and `unsupported_task` never
  fallback, call no model, and return `error_category=blocked`.
- If the fallback alias also fails, the runner returns a safe failure with no
  second fallback.
- Fallback emits a sanitized local `agent_fallback` loguru event only when
  fallback occurs.
- `local_think` timeout fallback is deferred because Agent-0 has no public
  think path yet.
- No remote providers, no remote calls, no Qdrant mutation, no real data, and
  no live services required for unit tests.

## GW-18 Current Work

GW-18 adds the reproducible Agent-0 golden question harness.

Deliverables:

- `tests/golden/questions.yaml` with 8 synthetic financial-domain questions.
- `scripts/run_golden_harness.py` opt-in harness guarded by
  `RUN_GOLDEN_HARNESS=1`.
- Offline `--dry-run` mode that emits JSONL and summary JSON without live
  services.
- `scripts/compare_golden_runs.py` for summary-to-summary regression checks.
- `docs/AGENT0_GOLDEN_HARNESS.md` and `tests/golden/README.md`.

Rules:

- No answer text is stored in JSONL by default; only `answer_length_chars`.
- Reports exclude prompt/question/chunks/vectors/payloads/secrets and raw
  exceptions.
- Reports are written under `tests/golden/reports/`, which is ignored by Git.
- Quality scoring is human-readable only; no LLM-as-judge and no external API.
- Optional human scoring helper is deferred to a future issue.
- No remote providers, no remote calls, no Qdrant mutation, no real data, and
  no live services required for unit tests.

## GW-19 Current Work

GW-19 adds the Agent-0 observability signal contract.

Deliverables:

- `backend/gateway/observability_contract.py` with canonical allowlists and
  prohibited signal keys.
- `tests/unit/test_observability_signal_contract.py` for RouterDecision,
  TokenEconomyRecord, RagRunTrace, fallback events, decision logs, Agent-0
  output and golden harness dry-run reports.
- `docs/AGENT0_OBSERVABILITY.md`.
- GW-18 NB fixes:
  - golden harness uses `estimate_prompt_tokens` directly from
    `backend.gateway.routing_policy`;
  - `GoldenResult` rejects `skipped=True` with `error_category`.

Rules:

- Sanitization is enforced with allowlists, not blocklist-only checks.
- Fallback event `decision_id` must correlate with Agent-0 output.
- `estimated_remote_tokens_avoided` is checked across success, dry-run,
  blocked, fallback success and fallback failure paths.
- No prompt, raw user input, chunks, vectors, payloads, headers, API keys, raw
  exceptions or model weight paths may appear in observability keys.
- No runtime routing behavior, fallback behavior or remote provider behavior is
  changed.
- No live LiteLLM/Ollama/Qdrant services are required for tests.

## GW-13 Completed Work

GW-13 opens Gateway-1 with safe routing policy records only.

Deliverables:

- `backend/gateway/routing_policy.py` with frozen decision and token economy
  dataclasses.
- `config/rag_config.yaml` `gateway.routing` defaults with
  `remote_enabled: false` and no allowed remote providers.
- `docs/GATEWAY1_ROUTING_POLICY.md`.
- `docs/ADR/0020-controlled-remote-escalation-policy.md` with status Proposed.
- `docs/sprints/GATEWAY1_SPRINT_HANDOFF.md`.
- `tests/unit/test_gateway_routing_policy.py`.

Rules:

- No remote providers.
- No remote calls.
- No API keys.
- No runtime model routing change.
- No Qdrant mutation, reindexing, ingestion, or `openclaw_knowledge` access.
- Token economy is estimated only, not billed.
- Remote escalation requires future sanitization and an explicit Accepted ADR.

---

## GW-05a Timeout Contract

Runtime gateway calls now reserve different timeout budgets per semantic alias:

| Alias | Timeout | Notes |
|---|---:|---|
| `local_chat` | 30.0s | Default chat calls |
| `local_think` | 120.0s | Longer local reasoning calls |
| `local_rag` | 60.0s | RAG answer synthesis |
| `local_json` | 30.0s | Structured local responses |
| `local_embed` | 30.0s | Placeholder only; embeddings are not routed through LiteLLM in GW-05a |

Unknown aliases and `None` fall back to the global `timeout_seconds`.

---

## GW-12 Completed Work

GW-12 closed Gateway-0 as an operational readiness PR, not a feature PR.

Deliverables:

- `docs/GATEWAY_FINAL_RUNBOOK.md`.
- `scripts/check_gateway_readiness.sh` with static default mode and explicit
  `--live`.
- `tests/unit/test_gateway_readiness_script.py`.
- `tests/unit/test_gateway_final_baseline.py`.
- `docs/ADR/0019-gateway-0-sprint-boundary.md`.
- Final updates to shared context, setup, runtime and handoff docs.

Rules respected:

- No runtime architecture change.
- No remote providers.
- No FastAPI, MCP, quant tools, OpenTelemetry, Prometheus, Grafana,
  dashboards, profiling, or mandatory soak tests.
- No Qdrant mutation, no reindexing, no `openclaw_knowledge` access.
- Live proof remains opt-in and must not become CI.
- Memory/resource baseline: not implemented in GW-12. Deferred to a future sprint. See ADR-0019 Future Work section.

## Historical Work

GW-05b:

- Add `timeout_s` to gateway call debug logs.
- Run expanded live smoke with LiteLLM and Ollama actually running when
  `RUN_LITELLM_SMOKE=1` is explicitly set.
- Validate `local_chat`, `local_think`, `local_rag`, and `local_json` against
  their effective timeout budgets.
- Keep smoke synthetic-only and local-only.
- Do not introduce remote providers, real data, RAG E2E, or embeddings through
  LiteLLM.

Live smoke status for GW-05b:

- **2026-04-28: PASSED** — Cenário A completo.
- 128/128 unit+integration tests passed. mypy 0. pyright 0.
- `RUN_LITELLM_SMOKE=1 pytest tests/smoke/` — 7/7 passed.
- `RUN_LITELLM_SMOKE=1 RUN_LITELLM_SMOKE_REPEAT=3 pytest tests/smoke/` — 7/7 passed (54s).

Observed latencies (macOS, qwen3:14b Q4_K_M):

| Alias | elapsed_s | timeout_s |
|---|---:|---:|
| `local_chat` | 2.20 | 30.0 |
| `local_think` | 12.44 | 120.0 |
| `local_rag` | 2.23 | 60.0 |
| `local_json` | 1.72 | 30.0 |

GW-06:

- Evaluate whether embeddings should route through `local_embed`.
- Add an experimental `GatewayEmbedClient` for OpenAI-compatible
  `/embeddings` calls through LiteLLM.
- Keep existing direct/local embedding behavior as the default RAG path.
- Do not reindex Qdrant or touch real documents.
- Use only synthetic smoke inputs.
- Live evaluation on 2026-04-28 passed against local LiteLLM + Ollama.
- Decision status: **Approved for future migration**.
- Migration is still not performed in GW-06; a future PR must preserve or
  replace the current Ollama embedder's retry/backoff/concurrency behavior.

Observed local_embed results (2026-04-28):

| Check | Result |
|---|---|
| LiteLLM single embedding | 768 dimensions, 0.08s |
| LiteLLM batch embedding | 2 vectors, 768 dimensions each, 0.05s |
| Direct Ollama parity | 768 dimensions |
| Cosine similarity | 1.000000 |
| Script smoke | 768 dimensions, 0.70s |

GW-07:

- Prove a synthetic RAG end-to-end flow against the gateway path.
- Keep Qdrant data synthetic and local.
- Use a unique temporary collection named `gw07_synthetic_rag_<short_uuid>`.
- Attempt prefix-guarded cleanup and delete only temporary collections with the
  `gw07_synthetic_rag_` prefix.
- Never touch `openclaw_knowledge`.
- Keep embeddings direct through `OllamaEmbedder`; `quimera_embed` appears only
  as embedding contract metadata in this PR.
- Generate the final answer through LiteLLM using `local_rag`.
- Run only when explicitly enabled with `RUN_RAG_E2E_SMOKE=1`.

Manual live command:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/test_rag_e2e_gateway.sh
```

Direct pytest command:

```bash
RUN_RAG_E2E_SMOKE=1 uv run pytest tests/smoke/test_rag_e2e_gateway_smoke.py -v
```

Cleanup is attempted in teardown. If cleanup is interrupted, manually delete
only Qdrant collections whose names start with `gw07_synthetic_rag_`.

Live status:

- **2026-04-30: PASSED** — Cenário A completo for GW-07.
- Command: `RUN_RAG_E2E_SMOKE=1 uv run pytest tests/smoke/test_rag_e2e_gateway_smoke.py -v -s`.
- Corpus: 3 PT-BR synthetic documents, 14 chunks, 5 chunks retrieved/used.
- Temporary collection: `gw07_synthetic_rag_<short_uuid>` with prefix-guarded
  cleanup for the recorded run; interrupted runs may require manual cleanup by
  prefix.
- Embedding path: direct `OllamaEmbedder` to Ollama `/api/embed`.
- Generation path: `LocalGenerator` / `GatewayChatClient` through LiteLLM
  `local_rag`.

Observed GW-07 latencies (2026-04-30):

| Stage | Latency |
|---|---:|
| embedding/indexing | 178.1 ms |
| retrieval | 18.4 ms |
| generation | 3621.2 ms |
| total pipeline | 3639.6 ms |

---

## Validation Expectations For GW-07

Before opening PR:

```bash
git diff --check
uv run pytest -v
uv run mypy --strict .
uv run pyright
uv run python -m compileall backend tests scripts infra
uv run pytest tests/unit/test_gateway_embed_client.py -v
uv run pytest tests/smoke/ -v
```

## GW-10 Completed Work

GW-10 adds `RagRunTrace`, a safe frozen dataclass for per-query provenance:

```text
LocalRagPipeline.ask(...)
  -> retrieval/prompt/generation timings
  -> RagRunTrace safe metadata only
  -> logger.bind(trace=...).log(...)
```

Trace scope:

- Records collection name, embedding backend/model/alias/dimensions, chunk
  count, gateway alias, and latency metadata.
- Does not record query text, chunk text, prompts, answer text, vectors,
  payloads, real portfolio data, private documents, API keys, Authorization
  headers, or secrets.
- Uses `rag.tracing.enabled` and `rag.tracing.log_level` from
  `config/rag_config.yaml`.
- Raises `EmbeddingDimensionMismatchError` if trace dimensions diverge from
  active expected dimensions.
- Does not mutate Qdrant, reindex collections, or touch `openclaw_knowledge`.

GW-11 current work remains separate from `RagRunTrace`: lifecycle events are
local structured loguru records around embedding, retrieval, and generation.
Memory/resource baseline: not implemented in GW-12. Deferred to a future sprint. See ADR-0019 Future Work section.

Live smoke tests should skip by default unless their explicit guards are set.
GW-07 requires `RUN_RAG_E2E_SMOKE=1`.

Optional live validation when local services are already running:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
RUN_LITELLM_EMBED_SMOKE=1 uv run pytest tests/smoke/test_gateway_embed_smoke.py -v
scripts/test_local_embed_litellm.sh
```

Optional GW-07 live validation when Qdrant, Ollama, LiteLLM, and credentials are
already running locally:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/test_rag_e2e_gateway.sh
```

## GW-08 Completed Work

GW-08 aligns new controlled RAG embedding generation with the accepted
OpenAI-compatible embeddings contract:

```text
RagEmbedder factory
  -> gateway_litellm
  -> GatewayEmbedClient
  -> LiteLLM /v1/embeddings
  -> quimera_embed
  -> Ollama / nomic-embed-text
```

Rollback remains explicit:

```bash
export QUIMERA_RAG_EMBEDDING_BACKEND="direct_ollama"
```

Key rules:

- `OllamaEmbedder` remains available.
- `direct_ollama` remains the rollback backend.
- Existing collections are not reindexed automatically.
- `openclaw_knowledge` is not touched.
- Vectors from different embedding backends, models, providers, or dimensions
  must not be mixed silently in one collection.
- GW-08 smoke uses temporary collections with prefix
  `gw08_embedding_migration_`.

Validation expectations:

```bash
git diff --check
uv run pytest -v
uv run mypy --strict .
uv run pyright
uv run pytest tests/smoke/ -v
```

Optional live validation:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/test_gw08_embedding_migration.sh
```

Live status:

- **2026-04-30: PASSED** — controlled migration smoke and parity smoke passed.
- Required operational note: restart LiteLLM after adding `quimera_embed`; an
  old LiteLLM process may still expose only `local_embed`.
- Command: `QUIMERA_LLM_API_KEY=<local-placeholder> scripts/test_gw08_embedding_migration.sh`.
- Temporary collection prefix: `gw08_embedding_migration_`.
- Synthetic chunks: 4 indexed, 4 retrieved/used.
- Embedding path: `RagEmbedder factory -> gateway_litellm -> GatewayEmbedClient -> LiteLLM /v1/embeddings -> quimera_embed`.
- Generation path: `LocalGenerator / GatewayChatClient -> LiteLLM local_rag`.
- Rollback path remains: `QUIMERA_RAG_EMBEDDING_BACKEND=direct_ollama`.
- `openclaw_knowledge` was not touched.

Observed GW-08 latencies and parity (2026-04-30):

| Check | Result |
|---|---:|
| embedding/indexing | 314.7 ms |
| retrieval | 27.4 ms |
| generation | 4951.7 ms |
| total pipeline | 4979.1 ms |
| cosine similarity vs direct Ollama | 1.000000 |
| vector dimensions | 768 |

## GW-09 Completed Work

GW-09 adds a traceability guard for Qdrant collection embedding metadata:

```text
Qdrant payload sample
  -> embedding_backend/model/dimensions/contract/alias check
  -> structured warning on drift
  -> hard error only for dimension mismatch by default
```

Key rules:

- The guard samples payloads with `with_payload=True` and `with_vectors=False`.
- It does not mutate, delete, recreate, or reindex collections.
- It does not touch `openclaw_knowledge`.
- Backend, model, contract, alias, and missing metadata drift warn by default.
- Dimension mismatch always raises `EmbeddingDimensionMismatchError`.
- `strict=True` can raise on backend/model/contract/alias mismatch.
- No chunk text, vectors, prompts, secrets, or Authorization headers are logged.
- GW-10 remains the place for `RagRunTrace`.
- GW-11 adds structured RAG observability lifecycle events separately.

Validation expectations:

```bash
git diff --check
uv run pytest -v
uv run mypy --strict .
uv run pyright
uv run pytest tests/smoke/ -v
```

## GW-11 Completed Work

GW-11 adds local structured RAG lifecycle observability events:

```text
embedding/retrieval/generation stage
  -> RagObservabilityEvent safe metadata only
  -> logger.bind(event=...).log(...)
```

Scope:

- `backend/rag/observability.py` defines event kinds, error categories, config,
  safe serialization, emission, and exception categorization.
- `GatewayEmbedClient` emits embedding started/finished/failed events for
  `gateway_litellm`.
- `OllamaEmbedder` emits embedding started/finished/failed events for
  `direct_ollama`.
- `LocalRagPipeline` emits retrieval and generation lifecycle events.
- `config/rag_config.yaml` has `rag.observability` flags and log level.

Safety rules:

- Events contain only safe scalar metadata.
- Events never include query text, prompt text, answer text, chunk text,
  document text, vectors, Qdrant payloads, portfolio data, API keys,
  Authorization headers, tokens, passwords, or secrets.
- No return values change.
- Retry/backoff/concurrency semantics are unchanged.
- Qdrant is not mutated and `openclaw_knowledge` is not touched.

Out of scope:

- OpenTelemetry, Prometheus, Grafana, dashboards, distributed tracing,
  profiling, soak tests, and memory/resource baselines.
- Memory/resource baseline: not implemented in GW-12. Deferred to a future sprint. See ADR-0019 Future Work section.

## GW-20 Completed Work

GW-20 adds the Gateway-1 operational proof-of-life smoke and closes the
Gateway-1 readiness loop before Gateway-2:

```text
dry-run Agent-0
  -> local URL guard
  -> Ollama/Qdrant/LiteLLM probes
  -> live local_chat
  -> live local_rag or explicit fallback
  -> forced Qdrant degradation
  -> policy block no-model-call check
  -> sanitized summary JSON
```

Key files:

- `docs/sprints/GATEWAY1_DONE_CRITERIA.md`
- `scripts/test_gateway1_proof_of_life.py`
- `docs/AGENT0_SMOKE.md`
- `tests/unit/test_gateway1_proof_of_life.py`

Rules:

- The smoke is opt-in with `RUN_GATEWAY1_PROOF_OF_LIFE=1`.
- Live probes refuse non-local service URLs.
- Summary reports do not store answer text, prompts, questions, chunks,
  vectors, payloads, secrets, Authorization headers, raw exceptions or
  tracebacks.
- Forced degradation is injected through Agent-0 hooks; it does not stop Docker,
  mutate Qdrant, reindex, or touch `openclaw_knowledge`.
- Gateway-2 should not begin until GW-20 passes locally.

Live proof result on 2026-05-02:

- Command:
  `QUIMERA_LLM_API_KEY=dev-local-key-change-me RUN_GATEWAY1_PROOF_OF_LIFE=1 uv run python scripts/test_gateway1_proof_of_life.py --output-dir /tmp/openclaw_gateway1_smoke`
- Result: **PASSED** — G1-01 through G1-11 all true.
- Summary: `/tmp/openclaw_gateway1_smoke/gateway1_proof_of_life_9f23ce3df3f2.json`.
- Probes: Ollama OK, Qdrant OK, LiteLLM OK.
- Live runner: `local_chat` OK, `local_rag` OK.
- Forced Qdrant degradation: fallback to `local_chat` with
  `qdrant_unavailable`.
- Policy block: blocked before model call.

Observed live latencies:

| Check | Latency |
|---|---:|
| Ollama probe | 28.6 ms |
| Qdrant probe | 9.4 ms |
| LiteLLM probe | 26.1 ms |
| Agent-0 `local_chat` | 8790.5 ms |
| Agent-0 `local_rag` | 32162.8 ms |
| forced degradation | 0.03 ms |

## G2-01 Current Work

G2-01 starts Gateway-2 with a measurement-only RAG latency baseline:

```text
LocalRagPipeline
  -> RagRunTrace optional segment fields
  -> embed/search/pack/prompt/generation/total timings
  -> safe trace serialization only
```

Scope:

- Extend `RagRunTrace` with optional per-segment fields:
  `routing_ms`, `embedding_ms`, `retrieval_ms`, `context_pack_ms`,
  `prompt_build_ms`, `generation_ms`, `total_ms`, and `run_context`.
- Preserve old trace fields such as `retrieval_latency_ms`,
  `generation_latency_ms`, `prompt_latency_ms`, and `total_latency_ms`.
- Populate pipeline traces from existing `time.perf_counter()` wrappers and
  `Retriever.last_timings`.
- Keep `total_ms` as a directly measured outer timer, not a segment sum.
- Add optional Ollama metric fields, but only when already available in
  metadata. Current LiteLLM path does not expose native Ollama metrics, so
  normal traces record `ollama_metrics_available=false`.

Safety:

- No optimization.
- No prompt/top-k/model/timeout/alias/routing/fallback behavior change.
- No Qdrant mutation, no reindex, no `openclaw_knowledge` access.
- No prompt, question, chunks, answer, vectors, payloads, API keys,
  Authorization headers, raw exceptions or tracebacks in trace serialization.

Deferred from G2-01:

- First optimization experiment: configurable local RAG context budget cap.

## G2-02 Current Work

G2-02 adds a rollback-safe, config-controlled context budget cap for
`local_rag`:

```text
retrieved chunks
  -> existing ContextPacker dedup/token-limit/document ordering
  -> optional whole-chunk max_context_chunks cap
  -> PromptBuilder
  -> LocalGenerator/local_rag
```

Scope:

- Add `rag.context_budget` to `config/rag_config.yaml`:
  `enabled: false`, `max_context_chunks: 3`, `mode: whole_chunks`,
  `apply_to_aliases: [local_rag]`.
- Add typed `ContextBudgetConfig` and `ContextBudgetResult`.
- Apply the cap in `ContextPacker` only, after existing packing logic.
- Preserve whole chunks, citation ids, `doc_id`, `chunk_index`, and payload
  metadata.
- Expose safe trace metadata on `RagRunTrace`:
  `context_budget_enabled`, `context_budget_applied`,
  `context_chunks_retrieved`, `context_chunks_used`,
  `context_chunks_dropped`, `context_budget_max_chunks`, and
  `context_estimated_tokens_used`.

Safety:

- Default `enabled: false` preserves existing behavior.
- Rollback is a single config change.
- No retrieval/top-k/Qdrant/model alias/prompt template/timeout change.
- No Qdrant mutation, no reindex, no `openclaw_knowledge` access.
- No prompt, chunks, answer, vectors, payloads, secrets, Authorization headers,
  raw exceptions or tracebacks in trace serialization.

Deferred:

- Token-based context budgeting.
- Full recalibration of `estimated_remote_tokens_avoided` against the final
  capped prompt.
- Mandatory live Golden Harness before/after gate.

## G2-07 Current Work

G2-07 closes Gateway-2 with an offline baseline freeze and regression gate.
This is not an optimization PR.

Delivered scope:

- Official tracked baseline artifacts under `tests/golden/baseline/`:
  `gateway2_baseline_summary.json`, `gateway2_baseline_results.jsonl`,
  `gateway2_baseline_scores.jsonl`, and
  `gateway2_regression_thresholds.yaml`.
- `scripts/compare_golden_runs.py` now supports:
  `--verify-only <summary.json>` and
  `--baseline <summary.json> --candidate <summary.json> --thresholds <yaml>`.
- Regression gate exit codes:
  `0` pass, `2` schema/sanitization, `3` citation/quality,
  `4` latency, `5` fixture/config mismatch, `6` incompatibility.
- Baseline summaries stay grouped by alias and run type:
  `cold_start`, `warm_model`, and `degraded_qdrant`.
- Generated report directories are ignored while official baseline artifacts
  remain explicitly allowed.

Safety:

- No prompt, question text, answer text, chunks, vectors, payloads, headers,
  API keys, raw exceptions, tracebacks, usernames, local paths or model weight
  paths are allowed in baseline artifacts.
- No remote providers, no live services, no Qdrant mutation, no reindexing and
  no `openclaw_knowledge` access are required for the gate.

Gateway-2 handoff:

- See `docs/GATEWAY2_BASELINE.md`.
- See `docs/sprints/GATEWAY2_SPRINT_HANDOFF.md`.
- Gateway-3 should start from the frozen Gateway-2 baseline and use the offline
  gate before accepting performance or quality regressions.
