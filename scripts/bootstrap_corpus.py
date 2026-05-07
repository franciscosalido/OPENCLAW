#!/usr/bin/env python
"""Bootstrap one controlled Agent-0 corpus into its mapped collection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from backend.ingestion.bootstrap import BootstrapOptions, CorpusName, run_bootstrap
from backend.ingestion.report import IngestionMode
from backend.ingestion.commit_store import QdrantIngestionCommitStore


def build_parser() -> argparse.ArgumentParser:
    """Build the bootstrap CLI parser."""

    parser = argparse.ArgumentParser(
        description="Verify or explicitly commit a controlled Agent-0 corpus.",
    )
    parser.add_argument(
        "--corpus",
        choices=("internal", "financial"),
        required=True,
        help="Corpus namespace to bootstrap.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Validate, chunk and report without Qdrant mutation. This is the default.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Explicitly commit to the mapped Qdrant collection.",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=None,
        help="Optional sanitized JSON report path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the bootstrap CLI."""

    raw_args = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args = parser.parse_args(raw_args)

    if args.verify_only and args.commit:
        parser.error("--verify-only and --commit cannot be used together")

    corpus = cast(CorpusName, args.corpus)
    mode: IngestionMode = "commit" if args.commit else "verify_only"
    result = run_bootstrap(
        BootstrapOptions(
            corpus=corpus,
            mode=mode,
            report_out=args.report_out,
        ),
        commit_store=QdrantIngestionCommitStore(
            collection_name=(
                "openclaw_internal" if corpus == "internal" else "openclaw_financial"
            ),
            corpus=corpus,
        )
        if args.commit
        else None,
    )

    rendered = json.dumps(result.report, indent=2, sort_keys=True) + "\n"
    if args.report_out is not None:
        args.report_out.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
