# Agent-0 Golden Questions

This directory contains the stable synthetic question registry for the Agent-0
golden benchmark harness.

A0-PR03 uses only the split citation manifests:

- `internal_questions.yaml`
- `financial_questions.yaml`

The pre-existing `questions.yaml` file belongs to the older Gateway golden
question harness and uses a different schema. It is not an A0-PR03
super-manifest and is not loaded by `scripts/run_golden_questions.py`.

Reports are written to `tests/golden/reports/` and are intentionally ignored by
Git. Do not commit generated reports unless a future baseline-update issue
explicitly authorizes it.

Baseline policy:

- The registry is synthetic-only.
- No real tickers, companies, funds, portfolios or private data are allowed.
- Dry-run reports are useful for schema validation only.
- The first live baseline should preferably use the median of 3 local runs.
- Live baseline publication is deferred until an explicit future decision.
