#!/usr/bin/env python
"""Public OpenClaw CLI."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from backend.agent0.openclaw import Answer, OpenClaw


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenClaw local-first CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ask_parser = subparsers.add_parser("ask", help="Ask one local Agent-0 question.")
    ask_parser.add_argument("question", help="Question to answer locally.")
    ask_parser.add_argument("--json", action="store_true", help="Emit safe JSON.")
    ask_parser.add_argument(
        "--debug",
        action="store_true",
        help="Include safe error category only; never traceback.",
    )
    return parser.parse_args(argv)


def render_answer(answer: Answer, *, json_output: bool) -> str:
    """Render an answer without exposing prompt, chunks or payloads."""

    if json_output:
        return json.dumps(answer.to_dict(), ensure_ascii=False, sort_keys=True)
    lines = [answer.answer]
    if answer.citations:
        lines.append("")
        lines.append("Citations:")
        for citation in answer.citations:
            lines.append(
                "- "
                f"{citation.doc_id}#{citation.chunk_index} "
                f"({citation.collection_name})"
            )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if args.command == "ask":
            answer = OpenClaw().ask(args.question)
            sys.stdout.write(render_answer(answer, json_output=args.json) + "\n")
            return 1 if answer.error_category else 0
        return 2
    except Exception as exc:
        error = {"error_category": exc.__class__.__name__.lower()}
        sys.stderr.write(json.dumps(error, sort_keys=True) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
