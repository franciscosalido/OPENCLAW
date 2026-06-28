from __future__ import annotations

from pathlib import Path


DONE = Path("docs/sprints/FINLIB0_DONE_CRITERIA.md")
HANDOFF = Path("docs/sprints/FINLIB0_HANDOFF_TO_DATA_AGENTS.md")


def test_done_criteria_contains_go_no_go_and_required_commands() -> None:
    text = DONE.read_text(encoding="utf-8")

    assert "Go" in text
    assert "No-Go" in text
    assert "python scripts/check_finlib_readiness.py --json" in text
    assert "No destructive retention policy" in text
    assert "uvx --from import-linter lint-imports" in text


def test_handoff_blocks_agents_until_readiness_is_ready() -> None:
    text = HANDOFF.read_text(encoding="utf-8")

    assert 'status == "READY"' in text
    assert "ready_for_data_agents == true" in text
    assert "If readiness is `BLOCKED`, the agent must not start." in text
    assert "TimescaleDB is the future canonical source of OHLCVA" in text
    assert "Kronos does not run in FINLIB-0" in text
    assert "Qlib files" in text
