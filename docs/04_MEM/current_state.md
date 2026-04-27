# current_state.md — OPENCLAW Operational Memory

> Volatile project state for Codex, Claude Code, ChatGPT Thinking, and human
> review. Read after `docs/04_MEM/AGENT_CONTEXT.md`. Update at the end of
> meaningful sessions.

**Last updated:** 2026-04-26
**Updated by:** Codex — Gateway workflow normalization handoff

---

## Active Sprint: Gateway-0 / LiteLLM

**Goal:** make LiteLLM the local-only model gateway for OpenClaw runtime model
calls while preserving existing RAG/Qdrant behavior.

**Hard constraints:**

- Local only.
- No remote providers.
- No FastAPI.
- No MCP.
- No quant tools.
- No secrets or real portfolio data.
- No final local merge into `main`; GitHub PR approval is the integration path.

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

## Current Local State Warning

Current observed branch:

```text
feat/gateway-runtime-smoke
```

Current observed risk:

- The working tree contains mixed Gateway PR1-PR4 modifications and untracked
  files.
- Local `main`/`origin/main` may not reflect the user-reported manual Gateway
  merges yet.
- Do not run `git reset`, `git clean`, destructive checkout, or broad stash
  commands until the Gateway changes are intentionally preserved or split.
- `uv.lock` is untracked; decide deliberately whether dependency lock changes
  belong in a PR.
- `.gitignore` is modified; decide deliberately whether the `.claude/worktrees/`
  ignore rule belongs in a PR.

Read `docs/sprints/GATEWAY_SPRINT_HANDOFF.md` before the next Gateway action.

---

## Gateway PR Tracking

| PR | Branch | User-reported state | Local verification state | Next action |
|---|---|---|---|---|
| GW-01 | `feat/gateway-prep-contracts` | Merged manually | Backfill issue/PR status in GitHub | Normalize records |
| GW-02 | `feat/gateway-install-health` | Merged manually | Backfill issue/PR status in GitHub | Normalize records |
| GW-03 | `feat/gateway-route-opencraw-litellm` | Merged manually | Backfill issue/PR status in GitHub | Normalize records |
| GW-04 | `feat/gateway-runtime-smoke` | In progress | Local changes present | Preserve/split, then open PR |

Proposed issue and PR titles are recorded in
`docs/sprints/GATEWAY_SPRINT_HANDOFF.md`.

---

## Last Known Validation

Before this documentation handoff, the Gateway PR4 local work had passed:

```bash
uv run pytest -v
uv run mypy --strict . || true
uv run pyright || true
uv run python -m compileall backend scripts infra tests || true
git diff --check
```

Observed result from the prior local run:

```text
115 passed, 2 skipped, 35 subtests passed
mypy: success
pyright: 0 errors
compileall: success
git diff --check: success
```

Live LiteLLM smoke was attempted with a fake local key and failed clearly because
LiteLLM was not running at `127.0.0.1:4000`. No secrets were printed.

---

## Next Recommended Move

1. Preserve the current Gateway work before any branch switch.
2. Backfill GitHub issues for GW-01 through GW-04.
3. Verify whether the manual merges are actually present on GitHub `main`.
4. If not, split or replay the local Gateway changes into the required PR chain.
5. Do not begin a new feature PR until GW-01 through GW-03 are represented in
   GitHub and local `main` is synchronized.
