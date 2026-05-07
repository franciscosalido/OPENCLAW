# ADR-001: RAG Pipeline Local-Only

**Status:** Accepted
**Date:** 2026-04-26

## Context

Quimera/OpenClaw needs a retrieval pipeline that can ground local answers in a
known corpus without sending private context outside the machine. RAG-0 is the
first proof-of-life sprint for this capability.

## Decision

RAG-0 is local-only:

- Ollama provides embeddings and generation.
- `nomic-embed-text` provides 768-dimensional embeddings.
- `qwen3:14b` provides local generation.
- Qdrant runs locally via Docker.
- Python modules orchestrate deterministic retrieval, prompt construction, and tests.
- Synthetic documents are used for tests and smoke workflows.

RAG-0 explicitly excludes:

- LiteLLM
- Redis
- FastAPI
- remote AI providers
- LangChain
- sentence-transformers
- real portfolio, brokerage, credential, or private document data

## Consequences

Positive:

- The MVP can be tested without external providers.
- Security boundaries are simple and auditable.
- GitHub PRs can validate behavior with fakes and in-memory Qdrant.

Tradeoffs:

- Real answer quality depends on the local model.
- Real-service smoke requires local Ollama models and Docker Qdrant.
- Gateway-0 must later add remote routing and sanitization explicitly.

## Follow-Ups

- Gateway-0 may introduce LiteLLM after RAG-0 is green.
- Validation helpers live in `backend/rag/_validation.py`.
- Qdrant client/server versions should stay aligned.
