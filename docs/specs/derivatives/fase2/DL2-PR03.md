# DL2-PR03 — Núcleo binomial e parametrização CRR

Estado: **SPEC_PRONTA** (Claude, 2026-11-19). Autoridade: ADR-0025 e `SDD_FASE2A.md`,
critérios 1, 2 e 5, com o Adendo 1 que acompanha este cartão.
Base: `main` em `ad86380ed67c1c0ad7ad0974562d9bfce38d16f8`.
Branch: `feat/dl2-pr03-binomial-crr`.
Implementa: Codex. Revisa e integra: Claude. Estado de prontidão: A, sem mudança.

Como usar: o primeiro commit do branch traz duas coisas, sem alteração de texto. (1) Este
arquivo, copiado para `docs/specs/derivatives/fase2/DL2-PR03.md`. (2) O conteúdo de
`reports/fase02/SDD_FASE2A_ADENDO_1.md`, acrescentado ao fim de
`docs/specs/derivatives/fase2/SDD_FASE2A.md`. SHA-256 do adendo:
`999c6c855bfeaf1849d99e057922b951f9826794c5459ce21259b700d7dbe923`.
As evidências entram abaixo do cartão, em seções novas.

## Objetivo

Uma função pura devolve o preço de uma opção em árvore binomial, europeia ou americana, ou
recusa com motivo tipado. São duas peças: um núcleo de indução retroativa, que recebe a árvore
pronta e não sabe o que é CRR, e uma parametrização CRR, que monta a árvore a partir de
volatilidade, taxa, rendimento, prazo e número de passos. Nada em produção chama essas funções
ao fim deste PR.

## Escopo

| Arquivo | O que entra |
|---|---|
| `backend/derivatives/pricing/binomial.py` (novo) | tipos, recusas e as três funções |
| `tests/unit/derivatives/test_binomial.py` (novo) | testes de contrato |
| `tests/architecture/test_binomial_isolation.py` (novo) | isolamento |
| `docs/specs/derivatives/fase2/DL2-PR03.md` | este cartão e as evidências |
| `docs/specs/derivatives/fase2/SDD_FASE2A.md` | só o Adendo 1, no fim do arquivo |
| `docs/04_MEM/current_state.md` | só o bloco "Fase 02 — Marco 2A" |

Produção nova: um arquivo, com meta de até 220 linhas (teto do marco: 400). Zero dependência
nova: só `math`, `dataclasses`, `enum` e os enums `OptionKind` e `ExerciseStyle` de
`backend.derivatives.domain.models`.

## Não-objetivos

- Ligar o binomial à chain, ao `ChainService`, ao MCP, ao CLI ou à ponte de precificação.
- Importar `bsm`, `series_terms`, `carry` ou `config` dentro de `binomial.py`. Não há recuo
  silencioso de americana para BSM.
- Tocar em `bsm.py`, inclusive para acrescentar valor a `PricingModel`.
- Gregas, volatilidade implícita, dividendo discreto, suavização, Richardson, Leisen–Reimer.
- Referência americana em JSON, grade de 2.000 casos, medição de tempo: são do DL2-PR04.
- Otimizar. O único requisito de custo deste PR é a memória (seção "Testes exigidos", item 9).

## Contrato

### Tipos públicos de `binomial.py`

**`BinomialRefusalCode`** (`StrEnum`): os oito identificadores da tabela de recusas.

**`BinomialRefusal`** (`Exception`): atributo `code`; a mensagem é só o valor do código, sem
ecoar entrada. Mesmo molde de `TermsRefusal` e `CarryRefusal`.

**`TreeParameters`** (`dataclass` congelada, com `slots`): `up`, `down`, `prob_up`, `discount`
(todos `float`) e `steps` (`int`). `discount` é o fator de desconto de um passo. O número de
passos mora dentro da árvore para que núcleo e parametrização não possam divergir.

### Regras de entrada, comuns às três funções

- Todos os parâmetros são nomeados e obrigatórios. Nenhum tem valor padrão, nem o rendimento.
- Número é `float` exato. `int`, `bool`, `Decimal` e `str` são recusados, inclusive `100` no
  lugar de `100.0`. Quem converte é o chamador.
- `steps` é `int` exato em `[1, 5000]`. `True` e `200.0` são recusados.
- `kind` é `OptionKind`; `style` é `ExerciseStyle`. Texto é recusado.

### `crr_parameters(*, sigma, rate_cont, dividend_yield, time_years, steps) -> TreeParameters`

Com as expressões nesta forma, para que duas implementações cheguem aos mesmos números:

```text
dt       = time_years / steps
up       = exp(sigma * sqrt(dt))
down     = 1.0 / up
growth   = exp((rate_cont - dividend_yield) * dt)
prob_up  = (growth - down) / (up - down)
discount = exp(-rate_cont * dt)
```

`prob_up` nunca é truncado para caber em `(0, 1)`. A condição equivale a
`|rate_cont - dividend_yield| * sqrt(dt) < sigma`: com volatilidade baixa, taxa alta e poucos
passos ela falha, e a resposta é recusa.

### `tree_price(*, kind, style, spot, strike, tree) -> float`

Indução retroativa sobre `tree`. No vencimento, o valor de cada nó é o payoff. Em cada nó
anterior, a continuação é
`discount * (prob_up * valor_de_cima + (1 - prob_up) * valor_de_baixo)`. No estilo europeu o
valor do nó é a continuação. No americano é o maior entre a continuação e o intrínseco do nó,
em todos os nós, inclusive a raiz. O preço do ativo no nó com `j` altas depois de `i` passos
vale `spot * up**j * down**(i - j)`. A forma de calcular é livre, respeitada a regra numérica 1.

### `crr_price`

```text
crr_price(*, kind, style, spot, strike, time_years, rate_cont, sigma, dividend_yield,
          steps) -> float
```

Valida as entradas. Se `time_years == 0.0`, devolve o intrínseco, nos dois estilos, sem montar
árvore. Caso contrário devolve `tree_price(..., tree=crr_parameters(...))`.

### Recusas e precedência

Nenhuma destas condições devolve número. A ordem abaixo é a de avaliação: quando duas
condições valem ao mesmo tempo, sai a de cima.

| # | Código | Condição |
|---:|---|---|
| 1 | `invalid_input_type` | número que não é `float` exato; `kind`, `style`, `tree` de outro tipo |
| 2 | `unknown_exercise_style` | `style` é `UNKNOWN` |
| 3 | `non_finite_input` | `NaN` ou infinito em qualquer número |
| 4 | `invalid_steps` | `steps` que não é `int` exato, ou fora de `[1, 5000]` |
| 5 | `input_out_of_domain` | ver abaixo |
| 6 | `zero_volatility` | `sigma == 0.0` com `time_years > 0.0` (só na parametrização CRR) |
| 7 | `probability_out_of_range` | `prob_up <= 0.0` ou `prob_up >= 1.0` |
| 8 | `tree_not_representable` | ver abaixo |

`input_out_of_domain`: `spot <= 0`, `strike <= 0`, `sigma < 0`, `time_years < 0`,
`dividend_yield < 0`. No núcleo: `down <= 0`, `up <= down`, `discount <= 0`. Taxa negativa é
válida, e por isso `discount > 1` também é.

`tree_not_representable`: a árvore não cabe em `float`. Cobre `OverflowError` em `exp` ou em
potência, maior preço do ativo (`spot * up**steps`) não finito, `up` e `down` iguais depois do
arredondamento, e resultado final não finito. Sai no ponto em que o cálculo quebra, o que pode
ser antes ou depois da condição 7.

Dois pontos de ordem que os testes fixam:

- `time_years == 0.0` é avaliado depois das condições 1 a 5 e antes da 6. Prazo zero com
  `sigma == 0.0` devolve o intrínseco; prazo zero com `steps = 0` é `invalid_steps`.
- `crr_parameters` não trata prazo zero: lá, `time_years == 0.0` cai em
  `tree_not_representable`, porque `up == down`.

### Três regras numéricas

Cada uma evita uma reprovação que só apareceria na revisão. As três foram medidas no protótipo
do revisor.

1. **Na raiz, o intrínseco usa o `spot` recebido.** Se o preço da raiz vier de produtos ou
   divisões acumulados ao longo da árvore, ele sai diferente de `spot` no último dígito, e a
   americana fica abaixo do intrínseco. No protótipo isso deu `29.999999999999993` onde o
   correto é `30.0`, e 9 violações de invariante em 288 casos.
2. **A europeia sai da mesma indução, sem o máximo.** Fórmula fechada ou soma binomial para a
   europeia quebra a desigualdade exata `americana >= europeia`, que só vale nó a nó quando as
   duas usam a mesma aritmética.
3. **Nenhum teste encosta na fronteira de `prob_up`.** Em `sigma = 0.01`, `r = 0.5`, `T = 1`
   a fronteira exata é `N = 2500`; ali o resultado depende do arredondamento da `libm`. Os
   testes usam `N = 2400` (recusa) e `N = 2600` (aceita).

## Casos à mão

Árvores dadas, que não são CRR. O teste calcula `prob_up = (exp(r) - d) / (u - d)` e
`discount = exp(-r)`, com `r` por passo. Valores abaixo conferidos em aritmética decimal de
40 dígitos.

| Caso | Opção | S | K | u | d | r | Passos | Europeia | Americana |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| H1 | PUT | 50 | 52 | 1.2 | 0.8 | 0.05 | 2 | 4.192654280604 | 5.089632474198 |
| H2 | PUT | 50 | 80 | 1.2 | 0.8 | 0.05 | 2 | 22.386993442877 | 30.0 |
| H3 | CALL | 100 | 90 | 1.1 | 0.9 | -0.05 | 1 | 5.385601326158 | 10.0 |
| H4 | CALL | 100 | 90 | 1.1 | 0.9 | 0.05 | 1 | 14.389351794936 | 14.389351794936 |
| H5 | CALL | 50 | 45 | 1.2 | 0.8 | -0.05 | 2 | 5.824442308122 | 6.741456697459 |

Tolerâncias: H1 com 5e-5, como manda o critério 1 do SDD, e também com 1e-9. Os demais com
1e-9. Três igualdades exatas (`==`): americana de H2 igual a `30.0`; americana de H3 igual a
`10.0`; americana de H4 igual à europeia de H4.

O que cada caso prende:

- **H1** é o critério 1 do SDD. O exercício acontece no nó de baixa do passo 1 (12 contra
  continuação de 9.4639). Sem exercício antecipado sai 4.192654; com exercício só na raiz,
  também.
- **H2** tem exercício na raiz: todos os nós estão dentro do dinheiro. Sem o exercício na raiz
  sai 26.098354.
- **H3** e **H5** são calls sem rendimento com taxa negativa, em que exercer antes é ótimo.
  Em H5 o exercício é no nó de alta do passo 1, não na raiz.
- **H4** é a mesma árvore de H3 com taxa positiva: a call americana vale a europeia.

Nota de contexto: H1 e H2 são puts americanas. O Manual de Procedimentos Operacionais de
Negociação da B3 (01/07/2026, item 3.3.1) lista puts sobre ações, BDRs e ETFs como somente
europeias. Esses casos testam o núcleo; não correspondem a instrumento listado.

## CRR europeu contra BSM

Referência: `bsm.price(BsmInputs(...), theta_basis=252).price`, de
`backend.derivatives.pricing.bsm`. Em todos os casos `S = 100.0`, estilo europeu, e `N` em
`{200, 201, 1000, 1001}`. `erro = crr - bsm`. Os números das tabelas entram como `float`
(`100.0`, não `100`).

| # | Opção | K | T | r | sigma | q | dd |
|---:|---|---:|---|---:|---:|---:|---:|
| 1 | CALL | 100 | 1.0 | 0.10 | 0.20 | 0.0 | 2.08821 |
| 2 | PUT | 100 | 1.0 | 0.10 | 0.20 | 0.0 | 2.08821 |
| 3 | CALL | 90 | 0.5 | 0.05 | 0.30 | 0.0 | 1.73123 |
| 4 | PUT | 110 | 0.5 | 0.05 | 0.30 | 0.0 | 2.31064 |
| 5 | CALL | 110 | 0.25 | 0.12 | 0.25 | 0.0 | 1.54177 |
| 6 | PUT | 90 | 0.25 | 0.12 | 0.25 | 0.0 | 0.75104 |
| 7 | CALL | 100 | 2.0 | 0.08 | 0.15 | 0.03 | 2.0676 |
| 8 | PUT | 100 | 2.0 | 0.08 | 0.15 | 0.03 | 2.0676 |
| 9 | CALL | 120 | 1.0 | 0.10 | 0.40 | 0.0 | 4.87121 |
| 10 | PUT | 80 | 1.0 | 0.10 | 0.40 | 0.0 | 2.60857 |
| 11 | CALL | 80 | 1.0 | 0.14 | 0.20 | 0.05 | 0.609434 |
| 12 | PUT | 120 | 1.0 | 0.14 | 0.20 | 0.05 | 3.12159 |
| 13 | CALL | 100 | 21/252 | 0.10 | 0.30 | 0.0 | 0.863823 |
| 14 | PUT | 100 | 21/252 | 0.10 | 0.30 | 0.0 | 0.863823 |
| 15 | CALL | 105 | 0.75 | -0.01 | 0.25 | 0.0 | 2.17055 |
| 16 | PUT | 95 | 0.75 | -0.01 | 0.25 | 0.0 | 2.11796 |
| 17 | CALL | 100 | 1.5 | 0.02 | 0.50 | 0.02 | 5.83235 |
| 18 | PUT | 100 | 1.5 | 0.02 | 0.50 | 0.02 | 5.83235 |
| 19 | CALL | 95 | 5/252 | 0.15 | 0.10 | 0.0 | 0.00040489 |
| 20 | PUT | 102 | 5/252 | 0.15 | 0.10 | 0.0 | 0.13198 |
| 21 | CALL | 100 | 1.0 | 0.0 | 0.20 | 0.0 | 1.99138 |
| 22 | PUT | 100 | 1.0 | 0.0 | 0.20 | 0.0 | 1.99138 |
| 23 | CALL | 130 | 1.0 | 0.10 | 0.20 | 0.0 | 3.5057 |
| 24 | PUT | 70 | 1.0 | 0.10 | 0.20 | 0.0 | 0.200291 |

Quatro critérios, todos fixados antes do GREEN:

- **(a) Tolerância do SDD.** `|erro| <= 0.03` em `N` 1000 e 1001; `|erro| <= 0.15` em `N` 200
  e 201 (Adendo 1, item A1). Medido: 0.0058 e 0.0292.
- **(b) Limite teórico por caso.** `|erro| <= 1.25 * dd / N + 1e-6`, nos quatro `N`. `dd` é o
  limite do coeficiente de `1/N` na expansão do erro do CRR (definição abaixo). Medido: o pior
  caso usa 80% do limite.
- **(c) Ordem de convergência.** Para cada caso, `m200 = |(erro(200) + erro(201)) / 2|` e
  `m1000 = |(erro(1000) + erro(1001)) / 2|`. A soma dos `m1000` é no máximo 0.30 vezes a soma
  dos `m200`. O valor teórico é 0.20; medido, 0.2185.
- **(d) Paridade na árvore.** Para cada uma das 24 linhas, com os mesmos parâmetros e nos
  quatro `N`: `|call - put - (S * exp(-q*T) - K * exp(-r*T))| <= 1e-9`. Medido: 1.3e-11.

O critério (a) sozinho deixa passar erro de ordem `1/N`, como `dt = T / (N + 1)`. O (b) pega.

**De onde vem `dd`.** Diener e Diener (2004) e Chang e Palmer (2007) dão o termo de ordem
`1/N` do erro do CRR para a call europeia. Escrevendo `s = sigma * sqrt(T)` e
`m = (r - q) * T`:

```text
d1  = (ln(S / K) + m + s*s/2) / s          d2 = d1 - s
A   = -s*s*(6 + d1*d1 + d2*d2) + 4*(d1*d1 - d2*d2)*m - 12*m*m
pre = S * exp(-q*T) * exp(-d1*d1/2) / (24 * s * sqrt(2*pi))
dd  = max(|pre * A|, |pre * (A + 12*s*s)|)
```

O coeficiente oscila com `N` dentro do intervalo `[pre*A, pre*(A + 12*s*s)]`; essa oscilação é
a diferença entre passos pares e ímpares. A fórmula publicada é para `S = 1`, `T = 1` e
`q = 0`. A passagem para `S`, `T` e `q` gerais é do revisor e foi conferida numericamente: o
maior valor de `|erro| * N / dd` em cada caso ficou entre 0.35 e 0.9999, sem passar de 1.
Para puts vale o mesmo `dd`, porque a árvore obedece à paridade.

## Invariantes em grade

Grade de 432 casos: `kind` em `{CALL, PUT}`, `K` em `{70, 100, 130}`, `sigma` em
`{0.15, 0.45}`, `T` em `{0.1, 1.0}`, `r` em `{-0.02, 0.0, 0.12}`, `q` em `{0.0, 0.06}`, `N` em
`{50, 51, 200}`, com `S = 100.0`. Americana e europeia saem da mesma árvore.

- `americana >= europeia`, sem tolerância. Medido: 0 violação.
- `americana >= intrínseco`, sem tolerância. Medido: 0 violação.
- Call com `q = 0` e `r >= 0` (72 casos): `|americana - europeia| <= 1e-11 * max(1, europeia)`
  (Adendo 1, item A3). Medido: 1.2e-15 em termos relativos.
- Put com `r <= 0` e `q >= r` (144 casos): mesmo limite. Medido: 2.1e-14.
- Fora da grade, call com `r = -0.05`, `q = 0`, `K = 90`, `T = 1`, `sigma = 0.2`, `N = 200`:
  `americana - europeia > 0.5`. Medido: 0.958.

As regiões sem prêmio de exercício vêm de Healy (2021): call com `q <= 0` e `q <= r`; put com
`r <= 0` e `r <= q`.

## Entradas de recusa

Caso-base de `crr_price`: `kind=PUT`, `style=AMERICAN`, `spot=100.0`, `strike=100.0`,
`time_years=1.0`, `rate_cont=0.10`, `sigma=0.20`, `dividend_yield=0.0`, `steps=200`. Cada linha
troca só o que está escrito.

| Troca | Resultado |
|---|---|
| `spot` em `Decimal("100")`, `100`, `True` | `invalid_input_type` |
| `sigma="0.2"`, `rate_cont=None` | `invalid_input_type` |
| `kind="PUT"`, `style="AMERICAN"` | `invalid_input_type` |
| `style=UNKNOWN` | `unknown_exercise_style` |
| `spot=nan`, `rate_cont=inf`, `sigma=-inf` | `non_finite_input` |
| `steps` em `0`, `-1`, `5001`, `True`, `200.0`, `"200"` | `invalid_steps` |
| `spot=0.0`, `strike=-1.0`, `sigma=-0.1` | `input_out_of_domain` |
| `time_years=-1.0`, `dividend_yield=-0.01` | `input_out_of_domain` |
| `sigma=0.0` | `zero_volatility` |
| `sigma=0.01`, `rate_cont=0.5`, `steps=1` | `probability_out_of_range` |
| `sigma=0.01`, `rate_cont=-0.5`, `steps=1` | `probability_out_of_range` |
| `sigma=0.01`, `rate_cont=0.5`, `steps=2400` | `probability_out_of_range` |
| `sigma=0.01`, `rate_cont=0.5`, `steps=2600` | aceita |
| `sigma=5.0`, `time_years=100.0`, `steps=5000` | `tree_not_representable` |
| `sigma=800.0`, `steps=1` | `tree_not_representable` |
| `time_years=1e-40`, `steps=1` | `tree_not_representable` |
| `steps=1` e `steps=5000` | aceita |
| `time_years=0.0` | `0.0` |
| `time_years=0.0`, `strike=110.0` | `10.0` |
| `time_years=0.0`, `sigma=0.0` | `0.0` |

Precedência, uma linha por par:

| Troca | Resultado |
|---|---|
| `spot=Decimal("1")` e `style=UNKNOWN` | `invalid_input_type` |
| `style=UNKNOWN` e `spot=nan` | `unknown_exercise_style` |
| `spot=nan` e `steps=0` | `non_finite_input` |
| `steps=0` e `spot=-1.0` | `invalid_steps` |
| `spot=-1.0` e `sigma=0.0` | `input_out_of_domain` |
| `time_years=0.0` e `steps=0` | `invalid_steps` |
| `time_years=0.0` e `sigma=-0.1` | `input_out_of_domain` |
| `sigma=0.0` e `rate_cont=0.5` | `zero_volatility` |

Núcleo, com `kind=PUT`, `style=AMERICAN`, `spot=50.0`, `strike=52.0` e a árvore `up=1.2`,
`down=0.8`, `prob_up=0.6`, `discount=0.95`, `steps=2`:

| Troca | Resultado |
|---|---|
| `prob_up` em `0.0`, `1.0`, `-0.1`, `1.2` | `probability_out_of_range` |
| `up=0.8`, `down=0.0`, `discount=0.0`, `spot=0.0` | `input_out_of_domain` |
| `up=0.8` e `prob_up=2.0` | `input_out_of_domain` |
| `tree` como `dict`; `up=1` (inteiro) | `invalid_input_type` |
| `steps=0` dentro da árvore | `invalid_steps` |
| `discount=1.05` | aceita |

## Testes exigidos

1. **Casos à mão.** H1 a H5, com as tolerâncias e as três igualdades exatas.
2. **Fórmulas CRR.** `crr_parameters` contra os valores abaixo, com tolerância relativa 1e-14,
   `steps` igual ao pedido e `down == 1.0 / up` com `==`.

   ```text
   sigma=0.2, rate_cont=0.10, dividend_yield=0.03, time_years=1.0, steps=200
     up=1.0142426086996437    down=0.9859573946337119
     prob_up=0.508840646914882    discount=0.9995001249791693

   sigma=0.45, rate_cont=-0.02, dividend_yield=0.0, time_years=0.25, steps=51
     up=1.0320078791759375    down=0.9689848499979516
     prob_up=0.49056854288508794  discount=1.0000980440216873
   ```

3. **Composição.** `crr_price(...) == tree_price(..., tree=crr_parameters(...))`, com `==`, em
   três casos da tabela do BSM, nos dois estilos.
4. **CRR contra BSM.** Os critérios (a), (b), (c) e (d) nas 24 linhas.
5. **Invariantes.** A grade de 432 casos e o caso de taxa negativa.
6. **Recusas.** As três tabelas de entradas, com o código conferido e a mensagem igual ao
   código.
7. **Prazo zero.** Intrínseco para call e put, dentro e fora do dinheiro, nos dois estilos.
8. **Determinismo.** Duas chamadas com as mesmas entradas devolvem o mesmo `float`. Nenhum
   estado de módulo muda.
9. **Memória.** Pico medido por `tracemalloc` abaixo de 1 MiB para uma americana com
   `N = 1000`. Uma árvore guardada inteira passaria de 10 MiB. Medido no protótipo: 62 KiB.
10. **Assinaturas.** As três funções só aceitam argumentos nomeados e nenhum tem valor padrão.

Tempo de referência no protótipo, em Python puro: 0.02 s para uma americana com `N = 1000` e
0.63 s com `N = 5000`. Não é critério deste PR; serve para o autor desconfiar de uma
implementação dez vezes mais lenta.

## Isolamento

Em `tests/architecture/test_binomial_isolation.py`:

1. **Ninguém importa o binomial.** Nenhum arquivo de `backend/` ou de `scripts/`, fora o
   próprio `binomial.py`, importa `backend.derivatives.pricing.binomial` (por `import`, por
   `from`, com apelido ou relativo), nem traz esse caminho em constante de texto. Como não há
   consumidor permitido, a varredura direta basta: alcance indireto exigiria um importador
   direto.
2. **Prova em execução.** Um interpretador novo importa todos os módulos de
   `backend.derivatives` menos o binomial. Ao fim, ele não está em `sys.modules`.
3. **O binomial só importa o que foi declarado.** Por AST, os imports de `binomial.py` são
   `__future__`, `math`, `dataclasses`, `enum`, `typing` e
   `backend.derivatives.domain.models`.

A guarda de `tests/architecture/test_series_terms_imports.py` não é editada e continua verde.

## RED exigido

Dois RED por comportamento, com a saída colada no cartão e o commit identificado. Erro de
coleta ou `ImportError` não vale.

1. Com o núcleo fazendo a indução sem comparar com o intrínseco: a americana de H1 falha por
   devolver 4.192654 no lugar de 5.089632. É o RED que o critério 1 do SDD exige.
2. Com `crr_parameters` devolvendo a árvore sem conferir `prob_up`: o caso `sigma=0.01`,
   `rate_cont=0.5`, `steps=1` falha com `DID NOT RAISE BinomialRefusal`.

## Mutação

O autor aplica um por vez em cópia temporária e registra as falhas. Mínimo: 15 mortos, 0
sobrevivente.

1. sem exercício antecipado; 2. exercício só na raiz; 3. sem exercício na raiz; 4. intrínseco
do nó calculado com o preço do nível vizinho; 5. `prob_up` e `1 - prob_up` trocados; 6. sem
desconto; 7. payoffs de call e put trocados; 8. `dt = T / (N + 1)`; 9. `up` sem a raiz
quadrada; 10. `prob_up` com `r` no lugar de `r - q`; 11. desconto com `r - q`; 12. aceitar
`prob_up == 1.0`; 13. aceitar `steps = 5001`; 14. prazo zero entrando na árvore; 15.
`sigma == 0.0` devolvendo número; 16. estilo europeu aplicando o máximo; 17. raiz usando preço
acumulado no lugar de `spot`; 18. aceitar `int` no lugar de `float`.

Mutante equivalente, para ninguém perder tempo: trocar `>=` por `>` na comparação entre
continuação e intrínseco não muda nenhum resultado.

O revisor roda a própria lista, sem reaproveitar a do autor.

## Conferência deste cartão

Antes de entregar, o revisor executou todas as linhas das tabelas e todos os critérios deste
cartão contra o próprio protótipo, já no contrato final: 0 falha. Os 18 mutantes da lista
acima morrem com os testes exigidos. O protótipo tem cerca de 110 linhas sem docstrings, então
a meta de 220 linhas é folgada. Ele não acompanha o cartão: o autor escreve o RED primeiro.

## Regressão e portão

Linha de base em `ad86380`, Linux aarch64 limpo: 8.539 aprovados, 16 pulados, 261 subtestes.
O PR só pode aumentar a contagem de aprovados.

```sh
python -m pytest tests/ -q --ignore=tests/integration --timeout=120
python -m mypy backend/ --strict
pyright backend/
git diff --check ad86380 HEAD
git diff --numstat ad86380 HEAD -- backend
git diff --exit-code ad86380 HEAD -- backend ':(exclude)backend/derivatives/pricing/binomial.py'
git diff --exit-code ad86380 HEAD -- config scripts pyproject.toml uv.lock \
    CLAUDE.md AGENTS.md .claude
git diff --exit-code ad86380 HEAD -- tests/architecture/test_series_terms_imports.py
```

Os três últimos têm de sair com rc 0.

Demo e CLI, comparados entre a base e a ponta na mesma plataforma:

```sh
python -m backend.derivatives.cli chain BOVA11 2026-11-19 --provider offline_fixture
python -m backend.derivatives.cli chain BOVA11 2026-11-19
```

A primeira saída é idêntica byte a byte à da base. A segunda devolve `LIVE_NOT_ACTIVATED`,
rc 3. A americana continua recusada na chain, no MCP e no CLI com
`american_not_supported_phase1`; os testes da Fase 01 que prendem isso seguem verdes sem
edição. Rodar em macOS e em Linux, em clone limpo.

Regras do repositório: docstring em toda classe e função pública, anotação de tipos, imports
absolutos, linhas com até 100 colunas, nunca `print`. Sem chamada real à OpLab, sem token, sem
leitura de `.env`.

## Decisões deste cartão

Tomadas dentro do ADR-0025. Francisco pode vetar qualquer uma antes do RED.

- **D1.** Oito códigos de recusa: os quatro do critério 5 e mais quatro, para que nenhuma
  entrada produza exceção não tipada.
- **D2.** Número é `float` exato. É a mesma regra de tipo exato dos termos e do carry, e
  elimina a classe de erro de `Decimal` e de inteiro gigante entrando na conta.
- **D3.** `steps` mora em `TreeParameters`.
- **D4.** Prazo zero tem precedência sobre volatilidade zero, como no BSM da Fase 01.
- **D5.** Rendimento sem valor padrão. Quem chama informa `0.0` de forma explícita.
- **D6.** Tolerância de 0.15 no par 200/201 e novo limite da igualdade da call (Adendo 1).
- **D7.** O limite teórico por caso, critério (b), entra como teste.

## Fora deste PR, com dono

| Item | Dono |
|---|---|
| Referência americana em JSON (critério 3) | DL2-PR04 |
| Quem gera essa referência | Francisco decide no DL2-PR04 (ver nota) |
| Grade de 2.000 casos, mutação do critério 8, medição de tempo | DL2-PR04 |
| Ponte termos → carry → binomial, e abertura das guardas | Marco 2B |
| Valor `crr` em `PricingModel` | PR da ponte |
| Adendo ao ADR-0025 sobre o manual da B3 | Claude |

Nota sobre a referência: o ADR-0025 (L3) diz que ela é gerada pelo Codex, e não por quem
implementa. Com o Codex implementando este PR, a regra passa a se contradizer. O protótipo do
revisor nunca foi entregue ao autor e pode servir de referência independente.

## Entrega

1. PR em rascunho contra `main`, com a descrição batendo com os números finais do cartão.
2. Bloco "Fase 02 — Marco 2A" do `current_state.md` em `PR atual: DL2-PR03 — EM_REVISAO`.
3. O autor não mergeia. O revisor revalida em clone limpo, roda a própria mutação e, com GO,
   faz o squash no GitHub e o avanço local (L2).

## Base bibliográfica

O rótulo entre parênteses diz o peso da fonte.

- Cox, Ross e Rubinstein (1979), *Option Pricing: A Simplified Approach*, Journal of Financial
  Economics 7(3), 229–263. Árvore, probabilidade neutra ao risco e a observação de que, sem
  dividendos, a call vale mais que o intrínseco enquanto a taxa for positiva. (artigo original)
- Hull, *Options, Futures, and Other Derivatives*, capítulo de árvores binomiais. Origem de H1;
  o livro traz 4.1923 e 5.0894, com `p` arredondado. (livro-texto; valores arredondados)
- Leisen e Reimer (1996), Applied Mathematical Finance 3(4), 319–346,
  DOI 10.1080/13504869600000015. Ordem de convergência 1 do CRR para a call europeia.
  (revisado por pares)
- Diener e Diener (2004), Mathematical Finance 14(2), 271–293; Chang e Palmer (2007), Finance
  and Stochastics 11(1), 91–105, DOI 10.1007/s00780-006-0020-6. Coeficiente explícito do termo
  `1/N` e sua oscilação. (revisado por pares; a fórmula foi lida como reproduzida em
  arXiv:1207.6756 e conferida numericamente pelo revisor)
- Lamberton (2018), *On the binomial approximation of the American put*, arXiv:1802.05614. Erro
  da put americana em `O((ln n)^a / n)`, com `r > 0` e rendimento não negativo. Motivo para
  não fixar tolerância americana neste PR. (arXiv; o registro indica publicação em Applied
  Mathematics and Optimization)
- Healy (2021), *Pricing American options under negative rates*, arXiv:2109.15157. Regiões sem
  exercício antecipado para call e put. (arXiv; não conferi se houve publicação com revisão
  por pares; as regiões usadas aqui foram conferidas numericamente na grade)
- Joshi, *The convergence of binomial trees for pricing the American put*, Journal of Risk.
  Compara 11 escolhas de parâmetros de árvore e aponta como mais eficazes a de Tian e uma
  árvore nova. Motivo para medir antes de otimizar. (revisado por pares; lido só o resumo)
- Manual de Procedimentos Operacionais de Negociação da B3, versão de 01/07/2026, item 3.3.1.
  SHA-256 do PDF: `35df8963b85b36774f431ae3c9b04c867a8ea7b863621307a45f3812e8b250ec`.

Quant Stack Exchange: o site está bloqueado para as ferramentas de leitura desta sessão e não
apareceu nas buscas. Nenhuma afirmação deste cartão se apoia nele.
