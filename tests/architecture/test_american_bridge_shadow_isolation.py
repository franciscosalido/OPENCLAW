"""A ponte CRR conhece apenas o contrato de limites, não o motor de sombra."""

import ast
from pathlib import Path

from tests.architecture.derivatives_imports import local_targets

_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = "backend.derivatives.pricing"
_IV = f"{_PACKAGE}.implied_vol"
_BSM = f"{_PACKAGE}.bsm"


def test_b8_bridge_does_not_import_the_shadow_solver() -> None:
    """Permite só price_bounds, incluindo resolução de imports relativos e aliases."""
    path = _ROOT / "backend/derivatives/pricing/american_bridge.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        targets = set(local_targets(node, _PACKAGE))
        assert _BSM not in targets, f"import BSM na ponte: {ast.unparse(node)}"
        if _IV not in targets:
            continue
        assert isinstance(node, ast.ImportFrom), f"import da IV na ponte: {ast.unparse(node)}"
        assert [alias.name for alias in node.names] == ["price_bounds"], ast.unparse(node)
