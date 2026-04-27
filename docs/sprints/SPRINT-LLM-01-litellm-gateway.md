# Sprint LLM-01: LiteLLM Gateway

## Mandatory Workflow

All Gateway PRs use GitHub as the source of truth:

1. Sync `main` with `git pull --ff-only origin main`.
2. Open or update a GitHub Issue before implementation.
3. Branch from updated `main`.
4. Implement, validate, commit, push.
5. Open a GitHub PR and link it to the issue.
6. Merge only through GitHub after approval.

The current local checkout contains combined PR1-PR4 work. Normalize GitHub
issues/PRs and preserve local work before starting PR4 review or PR5 planning.

## Goal

Introduce LiteLLM as a local-only model gateway for Quimera/OpenClaw.

## PR 1: Gateway Prep Contracts

Branch: `feat/gateway-prep-contracts`  
Issue title: `[Gateway-01] LiteLLM gateway contracts and semantic aliases`  
PR title: `feat(gateway): add LiteLLM prep contracts`  
Status: user-reported merged manually; GitHub issue/PR tracking must be
backfilled or verified.

Delivered:

- ADR and Blueprint V3.0.
- Semantic aliases: `local_chat`, `local_think`, `local_rag`, `local_json`,
  `local_embed`.
- Gateway exception taxonomy.
- Pydantic config validation and contract tests.
- Semantic gateway health check contracts.

Risk posture after PR 1:

- Missing aliases are caught by tests.
- Remote provider config is rejected by validation.
- `thinking_mode` is a tested contract.
- Gateway exceptions are local domain exceptions, not LiteLLM internals.

## PR 2: Gateway Install And Health

Branch: `feat/gateway-install-health`  
Issue title: `[Gateway-02] Local-only LiteLLM install and health scripts`  
PR title: `feat(gateway): add local LiteLLM install and health scripts`  
Status: user-reported merged manually; GitHub issue/PR tracking must be
backfilled or verified.

Scope:

- Add `infra/litellm/` operational directory.
- Install LiteLLM in an isolated venv.
- Start LiteLLM on `127.0.0.1:4000`.
- Validate `/v1/models`.
- Validate a short `local_chat` call through Qwen/Ollama.
- Add local healthcheck scripts.

Out of scope:

- OpenClaw runtime wiring to LiteLLM.
- Remote providers.
- FastAPI.
- Redis.
- Quant tools.
- Real portfolio data.

Merge criteria:

- Shell scripts fail clearly when dependencies or services are missing.
- LiteLLM config contains only local Ollama aliases.
- Existing tests pass.
- `python -m compileall` or equivalent compile check is clean.
- Health scripts pass when Ollama and LiteLLM are running locally.

## PR 3: Runtime Route Through LiteLLM

Branch: `feat/gateway-route-opencraw-litellm`  
Issue title: `[Gateway-03] Route OpenClaw runtime chat through LiteLLM`  
PR title: `feat(gateway): route runtime chat through local LiteLLM`  
Status: user-reported merged manually; GitHub issue/PR tracking must be
backfilled or verified.

Delivered:

- Runtime chat/generation calls route through LiteLLM `/v1/chat/completions`.
- Default base URL is `http://127.0.0.1:4000/v1`.
- Application-facing defaults use semantic aliases, not vendor model names.
- Qdrant, retrieval, chunking, embeddings, and prompt construction remain
  unchanged.

## PR 4: Runtime Smoke

Branch: `feat/gateway-runtime-smoke`  
Issue title: `[Gateway-04] Optional LiteLLM runtime smoke and observability`  
PR title: `feat(gateway): add optional runtime smoke for local LiteLLM`  
Status: current / in progress; local changes present and must be preserved
before branch operations.

Scope:

- Optional live smoke tests guarded by `RUN_LITELLM_SMOKE=1`.
- Script smoke for `local_chat`, `local_think`, `local_rag`, and `local_json`.
- Minimal gateway observability: alias, local endpoint host, latency, status,
  and error category.
- No Qdrant, embeddings, remote providers, FastAPI, MCP, or quant tools.

## Normalization Commands

Do not run destructive commands while the current worktree is dirty. First
inspect and preserve the local Gateway work:

```bash
cd /Users/fas/projetos/OPENCLAW
git status --short --branch
git branch -vv
gh issue list --state open
gh pr list --state all --limit 20
```

Create or backfill issues:

```bash
gh issue create --title "[Gateway-01] LiteLLM gateway contracts and semantic aliases" --body-file /tmp/gateway-01-issue.md --label codex-task --label local-only
gh issue create --title "[Gateway-02] Local-only LiteLLM install and health scripts" --body-file /tmp/gateway-02-issue.md --label codex-task --label local-only
gh issue create --title "[Gateway-03] Route OpenClaw runtime chat through LiteLLM" --body-file /tmp/gateway-03-issue.md --label codex-task --label local-only
gh issue create --title "[Gateway-04] Optional LiteLLM runtime smoke and observability" --body-file /tmp/gateway-04-issue.md --label codex-task --label local-only
```

Only after local Gateway work is preserved or intentionally split:

```bash
git checkout main
git pull --ff-only origin main
```

Then replay each PR from updated `main` if GitHub does not already contain it.
