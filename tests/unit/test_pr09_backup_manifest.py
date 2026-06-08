from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from infra.postgres.backup_manifest import (
    compute_sha256,
    create_manifest,
    prune_old_backups,
    sanitize_dsn,
    update_restore_verified,
)


def test_manifest_schema_hash_and_restore_update(tmp_path: Path) -> None:
    dump = tmp_path / "quimera_pg18_quimera_20260605T000000Z.dump"
    dump.write_bytes(b"safe synthetic dump")

    manifest = create_manifest(
        dump_file=dump,
        database="quimera",
        postgres_version="18.4",
        pg_dump_version="18.4",
        retention_days=7,
    )
    manifest_path = dump.with_suffix(".manifest.json")

    assert manifest["schema_version"] == "quimera-postgres-backup-manifest-v1"
    assert manifest["sha256"] == compute_sha256(dump)
    assert manifest["dump_size_bytes"] == dump.stat().st_size
    assert manifest["restore_verified"] is False
    assert (
        json.loads(manifest_path.read_text(encoding="utf-8"))["database"] == "quimera"
    )

    updated = update_restore_verified(manifest_path)
    assert updated["restore_verified"] is True
    assert updated["restore_verified_at"] is not None


def test_sanitize_dsn_redacts_password() -> None:
    assert (
        sanitize_dsn("postgresql://user:secret@127.0.0.1:5432/quimera")
        == "postgresql://user:***@127.0.0.1:5432/quimera"
    )
    assert "secret" not in sanitize_dsn(
        "postgresql://user:secret@127.0.0.1:5432/quimera"
    )


def test_prune_old_backups_only_removes_safe_prefix(tmp_path: Path) -> None:
    old_dump = tmp_path / "quimera_pg18_quimera_20200101T000000Z.dump"
    old_manifest = tmp_path / "quimera_pg18_quimera_20200101T000000Z.manifest.json"
    unsafe = tmp_path / "manual.dump"
    for path in (old_dump, old_manifest, unsafe):
        path.write_text("x", encoding="utf-8")
    old_time = (datetime.now(UTC) - timedelta(days=30)).timestamp()
    for path in (old_dump, old_manifest, unsafe):
        os.utime(path, (old_time, old_time))

    removed = prune_old_backups(tmp_path, retention_days=7)

    assert old_dump in removed
    assert old_manifest in removed
    assert not old_dump.exists()
    assert not old_manifest.exists()
    assert unsafe.exists()
