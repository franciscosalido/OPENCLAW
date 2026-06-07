from __future__ import annotations

from pathlib import Path


SDD = Path("docs/specs/rag-01b/pr-08-agentic0-integration-smoke.md")
CLIENT = Path("integration/agentic0_client.py")


def test_pr08_does_not_depend_on_unstable_openai_compat_features() -> None:
    text = (SDD.read_text(encoding="utf-8") + "\n" + CLIENT.read_text(encoding="utf-8")).lower()

    assert "previous_response_id" not in text
    assert "logprobs" not in text
    assert "tool_choice" not in text
    assert "autonomous tool-use é opt-in" in text
    assert "/v1/models" in text
    assert "/health/readiness" in Path("infra/litellm/README.md").read_text(encoding="utf-8")
