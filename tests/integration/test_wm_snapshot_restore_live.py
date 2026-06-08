from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.integration


def test_wm_snapshot_restore_live_requires_explicit_stack() -> None:
    if os.environ.get("QUIMERA_TEST_WM_RESTORE_LIVE") != "1":
        pytest.skip(
            "set QUIMERA_TEST_WM_RESTORE_LIVE=1 with Qdrant/Postgres to run restore smoke"
        )
    pytest.fail(
        "live restore smoke is reserved for explicit operator-run stack validation"
    )
