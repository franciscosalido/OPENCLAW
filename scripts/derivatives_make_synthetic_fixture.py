"""Gera a chain sintetica deterministica do Laboratorio de Derivativos (DL-PR06).

Dados **sinteticos** (``provenance=synthetic``, ``purpose=test``): precos derivados de
BSM com smile suave e spread arredondado ao centavo. Nunca sao mercado e nunca podem
ser apresentados como tal. Mesma semente e mesmos parametros geram os mesmos bytes.

Uso:
    uv run python scripts/derivatives_make_synthetic_fixture.py \
        --seed 20261105 --underlying BOVA11 --expiry 2026-11-19 --n 100 --style EUROPEAN
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from loguru import logger

from backend.derivatives.domain.models import OptionKind
from backend.derivatives.pricing.bsm import BsmInputs, price
from backend.derivatives.pricing.calendar import CalendarId, load_calendars
from backend.derivatives.pricing.conventions import time_to_expiry
from config.derivatives_config_model import load_derivatives_config

GENERATOR_VERSION = "1"
DEFAULT_DIR = Path("tests/fixtures/derivatives/synthetic")
VALUATION = datetime(2026, 11, 5, 17, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
SPOT = 150.0
RATE_PCT_AA = 14.9
STRIKE_STEP = 0.5
CONTRACT_SIZE = 100
QUOTATION_FORM = 1
NOTE = "dados sinteticos gerados por script; nunca apresentar como mercado"
ENDPOINTS = {
    "market_options_{u}.json": "GET /market/options/{symbol}",
    "market_stocks_{u}.json": "GET /market/stocks/{symbol}",
    "market_interest_rates.json": "GET /market/interest_rates",
    "market_status.json": "GET /market/status",
}


def smile_sigma(strike: float, forward: float) -> float:
    """Smile suave e deterministico em log-moneyness (referencia dos testes)."""
    k = math.log(strike / forward)
    return 0.22 - 0.10 * k + 0.90 * k * k


def series_symbol(underlying: str, kind: OptionKind, expiry: date, strike: float) -> str:
    """Codigo no formato B3: raiz + letra do mes (A-L call, M-X put) + strike x 10."""
    base = ord("A") if kind is OptionKind.CALL else ord("M")
    return f"{underlying[:4]}{chr(base + expiry.month - 1)}{round(strike * 10)}"


def build_fixture(
    *, seed: int, underlying: str, expiry: date, n: int, style: str, root: Path,
) -> dict[str, object]:
    """Monta os quatro payloads (nome de arquivo -> JSON) de uma captura coerente."""
    if n <= 0 or n % 2:
        raise ValueError("n deve ser par e positivo (uma call e uma put por strike)")
    cfg = load_derivatives_config()
    calendar = load_calendars(cfg.conventions, root=root)[CalendarId.B3_LISTED_TRADING]
    tte = time_to_expiry(calendar, valuation_date=VALUATION.date(), expiry=expiry,
                         cfg=cfg.conventions)
    rate_cont = math.log(1.0 + RATE_PCT_AA / 100.0)
    forward = SPOT * math.exp(rate_cont * tte.year_fraction)
    rng = random.Random(seed)
    stamp_ms = int(VALUATION.timestamp() * 1000)
    stamp_iso = VALUATION.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    strikes = [SPOT + STRIKE_STEP * (index - n // 4) for index in range(n // 2)]
    options: list[dict[str, object]] = []
    for strike in strikes:
        for kind in (OptionKind.CALL, OptionKind.PUT):
            fair = price(BsmInputs(kind=kind, spot=SPOT, strike=strike,
                                   time_years=tte.year_fraction, rate_cont=rate_cont,
                                   sigma=smile_sigma(strike, forward)), theta_basis=252).price
            half_spread = max(0.01, 0.01 * fair) * (1.0 + 0.5 * rng.random())
            bid = math.floor((fair - half_spread) * 100.0) / 100.0
            ask = math.ceil((fair + half_spread) * 100.0) / 100.0
            has_bid = bid >= 0.01
            options.append({
                "symbol": series_symbol(underlying, kind, expiry, strike),
                "name": f"SINTETICO {underlying} {strike:.2f} {expiry.isoformat()}",
                "category": kind.value, "type": kind.value, "maturity_type": style,
                "due_date": expiry.isoformat(), "strike": strike,
                "contract_size": CONTRACT_SIZE,
                "bid": bid if has_bid else 0, "ask": ask,
                "bid_volume": 100 * rng.randint(1, 50) if has_bid else 0,
                "ask_volume": 100 * rng.randint(1, 50),
                "close": round(fair, 2), "volume": 100 * rng.randint(1, 500),
                "trades": rng.randint(1, 200), "spot_price": SPOT, "time": stamp_ms,
                "last_trade_at": stamp_ms - 1000 * rng.randint(0, 30),
                "days_to_maturity": tte.business_days, "market_maker": False,
            })
    stock = {"symbol": underlying, "name": f"SINTETICO {underlying}", "type": "STOCK",
             "category": "VISTA", "bid": SPOT - 0.01, "ask": SPOT + 0.01, "close": SPOT,
             "bid_volume": 1000, "ask_volume": 1000, "volume": 1000000, "trades": 5000,
             "time": stamp_ms, "last_trade_at": stamp_ms, "contract_size": CONTRACT_SIZE,
             "quotation_form": QUOTATION_FORM, "has_options": True}
    rates = [{"name": "Taxa DI", "uid": "CETIP", "value": RATE_PCT_AA, "updated_at": stamp_iso},
             {"name": "Taxa Selic", "uid": "SELIC", "value": RATE_PCT_AA,
              "updated_at": stamp_iso}]
    status = {"market_status": "N", "server_time": VALUATION.isoformat()}
    payloads = (options, stock, rates, status)
    return {name.format(u=underlying): payload
            for name, payload in zip(ENDPOINTS, payloads, strict=True)}


def encode(payload: object) -> bytes:
    """JSON canonico: chaves ordenadas, separadores compactos, UTF-8 e quebra final."""
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_fixture(directory: Path, files: dict[str, object], params: dict[str, object]) -> Path:
    """Grava os payloads e o ``manifest.json`` com hashes; devolve o caminho do manifesto."""
    directory.mkdir(parents=True, exist_ok=True)
    entries: dict[str, dict[str, str]] = {}
    for (name, payload), endpoint in zip(files.items(), ENDPOINTS.values(), strict=True):
        data = encode(payload)
        (directory / name).write_bytes(data)
        entries[name] = {"sha256": hashlib.sha256(data).hexdigest(), "endpoint": endpoint}
    manifest = {"provenance": "synthetic", "purpose": "test", "note": NOTE,
                "generator": "scripts/derivatives_make_synthetic_fixture.py",
                "generator_version": GENERATOR_VERSION, "params": params,
                "valuation": VALUATION.isoformat(), "files": entries}
    path = directory / "manifest.json"
    path.write_bytes(encode(manifest))
    return path


def main(argv: Sequence[str] | None = None) -> int:
    """CLI do gerador; logs em stderr via loguru."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261105)
    parser.add_argument("--underlying", default="BOVA11")
    parser.add_argument("--expiry", type=date.fromisoformat, default=date(2026, 11, 19))
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--style", choices=("EUROPEAN", "AMERICAN"), default="EUROPEAN")
    parser.add_argument("--out", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args(argv)
    files = build_fixture(seed=args.seed, underlying=args.underlying, expiry=args.expiry,
                          n=args.n, style=args.style, root=Path.cwd())
    params: dict[str, object] = {
        "seed": args.seed, "underlying": args.underlying, "expiry": args.expiry.isoformat(),
        "n": args.n, "style": args.style, "spot": SPOT, "rate_pct_aa": RATE_PCT_AA}
    manifest = write_fixture(args.out, files, params)
    logger.info("fixture sintetica gravada: {} ({} opcoes)", manifest, args.n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
