# Gateway Sprint Handoff

> Start the next Gateway cycle by reading this file before touching Git.

**Last updated:** 2026-04-26  
**Repository:** OpenClaw  
**Product:** Quimera  
**Sprint:** Gateway-0 / LiteLLM  

---

## Mandatory GitHub Workflow

The local project directory is not the final integration point. GitHub is the
source of truth for issues, branches, pull requests, review status, and merge
state.

For every tracked PR:

1. Sync local `main`:

```bash
cd /Users/fas/projetos/OPENCLAW
git checkout main
git pull --ff-only origin main
```

2. Open or update a GitHub Issue before implementation.
3. Create the feature branch from updated `main`.
4. Implement locally.
5. Run relevant validations locally.
6. Commit with clear atomic messages.
7. Push the feature branch.
8. Open a GitHub PR from the feature branch to `main`.
9. Link the PR to the issue.
10. Address review comments on the same branch.
11. Merge only in GitHub after approval.
12. After GitHub merge, sync local `main` with `--ff-only`.

Never push directly to `main`. Never use `git push --force`; if unavoidable
after a rebase, use `git push --force-with-lease`.

---

## Current Local Risk

Current observed branch:

```text
feat/gateway-runtime-smoke
```

The working tree currently contains combined Gateway PR1-PR4 changes. This is
valuable work, but it is not yet cleanly represented in GitHub from this local
checkout.

Do not run:

```bash
git reset --hard
git clean -fd
git checkout -- .
```

Do not switch away from the branch until the current work is preserved, split,
or intentionally committed.

Known local risks:

- `origin/main` in this checkout may still point to the older RAG-07 state.
- Gateway PR1-PR3 are user-reported as merged manually, but this checkout still
  needs GitHub verification.
- Many Gateway files are untracked.
- `.gitignore` is modified.
- `uv.lock` is untracked and should not be staged unless intentionally part of
  dependency policy.

---

## Proposed GitHub Records

| PR | Issue title | Branch | PR title |
|---|---|---|---|
| GW-01 | `[Gateway-01] LiteLLM gateway contracts and semantic aliases` | `feat/gateway-prep-contracts` | `feat(gateway): add LiteLLM prep contracts` |
| GW-02 | `[Gateway-02] Local-only LiteLLM install and health scripts` | `feat/gateway-install-health` | `feat(gateway): add local LiteLLM install and health scripts` |
| GW-03 | `[Gateway-03] Route OpenClaw runtime chat through LiteLLM` | `feat/gateway-route-opencraw-litellm` | `feat(gateway): route runtime chat through local LiteLLM` |
| GW-04 | `[Gateway-04] Optional LiteLLM runtime smoke and observability` | `feat/gateway-runtime-smoke` | `feat(gateway): add optional runtime smoke for local LiteLLM` |

---

## Issue Body Templates

### GW-01

Context: Gateway-0 introduces LiteLLM as the local-only model gateway contract.

Objective: add ADR, Blueprint V3.0, semantic aliases, config validation,
gateway exceptions, and contract tests without changing runtime behavior.

Scope: docs, config, `backend/gateway` contracts, unit tests.

Out of scope: remote providers, FastAPI, MCP, quant tools, OpenClaw runtime
routing, RAG behavior changes.

Acceptance criteria: aliases exist, remote providers absent, schema validation
passes, tests pass, no secrets committed.

Risks/follow-ups: keep runtime wiring for later PRs; maintain small Gateway
exception taxonomy.

### GW-02

Context: PR1 created the Gateway contract; PR2 makes local LiteLLM installable
and testable.

Objective: add `infra/litellm` operational scripts and documentation for
starting and checking LiteLLM bound to `127.0.0.1`.

Scope: local config, `.env.example`, start script, healthcheck scripts, setup
docs, script tests.

Out of scope: runtime integration, remote providers, FastAPI, MCP, quant tools,
real portfolio data.

Acceptance criteria: LiteLLM can start locally, `/v1/models` responds,
`local_chat` works through local Qwen, scripts fail clearly, no secrets
committed.

Risks/follow-ups: live checks require local Ollama/LiteLLM; docs must keep MCP
and tooling direction explicitly out of scope.

### GW-03

Context: PR2 made the gateway operational; PR3 routes OpenClaw runtime chat
generation through LiteLLM.

Objective: make application-facing model calls use OpenAI-compatible
`/chat/completions` at `http://127.0.0.1:4000/v1` with semantic aliases.

Scope: gateway client, runtime generation adapter, config defaults, docs, mocked
unit tests.

Out of scope: embeddings-through-gateway, Qdrant changes, retrieval changes,
remote providers, FastAPI, MCP, quant tools.

Acceptance criteria: default route is LiteLLM local, default alias is
`local_chat`, reasoning/RAG/JSON aliases are available, vendor model names stay
out of application-facing defaults, tests pass.

Risks/follow-ups: `_validate_messages` duplication was intentionally temporary
and should be consolidated in GW-04.

### GW-04

Context: PR3 routes runtime calls; PR4 proves the live route with optional smoke
tests and minimal observability.

Objective: add opt-in runtime smoke coverage for
`OpenClaw -> LiteLLM -> Ollama/Qwen` and resolve the temporary message
validation duplication.

Scope: optional smoke script/test, LiteLLM health helper if narrow, minimal
debug observability, docs, validation cleanup.

Out of scope: embeddings-through-gateway, Qdrant/retrieval/chunking changes,
remote providers, FastAPI, MCP, quant tools, real portfolio prompts.

Acceptance criteria: normal tests skip live smoke by default, `RUN_LITELLM_SMOKE=1`
enables live checks, smoke uses only synthetic prompts and local aliases, no
secrets are printed, existing tests pass.

Risks/follow-ups: live smoke requires local LiteLLM and Ollama; if services are
down, failures must be clear and secret-safe.

---

## Exact Command Plan For Normalization

First inspect without changing history:

```bash
cd /Users/fas/projetos/OPENCLAW
git status --short --branch
git branch -vv
gh auth status
gh issue list --state open
gh pr list --state all --limit 20
```

Create issue body files in `/tmp` manually from the templates above, then:

```bash
gh issue create --title "[Gateway-01] LiteLLM gateway contracts and semantic aliases" --body-file /tmp/gateway-01-issue.md --label codex-task --label local-only
gh issue create --title "[Gateway-02] Local-only LiteLLM install and health scripts" --body-file /tmp/gateway-02-issue.md --label codex-task --label local-only
gh issue create --title "[Gateway-03] Route OpenClaw runtime chat through LiteLLM" --body-file /tmp/gateway-03-issue.md --label codex-task --label local-only
gh issue create --title "[Gateway-04] Optional LiteLLM runtime smoke and observability" --body-file /tmp/gateway-04-issue.md --label codex-task --label local-only
```

If PR1-PR3 are already present on GitHub, link or comment on those issues with
the existing PR URLs instead of recreating duplicate PRs.

If PR1-PR3 are not present on GitHub, preserve current work before syncing:

```bash
git status --short --branch
git diff --stat
git diff --check
```

Then decide one of these safe paths:

- commit a temporary preservation branch with explicit files;
- split patches into the four target branches;
- create a worktree backup before replaying from `main`.

After preservation:

```bash
git checkout main
git pull --ff-only origin main
```

Then replay each branch from updated `main`, validate, push, and open the PR:

```bash
git checkout -b feat/gateway-prep-contracts
# apply GW-01 files
uv run pytest tests/unit/test_gateway_config.py tests/unit/test_gateway_health.py tests/unit/test_gateway_errors.py -v
git status --short --branch
git add <gw-01-files>
git commit -m "feat(gateway): add LiteLLM prep contracts"
git push -u origin feat/gateway-prep-contracts
gh pr create --base main --head feat/gateway-prep-contracts --title "feat(gateway): add LiteLLM prep contracts" --body-file /tmp/gateway-01-pr.md
```

Repeat the same pattern for GW-02, GW-03, and GW-04.

---

## Last Known PR4 Validation

The PR4 local bundle previously passed:

```bash
uv run pytest -v
uv run mypy --strict . || true
uv run pyright || true
uv run python -m compileall backend scripts infra tests || true
git diff --check
```

Observed result:

```text
115 passed, 2 skipped, 35 subtests passed
mypy: success
pyright: 0 errors
compileall: success
git diff --check: success
```

Live smoke with a fake local key failed clearly because LiteLLM was not running
at `127.0.0.1:4000`. No secrets were printed.

---

## Next Cycle Start

Start with:

```bash
cd /Users/fas/projetos/OPENCLAW
git status --short --branch
sed -n '1,260p' docs/sprints/GATEWAY_SPRINT_HANDOFF.md
```

Then normalize GitHub records before doing new Gateway implementation work.
