# AGENTS.md — OpenAI/Codex Memory Entry Point

> Compact operational instructions for OpenAI agents working in OpenClaw.
> The shared cross-agent memory lives in `docs/04_MEM/AGENT_CONTEXT.md`.

## First Reads

Start with the smallest useful context:

1. `git status --short --branch`
2. `docs/04_MEM/AGENT_CONTEXT.md`
3. `docs/04_MEM/current_state.md`
4. `docs/04_MEM/decisions.md`
5. Task-specific files found with `rg`

Do not read `.env`, `.env.*`, `.claude/`, secrets, caches, `.venv`, `dist`, or large generated files.

## Prime Directive

Quimera/OpenClaw is local-first and security-first.

- Product name: Quimera.
- Repository name: OpenClaw.
- RAG-0 is local only.
- Ollama is the local runtime.
- Qwen model: `qwen3:14b`.
- Embedding model: `nomic-embed-text`.
- Vector database: Qdrant.
- Python handles deterministic calculations.
- GitHub is the source of truth for issues, PRs, branches, and merge state.

## Forbidden Without Explicit Human Authorization

- Modify `CLAUDE.md`.
- Modify `.claude/`.
- Read or modify `.env` or `.env.*`.
- Access real portfolio data, real brokerage data, private documents, production databases, or secrets.
- Add LiteLLM, FastAPI, Redis, MCP, or remote AI fallback.
- Install dependencies.
- Commit or push secrets.

## Workflow

Before changes:

1. Restate the task.
2. State risk level.
3. List likely files to touch.
4. State validation plan.
5. Ask for confirmation when risk is medium/high or services/secrets/data/dependencies are affected.

During changes:

- Work one issue per session.
- Prefer small branches and small diffs.
- Use `rg` before opening files.
- Do not use `print()` for diagnostics, scripts, tests, or runtime code. Prefer
  `loguru` logging with secret-safe, prompt-safe messages.
- Stage only intended files.
- Do not touch unrelated dirty worktree files.

After changes:

1. Files changed.
2. What changed.
3. What was intentionally not changed.
4. Validation commands and results.
5. Remaining risks.
6. Next action for Claude/human review.

## Current Pointer

For the latest sprint state, always read:

```bash
sed -n '1,240p' docs/04_MEM/current_state.md
```

For durable coordination rules, read:

```bash
sed -n '1,260p' docs/04_MEM/AGENT_CONTEXT.md
```
