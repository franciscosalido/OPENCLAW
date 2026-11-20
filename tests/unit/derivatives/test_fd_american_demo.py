"""Contratos de integração do FD na demonstração sintética."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.derivatives.cli import FIXTURE_DIR
from backend.derivatives.service.chain_service import PricedChain, PricedRow
from backend.derivatives.service.demo_chain import build_demo_chain


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
