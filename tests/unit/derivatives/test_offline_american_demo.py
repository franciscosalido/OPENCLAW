"""Contrato público do opt-in local. As três americanas são observações distintas."""
import json
import math
import shutil
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, TypedDict, cast

from unittest.mock import patch

import pytest
import yaml
from pydantic import ValidationError

from fastmcp import Client
from fastmcp.exceptions import ToolError

from backend.derivatives.cli import FIXTURE_DIR, main, run_chain
from backend.derivatives.config import DerivativesMcpConfig
from backend.derivatives.mcp.derivatives_server import (
    create_derivatives_server, demo_tool, system_clock,
)
from backend.derivatives.oplab import demo_fixture
from backend.derivatives.oplab.demo_fixture import REPO_ROOT, DemoFixture
from backend.derivatives.domain.models import ExerciseStyle, OptionKind
from backend.derivatives.domain.series_registry import SeriesRegistry
from backend.derivatives.pricing.binomial import crr_price
from backend.derivatives.provenance import Provenance, Purpose, Readiness
from backend.derivatives.service import american_demo, demo_chain
from backend.derivatives.service.chain_service import Capture, ChainService, PricedChain
from backend.derivatives.service.demo_chain import build_demo_chain
from config.american_iv_config_model import AmericanIvConfig, load_american_iv_config
from config.derivatives_config_model import load_derivatives_config

ARGS = ["chain", "BOVA11", "2026-11-19"]
DEMO = [*ARGS, "--provider", "offline_fixture"]
OPTIONS = ["--american-demo", "--steps", "32", "--series-registry", "synthetic-v1"]


def invoke(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, Any]]:
    """Executa a entrada da CLI e lê sua saída JSON."""
    rc = main(args)
    return rc, json.loads(capsys.readouterr().out)


def test_default_cli_still_refuses(capsys: pytest.CaptureFixture[str]) -> None:
    """O modo padrão nunca publica a fixture."""
    rc, reply = invoke(ARGS, capsys)
    assert rc == 3 and reply["data"]["status"] == "LIVE_NOT_ACTIVATED"
    assert "rows" not in reply["data"]


def test_opt_in_preserves_each_european_and_prices_or_explains_every_american(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Conserva europeias e explica cada americana no formato v1."""
    rc, plain = invoke(DEMO, capsys)
    assert rc == 0
    rc, mixed = invoke([*DEMO, *OPTIONS], capsys)
    assert rc == 0
    data = mixed["data"]
    assert (data["purpose"], data["provenance"], data["schema_version"]) == (
        "test", "synthetic", "quimera-derivatives-chain-v1")
    rows = data["rows"]
    europeans = [row for row in rows if row["exercise_style"] == "EUROPEAN"]
    assert europeans == plain["data"]["rows"]
    assumptions = data["model_assumptions"]
    plain_assumptions = plain["data"]["model_assumptions"]
    assert {key: assumptions[key] for key in plain_assumptions} == plain_assumptions
    assert "european_dividend_yield" not in assumptions
    assert "european_strike_adjusted_by_exchange_assumed" not in assumptions
    assert not any(key.startswith("shadow_") for row in rows for key in row)
    assert data["row_count"] == len(rows) == len(europeans) + 3
    supported, absent, wrong = [row for row in rows if row["exercise_style"] == "AMERICAN"]
    assert [row["symbol"] for row in (supported, absent, wrong)] == [
        "SYNAC150", "SYNABS151", "SYNAC150"]
    assert supported["supported"] and float(supported["model_price"]) > 0
    assert supported["greeks"] is None and supported["reason"] is None
    iv = supported["iv"]
    assert 0 < iv["bid"]["sigma"] < iv["mid"]["sigma"] < iv["ask"]["sigma"]
    assert {side["status"] for side in iv.values()} == {"ok"}
    for row, reason in [(absent, "registry:missing_series_record"),
                        (wrong, "registry:series_contract_mismatch")]:
        assert not row["supported"] and row["reason"] == reason
        assert row["model_price"] is row["greeks"] is row["iv"] is None


@pytest.mark.parametrize("payload", [None, "bracket_hi: false", "bracket_hi: ["],
                         ids=["missing", "invalid-fields", "invalid-yaml"])
def test_invalid_crr_config_refuses_only_opt_in(
    payload: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Configuração inválida não afeta a demo padrão."""
    path = tmp_path / "american_iv.yaml"
    if payload is not None:
        path.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(
        demo_chain, "load_american_iv_config", lambda: load_american_iv_config(path),
    )
    assert invoke(DEMO, capsys)[0] == 0
    rc, reply = invoke([*DEMO, *OPTIONS], capsys)
    assert rc == 1 and reply["error"] == "DEMO_UNAVAILABLE" and reply["data"] == {}

@pytest.mark.parametrize("selection", [
    ["--american-demo"], ["--steps", "32"], OPTIONS[:-2],
    [*OPTIONS[:2], "0", *OPTIONS[3:]], [*OPTIONS[:2], "5000", *OPTIONS[3:]],
    [*OPTIONS[:-1], "unknown"],
])
def test_partial_or_invalid_selection_refuses_without_quotes(
    selection: list[str], capsys: pytest.CaptureFixture[str],
) -> None:
    """Combinações inválidas recusam antes de publicar dados."""
    rc, reply = invoke([*DEMO, *selection], capsys)
    assert rc == 1 and reply["error"] == "INVALID_ARGUMENTS" and reply["data"] == {}


def substitute_read(
    monkeypatch: pytest.MonkeyPatch, file: str, change: Callable[[Any], Any],
) -> None:
    """Altera uma leitura já autenticada só na memória do teste."""
    original = DemoFixture._payload

    def read(fixture: DemoFixture, name: str) -> object:
        """Substitui só a leitura selecionada no teste."""
        payload = original(fixture, name)
        return change(payload) if name == file else payload

    monkeypatch.setattr(DemoFixture, "_payload", read)


def quote_change(fields: dict[str, object]) -> Callable[[Any], Any]:
    """Cria uma alteração somente na CALL sintética suportada."""
    def change(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Aplica o conjunto de campos à linha alvo."""
        return [row | fields if row["symbol"] == "SYNAC150" and row["strike"] == 150 else row
                for row in options]
    return change


TIME = 1793908800000
OPTIONS_FILE = "market_options_BOVA11.json"
STOCK = "market_stocks_BOVA11.json"
RATES = "market_interest_rates.json"


@pytest.mark.parametrize(("file", "change", "reason"), [
    (OPTIONS_FILE, quote_change({"time": TIME - 61000}), "quality:stale_quote"),
    (OPTIONS_FILE, quote_change({"time": TIME + 1}), "quality:clock_mismatch"),
    (OPTIONS_FILE, quote_change({"time": None}), "quality:missing_source_time"),
    (STOCK, lambda s: s | {"time": TIME - 61000}, "quality:spot_not_synchronous"),
    (STOCK, lambda s: s | {"time": None}, "quality:spot_not_synchronous"),
    (STOCK, lambda s: s | {"close": None}, "quality:spot_not_synchronous"),
    (RATES, lambda _: [], "chain_unpriceable:missing_rate"),
    (RATES, lambda rs: [r | {"updated_at": None} for r in rs], "quality:missing_rate_time"),
    (OPTIONS_FILE, quote_change({"contract_size": 99}), "registry:series_contract_mismatch"),
])
def test_unusable_observation_preserves_refused_row(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    file: str, change: Callable[[Any], Any], reason: str,
) -> None:
    """Preserva a linha e explica por que a observação não serve."""
    substitute_read(monkeypatch, file, change)
    rc, reply = invoke([*DEMO, *OPTIONS], capsys)
    assert rc == 0 and reply["data"]["row_count"] == 103
    row = next(r for r in reply["data"]["rows"] if r["symbol"] == "SYNAC150")
    assert not row["supported"] and row["reason"] == reason
    assert row["model_price"] is row["iv"] is row["greeks"] is None


def test_missing_spot(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Sem spot, toda a chain permanece sem preço ou IV."""
    substitute_read(monkeypatch, STOCK, lambda s: s | {"close": None})
    substitute_read(monkeypatch, OPTIONS_FILE, lambda rs: [r | {"spot_price": None} for r in rs])
    rc, reply = invoke([*DEMO, *OPTIONS], capsys)
    assert rc == 0
    rows = reply["data"]["rows"]
    assert len(rows) == 103
    assert all(r["reason"] == "chain_unpriceable:missing_spot" and r["iv"] is None
               and r["model_price"] is None for r in rows)


@pytest.mark.parametrize(("bid", "ask", "bad", "reason"), [
    (None, 3.1, "bid", "iv_unavailable:missing_quote"),
    (2.9, None, "ask", "iv_unavailable:missing_quote"),
    (2.9, 350, "ask", "iv:above_upper_bound"),
    (0.01, 3.1, "bid", None),
])
def test_each_side_is_independent_and_only_mid_can_price(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    bid: float | None, ask: float | None, bad: str, reason: str | None,
) -> None:
    """Preserva cada lado observável sem inferir o mid."""
    substitute_read(monkeypatch, OPTIONS_FILE, quote_change({"bid": bid, "ask": ask}))
    _, reply = invoke([*DEMO, *OPTIONS], capsys)
    row = next(r for r in reply["data"]["rows"] if r["symbol"] == "SYNAC150")
    assert row["reason"] == reason and row["supported"] == (reason is None)
    assert (row["model_price"] is None) == (reason is not None)
    iv = row["iv"]
    good = iv["ask" if bad == "bid" else "bid"]
    assert good["sigma"] > 0 and good["status"] == "ok"
    if bid is None or ask is None:
        assert iv[bad] is iv["mid"] is None
    else:
        status = "below_intrinsic" if bad == "bid" else "above_upper_bound"
        assert iv[bad] == {"status": status, "sigma": None}
        assert (iv["mid"]["sigma"] is None) == (reason is not None)


CONFIG = DerivativesMcpConfig(context="test", fixture_dir=FIXTURE_DIR)


async def test_mixed_mcp_matches_cli_and_rejects_call_options() -> None:
    """Confere equivalência MCP/CLI e ausência de flags por chamada."""
    class Selection(TypedDict):
        """Seleção fixa no servidor durante a inicialização."""
        american_demo: bool
        steps: int
        series_registry: str

    selection = Selection(american_demo=True, steps=32, series_registry="synthetic-v1")
    server = create_derivatives_server(CONFIG, **selection)
    async with Client(server) as client:
        schemas = {tool.name: tool.inputSchema for tool in await client.list_tools()}
        for name in ("derivatives_chain", "derivatives_chain_demo"):
            assert set(schemas[name]["properties"]) == {"symbol", "due_date"}
        args = {"symbol": "BOVA11", "due_date": "2026-11-19"}
        demo = await client.call_tool("derivatives_chain_demo", args)
        expected = await run_chain(
            "BOVA11", "2026-11-19", "offline_fixture", system_clock, **selection,
        )
        assert demo.data == expected and len(json.dumps(expected)) < 80_000
        live = await client.call_tool("derivatives_chain", args)
        assert live.data["data"]["status"] == "LIVE_NOT_ACTIVATED"
        for name in ("derivatives_chain", "derivatives_chain_demo"):
            with pytest.raises(ToolError, match="INVALID_TOOL_CALL"):
                await client.call_tool(name, {**args, **selection})


@pytest.mark.parametrize("config", [
    replace(CONFIG, provider_mode="live_homologated"), replace(CONFIG, context="prod"),
    replace(CONFIG, readiness=Readiness.C_PROMOTED), replace(CONFIG, fixture_dir="mixed"),
])
async def test_forged_configuration_never_returns_prices(config: DerivativesMcpConfig) -> None:
    """Configuração adulterada não libera a demo."""
    reply = await demo_tool("BOVA11", "2026-11-19", config=config, root=REPO_ROOT,
                            american_demo=True, steps=32, series_registry="synthetic-v1")
    assert not reply["ok"] and reply["error"] == "DEMO_UNAVAILABLE" and reply["data"] == {}


@pytest.mark.parametrize(("name", "symlink"), [
    ("registry.json", False), ("options.json", False),
    ("registry.json", True), ("options.json", True),
])
def test_mixed_files_are_pinned_and_refuse_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, symlink: bool,
) -> None:
    """Valida a identidade e a origem dos dois arquivos mistos."""
    root = Path(FIXTURE_DIR)
    shutil.copytree(REPO_ROOT / root, tmp_path / root)
    source = tmp_path / root / "mixed" / name
    if symlink:
        source.rename(source.with_suffix(".copy"))
        source.symlink_to(source.with_suffix(".copy"))
    else:
        with source.open("ab") as stream:
            stream.write(b" ")
    monkeypatch.setattr(demo_fixture, "REPO_ROOT", tmp_path)
    with pytest.raises((ValueError, OSError)):
        DemoFixture(root, mixed=True)
    assert DemoFixture(root).registry_json is None


@pytest.mark.parametrize("steps", [3, 32, 200])
async def test_price_and_each_iv_use_the_observed_unit_price(steps: int) -> None:
    """B4: preço e três IVs são do mesmo par CRR e reproduzem as cotações."""
    priced, valuation = await build_demo_chain(
        "BOVA11", date(2026, 11, 19), directory=Path(FIXTURE_DIR), american_demo=True,
        steps=steps, series_registry="synthetic-v1")
    row = next(item for item in priced.rows if item.row.contract.symbol == "SYNAC150")
    result = row.pricing
    assert result.model == "crr_american_v1" and result.sigma_source == "mid"
    assert result.iv is not None and result.iv.mid is not None and result.iv.mid.sigma is not None
    assert result.assumptions["carry_dividend_yield"] == 0
    assert "dividend_yield" not in result.assumptions
    assert "strike_adjusted_by_exchange_assumed" not in result.assumptions
    assert priced.valuation_date == valuation.date()
    tte = priced.time_to_expiry
    assert tte is not None
    rate = math.log1p(14.9 / 100)
    for observed, iv in [(2.9, result.iv.bid), (3.0, result.iv.mid), (3.1, result.iv.ask)]:
        assert iv is not None and iv.sigma is not None
        pair = [crr_price(kind=OptionKind.CALL, style=ExerciseStyle.AMERICAN, spot=150.,
                          strike=150., time_years=tte.year_fraction, rate_cont=rate,
                          dividend_yield=0., sigma=iv.sigma, steps=n) for n in (steps, steps + 1)]
        assert sum(pair) / 2 == pytest.approx(observed, abs=1e-7, rel=0)
        assert iv.diagnostic.message == result.model
        assert iv.diagnostic.iterations > 0
    assert result.price is not None
    assert float(result.price) == pytest.approx(3.0, abs=1e-7, rel=0)


@pytest.mark.parametrize("forgery", ["purpose", "provenance", "captured_at"])
async def test_mixed_chain_rejects_forged_stamps(
    forgery: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recusa alterações de propósito, procedência e relógio."""
    original = ChainService.acquire

    async def forged(service: ChainService, symbol: str, *, now: datetime) -> Capture:
        """Produz captura adulterada em memória."""
        cap = await original(service, symbol, now=now)
        if forgery == "captured_at":
            stamp = replace(cap.stamp, captured_at=now - timedelta(days=1))
        elif forgery == "purpose":
            stamp = replace(cap.stamp, provenance=Provenance.OBSERVED, purpose=Purpose.PRODUCTION)
        else:
            stamp = replace(cap.stamp, provenance=Provenance.REPLAY)
        return replace(cap, stamp=stamp)

    monkeypatch.setattr(ChainService, "acquire", forged)
    reply = await demo_tool("BOVA11", "2026-11-19", config=CONFIG, root=REPO_ROOT,
                            american_demo=True, steps=32, series_registry="synthetic-v1")
    data = reply["data"]
    if forgery == "captured_at":
        assert isinstance(data, dict)
        american = [r for r in data["rows"] if r["exercise_style"] == "AMERICAN"]
        assert len(american) == 3
        assert all(r["reason"] == "quality:clock_mismatch" and r["model_price"] is r["iv"] is None
                   for r in american)
    else:
        assert reply["error"] == "DEMO_UNAVAILABLE" and data == {}


@pytest.mark.parametrize("steps", [True, 32.0, "32"])
async def test_constructor_refuses_coerced_steps(steps: Any) -> None:
    """Aceita apenas passos inteiros reais, não valores coercíveis."""
    reply = await demo_tool("BOVA11", "2026-11-19", config=CONFIG, root=REPO_ROOT,
                            american_demo=True, steps=steps, series_registry="synthetic-v1")
    assert reply["error"] == "INVALID_ARGUMENTS" and reply["data"] == {}


@pytest.mark.parametrize(("symbol", "config", "error"), [
    (None, CONFIG, "INVALID_ARGUMENTS"),
    ("BOVA11", replace(CONFIG, fixture_dir=cast(Any, 123)), "DEMO_UNAVAILABLE"),
])
async def test_malformed_direct_calls_fail_closed(
    symbol: Any, config: DerivativesMcpConfig, error: str,
) -> None:
    """Entradas Python inválidas não escapam como exceção."""
    reply = await demo_tool(symbol, "2026-11-19", config=config, root=REPO_ROOT,
                            american_demo=True, steps=32, series_registry="synthetic-v1")
    assert reply["error"] == error and reply["data"] == {}


async def _capture_before_american_projection() -> tuple[PricedChain, datetime]:
    with patch.object(american_demo, "_price_mixed_demo", side_effect=lambda priced, **_: priced):
        return await build_demo_chain(
            "BOVA11", date(2026, 11, 19), directory=Path(FIXTURE_DIR), american_demo=True,
            steps=32, series_registry="synthetic-v1")


async def test_mixed_projection_independently_refuses_replay_test_stamp() -> None:
    """Replay não satisfaz a barreira sintética."""
    priced, _ = await _capture_before_american_projection()
    fixture = DemoFixture(Path(FIXTURE_DIR), mixed=True)
    cfg, iv_config = load_derivatives_config(), load_american_iv_config()
    control = american_demo._price_mixed_demo(priced, fixture=fixture, steps=32,
                                             conventions=cfg.conventions, iv_config=iv_config,
            shadow_config=cfg.iv, steps_source="argument")
    assert any(row.pricing.supported for row in control.rows
               if row.row.contract.symbol == "SYNAC150")
    chain = priced.chain
    assert chain.purpose is chain.stamp.purpose is Purpose.TEST
    replay = chain.model_copy(update={"stamp": replace(chain.stamp, provenance=Provenance.REPLAY)})
    with pytest.raises(ValueError, match="^fixture_provenance$"):
        american_demo._price_mixed_demo(
            priced.model_copy(update={"chain": replay}), fixture=fixture, steps=32,
            conventions=cfg.conventions, iv_config=iv_config,
            shadow_config=cfg.iv, steps_source="argument")


@pytest.mark.parametrize("q", [0.0, 0.04])
async def test_factor_1000_preserves_unit_targets_with_nonstandard_lot(q: float) -> None:
    """CRR e sombra recebem mid por unidade, e a sombra recebe o carry do registro."""
    priced, valuation = await _capture_before_american_projection()
    fixture = DemoFixture(Path(FIXTURE_DIR), mixed=True)
    assert fixture.registry_json is not None and priced.time_to_expiry is not None
    assert priced.chain.spot is not None
    spot = priced.chain.spot.model_copy(update={"price": Decimal("100")})
    chain = priced.chain.model_copy(update={"spot": spot})
    tte = replace(priced.time_to_expiry, year_fraction=0.25)
    priced = priced.model_copy(update={"chain": chain, "time_to_expiry": tte})
    item = next(row for row in priced.rows if row.row.contract.symbol == "SYNAC150")
    iv_config = load_american_iv_config()
    baseline = None
    shadow_config = load_derivatives_config().iv
    for factor in (1, 1000):
        payload = json.loads(fixture.registry_json)
        payload["records"][0]["terms"].update(strike="90", contract_size=37,
                                             quotation_form=factor)
        if q:
            record = payload["records"][0]
            record["carry"].update(kind="CONTINUOUS_YIELD", dividend_yield=str(q))
            record["terms"].update(adjustment_policy="UNPROTECTED", evidence={
                "issuer": "B3", "document": "synthetic-v1 fixture", "version": "test",
                "published_on": "2026-11-05", "symbol": "SYNAC150",
                "effective_on": "2026-11-05", "policy": "UNPROTECTED",
            })
        registry = SeriesRegistry.model_validate_json(json.dumps(payload))
        contract = item.row.contract.model_copy(update={
            "strike": Decimal("90"), "contract_size": 37, "quotation_form": factor,
        })
        bid, ask, mid = Decimal("12.4"), Decimal("12.6"), Decimal("12.5")
        quote = item.row.quote.model_copy(update={"bid": bid * factor, "ask": ask * factor})
        row = item.row.model_copy(update={"contract": contract, "quote": quote})
        assert quote.mid == mid * factor
        with patch.object(american_demo, "american_implied_vol",
                          wraps=american_demo.american_implied_vol) as solve, patch.object(
            american_demo, "implied_vol", wraps=american_demo.implied_vol,
        ) as shadow:
            outcome = american_demo._price_row(
                item.model_copy(update={"row": row}), priced, registry, valuation=valuation,
                steps=32, rate=0.05, iv_config=iv_config, shadow_config=shadow_config)
        assert [call.kwargs["target_price"] for call in solve.call_args_list] == [bid, ask, mid]
        shadow.assert_called_once()
        assert shadow.call_args.args == (float(mid),)
        assert shadow.call_args.kwargs == {
            "kind": OptionKind.CALL, "spot": 100.0, "strike": 90.0, "time_years": 0.25,
            "rate_cont": 0.05, "dividend_yield": q, "cfg": shadow_config,
        }
        assert outcome.supported and outcome.price is not None and outcome.iv is not None
        assert outcome.iv.bid is not None and outcome.iv.ask is not None
        assert outcome.iv.mid is not None
        result = outcome.price, outcome.iv.bid.sigma, outcome.iv.ask.sigma, outcome.iv.mid.sigma
        assert all(sigma is not None for sigma in result[1:])
        if baseline is None:
            baseline = result
        else:
            assert result == baseline


async def test_r1_default_steps_match_explicit_200() -> None:
    """B2: a composição usa 200 do perfil e distingue o argumento explícito."""
    args = ("BOVA11", date(2026, 11, 19))
    defaulted, _ = await build_demo_chain(
        *args, directory=Path(FIXTURE_DIR), american_demo=True,
        series_registry="synthetic-v1", steps=None,
    )
    explicit, _ = await build_demo_chain(
        *args, directory=Path(FIXTURE_DIR), american_demo=True,
        series_registry="synthetic-v1", steps=200,
    )
    assert defaulted.chain.model_assumptions["american_crr_steps"] == 200
    assert defaulted.chain.model_assumptions["american_crr_steps_source"] == "config"
    assert explicit.chain.model_assumptions["american_crr_steps_source"] == "argument"
    assert defaulted.rows == explicit.rows


async def test_r1_shadow_is_diagnostic_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """B5: sombra auditável e falha isolada do preço, das IVs e das recusas."""
    async def demo() -> PricedChain:
        """Executa a demo com o perfil de passos explícito."""
        priced, _ = await build_demo_chain(
            "BOVA11", date(2026, 11, 19), directory=Path(FIXTURE_DIR), american_demo=True,
            steps=200, series_registry="synthetic-v1",
        )
        return priced

    normal = await demo()
    supported = next(r.pricing for r in normal.rows if r.pricing.model == "crr_american_v1")
    shadow = supported.assumptions
    assert shadow["shadow_engine"] == "bsm_european_v1"
    assert shadow["shadow_iv_status"] == "ok"
    assert supported.iv is not None and supported.iv.mid is not None
    sigma = supported.iv.mid.sigma
    shadow_sigma = shadow["shadow_iv_mid"]
    gap = shadow["shadow_iv_gap"]
    assert sigma is not None and type(shadow_sigma) is float and type(gap) is float
    assert gap == sigma - shadow_sigma and abs(gap) > 1e-9

    def broken(*_args: object, **_kwargs: object) -> None:
        """Simula falha interna do cálculo auxiliar."""
        raise RuntimeError("shadow unavailable")

    monkeypatch.setattr(american_demo, "implied_vol", broken)
    failed = await demo()
    failed_supported = next(
        r.pricing for r in failed.rows
        if r.row.contract.symbol == "SYNAC150" and r.row.contract.strike == Decimal("150")
    )
    assert failed_supported.supported, failed_supported.reason
    assert failed_supported.assumptions["shadow_iv_status"] == "error"
    exclude = {"assumptions"}
    for left, right in zip(normal.rows, failed.rows, strict=True):
        assert left.pricing.model_dump(exclude=exclude) == right.pricing.model_dump(exclude=exclude)
        if left.row.contract.exercise_style is ExerciseStyle.EUROPEAN or not left.pricing.supported:
            assert not any(key.startswith("shadow_") for key in left.pricing.assumptions)


@pytest.mark.parametrize(
    ("scenario", "reason", "mid_status"),
    [
        ("missing_ask", "iv_unavailable:missing_quote", None),
        ("stale", "quality:stale_quote", None),
        ("lower_bound", "iv:not_identifiable", "not_applicable"),
        ("control", None, "ok"),
    ],
)
def test_b7_mid_volatility_requires_an_identifiable_quote(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    scenario: str, reason: str | None, mid_status: str | None,
) -> None:
    """Publica a IV do meio só para cotação bilateral, atual e identificável."""
    if scenario == "missing_ask":
        quote_fields: dict[str, object] = {"ask": None}
    elif scenario == "stale":
        quote_fields = {"time": TIME - 61_000}
    elif scenario == "lower_bound":
        from asyncio import run

        captured, _ = run(_capture_before_american_projection())
        tte = captured.time_to_expiry
        assert tte is not None
        # CALL sintética ATM, sem carry; o piso é S - K exp(-rT), não zero.
        floor = -150.0 * math.expm1(-math.log1p(14.9 / 100) * tte.year_fraction)
        quote_fields = {"bid": floor, "ask": floor}
    else:
        quote_fields = {}
    substitute_read(monkeypatch, OPTIONS_FILE, quote_change(quote_fields))

    rc, reply = invoke([*DEMO, *OPTIONS], capsys)
    assert rc == 0
    row = next(r for r in reply["data"]["rows"] if r["symbol"] == "SYNAC150")
    iv = row["iv"]
    assert row["reason"] == reason and row["supported"] == (reason is None)
    if reason is None:
        assert row["model_price"] is not None
        assert 0 < iv["bid"]["sigma"] < iv["mid"]["sigma"] < iv["ask"]["sigma"]
        assert {side["status"] for side in iv.values()} == {"ok"}
    else:
        assert row["model_price"] is None
        mid = None if iv is None else iv["mid"]
        if mid_status is None:
            assert mid is None
        else:
            assert mid == {"sigma": None, "status": mid_status}
    if scenario == "missing_ask":
        assert iv["ask"] is None and iv["bid"]["status"] == "ok"


@pytest.mark.parametrize("bad", [None, 0, 5000, True, 200.0, "200"])
@pytest.mark.parametrize("strict", [True, False])
def test_r1_default_steps_config_contract(bad: Any, strict: bool) -> None:
    """B1: valor ausente e coerções são rejeitados pelo modelo, não substituídos."""
    yaml_data = yaml.safe_load((REPO_ROOT / "config/american_iv.yaml").read_text(encoding="utf-8"))
    assert yaml_data["default_steps"] == 200
    assert load_american_iv_config().default_steps == 200
    if bad is None:
        del yaml_data["default_steps"]
    else:
        yaml_data["default_steps"] = bad
    with pytest.raises(ValidationError, match="default_steps"):
        AmericanIvConfig.model_validate(yaml_data, strict=strict)


async def test_r1_default_steps_come_from_the_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """B2/B3: 37 no perfil muda as linhas; 32 explícito ignora o padrão."""
    cfg = load_american_iv_config()
    custom = AmericanIvConfig.model_validate(dict(cfg.model_dump(), default_steps=37))
    monkeypatch.setattr(demo_chain, "load_american_iv_config", lambda: custom)

    async def price(steps: int | None) -> PricedChain:
        """Executa a demo com argumento de passos opcional."""
        chain, _ = await build_demo_chain(
            "BOVA11", date(2026, 11, 19), directory=Path(FIXTURE_DIR), american_demo=True,
            steps=steps, series_registry="synthetic-v1",
        )
        return chain

    defaulted = await price(None)
    explicit = await price(37)
    other = await price(32)
    assert defaulted.chain.model_assumptions["american_crr_steps"] == 37
    assert defaulted.rows == explicit.rows
    assert other.chain.model_assumptions["american_crr_steps"] == 32
    assert other.chain.model_assumptions["american_crr_steps_source"] == "argument"
    assert other.rows != defaulted.rows


async def test_r1_shadow_chain_aggregate(monkeypatch: pytest.MonkeyPatch) -> None:
    """B6: só linhas comparadas contam; um agregado vazio não publica máximo."""
    async def demo() -> PricedChain:
        """Executa a demo com o perfil de passos explícito."""
        priced, _ = await build_demo_chain(
            "BOVA11", date(2026, 11, 19), directory=Path(FIXTURE_DIR), american_demo=True,
            steps=32, series_registry="synthetic-v1",
        )
        return priced

    mixed = await demo()
    gaps = [
        abs(float(r.pricing.assumptions["shadow_iv_gap"])) for r in mixed.rows
        if "shadow_iv_gap" in r.pricing.assumptions
    ]
    summary = mixed.chain.model_assumptions
    assert summary["american_shadow_engine"] == "bsm_european_v1"
    assert summary["american_shadow_rows"] == len(gaps) == 1
    assert summary["american_shadow_max_abs_gap"] == max(gaps)

    substitute_read(monkeypatch, OPTIONS_FILE, quote_change({"ask": None}))
    empty = (await demo()).chain.model_assumptions
    assert empty["american_shadow_rows"] == 0
    assert "american_shadow_max_abs_gap" not in empty


def test_r1_cli_allows_mixed_demo_without_steps(capsys: pytest.CaptureFixture[str]) -> None:
    """O opt-in público aplica o padrão sem exigir que o usuário informe passos."""
    rc, reply = invoke([*DEMO, "--american-demo", "--series-registry", "synthetic-v1"], capsys)
    assert rc == 0
    assumptions = reply["data"]["model_assumptions"]
    assert assumptions["american_crr_steps"] == 200
    assert assumptions["american_crr_steps_source"] == "config"
