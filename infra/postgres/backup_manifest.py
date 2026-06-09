"""Safe local PostgreSQL backup manifest helpers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

BACKUP_SCHEMA_VERSION = "quimera-postgres-backup-manifest-v1"
SAFE_BACKUP_PREFIX = "quimera_pg18_"
MANIFEST_SUFFIX = ".manifest.json"
_DSN_PASSWORD_RE = re.compile(r"(postgres(?:ql)?://[^:/@]+:)([^@]+)(@)", re.IGNORECASE)


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_manifest(
    *,
    dump_file: Path,
    database: str,
    postgres_version: str,
    pg_dump_version: str,
    retention_days: int,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    dump_file = dump_file.resolve()
    manifest = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "postgres_version": postgres_version,
        "database": database,
        "dump_file": str(dump_file),
        "dump_size_bytes": dump_file.stat().st_size,
        "sha256": compute_sha256(dump_file),
        "pg_dump_format": "custom",
        "pg_dump_version": pg_dump_version,
        "restore_verified": False,
        "restore_verified_at": None,
        "retention_days": retention_days,
        "warnings": warnings or [],
    }
    manifest_path = _manifest_path_for_dump(dump_file)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _chmod_private(manifest_path)
    return manifest


def update_restore_verified(
    manifest_path: Path, *, verified: bool = True
) -> dict[str, Any]:
    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw_manifest, dict):
        raise ValueError("manifest must be a JSON object")
    manifest: dict[str, Any] = raw_manifest
    manifest["restore_verified"] = verified
    manifest["restore_verified_at"] = (
        datetime.now(UTC).isoformat() if verified else None
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _chmod_private(manifest_path)
    return manifest


def sanitize_dsn(value: str) -> str:
    return _DSN_PASSWORD_RE.sub(r"\1***\3", value)


def prune_old_backups(directory: Path, retention_days: int) -> list[Path]:
    if retention_days < 1:
        raise ValueError("retention_days must be positive")
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    removed: list[Path] = []
    for path in directory.iterdir() if directory.exists() else ():
        if not _safe_backup_artifact(path):
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if modified < cutoff:
            path.unlink()
            removed.append(path)
    return removed


def _safe_backup_artifact(path: Path) -> bool:
    name = path.name
    return name.startswith(SAFE_BACKUP_PREFIX) and (
        name.endswith(".dump") or name.endswith(MANIFEST_SUFFIX)
    )


def _manifest_path_for_dump(dump_file: Path) -> Path:
    name = dump_file.name.removesuffix(".dump") + MANIFEST_SUFFIX
    return dump_file.with_name(name)


def _chmod_private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--dump-file", required=True)
    create.add_argument("--database", required=True)
    create.add_argument("--postgres-version", required=True)
    create.add_argument("--pg-dump-version", required=True)
    create.add_argument("--retention-days", type=int, required=True)
    create.add_argument("--warning", action="append", default=[])
    verify = sub.add_parser("mark-restore-verified")
    verify.add_argument("--manifest", required=True)
    prune = sub.add_parser("prune")
    prune.add_argument("--directory", required=True)
    prune.add_argument("--retention-days", type=int, required=True)
    args = parser.parse_args()
    if args.command == "create":
        manifest = create_manifest(
            dump_file=Path(args.dump_file),
            database=args.database,
            postgres_version=args.postgres_version,
            pg_dump_version=args.pg_dump_version,
            retention_days=args.retention_days,
            warnings=list(args.warning),
        )
        print(json.dumps(manifest, sort_keys=True))
        return 0
    if args.command == "mark-restore-verified":
        manifest = update_restore_verified(Path(args.manifest))
        print(json.dumps(manifest, sort_keys=True))
        return 0
    removed = prune_old_backups(Path(args.directory), args.retention_days)
    print(json.dumps({"removed": [str(path) for path in removed]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
