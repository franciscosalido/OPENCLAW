"""Fronteiras de import e de conteudo do Laboratorio de Derivativos (DL-PR00/DL-PR01)."""

from __future__ import annotations

import ast
from pathlib import Path

DERIVATIVES = Path("backend/derivatives")
CONFIG_YAML = Path("config/derivatives.yaml")
FORBIDDEN_IMPORTS = {"httpx", "asyncpg", "qdrant_client"}
FORBIDDEN_PREFIXES = ("backend.mcp",)


def _python_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*.py") if "__pycache__" not in path.parts
    )


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_derivatives_does_not_import_mcp_or_io_clients() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _python_files(DERIVATIVES):
        bad = [
            imported
            for imported in _imports(path)
            if imported.split(".", 1)[0] in FORBIDDEN_IMPORTS
            or imported.startswith(FORBIDDEN_PREFIXES)
        ]
        if bad:
            offenders[str(path)] = sorted(bad)
    assert offenders == {}


def test_oplab_token_absent_in_dl_pr00() -> None:
    hits = [
        str(path)
        for path in _python_files(DERIVATIVES)
        if "OPLAB_TOKEN" in path.read_text(encoding="utf-8")
    ]
    assert hits == [], "OPLAB_TOKEN so pode aparecer no transporte (DL-PR04)"


def test_no_domain_routes_in_lab() -> None:
    hits = [
        str(path)
        for path in [*_python_files(DERIVATIVES), CONFIG_YAML]
        if "/domain" in path.read_text(encoding="utf-8")
    ]
    assert hits == [], "rota do dominio de ordens e proibida no Laboratorio"


def test_domain_package_does_not_import_vendor_layer() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _python_files(DERIVATIVES / "domain"):
        bad = sorted(
            imported
            for imported in _imports(path)
            if imported.startswith("backend.derivatives.oplab")
        )
        if bad:
            offenders[str(path)] = bad
    assert offenders == {}, "o dominio nao conhece o fornecedor (conversao so em adapters)"


def test_no_wall_clock_in_derivatives() -> None:
    hits = [
        str(path)
        for path in _python_files(DERIVATIVES)
        if "datetime.now(" in path.read_text(encoding="utf-8")
        or "datetime.utcnow(" in path.read_text(encoding="utf-8")
    ]
    assert hits == [], "tempo e sempre injetado no Laboratorio (sem relogio interno)"
