from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.integration


def test_wm_qdrant_restart_restore_live_is_opt_in() -> None:
    if os.environ.get("QUIMERA_TEST_CAN_CONTROL_RUNTIME") != "1":
        pytest.skip(
            "set QUIMERA_TEST_CAN_CONTROL_RUNTIME=1 to run restart/restore validation"
        )
    pytest.fail("runtime-control restart restore is intentionally human-operated")
