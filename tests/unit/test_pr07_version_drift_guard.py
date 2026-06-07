from __future__ import annotations

from pathlib import Path


SDD = Path("docs/specs/rag-01b/pr-07-benchmark-adr-mcp-memory.md")
COMPOSE = Path("infra/docker/compose.quimera.local.yml")
ADR_PG = Path("docs/ADR/ADR-0021-postgresql-18-4-canonical-version.md")
ADR_QDRANT = Path("docs/ADR/ADR-018-qdrant-118-upgrade.md")


def test_pr07_sdd_has_gate_zero_without_obsolete_versions() -> None:
    text = SDD.read_text(encoding="utf-8")

    assert "Gate Zero - Version Drift Reconciliation" in text
    assert "PostgreSQL 17" not in text
    assert "Qdrant 1.13" not in text


def test_compose_does_not_use_obsolete_postgres_or_qdrant() -> None:
    text = COMPOSE.read_text(encoding="utf-8")

    assert "postgres:17" not in text
    assert "qdrant/qdrant:v1.13" not in text
    assert "postgres:18.4-trixie" in text
    assert "qdrant/qdrant:v1.18.2" in text


def test_canonical_adrs_exist() -> None:
    assert "PostgreSQL 18.4" in ADR_PG.read_text(encoding="utf-8")
    assert "Qdrant 1.18" in ADR_QDRANT.read_text(encoding="utf-8")
