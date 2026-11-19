"""Gera a referência CRR americana e europeia em aritmética decimal de alta precisão.

Usa somente a biblioteca padrão e não importa nada do QUIMERA. O arquivo gerado traz o preço
exato da árvore CRR finita, nos valores binários que a produção recebe, e não o preço do
modelo contínuo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from pathlib import Path
from typing import Any

WORK_DIGITS = 60
CHECK_DIGITS = 90
PUBLISHED_DIGITS = 20
OUTPUT_NAME = "crr_american_reference.json"
RESULT_FIELDS = ("up", "prob_up", "discount", "european_price", "american_price")


@dataclass(frozen=True, slots=True)
class Case:
    """Um caso nominal; os números são o `repr` do binário de 64 bits usado na conta."""

    case_id: str
    group: str
    kind: str
    spot: str
    strike: str
    rate_cont: str
    dividend_yield: str
    sigma: str
    time_years: str
    steps: int


def _cases() -> tuple[Case, ...]:
    hull = ("put", "50.0", "50.0", "0.1", "0.0", "0.4", "0.4166666666666667")
    rows: list[tuple[str, str, str, str, str, str, str, str, int]] = [
        ("hull", *hull, 5),
        ("hull", *hull, 30),
        ("hull", *hull, 50),
        ("hull", *hull, 100),
        ("hull", *hull, 500),
        ("call_yield", "call", "100.0", "100.0", "0.05", "0.08", "0.2", "1.0", 200),
        ("call_yield", "call", "100.0", "100.0", "0.05", "0.08", "0.2", "1.0", 201),
        ("call_yield", "call", "100.0", "80.0", "0.05", "0.08", "0.2", "1.0", 200),
        ("call_yield", "call", "100.0", "120.0", "0.05", "0.08", "0.2", "1.0", 201),
        ("call_yield", "call", "100.0", "100.0", "0.12", "0.04", "0.4", "2.0", 200),
        ("call_yield", "call", "100.0", "90.0", "0.12", "0.12", "0.3", "0.5", 51),
        ("call_yield", "call", "100.0", "110.0", "0.02", "0.1", "0.25", "0.25", 50),
        ("call_yield", "call", "100.0", "50.0", "0.05", "0.15", "0.3", "1.0", 200),
        ("call_yield", "call", "130.0", "125.0", "0.13", "0.06", "0.22", "0.12", 100),
        ("call_yield", "call", "100.0", "100.0", "0.05", "0.08", "0.2", "1.0", 500),
        ("put_rate", "put", "100.0", "100.0", "0.05", "0.0", "0.2", "1.0", 200),
        ("put_rate", "put", "100.0", "100.0", "0.05", "0.0", "0.2", "1.0", 201),
        ("put_rate", "put", "100.0", "120.0", "0.05", "0.0", "0.2", "1.0", 200),
        ("put_rate", "put", "100.0", "80.0", "0.05", "0.0", "0.2", "1.0", 201),
        ("put_rate", "put", "100.0", "100.0", "0.12", "0.03", "0.35", "2.0", 200),
        ("put_rate", "put", "100.0", "150.0", "0.1", "0.0", "0.2", "1.0", 200),
        ("put_rate", "put", "100.0", "105.0", "0.13", "0.06", "0.22", "0.25", 51),
        ("put_rate", "put", "100.0", "100.0", "0.03", "0.07", "0.3", "1.0", 50),
        ("put_rate", "put", "100.0", "100.0", "0.05", "0.0", "0.2", "1.0", 500),
        ("put_rate", "put", "100.0", "110.0", "0.08", "0.0", "1.0", "0.5", 200),
        ("negative_rate", "call", "100.0", "90.0", "-0.05", "0.0", "0.2", "1.0", 200),
        ("negative_rate", "call", "100.0", "100.0", "-0.02", "0.0", "0.15", "2.0", 201),
        ("negative_rate", "call", "100.0", "60.0", "-0.03", "0.0", "0.25", "1.0", 50),
        ("negative_rate", "put", "100.0", "110.0", "-0.02", "0.0", "0.2", "1.0", 200),
        ("negative_rate", "put", "100.0", "100.0", "-0.01", "0.02", "0.3", "0.5", 51),
        ("no_premium", "call", "100.0", "100.0", "0.05", "0.0", "0.2", "1.0", 200),
        ("no_premium", "call", "100.0", "70.0", "0.0", "0.0", "0.3", "1.0", 201),
        ("no_premium", "call", "100.0", "130.0", "0.1", "0.0", "0.45", "0.1", 50),
        ("scale_and_tenor", "put", "0.5", "0.55", "0.1", "0.0", "0.6", "0.5", 100),
        ("scale_and_tenor", "call", "10000.0", "9500.0", "0.06", "0.09", "0.18", "1.0", 200),
        ("scale_and_tenor", "put", "100.0", "100.0", "0.13", "0.0", "0.25",
         "0.003968253968253968", 50),
        ("scale_and_tenor", "call", "100.0", "100.0", "0.05", "0.08", "0.2", "5.0", 201),
        ("scale_and_tenor", "put", "100.0", "100.0", "0.05", "0.0", "0.05", "1.0", 200),
        ("small_trees", "put", "100.0", "105.0", "0.05", "0.0", "0.2", "1.0", 1),
        ("small_trees", "put", "100.0", "105.0", "0.05", "0.0", "0.2", "1.0", 2),
        ("small_trees", "call", "100.0", "95.0", "0.05", "0.1", "0.2", "1.0", 3),
        ("small_trees", "call", "100.0", "95.0", "0.05", "0.1", "0.2", "1.0", 4),
    ]
    return tuple(Case(f"crr_{index:02d}_{row[0]}", *row) for index, row in enumerate(rows, 1))


def _binary(text: str) -> Decimal:
    value = float(text)
    if repr(value) != text:
        raise ValueError(f"entrada fora da forma canônica: {text}")
    return Decimal(value)


def _published(number: Decimal) -> str:
    return format(number, f".{PUBLISHED_DIGITS - 1}e")


def _solve(case: Case, digits: int) -> dict[str, str]:
    """Resolve a árvore por níveis, com cada preço de nó obtido por uma exponencial própria."""
    context = Context(prec=digits, rounding=ROUND_HALF_EVEN)
    with localcontext(context):
        spot, strike, rate, carry, sigma, time = (
            _binary(text) for text in (case.spot, case.strike, case.rate_cont,
                                       case.dividend_yield, case.sigma, case.time_years))
        steps = case.steps
        step_time = time / steps
        log_up = sigma * step_time.sqrt()
        up = log_up.exp()
        down = (-log_up).exp()
        prob_up = (((rate - carry) * step_time).exp() - down) / (up - down)
        if not 0 < prob_up < 1:
            raise ValueError(f"probabilidade inadmissível em {case.case_id}")
        prob_down = 1 - prob_up
        discount = (-rate * step_time).exp()
        sign = 1 if case.kind == "call" else -1
        asset = {net: spot * (log_up * net).exp() for net in range(-steps, steps + 1)}
        european = [max(Decimal(0), sign * (asset[2 * ups - steps] - strike))
                    for ups in range(steps + 1)]
        american = list(european)
        for level in range(steps - 1, -1, -1):
            for ups in range(level + 1):
                european[ups] = discount * (prob_up * european[ups + 1]
                                            + prob_down * european[ups])
                held = discount * (prob_up * american[ups + 1] + prob_down * american[ups])
                american[ups] = max(held, sign * (asset[2 * ups - level] - strike))
        closed = discount ** steps * sum(
            math.comb(steps, ups) * prob_up ** ups * prob_down ** (steps - ups)
            * max(Decimal(0), sign * (asset[2 * ups - steps] - strike))
            for ups in range(steps + 1))
        if _published(closed) != _published(european[0]):
            raise ValueError(f"europeia por indução e por soma fechada divergem: {case.case_id}")
        numbers = (up, prob_up, discount, european[0], american[0])
        return {name: _published(number)
                for name, number in zip(RESULT_FIELDS, numbers, strict=True)}


def _metadata(count: int) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "gerado_por": "Claude, revisor do Marco 2A; não é o implementador de binomial.py",
        "modelo": "árvore recombinante de Cox, Ross e Rubinstein com rendimento contínuo q",
        "o_que_e": "preço exato da árvore finita de N passos, europeia e americana",
        "o_que_nao_e": "não é o preço do modelo contínuo; o erro de discretização da árvore "
                       "não aparece aqui",
        "formulas": {
            "dt": "T_years / steps",
            "up": "exp(sigma * sqrt(dt))",
            "down": "exp(-sigma * sqrt(dt))",
            "prob_up": "(exp((r_cont - q) * dt) - down) / (up - down)",
            "discount": "exp(-r_cont * dt)",
            "no": "S * exp((altas - baixas) * sigma * sqrt(dt)), uma exponencial por nó",
            "americana": "max(continuação, intrínseco) em todo nó antes do vencimento, "
                         "inclusive na raiz",
        },
        "metodo": "indução retroativa por níveis em decimal.Decimal, arredondamento "
                  "ROUND_HALF_EVEN; exp e sqrt do módulo decimal são corretamente arredondadas",
        "precisao_de_trabalho_digitos": WORK_DIGITS,
        "precisao_de_conferencia_digitos": CHECK_DIGITS,
        "digitos_significativos_publicados": PUBLISHED_DIGITS,
        "conferencia": "cada resultado publicado é idêntico, nos 20 dígitos, quando a conta "
                       "inteira é refeita com 90 dígitos",
        "conferencia_da_europeia": "a europeia da indução coincide, nos 20 dígitos, com a "
                                   "soma binomial fechada de N + 1 termos",
        "politica_de_entrada": "S, K, r_cont, q, sigma e T_years são o repr do binário de 64 "
                               "bits; a conta parte do valor exato desse binário, de modo que "
                               "float(texto) reproduz a entrada da produção",
        "unidades": "taxas contínuas anuais em decimal; preços por unidade do ativo",
        "ancora_publicada": {
            "caso": "grupo hull, 5 passos",
            "fonte": "Hull, Risk Management and Financial Institutions, apêndice F",
            "valores_impressos": {"dt": "0.08333", "u": "1.1224", "d": "0.8909",
                                  "a": "1.0084", "p": "0.5073"},
        },
        "dependencias": "biblioteca padrão do Python; nenhuma importação do QUIMERA",
        "casos": count,
    }


def build_document() -> str:
    """Devolve o texto JSON completo, já conferido na precisão maior."""
    records: list[dict[str, Any]] = []
    for case in _cases():
        results = _solve(case, WORK_DIGITS)
        if results != _solve(case, CHECK_DIGITS):
            raise ValueError(f"dígitos publicados instáveis em {case.case_id}")
        records.append({
            "case_id": case.case_id, "group": case.group, "kind": case.kind,
            "S": case.spot, "K": case.strike, "r_cont": case.rate_cont,
            "q": case.dividend_yield, "sigma": case.sigma, "T_years": case.time_years,
            "steps": case.steps, **results,
        })
    document = {"metadata": _metadata(len(records)), "cases": records}
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    """Grava o JSON e o arquivo de SHA-256 na pasta indicada."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    folder: Path = parser.parse_args().output_dir
    payload = build_document().encode("utf-8")
    (folder / OUTPUT_NAME).write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    (folder / "crr_american_reference.sha256").write_text(
        f"{digest}  {OUTPUT_NAME}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
