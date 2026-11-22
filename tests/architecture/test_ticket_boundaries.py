"""Fronteiras de importação e ambiente da boleta D0."""
import ast
from pathlib import Path

from backend.derivatives.oplab import routes
from backend.derivatives.ticket.models import Environment
from tests.architecture.derivatives_imports import local_targets

ROOT = Path(__file__).resolve().parents[2]
TICKET = "backend.derivatives.ticket"
MCP = "backend.derivatives.mcp"
FORBIDDEN = {
    "httpx", "requests", "socket", "urllib.request", "http.client", "aiohttp", "litellm",
    "openai", "anthropic", "mcp", "fastmcp", "backend.gateway", MCP,
    "backend.derivatives.oplab.transport", "backend.derivatives.oplab.client",
}


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    package = ".".join(path.parent.relative_to(ROOT).parts)
    tree = ast.parse(path.read_text())
    loaders = {"__import__", "import_module"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "importlib":
            loaders.update(a.asname or a.name for a in node.names if a.name == "import_module")
    for node in ast.walk(tree):
        names.update(local_targets(node, package))
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            fn = node.func
            if not ((isinstance(fn, ast.Name) and fn.id in loaders)
                    or (isinstance(fn, ast.Attribute) and fn.attr == "import_module")):
                continue
            name = node.args[0] if node.args else next(
                (kw.value for kw in node.keywords if kw.arg == "name"), None)

            if isinstance(name, ast.Constant) and isinstance(name.value, str):
                names.add(name.value)
    return names


def test_ticket_isolation_and_mcp_direction() -> None:
    """Inspeciona todos os módulos nas duas direções, incluindo imports relativos."""
    for package, forbidden in [(TICKET, FORBIDDEN), (MCP, {TICKET})]:
        for path in ROOT.joinpath(*package.split(".")).rglob("*.py"):
            for name in _imports(path):
                blocked = any(name == item or name.startswith(item + ".") for item in forbidden)
                assert not blocked, (path, name)


def test_only_simulated_environment_and_read_only_market_routes() -> None:
    """O contrato mantém D0 simulado e a fronteira de mercado em leitura."""
    assert {item.value for item in Environment} == {"SIMULATED"}
    assert routes.ALLOWED_METHOD == "GET" and routes.ALLOWED_HOST == "api.oplab.com.br"


def test_ticket_determinism_imports() -> None:
    """Impede dependências de tempo, sorteio e concorrência adicionais."""
    for path in ROOT.joinpath(*TICKET.split(".")).rglob("*.py"):
        banned = {"random", "secrets", "time", "asyncio", "threading"}
        if path.name == "sequencing.py":
            banned.remove("threading")
        assert not {n.split(".")[0] for n in _imports(path)} & banned, path


def test_ticket_has_no_wall_clock() -> None:
    """Identifica chamadas ao relógio por datetime, date ou aliases importados."""
    for path in ROOT.joinpath(*TICKET.split(".")).rglob("*.py"):
        tree = ast.parse(path.read_text())
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "datetime":
                aliases.update({a.asname or a.name: a.name for a in node.names})
            elif isinstance(node, ast.Import):
                aliases.update({a.asname or a.name: a.name for a in node.names})
        for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
            parts = ast.unparse(call.func).split(".")
            parts[0] = aliases.get(parts[0], parts[0])
            assert ".".join(parts).removeprefix("datetime.datetime.") not in (
                "now", "today", "utcnow") or len(parts) == 1, path
            assert ".".join(parts) not in {"datetime.now", "datetime.utcnow", "datetime.today",
                                           "date.today", "datetime.date.today"}, path


def test_only_gate_issues_or_constructs_decisions() -> None:
    """Impede importação da emissão e construção externa, inclusive por alias."""
    gate = TICKET + ".gate"
    for path in (ROOT / "backend").rglob("*.py"):
        if path == ROOT / "backend/derivatives/ticket/gate.py":
            continue
        tree = ast.parse(path.read_text())
        aliases = {}
        package = ".".join(path.parent.relative_to(ROOT).parts)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    aliases[a.asname or a.name] = a.name
            elif isinstance(node, ast.ImportFrom):
                from importlib.util import resolve_name
                module = resolve_name("." * node.level + (node.module or ""), package)
                for a in node.names:
                    aliases[a.asname or a.name] = module + "." + a.name
                    assert aliases[a.asname or a.name] not in {gate+".issue",gate+".*"}, path
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                first, dot, rest = name.partition(".")
                target = aliases.get(first,first) + dot + rest
                assert target not in {gate+".issue",gate+".HumanDecision","HumanDecision"}, path


def test_trigger_only_notifies() -> None:
    """O gatilho não depende dos módulos operacionais e não chama execução ou reserva."""
    path=ROOT / "backend/derivatives/ticket/trigger.py"
    assert not _imports(path) & {TICKET+"."+n for n in
                                 ("gate","venue","paper_venue","sequencing","receipt")}
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
            assert node.func.attr not in {"submit","request_cancel","reserve"}


def test_engine_uses_protocol_and_never_drives_replay() -> None:
    """Restringe importações e impede o motor de avançar o replay ou a venue."""
    path = ROOT / "backend/derivatives/ticket/engine.py"
    allowed = {"gate": {"Action", "DecisionLedger", "DecisionRefusal", "HumanDecision"},
               "replay": {"ReplayEvent"}, "paper_venue": set()}
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        for name in allowed:
            module = TICKET + "." + name
            if module not in set(local_targets(node, TICKET)):
                continue
            assert isinstance(node, ast.ImportFrom) and node.module in (module, name), path
            assert {a.name for a in node.names} <= allowed[name], path
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr != "advance", path


def test_engine_only_accesses_its_own_private_attributes() -> None:
    """Estado privado de colaboradores só pode ser consultado pela interface pública."""
    tree = ast.parse((ROOT / "backend/derivatives/ticket/engine.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                continue
            assert isinstance(node.value, ast.Name) and node.value.id == "self", ast.unparse(node)


def test_ticket_replay_script_imports_and_clock() -> None:
    """O humano simulado usa apenas o domínio da boleta e o horário da fita."""
    path = ROOT / "scripts/derivatives_ticket_replay.py"
    tree = ast.parse(path.read_text())
    imports = _imports(path)
    for name in imports:
        assert not any(name == banned or name.startswith(banned + ".") for banned in FORBIDDEN)
        if name.startswith("backend."):
            assert name == "backend.derivatives" or name == TICKET or name.startswith(TICKET + ".")
    bindings = _script_bindings(tree)
    for target in bindings.values():
        if target.split(".")[0] == "backend":
            assert target == TICKET or target.startswith(TICKET + "."), target
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = _resolved(node.func, bindings)
            assert target not in {"datetime.datetime.now", "datetime.datetime.utcnow",
                                  "datetime.datetime.today", "datetime.date.today", "time.time"}


def _script_bindings(tree: ast.AST) -> dict[str, str]:
    bindings = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            bindings.update({a.asname or a.name: f"{node.module}.{a.name}" for a in node.names})
        elif isinstance(node, ast.Import):
            bindings.update({a.asname or a.name: a.name for a in node.names})
    return bindings


def _resolved(node: ast.AST, bindings: dict[str, str]) -> str:
    first, dot, rest = ast.unparse(node).partition(".")
    return bindings.get(first, first) + dot + rest


def test_script_gate_authority_is_exclusive() -> None:
    """Somente o roteiro pode importar o emissor de decisões no diretório scripts."""
    for path in (ROOT / "scripts").rglob("*.py"):
        if path == ROOT / "scripts/derivatives_ticket_replay.py":
            continue
        names = _imports(path)
        assert TICKET + ".gate.issue" not in names and TICKET + ".gate.*" not in names, path
        tree = ast.parse(path.read_text())
        bindings = _script_bindings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "issue":
                assert _resolved(node, bindings) != TICKET + ".gate.issue", path
