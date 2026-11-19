"""Regressões independentes da fase A; dados artificiais e transporte em memória."""
from datetime import date
from pathlib import Path
import json
import shutil

import httpx
import pytest

from backend.derivatives.domain.models import OptionKind
from backend.derivatives.oplab.budget import RequestBudget
from backend.derivatives.oplab.client import OplabMarketClient
from backend.derivatives.oplab.errors import OplabError
from backend.derivatives.oplab.transport import FixtureTransport, HttpTransport
from backend.derivatives.oplab.vendor_models import VendorPayloadError
from backend.derivatives.pricing.bsm import BsmInputs, price
from backend.derivatives.pricing.calendar import load_calendars
from backend.derivatives.provenance import Purpose
from backend.derivatives.service.chain_service import ChainService
from config.derivatives_config_model import load_derivatives_config
from scripts.derivatives_make_synthetic_fixture import VALUATION

FIXTURE = Path("tests/fixtures/derivatives/synthetic")
EXPIRY = date(2026, 11, 19)

def test_tail_put_against_decimal_oracle():
    # Referência recalculável em validacao/oraculo.py; o piso absoluto default de pytest não serve.
    result = price(BsmInputs(OptionKind.PUT, 100, 70, 2, 0.10, 0.05), theta_basis=252)
    assert result.price == pytest.approx(1.145122080277693e-15, rel=1e-9, abs=0.0)

async def build(transport):
    cfg = load_derivatives_config()
    client = OplabMarketClient(transport, stamp_source="teste:")
    service = ChainService(client, cfg=cfg, calendars=load_calendars(cfg.conventions, root=Path.cwd()))
    return await service.build("BOVA11", EXPIRY, now=VALUATION)

async def test_mock_transport_fixture_chain_stays_test():
    cfg = load_derivatives_config()
    files = {"/v3/market/options/BOVA11": "market_options_BOVA11.json",
             "/v3/market/stocks/BOVA11": "market_stocks_BOVA11.json",
             "/v3/market/interest_rates": "market_interest_rates.json",
             "/v3/market/status": "market_status.json"}
    calls = []
    def fixture(request):
        calls.append(request.url.path)
        return httpx.Response(200, content=(FIXTURE / files[request.url.path]).read_bytes())
    transport = HttpTransport(cfg.oplab, RequestBudget(cfg.budget, key="fixture"),
                              env={"OPLAB_TOKEN": "synthetic-placeholder"},
                              mock_transport=httpx.MockTransport(fixture))
    result = await build(transport)
    assert len(result.rows) == 100 and calls == list(files)
    assert result.purpose is Purpose.TEST, (result.chain.stamp.provenance, result.purpose)

async def test_invalid_annual_rate_has_a_domain_refusal(tmp_path):
    directory = tmp_path / "synthetic"
    shutil.copytree(FIXTURE, directory)
    options = directory / "market_options_BOVA11.json"
    options.write_text(json.dumps(json.loads(options.read_bytes())[:1]))
    file = directory / "market_interest_rates.json"
    rates = json.loads(file.read_bytes())
    for rate in rates:
        rate["value"] = -100.0
    file.write_text(json.dumps(rates))
    try:
        result = await build(FixtureTransport(directory))
    except (VendorPayloadError, OplabError):
        return
    assert result.rows and all(not row.pricing.supported and row.pricing.reason
                               for row in result.rows)
