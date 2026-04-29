# decisions.md — Architectural Decisions Log

> Append new decisions. Never delete existing ones. Source of truth for *why* things are the way they are.

---

## ADR Change Protocol — Meta-Rule (added 2026-04-29)

An ADR may be changed during the project, but **never silently**.
If a decision changes, do one of the following:
- amend the ADR with dated rationale
- supersede it with a new ADR
- mark it deprecated if no longer valid

Never rewrite history as if the old architectural decision never existed.

### Revisability tiers

| Tier | Examples | How to change |
|---|---|---|
| **Non-revisable** | ADR-007 (no trade execution) | Cannot be changed |
| **Strongly restricted** | ADR-012 (Level 0 data) | Explicit security review + new ADR required |
| **Sprint-bound** | ADR-002 (no LangChain), ADR-003 (no sentence-transformers), ADR-006 (no Redis), no FastAPI | May be revisited at explicit sprint approval |
| **Implementation strategy** | All other ADRs | May evolve as the system matures |

---

## ADR-001 — RAG Pipeline: Local Only for RAG-0

**Date:** 2026-04-25 | **Status:** Accepted

**Decision:** RAG-0 is 100% local — Ollama + Qdrant + Python. No LiteLLM, no remote providers, no FastAPI.

**Why:** Minimize surface area for the first working pipeline. Prove the loop locally before adding complexity. Every external dep is a failure point.

**Consequence:** Quality bounded by qwen3:14b local. LiteLLM enters opt-in in Gateway-0.

---

## ADR-002 — No LangChain

**Date:** 2026-04-25 | **Status:** Sprint-bound — revisable after explicit sprint approval

**Decision:** LangChain prohibited for chunking and any RAG operation. Pure Python only.

**Why:** ~40 transitive deps for 30 lines of code. Magic in the critical path. Untestable behavior.

---

## ADR-003 — No sentence-transformers

**Date:** 2026-04-25 | **Status:** Sprint-bound — revisable after explicit sprint approval

**Decision:** Embedding via Ollama API (`POST /api/embed`). sentence-transformers prohibited.

**Why:** Ollama already runs the model. Two inference services for zero benefit.

---

## ADR-004 — Qdrant: Pinned Version + Docker

**Date:** 2026-04-25 | **Status:** Accepted

**Decision:** `qdrant/qdrant:v1.13.2` pinned. `:latest` prohibited.

**Why:** Reproducibility. `:latest` silently breaks between sessions.

---

## ADR-005 — GitHub as Operational Second Brain

**Date:** 2026-04-25 | **Status:** Accepted — expanded by ADR-011

**Decision:** GitHub `docs/04_MEM/` holds live operational state. Obsidian = cognitive second brain (optional, not runtime dependency).

**Why:** After context loss from local/remote divergence, persistent state must live in version control — readable by any Claude instance without prior chat.

---

## ADR-006 — No Redis in V1

**Date:** 2026-04-25 | **Status:** Sprint-bound — revisable after explicit sprint approval

**Decision:** No Redis. Gateway-0 caching uses SQLite.

**Why:** Redis is operational complexity for a solo-user tool. SQLite is zero-config and sufficient.

---

## ADR-007 — No Trade Execution / No Broker Access

**Date:** 2026-04-25 | **Status:** Accepted — NON-REVISABLE
**Amended:** 2026-04-29 — expanded scope and enforcement rules

**Decision:** The system must never execute trades, send orders, rebalance automatically, log into broker accounts, or directly access any brokerage interface or exchange account.

This prohibition includes:
- order placement or cancellation
- portfolio rebalancing execution
- API key usage for broker operations
- headless browser automation against brokerage portals
- account login, session handling, or credential storage
- "assistive" click automation for trading actions

**Why:** OPENCLAW / QUIMERA is an intelligence, analysis, memory, and decision-support system — not an execution system. Trade execution introduces financial liability, regulatory risk, credential compromise risk, accidental automation risk, and unacceptable blast radius from model or prompt failure. Even a "human-in-the-loop" implementation creates pressure toward unsafe automation and must remain outside project scope.

**Allowed:** research, education, simulation, portfolio analysis, scenario generation, risk explanation, checklist generation, recommendation drafts marked as non-executable.

**Forbidden:** any code path capable of touching a real broker or exchange; any integration trivially upgradable into real execution; storing broker secrets for future use.

**Enforcement:**
- no brokerage SDKs in dependencies
- no broker credentials in env files
- no browser automation targeting broker sites
- CI must reject any module introducing trading endpoints or execution adapters
- PR review treats broker access as a hard stop

---

## ADR-008 — uv as Package Manager

**Date:** 2026-04-25 | **Status:** Accepted

**Decision:** `uv` manages all Python dependencies. No direct pip in scripts or CI.

**Why:** Fast, lockfile-based, native pyproject.toml support.

---

## ADR-009 — Security Taxonomy: 3 Levels, No Ambiguity

**Date:** 2026-04-25 | **Status:** Accepted — expanded by ADR-012 and ADR-013

**Decision:** Level 0 = local only (never remote). Level 1 = sanitized before remote. Level 2 = blocked (credentials, real portfolio).

**Why:** Previous 3-level taxonomy had "Level 2 = remote sensitive" which created a dangerous ambiguity. Renamed: blocked = never leaves machine under any circumstance.

---

## ADR-010 — GitHub Issue/PR Workflow Is Mandatory

**Date:** 2026-04-26 | **Status:** Accepted — formalized and expanded by ADR-011

**Decision:** GitHub is the operational source of truth for tracked work. Every PR-sized task must start from synced `main`, have a GitHub Issue before implementation, use a feature branch from updated `main`, push that branch, open a GitHub PR, link the PR to the issue, and merge only through GitHub after approval.

**Why:** Local-only integration created ambiguity around Gateway PR1-PR3 status. The project needs durable issue/PR history, review state, and merge tracking that survives agent handoffs and local worktree drift.

**Consequence:** Agents must not treat the local project directory as the final integration point. If local state is dirty or contains unsplit work, preserve it first, then normalize GitHub records before starting the next feature.

---

## ADR-011 — GitHub as Source of Truth for CI/CD Workflow

**Date:** 2026-04-29 | **Status:** Accepted — formalizes and expands ADR-010

**Decision:** GitHub is the official source of truth for the full development lifecycle.

Mandatory flow: `Issue → Branch → Commit(s) → Pull Request → CI → Review → Merge on GitHub → Local sync`

No feature, fix, or refactor is considered complete with only local changes. Official integration occurs only after an approved, merged PR on GitHub.

**Workflow:**
1. Create or link an Issue with context, objective, scope, out-of-scope, and acceptance criteria.
2. Update local `main` from `origin/main`.
3. Create branch from updated `main`.
4. Implement locally with small, atomic commits.
5. Open PR on GitHub linked to the Issue.
6. Run CI on the PR (lint, type-check, tests, build validations).
7. Pass technical review.
8. Merge on GitHub — never treat local merge as final integration.
9. Sync local `main` after merge; delete branch when safe.

**Hard rules:**
- Prohibited: treating local `main` as final source
- Prohibited: final-only local merge
- Prohibited: direct push to `main`
- Rebase or force push only with explicit care; prefer `--force-with-lease`
- Every PR must link issue, description, validations executed, and known risks

---

## ADR-012 — Level 0 Portfolio Data Must Always Stay Local

**Date:** 2026-04-29 | **Status:** Accepted — strongly restricted, revisable only by explicit security review + new ADR

**Decision:** Level 0 data (real portfolio holdings, account balances, transaction history, tax identifiers, personally identifying financial records, any data that can reconstruct the actual investor position) must remain strictly local.

Level 0 data must never be:
- sent to remote LLMs
- stored in remote vector databases
- copied to third-party SaaS
- included in telemetry
- exported in logs
- embedded into remote prompts
- exposed through public or network-accessible services by default

**Allowed:** local parsing, local embeddings, local retrieval, local summarization, local indexing in local Qdrant, local-only audit trails.

**Forbidden:** remote inference with raw Level 0 data; remote embeddings; remote backups without explicit encryption and separate approval; analytics pipelines exporting identifiable portfolio state.

**Enforcement:**
- classify inputs before routing
- Level 0 automatically forces local-only path
- CI and code review must reject remote code paths reachable from Level 0 routing
- logs must redact identifiers and balances by default
- config defaults to local loopback endpoints only

---

## ADR-013 — Local-First Inference Routing

**Date:** 2026-04-29 | **Status:** Accepted

**Decision:** Default inference path is always local. Remote inference is opt-in, policy-gated, logged, and blocked for Level 0 data.

**Why:** Security posture. Protects sensitive financial context by default. Remote paths require explicit sprint authorization.

---

## ADR-014 — Qdrant Is Memory, Not Model

**Date:** 2026-04-29 | **Status:** Accepted

**Decision:** Qdrant is the retrieval/memory layer. LiteLLM/Ollama is the inference layer. These concerns must remain separate and independently testable.

**Why:** Clear separation prevents cross-contamination of retrieval state and generation logic. Each layer must be testable in isolation.

---

## ADR-015 — No Hidden Remote Calls

**Date:** 2026-04-29 | **Status:** Accepted

**Decision:** No module may silently call a remote provider. Every remote path must be explicit, reviewable, configurable, and auditable.

**Why:** Silent remote calls are a security and privacy violation in a local-first system handling financial data.

---

## ADR-016 — Prompt and Retrieval Logging Policy

**Date:** 2026-04-29 | **Status:** Accepted

**Decision:** Only safe metadata may be logged by default. Raw sensitive prompts and retrieved financial content must not be logged unless explicitly redacted and locally stored.

**Why:** Prevents accidental exfiltration of Level 0 data through log pipelines. Logs are often the largest unmonitored data path in ML systems.

---

## ADR-017 — Human Advisory Only

**Date:** 2026-04-29 | **Status:** Accepted

**Decision:** The system may produce analysis, options, and checklists, but must not represent itself as fiduciary, discretionary, or autonomous execution software.

**Why:** Legal, ethical, and regulatory boundary. OPENCLAW / QUIMERA is a decision-support and intelligence tool, not a financial advisor or execution engine.
