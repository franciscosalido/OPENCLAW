"""Mantém o piso declarado do pydantic acima da correção dos avisos e coerente com o lock."""
import re
import tomllib
from importlib.metadata import version
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_PATCHED = (2, 14, 2)  # GHSA-qpmf-fgh3-ff25 e GHSA-3r8g-cqwr-jr29
_NAME = re.compile(r"^pydantic(?![A-Za-z0-9_.-])")
_BOUND = re.compile(r"^(>=|<)([0-9]+(?:\.[0-9]+)*)$")


def _release(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def _bounds(requirement: str) -> dict[str, tuple[int, ...]]:
    """Lê somente as formas `>=X` e `<Y`; qualquer outra recusa o manifesto."""
    clauses = requirement.removeprefix("pydantic").replace(" ", "").split(",")
    bounds: dict[str, tuple[int, ...]] = {}
    for clause in clauses:
        match = _BOUND.fullmatch(clause)
        assert match is not None and match[1] not in bounds, requirement
        bounds[match[1]] = _release(match[2])
    return bounds


def _declared() -> str:
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    rows = [dep for dep in project["dependencies"] if _NAME.match(dep)]
    assert len(rows) == 1, rows
    return str(rows[0])


def _locked() -> str:
    lock = tomllib.loads((_ROOT / "uv.lock").read_text(encoding="utf-8"))
    rows = [pkg["version"] for pkg in lock["package"] if pkg["name"] == "pydantic"]
    assert len(rows) == 1, rows
    return str(rows[0])


def _pad(value: tuple[int, ...]) -> tuple[int, ...]:
    return value + (0,) * (3 - len(value))


def test_p1_declared_floor_covers_patched_release() -> None:
    """O manifesto exige a versão corrigida e recusa a próxima maior."""
    bounds = _bounds(_declared())
    assert set(bounds) == {">=", "<"}
    assert _pad(bounds[">="]) >= _PATCHED
    assert bounds["<"] == (3,)


def test_p2_lock_satisfies_manifest() -> None:
    """A versão travada está dentro do intervalo declarado; sem teto, o intervalo é aberto."""
    bounds = _bounds(_declared())
    locked = _pad(_release(_locked()))
    assert _pad(bounds[">="]) <= locked
    assert "<" not in bounds or locked < _pad(bounds["<"])


def test_p3_lock_covers_patched_release() -> None:
    """O lock instala a versão corrigida dos avisos."""
    assert _pad(_release(_locked())) >= _PATCHED


def test_p4_environment_matches_lock() -> None:
    """O portão roda sobre o ambiente do lock, nunca sobre imagem ou venv antigos."""
    assert version("pydantic") == _locked()


def test_p5_bounds_parser_refuses_unknown_forms() -> None:
    """O leitor não aceita formas que ele não sabe comparar."""
    assert _pad(_release("2.14.4.0")) == _pad(_release("2.14.4"))
    for text in (
        "pydantic~=2.14", "pydantic>=2.14.4,>=2.15", "pydantic==2.14.4", "pydantic",
        "pydantic>=2.1 4.4,<3",
    ):
        try:
            _bounds(text)
        except AssertionError:
            continue
        raise AssertionError(text)
