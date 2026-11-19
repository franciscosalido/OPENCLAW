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
  oplab/    routes, vendor_models, transport, budget, errors, client  (DL-PR01/05)
  domain/   models, normalize, quality                                (DL-PR01)
  pricing/  conventions, bsm, implied_vol                             (DL-PR02–04)
  service/  chain_service                                             (DL-PR06)
  mcp/      derivatives_server                                        (DL-PR07)
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
- **Emenda 2026-11-18 — caudas numericas (DL-PR04, Adendo 2):** a CDF
  passa de `0.5*(1+erf)` para `0.5*erfc(-x/sqrt(2))`, ainda sem
  dependencias novas. Preco, delta, carry e rho da put usam `N(-d1)` e
  `N(-d2)` diretamente, nunca `1-N(d)`, evitando cancelamento observado
  em Linux aarch64 (`S=100`, `K=70`, `T=2`, `r=0.10`, `sigma=0.05`).
  O sinal call/put orienta tambem a saturacao em `zero_vol`, preservando
  o limite ATM-forward `n=0.5`. Depois das CDFs diretas, o preco recebe
  piso zero para eventual residuo subnormal (~`1e-322`). O SDD_DL-PR04
  registra grade de nao negatividade/paridade, resultados e limites
  da validacao; testes existentes e tolerancias permanecem intactos.

## IV por bissecao protegida (DL-PR04)

- **Algoritmo:** bissecao pura (sem Newton/Brent nesta fase) sobre
  `bsm.price` — unica implementacao BSM do pacote. Protecoes, nesta ordem:
  dominio (`DOMAIN_ERROR`, nenhuma excecao escapa; alvo negativo e erro de
  dominio), `T == 0` -> `NOT_APPLICABLE`, limites de nao-arbitragem
  (`BELOW_INTRINSIC` / `ABOVE_UPPER_BOUND`, com folga
  `tol = tol_price_rel x max(1, alvo)`), mudanca de sinal estrita no
  bracket `[bracket_lo, bracket_hi]` com expansao dobrada e contada ate
  `bracket_hi_max`, e maximo de iteracoes.
- **Tolerancia dupla:** para somente quando
  `|preco(sigma) - alvo| <= tol_price` **e** `hi - lo <= tol_vol`.
  Estourar `max_iterations` devolve `NO_CONVERGENCE` com `sigma=None` —
  nunca o meio do bracket e nunca `sigma=0` como marcador.
- **Politica de `LOW_VEGA`:** convergiu, mas a vega bruta na solucao fica
  abaixo de `low_vega_threshold`; `sigma` vem **preenchido** e declarado mal
  condicionado (preco plano em sigma no float). Alvo exatamente no
  intrinseco ITM: plato por underflow -> `LOW_VEGA` no topo do plato, ou
  `NO_CONVERGENCE` quando a raiz fica abaixo de `bracket_lo`.
- **bid/ask/mid separados e cotacao intocada:** `iv_for_quote` inverte cada
  lado existente; lado ausente e campo `None` (nunca status disfarcado);
  **`mid` e indicativo e nao pressupoe execucao** (`price_source_note`).
  Mercado cruzado continua calculado; a flag e de `QualityFlags` (DL-PR01).
- **Recusa explicada na ponte:** `price_contract_from_quote` recusa
  americana/estilo desconhecido **antes** de qualquer IV; fonte pedida sem
  IV utilizavel vira `supported=False`,
  `reason=iv_unavailable:<status|missing_quote>`, numericos `None` e os
  diagnosticos completos em `iv`.
- **Hipoteses registradas:** `theta_basis` e irrelevante para a inversao
  (passa 252); vega bruta = `vega_per_pct_point x 100`; a recuperabilidade
  em float64 e limitada pela planicie do preco (deep ITM/OTM curtos de vol
  baixa nao sao inversiveis — contrato degrada para `LOW_VEGA`/
  `NO_CONVERGENCE`, nunca excecao); o caso-limite ATM `T=1e-9` do oraculo e
  bem condicionado e recupera sigma (errata ao card registrada no SDD).

## Cliente OpLab — allowlist, orcamento e erros (DL-PR05)

- **Dupla lista de rotas:** uma rota so e aceita se pertencer ao enum
  `MarketRoute` (codigo) **e** a `oplab.allowed_routes` (YAML). O YAML pode
  restringir, nunca ampliar. A checagem e positiva (`fullmatch` do caminho
  inteiro), sobre esquema `https`, host exato `api.oplab.com.br`, prefixo
  `/v3` e metodo `GET`; query string e fragmento sao proibidos.
- **Dominio de ordens:** qualquer segmento `domain` no caminho e recusado
  explicitamente, alem de ja nao casar com nenhuma rota enumerada.
- **`symbol` restrito a `[A-Z0-9]{4,12}`:** sem barra, ponto, interrogacao
  ou minusculas; e o unico parametro de rota existente.
- **Taxonomia de erros:** 401 `AuthError`, 402 `SubscriptionError`, 403
  `PermissionError_`, 404 `NotFoundError`, 429 `RateLimitedError`, 503 e
  demais 5xx `UnavailableError`; recusas locais `ForbiddenRouteError`,
  `ForbiddenHostError`, `BudgetExceededError`, `NetworkForbiddenError`;
  falha de transporte `TransportError`. A mensagem nunca carrega corpo,
  headers, URL recusada nem token.
- **`Retry-After` sem retry:** 429/503 carregam `next_eligible_at` (header
  em segundos ou HTTP-date); sem header legivel valem os bloqueios
  publicados — **429: 5 min; 503: 1 s** (hipotese ate homologacao). O
  cliente nunca dorme e nunca repete a chamada: quem decide esperar e o
  chamador.
- **Orcamento por credencial:** janelas deslizantes de 50/s e 100/min em
  memoria, chaveadas pelo SHA-256 dos 8 primeiros caracteres do token (o
  token nunca e guardado); recusa local acontece antes de qualquer rede.
- **Divisao do PR:** a implementacao mediu 444 linhas de producao; o card
  mandava dividir acima de 400. Parte A (erros, rotas, orcamento — pura) e
  Parte B (transporte e cliente — unico ponto de `httpx` e do token).

- **Transporte HTTP (Parte B):** unico modulo que importa `httpx` e le
  `OPLAB_TOKEN`; sem redirecionamento (3xx e `ForbiddenHostError`), sem
  retry (`max_retries != 0` e recusado na construcao) e com a causa `httpx`
  suprimida (`from None`), porque a requisicao carrega o header do token.
  `received_at` e o relogio injetado. Em A toda resposta vem de simulador e
  nasce `REPLAY`; `OBSERVED` so nascera na aquisicao homologada do estado B
  (adendo de 2026-11-19).
- **Transporte de fixtures:** mesmo contrato, procedencia `DOCUMENTAL`,
  `SYNTHETIC` ou `REPLAY` — nunca `OBSERVED` (recusado na construcao).
- **Cliente:** devolve modelos do fornecedor + `ProvenanceStamp`; o JSON
  bruto nao sai do pacote; payload malformado vira `VendorPayloadError` sem
  os valores do payload.

## ChainService — uma captura, recusa explicada (DL-PR06)

- **Uma captura = quatro leituras** (chain, ativo, taxas, status), em ordem
  fixa; todos os calculos reutilizam a mesma captura. Falha de leitura
  propaga erro tipado: nao ha chain parcial nem fallback para fixture.
- **Carimbo worst-of:** o proposito da captura herda das quatro leituras.
  `PricedChain.purpose` e recalculado (campo, carimbo, procedencia) e por
  isso resiste a `model_copy`, que nao valida.
- **Recusa da chain inteira** com motivo nomeado quando falta spot, taxa,
  cobertura de calendario, prazo valido ou quando `day_count` nao e
  `business_252` (`calendar_365` esta nomeado no contrato, sem contagem
  implementada).
- **Sigma do mid:** preco BSM com a IV do mid serve para as gregas; nao e
  validacao. A validacao independente usa a fixture sintetica, cujo sigma
  verdadeiro precisa cair em `[IV_bid, IV_ask]`.
- **Data de avaliacao** e `now` no fuso `America/Sao_Paulo`.
- **Renumeracao:** onde este ADR cita "DL-PR05 service" e "DL-PR06 mcp" na
  arvore alvo, e "testes de contaminacao (DL-PR06)", leia-se DL-PR06
  (servico) e DL-PR07 (MCP), conforme a renumeracao de 2026-11-06.

## Servidor MCP `quimera-derivatives` (DL-PR07)

- **Superficie:** `derivatives_health`, `derivatives_chain` (produtiva) e
  `derivatives_chain_demo` (so com `QUIMERA_DERIV_CONTEXT=test` no ambiente
  do processo). Bind fixo em `127.0.0.1`, porta 8814.
- **Ativacao da tool produtiva exige tres condicoes simultaneas:**
  `provider_mode = live_homologated`, `readiness = C` e servico ao vivo
  injetado. Na Fase 1 nenhuma e alcancavel; a resposta e sempre
  `LIVE_NOT_ACTIVATED`, sem campos de cotacao, e o servico nem e chamado.
- **Barreira unica (`production_view`):** a tool produtiva so serializa
  chain com proposito efetivo `production`; uma leitura de teste na captura
  bloqueia (worst-of). Falha ao vivo e erro, nunca fallback para fixture.
- **Parametros:** exatamente `symbol` e `due_date`; provedor, contexto e
  diretorio de fixture vem do ambiente do processo, nunca da chamada.
- **Demonstracao:** avalia no instante registrado no manifesto da fixture;
  a resposta e reprodutivel e sempre rotulada `DEMO_TEST_DATA`/`test`.
- **Relogio real:** entra apenas por `system_clock`, na raiz de composicao.

## CLI `quimera chain` (DL-PR08)

- Segunda superficie, de terminal, sobre as mesmas funcoes das tools MCP;
  sem logica propria, sem opcao de caminho, URL, token ou diretorio.
- Padrao `--provider live` -> `LIVE_NOT_ACTIVATED` com exit 3; a demo exige
  `--provider offline_fixture` e sai sempre rotulada como teste (exit 0).
- Unica mudanca em arquivo protegido da Fase 1: a entrada
  `[project.scripts]` do `pyproject.toml`, sem dependencia nova.

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

## Adendo de implementação da candidata local em 2026-11-19

Em A, a indisponibilidade produtiva é incondicional. A guarda também se
aplica a configurações e serviços construídos em código. A projeção produtiva
sempre recusa. O cálculo de propósito não autentica um objeto reconstruído.
Isso substitui a descrição anterior de ativação por três condições na
implementação da Fase 1. B e C exigem homologação e implementação próprias.

A demo usa o manifesto sintético fixado da BOVA11. O cliente HTTP só opera
por injeção explícita de mock e ambiente de teste. O registro de validação
da candidata está no [SDD de conciliação](../specs/derivatives/SDD_conciliacao_fase01.md).

### Correcoes apos a revisao independente (2026-11-19)

- **Procedencia do transporte simulado.** `HttpTransport` em A carimba
  `REPLAY`, nunca `OBSERVED`. `REPLAY` significa resposta reproduzida por
  simulador em memoria, de conteudo nao atestado: proposito `test`, e nao
  atravessa a demo (que exige `SYNTHETIC` do adaptador de manifesto) nem a
  projecao produtiva. Nenhum modulo de `backend/derivatives/` atribui
  `OBSERVED` em A; um teste de AST e a trava, a ser alterada de proposito
  quando a aquisicao real do estado B for implementada.
- **Dominio da taxa.** Na capitalizacao `annual_exp_252`, `i <= -100% a.a.`
  esta fora do dominio de `ln(1 + i)`. A conversao levanta `RateDomainError`
  e a chain inteira e recusada com `invalid_rate`, linhas preservadas.
  Taxas negativas acima de -100% e a capitalizacao `continuous` seguem
  validas. Limite de plausibilidade e decisao de homologacao.

Registro: [SDD das correcoes](../specs/derivatives/SDD_correcoes_fase01.md).
