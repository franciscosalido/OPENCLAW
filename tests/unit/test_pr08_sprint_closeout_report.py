from __future__ import annotations

from pathlib import Path


DOC = Path("docs/04_MEM/AGENT_CONTEXT.md")


def test_agent_context_contains_rag01b_final_closeout() -> None:
    text = DOC.read_text(encoding="utf-8")

    for token in (
        "RAG-01B Final Integration State",
        "PostgreSQL 18.4",
        "Qdrant 1.18.x",
        "LiteLLM host",
        "Ollama/Qwen3",
        "TimescaleDB",
        "./scripts/start_quimera.sh status --json",
        "./scripts/start_quimera.sh integration-health --json",
        "./scripts/start_quimera.sh agentic0-smoke --json",
        "Agentic0 memory access policy",
        "Level 0 data never leaves the machine",
        "Known gaps for the next sprint",
    ):
        assert token in text


def test_start_quimera_final_gate_reads_json_from_temp_files() -> None:
    script = Path("scripts/start_quimera.sh").read_text(encoding="utf-8")

    assert "mktemp -d" in script
    assert "load_json(sys.argv[1])" in script
    assert "json.loads('''${status_json}''')" not in script
    assert "json.loads('''${health_json}''')" not in script
    assert "json.loads('''${smoke_json}''')" not in script
