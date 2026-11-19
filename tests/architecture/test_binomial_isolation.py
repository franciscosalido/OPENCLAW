"""Fronteira de imports do núcleo binomial enquanto não há consumidor autorizado."""

import ast
import subprocess
import sys
from importlib.util import resolve_name
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = "backend.derivatives.pricing.binomial"
SOURCE = ROOT / "backend/derivatives/pricing/binomial.py"


def test_no_binomial_consumer() -> None:
    """Percorre imports absolutos, relativos, aliases e literais em produção e scripts."""
    offenders = []
    for directory in ("backend", "scripts"):
        for path in (ROOT / directory).rglob("*.py"):
            if path == SOURCE:
                continue
            package = ".".join(path.relative_to(ROOT).parent.parts)
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    targets = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    module = resolve_name("." * node.level + (node.module or ""), package)
                    targets = [module, *(f"{module}.{alias.name}" for alias in node.names)]
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if TARGET in node.value:
                        offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
                    continue
                else:
                    continue
                if any(name == TARGET or name.startswith(TARGET + ".") for name in targets):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, offenders


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
def offline(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.bind"}:
        raise RuntimeError(event)
sys.addaudithook(offline)
sys.path.insert(0, str(Path.cwd()))
for name in sys.argv[2:]:
    import_module(name)
if sys.argv[1] in sys.modules:
    sys.exit(sys.argv[1])
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe, TARGET, *sorted(modules - {TARGET})],
        cwd=ROOT, env={"QUIMERA_DERIV_FORBID_NETWORK": "1", "FASTMCP_CHECK_FOR_UPDATES": "off"},
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr
