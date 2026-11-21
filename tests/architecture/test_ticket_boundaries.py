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
