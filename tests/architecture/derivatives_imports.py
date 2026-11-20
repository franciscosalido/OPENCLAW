"""Arestas locais de imports com nome e pacote literais, inclusive dentro de funções."""
import ast
from collections.abc import Iterator
from importlib.util import resolve_name


def local_targets(node: ast.AST, package: str) -> Iterator[str]:
    names = []
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
    elif isinstance(node, ast.ImportFrom):
        module = resolve_name("." * node.level + (node.module or ""), package)
        names = [module, *(f"{module}.{alias.name}" for alias in node.names)]
    elif isinstance(node, ast.Call):
        # O nome da função pode ser um alias local de import_module.
        kwargs = {kw.arg: kw.value for kw in node.keywords}
        name = node.args[0] if node.args else kwargs.get("name")
        parent = node.args[1] if len(node.args) > 1 else kwargs.get("package")
        if isinstance(name, ast.Constant) and isinstance(name.value, str):
            if not name.value.startswith("."):
                names = [name.value]
            elif isinstance(parent, ast.Constant) and isinstance(parent.value, str):
                names = [resolve_name(name.value, parent.value)]
            elif isinstance(parent, ast.Name) and parent.id == "__package__":
                names = [resolve_name(name.value, package)]
    for target in names:
        if target.partition(".")[0] in {"backend", "scripts", "config"}:
            while target:
                yield target
                target = target.rpartition(".")[0]
