"""Qualidade deterministica de cotacoes (DL-PR01): relogio injetado, limiares do contrato."""
from __future__ import annotations

from datetime import datetime

from backend.derivatives.domain.models import (ExerciseStyle, OptionContract, QualityFlags,
    Quote, SpotObservation, SpotSource)
from config.derivatives_config_model import Quality

def assess_quality(
    *, quote: Quote, contract: OptionContract, spot: SpotObservation | None,
    now: datetime, cfg: Quality,
) -> QualityFlags:
    """Deriva as flags de uma linha; limiar exato nao e stale; ``now`` naive e erro."""
    if now.tzinfo is None:
        raise ValueError("now deve ser datetime tz-aware")
    age_s = None if quote.source_time is None else (now - quote.source_time).total_seconds()
    not_sync = (spot is None or spot.source is SpotSource.OPTION_LAST_TRADE
        or spot.observed_at is None or quote.source_time is None
        or abs((spot.observed_at - quote.source_time).total_seconds()) > cfg.spot_sync_tolerance_s)
    checks = (("exercise_style", contract.exercise_style is ExerciseStyle.UNKNOWN),
        ("contract_size", contract.contract_size is None),
        ("quotation_form", contract.quotation_form is None),
        ("source_time", quote.source_time is None), ("spot", spot is None))
    return QualityFlags(
        stale=age_s is None or age_s > cfg.max_age_s, age_s=age_s,
        missing_bid=quote.bid is None, missing_ask=quote.ask is None,
        missing_last=quote.last is None, zero_volume=(quote.volume or 0) == 0,
        crossed_market=quote.bid is not None and quote.ask is not None and quote.bid > quote.ask,
        spot_not_synchronous=not_sync, spot_source=None if spot is None else spot.source,
        missing_metadata=tuple(name for name, absent in checks if absent),
    )
