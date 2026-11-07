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

## Acceptance evidence

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
- Producao 386 linhas (<= 400); 0 linhas > 100 col nos arquivos do PR.
