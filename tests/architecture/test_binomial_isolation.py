"""Fronteira de imports do núcleo binomial com uma única ponte autorizada."""

import ast
import subprocess
import sys
from importlib.util import resolve_name
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TARGET = "backend.derivatives.pricing.binomial"
SOURCE = ROOT / "backend/derivatives/pricing/binomial.py"
BRIDGE = "backend.derivatives.pricing.american_bridge"
BRIDGE_PATH = Path("backend/derivatives/pricing/american_bridge.py")


def _binomial_consumers(root: Path) -> list[str]:
    offenders = []
    for directory in ("backend", "scripts"):
        for path in (root / directory).rglob("*.py"):
            if path.relative_to(root) in (SOURCE.relative_to(ROOT), BRIDGE_PATH):
                continue
            package = ".".join(path.relative_to(root).parent.parts)
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    targets = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    module = resolve_name("." * node.level + (node.module or ""), package)
                    targets = [module, *(f"{module}.{alias.name}" for alias in node.names)]
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if TARGET in node.value:
                        offenders.append(f"{path.relative_to(root)}:{node.lineno}")
                    continue
                else:
                    continue
                if any(name == TARGET or name.startswith(TARGET + ".") for name in targets):
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    return offenders


def test_no_binomial_consumer() -> None:
    """Somente a ponte pode consumir o núcleo em produção e scripts."""
    assert _binomial_consumers(ROOT) == []


@pytest.mark.parametrize("path", [BRIDGE_PATH, BRIDGE_PATH.with_name("other_bridge.py")])
def test_t10_binomial_exception(tmp_path: Path, path: Path) -> None:
    """O mesmo import só é aceito no caminho exato da ponte."""
    consumer = tmp_path / path
    consumer.parent.mkdir(parents=True)
    consumer.write_text("from .binomial import crr_price\n", encoding="utf-8")
    assert _binomial_consumers(tmp_path) == ([] if path == BRIDGE_PATH else [f"{path}:1"])


def test_binomial_dependencies() -> None:
    """O núcleo usa somente a biblioteca padrão declarada e os dois enums do domínio."""
    allowed = {"__future__", "math", "dataclasses", "enum", "typing"}
    for node in ast.walk(ast.parse(SOURCE.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            assert all(alias.name in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            if node.module == "backend.derivatives.domain.models":
                assert {alias.name for alias in node.names} <= {"OptionKind", "ExerciseStyle"}
            else:
                assert node.module in allowed


def test_fresh_interpreter() -> None:
    """Importa todos os outros módulos de derivativos e confere o registro do interpretador."""
    modules = set()
    for path in (ROOT / "backend/derivatives").rglob("*.py"):
        parts = path.relative_to(ROOT).with_suffix("").parts
        modules.add(".".join(parts[:-1] if parts[-1] == "__init__" else parts))
    probe = """
import sys
from importlib import import_module
from pathlib import Path

import pytest
def offline(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.bind"}:
        raise RuntimeError(event)
sys.addaudithook(offline)
sys.path.insert(0, str(Path.cwd()))
for name in sys.argv[3:]:
    import_module(name)
loaded = sorted(set(sys.argv[1:3]).intersection(sys.modules))
if loaded:
    sys.exit(", ".join(loaded))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe, TARGET, BRIDGE,
         *sorted(modules - {TARGET, BRIDGE})],
        cwd=ROOT, env={"QUIMERA_DERIV_FORBID_NETWORK": "1", "FASTMCP_CHECK_FOR_UPDATES": "off"},
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr
