"""Keep the archived external oracle out of all execution paths."""
import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ARCHIVED_GENERATOR = Path(
    "tests/fixtures/derivatives/reference/quantlib/generate_quantlib_reference.py"
)


def _imports_quantlib(node: ast.AST) -> bool:
    """Recognize both direct and from imports of the package."""
    if isinstance(node, ast.Import):
        return any(alias.name.split(".")[0].casefold() == "quantlib" for alias in node.names)
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return node.module.split(".")[0].casefold() == "quantlib"
    return False


def _offenders(root: Path, *directories: str) -> list[Path]:
    """Find source files importing QuantLib, except the inert archived generator."""
    return sorted(
        relative
        for directory in directories
        for path in (root / directory).rglob("*.py")
        if (relative := path.relative_to(root)) != _ARCHIVED_GENERATOR
        and any(_imports_quantlib(node) for node in ast.walk(ast.parse(path.read_bytes())))
    )


def test_g1_no_quantlib_imports():
    """Forbid QuantLib imports in runtime, tooling, and executable tests."""
    assert not _offenders(_ROOT, "backend", "config", "scripts", "tests")


def test_g2_no_quantlib_dependency():
    """Keep the library out of the project manifest and lockfile."""
    for name in ("pyproject.toml", "uv.lock"):
        assert "quantlib" not in (_ROOT / name).read_text().casefold()


def test_g3_no_runtime_reference():
    """Disallow production or tooling from referring to the oracle artifact."""
    markers = (b"quantlib_reference", b"reference/quantlib")
    for directory in ("backend", "config", "scripts"):
        for path in (_ROOT / directory).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                data = path.read_bytes()
                assert not any(marker in data for marker in markers), path


def test_g4_detects_intruder(tmp_path: Path):
    """Prove the AST guard detects both import syntaxes."""
    root = tmp_path / "scripts"
    root.mkdir()
    for name, code in (
        ("direct.py", "import QuantLib as ql\n"),
        ("from_pkg.py", "from QuantLib import VanillaOption\n"),
    ):
        (root / name).write_text(code)
    assert _offenders(tmp_path, "scripts") == [
        Path("scripts/direct.py"), Path("scripts/from_pkg.py"),
    ]
