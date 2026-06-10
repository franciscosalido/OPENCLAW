from __future__ import annotations

from pathlib import Path

import tomllib


LOCK = Path("uv.lock")


def _locked_version(package_name: str) -> str:
    data = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    for package in data["package"]:
        if package["name"] == package_name:
            return str(package["version"])
    raise AssertionError(f"{package_name} not found in uv.lock")


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split(".") if part.isdigit())


def test_pyjwt_lock_is_past_deep_report_vulnerable_version() -> None:
    assert _version_tuple(_locked_version("pyjwt")) >= (2, 13, 0)


def test_urllib3_lock_uses_patched_deep_report_version() -> None:
    assert _version_tuple(_locked_version("urllib3")) >= (2, 7, 0)


def test_idna_lock_uses_patched_audit_version() -> None:
    assert _version_tuple(_locked_version("idna")) >= (3, 15)
