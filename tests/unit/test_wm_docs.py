from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


def test_adr_directory_is_spelled_as_tracked_in_git() -> None:
    """``docs/ADR`` e o nome rastreado; volumes insensiveis a caixa escondem o erro."""
    names = {entry.name for entry in DOCS.iterdir()}
    assert "ADR" in names
    assert "adr" not in names


def test_pr10_sdd_and_adr_contracts_exist() -> None:
    sdd = (DOCS / "specs/rag-01b/pr-10-working-memory-qdrant-pgvector.md").read_text(
        encoding="utf-8"
    )
    adr = (
        DOCS / "ADR" / "ADR-005-qdrant-working-memory-pgvector-checkpoints.md"
    ).read_text(encoding="utf-8")
    mem = (DOCS / "04_MEM/WORKING_MEMORY_QDRANT.md").read_text(encoding="utf-8")

    assert "working memory vetorial quente em Qdrant" in sdd
    assert "Status: Accepted" in adr
    assert "quimera_working_memory" in adr
    assert "work-dense" in adr
    assert "pgvector is a checkpoint" in adr
    assert "not HybridRAG" in mem
