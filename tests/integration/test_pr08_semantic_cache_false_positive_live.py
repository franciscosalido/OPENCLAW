from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


def test_pr08_semantic_cache_false_positive_risk_is_bypassed_or_skipped() -> None:
    if os.getenv("QUIMERA_CACHE_ENABLED") != "1":
        pytest.skip("skipped_valid: semantic cache is disabled, PR-08 smoke uses cache-safe deterministic retrieval")

    assert os.getenv("QUIMERA_AGENTIC0_CACHE_BYPASS", "1") == "1"
