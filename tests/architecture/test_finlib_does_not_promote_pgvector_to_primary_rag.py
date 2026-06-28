from __future__ import annotations

from pathlib import Path


MIGRATIONS = Path("backend/memory/postgres/migrations")
BACKEND = Path("backend")
DOCS = Path("docs")
MIGRATION_RANGE = range(18, 29)

PRIMARY_EMBEDDING_MARKERS = (
    "primary_embeddings",
    "rag_embeddings",
    "semantic_retriever",
    "chunk_embeddings_primary",
    "primary_semantic_backend",
    "pgvector_primary",
)

PGVECTOR_PRIMARY_PHRASES = (
    "primary semantic retriever: pgvector",
    'primary_semantic_retriever = "pgvector"',
    'primary_semantic_backend = "pgvector"',
    "pgvector is the primary semantic retriever",
    "pgvector is primary semantic retriever",
    "pgvector as primary rag",
)


def _migration_files_018_to_028() -> list[Path]:
    files: list[Path] = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        prefix = path.name.split("_", 1)[0]
        if prefix.isdigit() and int(prefix) in MIGRATION_RANGE:
            files.append(path)
    return files


def _read_lower(path: Path) -> str:
    return path.read_text(encoding="utf-8").lower()


def test_migrations_018_028_do_not_create_primary_embedding_tables() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _migration_files_018_to_028():
        sql = _read_lower(path)
        matches = [marker for marker in PRIMARY_EMBEDDING_MARKERS if marker in sql]
        if matches:
            offenders[str(path)] = matches

    assert offenders == {}


def test_migrations_018_028_do_not_define_vector_columns() -> None:
    offenders = [
        str(path)
        for path in _migration_files_018_to_028()
        if "vector(" in _read_lower(path)
    ]

    assert offenders == []


def test_backend_does_not_promote_pgvector_to_primary_retriever() -> None:
    offenders: dict[str, list[str]] = {}
    for path in sorted(BACKEND.rglob("*.py")):
        if ".venv" in path.parts:
            continue
        text = _read_lower(path)
        matches = [phrase for phrase in PGVECTOR_PRIMARY_PHRASES if phrase in text]
        if matches:
            offenders[str(path)] = matches

    assert offenders == {}


def test_active_docs_do_not_state_pgvector_is_primary_rag() -> None:
    offenders: dict[str, list[str]] = {}
    for path in sorted(DOCS.rglob("*.md")):
        text = _read_lower(path)
        matches = [phrase for phrase in PGVECTOR_PRIMARY_PHRASES if phrase in text]
        if matches:
            offenders[str(path)] = matches

    assert offenders == {}
