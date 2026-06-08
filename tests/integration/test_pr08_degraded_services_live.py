from __future__ import annotations

import os

import pytest

from integration.check_integration_health import build_integration_health_report

pytestmark = pytest.mark.integration


def test_pr08_degraded_services_contract_is_safe_by_default() -> None:
    if os.getenv("QUIMERA_TEST_CAN_CONTROL_RUNTIME") == "1":
        pytest.skip(
            "runtime-control destructive scenarios are not executed by the default suite"
        )

    report = build_integration_health_report()

    assert report["overall"] in {"ok", "degraded", "fail"}
    assert "qdrant" in report["services"]
    assert "postgres" in report["services"]
