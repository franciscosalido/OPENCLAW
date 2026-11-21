"""Gera a referência independente da Fase 2C2 com o QuantLib.

Roda fora do ambiente do projeto, em contêiner descartável, com o QuantLib fixado por hash.
Não é importado por nenhum módulo ou teste. Uso:

    python generate_quantlib_reference.py SAIDA.json

Autor: Claude (cartão DL2C2). Não editar: o SHA-256 deste arquivo é conferido por teste.
"""
import json
import math
import platform
import sys

import QuantLib as ql

EXPECTED_QUANTLIB = "1.44"
TODAY = ql.Date(19, 11, 2026)
DAY_COUNT = ql.Actual365Fixed()
R_SELIC = math.log1p(0.149)


def _cases() -> list[tuple[str, str, float, float, int, float, float, float]]:
    """Lista fixa: id, tipo, spot, strike, dias corridos, taxa, rendimento, volatilidade."""
    out: list[tuple[str, str, float, float, int, float, float, float]] = []
    for spot in (90.0, 100.0, 110.0):  # A: call sem rendimento, o caso listado na B3
        for days in (30, 91, 365):
            for sigma in (0.20, 0.35):
                out.append((f"A{len(out) + 1:02d}", "CALL", spot, 100.0, days, R_SELIC, 0.0, sigma))
    carries = ((R_SELIC, 0.06), (R_SELIC, 0.12), (0.05, 0.10))
    start = len(out)
    for spot in (95.0, 105.0, 120.0):  # B: call com rendimento não compensado
        for days in (91, 365, 730):
            for index, (rate, q) in enumerate(carries):
                sigma = (0.25, 0.40, 0.20)[index]
                number = len(out) - start + 1
                out.append((f"B{number:02d}", "CALL", spot, 100.0, days, rate, q, sigma))
    start = len(out)
    for spot in (90.0, 100.0, 110.0):  # C: put americana, só para exercitar os motores
        for days in (30, 182, 730):
            for rate, q in ((R_SELIC, 0.0), (0.05, 0.02)):
                number = len(out) - start + 1
                out.append((f"C{number:02d}", "PUT", spot, 100.0, days, rate, q, 0.25))
    stress = (  # D: regimes de borda
        ("CALL", 131.0, 125.0, 730, 0.08, 0.0, 0.83),
        ("CALL", 100.0, 100.0, 730, R_SELIC, 0.05, 1.0),
        ("PUT", 100.0, 100.0, 730, R_SELIC, 0.04, 0.60),
        ("PUT", 100.0, 100.0, 7, R_SELIC, 0.0, 0.30),
        ("CALL", 100.0, 100.0, 365, R_SELIC, 0.16, 0.12),
        ("PUT", 80.0, 100.0, 365, 0.02, 0.0, 0.30),
    )
    for number, row in enumerate(stress, start=1):
        out.append((f"D{number:02d}", *row))
    return out


def _process(spot: float, rate: float, q: float, sigma: float) -> ql.BlackScholesMertonProcess:
    flat = lambda value: ql.YieldTermStructureHandle(  # noqa: E731
        ql.FlatForward(TODAY, value, DAY_COUNT, ql.Continuous, ql.NoFrequency))
    vol = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(TODAY, ql.NullCalendar(), sigma, DAY_COUNT))
    quote = ql.QuoteHandle(ql.SimpleQuote(spot))
    return ql.BlackScholesMertonProcess(quote, flat(q), flat(rate), vol)


def _option(kind: str, strike: float, days: int, american: bool) -> ql.VanillaOption:
    maturity = TODAY + days
    exercise = ql.AmericanExercise(TODAY, maturity) if american else ql.EuropeanExercise(maturity)
    side = ql.Option.Call if kind == "CALL" else ql.Option.Put
    return ql.VanillaOption(ql.PlainVanillaPayoff(side, strike), exercise)


def _npv(option: ql.VanillaOption, engine: ql.PricingEngine) -> float:
    option.setPricingEngine(engine)
    value = float(option.NPV())
    if not math.isfinite(value):
        raise SystemExit("preço não finito")
    return value


def main(path: str) -> None:
    """Escreve o JSON da referência; falha se a versão do QuantLib não for a fixada."""
    if ql.__version__ != EXPECTED_QUANTLIB:
        raise SystemExit(f"QuantLib {ql.__version__}; esperado {EXPECTED_QUANTLIB}")
    ql.Settings.instance().evaluationDate = TODAY
    rows = []
    for case_id, kind, spot, strike, days, rate, q, sigma in _cases():
        years = days / 365
        if DAY_COUNT.yearFraction(TODAY, TODAY + days) != years:
            raise SystemExit(f"{case_id}: prazo do QuantLib difere de dias/365")
        process = _process(spot, rate, q, sigma)
        american = _option(kind, strike, days, True)
        fine = ql.QdFpLegendreTanhSinhScheme(40, 100, 40, 1e-12)
        value = _npv(american, ql.QdFpAmericanEngine(process, fine))
        checks = (
            _npv(american, ql.QdFpAmericanEngine(process, fine, ql.QdFpAmericanEngine.FP_A)),
            _npv(american, ql.QdFpAmericanEngine(
                process, ql.QdFpAmericanEngine.highPrecisionScheme())),
        )
        grid = _npv(american, ql.FdBlackScholesVanillaEngine(
            process, 2000, 2000, 2, ql.FdmSchemeDesc.CrankNicolson()))
        european = _npv(_option(kind, strike, days, False), ql.AnalyticEuropeanEngine(process))
        rows.append({
            "id": case_id, "kind": kind, "spot": spot, "strike": strike, "days": days,
            "time_years": years, "rate_cont": rate, "dividend_yield": q, "sigma": sigma,
            "american": value, "american_uncertainty": max(abs(c - value) for c in checks),
            "american_fixed_point_a": checks[0], "american_high_precision_scheme": checks[1],
            "american_finite_differences": grid, "european": european,
        })
    document = {
        "schema": "quimera-quantlib-reference/1",
        "quantlib": ql.__version__, "python": platform.python_version(),
        "machine": platform.machine(), "system": platform.system(),
        "evaluation_date": "2026-11-19", "day_count": "Actual/365 (Fixed)",
        "compounding": "continuous",
        "american_engine": "QdFpAmericanEngine/QdFpLegendreTanhSinhScheme(40,100,40,1e-12)/Auto",
        "cross_checks": ["mesmo esquema com FP_A", "QdFpAmericanEngine/highPrecisionScheme",
                         "FdBlackScholesVanillaEngine/2000x2000/CrankNicolson/damping=2"],
        "european_engine": "AnalyticEuropeanEngine", "cases": rows,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=1, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    main(sys.argv[1])
