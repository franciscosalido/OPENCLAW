# Lab de Derivativos DL-PR03 - BSM europeu e gregas com unidades declaradas

Branch: `feat/dl-pr03-bsm-greeks`
GitHub Issue: pendente (card READ-DO de 2026-11-06 autoriza o PR diretamente)
Status: Initial SDD

## Objective

DL-PR03 entrega o coprocessador BSM deterministico e auditavel do Lab:
preco e gregas (delta, gamma, vega, theta, rho) de opcoes **europeias**, com
a unidade no nome do campo, dominio validado (`PricingDomainError`), regimes
limite (`expiry`, `zero_vol`) tratados a parte sem divisao por zero, e recusa
explicita de americanas/estilo desconhecido na ponte `price_contract`
(ADR-0023, decisao 4: americana nunca recebe BSM "por aproximacao").

This PR does not implement IV (DL-PR04), CRR/Bjerksund-Stensland (Fase 2),
dividendos discretos, HTTP, MCP, persistencia, uso de `/market/options/bs`
da OpLab (so reconciliacao futura) nem qualquer "correcao" de preco de
mercado.

## Files

- `backend/derivatives/pricing/bsm.py` — `PricingModel` (`bsm_european_v1`),
  `PricingDomainError(ValueError)`, `BsmInputs` (frozen, `__post_init__`
  valida dominio e finitude), `Greeks` (`delta`, `gamma`,
  `vega_per_pct_point`, `theta_per_day`, `rho_per_pct_point`,
  `theta_basis`), `BsmResult` (`model`, `price`, `greeks`, `d1`, `d2`,
  `regime`, `notes`), `norm_cdf`/`norm_pdf` via `math.erf`, `price(...)`
  com regimes `regular`/`expiry`/`zero_vol`, `unsupported(...)`.
- `backend/derivatives/pricing/contract_pricing.py` — `PricingOutcome`
  (pydantic `extra="forbid"`, frozen) e `price_contract(...)`: europeia vai
  ao BSM com `Decimal(str(price))`; qualquer outro estilo volta
  `supported=False` com motivo e todos os campos numericos `None`.
- `tests/unit/derivatives/{test_bsm,test_contract_pricing}.py` + extensao de
  `tests/architecture/test_derivatives_boundaries.py` (bsm.py sem
  `pydantic`/`decimal`; `random` proibido no pacote).
- `tests/fixtures/derivatives/reference/` — oraculo mpmath do Codex
  (92 casos, 50 dps, serializado a 20 digitos), versionado neste PR com
  README, gerador congelado (`gerador_reference.py.txt`), SHA-256 e
  `validation_report.json`.

## Convencoes de sinal e unidade (ADR-0023, secao BSM)

- `theta_per_day` = (dP/dt no calendario, anual) / `theta_basis` (252|365);
  negativo para compradas tipicas.
- `vega_per_pct_point` = `S e^{-qT} phi(d1) sqrt(T) * 0.01`;
  `rho_per_pct_point` = `+-K T e^{-rT} N(+-d2) * 0.01`.
- `q` continuo, default 0.0 com `strike_adjusted_by_exchange_assumed=true`.

## Decisions inside scope

- **Nucleo unico `_analytic`:** os regimes `regular` e `zero_vol` usam o
  mesmo corpo de formulas; no limite `sigma == 0` entram `N(d1)=N(d2)=n`
  saturados (`n = 1/0.5/0` conforme o sinal de
  `S e^{-qT} - K e^{-rT}`) e `phi(d1)=0`. O valor `n = 0.5` no
  ATM-forward e o limite matematico de `N(d1)` quando `sigma -> 0+`, nao
  uma convencao arbitraria; a paridade e as gregas-limite saem consistentes
  por construcao.
- **`expiry` antes de `zero_vol`:** `T == 0` decide primeiro; delta 0.5 em
  `S == K` no vencimento e convencao declarada (nota
  `expiry_day_intrinsic`).
- **Oraculo presente e versionado:** o card previa skip se ausente; os
  arquivos chegaram como untracked no inicio da sessao (21:02, apos o
  pre-voo), com SHA-256 conferido
  (`aa15a6dedd03da14adbc809fdcbd4f2195d462449ad0cc77bb79dcce4892d74d`).
  Decisao: versionar `tests/fixtures/derivatives/reference/` neste PR para a
  suite ser auto-contida em CI. O teste mantem o ramo de skip
  ("oráculo mpmath ainda não entregue") para arvores sem a fixture.
- **Theta do oraculo e da call:** `metadata.theta_option_type = "call"`; a
  comparacao de `theta_per_day_{252,365}` no teste do oraculo cobre so a
  call. O theta da put e validado por diferencas finitas e pela identidade
  de paridade nos demais testes.
- **Casos `limit` do oraculo caem no regime `regular`:** o gerador usa
  `sigma = 1e-6` e `T = 1e-9` estritamente positivos (politica declarada no
  metadata: sem substituicao por zero); o teste verifica regime `regular` e
  ausencia de excecao, como pede o card.
- **Paridade declarada no arquivo:** o teste exige
  `|parity_residual| < 1e-20` por caso (campo interno a 50 dps; o maximo
  observado e 2.7e-49). `parity_residual_serialized` (recomputado dos
  valores ja arredondados a 20 digitos, max 9.9e-19) nao esta sujeito a
  esse criterio.
- **Sem campo novo em `Conventions`:** `year_basis` (DL-PR02) vira
  `theta_basis`; nenhuma proposta de config adicional.

## Acceptance evidence

- Hull (S=42, K=40, r=0.10, sigma=0.20, T=0.5): call 4.759422, put
  0.808599, d1 0.769263, d2 0.627841 — dentro de |erro| <= 0.005 / 1e-3.
- Paridade: grade 162 casos, residuo maximo ~2e-14 (<= 1e-9).
- Diferencas finitas centrais (h relativo 1e-5) vs analiticas: pior erro
  relativo ~5.2e-6 (gamma; demais <= 3e-8), tolerancia 1e-5.
- Oraculo mpmath: 92 casos; pior erro absoluto vs float64 ~2.8e-14 em
  preco/d1/d2 e <= 7e-16 nas gregas (tolerancias 1e-9/1e-8).
- `pytest tests/ --ignore=tests/integration` rc 0; coleta de
  `tests/unit/derivatives` >= 200.
- `mypy backend/ --strict` 0; `pyright backend/` 0.
- Producao 245 linhas (<= 250), zero linhas > 100 colunas.
