from __future__ import annotations

from pathlib import Path


def test_pr10_sdd_and_adr_contracts_exist() -> None:
    sdd = Path("docs/specs/rag-01b/pr-10-working-memory-qdrant-pgvector.md").read_text(encoding="utf-8")
    adr = Path("docs/adr/ADR-005-qdrant-working-memory-pgvector-checkpoints.md").read_text(encoding="utf-8")
    mem = Path("docs/04_MEM/WORKING_MEMORY_QDRANT.md").read_text(encoding="utf-8")

    assert "working memory vetorial quente em Qdrant" in sdd
    assert "Status: Accepted" in adr
    assert "quimera_working_memory" in adr
    assert "work-dense" in adr
    assert "pgvector is a checkpoint" in adr
    assert "not HybridRAG" in mem
