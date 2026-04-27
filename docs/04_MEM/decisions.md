# decisions.md — Architectural Decisions Log

> Append new decisions. Never delete existing ones. Source of truth for *why* things are the way they are.

---

## ADR-001 — RAG Pipeline: Local Only for RAG-0

**Date:** 2026-04-25 | **Status:** Accepted

**Decision:** RAG-0 is 100% local — Ollama + Qdrant + Python. No LiteLLM, no remote providers, no FastAPI.

**Why:** Minimize surface area for the first working pipeline. Prove the loop locally before adding complexity. Every external dep is a failure point.

**Consequence:** Quality bounded by qwen3:14b local. LiteLLM enters opt-in in Gateway-0.

---

## ADR-002 — No LangChain

**Date:** 2026-04-25 | **Status:** Permanent

**Decision:** LangChain prohibited for chunking and any RAG operation. Pure Python only.

**Why:** ~40 transitive deps for 30 lines of code. Magic in the critical path. Untestable behavior.

---

## ADR-003 — No sentence-transformers

**Date:** 2026-04-25 | **Status:** Permanent

**Decision:** Embedding via Ollama API (`POST /api/embed`). sentence-transformers prohibited.

**Why:** Ollama already runs the model. Two inference services for zero benefit.

---

## ADR-004 — Qdrant: Pinned Version + Docker

**Date:** 2026-04-25 | **Status:** Accepted

**Decision:** `qdrant/qdrant:v1.13.2` pinned. `:latest` prohibited.

**Why:** Reproducibility. `:latest` silently breaks between sessions.

---

## ADR-005 — GitHub as Operational Second Brain

**Date:** 2026-04-25 | **Status:** Accepted

**Decision:** GitHub `docs/04_MEM/` holds live operational state. Obsidian = cognitive second brain (optional, not runtime dependency).

**Why:** After context loss from local/remote divergence, persistent state must live in version control — readable by any Claude instance without prior chat.

---

## ADR-006 — No Redis in V1

**Date:** 2026-04-25 | **Status:** Accepted

**Decision:** No Redis. Gateway-0 caching uses SQLite.

**Why:** Redis is operational complexity for a solo-user tool. SQLite is zero-config and sufficient.

---

## ADR-007 — No Automatic Trading / No Brokerage

**Date:** 2026-04-25 | **Status:** Permanent — not revisable

**Decision:** System will never execute trades, access brokerage APIs, or handle real account credentials.

**Why:** Safety boundary. This is an intelligence tool, not an execution engine.

---

## ADR-008 — uv as Package Manager

**Date:** 2026-04-25 | **Status:** Accepted

**Decision:** `uv` manages all Python dependencies. No direct pip in scripts or CI.

**Why:** Fast, lockfile-based, native pyproject.toml support.

---

## ADR-009 — Security Taxonomy: 3 Levels, No Ambiguity

**Date:** 2026-04-25 | **Status:** Accepted

**Decision:** Level 0 = local only (never remote). Level 1 = sanitized before remote. Level 2 = blocked (credentials, real portfolio).

**Why:** Previous 3-level taxonomy had "Level 2 = remote sensitive" which created a dangerous ambiguity. Renamed: blocked = never leaves machine under any circumstance.

---

## ADR-010 — GitHub Issue/PR Workflow Is Mandatory

**Date:** 2026-04-26 | **Status:** Accepted

**Decision:** GitHub is the operational source of truth for tracked work. Every
PR-sized task must start from synced `main`, have a GitHub Issue before
implementation, use a feature branch from updated `main`, push that branch, open
a GitHub PR, link the PR to the issue, and merge only through GitHub after
approval.

**Why:** Local-only integration created ambiguity around Gateway PR1-PR3 status.
The project needs durable issue/PR history, review state, and merge tracking
that survives agent handoffs and local worktree drift.

**Consequence:** Agents must not treat the local project directory as the final
integration point. If local state is dirty or contains unsplit work, preserve it
first, then normalize GitHub records before starting the next feature.
