from __future__ import annotations

from pathlib import Path


def test_agent_onboarding_doc_contains_required_boundaries() -> None:
    text = Path("docs/runbooks/agent_onboarding_15min.md").read_text(encoding="utf-8")

    for token in ("variables", "virtual key", "MCP tools", "allowed_tools", "./run_smoke.sh --quick"):
        assert token.lower() in text.lower()
    for forbidden_guidance in ("DB direto", "wildcard tools", "Nível 0", "provider remoto"):
        assert forbidden_guidance in text
