"""Testes da ponte cotacao -> IVs (DL-PR04): bid/ask/mid separados, cotacao intocada,
mid indicativo, e ``price_contract_from_quote`` com recusa explicada."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

import pytest

from backend.derivatives.domain.models import (
    ExerciseStyle,
    OptionContract,
    OptionKind,
    Quote,
)
from backend.derivatives.pricing.bsm import BsmInputs, price
from backend.derivatives.pricing.contract_pricing import (
    PricingOutcome,
    price_contract,
    price_contract_from_quote,
)
from backend.derivatives.pricing.conventions import TimeToExpiry
from backend.derivatives.pricing.implied_vol import IvStatus, implied_vol
from backend.derivatives.pricing.quote_iv import (
    PRICE_SOURCE_NOTE,
    QuoteIv,
    iv_for_quote,
)
from config.derivatives_config_model import Conventions, Iv

NOW = datetime(2026, 11, 6, 18, 0, tzinfo=UTC)
SPOT = Decimal("105.00")
RATE = 0.09
DAYS = 25
CFG_IV = Iv()
CONV = Conventions()
ASSUMPTIONS: dict[str, str | float | bool] = {"dividend_yield": 0.0}


def _contract(style: ExerciseStyle = ExerciseStyle.EUROPEAN,
              kind: OptionKind = OptionKind.CALL) -> OptionContract:
    return OptionContract(symbol="PETR4X100", underlying="PETR4", kind=kind,
                          exercise_style=style, strike=Decimal("100.00"),
                          expiry=date(2026, 12, 18), contract_size=None,
                          quotation_form=None, isin=None)


def _tte(days: int = DAYS) -> TimeToExpiry:
    return TimeToExpiry(business_days=days, year_fraction=days / 252.0,
                        convention="(D0,Dv]", calendar_id="B3_LISTED_TRADING",
                        basis=252, is_expiry_day=days == 0)


def _premium(sigma: float, kind: OptionKind = OptionKind.CALL,
             days: int = DAYS) -> Decimal:
    result = price(BsmInputs(kind=kind, spot=float(SPOT), strike=100.0,
                             time_years=days / 252.0, rate_cont=RATE, sigma=sigma,
                             dividend_yield=0.0), theta_basis=252)
    return Decimal(str(result.price))


def _quote(bid: Decimal | None, ask: Decimal | None) -> Quote:
    return Quote(bid=bid, ask=ask, last=None, bid_size=None, ask_size=None,
                 volume=None, trades=None, last_trade_at=None, source_time=None,
                 received_at=NOW)


def _ivs(quote: Quote, contract: OptionContract | None = None) -> QuoteIv:
    return iv_for_quote(quote, contract or _contract(), spot=SPOT, rate_cont=RATE,
                        tte=_tte(), cfg=CFG_IV, dividend_yield=0.0)


def _from_quote(quote: Quote, contract: OptionContract | None = None,
                sigma_source: Literal["mid", "bid", "ask"] = "mid") -> PricingOutcome:
    return price_contract_from_quote(
        contract or _contract(), quote, spot=SPOT, rate_cont=RATE, tte=_tte(),
        cfg_conv=CONV, cfg_iv=CFG_IV, assumptions=ASSUMPTIONS,
        sigma_source=sigma_source,
    )


def test_both_sides_present_give_three_independent_ivs() -> None:
    ivs = _ivs(_quote(_premium(0.24), _premium(0.28)))
    assert ivs.bid is not None and ivs.ask is not None and ivs.mid is not None
    assert ivs.bid.diagnostic.status is IvStatus.OK
    assert ivs.ask.diagnostic.status is IvStatus.OK
    assert ivs.mid.diagnostic.status is IvStatus.OK
    assert ivs.bid.sigma == pytest.approx(0.24, abs=1e-6)
    assert ivs.ask.sigma == pytest.approx(0.28, abs=1e-6)
    assert ivs.bid.sigma is not None and ivs.ask.sigma is not None
    assert ivs.mid.sigma is not None
    assert ivs.bid.sigma < ivs.mid.sigma < ivs.ask.sigma


def test_price_source_note_declares_mid_as_indicative() -> None:
    ivs = _ivs(_quote(_premium(0.24), _premium(0.28)))
    assert ivs.price_source_note == PRICE_SOURCE_NOTE
    assert "mid" in ivs.price_source_note


def test_only_bid_leaves_ask_and_mid_none() -> None:
    ivs = _ivs(_quote(_premium(0.24), None))
    assert ivs.bid is not None
    assert ivs.ask is None
    assert ivs.mid is None


def test_only_ask_leaves_bid_and_mid_none() -> None:
    ivs = _ivs(_quote(None, _premium(0.28)))
    assert ivs.ask is not None
    assert ivs.bid is None
    assert ivs.mid is None


def test_crossed_quote_still_computes_three_sides() -> None:
    # bid > ask: as tres IVs sao calculadas; sinalizar crossed_market e papel de
    # QualityFlags (DL-PR01), nao desta ponte.
    ivs = _ivs(_quote(_premium(0.30), _premium(0.20)))
    assert ivs.bid is not None and ivs.ask is not None and ivs.mid is not None
    assert ivs.bid.sigma is not None and ivs.ask.sigma is not None
    assert ivs.bid.sigma > ivs.ask.sigma
    assert "crossed_market" not in QuoteIv.model_fields


def test_quote_is_never_mutated() -> None:
    quote = _quote(_premium(0.30), _premium(0.20))
    before = quote.model_dump()
    _ivs(quote)
    assert quote.model_dump() == before


def test_matches_direct_inversion_bit_for_bit() -> None:
    bid = _premium(0.24)
    ivs = _ivs(_quote(bid, None))
    direct = implied_vol(float(bid), kind=OptionKind.CALL, spot=float(SPOT),
                         strike=100.0, time_years=DAYS / 252.0, rate_cont=RATE,
                         dividend_yield=0.0, cfg=CFG_IV)
    assert ivs.bid is not None
    assert ivs.bid.sigma == direct.sigma
    assert ivs.bid.diagnostic.iterations == direct.diagnostic.iterations
    assert ivs.bid.diagnostic.residual_price == direct.diagnostic.residual_price


def test_quote_iv_serializes_status_as_string() -> None:
    ivs = _ivs(_quote(_premium(0.24), _premium(0.28)))
    payload = json.loads(ivs.model_dump_json())
    assert payload["bid"]["diagnostic"]["status"] == "ok"
    assert isinstance(payload["mid"]["sigma"], float)
    assert payload["price_source_note"] == PRICE_SOURCE_NOTE


def test_bid_below_intrinsic_keeps_diagnostic_and_none_sigma() -> None:
    ivs = _ivs(_quote(Decimal("0.01"), None))
    assert ivs.bid is not None
    assert ivs.bid.diagnostic.status is IvStatus.BELOW_INTRINSIC
    assert ivs.bid.sigma is None


def test_from_quote_mid_prices_like_price_contract() -> None:
    outcome = _from_quote(_quote(_premium(0.24), _premium(0.28)))
    assert outcome.supported is True
    assert outcome.sigma_source == "mid"
    assert outcome.iv is not None
    assert outcome.iv.mid is not None and outcome.iv.mid.sigma is not None
    direct = price_contract(_contract(), spot=SPOT, rate_cont=RATE,
                            sigma=outcome.iv.mid.sigma, tte=_tte(), cfg=CONV,
                            assumptions=ASSUMPTIONS)
    assert outcome.price == direct.price
    assert outcome.greeks == direct.greeks
    assert outcome.inputs_echo["sigma"] == outcome.iv.mid.sigma


@pytest.mark.parametrize("source", ["bid", "ask"])
def test_from_quote_uses_requested_source(source: Literal["bid", "ask"]) -> None:
    outcome = _from_quote(_quote(_premium(0.24), _premium(0.28)),
                          sigma_source=source)
    assert outcome.supported is True
    assert outcome.sigma_source == source
    assert outcome.iv is not None
    side = outcome.iv.bid if source == "bid" else outcome.iv.ask
    assert side is not None
    assert outcome.inputs_echo["sigma"] == side.sigma


def test_from_quote_missing_source_is_explained_refusal() -> None:
    outcome = _from_quote(_quote(_premium(0.24), None), sigma_source="mid")
    assert outcome.supported is False
    assert outcome.reason == "iv_unavailable:missing_quote"
    assert outcome.reason.startswith("iv_unavailable:")
    assert outcome.price is None and outcome.greeks is None
    assert outcome.model is None and outcome.regime is None
    assert outcome.sigma_source is None
    assert outcome.inputs_echo["sigma"] == "unresolved"
    assert outcome.iv is not None
    assert outcome.iv.bid is not None
    assert outcome.iv.mid is None


def test_from_quote_unusable_status_is_explained_refusal() -> None:
    outcome = _from_quote(_quote(Decimal("0.01"), None), sigma_source="bid")
    assert outcome.supported is False
    assert outcome.reason == "iv_unavailable:below_intrinsic"
    assert outcome.price is None and outcome.greeks is None
    assert outcome.iv is not None
    assert outcome.iv.bid is not None
    assert outcome.iv.bid.diagnostic.status is IvStatus.BELOW_INTRINSIC


def test_from_quote_low_vega_sigma_is_still_usable() -> None:
    # Plato logo acima do intrinseco (S=110, K=100, r=q=0): a IV do ask converge
    # com LOW_VEGA e o sigma mal condicionado ainda precifica, levando o
    # diagnostico junto no resultado.
    quote = _quote(None, Decimal("10.0000000001"))
    outcome = price_contract_from_quote(
        _contract(), quote, spot=Decimal("110.00"), rate_cont=0.0, tte=_tte(),
        cfg_conv=CONV, cfg_iv=CFG_IV, assumptions=ASSUMPTIONS, sigma_source="ask")
    assert outcome.iv is not None and outcome.iv.ask is not None
    assert outcome.iv.ask.diagnostic.status is IvStatus.LOW_VEGA
    assert outcome.supported is True
    assert outcome.sigma_source == "ask"
    assert outcome.iv.ask.sigma is not None
    assert outcome.iv.ask.sigma > 0.0
    assert outcome.inputs_echo["sigma"] == outcome.iv.ask.sigma


@pytest.mark.parametrize(("style", "reason"), [
    (ExerciseStyle.AMERICAN, "american_not_supported_phase1"),
    (ExerciseStyle.UNKNOWN, "unknown_exercise_style"),
])
def test_from_quote_refuses_non_european_before_any_iv(
    style: ExerciseStyle, reason: str,
) -> None:
    outcome = _from_quote(_quote(_premium(0.24), _premium(0.28)),
                          contract=_contract(style))
    assert outcome.supported is False
    assert outcome.reason == reason
    assert outcome.iv is None
    assert outcome.sigma_source is None
    assert outcome.price is None and outcome.greeks is None
    assert outcome.inputs_echo["sigma"] == "unresolved"


def test_price_contract_outcome_keeps_new_fields_none_by_default() -> None:
    outcome = price_contract(_contract(), spot=SPOT, rate_cont=RATE, sigma=0.3,
                             tte=_tte(), cfg=CONV, assumptions=ASSUMPTIONS)
    assert outcome.supported is True
    assert outcome.iv is None
    assert outcome.sigma_source is None
