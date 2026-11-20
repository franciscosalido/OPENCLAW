"""Composição da chain de demonstração a partir da captura sintética fixada."""
from datetime import date, datetime
from pathlib import Path

from backend.derivatives.oplab.client import OplabMarketClient
from backend.derivatives.oplab.demo_fixture import REPO_ROOT, DemoFixture
from backend.derivatives.pricing.calendar import load_calendars
from backend.derivatives.service.chain_service import ChainService, PricedChain
from config.american_iv_config_model import load_american_iv_config
from config.derivatives_config_model import load_derivatives_config


class InvalidDemoSelection(ValueError):
    """A seleção offline exige a flag e o identificador; passos são opcionais."""


async def build_demo_chain(
    symbol: str, expiry: date, *, directory: Path, american_demo: bool,
    steps: int | None, series_registry: str | None,
) -> tuple[PricedChain, datetime]:
    """A mesma fixture fornece as quatro leituras, o relógio e o registro da seleção."""
    if american_demo is True:
        if ((steps is not None and (type(steps) is not int or not 1 <= steps <= 4999))
                or type(series_registry) is not str or series_registry != "synthetic-v1"):
            raise InvalidDemoSelection
    elif american_demo is not False or steps is not None or series_registry is not None:
        raise InvalidDemoSelection
    fixture = DemoFixture(directory, mixed=american_demo)
    cfg = load_derivatives_config()
    service = ChainService(OplabMarketClient(fixture, stamp_source="fixture:"), cfg=cfg,
                           calendars=load_calendars(cfg.conventions, root=REPO_ROOT))
    priced = await service.build(symbol, expiry, now=fixture.valuation)
    if american_demo:
        from backend.derivatives.service.american_demo import _price_mixed_demo

        iv_config = load_american_iv_config()
        priced = _price_mixed_demo(
            priced, fixture=fixture, steps=iv_config.default_steps if steps is None else steps,
            steps_source="config" if steps is None else "argument",
            conventions=cfg.conventions, iv_config=iv_config, shadow_config=cfg.iv,
        )
    return priced, fixture.valuation
