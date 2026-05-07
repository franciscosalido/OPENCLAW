#!/usr/bin/env python
"""Verify a controlled Agent-0 corpus manifest without Qdrant writes by default."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.ingestion.pipeline import IngestionOptions, run_ingestion
from backend.ingestion.report import write_report


DEFAULT_MANIFEST = Path("data/corpus/manifest.yaml")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify or explicitly commit the controlled Agent-0 corpus.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to data/corpus/manifest.yaml.",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=None,
        help="Optional path for the sanitized JSON report.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Enable explicit commit mode. Verify-only is the default.",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Optional target collection name for commit mode.",
    )
    parser.add_argument(
        "--allow-pending",
        action="store_true",
        help="Do not fail commit solely because pending/rejected docs were skipped.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_args = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args = parser.parse_args(raw_args)

    if args.commit and not any(argument.startswith("--manifest") for argument in raw_args):
        parser.error("--commit requires an explicit --manifest")
    if args.collection is not None and not args.commit:
        parser.error("--collection is only valid with --commit")

    options = IngestionOptions(
        manifest_path=args.manifest,
        mode="commit" if args.commit else "verify_only",
        fail_on_pending=not args.allow_pending,
        collection=args.collection,
    )
    result = run_ingestion(options)

    if args.report_out is not None:
        write_report(args.report_out, result.report)
    else:
        sys.stdout.write(json.dumps(result.report, indent=2, sort_keys=True) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
