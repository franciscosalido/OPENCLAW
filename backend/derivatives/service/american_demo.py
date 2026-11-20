"""Ligação do registro e da ponte às linhas americanas da captura sintética."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from backend.derivatives.domain.models import ExerciseStyle
from backend.derivatives.domain.carry import CarryRefusal
from backend.derivatives.domain.series_registry import RegistryRefusal, SeriesRegistry
from backend.derivatives.oplab.demo_fixture import DemoFixture
from backend.derivatives.pricing.american_bridge import (
    AMERICAN_MODEL, AmericanIvRefusal, AmericanIvSolution, american_implied_vol,
    price_american_contract,
)
from backend.derivatives.pricing.contract_pricing import PricingOutcome
from backend.derivatives.pricing.conventions import continuous_rate
from backend.derivatives.pricing.implied_vol import IvStatus, implied_vol
from backend.derivatives.pricing.quote_iv import IvDiagnosticModel, IvResultModel, QuoteIv
from backend.derivatives.provenance import Provenance, Purpose
from backend.derivatives.service.chain_service import B3_TIMEZONE, PricedChain, PricedRow
from config.american_iv_config_model import AmericanIvConfig
from config.derivatives_config_model import Conventions, Iv

SHADOW_ENGINE = "bsm_european_v1"


def _iv_side(result: AmericanIvSolution | AmericanIvRefusal) -> IvResultModel:
    """Conserva o motivo ou o modelo do PR02 no diagnóstico do contrato existente."""
    message: str
    lo: float | None = None
    hi: float | None = None
    if isinstance(result, AmericanIvSolution):
        status, message = IvStatus.OK, result.model
        lo, hi = result.bracket
    else:
        message = result.reason
        status = {
            "iv:below_intrinsic": IvStatus.BELOW_INTRINSIC,
            "iv:above_upper_bound": IvStatus.ABOVE_UPPER_BOUND,
            "iv:no_convergence": IvStatus.NO_CONVERGENCE,
            "iv:unbracketed": IvStatus.NO_CONVERGENCE,
            "iv:expiry": IvStatus.NOT_APPLICABLE,
            "iv:not_identifiable": IvStatus.NOT_APPLICABLE,
        }.get(message, IvStatus.DOMAIN_ERROR)
    return IvResultModel(sigma=result.sigma, diagnostic=IvDiagnosticModel(
        status=status, iterations=result.iterations, bracket_lo=lo, bracket_hi=hi,
        residual_price=None, residual_vol=None, vega_at_solution=None,
        expansions=result.expansions, message=message))


def _price_row(item: PricedRow, priced: PricedChain, registry: SeriesRegistry, *,
               valuation: datetime, steps: int, rate: float,
               iv_config: AmericanIvConfig, shadow_config: Iv) -> PricingOutcome:
    chain, tte = priced.chain, priced.time_to_expiry
    row = item.row
    quote, contract = row.quote, row.contract

    def refused(reason: str, iv: QuoteIv | None = None) -> PricingOutcome:
        return PricingOutcome(
            supported=False, reason=reason, model=None, price=None, greeks=None, regime=None,
            inputs_echo={"symbol": contract.symbol}, assumptions={}, iv=iv)

    assert chain.spot is not None and chain.rate is not None and tte is not None
    if quote.source_time is None:
        return refused("quality:missing_source_time")
    if chain.rate.observed_at is None:
        return refused("quality:missing_rate_time")
    if (chain.acquired_at != valuation or chain.stamp.captured_at != valuation
            or quote.received_at != valuation or quote.source_time > valuation
            or chain.rate.observed_at > valuation
            or (chain.spot.observed_at is not None and chain.spot.observed_at > valuation)):
        return refused("quality:clock_mismatch")
    if row.quality.stale:
        return refused("quality:stale_quote")
    if row.quality.spot_not_synchronous:
        return refused("quality:spot_not_synchronous")
    try:
        resolved = registry.resolve(contract, as_of=valuation.astimezone(B3_TIMEZONE).date())
        record = resolved.record
    except RegistryRefusal as exc:
        return refused(f"registry:{exc.code.value}")
    except CarryRefusal as exc:
        return refused(f"carry:{exc.code.value}")
    spot = chain.spot.price

    def invert(price: Decimal | None) -> IvResultModel | None:
        if price is None:
            return None
        return _iv_side(american_implied_vol(
            contract, terms=record.terms, carry=record.carry, spot=spot,
            target_price=price / record.terms.quotation_form, rate_cont=rate, tte=tte, steps=steps,
            cfg=iv_config))

    iv = QuoteIv(bid=invert(quote.bid), ask=invert(quote.ask), mid=invert(quote.mid))
    if iv.mid is None:
        return refused("iv_unavailable:missing_quote", iv)
    if iv.mid.sigma is None:
        return refused(iv.mid.diagnostic.message, iv)
    outcome = price_american_contract(
        contract, terms=record.terms, carry=record.carry, spot=spot, rate_cont=rate,
        sigma=iv.mid.sigma, tte=tte, steps=steps, assumptions=chain.model_assumptions)
    outcome = outcome.model_copy(
        update={"iv": iv, "sigma_source": "mid" if outcome.supported else None},
    )
    if not outcome.supported:
        return outcome

    mid = quote.mid
    assert mid is not None
    assumptions = dict(outcome.assumptions, shadow_engine=SHADOW_ENGINE)
    try:
        shadow = implied_vol(
            float(mid / record.terms.quotation_form), kind=contract.kind, spot=float(spot),
            strike=float(contract.strike), time_years=tte.year_fraction, rate_cont=rate,
            dividend_yield=resolved.carry.dividend_yield, cfg=shadow_config,
        )
        assumptions["shadow_iv_status"] = shadow.diagnostic.status.value
        if shadow.sigma is not None:
            assumptions.update(shadow_iv_mid=shadow.sigma, shadow_iv_gap=iv.mid.sigma - shadow.sigma)
    except Exception:
        assumptions["shadow_iv_status"] = "error"
    return outcome.model_copy(update={"assumptions": assumptions})


def _price_mixed_demo(priced: PricedChain, *, fixture: DemoFixture, steps: int,
                     conventions: Conventions, iv_config: AmericanIvConfig, shadow_config: Iv,
                     steps_source: Literal["config", "argument"]) -> PricedChain:
    """Conserva a ordem da captura. Só a raiz de composição da demo chama esta função."""
    chain = priced.chain
    if (chain.purpose is not Purpose.TEST or chain.stamp.purpose is not Purpose.TEST
            or chain.stamp.provenance is not Provenance.SYNTHETIC or fixture.registry_json is None):
        raise ValueError("fixture_provenance")
    if type(steps) is not int or not 1 <= steps <= 4999:
        raise ValueError("invalid_steps")
    registry = SeriesRegistry.model_validate_json(fixture.registry_json)
    if registry.version != "synthetic-v1":
        raise ValueError("fixture_registry")
    if priced.unpriceable_reason is not None:
        return priced
    assert chain.rate is not None
    rate = continuous_rate(chain.rate.value_pct_aa, compounding=conventions.rate_compounding)
    rows = tuple(
        PricedRow(row=item.row, pricing=_price_row(item, priced, registry,
                  valuation=fixture.valuation, steps=steps, rate=rate, iv_config=iv_config,
                  shadow_config=shadow_config))
        if item.row.contract.exercise_style is ExerciseStyle.AMERICAN else item
        for item in priced.rows)
    # Preserve as chaves v1 da Fase 1; a linha americana usa somente o carry resolvido.
    assumptions = dict(chain.model_assumptions)
    assumptions.update(american_pricing_model=AMERICAN_MODEL, american_crr_steps=steps,
                       american_series_registry=registry.version)
    gaps = [abs(float(item.pricing.assumptions["shadow_iv_gap"])) for item in rows
            if "shadow_iv_gap" in item.pricing.assumptions]
    assumptions.update(american_crr_steps_source=steps_source,
                       american_shadow_engine=SHADOW_ENGINE, american_shadow_rows=len(gaps))
    if gaps:
        assumptions["american_shadow_max_abs_gap"] = max(gaps)
    return priced.model_copy(update={
        "rows": rows, "chain": chain.model_copy(update={"model_assumptions": assumptions})})
