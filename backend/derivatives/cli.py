"""CLI fino do Laboratorio de Derivativos (DL-PR08): ``quimera chain SYMBOL DATA``.

Segunda porta para as **mesmas** funcoes das tools MCP — nenhuma logica propria:
``--provider live`` (padrao) devolve ``LIVE_NOT_ACTIVATED``; ``--provider offline_fixture``
devolve a demonstracao sintetica, sempre rotulada como teste. JSON em stdout, logs em
stderr. Nao ha opcao de caminho, URL ou diretorio de fixture.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence

from loguru import logger

from backend.derivatives.config import DerivativesMcpConfig
from backend.derivatives.mcp.derivatives_server import (DEMO_TEST_DATA, Clock, chain_tool,
    demo_tool, system_clock)
from backend.derivatives.oplab.demo_fixture import REPO_ROOT

FIXTURE_DIR = "tests/fixtures/derivatives/synthetic"
EXIT_OK = 0
EXIT_REFUSED = 1  # entrada invalida ou demonstracao indisponivel (``ok=False``)
EXIT_NOT_ACTIVATED = 3  # provedor ao vivo fora do estado C: resposta valida, sem cotacao

def build_parser() -> argparse.ArgumentParser:
    """Monta o parser; ``chain`` e o unico subcomando da Fase 1."""
    parser = argparse.ArgumentParser(
        prog="quimera", description="Laboratorio de Derivativos do QUIMERA (estado A)")
    commands = parser.add_subparsers(dest="command", required=True)
    chain = commands.add_parser("chain", help="chain de opcoes de um subjacente")
    chain.add_argument("symbol", help="subjacente, ex.: BOVA11")
    chain.add_argument("due_date", help="vencimento em ISO 8601, ex.: 2026-11-19")
    chain.add_argument("--provider", choices=("live", "offline_fixture"), default="live",
                       help="offline_fixture serve dados sinteticos (nunca mercado)")
    chain.add_argument(
        "--american-demo", action="store_true", help="habilita a ponte americana na demo",
    )
    chain.add_argument(
        "--steps", type=int, help="passos CRR opcionais (1 a 4999; padrão no YAML)",
    )
    chain.add_argument("--series-registry", help="registro explícito da demo: synthetic-v1")
    chain.add_argument("--indent", type=int, default=None, help="indentacao do JSON")
    return parser

async def run_chain(
    symbol: str, due_date: str, provider: str, clock: Clock, *, american_demo: bool = False,
    steps: int | None = None, series_registry: str | None = None,
) -> dict[str, object]:
    """Despacha para a mesma funcao que atende a tool MCP correspondente."""
    if provider == "offline_fixture":
        config = DerivativesMcpConfig(context="test", fixture_dir=FIXTURE_DIR)
        return await demo_tool(symbol, due_date, config=config, root=REPO_ROOT,
                               american_demo=american_demo, steps=steps,
                               series_registry=series_registry)
    return await chain_tool(symbol, due_date, config=DerivativesMcpConfig(), clock=clock)

def exit_code(response: dict[str, object]) -> int:
    """0 so quando ha chain de demonstracao; nunca 0 para resposta sem cotacao."""
    data = response.get("data")
    status = data.get("status") if isinstance(data, dict) else None
    if response.get("ok") is True and status == DEMO_TEST_DATA:
        return EXIT_OK
    return EXIT_NOT_ACTIVATED if response.get("ok") is True else EXIT_REFUSED

def main(argv: Sequence[str] | None = None, *, clock: Clock = system_clock) -> int:
    """Executa o comando e escreve exatamente um documento JSON em stdout."""
    args = build_parser().parse_args(argv)
    response = asyncio.run(run_chain(args.symbol, args.due_date, args.provider, clock,
                                     american_demo=args.american_demo, steps=args.steps,
                                     series_registry=args.series_registry))
    sys.stdout.write(json.dumps(response, indent=args.indent, ensure_ascii=False) + "\n")
    return exit_code(response)

def run() -> None:
    """Ponto de entrada do console: logs so de WARNING para cima, em stderr."""
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    raise SystemExit(main())

if __name__ == "__main__":
    run()
