# DL2B-PR01 — Ponte americana pura, com volatilidade dada

Estado: **SPEC_PRONTA** (Claude, 2026-11-19). Autoridade: ADR-0026 e `SDD_FASE2B.md`,
critérios 1 a 5, 9 e 10. Os dois documentos acompanham este cartão.
Base: `main` em `ff0c1bec941eb4b78da0c717f1ece4dae2cf02e7`.
Branch: `feat/dl2b-pr01-american-bridge`.
Implementa: Codex. Revisa e integra: Claude. Estado de prontidão: A, sem mudança.

Como usar: o primeiro commit traz três cópias de `reports/fase02/dl2b-pr01/`, sem alteração
de um byte, e mais nada. Mandar o Codex começar é a aprovação do ADR-0026 por Francisco.

```sh
SRC=reports/fase02/dl2b-pr01
mkdir -p docs/specs/derivatives/fase2b
cp $SRC/ADR-0026.md docs/ADR/ADR-0026-laboratorio-derivativos-fase2b.md
cp $SRC/SDD_FASE2B.md docs/specs/derivatives/fase2b/SDD_FASE2B.md
cp $SRC/DL2B-PR01_CARD.md docs/specs/derivatives/fase2b/DL2B-PR01.md
```

SHA-256 dos dois documentos que acompanham o cartão:

```text
16e2235748e4d8116eb9dbe231532b07a3f42e530d85102ba5759870f04ee39d  ADR-0026.md
aa00a4a53e5f2a8b185b145733abbb8a3e8447fd98ffe897117e5c4578645800  SDD_FASE2B.md
```

## Objetivo

Uma função pura recebe um contrato americano, os termos da série, a premissa de carry, o
spot, a taxa, a volatilidade, o prazo e o número de passos. Devolve `PricingOutcome` com o
preço da árvore CRR, ou uma recusa que diz qual precondição faltou. Nada em produção chama
essa função ao fim deste PR.

## O que este PR vale, e o que não vale

Na B3 só a call pode ser americana, e call sem rendimento e com taxa positiva vale o mesmo
que a europeia. Para a maioria das séries, portanto, o número da ponte vai coincidir com o
BSM a menos do erro da árvore. O ganho deste PR é outro: a americana deixa de ser recusada
em bloco e passa a entrar por uma porta que exige lote, fator de cotação, política de
ajuste e premissa de carry, e que acerta o caso em que o rendimento chega perto da taxa.

## Escopo

| Arquivo | O que entra |
|---|---|
| `backend/derivatives/pricing/american_bridge.py` (novo) | a ponte |
| `tests/unit/derivatives/test_american_bridge.py` (novo) | testes T1 a T9 |
| `tests/architecture/test_binomial_isolation.py` | exceção para a ponte; T10 |
| `tests/architecture/test_series_terms_imports.py` | exceção para a ponte; T10 |
| `docs/ADR/ADR-0026-laboratorio-derivativos-fase2b.md` | cópia |
| `docs/specs/derivatives/fase2b/` | SDD, este cartão e as evidências |
| `docs/04_MEM/current_state.md` | bloco novo "Fase 02 — Marco 2B" |

Produção nova: um arquivo, com meta de até 130 linhas. Nenhum outro arquivo de `backend/`,
`config/` ou `scripts/` muda. Zero dependência nova.

## Não-objetivos

- Chamar a ponte de `contract_pricing.py`, do `ChainService`, do MCP ou do CLI.
- Tocar em `bsm.py`, `binomial.py`, `series_terms.py`, `carry.py` ou em `PricingOutcome`.
- Volatilidade implícita, gregas, número de passos padrão, configuração em YAML.
- Recuo para BSM, em qualquer caso. Extrapolação, suavização ou outra árvore.
- Conferir a vigência dos termos contra a data de avaliação. É do DL2B-PR03.
- Aceitar europeia na ponte. Europeia continua sendo BSM.

## Contrato

```python
AMERICAN_MODEL = "crr_american_v1"

def price_american_contract(
    contract: OptionContract,
    *,
    terms: SeriesTerms,
    carry: CarryAssumption | None,
    spot: Decimal,
    rate_cont: float,
    sigma: float,
    tte: TimeToExpiry,
    steps: int,
    assumptions: Mapping[str, str | float | bool],
) -> PricingOutcome
```

`PricingOutcome` e `TimeToExpiry` são os da Fase 01, importados sem mudança. O número de
passos é obrigatório e não tem valor padrão.

### Ordem das conferências

A primeira que falhar decide o motivo. Nenhuma recusa traz número.

| Ordem | Conferência | Motivo (`reason`) |
|---|---|---|
| 1 | estilo do contrato é `UNKNOWN` | `unknown_exercise_style` |
| 2 | estilo do contrato não é `AMERICAN` | `american_bridge:not_american` |
| 3 | `resolve_carry(terms, carry)` levanta `TermsRefusal` | `terms:<código>` |
| 4 | `resolve_carry` levanta `CarryRefusal` | `carry:<código>` |
| 5 | `resolve_carry` levanta `ValidationError` | `american_bridge:invalid_terms_or_carry` |
| 6 | termos divergem do contrato | `american_bridge:series_terms_mismatch` |
| 7 | qualquer chamada ao binomial levanta `BinomialRefusal` | `binomial:<código>` |

Conferência 6: `symbol`, `strike` e `exercise_style` dos termos têm de ser iguais aos do
contrato. `contract_size` e `quotation_form` do contrato têm de ser iguais aos dos termos
**quando o contrato os traz**; se vierem `None` no contrato, valem os dos termos.

O `<código>` é o `.value` do código original, sem tradução. A ponte não cria recusa
numérica própria: tipo errado de `sigma`, `steps` fora do intervalo, `spot` não positivo e
probabilidade inadmissível são recusas do binomial e chegam com o código dele. Como a ponte
usa `steps` e `steps + 1`, o maior valor aceito é 4999.

### Cálculo

Com `q = resolved.dividend_yield`, `S = float(spot)`, `K = float(contract.strike)` e
`T = tte.year_fraction`, quatro chamadas a `crr_price`: americana e europeia, com `steps` e
com `steps + 1`.

```text
preço            = (americana_N + americana_N1) / 2
europeia         = (europeia_N + europeia_N1) / 2
prêmio           = preço - europeia
price            = Decimal(str(preço))
```

Com `T == 0.0` as quatro chamadas devolvem o intrínseco e o regime é `expiry`.

### Resultado suportado

| Campo | Valor |
|---|---|
| `supported`, `reason` | `True`, `None` |
| `model` | `"crr_american_v1"` |
| `price` | `Decimal(str(preço))` |
| `greeks`, `iv` | `None`, `None` |
| `regime` | `"expiry"` se `T == 0.0`; senão `"tree"` |
| `sigma_source` | `"given"` |

`inputs_echo`, nesta ordem: `symbol`, `kind`, `exercise_style`, `spot`, `strike`,
`time_years`, `rate_cont`, `sigma`, `dividend_yield` (o `q` resolvido), `steps` (como
`float`), `price_steps_n`, `price_steps_n1`, `european_same_trees`.

`assumptions`: as recebidas, **menos** as chaves `dividend_yield` e
`strike_adjusted_by_exchange_assumed`; mais as cinco de `resolved.assumptions()`; mais
`pricing_model = "crr_american_v1"`, `crr_steps` (como `float`), `crr_pair_average = True`
e `early_exercise_premium` (o prêmio, `float`).

### Resultado recusado

`supported = False`; `model`, `price`, `greeks`, `regime`, `iv` e `sigma_source` nulos.
`inputs_echo` traz os dez primeiros campos da lista acima, com `dividend_yield` igual a
`"unresolved"` enquanto o carry não tiver sido resolvido (conferências 1 a 5) e igual ao
`q` resolvido nas conferências 6 e 7. `assumptions` é cópia das recebidas, sem mexer.

## Âncoras

Contrato `XPTO1`, lote 100, fator 1, vencimento qualquer; `spot = Decimal("100")`,
`rate_cont = 0.05`, `sigma = 0.2`, `T = 1.0`, `steps = 200`.

| Âncora | Série | Termos | Carry | Prêmio |
|---|---|---|---|---|
| A1 | call, `K = 100` | `UNPROTECTED`, com evidência | rendimento contínuo `0.08` | 0.401060 |
| A2 | put, `K = 100` | `UNKNOWN` | `NONE` | 0.519060 |

Preço esperado: A1 é a média de `crr_06` e `crr_07`; A2, a de `crr_16` e `crr_17`.

O esperado sai do JSON de referência do 2A, em `Decimal`: média dos dois `american_price`,
tolerância `1e-11 * max(1, ref)`. Valores que o protótipo do revisor obteve, para
conferência: A1 `6.543803959785978`, A2 `6.091951932388676`.

A2 é put americana, que a B3 não lista nessas classes. Está aqui porque exercita o caminho
"política desconhecida e nenhum rendimento", que a ponte tem de aceitar.

## Erro de discretização

Doze casos, `S = 100`, `steps = 400`. O preço da ponte tem de ficar a no máximo **0.01** do
valor de referência.

```text
tipo  K    r     q     sigma  T     referência
call  90   0.13  0.13  0.25   0.25  11.0944
call  100  0.13  0.13  0.25   0.25   4.8565
call  110  0.13  0.13  0.25   0.25   1.6336
call  90   0.05  0.10  0.20   1.00  11.3127
call  100  0.05  0.10  0.20   1.00   5.9283
call  110  0.05  0.10  0.20   1.00   2.8874
call  90   0.13  0.06  0.40   1.00  22.5981
call  100  0.13  0.06  0.40   1.00  17.8341
call  110  0.13  0.06  0.40   1.00  13.9470
put   90   0.13  0.00  0.25   0.25   0.8434
put   100  0.13  0.00  0.25   0.25   3.7929
put   110  0.13  0.00  0.25   0.25  10.3163
```

De onde vem a referência: média das árvores de `N` e `N + 1` com 2.000 e com 4.000 passos,
extrapolada (`2 * A(4000) - A(2000)`), calculada com o próprio `crr_price`. Não é
independente da produção; mede só o erro de discretização, sobre um núcleo que o 2A já
conferiu. Incerteza da referência, pela diferença para o nível anterior: até 0.00045.
Erro medido com 400 passos: até 0.0030. Com 200 passos: até 0.0077.

Calls com `q > 0` usam termos `UNPROTECTED` com evidência; puts usam `UNKNOWN` e `NONE`.

## Testes exigidos

Em `tests/unit/derivatives/test_american_bridge.py`, salvo T10.

**T1. Âncoras A1 e A2**, com preço, prêmio (tolerância `1e-9`), `model`, `regime`,
`sigma_source`, `greeks is None` e `iv is None`.

**T2. Média do par.** `price == Decimal(str((price_steps_n + price_steps_n1) / 2))`, e os
dois valores do eco são os de `crr_price` com `steps` e `steps + 1`.

**T3. Fonte única do rendimento.** Com `assumptions` de entrada contendo
`dividend_yield = 0.0` e `strike_adjusted_by_exchange_assumed = True`: no resultado
suportado as duas chaves não existem; `carry_dividend_yield` e o `dividend_yield` do eco
são `0.08`; as outras chaves de entrada continuam lá. No resultado recusado, `assumptions`
é igual à entrada.

**T4. Tabela de recusas**, uma linha por teste, conferindo `reason` exato e todos os
campos numéricos nulos:

```text
contrato europeu                      american_bridge:not_american
contrato de estilo desconhecido       unknown_exercise_style
carry ausente (None)                  carry:missing_carry_assumption
PROTECTED com rendimento              carry:dividend_double_count
UNKNOWN com rendimento                carry:strike_adjustment_unknown
carry de outra série                  carry:missing_carry_assumption
termos adulterados (model_construct)  american_bridge:invalid_terms_or_carry
strike do contrato difere             american_bridge:series_terms_mismatch
símbolo do contrato difere            american_bridge:series_terms_mismatch
lote do contrato difere               american_bridge:series_terms_mismatch
fator do contrato difere              american_bridge:series_terms_mismatch
sigma = 0.0                           binomial:zero_volatility
sigma inteiro                         binomial:invalid_input_type
sigma NaN                             binomial:non_finite_input
steps = 0                             binomial:invalid_steps
steps = 5000                          binomial:invalid_steps
spot = 0                              binomial:input_out_of_domain
sigma = 0.001 com rate_cont = 0.9     binomial:probability_out_of_range
```

**T5. Precedência.** Contrato europeu com carry ausente devolve `not_american`. Carry
ausente com strike divergente devolve `carry:missing_carry_assumption`. Strike divergente
com `sigma = 0.0` devolve `series_terms_mismatch`.

**T6. Lote e fator ausentes no contrato.** Com `contract_size = None` e
`quotation_form = None` no contrato, o resultado é suportado e igual ao de A1.

**T7. Vencimento.** `T = 0.0`, call, `spot = 120`, `K = 100`: preço `Decimal("20.0")`,
regime `expiry`, prêmio `0.0`.

**T8. Sem prêmio onde não pode haver.** Call, `PROTECTED` com evidência, carry `NONE`,
`rate_cont = 0.13`: `early_exercise_premium` com módulo até `1e-11 * max(1, preço)`.

**T9. Erro de discretização**, os doze casos, tolerância 0.01.

**T10. Guardas**, nos dois arquivos de arquitetura:

- a ponte pode importar `binomial`, `series_terms` e `carry`; os testes antigos passam sem
  perder nenhum caso;
- outro arquivo em `backend/derivatives/pricing/` que importe qualquer um dos três é
  infrator;
- um arquivo de `service/`, `mcp/`, `scripts/` ou `cli.py` que importe a ponte é infrator,
  direto ou por um intermediário;
- na árvore real, nenhum módulo de `backend/` ou `scripts/` importa a ponte;
- interpretador novo: importando todos os módulos de derivativos menos `binomial` e a
  ponte, nenhum dos dois aparece em `sys.modules`.

A exceção é o caminho fixo `backend/derivatives/pricing/american_bridge.py`. Não vale
padrão de nome, pasta inteira nem lista configurável.

## RED exigido

Dois RED por comportamento, com a saída colada no cartão e o commit identificado.

1. Com a ponte devolvendo só a árvore de `steps` passos: A1 falha por devolver
   `6.537469676838961` no lugar de `6.543803959785978`.
2. Com a ponte repassando as hipóteses recebidas sem filtrar: T3 falha por encontrar
   `dividend_yield = 0.0` ao lado de `carry_dividend_yield = 0.08`.

## Mutação

O autor aplica um por vez em cópia temporária e registra as falhas. Mínimo: 14 mortos, 0
sobrevivente.

1. só a árvore de `N`; 2. média de `N` e `N + 2`; 3. `q` lido de `assumptions`; 4. `q = 0`
quando o carry é `None`; 5. sem conferir strike; 6. sem conferir lote; 7. europeia aceita;
8. recusa com preço preenchido; 9. `BinomialRefusal` virando motivo genérico; 10. prêmio
com sinal trocado; 11. regime sempre `tree`; 12. chaves da Fase 01 mantidas; 13. recusa
alterando `assumptions`; 14. conferência do contrato antes da de carry; 15. `Decimal(preço)`
sem passar por `str`; 16. lote ausente no contrato tratado como divergência.

O revisor roda a própria lista.

## Conferência deste cartão

O revisor escreveu um protótipo da ponte e executou, na base `ff0c1be` e em Linux aarch64,
as duas âncoras, as 18 linhas de recusa e T5 a T8: os valores e motivos deste cartão são os
que o protótipo devolveu. O protótipo tem cerca de 45 linhas e não acompanha o cartão. As
guardas (T10) não foram prototipadas.

## Regressão e portão

Linha de base em `ff0c1be`, Linux aarch64 limpo: 9.184 aprovados, 16 pulados, 261
subtestes. O PR só pode aumentar a contagem.

```sh
python -m pytest tests/ -q --ignore=tests/integration --timeout=120
python -m mypy backend/ --strict
pyright backend/
git diff --check ff0c1be HEAD
git diff --numstat ff0c1be HEAD -- backend
git diff --exit-code ff0c1be HEAD -- backend \
    ':(exclude)backend/derivatives/pricing/american_bridge.py'
git diff --exit-code ff0c1be HEAD -- config scripts pyproject.toml uv.lock \
    CLAUDE.md AGENTS.md .claude tests/fixtures
git diff --stat ff0c1be HEAD -- tests/architecture
```

Os dois `--exit-code` saem com rc 0. O último comando lista só os dois arquivos de guarda.

```sh
python -m backend.derivatives.cli chain BOVA11 2026-11-19 --provider offline_fixture
python -m backend.derivatives.cli chain BOVA11 2026-11-19
```

A primeira saída é idêntica byte a byte à da base, por plataforma. A segunda devolve
`LIVE_NOT_ACTIVATED`, rc 3. A americana continua recusada na chain, no MCP e no CLI com
`american_not_supported_phase1`. Rodar em macOS e em Linux, em clone limpo.

Regras do repositório: docstring em toda classe e função pública, anotação de tipos,
imports absolutos, linhas com até 100 colunas, nunca `print`. Sem chamada real à OpLab, sem
token, sem leitura de `.env`.

## Decisões deste cartão

Francisco pode vetar qualquer uma antes do RED.

1. **ADR e SDD do marco entram no commit de SPEC deste PR**, em vez de um PR só de
   documentos. Poupa um ciclo. O custo: a aprovação do ADR fica implícita no "pode começar".
2. **Média de `N` e `N + 1`, sem extrapolação.** Corta o erro máximo pela metade na medição
   do revisor (180 casos), e não acrescenta método novo.
3. **A diferença entre as duas árvores não é limite de erro.** Em 180 casos ela cobriu o
   erro real em 75% a 82% deles, conforme `N`. Fica no eco, sem nome que sugira garantia.
4. **`steps` obrigatório, sem padrão.** O padrão e o lugar dele na configuração são a
   decisão D2 do ADR, no DL2B-PR04.
5. **Sem recuo para BSM**, mesmo onde americana e europeia coincidem (decisão D1 do ADR).
6. **`PricingOutcome` reaproveitado sem mudança**, com `greeks = None` em resultado
   suportado. O valor do modelo é uma constante da ponte; `PricingModel` não muda.
7. **Put americana é aceita pela ponte.** A B3 não lista, mas o núcleo calcula e a recusa
   por classe de ativo é assunto dos termos de série, não da ponte.

## Fora deste PR, com dono

| Item | Dono | Onde |
|---|---|---|
| IV americana e medição de custo | Codex, com cartão de Claude | DL2B-PR02 |
| Origem e vigência dos termos e do carry | Francisco decide (D3) | DL2B-PR03 |
| Chave, ligação na chain e número de passos padrão | Francisco decide (D2) | DL2B-PR04 |
| Simplificação de `crr_parameters` (piloto, S1) | Codex | PR próprio |
| Pontos cegos da guarda por alcance (`config/`, import dinâmico) | Codex | DL2B-PR04 |

## Entrega

PR em rascunho, com base e head na descrição, contagens do portão em macOS e em Linux e as
evidências no cartão. Em `current_state.md`, bloco "Fase 02 — Marco 2B" com
"PR atual: DL2B-PR01 — EM_REVISAO". O autor não integra.

Revisão paralela pela skill `quimera-lab-review`, se Francisco a mantiver: sessão que não
seja a do autor, sobre o head publicado, com o parecer fora do Git e só o SHA-256 dele na
descrição do PR. O resumo do parecer não vai na mensagem de entrega.

## Base bibliográfica

O rótulo entre parênteses diz o peso da fonte.

- Merton (1973), *Theory of Rational Option Pricing*. Call americana sem dividendo não é
  exercida antes do vencimento. (artigo original; citado de memória, sem leitura nesta
  sessão; o resultado foi conferido na árvore pela grade do DL2-PR04)
- Broadie e Detemple (1996), *American Option Valuation: New Bounds, Approximations, and a
  Comparison of Existing Methods*, Review of Financial Studies 9(4), 1211–1250. Comparação
  em larga escala de métodos para americanas e a variante binomial BBSR. (revisado por
  pares; lido só o resumo)
- Joshi, *The convergence of binomial trees for pricing the American put*, Journal of Risk.
  Os métodos mais eficazes usam truncamento, extrapolação de Richardson e às vezes
  suavização. Motivo para a decisão 2 ficar registrada como escolha mínima, não como a
  melhor. (revisado por pares; lido só o resumo)
- Medições do revisor nesta sessão: 180 casos contra referência extrapolada, e os 12 casos
  da tabela. (medição própria, com o próprio núcleo; grade pequena)
- Manual de Procedimentos Operacionais de Negociação da B3, versão de 01/07/2026, item
  3.3.1. SHA-256 do PDF:
  `35df8963b85b36774f431ae3c9b04c867a8ea7b863621307a45f3812e8b250ec`.

Quant Stack Exchange: o site segue bloqueado para as ferramentas de leitura desta sessão
e a busca restrita a ele voltou vazia. Nenhuma afirmação deste cartão se apoia nele.

## Evidências da implementação — EM_REVISAO

Base `ff0c1bec941eb4b78da0c717f1ece4dae2cf02e7`. A SPEC, em
`515f0cf4fc1e3580d6bd7c6fe6280059e25d705e`, contém as três cópias conferidas pelo
manifesto de origem. O GREEN de código e testes é
`522fa89a1304a8f23d1b1a8357637b28fc59e473`. O registro posterior das evidências muda
apenas este cartão e o bloco Marco 2B da memória.

### Dois REDs reproduzidos em clones dos respectivos commits

1. `609a2cdd0ed146e0feb7ebd1e2f0a9568812b495`. A1 devolveu o preço de N sozinho.
   A média esperada vem dos dois `american_price` do JSON em Decimal. Saída de pytest
   (trecho de `logs/red1.log`).

   ```text
   >       assert abs(outcome.price - american) <= Decimal("1e-11") * max(1, american)
   E       AssertionError: assert Decimal('0.00633428294684240645') <= (Decimal('1E-11') * Decimal('6.54380395978580340645'))
   E        +  where Decimal('0.00633428294684240645') = abs((Decimal('6.537469676838961') - Decimal('6.54380395978580340645')))
   FAILED tests/unit/derivatives/test_american_bridge.py::test_t1_anchors[A1] - ...
   1 failed in 0.13s
   ```

2. `c799efaefa0b6de0250c173fb1306b6c8312e46c`. A1 e A2 passaram com a média. Em T3,
   o rendimento de entrada `0.0` permaneceu nas hipóteses junto ao carry resolvido `0.08`.
   Saída de pytest (trechos de `logs/red2.log`).

   ```text
               "dividend_yield": 0.0, "strike_adjusted_by_exchange_assumed": True,
           assert outcome.assumptions["carry_dividend_yield"] == 0.08
   >       assert "dividend_yield" not in outcome.assumptions, outcome.assumptions
   E       AssertionError: {'calendar_id': 'test_calendar', 'carry_dividend_yield': 0.08, 'carry_effective_on': '2026-11-19', 'carry_kind': 'CONTINUOUS_YIELD', ...}
   FAILED tests/unit/derivatives/test_american_bridge.py::test_t3_single_yield_source
   1 failed, 2 passed in 0.12s
   ```

As reproduções com `pytest -vv` registram os SHAs, as asserções e o rc 1 em
`logs/red1.pinned.log` e `logs/red2.pinned.log`. No GREEN, T1–T9 somam 45 casos.
As duas guardas somam 48, incluindo os intrusos diretos e indiretos de T10 e as
provas em interpretador novo.

### Resultados numéricos

| Âncora | Preço no Mac | Prêmio no Mac |
|---|---:|---:|
| A1 · call com rendimento de 0.08 | 6.543803959785978 | 0.4010597478426474 |
| A2 · put com carry NONE | 6.091951932388676 | 0.5190598881323645 |

T1 compara com a referência decimal independente do 2A. T9 compara com as 12 referências
de alta resolução do cartão. No Mac, o maior erro absoluto a 400 passos foi
**0.00292704077488**, na call com K = 110, r = 0.13, q = 0.06, sigma = 0.40 e T = 1.
Preço obtido 13.94992704077488, referência 13.9470, limite 0.01. Os limites de T1, T8 e T9
são os da SPEC.

### Mutação

Um único defeito por execução em clone separado de `522fa89`. Controle de T1–T9 com
45 aprovados. Cada execução terminou com rc 1 por falha de asserção. O clone voltou
à árvore limpa. Os patches e as saídas individuais estão em `logs/mutants/M01…M16`.

| Mutante | Defeito introduzido | Primeiro teste que falhou |
|---|---|---|
| 01 | só N | T1 A1 |
| 02 | N e N + 2 | T1 A1 |
| 03 | q das hipóteses | T1 A1 |
| 04 | ausência de carry vira NONE | T3 |
| 05 | omite igualdade do strike | T4 strike |
| 06 | omite igualdade do lote | T4 lot |
| 07 | aceita europeia | T4 european |
| 08 | recusa com preço | T4 european |
| 09 | motivo genérico do binomial | T4 zero-sigma |
| 10 | prêmio com sinal trocado | T1 A1 |
| 11 | regime sempre tree | T7 vencimento |
| 12 | mantém chaves da Fase 01 | T3 |
| 13 | altera hipóteses na recusa | T3 |
| 14 | identidade do contrato antes de resolver carry | T4 invalid-terms |
| 15 | Decimal direto do float | T2 média exata |
| 16 | lote ausente diverge | T6 |

### Portões e consumidores

Clones limpos de base e candidato por plataforma. Python 3.12.13, ambientes existentes
conferidos contra o lock congelado. O Linux usou a imagem aarch64 local com rede desligada.

| Prova no GREEN | macOS arm64 nativo | Linux aarch64 |
|---|---:|---:|
| pytest do cartão · aprovados / pulados / subtestes aprovados | 9.244 / 16 / 261 | 9.244 / 16 / 261 |
| T1–T10, inclusive casos antigos das guardas | 93 aprovados | 93 aprovados |
| mypy strict | 0 erros, 160 arquivos | 0 erros, 160 arquivos |
| pyright | 0 erros, 0 avisos | 0 erros, 0 avisos |
| CLI padrão | LIVE_NOT_ACTIVATED, rc 3 | LIVE_NOT_ACTIVATED, rc 3 |
| cmp da demo offline entre base e candidato | rc 0, 67.097 bytes | rc 0, 67.101 bytes |

SHA-256 da demo offline em base e candidato, por plataforma:

- Mac `a7d82699b47d31acec31995ccea3cf4149ebcb92311f980fb23390627b1de9c3`
- Linux `f4f8003f2021b2744202c782f6e5245872c09d7f9d1968a3356466a7e85ead08`

**Prova separada da demo.** Na resposta sintética em memória, dez das cem linhas receberam
estilo americano. Em cada plataforma, o ChainService, a ferramenta MCP de teste e o CLI
devolveram os mesmos dez símbolos com `american_not_supported_phase1`, preço, gregas e IV
nulos. As outras 90 linhas continuaram suportadas em cada consumidor.

`git diff --check` e os dois `git diff --exit-code` do cartão retornaram 0. O numstat de
produção é 109 adições em `american_bridge.py`. Em arquitetura o diff lista somente as
duas guardas. O estado de prontidão continua A.

**Arquivo local das evidências.** No pai do clone, `evidencias-dl2b-pr01/` contém o manifesto
`SHA256SUMS.txt`, os patches de mutação e os logs novos. Em `logs/{mac,linux}/green/` ficam
as provas do commit de código. Em `logs/{mac,linux}/final/` ficam os portões repetidos para
o head de entrega, identificado por `git rev-parse HEAD` em `head.gates.log`.

## Revisão independente: GO (Claude, 2026-11-19)

Head revisado: `0883138baedd721f667c0133eb2e3fed286ea301`. Parecer: **GO**, sem defeito de
produção. Uma lacuna de teste fechada no commit desta seção e um resíduo retirado.

### Conferências

- **Primeiro commit (`515f0cf`).** Três arquivos e nada mais, com os SHA-256 do cartão. ADR
  e SDD não mudaram depois; o cartão só recebeu texto no fim.
- **Produção.** Um arquivo novo, `american_bridge.py`, com 109 linhas. `git diff
  --exit-code` com rc 0 para o resto de `backend`, `config`, `scripts`, arquivos protegidos
  e `tests/fixtures`. Em `tests/architecture`, só as duas guardas.
- **Ponte, lida linha a linha contra o contrato.** Ordem das sete conferências, eco,
  hipóteses e resultado conferem. Dois cuidados além do cartão, ambos corretos: `spot` com
  NaN sinalizador vira NaN comum e é recusado pelo binomial; a média do par não estoura
  quando a soma passa do maior `float`.
- **Guardas.** A exceção é o caminho fixo. Importar a ponte é infração em qualquer lugar,
  inclusive no domínio e por intermediário. O texto literal do nome dos módulos passou a
  propagar alcance, o que deixa a guarda mais estrita que antes.
- **REDs.** Reproduzidos em `609a2cd` (A1 com `6.537469676838961`) e em `c799efa` (T3 com
  `dividend_yield` ao lado de `carry_dividend_yield`).
- **Portão, clone limpo, Linux aarch64, Python 3.12.16.** 9.244 aprovados, 16 pulados, 261
  subtestes no head do autor; `mypy --strict` em 160 arquivos e `pyright` sem erro. Demo
  com o mesmo SHA-256 da base; CLI padrão com `LIVE_NOT_ACTIVATED`, rc 3.
- **Não reproduzido pelo revisor:** macOS. Os números do Mac são do autor.

### Ataques

- **Entradas hostis.** 70.000 chamadas com tipos válidos e valores extremos (NaN, infinito,
  `Decimal` fora de faixa, passos de `-1` a `10**400`, prazo negativo, série, estilo e
  carry divergentes): nenhuma exceção escapou, nenhuma recusa trouxe número e todo
  resultado suportado teve preço finito e não negativo.
- **Mutação do revisor.** 32 trocas próprias, rodando o arquivo novo e as duas guardas. O
  controle passou; 30 morreram; 2 ficaram vivas.

### Lacuna fechada neste commit

**Uma chave recebida podia, em tese, sobrescrever uma chave resolvida sem teste perceber.**
O mutante que põe as hipóteses do carry antes das recebidas sobreviveu: com ele, um chamador
que mandasse `carry_dividend_yield = 0.0` nas hipóteses apagaria o valor resolvido, e
voltaria a existir uma segunda fonte para o rendimento. A produção faz na ordem certa; o
que faltava era o teste. `test_caller_cannot_override_resolved_keys` envia as nove chaves
da ponte com valores falsos e exige o mesmo resultado de uma chamada limpa. O teste não foi
revisto por outro agente.

O outro mutante vivo é equivalente: comparar o contrato com os termos recebidos ou com os
revalidados dá no mesmo, porque termos inválidos já foram recusados antes.

### Resíduo retirado

O texto do programa de sonda em `test_fresh_interpreter` trazia um `import pytest` sem uso.
Retirado; o teste segue passando.

### Portão final

Com o teste do revisor, Linux aarch64 limpo: 9.245 aprovados, 16 pulados, 261 subtestes.

### Observações sem ação

- Quatro linhas das evidências passam de 100 colunas; são saída colada do pytest.
- A ponte não confere a vigência dos termos contra a data de avaliação. Está no cartão como
  não-objetivo e no SDD como pendência do DL2B-PR03.
- `steps` com tipo errado (texto, por exemplo) levanta exceção antes de qualquer
  conferência. O critério 2 do SDD cobre só tipo válido; o chamador da ponte, no DL2B-PR04,
  terá de garantir o tipo.
- Este parecer foi publicado antes de o revisor abrir o parecer da skill.
