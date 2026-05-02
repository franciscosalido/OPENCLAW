# Agent-0 Golden Questions

This directory contains the stable synthetic question registry for the Agent-0
golden benchmark harness.

Reports are written to `tests/golden/reports/` and are intentionally ignored by
Git. Do not commit generated reports unless a future baseline-update issue
explicitly authorizes it.

Baseline policy:

- The registry is synthetic-only.
- No real tickers, companies, funds, portfolios or private data are allowed.
- Dry-run reports are useful for schema validation only.
- The first live baseline should preferably use the median of 3 local runs.
- Live baseline publication is deferred until an explicit future decision.
