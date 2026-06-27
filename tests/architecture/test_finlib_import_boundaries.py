from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path("backend")
FINLIB = BACKEND / "finlib"
FORBIDDEN_FINLIB_IMPORTS = {
    "anthropic",
    "httpx",
    "litellm",
    "ollama",
    "openai",
    "qdrant_client",
    "requests",
}
FORBIDDEN_FINLIB_PREFIXES = (
    "backend.agent0",
    "backend.agents",
    "backend.memory.qdrant",
    "backend.rag",
)
UPSTREAM_DIRS = (
    BACKEND / "agent0",
    BACKEND / "agents",
    BACKEND / "rag",
)


def _python_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.py") if ".venv" not in path.parts)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_finlib_does_not_import_rag_agents_qdrant_llm_or_http_clients() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _python_files(FINLIB):
        bad: list[str] = []
        for imported in _imports(path):
            root = imported.split(".", 1)[0]
            if root in FORBIDDEN_FINLIB_IMPORTS or imported.startswith(
                FORBIDDEN_FINLIB_PREFIXES
            ):
                bad.append(imported)
        if bad:
            offenders[str(path)] = sorted(bad)

    assert offenders == {}


def test_agent0_and_rag_do_not_import_finlib_directly() -> None:
    offenders: dict[str, list[str]] = {}
    for root in UPSTREAM_DIRS:
        for path in _python_files(root):
            bad = [
                imported
                for imported in _imports(path)
                if imported.startswith("backend.finlib")
            ]
            if bad:
                offenders[str(path)] = sorted(bad)

    assert offenders == {}
