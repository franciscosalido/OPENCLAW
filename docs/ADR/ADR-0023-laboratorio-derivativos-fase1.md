# ADR-0023 - Laboratorio de Derivativos - Fase 1

## Status

Accepted (decisoes tomadas por Francisco em 2026-11-05)

## Contexto

O QUIMERA ainda nao tem MVP de derivativos. O Departamento de Producoes
precisa de uma fatia funcional offline — transporte simulado, normalizacao,
precificacao BSM local, servico de chain e servidor MCP — consumivel por
agentes consultores de forma agnostica (MCP), sem assinatura OpLab ativa e
sem nenhuma chamada de rede real nesta fase.

A API alvo e a OpLab REST v3 (documentacao lida em 2026-11-05). O mesmo token
que le `/market/*` tambem opera o dominio de ordens, o que eleva a allowlist
de rotas em codigo a controle de seguranca, nao estilo.

## Decisoes 1-8

| # | Decisao | Rejeitado | Motivo |
|---|---|---|---|
| 1 | O Lab so comeca com FL-PR14 mergeado, arvore limpa e `main == origin/main` | Comecar sobre stack local nao publicada | Isolamento de diffs e auditabilidade dos PRs do Lab |
| 2 | Fase 1 inteiramente offline com fixtures (`provider.mode = offline_fixture`) | Smoke autenticado ja na Fase 1 | Sem assinatura ativa; token e credencial sensivel; homologacao e fase propria (estado B) |
| 3 | Zero dependencias novas: BSM com `math.erf/log/exp`, bissecao em Python puro | NumPy/SciPy/pandas | Teto de dependencias do projeto; auditabilidade; suficiencia numerica para europeias |
| 4 | So europeias recebem BSM; americanas sao preservadas e marcadas, nunca precificadas | CRR / Bjerksund-Stensland na Fase 1 | Corretude antes de cobertura; modelos americanos exigem referencia propria (Fase 2) |
| 5 | Allowlist de rotas `/market/*` enumeradas em codigo; dominio de ordens proibido | Confiar em configuracao ou disciplina de uso | O mesmo token opera ordens; a allowlist e controle de seguranca |
| 6 | Barreira deterministica de procedencia: `purpose` worst-of; tool produtiva responde `LIVE_NOT_ACTIVATED` antes do estado C | Flag simples de "modo demo" | Fixture nunca pode chegar a um agente consumidor como se fosse mercado |
| 7 | Fixtures documentais byte a byte da doc oficial, com manifesto de hashes | Inventar fixtures "realistas" | Proveniencia verificavel; divergencia com a API real e retrabalho aceito na homologacao |
| 8 | Superficie de consumo via MCP (porta 8814), reutilizando `ToolResponse`/`mcp_safety` do padrao existente | CLI/FastAPI como interface primaria | Agentes consultores agnosticos; padrao MCP ja homologado no repo (8811-8813) |

## Tres estados de prontidao (nunca misturar)

- **A — verificado offline**: tudo que a Fase 1 entrega. `provider.mode = offline_fixture`.
- **B — homologado**: so apos assinatura e observacao de respostas reais. Fora desta fase.
- **C — producao**: B mais promocao explicita de Francisco em config confiavel. Fora desta fase.

Antes de C, a tool produtiva `derivatives_chain` retorna
`{"status": "LIVE_NOT_ACTIVATED", "readiness": "A", ...}` e nenhum campo de
cotacao. A tool de demonstracao so existe com `QUIMERA_DERIV_CONTEXT=test` no
ambiente do processo.

## Arquitetura alvo

```text
backend/derivatives/
  __init__.py  config.py  provenance.py          (DL-PR00)
  oplab/    routes, vendor_models, transport, budget, errors, client  (DL-PR01/04)
  domain/   models, normalize, quality                                (DL-PR01)
  pricing/  conventions, bsm, implied_vol, position                   (DL-PR02/03)
  service/  chain_service                                             (DL-PR05)
  mcp/      derivatives_server                                        (DL-PR06)
config/derivatives.yaml + config/derivatives_config_model.py          (DL-PR00)
tests/fixtures/derivatives/{documental,synthetic}/
```

Fronteiras de import (teste de arquitetura garante): `pricing/` e `domain/`
nao importam `oplab/`, `mcp/` nem I/O; `oplab/` nao importa `pricing/`; so
`service/` compoe. Nesta fase (DL-PR00) o pacote inteiro nao importa
`backend.mcp`, `httpx`, `asyncpg` nem `qdrant_client`.

## Convencoes numericas (hipoteses declaradas, com flag)

Todas configuraveis em `config/derivatives.yaml` e carregadas em
`Chain.model_assumptions` a partir do DL-PR01:

- Tempo: `T = dias_uteis_B3 / 252` (default); calendario de feriados em YAML;
  ausente gera `holidays_missing=true`. Alternativa nomeada: `calendar_365`.
- Taxa: `interest_rates.value` e % a.a.; **hipotese**: capitalizacao
  exponencial base 252 (padrao CDI/Selic), `r_cont = ln(1 + i/100)`, com
  `rate_compounding_assumed=true` ate homologacao.
- Dividendos: `q = 0` com `strike_adjusted_by_exchange_assumed=true` (B3
  ajusta strikes por proventos; hipotese a confirmar por contrato).
- Volatilidade: fracao decimal anualizada (0.25 = 25%).
- Gregas por unidade da opcao, com a unidade no nome do campo:
  `vega_per_pct_point`, `rho_per_pct_point`, `theta_per_day`.
- Multiplicador: `contract_size` e `quotation_form` sao campos distintos;
  conversao monetaria so com ambos presentes; **nunca assumir 100**.
- Spot: `spot_price` da linha da opcao e o spot no ultimo negocio da opcao,
  nao cotacao atual; flag `spot_not_synchronous` quando dessincronizado.

## Calendarios 3.0.0 e convencoes temporais (DL-PR02)

Os bundles `config/calendars/b3_calendar_{2026,2027,2028}.yaml`
(schema 3.0.0, JSON estrito, checksums em `SHA256SUMS`, evidencia
OC 041/2026 errata) substituem o `holidays_file` previsto acima. Hipoteses
declaradas, com flag, ate homologacao:

- **`trading` como relogio do DU** (`day_count_calendar: trading`,
  `day_count_calendar_assumed: true`): a contagem de dias uteis usa
  `B3_LISTED_TRADING`; `BR_ANBIMA_BUSINESS` fica carregado como referencia
  financeira. A equivalencia DU pregao x DU financeiro na B3 nao esta
  demonstrada.
- **Convencao de intervalo `(D0,Dv]`** (`interval_convention_assumed: true`):
  exclui a data de avaliacao, inclui o vencimento — padrao DU brasileiro.
- **Base anual 252** (`year_basis: 252`): os 247/249/251 dias observados nos
  calendarios nao substituem o denominador 252.
- **Recusa do desconhecido:** B3 2027/2028 sao `unknown` nos bundles; esses
  anos ficam fora de `coverage_years` e qualquer contagem que os toque
  levanta `CalendarCoverageError`. A projecao 2027 e lida e ignorada; nunca
  e promovida a cobertura.
- `third_friday_preceding` produz candidato por regra publicada (3a sexta
  civil, recuo ao dia util anterior); nao afirma serie listada.

## BSM europeu — convencoes e regimes (DL-PR03)

- **Unidades das gregas no nome do campo:** `vega_per_pct_point` e
  `rho_per_pct_point` sao sensibilidades por ponto percentual
  (derivada bruta x 0.01); `theta_per_day` e o theta anual
  (`dP/dt` no calendario, negativo para compradas tipicas) dividido por
  `theta_basis` (252|365, vindo de `year_basis` do DL-PR02).
- **Regime `expiry` (`T == 0`):** preco = intrinseco puro; delta em
  {0, +-1}, com +-0.5 em `S == K` declarado como convencao (limite lateral
  inexistente); gamma/vega/theta/rho = 0; `d1 = d2 = None`; nota
  `expiry_day_intrinsic`. Nunca se divide por `sqrt(T) = 0`.
- **Regime `zero_vol` (`sigma == 0`, `T > 0`):** preco = intrinseco
  descontado do forward (`max(S e^{-qT} - K e^{-rT}, 0)` e simetrico);
  gregas pela derivada do intrinseco descontado, com
  `N(d1) = N(d2) = n in {1, 0.5, 0}` saturado pelo sinal do forward —
  `n = 0.5` no ATM-forward e o limite de `N(d1)` com `sigma -> 0+`;
  vega = 0; nota `zero_volatility_limit`.
- **Recusa de americanas e estilo desconhecido:** `price_contract` responde
  `supported=False` com `reason` (`american_not_supported_phase1` |
  `unknown_exercise_style`) e todos os campos numericos `None`; americana
  nunca recebe BSM "por aproximacao" (decisao 4). O resultado europeu
  carrega `assumptions` com as chaves de `model_assumptions` (DL-PR02) mais
  `pricing_model = bsm_european_v1`.
- **Validacao independente:** Hull (call ~4.76, put ~0.81), paridade
  call-put, diferencas finitas centrais e o oraculo mpmath do Codex
  (`tests/fixtures/derivatives/reference/`, 92 casos a 50 dps, paridade
  interna < 1e-30 declarada no proprio arquivo).

## Barreira deterministica anti-fixture

- `Provenance` e `Purpose` atribuidos pelo adaptador de transporte; payload
  externo nunca define procedencia.
- Heranca worst-of (`inherit_purpose`): qualquer entrada `test` contamina o
  derivado como `test`; promocao e proibida (`ProvenanceStamp` rejeita).
- Falha de transporte real jamais faz fallback para fixture.
- Testes de contaminacao (DL-PR06) provam que `purpose=test` sobrevive a
  cache, serializacao e `model_copy`.

## Seguranca do token

O mesmo token OpLab le mercado e opera ordens. Consequencias vinculantes:

- Allowlist de rotas enumeradas em codigo desde a Fase 1.
- Header `Access-Token`; o parametro de query de token e proibido (vaza em
  logs e URLs).
- Token lido uma unica vez, dentro do transporte HTTP (DL-PR04); nenhum outro
  modulo referencia a variavel de ambiente.
- Nenhuma rota do dominio de ordens em codigo, config ou teste do Lab.

## Pendencias de homologacao (estado B)

- Campos, unidades e horarios reais de cada endpoint vs exemplos documentais.
- Base de capitalizacao de `interest_rates.value` (hipotese: 252 exponencial).
- Confirmacao de ajuste de strike por proventos, por contrato.
- Cobertura e semantica de `/market/options/strategies/covered` e das gregas
  da OpLab (uso futuro, so reconciliacao).
- Calendario de feriados B3 2026 (arquivo YAML a fornecer).
- Reproduzir um preco com a propria IV invertida **nao** conta como validacao.

## Escopo negativo

Este ADR nao autoriza chamadas reais, token real, rotas de ordens, modelos
americanos, Redis, Telegram, NumPy/SciPy, persistencia PostgreSQL de
snapshots, nem alteracao de `CLAUDE.md`/`AGENTS.md`/`.claude/`. Reversao da
proibicao de corretora e assunto exclusivo do ADR-0024 (proposto, nao
assinado).

## Referencias

- Hull, *Options, Futures, and Other Derivatives* — referencia numerica BSM
  (S=42, K=40, r=0.10, sigma=0.20, T=0.5: call ~4.76, put ~0.81).
- Documentacao OpLab REST API v3: <https://apidocs.oplab.com.br/> (lida em
  2026-11-05).
- `tests/fixtures/derivatives/documental/manifest.json` — hashes SHA-256 das
  fixtures documentais.
