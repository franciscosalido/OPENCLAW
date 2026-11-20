"""O motor FD tem dependências locais mínimas e não tem consumidor em produção."""
import ast
from pathlib import Path

import pytest

from tests.architecture.derivatives_imports import local_targets

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path("backend/derivatives/pricing/fd_american.py")
TARGET = "backend.derivatives.pricing.fd_american"


def _consumers(root: Path) -> list[str]:
    offenders = []
    for directory in ("backend", "scripts", "config"):
        for path in (root / directory).rglob("*.py"):
            relative = path.relative_to(root)
            if relative == SOURCE:
                continue
            package = ".".join(relative.parent.parts)
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, (ast.Import, ast.ImportFrom, ast.Call, ast.Constant)):
                    continue
                literal = (isinstance(node, ast.Constant) and isinstance(node.value, str)
                           and TARGET in node.value)
                if literal or TARGET in local_targets(node, package):
                    offenders.append(f"{relative}:{node.lineno}")
    return offenders


def test_t19_fd_dependencies() -> None:
    """Somente biblioteca padrão declarada e enums de domínio."""
    stdlib = {"math", "dataclasses", "enum", "typing"}
    source = ast.parse((ROOT / SOURCE).read_text(encoding="utf-8"))
    for node in ast.walk(source):
        if isinstance(node, ast.Import):
            assert {alias.name for alias in node.names} <= stdlib
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0
            if node.module == "backend.derivatives.domain.models":
                assert {alias.name for alias in node.names} <= {"ExerciseStyle", "OptionKind"}
            else:
                assert node.module in stdlib
        if isinstance(node, ast.Name):
            assert node.id != "__import__"


def test_t19_no_fd_consumers() -> None:
    """PR01 não habilita o motor em backend, scripts ou config."""
    assert _consumers(ROOT) == []


@pytest.mark.parametrize("source", [
    "from .fd_american import fd_price",
    "import backend.derivatives.pricing.fd_american",
    "from . import fd_american",
    "import_module('.fd_american', __package__)",
])
def test_t19_guard_catches_direct_and_dynamic_intruders(tmp_path: Path, source: str) -> None:
    """A guarda não deixa passar import absoluto, relativo ou dinâmico literal."""
    intruder = SOURCE.with_name("intruder.py")
    path = tmp_path / intruder
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    assert any(offender.startswith(f"{intruder}:") for offender in _consumers(tmp_path))
