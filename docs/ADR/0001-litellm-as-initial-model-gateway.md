# ADR-0001: LiteLLM as Initial Model Gateway

**Status:** Accepted
**Date:** 2026-04-26

## Context

Quimera/OpenClaw is a local-first, security-first, multi-agent assistant. RAG-0
proved local retrieval with Qdrant, Ollama, Qwen, and synthetic documents.
Gateway-0 prepares the next boundary: all model calls should eventually pass
through one configurable gateway instead of each agent or module choosing
providers directly.

## Decision

Use LiteLLM as the initial model gateway contract for Quimera/OpenClaw.

Gateway-0 defines semantic aliases:

- `local_chat`
- `local_think`
- `local_rag`
- `local_json`
- `local_embed`

The chat aliases map to local Ollama/Qwen. The embedding alias maps to local
Ollama/nomic-embed-text. Remote providers are not enabled in this PR.

RAG storage stays in Qdrant. LiteLLM is only the future gateway for model calls:
chat, reasoning, structured output, and embeddings. Vector CRUD, retrieval,
chunking, context packing, and prompt construction remain in the existing Python
RAG modules.

FastAPI is intentionally outside the MVP path. The first gateway steps are
configuration, contracts, local CLI usage, and tests. HTTP service boundaries can
be introduced later only with explicit approval.

## Consequences

Positive:

- Agents can request semantic model capabilities instead of hardcoded models.
- Local-only behavior remains the default.
- Future remote fallback must be added explicitly behind sanitization and audit.
- Existing RAG behavior is preserved while the gateway contract is reviewed.

Tradeoffs:

- This PR does not route runtime calls through LiteLLM yet.
- Thinking/no-thinking behavior is represented as alias metadata until adapter
  wiring is implemented.
- Operators must run Ollama locally before the future gateway can serve models.

## Guardrails

- No secrets in repository config.
- No remote providers enabled by default.
- No FastAPI in Gateway-0.
- No quant tools in this sprint.
- No changes to Claude/Cowork-specific files.
- Gateway PRs must follow the mandatory GitHub workflow: issue first, branch
  from updated `main`, push branch, open PR, link issue, and merge only in
  GitHub after approval.
