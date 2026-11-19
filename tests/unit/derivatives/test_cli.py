"""DL-PR08: CLI fino ``quimera chain`` — mesma resposta das tools, JSON puro em stdout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

from backend.derivatives.cli import (
    EXIT_NOT_ACTIVATED,
    EXIT_OK,
    EXIT_REFUSED,
    FIXTURE_DIR,
    build_parser,
    exit_code,
    main,
)
from backend.derivatives.config import DerivativesMcpConfig
from backend.derivatives.mcp.derivatives_server import demo_tool
from backend.derivatives.oplab.demo_fixture import REPO_ROOT

CLOCK_NOW = datetime(2026, 11, 5, 20, 0, 5, tzinfo=UTC)
DEMO = ["chain", "BOVA11", "2026-11-19", "--provider", "offline_fixture"]


def clock() -> datetime:
    return CLOCK_NOW


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict[str, Any]]:
    code = main(argv, clock=clock)
    out = capsys.readouterr().out
    assert out.endswith("\n") and out.count("\n") == 1, "exatamente um documento JSON"
    document: dict[str, Any] = json.loads(out)
    return code, document


def test_offline_fixture_prints_the_labelled_demo_chain(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, document = _run(capsys, DEMO)
    assert code == EXIT_OK == 0
    data = document["data"]
    assert document["ok"] is True and document["degraded"] is True
    assert (data["status"], data["purpose"], data["provenance"], data["readiness"]) == (
        "DEMO_TEST_DATA", "test", "synthetic", "A")
    assert data["underlying"] == "BOVA11" and data["row_count"] == len(data["rows"]) == 100


async def test_cli_output_is_exactly_the_mcp_demo_response(
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = DerivativesMcpConfig(context="test", fixture_dir=FIXTURE_DIR)
    expected = await demo_tool("BOVA11", "2026-11-19", config=config, root=REPO_ROOT)
    import asyncio

    code = await asyncio.to_thread(main, DEMO)
    assert code == 0
    assert json.loads(capsys.readouterr().out) == json.loads(json.dumps(expected))


def test_default_provider_is_live_and_never_serves_quotes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, document = _run(capsys, ["chain", "BOVA11", "2026-11-19"])
    assert code == EXIT_NOT_ACTIVATED == 3, "sem cotacao nunca e exit 0"
    assert document["data"] == {
        "schema_version": "quimera-derivatives-chain-v1", "status": "LIVE_NOT_ACTIVATED",
        "readiness": "A", "as_of": CLOCK_NOW.isoformat(),
        "message": "provedor ao vivo nao homologado nem promovido; sem cotacoes"}
    explicit, same = _run(capsys, ["chain", "BOVA11", "2026-11-19", "--provider", "live"])
    assert (explicit, same) == (code, document)


@pytest.mark.parametrize(
    ("argv", "error"),
    [
        (["chain", "BOVA11", "19/11/2026", "--provider", "offline_fixture"],
         "INVALID_ARGUMENTS"),
        (["chain", "BO", "2026-11-19", "--provider", "offline_fixture"], "INVALID_ARGUMENTS"),
        (["chain", "VALE3", "2026-11-19", "--provider", "offline_fixture"],
         "DEMO_SYMBOL_NOT_IN_FIXTURE"),
    ],
)
def test_refusals_exit_one_with_a_constant_code(
    capsys: pytest.CaptureFixture[str], argv: list[str], error: str,
) -> None:
    code, document = _run(capsys, argv)
    assert code == EXIT_REFUSED == 1
    assert document["ok"] is False and document["data"] == {}
    assert document["error"] == error
    assert argv[1] not in json.dumps(document) or argv[1] == "BO"
    assert argv[2] not in json.dumps(document) or argv[2] == "2026-11-19"


def test_unknown_expiry_is_an_empty_demo_chain(capsys: pytest.CaptureFixture[str]) -> None:
    code, document = _run(capsys, ["chain", "BOVA11", "2026-12-18", "--provider",
                                   "offline_fixture"])
    assert code == 0 and document["data"]["row_count"] == 0


def test_lowercase_symbol_is_normalized(capsys: pytest.CaptureFixture[str]) -> None:
    code, document = _run(capsys, ["chain", "bova11", "2026-11-19", "--provider",
                                   "offline_fixture"])
    assert code == 0 and document["data"]["underlying"] == "BOVA11"


@pytest.mark.parametrize(
    "argv",
    [
        [], ["chain"], ["chain", "BOVA11"], ["outro", "BOVA11", "2026-11-19"],
        ["chain", "BOVA11", "2026-11-19", "--provider", "replay"],
        ["chain", "BOVA11", "2026-11-19", "--provider", "live_homologated"],
        ["chain", "BOVA11", "2026-11-19", "--fixture-dir", "/tmp"],
        ["chain", "BOVA11", "2026-11-19", "--path", "/etc/passwd"],
        ["chain", "BOVA11", "2026-11-19", "--url", "https://example.invalid"],
        ["chain", "BOVA11", "2026-11-19", "extra"],
    ],
)
def test_argparse_refuses_anything_outside_the_contract(
    capsys: pytest.CaptureFixture[str], argv: list[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(argv, clock=clock)
    assert stopped.value.code == 2
    assert capsys.readouterr().out == "", "erro de uso vai para stderr, nunca para stdout"


def test_indent_only_changes_formatting(capsys: pytest.CaptureFixture[str]) -> None:
    main([*DEMO, "--indent", "2"], clock=clock)
    pretty = capsys.readouterr().out
    main(DEMO, clock=clock)
    compact = capsys.readouterr().out
    assert pretty.count("\n") > 100 and compact.count("\n") == 1
    assert json.loads(pretty) == json.loads(compact)


def test_exit_code_table() -> None:
    assert exit_code({"ok": True, "data": {"status": "DEMO_TEST_DATA"}}) == 0
    assert exit_code({"ok": True, "data": {"status": "LIVE_NOT_ACTIVATED"}}) == 3
    assert exit_code({"ok": True, "data": {}}) == 3
    assert exit_code({"ok": True}) == 3
    assert exit_code({"ok": False, "data": {"status": "DEMO_TEST_DATA"}}) == 1
    assert exit_code({}) == 1


def test_parser_offers_only_the_contract_options() -> None:
    chain = build_parser()._subparsers._group_actions[0].choices["chain"]  # type: ignore[union-attr]
    options = sorted(option for action in chain._actions for option in action.option_strings)
    assert options == ["--help", "--indent", "--provider", "-h"]


def test_console_script_points_at_an_importable_entry() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["scripts"] == {"quimera": "backend.derivatives.cli:run"}
    module_name, _, attribute = project["scripts"]["quimera"].partition(":")
    assert callable(getattr(import_module(module_name), attribute))
    assert len(project["dependencies"]) == 12, "o CLI nao adiciona dependencia"


def test_subprocess_writes_pure_json_to_stdout_and_logs_to_stderr() -> None:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(
        [sys.executable, "-m", "backend.derivatives.cli", *DEMO],
        capture_output=True, text=True, cwd=REPO_ROOT, env=env, timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-400:]
    document = json.loads(done.stdout)
    assert document["data"]["status"] == "DEMO_TEST_DATA"
    assert done.stdout.count("\n") == 1
    assert "INFO" not in done.stderr, "console: so WARNING para cima"
    live = subprocess.run(
        [sys.executable, "-m", "backend.derivatives.cli", "chain", "BOVA11", "2026-11-19"],
        capture_output=True, text=True, cwd=REPO_ROOT, env=env, timeout=60, check=False)
    assert live.returncode == 3
    assert json.loads(live.stdout)["data"]["status"] == "LIVE_NOT_ACTIVATED"
