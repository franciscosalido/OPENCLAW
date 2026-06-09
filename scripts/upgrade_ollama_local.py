"""Dry-run-first Ollama local upgrade policy helper.

This script does not install Ollama by default. On macOS it reports a manual
upgrade plan because Ollama may be managed by the desktop app, Homebrew, or the
standalone CLI installer.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from backend.rag.ollama_embedding_bakeoff import (
    OLLAMA_KNOWN_PRERELEASES,
    OLLAMA_LATEST_STABLE_KNOWN,
    select_latest_stable,
)


@dataclass(frozen=True, slots=True)
class OllamaUpgradePlan:
    """Safe upgrade plan; no command execution is embedded."""

    schema_version: str
    dry_run: bool
    execute_requested: bool
    target_version: str
    allow_prerelease: bool
    selected_version: str | None
    operating_system: str
    action: str
    reversible: bool
    notes: tuple[str, ...]

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dry_run": self.dry_run,
            "execute_requested": self.execute_requested,
            "target_version": self.target_version,
            "allow_prerelease": self.allow_prerelease,
            "selected_version": self.selected_version,
            "operating_system": self.operating_system,
            "action": self.action,
            "reversible": self.reversible,
            "notes": self.notes,
        }


def build_upgrade_plan(
    *,
    execute: bool,
    target_version: str,
    allow_prerelease: bool,
    known_releases: Sequence[str] = (
        OLLAMA_LATEST_STABLE_KNOWN,
        *tuple(sorted(OLLAMA_KNOWN_PRERELEASES)),
    ),
) -> OllamaUpgradePlan:
    """Build a D2P upgrade plan without mutating the local machine."""
    selected = select_latest_stable(known_releases, allow_prerelease=allow_prerelease)
    notes = [
        "Ollama runs outside Docker in Quimera/OpenClaw.",
        "Upgrade is D2P/reversible; rollback by reinstalling previous stable.",
        "Pre-release versions require --allow-prerelease.",
    ]
    if execute:
        notes.append(
            "Execute mode records intent only; install through Ollama app/CLI package manager."
        )
    return OllamaUpgradePlan(
        schema_version="ollama-local-upgrade-plan-v1",
        dry_run=not execute,
        execute_requested=execute,
        target_version=target_version,
        allow_prerelease=allow_prerelease,
        selected_version=selected,
        operating_system=platform.system(),
        action="manual_or_assisted_upgrade",
        reversible=True,
        notes=tuple(notes),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--target-version", default=OLLAMA_LATEST_STABLE_KNOWN)
    parser.add_argument("--allow-prerelease", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.target_version in OLLAMA_KNOWN_PRERELEASES and not args.allow_prerelease:
        sys.stderr.write(
            "ollama upgrade refused: pre-release target requires --allow-prerelease\n"
        )
        return 2
    plan = build_upgrade_plan(
        execute=args.execute,
        target_version=args.target_version,
        allow_prerelease=args.allow_prerelease,
    )
    sys.stdout.write(
        json.dumps(plan.to_safe_dict(), indent=2, sort_keys=True, ensure_ascii=False)
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
