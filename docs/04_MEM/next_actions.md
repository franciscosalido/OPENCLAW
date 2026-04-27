# next_actions.md — Immediate Next Steps

> This file drives the next session. Check it off as you complete items.

**Last updated:** 2026-04-26

---

## Right Now — Normalize Gateway GitHub Workflow

- [ ] Read `docs/sprints/GATEWAY_SPRINT_HANDOFF.md`.
- [ ] Run `git status --short --branch`.
- [ ] Verify GitHub issues and PRs for GW-01, GW-02, GW-03, and GW-04.
- [ ] Backfill missing issues before implementation or PR work.
- [ ] Preserve current local Gateway work before switching branches.
- [ ] Sync local `main` with `git pull --ff-only origin main` only after the
      current work is preserved or intentionally split.

---

## Required Issue Records

| PR | Issue title | Branch |
|---|---|---|
| GW-01 | `[Gateway-01] LiteLLM gateway contracts and semantic aliases` | `feat/gateway-prep-contracts` |
| GW-02 | `[Gateway-02] Local-only LiteLLM install and health scripts` | `feat/gateway-install-health` |
| GW-03 | `[Gateway-03] Route OpenClaw runtime chat through LiteLLM` | `feat/gateway-route-opencraw-litellm` |
| GW-04 | `[Gateway-04] Optional LiteLLM runtime smoke and observability` | `feat/gateway-runtime-smoke` |

---

## Mandatory Workflow Reminder

```bash
cd /Users/fas/projetos/OPENCLAW
git checkout main
git pull --ff-only origin main
gh issue create ...
git checkout -b <feature-branch>
# implement
# validate
git commit -m "<atomic message>"
git push -u origin <feature-branch>
gh pr create --base main --head <feature-branch> ...
```

Do not merge locally into `main` as the final integration step. Final merge
belongs in GitHub after review approval.

Use `/compact` in Claude Code after each PR. Use `/cost` periodically to monitor
token usage.
