"""Isolamento dos termos e do carry de todas as superfícies da Fase 01."""

import ast
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterator
from importlib.util import resolve_name
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = Path("backend/derivatives/domain")
TERMS = "backend.derivatives.domain.series_terms"
CARRY = "backend.derivatives.domain.carry"
BRIDGE_PATH = Path("backend/derivatives/pricing/american_bridge.py")
BRIDGE = "backend.derivatives.pricing.american_bridge"
PROTECTED = {TERMS, CARRY}
_LITERAL = re.compile(
    r"(?<![\w.])(?:" + "|".join(map(re.escape, sorted(PROTECTED | {BRIDGE}))) + r")(?!\w)"
)


def _module(path: Path) -> str:
    parts = path.with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _targets(node: ast.Import | ast.ImportFrom, package: str) -> Iterator[str]:
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
    else:
        module = resolve_name("." * node.level + (node.module or ""), package)
        names = [module, *(f"{module}.{alias.name}" for alias in node.names)]
    for name in names:
        if name.partition(".")[0] not in {"backend", "scripts"}:
            continue
        # Python inicializa cada pacote pai antes de carregar o módulo pedido.
        while name:
            yield name
            name = name.rpartition(".")[0]


def _offenders(root: Path) -> list[str]:
    # Arestas invertidas permitem propagar alcance até os consumidores, mesmo em ciclos.
    consumers: dict[str, set[tuple[Path, int]]] = defaultdict(set)
    offenders: set[str] = set()
    for tree in ("backend", "scripts"):
        for source in (root / tree).rglob("*.py"):
            path = source.relative_to(root)
            package = ".".join(path.parent.parts)
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"), filename=str(path))):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for target in _targets(node, package):
                        consumers[target].add((path, node.lineno))
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for match in _LITERAL.finditer(node.value):
                        consumers[match.group()].add((path, node.lineno))

    for protected in (PROTECTED, {BRIDGE}):
        reached = protected.copy()
        pending = list(reached)
        while pending:
            for path, line in consumers[pending.pop()]:
                if protected == {BRIDGE} or (DOMAIN not in path.parents and path != BRIDGE_PATH):
                    offenders.add(f"{path}:{line}")
                module = _module(path)
                if module not in reached:
                    reached.add(module)
                    pending.append(module)
    return sorted(offenders)


def test_only_domain_consumes_series_terms() -> None:
    """Somente domínio e ponte alcançam termos e carry; nenhum módulo alcança a ponte."""
    assert _offenders(ROOT) == []


@pytest.mark.parametrize(("path", "statement", "allowed"), [
    (BRIDGE_PATH, f"from {TERMS} import SeriesTerms", True),
    (BRIDGE_PATH, f"from {CARRY} import resolve_carry", True),
    (BRIDGE_PATH.with_name("other_bridge.py"), f"import {TERMS}", False),
    (BRIDGE_PATH.with_name("other_bridge.py"), f"import {CARRY}", False),
    (DOMAIN / "intruder.py", f"import {BRIDGE}", False),
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
    """Testa os imports diretos e a exceção de caminho da ponte."""
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


_SERVICE = "backend/derivatives/service/s.py"
_BRIDGE = "backend/derivatives/pricing/bridge.py"
_TOOL = "scripts/tool.py"


@pytest.mark.parametrize(("files", "expected"), [
    ({DOMAIN / "__init__.py": "from . import series_terms",
      _SERVICE: "import backend.derivatives.domain.models"}, [f"{_SERVICE}:2"]),
    ({DOMAIN / "facade.py": "from .carry import CarryKind",
      _BRIDGE: "from ..domain import facade", _TOOL: "import backend.derivatives.pricing.bridge"},
     [f"{_BRIDGE}:2", f"{_TOOL}:2"]),
    ({_SERVICE: f"import {CARRY}"}, [f"{_SERVICE}:2"]),
    ({"backend/derivatives/mcp/s.py": f'import_module("{CARRY}")'},
     ["backend/derivatives/mcp/s.py:2"]),
    ({_SERVICE: f'"""{TERMS}"""'}, [f"{_SERVICE}:2"]),
    ({_SERVICE: f'"""Referência a {CARRY}."""'}, [f"{_SERVICE}:2"]),
    ({_SERVICE: f'"""{CARRY}_other"""'}, []),
    ({DOMAIN / "pure.py": "from . import carry"}, []),
    ({DOMAIN / "__init__.py": "", _SERVICE: "from ..domain import models"}, []),
    ({DOMAIN / "a.py": "from . import b, series_terms", DOMAIN / "b.py": "from . import a",
      _SERVICE: "from ..domain import b"}, [f"{_SERVICE}:2"]),
    ({DOMAIN / "a.py": "from . import b", DOMAIN / "b.py": "from . import a",
      _SERVICE: "from ..domain import b"}, []),
    ({"backend/__init__.py": "from .derivatives.domain import carry",
      "backend/other/leaf.py": "", _TOOL: "import backend.other.leaf"},
     ["backend/__init__.py:2", f"{_TOOL}:2"]),
    ({DOMAIN / "__init__.py": "from . import facade",
      DOMAIN / "facade.py": "from .inner import b",
      DOMAIN / "inner/b.py": "from .. import facade, carry",
      _SERVICE: "import backend.derivatives.domain.other.deep as d"}, [f"{_SERVICE}:2"]),
    ({"outside/facade.py": f"import {CARRY}", _TOOL: "from outside import facade"}, []),
])
def test_transitive_boundary(
    tmp_path: Path, files: dict[Path | str, str], expected: list[str],
) -> None:
    """Exige arquivo e linha de cada import inicial no escopo fechado da guarda."""
    for name, statement in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# módulo sintético\n{statement}\n", encoding="utf-8")
    assert _offenders(tmp_path) == expected


@pytest.mark.parametrize("surface", [
    _SERVICE, "backend/derivatives/mcp/s.py", _TOOL, "backend/derivatives/cli.py",
])
@pytest.mark.parametrize("via_facade", [False, True], ids=["direct", "indirect"])
def test_t10_surface_cannot_reach_bridge(tmp_path: Path, surface: str, via_facade: bool) -> None:
    """Acusa a superfície consumidora inclusive quando um intermediário importa a ponte."""
    consumer = tmp_path / surface
    consumer.parent.mkdir(parents=True)
    target = BRIDGE
    expected = [f"{surface}:1"]
    if via_facade:
        facade = DOMAIN / "facade.py"
        (tmp_path / facade).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / facade).write_text(f"import {BRIDGE}\n", encoding="utf-8")
        target = _module(facade)
        expected.append(f"{facade}:1")
    consumer.write_text(f"import {target}\n", encoding="utf-8")
    assert _offenders(tmp_path) == sorted(expected)


_PROBE = """
import sys
from importlib import import_module
from pathlib import Path

def _forbid_network(event: str, args: tuple[object, ...]) -> None:
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.bind"}:
        raise RuntimeError("rede proibida na prova de import")

sys.addaudithook(_forbid_network)
sys.path.insert(0, str(Path.cwd()))
for name in sys.argv[3:]:
    import_module(name)
loaded = sorted(set(sys.argv[1:3]).intersection(sys.modules))
if loaded:
    sys.exit(f"módulos protegidos carregados: {', '.join(loaded)}")
"""


def _probe(root: Path) -> subprocess.CompletedProcess[str]:
    modules = {_module(path.relative_to(root)) for path in (root / "backend/derivatives")
               .rglob("*.py")}
    return subprocess.run(
        [sys.executable, "-I", "-B", "-c", _PROBE, *sorted(PROTECTED),
         *sorted(modules - PROTECTED - {BRIDGE})],
        cwd=root, env={"QUIMERA_DERIV_FORBID_NETWORK": "1", "FASTMCP_CHECK_FOR_UPDATES": "off"},
        capture_output=True, text=True, timeout=60, check=False,
    )


def test_surface_imports_in_fresh_process() -> None:
    """Importa as superfícies no interpretador isolado e inspeciona sys.modules."""
    probe = _probe(ROOT)
    assert probe.returncode == 0, probe.stderr


def test_dynamic_import_in_parent_initializer(tmp_path: Path) -> None:
    """A prova em execução vê até um caminho calculado ao inicializar o pacote pai."""
    domain = tmp_path / DOMAIN
    domain.mkdir(parents=True)
    for path in (domain, *list(domain.parents)[:2]):
        (path / "__init__.py").touch()
    (domain / "carry.py").touch()
    (tmp_path / "backend/__init__.py").write_text(
        'from importlib import import_module\nimport_module(".".join(("backend.derivatives", '
        '"domain", "carry")))\n', encoding="utf-8",
    )
    assert _offenders(tmp_path) == []
    probe = _probe(tmp_path)
    assert probe.returncode == 1
    assert probe.stderr.strip() == f"módulos protegidos carregados: {CARRY}"


@pytest.mark.parametrize("via_facade", [False, True])
def test_registry_cannot_be_loaded_by_a_surface(tmp_path: Path, via_facade: bool) -> None:
    surface = tmp_path / _SERVICE
    surface.parent.mkdir(parents=True)
    statement = 'import_module("backend.derivatives.domain.series_registry")'
    if via_facade:
        facade = tmp_path / DOMAIN / "facade.py"
        facade.parent.mkdir(parents=True)
        facade.write_text(statement, encoding="utf-8")
        statement = "from ..domain import facade"
    surface.write_text(statement, encoding="utf-8")
    assert _offenders(tmp_path) == [f"{_SERVICE}:1"]
