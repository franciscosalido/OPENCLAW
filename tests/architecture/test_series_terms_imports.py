"""Imports estáticos dos termos de série em backend e scripts (DL2-PR01, I5)."""

import ast
from importlib.util import resolve_name
from itertools import chain
from pathlib import Path

import pytest

DOMAIN = Path("backend/derivatives/domain")
TERMS = "backend.derivatives.domain.series_terms"


def _offenders(root: Path) -> list[str]:
    offenders: list[str] = []
    for path in chain((root / "backend").rglob("*.py"), (root / "scripts").rglob("*.py")):
        if root / DOMAIN in path.parents:
            continue
        package = ".".join(path.parent.relative_to(root).parts)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = resolve_name("." * node.level + (node.module or ""), package)
                imports = [module, *(f"{module}.{alias.name}" for alias in node.names)]
            else:
                continue
            if any(name == TERMS or name.startswith(TERMS + ".") for name in imports):
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    return sorted(offenders)


def test_only_domain_consumes_series_terms() -> None:
    assert _offenders(Path(__file__).resolve().parents[2]) == []


@pytest.mark.parametrize(("path", "statement", "allowed"), [
    (DOMAIN / "pure.py", f"from {TERMS} import SeriesTerms", True),
    (DOMAIN / "sub/pure.py", "from .. import series_terms", True),
    ("scripts/tool.py", f"import {TERMS} as terms", False),
    ("scripts/sub/tool.py", "from backend.derivatives.domain import series_terms as terms", False),
    ("backend/derivatives/service/s.py", "from ..domain import series_terms as t", False),
    ("backend/derivatives/mcp/s.py", "from ..domain.series_terms import SeriesTerms as T", False),
    ("backend/derivatives/cli.py", f"import os, {TERMS}", False),
    ("backend/derivatives/adapters/s.py", f"import {TERMS}.child as child", False),
    ("backend/other/s.py", "from ..derivatives.domain.series_terms.child import name", False),
    ("backend/derivatives/domain_other/s.py", f"from {TERMS} import *", False),
    ("scripts/tool.py", f"import {TERMS}_other", True),
    ("backend/other/s.py", "from ..derivatives.domain import models", True),
])
def test_static_import_boundary(tmp_path: Path, path: Path | str, statement: str,
                                allowed: bool) -> None:
    consumer = tmp_path / path
    consumer.parent.mkdir(parents=True)
    consumer.write_text(f"# import sintético\n{statement}\n", encoding="utf-8")
    assert _offenders(tmp_path) == ([] if allowed else [f"{path}:2"])


def test_domain_facade_does_not_publish_series_terms(tmp_path: Path) -> None:
    """A surface cannot reach the series terms through a domain facade."""
    facade = tmp_path / DOMAIN / "facade.py"
    consumer = tmp_path / "backend/derivatives/service/s.py"
    facade.parent.mkdir(parents=True)
    consumer.parent.mkdir(parents=True)
    facade.write_text(f"from {TERMS} import SeriesTerms\n", encoding="utf-8")
    consumer.write_text("from backend.derivatives.domain import facade\n", encoding="utf-8")
    assert _offenders(tmp_path) == ["backend/derivatives/service/s.py:1"]
