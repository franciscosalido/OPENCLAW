# Lab de Derivativos DL-PR07 - Servidor MCP, barreira e fechamento da Fase 1

Branch: `feat/dl-pr07-mcp-server` (empilhada sobre `feat/dl-pr06-chain-service`)
GitHub Issue: pendente (sem card dedicado; segue o prompt v1 §5.4/§7, as
erratas v1.1 E4-E6 e o ADR-0023)
Status: implementado; aguarda PR e revisao

## Objective

Expor o Laboratorio por MCP, somente leitura, em loopback: servidor
`quimera-derivatives` (porta 8814) com **uma** tool produtiva,
`derivatives_chain(symbol, due_date)`, que responde `LIVE_NOT_ACTIVATED`
antes do estado C, e uma tool de demonstracao registrada **apenas** com
`QUIMERA_DERIV_CONTEXT=test` no ambiente do processo. A barreira de
procedencia garante que dado de teste nunca sai pela tool produtiva.

Nao-objetivos: provedor ao vivo, homologacao (estado B), promocao (estado
C), escrita, ordens, CLI (DL-PR08, opcional), Telegram, cache.

## Files

- `backend/derivatives/mcp/derivatives_server.py`: `create_derivatives_server`,
  `chain_tool`, `demo_tool`, `chain_view`, `production_view`,
  `ProvenanceBarrierError`, `system_clock`, `main`.
- `backend/derivatives/config.py`: `DerivativesMcpConfig.fixture_dir`, lido
  de `QUIMERA_DERIV_FIXTURE_DIR` (so usado pela demonstracao).
- Testes: `test_derivatives_mcp.py` (61); fronteiras de arquitetura
  atualizadas (20 no arquivo).

## Tools

| Tool | Quando existe | Resposta |
|---|---|---|
| `derivatives_health` | sempre | `HealthResponse` com `readiness`, `provider_mode`, `context` |
| `derivatives_chain` | sempre | `LIVE_NOT_ACTIVATED` (sem cotacao) antes do estado C |
| `derivatives_chain_demo` | so com contexto `test` | chain da fixture, `status=DEMO_TEST_DATA`, `purpose=test` |

Todas devolvem `backend.mcp.mcp_models.ToolResponse` (`schema_version`
`quimera-mcp-response-v1`); o payload de dominio vai em `data` com
`schema_version = quimera-derivatives-chain-v1`. Erro volta como
`ok=False` + `error` sanitizado (`mcp_safety.sanitize_error`), nunca como
excecao ao cliente.

## Decisoes dentro do escopo

- **Tres condicoes para a tool produtiva sair do `LIVE_NOT_ACTIVATED`:**
  `provider_mode == live_homologated`, `readiness == C` e um servico ao vivo
  injetado. Na Fase 1 nenhuma e alcancavel: o carregador de configuracao
  recusa `live_homologated` e `main()` nunca injeta servico. Sem ativacao
  completa o servico injetado **nem e chamado** (testado: zero leituras).
- **Barreira unica antes da serializacao (`production_view`).** Mesmo com
  configuracao forjada em codigo, a tool produtiva so serializa
  `PricedChain` cujo proposito efetivo e `production`. O proposito efetivo e
  worst-of (DL-PR06), entao uma unica leitura de fixture bloqueia; resiste
  a `model_copy`, a ida e volta por JSON e a reuso de objeto ("cache"). Um
  teste de arquitetura exige que a tool produtiva so saia por essa funcao.
- **Falha do provedor ao vivo e erro, nunca fallback para fixture.**
- **Contexto e diretorio de fixture vem do ambiente do processo.** As tools
  aceitam exatamente `symbol` e `due_date`; `mode`, `allow_fixture`, `path`,
  `url`, `provider`, `context`, `fixture_dir` sao rejeitados pelo schema.
- **Demonstracao reprodutivel:** o instante de avaliacao e o `valuation` do
  `manifest.json` da fixture, nao o relogio; a resposta nao "vence" com o
  passar dos dias. Diretorio sem manifesto (ex.: documental) e erro.
- **Visao compacta (`chain_view`).** Precos como texto decimal, numeros de
  modelo em float, flags de qualidade so as verdadeiras, IV com `sigma` e
  `status` por lado. `model_price` e o BSM na IV do mid (nao e cotacao). A
  resposta de 100 linhas tem ~67 KB.
- **Relogio real em um unico ponto** (`system_clock`), a raiz de composicao;
  todo o resto do Lab continua recebendo `now`.
- **Bind:** host, porta e caminho vem de `DerivativesMcpConfig`; o host nao
  e configuravel por ambiente e permanece `127.0.0.1`.
- **Simbolo em minusculas e normalizado** para maiusculas antes da
  validacao de formato.

## Como subir (estado A)

```bash
# producao (estado A): so health + derivatives_chain -> LIVE_NOT_ACTIVATED
uv run python -m backend.derivatives.mcp.derivatives_server

# demonstracao com dados sinteticos (nunca mercado)
QUIMERA_DERIV_CONTEXT=test \
QUIMERA_DERIV_FIXTURE_DIR=tests/fixtures/derivatives/synthetic \
uv run python -m backend.derivatives.mcp.derivatives_server
# endpoint: http://127.0.0.1:8814/mcp (streamable-http)
```

## Acceptance evidence (Linux aarch64, Python 3.12.16, `uv.lock`)

- `pytest tests/ --ignore=tests/integration`: rc 0, 8.028 passed, 15
  skipped. Lab + arquitetura: 5.891 passed em 3 ordens.
- `mypy backend/ --strict`: 0 erros (153 arquivos); `pyright backend/`: 0.
- Producao: 205 linhas (<= 400); 0 linhas > 100 colunas; protegidos
  intocados; nenhuma dependencia nova (`fastmcp` ja era dependencia).
- Fumaca de ponta a ponta (fora da suite): servidor real em
  `127.0.0.1:8814` (contexto `test`) e `:8815` (contexto `prod`), cliente
  FastMCP por HTTP: lista de tools correta, `LIVE_NOT_ACTIVATED`, demo com
  100 linhas; `ss` mostra bind so em loopback; boot com
  `QUIMERA_DERIV_PROVIDER_MODE=live_homologated` falha com
  `DerivativesConfigError`.

## Fechamento da Fase 1 — criterios do prompt v1

| CS | Criterio | Situacao | Onde |
|---|---|---|---|
| CS1 | pytest / mypy strict / pyright em 0 | atendido (gate sem `tests/integration`, errata E3) | todos os PRs |
| CS2 | nenhum teste abre socket | atendido (`no_network` autouse + flag) | DL-PR05b |
| CS3 | BSM x Hull e paridade | atendido | DL-PR03 / DL-PR04 Adendo 2 |
| CS4 | IV recupera sigma; fora de dominio nunca 0 | atendido | DL-PR04 |
| CS5 | americana sem numeros, com motivo | atendido | DL-PR03 / DL-PR06 |
| CS6 | recusa de host, rota, metodo, redirect | atendido | DL-PR05a/b |
| CS7 | orcamento e `Retry-After` sem retry | atendido | DL-PR05a/b |
| CS8 | procedencia e contaminacao | atendido | DL-PR06 / DL-PR07 |
| CS9 | MCP com tool produtiva e demo por contexto | atendido | DL-PR07 |
| CS10 | latencia p95 < 2 s em 100 europeias | medido em VM Linux no Mac (27,8 ms); **macOS nativo pendente** | DL-PR06 |
| CS11 | ADR-0023 com decisoes e pendencias | atendido | DL-PR00..07 |

DL-PR08 (CLI) e opcional e **nao foi feito**; segue no BACKLOG.

## O que nao esta demonstrado

- Nada desta fase tocou a API real: estado B (homologacao) depende da
  assinatura OpLab e de token, que sao decisoes e credenciais humanas.
- Consumo por um agente real (Helena, Armand, Dots) via cliente MCP externo.
- Execucao nativa em macOS desta pilha (validada em Linux aarch64).
- Integracao em `main`: as branches estao empilhadas e locais; faltam push,
  PRs e merges (acoes humanas).
