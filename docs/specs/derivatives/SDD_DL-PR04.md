# Lab de Derivativos DL-PR04 - IV por bissecao protegida (bid/ask/mid)

Branch: `feat/dl-pr04-implied-vol`
GitHub Issue: pendente (card READ-DO de 2026-11-06 autoriza o PR diretamente)
Status: Initial SDD

## Objective

DL-PR04 inverte preco -> volatilidade implicita com **bissecao protegida**:
dominio validado (`DOMAIN_ERROR`, nenhuma excecao escapa), limites de
nao-arbitragem (`BELOW_INTRINSIC`/`ABOVE_UPPER_BOUND`), bracket
`[bracket_lo, bracket_hi]` com expansao dobrada e contada ate
`bracket_hi_max`, maximo de iteracoes e **tolerancia dupla** (preco E vol).
A inversao roda separadamente para **bid, ask e mid** sem jamais alterar a
cotacao, e `price_contract_from_quote` liga IV -> sigma -> BSM com recusa
sempre explicada. `sigma == 0.0` jamais significa ausencia; ausencia e
`sigma=None` com diagnostico completo.

Nao-objetivos: Newton/Brent/Jäckel (backlog, apos este oraculo), americanas,
superficie/interpolacao, HTTP/OpLab, `ChainService` (PR06), MCP (PR07),
`/market/options/bs`.

## Files

- `backend/derivatives/pricing/implied_vol.py` (puro; imports internos so
  `bsm` e `domain.models`; `Iv` entra via `TYPE_CHECKING`): `IvStatus`
  (StrEnum, 7 estados), `IvDiagnostic`/`IvResult` (frozen+slots; invariante
  `sigma is None <=> status fora de {OK, LOW_VEGA}` validado em
  `__post_init__`), `price_bounds`, `implied_vol`.
- `backend/derivatives/pricing/quote_iv.py` (ponte pydantic):
  `IvDiagnosticModel`/`IvResultModel`/`QuoteIv` (`extra="forbid"`, frozen;
  enum serializa como `str`), `iv_for_quote` (lado ausente -> campo `None`,
  nunca `NOT_APPLICABLE`; `Decimal -> float` so na entrada do modelo).
- `backend/derivatives/pricing/contract_pricing.py`: `PricingOutcome` ganha
  `iv: QuoteIv | None = None` e `sigma_source` opcionais (compatibilidade
  PR03 preservada); `_inputs_echo` extraido; `price_contract_from_quote`.
- `tests/unit/derivatives/{test_implied_vol,test_quote_iv}.py` + extensao de
  `tests/architecture/test_derivatives_boundaries.py` (pureza do
  `implied_vol.py`; grep anti-`sigma=0.0`).

## Decisions inside scope

- **`price_contract_from_quote` vive em `contract_pricing.py`**, nao em
  `quote_iv.py` como o card agrupava: `PricingOutcome.iv: QuoteIv` obriga
  `contract_pricing` a importar `quote_iv`; colocar a funcao em `quote_iv`
  criaria import circular. `quote_iv.py` continua importando apenas
  `implied_vol` + dominio + convencoes.
- **Politica de `LOW_VEGA`:** convergencia com `vega bruta < 
  low_vega_threshold` devolve `sigma` **preenchido** e mal condicionado
  (a solucao existe; o preco e plano em sigma). `LOW_VEGA` e utilizavel por
  `price_contract_from_quote` — o diagnostico viaja no resultado.
- **Alvo exatamente no intrinseco (ITM):** quando o preco no `bracket_lo` ja
  iguala o alvo no float (plato por underflow da opcionalidade), a bissecao
  converge no topo do plato e sinaliza `LOW_VEGA`; quando
  `preco(bracket_lo) > alvo` (raiz abaixo de `bracket_lo`), devolve
  `NO_CONVERGENCE` com mensagem "raiz abaixo de bracket_lo". Nunca
  `sigma=0`.
- **Alvo negativo e `DOMAIN_ERROR`** (preco negativo nao e preco);
  `BELOW_INTRINSIC` fica para alvos nao negativos abaixo do intrinseco
  descontado menos `tol`.
- **Fonte ausente na cotacao** em `price_contract_from_quote` recusa com
  `iv_unavailable:missing_quote` (a fonte nao tem `IvResult`; reutilizar
  `NOT_APPLICABLE` contradiria o contrato "lado ausente -> None").
- **Echo sem sigma resolvido:** nas recusas de `price_contract_from_quote`,
  `inputs_echo["sigma"] = "unresolved"` (tipo do campo ja era
  `float | str`); `price_contract` segue ecoando o sigma dado.
- **`price_source_note` em ASCII** ("mid e indicativo; nao pressupoe
  execucao"): o card grafou com acentos; o codigo do repo e ASCII.

## Erratas ao card

- **`awk 'length>100' backend/derivatives/pricing/*.py` nao e 0 na base:**
  `calendar.py` (15 linhas) e `conventions.py` (1 linha) ja excediam 100
  colunas desde o DL-PR02. Regra da sessao (BACKLOG): mudanca fora do PR e
  nomeada, nunca implementada "ja que estou aqui" — item adicionado ao
  BACKLOG; os arquivos do PR04 (`bsm`, `implied_vol`, `quote_iv`,
  `contract_pricing`) tem 0 linhas > 100 colunas.
- **Caso `limit_T_1e-9_K100` (ATM) recupera sigma:** o card previa
  `LOW_VEGA`/`NO_CONVERGENCE` para todos os `limit`; o caso ATM de limite de
  tempo e bem condicionado (vega bruta ~1.3e-3) e devolve `OK` com
  sigma=0.20 +- 1e-7. Desfechos dos seis `limit` pinados no teste.
- **Round-trip/oraculo em pontos degenerados:** deep ITM/OTM com vol baixa
  e/ou prazo curto tem preco float plano em sigma (opcionalidade abaixo de
  1 ulp); nesses pontos o contrato e `LOW_VEGA`/`NO_CONVERGENCE`, nunca
  igualdade de sigma. Criterio deterministico: vega bruta no sigma
  verdadeiro `< low_vega_threshold` (no oraculo, vega do proprio arquivo)
  ou `sigma_verdadeiro < bracket_lo`.

## Adendo: passo do gamma por diferencas finitas (test_bsm.py)

`test_gamma_matches_second_difference` falhava em Linux por tolerancia. A
segunda diferenca central tem erro total
`O(h^2) [truncatura] + O(eps*P/h^2) [arredondamento]`, com `P ~ 10` e
`eps ~ 2e-16`:

- Com `h = 1e-5*S` (= 1e-3), o termo de arredondamento domina:
  `~4*eps*P/h^2 ~ 1e-8` absoluto -> ate ~5e-6 relativo no gamma. Pior margem
  observada no macOS: 5.2e-6 contra tolerancia 1e-5 — ruido dependente da
  libm, que em glibc ultrapassa o limite.
- Com `h = 1e-4*S` (= 1e-2), o arredondamento cai ~100x (`~1e-10` absoluto,
  ~1e-8 relativo) e o residuo passa a ser truncatura `O(h^2)`,
  deterministica e estavel entre libms (depende de valores suaves da
  funcao, nao de cancelamento). Pior erro observado: 1.0e-6 relativo
  (dominado pelo ponto de menor `sigma*sqrt(T)` = 0.075), margem ~10x sob
  a tolerancia 1e-5, que fica inalterada.

Correcao no teste (`H_REL_GAMMA = 1e-4`, so no gamma; as primeiras
diferencas de delta/vega/rho/theta mantem `H_REL = 1e-5`); `bsm.py`
intocado.

## Adendo 2: caudas BSM sem cancelamento (2026-11-18)

Falha informada em Linux aarch64: o round-trip PUT com `S=100`, `K=70`,
`T=2`, `r=0.10`, `sigma=0.05` recebia `DOMAIN_ERROR` porque o BSM
produzia aproximadamente `-5.97e-15`. A CDF `0.5*(1+erf)` e os
complementos `1-N(d)` perdiam a cauda por cancelamento.

- `norm_cdf(x)` passa a `0.5 * math.erfc(-x / math.sqrt(2.0))`.
- O nucleo analitico recebe `N(d1)`/`N(d2)` para call e
  `N(-d1)`/`N(-d2)` calculados diretamente para put. Preco, delta, carry
  e rho da put usam essas caudas, sem complementos `1-N(d)`.
- No regime `sigma=0`, o sinal call/put orienta o gap descontado antes
  da saturacao; o limite ATM-forward continua `n=0.5`. `d1`/`d2`
  reportados no regime regular mantem seus sinais originais.
- So depois dessas correcoes, `value = max(value, 0.0)` protege contra
  residuos subnormais restantes da ordem de `1e-322`, como comentado no
  codigo. Na grade executada neste Mac nao houve valor bruto negativo.
- Novo `tests/unit/derivatives/test_bsm_tails.py`: 4.704 pontos com
  `S=100`, `q=0`, sigma em `{0.02,0.05,0.1,0.2,0.4,0.8,2.0}`, `K/S`
  de `0.3` a `3.0` em passos de `0.1`, `T` em
  `{1/252,10/252,0.25,0.5,1,2}` e `r` em `{0,0.05,0.10,0.15}`.
  Ambos os precos devem ser `>=0`; paridade tem residuo absoluto
  `<=1e-12`. Mais tres testes pinam o put informado com preco `>0` e
  o limite ATM-forward com sigma zero para call/put.
- Nenhum teste existente ou tolerancia foi alterado. Os seis pares de
  desfechos de IV em `EXPECTED_LIMIT_OUTCOMES` permanecem iguais;
  o round-trip informado agora recebe preco positivo e passa pelo
  contrato existente de mau condicionamento.

Validacao local em macOS aarch64, Python 3.12.13, com dependencias ja
existentes; Linux aarch64 nao foi executado nesta sessao:

- Put pinado: `1.1451220802773962e-15`; maior residuo absoluto da
  paridade na grade: `5.6843418860808015e-14`.
- `pytest tests/unit/derivatives tests/architecture/test_derivatives_boundaries.py`:
  rc 0, **5.609 passed**, incluindo Hull, oraculo de 92 casos e IV.
- `mypy backend/ --strict`: rc 0, 144 arquivos sem erros;
  `pyright backend/`: rc 0, 0 errors / 0 warnings / 0 informations.
- `pytest tests/ --ignore=tests/integration`: **rc 1**, 7.763 passed,
  15 skipped, 261 subtests passed, 1 failed. Unica falha final:
  `test_qwen3_summary_does_not_leak_query_payload_vectors`, por ausencia
  de `evaluation/results/qdrant_118_qwen3_benchmark_summary.json`,
  artefato ignorado pelo Git e ausente no `git archive`. Gate global
  **pendente**, sem alterar o teste nem fabricar/copiar o artefato.
- Todas as execucoes ocorreram em copia temporaria de `git archive HEAD`
  com os quatro arquivos autorizados sobrepostos, sem suite ampla no
  checkout. A copia recebeu metadados Git locais vazios, sem commits,
  para os testes de `git check-ignore`; ambiente de processo limpo,
  sem carregar `.env` ou habilitar testes de servicos por flags herdadas.
- Producao medida incluindo o worktree com
  `git diff --numstat $(git merge-base origin/main HEAD) -- backend/`:
  **399 adicoes e 24 remocoes**, contra merge-base `c9c6e68`.
  Antes: **386 adicoes e 14 remocoes**; adendo em `bsm.py`:
  **13 adicoes e 10 remocoes**. O gate considera adicoes, nao saldo;
  `399 <= 400`. Nenhuma linha de `bsm.py` excede 100 colunas.

Fora de escopo: `calendar_365`, overflow e demais achados; sem mudanca de
solver IV, dependencia, servico, segredo, commit, push ou merge. Proximo
passo: revisao humana/Claude e gate global em Dots com o artefato legado
apropriado, mantendo os mesmos testes e tolerancias.

### Validacao independente em Linux aarch64 (2026-11-18, Claude)

Clone isolado fora do checkout; glibc 2.35, Python 3.12.16, dependencias
do `uv.lock` (`uv sync --frozen`). Arvores testadas: este PR com o
Adendo 2 e a combinacao `main` + PR #130 + este PR.

- Caso original: `test_round_trip...[0.05-0.7-2.0-PUT]` passa; em `main`
  (`c9c6e68`) o Linux tambem reprova dois testes de gamma, corrigidos
  pelo adendo anterior deste PR.
- `pytest tests/unit/derivatives tests/architecture`: rc 0, 5.627 passed.
- `mypy backend/ --strict`: 0 erros (144 arquivos); `pyright backend/`:
  0 erros.
- `pytest tests/ --ignore=tests/integration` em clone limpo: 7.762
  passed, 15 skipped, 2 failed. As duas falhas existem em `main` e nao
  sao deste PR: (a) `test_qwen3_summary_does_not_leak_query_payload_vectors`
  le um JSON ignorado pelo Git; (b)
  `test_pr10_sdd_and_adr_contracts_exist` abre `docs/adr/` em minusculas
  e so resolve em sistema de arquivos insensivel a caixa. Com o JSON
  legado presente e `docs/adr` resolvivel, como no checkout do Mac:
  7.764 passed, 15 skipped, 0 failed.
- Referencia mpmath (50 digitos), 40.000 precos aleatorios (call/put,
  `S` de 1 a 1.6e5, `K/S` de 0.30 a 3.3, `T` de 0.0025 a 3.2, `sigma`
  de 1.3% a 316%, `q` ate 8%): em `main`, 103 precos negativos e erro
  relativo de ate 1.2e3 nas caudas; com o Adendo 2, 0 negativos, erro
  relativo nas caudas <= 3.2e-9, `|erro|/S` <= 8.8e-16 e residuo de
  paridade `/S` <= 8.9e-16.
- Round-trip de IV em 12.000 lados aleatorios: 0 excecoes, 0 violacoes
  do invariante sigma/status, nenhum `DOMAIN_ERROR` a partir de preco do
  proprio modelo; pior `|sigma_rec - sigma|` nos `OK`: 3.9e-8.
- Determinismo: digest SHA-256 de precos, gregas e IVs identico em 6
  processos (`PYTHONHASHSEED` 0, 7 e aleatorio); suite completa em 4
  execucoes (`PYTHONHASHSEED` 0/1/4242/99; ordem natural, invertida e
  duas embaralhadas) com 7.779 testes e 0 desfechos divergentes; arvore
  limpa apos a suite na combinacao com o PR #130.

## Acceptance evidence (antes do Adendo 2)

- Round-trip (5 sigmas x 5 moneyness x 3 prazos x call/put = 150 lados):
  128 lados `OK` com pior erro 7.3e-9 (tolerancia 1e-6); 22 lados (11
  pontos, listados em `EXPECTED_LOW_VEGA_RT`) degenerados por vega baixa.
- Oraculo mpmath (92 casos x call/put = 184 lados): 132 lados recuperados
  com `OK`, pior erro 7.3e-9 (tolerancia 1e-7); 52 lados degenerados
  (44 `LOW_VEGA`, 8 `NO_CONVERGENCE`), zero excecoes.
- Iteracoes nos lados `OK` (round-trip e oraculo): min 29, mediana 29,
  max 32 (max_iterations=200).
- Expansao: alvo de sigma=7 converge com `expansions=1`; alvo no teto
  `S e^{-qT}` esgota `bracket_hi_max` com `expansions=2` e
  `NO_CONVERGENCE`; `max_iterations=5` reporta `iterations=5` e
  `sigma=None`.
- Determinismo: chamadas repetidas comparam `==` em todos os campos.
- `pytest tests/ --ignore=tests/integration` rc 0 (3057 passed); coleta de
  `tests/unit/derivatives` = 891 (>= 650).
- `mypy backend/ --strict` 0; `pyright backend/` 0.
- Producao: 386 adicoes e 14 remocoes (adicoes <= 400);
  0 linhas > 100 col nos arquivos do PR.
