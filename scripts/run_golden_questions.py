#!/usr/bin/env python
"""Run Agent-0 golden question citation checks without answer generation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from backend.agent0.golden_questions import (
    GoldenMode,
    run_golden_questions,
    write_golden_report,
)


SMOKE_GUARD_ENV = "RUN_GOLDEN_SMOKE"


def build_parser() -> argparse.ArgumentParser:
    """Build the golden questions CLI parser."""

    parser = argparse.ArgumentParser(
        description="Validate Agent-0 golden question citations without answers.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Run offline with fake retrieval. This is the default.",
    )
    mode.add_argument(
        "--smoke",
        action="store_true",
        help="Run opt-in smoke mode guarded by RUN_GOLDEN_SMOKE=1.",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=None,
        help="Optional sanitized JSON report path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the golden questions harness."""

    parser = build_parser()
    args = parser.parse_args(argv)
    mode: GoldenMode = "smoke" if args.smoke else "dry_run"
    if mode == "smoke" and os.environ.get(SMOKE_GUARD_ENV) != "1":
        sys.stderr.write("Smoke mode requires RUN_GOLDEN_SMOKE=1.\n")
        return 2
    if mode == "smoke":
        sys.stderr.write("Smoke retriever is not wired in A0-PR03.\n")
        return 2

    result = run_golden_questions(mode=mode)
    rendered = json.dumps(result.report, indent=2, sort_keys=True) + "\n"
    if args.report_out is not None:
        write_golden_report(args.report_out, result.report)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
