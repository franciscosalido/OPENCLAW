from __future__ import annotations

from pathlib import Path


DOC = Path("docs/references/llm_harness_original_papers.md")


def test_llm_harness_references_document_pr08_methodology() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "EleutherAI LM Evaluation Harness" in text
    assert "HELM" in text
    assert "RAGAS" in text
    assert "MT-Bench" in text or "Chatbot Arena" in text
    assert "Como isso se aplica ao PR-08" in text
    assert "live calls opt-in" in text
    assert "no prompt/response/chunk/vector/secrets in artifacts" in text
    assert "LLM-as-judge não é hard gate" in text
