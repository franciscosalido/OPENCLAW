"""Protocolo de latencia do Laboratorio de Derivativos (DL-PR06, CS10).

Mede N execucoes do ``ChainService`` sobre a fixture **sintetica** (nunca mercado),
separando ``t_acquire``, ``t_normalize``, ``t_price`` e ``t_serialize``, e grava um
JSON com p50/p95/p99 em ``reports/derivatives/`` (diretorio ignorado pelo Git).
A meta p95 < 2000 ms e **verificada** aqui, nunca declarada: o resultado vale para a
maquina e o interpretador registrados no proprio relatorio.

Uso:
    uv run python scripts/derivatives_latency_protocol.py --runs 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import platform
import sys
import time
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from loguru import logger

from backend.derivatives.oplab.client import OplabMarketClient
from backend.derivatives.oplab.transport import FixtureTransport
from backend.derivatives.pricing.calendar import load_calendars
from backend.derivatives.service.chain_service import ChainService
from config.derivatives_config_model import load_derivatives_config
from scripts.derivatives_make_synthetic_fixture import DEFAULT_DIR, VALUATION

SCHEMA_VERSION = "quimera-derivatives-latency-v1"
TARGET_P95_MS = 2000.0
STEPS = ("t_acquire", "t_normalize", "t_price", "t_serialize", "t_total")


def percentile(values: Sequence[float], pct: float) -> float:
    """Percentil por posto mais proximo (nearest-rank), sem interpolacao."""
    if not values:
        raise ValueError("percentil de sequencia vazia")
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100.0 * len(ordered)))
    return ordered[rank - 1]


async def measure(
    *, runs: int, fixture_dir: Path, symbol: str, expiry: date, root: Path,
) -> dict[str, object]:
    """Executa o protocolo e devolve o relatorio (sem gravar nada)."""
    if runs <= 0:
        raise ValueError("runs deve ser positivo")
    cfg = load_derivatives_config()
    started = time.perf_counter()
    calendars = load_calendars(cfg.conventions, root=root)
    startup_ms = (time.perf_counter() - started) * 1000.0
    now = VALUATION.astimezone(UTC) + timedelta(seconds=5)
    samples: dict[str, list[float]] = {step: [] for step in STEPS}
    rows = 0
    priced = 0
    for _ in range(runs):
        client = OplabMarketClient(FixtureTransport(fixture_dir), stamp_source="synthetic:")
        service = ChainService(client, cfg=cfg, calendars=calendars)
        t0 = time.perf_counter()
        capture = await service.acquire(symbol, now=now)
        t1 = time.perf_counter()
        chain = service.normalize(capture, expiry, now=now)
        t2 = time.perf_counter()
        result = service.price(chain, market_status=capture.status.market_status, now=now)
        t3 = time.perf_counter()
        payload = result.model_dump_json()
        t4 = time.perf_counter()
        for step, begin, end in zip(STEPS, (t0, t1, t2, t3, t0), (t1, t2, t3, t4, t4),
                                    strict=True):
            samples[step].append((end - begin) * 1000.0)
        rows = len(result.rows)
        priced = sum(1 for item in result.rows if item.pricing.supported)
        if result.purpose.value != "test" or not payload:
            raise RuntimeError("protocolo de latencia so roda sobre dados de teste")
    stats = {step: {"p50": percentile(values, 50), "p95": percentile(values, 95),
                    "p99": percentile(values, 99), "max": max(values)}
             for step, values in samples.items()}
    p95_total = stats["t_total"]["p95"]
    return {
        "schema_version": SCHEMA_VERSION, "provenance": "synthetic", "purpose": "test",
        "runs": runs, "rows": rows, "rows_priced": priced, "symbol": symbol,
        "expiry": expiry.isoformat(), "startup_calendars_ms": startup_ms, "ms": stats,
        "target_p95_ms": TARGET_P95_MS, "meets_target": p95_total < TARGET_P95_MS,
        "platform": {"system": platform.system(), "machine": platform.machine(),
                     "python": platform.python_version()},
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: grava o relatorio e devolve 0 se a meta foi atingida, 1 caso contrario."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--fixture-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--symbol", default="BOVA11")
    parser.add_argument("--expiry", type=date.fromisoformat, default=date(2026, 11, 19))
    parser.add_argument("--out-dir", type=Path, default=Path("reports/derivatives"))
    args = parser.parse_args(argv)
    report = asyncio.run(measure(runs=args.runs, fixture_dir=args.fixture_dir,
                                 symbol=args.symbol, expiry=args.expiry, root=Path.cwd()))
    measured_at = datetime.now(UTC)
    report["measured_at"] = measured_at.isoformat()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"latency_{measured_at.date().isoformat()}.json"
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("latencia gravada em {} (meta p95 {:.0f} ms; atingida: {})", out_path,
                TARGET_P95_MS, report["meets_target"])
    return 0 if report["meets_target"] else 1


if __name__ == "__main__":
    sys.exit(main())
