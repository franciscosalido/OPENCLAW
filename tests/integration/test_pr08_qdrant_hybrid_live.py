from __future__ import annotations

import pytest

from integration.hybrid_fixture import hybrid_contract_summary

pytestmark = pytest.mark.integration


def test_pr08_qdrant_hybrid_synthetic_contract() -> None:
    summary = hybrid_contract_summary("integration")

    assert summary["dense_ok"] is True
    assert summary["sparse_ok"] is True
    assert summary["hybrid_ok"] is True
    assert summary["hybrid_recall_at_5"] >= summary["dense_recall_at_5"]
