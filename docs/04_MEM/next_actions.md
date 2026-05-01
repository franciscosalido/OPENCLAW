# next_actions.md — Immediate Next Steps

> This file drives the next session. Check it off as you complete items.

**Last updated:** 2026-05-01

---

## Right Now — Finish GW-12 Gateway Operational Readiness

- [ ] Read `docs/GATEWAY_FINAL_RUNBOOK.md`.
- [ ] Read `docs/sprints/GATEWAY_SPRINT_HANDOFF.md`.
- [ ] Run `scripts/check_gateway_readiness.sh`.
- [ ] Run unit baseline gates:
      `uv run pytest tests/unit/test_gateway_readiness_script.py tests/unit/test_gateway_final_baseline.py -v`.
- [ ] Run full gates: `uv run pytest -v`, `uv run mypy --strict .`,
      `uv run pyright`, `uv run pytest tests/smoke/ -v`.
- [ ] Open PR for `feat/gateway-operational-readiness`.
- [ ] Merge only in GitHub after review approval.

---

## Required Issue Records

| PR | Issue title | Branch |
|---|---|---|
| GW-12 | `[GW-12] Finalize Gateway-0 operational readiness, runbook, checks and handoff` | `feat/gateway-operational-readiness` |

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
