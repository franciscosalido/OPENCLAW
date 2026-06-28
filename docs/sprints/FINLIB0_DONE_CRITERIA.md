# FINLIB-0 Done Criteria

Status: Closeout checklist

## Required Commands

- [ ] `uv run pytest tests/unit -q`
- [ ] `uv run pytest tests/integration -q`
- [ ] `uv run pytest tests/architecture -q`
- [ ] `uv run pytest -q`
- [ ] `uv run mypy --strict .`
- [ ] `uv run pyright`
- [ ] `uvx ruff check .`
- [ ] `uvx ruff format --check .`
- [ ] `uvx sqlfluff lint backend/memory/postgres/migrations --dialect postgres`
- [ ] `uvx --from import-linter lint-imports`
- [ ] `python scripts/check_finlib_readiness.py --json` returns `READY`
- [ ] No destructive retention policy is present.
- [ ] `docs/data/DATA_DICTIONARY.md` is complete.
- [ ] `docs/sprints/FINLIB0_HANDOFF_TO_DATA_AGENTS.md` is complete.
- [ ] code-sandbox-mcp validation is complete.

## Go

FINLIB-0 is Go only when:

- readiness status is `READY`;
- `ready_for_data_agents` is `true`;
- all tests pass in code-sandbox-mcp or the reviewer records explicit
  environment skips;
- migration checksums have no drift;
- memory boundary tests pass;
- import-linter contracts pass;
- no Qdrant/pgvector boundary drift exists;
- no destructive retention policy exists;
- repositories import and write only through audited transactions.

## No-Go

FINLIB-0 is No-Go when:

- readiness status is `BLOCKED`;
- `ready_for_data_agents` is `false`;
- any destructive retention/drop/delete/truncate policy is detected;
- audit layer is missing;
- repositories fail to import;
- migrations are not applied through head `029`;
- memory boundary is broken;
- data dictionary or handoff docs are missing.

## Explicit Non-Goals

- Data agents;
- Kronos execution;
- model downloads;
- Qdrant mutation;
- pgvector mutation;
- destructive retention;
- broker or portfolio access.
