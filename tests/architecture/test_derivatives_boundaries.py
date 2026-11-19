"""Fronteiras de import e de conteudo do Laboratorio de Derivativos (DL-PR00/DL-PR01)."""

from __future__ import annotations

import ast
from pathlib import Path

DERIVATIVES = Path("backend/derivatives")
CONFIG_YAML = Path("config/derivatives.yaml")
FORBIDDEN_IMPORTS = {"httpx", "asyncpg", "qdrant_client"}
FORBIDDEN_PREFIXES = ("backend.mcp",)


def _python_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*.py") if "__pycache__" not in path.parts
    )


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


HTTP_TRANSPORT = DERIVATIVES / "oplab" / "transport.py"
MCP_SURFACE = DERIVATIVES / "mcp"
MCP_SERVER = MCP_SURFACE / "derivatives_server.py"


def test_derivatives_does_not_import_mcp_or_io_clients() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _python_files(DERIVATIVES):
        bad = [
            imported
            for imported in _imports(path)
            if imported.split(".", 1)[0] in FORBIDDEN_IMPORTS
            or imported.startswith(FORBIDDEN_PREFIXES)
        ]
        if path == HTTP_TRANSPORT:
            bad = [imported for imported in bad if imported != "httpx"]
        if MCP_SURFACE in path.parents:
            bad = [imported for imported in bad if not imported.startswith("backend.mcp")]
        if bad:
            offenders[str(path)] = sorted(bad)
    assert offenders == {}, (
        "httpx so em oplab/transport.py (DL-PR05b); backend.mcp so em mcp/ (DL-PR07)"
    )


def test_httpx_is_imported_only_by_the_http_transport() -> None:
    importers = [
        str(path)
        for path in _python_files(DERIVATIVES)
        if "httpx" in {name.split(".", 1)[0] for name in _imports(path)}
    ]
    assert importers == [str(HTTP_TRANSPORT)]


def test_oplab_token_is_read_in_exactly_one_backend_file() -> None:
    hits = [
        str(path)
        for path in _python_files(Path("backend"))
        if "OPLAB_TOKEN" in path.read_text(encoding="utf-8")
    ]
    assert hits == [str(HTTP_TRANSPORT)], "OPLAB_TOKEN so e lido no transporte HTTP"
    text = HTTP_TRANSPORT.read_text(encoding="utf-8")
    assert text.count("OPLAB_TOKEN") == 2, "uma leitura e uma mencao na docstring"
    assert text.count('.get("OPLAB_TOKEN")') == 1
    assert "os.environ[" not in text


def test_no_domain_routes_in_lab() -> None:
    hits = [
        str(path)
        for path in [*_python_files(DERIVATIVES), CONFIG_YAML]
        if "/domain" in path.read_text(encoding="utf-8")
    ]
    assert hits == [], "rota do dominio de ordens e proibida no Laboratorio"


def test_domain_package_does_not_import_vendor_layer() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _python_files(DERIVATIVES / "domain"):
        bad = sorted(
            imported
            for imported in _imports(path)
            if imported.startswith("backend.derivatives.oplab")
        )
        if bad:
            offenders[str(path)] = bad
    assert offenders == {}, "o dominio nao conhece o fornecedor (conversao so em adapters)"


def test_pricing_does_not_import_vendor_adapters_mcp_or_io() -> None:
    forbidden_prefixes = (
        "backend.derivatives.oplab",
        "backend.derivatives.adapters",
        "backend.mcp",
        "mcp",
    )
    offenders: dict[str, list[str]] = {}
    for path in _python_files(DERIVATIVES / "pricing"):
        bad = sorted(
            imported
            for imported in _imports(path)
            if imported.split(".", 1)[0] in {"httpx", "yaml", "mcp"}
            or imported.startswith(forbidden_prefixes)
        )
        if bad:
            offenders[str(path)] = bad
    assert offenders == {}, "pricing/ e puro: sem fornecedor, adapters, MCP ou I/O"


def test_pricing_calendar_is_json_only() -> None:
    imports = _imports(DERIVATIVES / "pricing" / "calendar.py")
    assert "yaml" not in {name.split(".", 1)[0] for name in imports}, (
        "bundles 3.0.0 sao JSON estrito; yaml.safe_load levaria ~2 s por arquivo"
    )


def test_bsm_module_is_arithmetic_only() -> None:
    imports = _imports(DERIVATIVES / "pricing" / "bsm.py")
    roots = {name.split(".", 1)[0] for name in imports}
    assert "pydantic" not in roots, "bsm.py e aritmetica pura: pydantic vive na ponte"
    assert "decimal" not in roots, "bsm.py trabalha em float; Decimal entra/sai na ponte"
    internal = {name for name in imports if name.startswith("backend.")}
    assert internal == {"backend.derivatives.domain.models"}


def test_implied_vol_module_is_arithmetic_only() -> None:
    imports = _imports(DERIVATIVES / "pricing" / "implied_vol.py")
    roots = {name.split(".", 1)[0] for name in imports}
    assert "pydantic" not in roots, "implied_vol.py e aritmetica pura: pydantic na ponte"
    assert "decimal" not in roots, "implied_vol.py trabalha em float; Decimal na ponte"
    internal = {name for name in imports if name.startswith("backend.")}
    assert internal == {
        "backend.derivatives.pricing.bsm",
        "backend.derivatives.domain.models",
    }, "implied_vol.py importa so bsm e domain.models (unica implementacao BSM)"


def test_no_sigma_zero_as_absence_marker_in_iv_modules() -> None:
    for name in ("implied_vol.py", "quote_iv.py"):
        text = (DERIVATIVES / "pricing" / name).read_text(encoding="utf-8")
        compact = text.replace(" ", "")
        assert "sigma=0.0" not in compact, (
            f"{name}: sigma == 0.0 jamais pode marcar ausencia (DL-PR04, A6)"
        )


def test_no_random_in_derivatives() -> None:
    offenders = [
        str(path)
        for path in _python_files(DERIVATIVES)
        if "random" in {name.split(".", 1)[0] for name in _imports(path)}
    ]
    assert offenders == [], "nada de aleatoriedade no Laboratorio (determinismo auditavel)"


def test_wall_clock_enters_only_through_the_mcp_server_root() -> None:
    hits = [
        str(path)
        for path in _python_files(DERIVATIVES)
        if "datetime.now(" in path.read_text(encoding="utf-8")
        or "datetime.utcnow(" in path.read_text(encoding="utf-8")
    ]
    assert hits == [str(MCP_SERVER)], "tempo e injetado; o relogio real so entra na raiz MCP"
    text = MCP_SERVER.read_text(encoding="utf-8")
    assert text.count("datetime.now(") == 1 and "datetime.utcnow(" not in text
    assert "datetime.now(UTC)" in text, "o unico relogio do Lab e tz-aware em UTC"


def test_oplab_does_not_import_pricing_adapters_or_mcp() -> None:
    forbidden_prefixes = (
        "backend.derivatives.pricing",
        "backend.derivatives.adapters",
        "backend.derivatives.domain",
        "backend.derivatives.service",
        "backend.derivatives.mcp",
        "backend.mcp",
        "mcp",
    )
    offenders: dict[str, list[str]] = {}
    for path in _python_files(DERIVATIVES / "oplab"):
        bad = sorted(name for name in _imports(path) if name.startswith(forbidden_prefixes))
        if bad:
            offenders[str(path)] = bad
    assert offenders == {}, "oplab/ so conhece o fornecedor: sem pricing, dominio ou MCP"


def test_oplab_never_sleeps() -> None:
    hits = [
        str(path)
        for path in _python_files(DERIVATIVES / "oplab")
        if "sleep(" in path.read_text(encoding="utf-8")
    ]
    assert hits == [], "o cliente nunca dorme: quem decide esperar e o chamador (DL-PR05)"


def test_no_token_query_parameter_in_lab() -> None:
    needle = "access" + "_token"
    hits = [
        str(path)
        for path in _python_files(DERIVATIVES)
        if needle in path.read_text(encoding="utf-8")
    ]
    assert hits == [], "token so viaja no header; parametro de query e proibido (ADR-0023)"


def test_only_the_service_package_composes_vendor_and_pricing() -> None:
    service = DERIVATIVES / "service"
    offenders: list[str] = []
    for path in _python_files(DERIVATIVES):
        if service in path.parents or MCP_SURFACE in path.parents:
            continue
        imports = _imports(path)
        uses_vendor = any(name.startswith("backend.derivatives.oplab") for name in imports)
        uses_pricing = any(name.startswith("backend.derivatives.pricing") for name in imports)
        uses_service = any(name.startswith("backend.derivatives.service") for name in imports)
        if (uses_vendor and uses_pricing) or uses_service:
            offenders.append(str(path))
    assert offenders == [], "so service/ compoe; mcp/ e a raiz de composicao (ADR-0023)"


def test_service_has_no_network_clock_or_cache() -> None:
    for path in _python_files(DERIVATIVES / "service"):
        roots = {name.split(".", 1)[0] for name in _imports(path)}
        assert roots.isdisjoint({"httpx", "time", "functools", "asyncio", "mcp"}), str(path)


def test_mcp_surface_is_a_leaf_nothing_below_imports_it() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _python_files(DERIVATIVES):
        if MCP_SURFACE in path.parents:
            continue
        bad = sorted(
            name for name in _imports(path)
            if name.startswith("backend.derivatives.mcp") or name.split(".", 1)[0] == "fastmcp"
        )
        if bad:
            offenders[str(path)] = bad
    assert offenders == {}, "dominio, pricing, oplab e service nao conhecem a superficie MCP"


def test_mcp_server_never_reads_credentials_or_opens_http() -> None:
    text = MCP_SERVER.read_text(encoding="utf-8")
    roots = {name.split(".", 1)[0] for name in _imports(MCP_SERVER)}
    assert roots.isdisjoint({"httpx", "os", "socket", "asyncpg", "qdrant_client"})
    assert "HttpTransport" not in text, "o servidor da Fase 1 nao monta transporte HTTP"
    assert "environ" not in text, "ambiente so entra por load_derivatives_mcp_config"
    assert 'host="127.0.0.1"' not in text, "host vem da configuracao, nao de literal"


def test_production_tool_module_has_one_barrier_before_serialization() -> None:
    text = MCP_SERVER.read_text(encoding="utf-8")
    assert text.count("def production_view(") == 1
    assert text.count("= production_view(priced") == 1, "tool produtiva so sai pela barreira"
    assert text.count("chain_view(priced, status=") == 2, "barreira e demo; nenhuma outra saida"
