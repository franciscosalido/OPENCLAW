from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _dsn() -> str | None:
    return os.getenv("QUIMERA_POSTGRES_DSN") or os.getenv("TEST_POSTGRES_DSN")


def _postgres_container_available() -> bool:
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "quimera-postgres-memory"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=10,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def test_pr09_pg_dump_restore_verify_live(tmp_path: Path) -> None:
    if not _dsn() and not _postgres_container_available():
        pytest.skip("Postgres DSN or quimera-postgres-memory container is required")

    env = os.environ.copy()
    env["QUIMERA_POSTGRES_BACKUP_DIR"] = str(tmp_path)
    env["QUIMERA_POSTGRES_BACKUP_RETENTION_DAYS"] = "7"
    backup = subprocess.run(["bash", "infra/postgres/backup.sh"], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=120)
    assert backup.returncode == 0, backup.stderr
    dump_files = sorted(tmp_path.glob("quimera_pg18_*.dump"))
    assert dump_files

    restore = subprocess.run(["bash", "infra/postgres/restore_verify.sh", str(dump_files[-1])], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=180)
    assert restore.returncode == 0, restore.stderr
    manifest = json.loads(dump_files[-1].with_suffix(".manifest.json").read_text(encoding="utf-8"))
    assert manifest["restore_verified"] is True
    assert "postgresql://" not in backup.stdout + backup.stderr + restore.stdout + restore.stderr
