"""DL-PR06: ``ChainService`` — uma captura, quatro leituras, N calculos explicados."""

from __future__ import annotations

import json
import math
import shutil
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from backend.derivatives.domain.models import ExerciseStyle, OptionKind
from backend.derivatives.oplab.client import OplabMarketClient
from backend.derivatives.oplab.errors import NotFoundError
from backend.derivatives.oplab.routes import MarketRoute
from backend.derivatives.oplab.transport import FixtureTransport, VendorResponse
from backend.derivatives.pricing.calendar import CalendarId, TradingCalendar, load_calendars
from backend.derivatives.pricing.implied_vol import IvStatus
from backend.derivatives.provenance import Provenance, Purpose
from backend.derivatives.service.chain_service import (
    CALLS_PER_CAPTURE,
    ChainService,
    PricedChain,
)
from config.derivatives_config_model import DerivativesConfig, load_derivatives_config
from scripts.derivatives_make_synthetic_fixture import (
    RATE_PCT_AA,
    SPOT,
    VALUATION,
    smile_sigma,
)

SYNTHETIC = Path("tests/fixtures/derivatives/synthetic")
DOCUMENTAL = Path("tests/fixtures/derivatives/documental")
EXPIRY = date(2026, 11, 19)
NOW = VALUATION.astimezone(UTC) + timedelta(seconds=5)
CFG = load_derivatives_config()


class CountingTransport:
    """Envolve um transporte, conta as leituras e pode trocar a procedencia por rota."""

    def __init__(
        self, inner: FixtureTransport,
        provenance_by_route: Mapping[MarketRoute, Provenance] | None = None,
    ) -> None:
        self.inner = inner
        self.routes: list[MarketRoute] = []
        self._override = dict(provenance_by_route or {})

    async def get(
        self, route: MarketRoute, *, params: Mapping[str, str], now: datetime,
    ) -> VendorResponse:
        self.routes.append(route)
        response = await self.inner.get(route, params=params, now=now)
        if route not in self._override:
            return response
        return VendorResponse(response.status, response.json, response.headers_safe,
                              response.received_at, response.route, self._override[route])


@pytest.fixture(scope="module")
def calendars() -> dict[CalendarId, TradingCalendar]:
    return load_calendars(CFG.conventions, root=Path.cwd())


def _service(
    transport: object, calendars: Mapping[CalendarId, TradingCalendar],
    cfg: DerivativesConfig = CFG,
) -> ChainService:
    client = OplabMarketClient(transport, stamp_source="test:")  # type: ignore[arg-type]
    return ChainService(client, cfg=cfg, calendars=calendars)


async def _synthetic(calendars: Mapping[CalendarId, TradingCalendar]) -> PricedChain:
    return await _service(FixtureTransport(SYNTHETIC), calendars).build(
        "BOVA11", EXPIRY, now=NOW)


async def test_one_capture_is_exactly_four_reads_in_fixed_order(
    calendars: dict[CalendarId, TradingCalendar],
) -> None:
    transport = CountingTransport(FixtureTransport(SYNTHETIC))
    result = await _service(transport, calendars).build("BOVA11", EXPIRY, now=NOW)
    assert len(transport.routes) == CALLS_PER_CAPTURE == 4
    assert transport.routes == [MarketRoute.OPTIONS_CHAIN, MarketRoute.STOCK,
                                MarketRoute.INTEREST_RATES, MarketRoute.MARKET_STATUS]
    assert len(result.rows) == 100


async def test_synthetic_chain_is_priced_and_stays_test(
    calendars: dict[CalendarId, TradingCalendar],
) -> None:
    result = await _synthetic(calendars)
    assert result.schema_version == "quimera-derivatives-priced-chain-v1"
    assert result.purpose is Purpose.TEST
    assert result.chain.purpose is Purpose.TEST
    assert result.chain.stamp.provenance is Provenance.SYNTHETIC
    assert result.unpriceable_reason is None
    assert result.market_status == "N"
    assert result.valuation_date == date(2026, 11, 5)
    assert result.time_to_expiry is not None
    assert result.time_to_expiry.business_days == 10
    assert result.time_to_expiry.year_fraction == 10 / 252
    assert all(item.pricing.supported for item in result.rows)
    assert {item.row.contract.exercise_style for item in result.rows} == {
        ExerciseStyle.EUROPEAN}
    assert result.chain.spot is not None and float(result.chain.spot.price) == SPOT
    assert result.chain.rate is not None and result.chain.rate.uid == "SELIC"


async def test_model_assumptions_travel_with_the_chain_and_every_row(
    calendars: dict[CalendarId, TradingCalendar],
) -> None:
    result = await _synthetic(calendars)
    assumptions = result.chain.model_assumptions
    for key in ("calendar_id", "interval_convention", "year_basis", "rate_compounding",
                "rate_compounding_assumed", "dividend_yield",
                "strike_adjusted_by_exchange_assumed", "day_count_calendar_assumed"):
        assert key in assumptions, key
    assert assumptions["calendar_id"] == "B3_LISTED_TRADING"
    for item in result.rows:
        assert item.pricing.assumptions["pricing_model"] == "bsm_european_v1"
        assert item.pricing.assumptions["calendar_id"] == "B3_LISTED_TRADING"
        assert item.pricing.sigma_source == "mid"


async def test_true_smile_sigma_lies_inside_the_bid_ask_iv_bracket(
    calendars: dict[CalendarId, TradingCalendar],
) -> None:
    """Checagem independente de tempo, taxa e spot: o gerador conhece o sigma real."""
    result = await _synthetic(calendars)
    rate_cont = math.log(1.0 + RATE_PCT_AA / 100.0)
    forward = SPOT * math.exp(rate_cont * 10 / 252)
    checked = 0
    for item in result.rows:
        iv = item.pricing.iv
        assert iv is not None and iv.bid is not None and iv.ask is not None
        assert iv.mid is not None
        if iv.bid.diagnostic.status is not IvStatus.OK:
            continue
        if iv.ask.diagnostic.status is not IvStatus.OK:
            continue
        assert iv.bid.sigma is not None and iv.ask.sigma is not None
        assert iv.mid.sigma is not None
        truth = smile_sigma(float(item.row.contract.strike), forward)
        assert iv.bid.sigma - 1e-7 <= truth <= iv.ask.sigma + 1e-7, item.row.contract.symbol
        assert iv.bid.sigma <= iv.mid.sigma <= iv.ask.sigma
        checked += 1
    assert checked >= 60, f"so {checked} linhas com IV de bid e ask bem condicionadas"


async def test_priced_rows_reproduce_the_mid_and_have_sane_greeks(
    calendars: dict[CalendarId, TradingCalendar],
) -> None:
    result = await _synthetic(calendars)
    for item in result.rows:
        pricing = item.pricing
        mid = item.row.quote.mid
        assert pricing.price is not None and pricing.greeks is not None and mid is not None
        assert abs(float(pricing.price) - float(mid)) <= 1e-6
        delta = pricing.greeks["delta"]
        if item.row.contract.kind is OptionKind.CALL:
            assert 0.0 < delta < 1.0
        else:
            assert -1.0 < delta < 0.0
        assert pricing.greeks["gamma"] > 0.0
        assert pricing.greeks["vega_per_pct_point"] > 0.0
        assert pricing.inputs_echo["time_years"] == 10 / 252
        assert pricing.inputs_echo["spot"] == SPOT


async def test_documental_2021_chain_is_refused_for_calendar_coverage(
    calendars: dict[CalendarId, TradingCalendar],
) -> None:
    class CalendarTransport(FixtureTransport):
        async def get(self, route, *, params, now):
            if route is MarketRoute.STOCK:
                # O cenário de calendário precisa de PETR3; a doc só publica o spot de PETR4.
                return VendorResponse(200, {"symbol": "PETR3", "close": 10.0}, {}, now,
                                      "/market/stocks/PETR3", Provenance.SYNTHETIC)
            return await super().get(route, params=params, now=now)

    service = _service(CalendarTransport(DOCUMENTAL), calendars)
    capture = await service.acquire("PETR3", now=NOW)
    assert capture.stamp.provenance is Provenance.DOCUMENTAL
    chain = service.normalize(capture, date(2021, 5, 21), now=NOW)
    result = service.price(chain, market_status=capture.status.market_status, now=NOW)
    assert result.unpriceable_reason == "expiry_before_valuation"
    old_now = datetime(2021, 5, 10, 22, 0, tzinfo=UTC)
    past = service.price(chain, market_status="N", now=old_now)
    assert past.unpriceable_reason == "calendar_coverage"
    assert len(past.rows) == 1
    only = past.rows[0]
    assert only.row.contract.exercise_style is ExerciseStyle.AMERICAN
    assert only.pricing.supported is False
    assert only.pricing.reason == "chain_unpriceable:calendar_coverage"
    assert only.pricing.price is None and only.pricing.greeks is None
    assert only.pricing.iv is None and only.pricing.model is None
    assert past.time_to_expiry is None


def _clone_synthetic(tmp_path: Path) -> Path:
    target = tmp_path / "synthetic"
    shutil.copytree(SYNTHETIC, target)
    return target


async def test_american_rows_are_preserved_and_never_priced(
    tmp_path: Path, calendars: dict[CalendarId, TradingCalendar],
) -> None:
    directory = _clone_synthetic(tmp_path)
    path = directory / "market_options_BOVA11.json"
    options = json.loads(path.read_text(encoding="utf-8"))
    for option in options[:10]:
        option["maturity_type"] = "AMERICAN"
    del options[10]["maturity_type"]
    path.write_text(json.dumps(options), encoding="utf-8")
    result = await _service(FixtureTransport(directory), calendars).build(
        "BOVA11", EXPIRY, now=NOW)
    by_style: dict[ExerciseStyle, list[str | None]] = {}
    for item in result.rows:
        by_style.setdefault(item.row.contract.exercise_style, []).append(item.pricing.reason)
        if item.row.contract.exercise_style is not ExerciseStyle.EUROPEAN:
            assert item.pricing.supported is False
            assert item.pricing.price is None and item.pricing.greeks is None
            assert item.pricing.iv is None
    assert by_style[ExerciseStyle.AMERICAN] == ["american_not_supported_phase1"] * 10
    assert by_style[ExerciseStyle.UNKNOWN] == ["unknown_exercise_style"]
    assert len(by_style[ExerciseStyle.EUROPEAN]) == 89
    assert set(by_style[ExerciseStyle.EUROPEAN]) == {None}


@pytest.mark.parametrize(
    ("filename", "payload", "reason"),
    [("market_interest_rates.json", [], "missing_rate")],
)
async def test_missing_inputs_refuse_every_row_with_the_reason(
    tmp_path: Path, calendars: dict[CalendarId, TradingCalendar], filename: str,
    payload: object, reason: str,
) -> None:
    directory = _clone_synthetic(tmp_path)
    (directory / filename).write_text(json.dumps(payload), encoding="utf-8")
    result = await _service(FixtureTransport(directory), calendars).build(
        "BOVA11", EXPIRY, now=NOW)
    assert result.unpriceable_reason == reason
    assert len(result.rows) == 100
    assert {item.pricing.reason for item in result.rows} == {f"chain_unpriceable:{reason}"}
    assert all(item.pricing.price is None for item in result.rows)


def _set_every_rate(directory: Path, value: float) -> None:
    path = directory / "market_interest_rates.json"
    rates = json.loads(path.read_text(encoding="utf-8"))
    for rate in rates:
        rate["value"] = value
    path.write_text(json.dumps(rates), encoding="utf-8")


@pytest.mark.parametrize("value", [-100.0, -100.0000001, -150.0, -1e6])
async def test_compound_rate_out_of_domain_refuses_every_row_and_keeps_them(
    tmp_path: Path, calendars: dict[CalendarId, TradingCalendar], value: float,
) -> None:
    # NO-GO de 19/11: -100% a.a. chegava a log(0) e a excecao escapava de build().
    directory = _clone_synthetic(tmp_path)
    _set_every_rate(directory, value)
    result = await _service(FixtureTransport(directory), calendars).build(
        "BOVA11", EXPIRY, now=NOW)
    assert result.unpriceable_reason == "invalid_rate"
    assert result.time_to_expiry is None
    assert len(result.rows) == 100
    assert {item.pricing.reason for item in result.rows} == {"chain_unpriceable:invalid_rate"}
    for item in result.rows:
        assert item.pricing.supported is False
        assert item.pricing.price is None and item.pricing.greeks is None
        assert item.pricing.iv is None
    # A taxa recusada continua visivel na chain, para diagnostico.
    assert result.chain.rate is not None
    assert float(result.chain.rate.value_pct_aa) == value


@pytest.mark.parametrize("value", [-99.999999, -50.0, -0.5, 0.0])
async def test_negative_rates_inside_the_domain_are_still_priced(
    tmp_path: Path, calendars: dict[CalendarId, TradingCalendar], value: float,
) -> None:
    directory = _clone_synthetic(tmp_path)
    _set_every_rate(directory, value)
    result = await _service(FixtureTransport(directory), calendars).build(
        "BOVA11", EXPIRY, now=NOW)
    assert result.unpriceable_reason is None
    assert result.time_to_expiry is not None
    priced = [item.pricing.price for item in result.rows if item.pricing.supported]
    assert priced and all(price is not None and math.isfinite(price) for price in priced)
    assert not any((item.pricing.reason or "").startswith("chain_unpriceable")
                   for item in result.rows)


async def test_continuous_compounding_accepts_minus_100_pct(
    tmp_path: Path, calendars: dict[CalendarId, TradingCalendar],
) -> None:
    directory = _clone_synthetic(tmp_path)
    _set_every_rate(directory, -100.0)
    conventions = CFG.conventions.model_copy(update={"rate_compounding": "continuous"})
    cfg = CFG.model_copy(update={"conventions": conventions})
    result = await _service(FixtureTransport(directory), calendars, cfg).build(
        "BOVA11", EXPIRY, now=NOW)
    assert result.unpriceable_reason is None


async def test_missing_spot_refuses_every_row(
    tmp_path: Path, calendars: dict[CalendarId, TradingCalendar],
) -> None:
    directory = _clone_synthetic(tmp_path)
    stock_path = directory / "market_stocks_BOVA11.json"
    stock = json.loads(stock_path.read_text(encoding="utf-8"))
    del stock["close"]
    stock_path.write_text(json.dumps(stock), encoding="utf-8")
    options_path = directory / "market_options_BOVA11.json"
    options = json.loads(options_path.read_text(encoding="utf-8"))
    for option in options:
        del option["spot_price"]
    options_path.write_text(json.dumps(options), encoding="utf-8")
    result = await _service(FixtureTransport(directory), calendars).build(
        "BOVA11", EXPIRY, now=NOW)
    assert result.chain.spot is None
    assert result.unpriceable_reason == "missing_spot"
    assert {item.pricing.reason for item in result.rows} == {"chain_unpriceable:missing_spot"}


async def test_expired_chain_and_expiry_day_are_explained(
    calendars: dict[CalendarId, TradingCalendar],
) -> None:
    service = _service(FixtureTransport(SYNTHETIC), calendars)
    after = await service.build("BOVA11", EXPIRY, now=NOW + timedelta(days=20))
    assert after.unpriceable_reason == "expiry_before_valuation"
    assert all(item.pricing.supported is False for item in after.rows)
    on_expiry = await service.build(
        "BOVA11", EXPIRY, now=datetime(2026, 11, 19, 15, 0, tzinfo=UTC))
    assert on_expiry.time_to_expiry is not None
    assert on_expiry.time_to_expiry.is_expiry_day is True
    assert {item.pricing.reason for item in on_expiry.rows} == {
        "iv_unavailable:not_applicable"}


async def test_valuation_date_uses_the_b3_timezone(
    calendars: dict[CalendarId, TradingCalendar],
) -> None:
    service = _service(FixtureTransport(SYNTHETIC), calendars)
    late_utc = datetime(2026, 11, 6, 2, 30, tzinfo=UTC)
    result = await service.build("BOVA11", EXPIRY, now=late_utc)
    assert result.valuation_date == date(2026, 11, 5)
    assert result.time_to_expiry is not None
    assert result.time_to_expiry.business_days == 10


async def test_unsupported_day_count_is_refused_not_silently_ignored(
    calendars: dict[CalendarId, TradingCalendar],
) -> None:
    cfg = CFG.model_copy(update={
        "conventions": CFG.conventions.model_copy(update={"day_count": "calendar_365"})})
    result = await _service(FixtureTransport(SYNTHETIC), calendars, cfg).build(
        "BOVA11", EXPIRY, now=NOW)
    assert result.unpriceable_reason == "unsupported_day_count:calendar_365"
    assert all(item.pricing.price is None for item in result.rows)


async def test_unknown_expiry_yields_an_empty_chain_not_an_error(
    calendars: dict[CalendarId, TradingCalendar],
) -> None:
    result = await _service(FixtureTransport(SYNTHETIC), calendars).build(
        "BOVA11", date(2026, 12, 18), now=NOW)
    assert result.rows == ()
    assert result.unpriceable_reason is None


@pytest.mark.parametrize("fixture_route", list(MarketRoute))
async def test_one_test_read_contaminates_the_whole_capture(
    calendars: dict[CalendarId, TradingCalendar], fixture_route: MarketRoute,
) -> None:
    override = {route: Provenance.OBSERVED for route in MarketRoute if route != fixture_route}
    transport = CountingTransport(FixtureTransport(SYNTHETIC), override)
    result = await _service(transport, calendars).build("BOVA11", EXPIRY, now=NOW)
    assert result.chain.stamp.purpose is Purpose.TEST
    assert result.chain.purpose is Purpose.TEST
    assert result.purpose is Purpose.TEST


async def test_all_observed_reads_are_the_only_path_to_production(
    calendars: dict[CalendarId, TradingCalendar],
) -> None:
    override = {route: Provenance.OBSERVED for route in MarketRoute}
    transport = CountingTransport(FixtureTransport(SYNTHETIC), override)
    result = await _service(transport, calendars).build("BOVA11", EXPIRY, now=NOW)
    assert result.purpose is Purpose.PRODUCTION


async def test_purpose_survives_model_copy_and_json_round_trip(
    calendars: dict[CalendarId, TradingCalendar],
) -> None:
    result = await _synthetic(calendars)
    forged_chain = result.chain.model_copy(update={"purpose": Purpose.PRODUCTION})
    forged = result.model_copy(update={"chain": forged_chain})
    assert forged.chain.purpose is Purpose.PRODUCTION
    assert forged.purpose is Purpose.TEST, "model_copy nao pode promover fixture"
    restored = PricedChain.model_validate_json(result.model_dump_json())
    assert restored.purpose is Purpose.TEST
    assert restored.chain.stamp.provenance is Provenance.SYNTHETIC
    assert restored == result
    payload = json.loads(result.model_dump_json())
    payload["chain"]["purpose"] = "production"
    with pytest.raises(ValueError, match="purpose"):
        PricedChain.model_validate(payload)


async def test_build_is_deterministic(calendars: dict[CalendarId, TradingCalendar]) -> None:
    first = await _synthetic(calendars)
    second = await _synthetic(calendars)
    assert first.model_dump_json() == second.model_dump_json()


async def test_missing_stock_fixture_is_a_typed_error_not_a_partial_chain(
    calendars: dict[CalendarId, TradingCalendar],
) -> None:
    transport = CountingTransport(FixtureTransport(DOCUMENTAL))
    with pytest.raises(NotFoundError):
        await _service(transport, calendars).build("PETR3", date(2021, 5, 21), now=NOW)
    assert transport.routes == [MarketRoute.OPTIONS_CHAIN, MarketRoute.STOCK]
