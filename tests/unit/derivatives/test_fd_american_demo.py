"""Contratos de integração do FD na demonstração sintética."""
import json
import math
from dataclasses import replace
from datetime import date
from typing import Any
from unittest.mock import patch
from decimal import Decimal
from pathlib import Path

import pytest

from backend.derivatives.cli import FIXTURE_DIR
from backend.derivatives.domain.models import ExerciseStyle, OptionKind
from backend.derivatives.domain.series_registry import SeriesRegistry
from backend.derivatives.oplab.demo_fixture import DemoFixture
from backend.derivatives.pricing.contract_pricing import PricingOutcome
from backend.derivatives.pricing.fd_american import FdGrid, FdIvResult, fd_price
from backend.derivatives.service import american_demo, demo_chain
from backend.derivatives.service.chain_service import PricedChain, PricedRow
from backend.derivatives.service.demo_chain import build_demo_chain
from config.american_fd_config_model import load_american_fd_config
from config.american_iv_config_model import load_american_iv_config
from config.derivatives_config_model import load_derivatives_config
from tests.unit.derivatives.test_offline_american_demo import (
    ARGS, DEMO, OPTIONS, _capture_before_american_projection, invoke,
)


async def _demo(*, steps: int = 32) -> PricedChain:
    priced, _ = await build_demo_chain(
        "BOVA11", date(2026, 11, 19), directory=Path(FIXTURE_DIR),
        american_demo=True, steps=steps, series_registry="synthetic-v1",
    )
    return priced


def _main_row(priced: PricedChain) -> PricedRow:
    return next(item for item in priced.rows
                if item.row.contract.symbol == "SYNAC150"
                and item.row.contract.strike == Decimal("150"))


async def test_u1_supported_row_has_additive_fd_diagnostics() -> None:
    """A VI do FD e a da árvore são distintas; o desvio tem sinal auditável."""
    priced = await _demo()
    result = _main_row(priced).pricing
    assert result.supported
    fd = result.assumptions
    assert fd.get("fd_engine") == "fd_cn_os_v1"
    assert fd["fd_grid"] == "400x200" and fd["fd_iv_status"] == "ok"
    assert result.iv is not None and result.iv.mid is not None and result.iv.mid.sigma is not None
    assert fd["fd_iv_gap"] == result.iv.mid.sigma - float(fd["fd_iv_mid"])
    assert "fd_price_gap" in fd
    assert fd["fd_iv_comparison"] == "informative"
    assert fd["fd_iv_alert"] is False


async def test_u2_standard_synthetic_gap_is_below_provisional_alert() -> None:
    """A captura fixa não excede o limiar no perfil padrão de 200 passos CRR."""
    row = _main_row(await _demo(steps=200)).pricing
    assert row.assumptions["fd_iv_status"] == "ok"
    assert abs(float(row.assumptions["fd_iv_gap"])) <= 5e-4


async def test_u3_fd_only_runs_for_supported_american_rows() -> None:
    """Linhas recusadas não chamam o FD, nem recebem diagnóstico dele."""
    with patch.object(american_demo, "fd_implied_vol", wraps=american_demo.fd_implied_vol) as spy:
        priced = await _demo()
    eligible = [item for item in priced.rows if item.pricing.supported
                and item.row.contract.exercise_style is ExerciseStyle.AMERICAN]
    assert len(eligible) == 1
    assert "fd_engine" in eligible[0].pricing.assumptions
    spy.assert_called_once()
    for item in priced.rows:
        if item not in eligible:
            assert not any(key.startswith("fd_") for key in item.pricing.assumptions)


def _assert_same_primary(a: PricedChain, b: PricedChain) -> None:
    """Compara toda a captura, excluindo apenas as chaves de diagnóstico FD."""
    assert a.model_dump(exclude={"chain", "rows"}) == b.model_dump(exclude={"chain", "rows"})
    assert a.chain.model_dump(exclude={"model_assumptions"}) == b.chain.model_dump(
        exclude={"model_assumptions"},
    )
    def legacy_chain(priced: PricedChain) -> dict[str, str | float | bool]:
        return {k: v for k, v in priced.chain.model_assumptions.items()
                if not k.startswith("american_fd_")}

    assert legacy_chain(a) == legacy_chain(b)
    for old, new in zip(a.rows, b.rows, strict=True):
        assert old.row == new.row
        assert old.pricing.model_dump(exclude={"assumptions"}) == new.pricing.model_dump(
            exclude={"assumptions"},
        )
        assert {k: v for k, v in old.pricing.assumptions.items() if not k.startswith("fd_")} == {
            k: v for k, v in new.pricing.assumptions.items() if not k.startswith("fd_")
        }


async def test_u4_fd_exception_is_diagnostic_only() -> None:
    """Exceção do FD não modifica preço, recusa, VI principal ou BSM."""
    normal = await _demo()
    with patch.object(american_demo, "fd_price", side_effect=RuntimeError("synthetic FD failure")):
        broken = await _demo()
    result = _main_row(broken).pricing
    assert result.assumptions["fd_iv_status"] == "error"
    assert "fd_iv_mid" not in result.assumptions and "fd_iv_gap" not in result.assumptions
    _assert_same_primary(normal, broken)


async def test_u5_fd_refusal_keeps_status_and_has_no_iv_numbers() -> None:
    """Recusa tipada da inversão permanece visível sem VI, desvio ou alerta."""
    normal = await _demo()
    blocked = FdIvResult("unbracketed", None)
    with patch.object(american_demo, "fd_implied_vol", return_value=blocked):
        refused = await _demo()
    fd = _main_row(refused).pricing.assumptions
    assert fd["fd_iv_status"] == "unbracketed"
    assert "fd_price_gap" in fd
    assert {"fd_iv_mid", "fd_iv_gap", "fd_iv_comparison", "fd_iv_alert"}.isdisjoint(fd)
    chain = refused.chain.model_assumptions
    assert chain["american_fd_rows"] == chain["american_fd_alert_rows"] == 0
    assert "american_fd_max_abs_gap" not in chain
    _assert_same_primary(normal, refused)


def test_u6_alert_preserves_cli_and_model_and_aggregates_modulus(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Desvio negativo com sensibilidade suficiente alerta sem recusar a linha."""
    args = [*DEMO, *OPTIONS]
    control_rc, control = invoke(args, capsys)
    canonical = next(
        row for row in control["data"]["rows"] if row["symbol"] == "SYNAC150" and row["supported"]
    )
    sigma = canonical["iv"]["mid"]["sigma"]
    with patch.object(american_demo, "fd_implied_vol", return_value=FdIvResult("ok", sigma + .01)):
        rc, alerted = invoke(args, capsys)
    assert rc == control_rc == 0
    assert alerted["data"]["rows"] == control["data"]["rows"]
    assumptions = alerted["data"]["model_assumptions"]
    assert assumptions["american_fd_engine"] == "fd_cn_os_v1"
    assert assumptions["american_fd_grid"] == "400x200"
    assert assumptions["american_fd_rows"] == assumptions["american_fd_alert_rows"] == 1
    assert assumptions["american_fd_low_sensitivity_rows"] == 0
    assert assumptions["american_fd_max_abs_gap"] == abs(sigma - (sigma + .01))


async def _two_rows() -> tuple[PricedChain, DemoFixture]:
    captured, _ = await _capture_before_american_projection()
    fixture = DemoFixture(Path(FIXTURE_DIR), mixed=True)
    assert fixture.registry_json is not None
    payload = json.loads(fixture.registry_json)
    record = json.loads(fixture.registry_json)["records"][0]
    symbol = "SYNAC150B"
    record["terms"]["symbol"] = record["carry"]["symbol"] = symbol
    payload["records"].append(record)
    fixture.registry_json = json.dumps(payload).encode()
    first = _main_row(captured)
    contract = first.row.contract.model_copy(update={"symbol": symbol})
    quote = first.row.quote.model_copy(update={"bid": Decimal("11.9"), "ask": Decimal("12.1")})
    row = first.row.model_copy(update={"contract": contract, "quote": quote})
    second = first.model_copy(update={"row": row})
    return captured.model_copy(update={"rows": (first, second)}), fixture


async def test_u7_larger_second_row_gap_wins_aggregation() -> None:
    """Não confunde primeiro desvio com máximo, nem conta linha sem comparação."""
    captured, fixture = await _two_rows()
    cfg = load_derivatives_config()
    original = american_demo.fd_implied_vol

    def larger_second(**kwargs: Any) -> FdIvResult:
        if kwargs["target_price"] == 12.:
            return FdIvResult("ok", 1.5)
        # Only synthetic kwargs observed at the typed production boundary reach the real solver.
        return original(**kwargs)

    with patch.object(american_demo, "fd_implied_vol", side_effect=larger_second):
        priced = american_demo._price_mixed_demo(
            captured, fixture=fixture, steps=32, conventions=cfg.conventions,
            iv_config=load_american_iv_config(), shadow_config=cfg.iv, steps_source="argument",
            fd_config=load_american_fd_config(),
        )
    gaps = [float(row.pricing.assumptions["fd_iv_gap"]) for row in priced.rows]
    assert gaps[1] < 0 and abs(gaps[1]) > abs(gaps[0])
    assert priced.chain.model_assumptions["american_fd_rows"] == 2
    assert priced.chain.model_assumptions["american_fd_max_abs_gap"] == abs(gaps[1])


async def test_u8_existing_line_and_chain_values_are_preserved() -> None:
    """Compara toda projeção interna com a mesma captura sem o diagnóstico opcional."""
    with patch.object(demo_chain, "load_american_fd_config", return_value=None):
        before = await _demo()
    after = await _demo()
    _assert_same_primary(before, after)


def test_u9_cli_default_is_unchanged_and_live_is_disabled(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nenhuma chamada FD ou seu loader é alcançável sem o opt-in completo."""
    from backend.derivatives.cli import main

    assert main(DEMO) == 0
    baseline = capsys.readouterr().out
    with patch.object(demo_chain, "load_american_fd_config",
                      side_effect=AssertionError("unexpected access")) as loader:
        assert main(DEMO) == 0
        assert capsys.readouterr().out == baseline
        rc, live = invoke(ARGS, capsys)
    loader.assert_not_called()
    assert rc == 3 and live["data"]["status"] == "LIVE_NOT_ACTIVATED"


@pytest.mark.parametrize("invalid", [False, True], ids=["missing", "invalid"])
def test_u10_missing_or_invalid_fd_yaml_fails_only_for_mixed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], invalid: bool,
) -> None:
    """Sem fallback de perfil, sem afetar a demonstração europeia."""
    from backend.derivatives.cli import main

    path = tmp_path / "american_fd.yaml"
    if invalid:
        path.write_text("space_nodes: false\n", encoding="utf-8")
    assert main(DEMO) == 0
    baseline = capsys.readouterr().out
    with patch.object(demo_chain, "load_american_fd_config",
                      side_effect=lambda: load_american_fd_config(path)):
        assert main(DEMO) == 0
        assert capsys.readouterr().out == baseline
        rc, mixed = invoke([*DEMO, *OPTIONS], capsys)
    assert rc == 1 and mixed["error"] == "DEMO_UNAVAILABLE" and mixed["data"] == {}


async def test_u12_fd_gets_exact_tree_inputs_and_unit_mid_not_mark() -> None:
    """Fator 1000, rendimento não nulo e prazo não redondo expõem desvios de insumo."""
    priced, valuation = await _capture_before_american_projection()
    assert priced.chain.spot is not None and priced.time_to_expiry is not None
    spot = priced.chain.spot.model_copy(update={"price": Decimal("100")})
    tte = replace(priced.time_to_expiry, year_fraction=.33333333333333)
    priced = priced.model_copy(update={
        "chain": priced.chain.model_copy(update={"spot": spot}), "time_to_expiry": tte,
    })
    fixture = DemoFixture(Path(FIXTURE_DIR), mixed=True)
    assert fixture.registry_json is not None
    payload = json.loads(fixture.registry_json)
    record = payload["records"][0]
    record["terms"].update(
        strike="90", contract_size=37, quotation_form=1000, adjustment_policy="UNPROTECTED",
        evidence={"issuer": "B3", "document": "Synthetic-v1", "version": "test",
                  "published_on": "2026-11-05", "symbol": "SYNAC150",
                  "effective_on": "2026-11-05", "policy": "UNPROTECTED"},
    )
    record["carry"].update(kind="CONTINUOUS_YIELD", dividend_yield="0.04")
    registry = SeriesRegistry.model_validate_json(json.dumps(payload))
    canonical = _main_row(priced)
    row = canonical.row
    contract = row.contract.model_copy(update={
        "strike": Decimal("90"), "contract_size": 37, "quotation_form": 1000,
    })
    quote = row.quote.model_copy(update={"bid": Decimal("12400"), "ask": Decimal("12600")})
    item = canonical.model_copy(update={"row": row.model_copy(
        update={"contract": contract, "quote": quote},
    )})
    original_price = american_demo.price_american_contract

    def displaced_mark(*args: Any, **kwargs: Any) -> PricingOutcome:
        outcome = original_price(*args, **kwargs)
        assert outcome.price is not None
        return outcome.model_copy(update={"price": outcome.price + Decimal("0.025")})

    tree_solver, fd_solver = american_demo.american_implied_vol, american_demo.fd_implied_vol
    with (
        patch.object(american_demo, "american_implied_vol", wraps=tree_solver) as solve_tree,
        patch.object(american_demo, "fd_implied_vol", wraps=fd_solver) as solve_fd,
        patch.object(american_demo, "price_american_contract", side_effect=displaced_mark),
    ):
        result = american_demo._price_row(
            item, priced, registry, valuation=valuation, steps=32, rate=.05,
            iv_config=load_american_iv_config(), shadow_config=load_derivatives_config().iv,
            fd_config=load_american_fd_config(),
        )
    assert result.supported and result.price is not None and result.price != Decimal("12.5")
    assert result.assumptions["fd_iv_status"] == "ok"
    assert solve_tree.call_count == 3 and solve_fd.call_count == 1
    tree = solve_tree.call_args_list[-1]
    fd = solve_fd.call_args.kwargs
    assert fd["kind"] == tree.args[0].kind == OptionKind.CALL
    assert fd["strike"] == tree.args[0].strike == Decimal("90")
    assert fd["spot"] == tree.kwargs["spot"] == Decimal("100")
    assert fd["rate_cont"] == tree.kwargs["rate_cont"] == .05
    assert fd["time_years"] == tree.kwargs["tte"].year_fraction == tte.year_fraction
    assert fd["dividend_yield"] == float(tree.kwargs["carry"].dividend_yield) == .04
    assert fd["target_price"] == tree.kwargs["target_price"] == Decimal("12.5")


def _primary_sigma(priced: PricedChain) -> float:
    iv = _main_row(priced).pricing.iv
    assert iv is not None and iv.mid is not None and iv.mid.sigma is not None
    return iv.mid.sigma


async def test_u13_low_sensitivity_retains_gap_but_suppresses_alert() -> None:
    """Limiar de VI sozinho não alerta se o preço não reagiu."""
    normal = await _demo()
    primary = _primary_sigma(normal)
    fd_sigma = primary + .01
    with (
        patch.object(american_demo, "fd_price", return_value=3.),
        patch.object(american_demo, "fd_implied_vol", return_value=FdIvResult("ok", fd_sigma)),
    ):
        priced = await _demo()
    diag = _main_row(priced).pricing.assumptions
    assert diag["fd_iv_comparison"] == "low_sensitivity"
    assert diag["fd_iv_gap"] == primary - fd_sigma
    assert diag["fd_iv_alert"] is False
    assert priced.chain.model_assumptions["american_fd_low_sensitivity_rows"] == 1
    assert priced.chain.model_assumptions["american_fd_alert_rows"] == 0
    _assert_same_primary(normal, priced)


async def test_u14_strict_alert_threshold_exactly_equal_then_above() -> None:
    """Fixa igualdade binária exata e um valor representável abaixo no limiar."""
    cfg = load_american_fd_config()
    normal = await _demo()
    primary = _primary_sigma(normal)
    shadow = primary + cfg.divergence_vol
    exact_gap = abs(primary - shadow)
    for limit, expected in ((exact_gap, False), (math.nextafter(exact_gap, 0.), True)):
        with (
            patch.object(american_demo, "fd_implied_vol", return_value=FdIvResult("ok", shadow)),
            patch.object(demo_chain, "load_american_fd_config",
                         return_value=cfg.model_copy(update={"divergence_vol": limit})),
        ):
            altered = await _demo()
        diag = _main_row(altered).pricing.assumptions
        assert abs(float(diag["fd_iv_gap"])) == exact_gap
        assert diag["fd_iv_comparison"] == "informative"
        assert diag["fd_iv_alert"] is expected
        _assert_same_primary(normal, altered)


async def test_u15_price_gap_uses_primary_sigma_and_one_fixed_grid() -> None:
    """Reproduz o preço auxiliar em sigma CRR, com a malha exata da inversão."""
    cfg = load_american_fd_config().model_copy(update={"space_nodes": 440, "time_steps": 210})
    with (
        patch.object(demo_chain, "load_american_fd_config", return_value=cfg),
        patch.object(american_demo, "fd_price", wraps=fd_price) as price,
        patch.object(american_demo, "fd_implied_vol", wraps=american_demo.fd_implied_vol) as solve,
    ):
        priced = await _demo()
    result = _main_row(priced).pricing
    assert price.call_count == 2
    solve.assert_called_once()
    grid = solve.call_args.kwargs["grid"]
    assert grid == FdGrid(440, 210, cfg.width_stdevs, cfg.rannacher_steps)
    first, second = (call.kwargs for call in price.call_args_list)
    assert first["grid"] is second["grid"] is grid
    sigma = _primary_sigma(priced)
    assert first["sigma"] == sigma and second["sigma"] == sigma + cfg.divergence_vol
    assert result.price is not None
    assert result.assumptions["fd_grid"] == "440x210"
    assert result.assumptions["fd_price_gap"] == float(result.price) - fd_price(**first)


async def test_u3_primary_final_refusal_skips_fd_even_with_three_ivs() -> None:
    """Uma recusa tardia da árvore não deve executar o diagnóstico auxiliar."""
    original = american_demo.price_american_contract

    def refuse(*args: Any, **kwargs: Any) -> PricingOutcome:
        outcome = original(*args, **kwargs)
        return outcome.model_copy(update={"supported": False, "reason": "synthetic_refusal"})

    with (
        patch.object(american_demo, "price_american_contract", side_effect=refuse),
        patch.object(american_demo, "fd_implied_vol", wraps=american_demo.fd_implied_vol) as spy,
    ):
        priced = await _demo()
    row = _main_row(priced).pricing
    assert not row.supported and row.reason == "synthetic_refusal"
    assert "fd_engine" not in row.assumptions
    spy.assert_not_called()
