# Agent-0 Rollback

Use this runbook only for rolling back the Agent-0 sprint surface.

```bash
git revert <A0_MERGE_COMMIT>
qdrant collection delete openclaw_internal
qdrant collection delete openclaw_financial
uv run pytest tests/unit -v
uv run mypy --strict .
uv run pyright
```

Do not delete `openclaw_knowledge`. It is outside the Agent-0 dual-corpus
bootstrap namespace.
