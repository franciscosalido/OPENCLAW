# Lab de Derivativos, Fase 02 - SDD do Marco 2A

Autoridade: [ADR-0025](../../../ADR/ADR-0025-laboratorio-derivativos-fase2a.md)
Base: `main` em `1421116` (Fase 01 fechada em estado A)
Status: SPEC do marco; aprovada com o ADR-0025 em 2026-11-19 (PR #141)

## Objetivo

Entregar, em Python puro e sem dependencia nova, um preco binomial
americano (CRR) correto e auditavel, apoiado em termos de serie e premissa
de carry explicitos. O binomial nasce isolado: nenhuma superficie da Fase
01 o chama.

## Nao-objetivos do marco

- Dividendo discreto, suavizacao de arvore, Leisen-Reimer, Richardson,
  Bjerksund-Stensland, IV americana, gregas americanas.
- Ligar o binomial a chain, ao MCP ou ao CLI.
- NumPy/SciPy, PostgreSQL, chamadas reais a OpLab, token real, ordens,
  ativacao para Helena.
- Mudar formato, digest ou motivo de recusa de qualquer saida da Fase 01.
- Otimizar desempenho. O marco mede o custo; a decisao e do 2B.

## PRs do marco

| PR | Conteudo | Ligado a producao? |
|---|---|---|
| DL2-PR00 | ADR-0025 e este SDD | nao (so docs) |
| DL2-PR01 | termos da serie e recusas | nao |
| DL2-PR02 | premissa de carry e trava de dupla contagem | nao |
| DL2-PR03 | nucleo binomial e parametrizacao CRR | nao |
| DL2-PR04 | referencia, invariantes, mutacao, medicao | nao |

## Ciclo por PR

`SPEC_PRONTA -> RED_MOSTRADO -> GREEN -> EM_REVISAO -> MERGEADO`

- **SPEC_PRONTA:** cartao do PR em `docs/specs/derivatives/fase2/`, com
  escopo, aceite e tolerancias ja escritos.
- **RED_MOSTRADO:** os testes novos falham pelo motivo esperado, e a saida
  da falha fica registrada no cartao.
- **GREEN:** testes novos e suite existente verdes; `mypy --strict` e
  `pyright` em zero.
- **EM_REVISAO:** PR aberto; ninguem mergeia o proprio PR sem revisao.
- **MERGEADO:** squash-merge no GitHub e `git merge --ff-only origin/main`
  local (L2 do ADR-0025).

O estado do PR corrente fica no bloco "Fase 02 - Marco 2A" do
`docs/04_MEM/current_state.md`.

## Criterios de aceite do marco

### 1. Caso a mao (DL2-PR03)

Put, 2 passos, `S = 50`, `K = 52`, `r = 5%` continuo, `dt = 1`, `u = 1.2`,
`d = 0.8`. A arvore e dada, nao e CRR (`d != 1/u`): o caso exercita o
nucleo, nao a parametrizacao.

```text
p   = (exp(0.05) - 0.8) / (1.2 - 0.8) = 0.6281777409
1-p =                                   0.3718222591
df  = exp(-0.05)                      = 0.9512294245

Vencimento (passo 2):
  S_uu = 72   payoff put = 0
  S_ud = 48   payoff put = 4
  S_dd = 32   payoff put = 20

Passo 1, continuacao:
  no u (S = 60): df*(p*0 + (1-p)*4)  = 1.4147530940
  no d (S = 40): df*(p*4 + (1-p)*20) = 9.4639300740

Passo 1, intrinseco:
  no u: max(52 - 60, 0) = 0     -> nao exerce; vale 1.4147530940
  no d: max(52 - 40, 0) = 12    -> exerce;     vale 12

Raiz (S = 50):
  europeia  = df*(p*1.4147530940 + (1-p)*9.4639300740) = 4.1926542806
  americana = df*(p*1.4147530940 + (1-p)*12)           = 5.0896324742
  intrinseco na raiz = 2 < 5.0896324742 -> nao exerce na raiz
```

**Valores de aceite: europeia 4.192654; americana 5.089632; tolerancia
5e-5.**

Nota: os valores de livro 4.1923 e 5.0894 saem da mesma conta com `p`
arredondado a quatro casas (0.6282). Diferem do calculo exato em 3.5e-4 e
2.3e-4, acima da tolerancia; por isso o aceite usa os valores exatos
(decisao de Francisco em 2026-11-19, na sessao do DL2-PR00).

O primeiro teste do DL2-PR03 e a americana deste caso, e **tem de falhar
com o exercicio antecipado desligado** (devolveria 4.192654). Esse e o RED
do PR.

### 2. CRR europeu contra BSM (DL2-PR03)

Pelo menos 20 casos, cada um nos pares de passos 200/201 e 1000/1001,
comparados ao `bsm.price` da Fase 01.

Tolerancia proposta: **0.03 em valor absoluto para `S = 100` com
`N >= 1000`**. So pode mudar por adendo a este SDD **antes** do GREEN do
DL2-PR03, nunca depois.

A tolerancia do par 200/201 nao esta fixada; ver Pendencias.

### 3. Referencia americana independente (DL2-PR04)

Pelo menos 30 casos americanos em JSON versionado, gerados por outro agente
(L3 do ADR-0025), com o metodo e a precisao declarados no proprio arquivo.
Quem implementa nao gera nem edita a referencia.

### 4. Invariantes em grade (DL2-PR04)

Grade de pelo menos 2000 casos, com 0 excecao nao tipada:

- americana >= europeia da mesma arvore;
- americana >= intrinseco;
- call com `q = 0` e `r >= 0` igual a europeia, com tolerancia 1e-12.

Com `r < 0` a igualdade da call **nao** vale: o exercicio antecipado da
call pode ser otimo mesmo com `q = 0`. Ha caso proprio para isso, fora da
invariante de igualdade.

### 5. Recusas tipadas do binomial (DL2-PR03)

Cada uma devolve recusa tipada, nunca numero: `p` fora de `(0,1)`; passos
fora de `[1, 5000]` ou nao inteiros; `sigma = 0`; entrada nao finita.

### 6. Recusas de serie e de carry (DL2-PR01 e DL2-PR02)

100% das linhas sem lote, sem fator de cotacao, com estilo desconhecido,
sem premissa de carry, ou com ajuste desconhecido e dividendo > 0,
recusadas com motivo especifico. Nenhum valor padrao para lote.

| Condicao | Motivo |
|---|---|
| lote ausente | `missing_contract_size` |
| fator de cotacao ausente | `missing_quotation_form` |
| estilo de exercicio desconhecido | `unknown_exercise_style` |
| moeda desconhecida | `unknown_currency` |
| premissa de carry nao informada | `missing_carry_assumption` |
| provento no strike e no rendimento | `dividend_double_count` |
| ajuste `UNKNOWN` com dividendo > 0 | `strike_adjustment_unknown` |
| dividendo discreto informado | `discrete_dividends_not_supported` |

### 7. Regressao (todos os PRs)

- suite existente verde;
- digest das europeias inalterado: `840770d25be12b8602c614bd`;
- demo identica byte a byte por plataforma;
- americana continua recusada na chain, no MCP e no CLI.

### 8. Mutacao (DL2-PR04)

Pelo menos 6 mutantes mortos:

1. sem exercicio antecipado;
2. desconto errado;
3. `p` e `1-p` trocados;
4. payoff de put e de call trocados;
5. exercicio so no vencimento;
6. exercicio so na raiz.

### 9. Portabilidade (DL2-PR04)

Mesma contagem de testes em macOS e Linux, em clone limpo. Diferenca
numerica relativa entre plataformas <= 1e-9.

### 10. Disciplina de PR e medicao (todos; medicao no DL2-PR04)

Cada PR com no maximo 400 linhas de producao; zero dependencia nova;
arquivos protegidos intactos. Tempo de um preco CRR com `N = 1000` medido
no Mac e registrado.

## Riscos e mitigacao

| Risco | Mitigacao |
|---|---|
| Oscilacao par/impar do CRR | Convergencia sempre no par `N` e `N+1` |
| `p` fora de `(0,1)` | Recusa tipada; nunca truncar `p` |
| Taxa negativa | Caso proprio; igualdade da call restrita a `r >= 0` |
| Dupla contagem de dividendo | Trava do DL2-PR02; carry com fonte e data |
| Tolerancia ajustada depois do resultado | So por adendo antes do GREEN |
| Lentidao em Python puro | Medir no 2A; decidir NumPy no 2B (L4) |
| Regra de bolsa de memoria | L5: documento datado ou `UNKNOWN` |

## Pendencias

- Tolerancia do criterio 2 para o par 200/201: nao fixada. Tem de entrar
  por adendo antes do GREEN do DL2-PR03.
- Identificadores das recusas do criterio 5: fixar na SPEC do DL2-PR03.
- Regras de ajuste de strike, proventos, lote, fator de cotacao, estilo e
  moeda por serie: **hipotese a confirmar com documento datado** (lista no
  ADR-0025). Ate la, a politica de ajuste e `UNKNOWN`.
- Definicao exata do digest e do procedimento de comparacao da demo por
  plataforma: reaproveitar o que o `SDD_correcoes_fase01.md` usou e citar o
  comando na SPEC do DL2-PR01.

## Adendo 1 (2026-11-19) - antes do GREEN do DL2-PR03

Autor: Claude. Entra no commit de SPEC do DL2-PR03. Nao reescreve o texto acima; onde houver
conflito, vale este adendo. Francisco pode vetar qualquer item antes do RED.

### A1. Criterio 2: tolerancia do par 200/201

**0.15 em valor absoluto para `S = 100` com `N` em `{200, 201}`.** E a mesma regra do 0.03 em
`N >= 1000`: tolerancia igual a `30/N`. A base e a ordem de convergencia 1 do CRR para
europeias (Leisen e Reimer, 1996; Diener e Diener, 2004; Chang e Palmer, 2007).

Medido antes do GREEN, nos 24 casos do cartao do DL2-PR03, com implementacao do revisor que
nao foi entregue ao autor: maior erro absoluto 0.0292 em 200/201 e 0.0059 em 1000/1001.

Fecha a pendencia "Tolerancia do criterio 2 para o par 200/201".

### A2. Criterio 5: identificadores das recusas do binomial

| Identificador | Condicao |
|---|---|
| `invalid_input_type` | numero que nao e `float` exato; `kind`, `style` ou arvore de outro tipo |
| `unknown_exercise_style` | estilo `UNKNOWN` |
| `non_finite_input` | `NaN` ou infinito em qualquer entrada numerica |
| `invalid_steps` | passos que nao sao `int` exato, ou fora de `[1, 5000]` |
| `input_out_of_domain` | `S <= 0`, `K <= 0`, `sigma < 0`, `T < 0`, `q < 0`; no nucleo, ver nota |
| `zero_volatility` | `sigma = 0` com `T > 0`, na parametrizacao CRR |
| `probability_out_of_range` | `p <= 0` ou `p >= 1` |
| `tree_not_representable` | estouro em `float`, `u` e `d` iguais, ou resultado nao finito |

Nota: no nucleo, `input_out_of_domain` cobre tambem `d <= 0`, `u <= d` e desconto `<= 0`.

Os quatro itens do criterio 5 correspondem a `probability_out_of_range`,
`invalid_steps`, `zero_volatility` e `non_finite_input`. Os outros quatro existem para que
nenhuma entrada produza excecao nao tipada.

Fecha a pendencia "Identificadores das recusas do criterio 5".

### A3. Criterio 4: igualdade da call americana com a europeia

Onde se le "com tolerancia 1e-12", leia-se:
**`|americana - europeia| <= 1e-11 * max(1, europeia)`**. A condicao `q = 0` e `r >= 0` nao
muda.

Motivo, medido antes do GREEN: com `r = 0` e call muito dentro do dinheiro, a continuacao e o
intrinseco sao iguais em aritmetica exata, e o arredondamento decide qual deles entra. Em
`S = 100`, `K = 40`, `sigma = 0.1`, `T = 0.05`, `N = 500` a diferenca absoluta foi 3.0e-12; em
`S = 10000` chegou a 1.9e-10. Em termos relativos ao preco, o maior valor em 1.458 casos foi
3.1e-14. Um limite absoluto de 1e-12 reprovaria uma implementacao correta.

## Adendo 2 (2026-11-19) - antes do primeiro teste do DL2-PR04

Autor: Claude. Entra no commit de SPEC do DL2-PR04. Nao reescreve o texto acima; onde houver
conflito, vale este adendo. Francisco pode vetar qualquer item antes do primeiro teste.

### B1. Criterio 3: o que e a referencia e quem a gera

Quem gera e Claude, que nao implementou `binomial.py` (Adendo 1 do ADR-0025). Quem implementa
copia os arquivos sem editar; os testes conferem o SHA-256 e regeneram o JSON byte a byte.

O arquivo traz o **preco exato da arvore CRR finita** de cada caso, europeu e americano,
calculado em `decimal` com 60 digitos de trabalho, 20 digitos publicados e conferencia a 90
digitos. **Nao e o preco do modelo continuo.** O erro de discretizacao da arvore nao aparece
nele, e nenhum criterio deste marco mede esse erro para americanas.

O que a referencia pega: erro de implementacao na producao (indice, percurso, ordem das
operacoes, arredondamento acumulado). O que ela nao pega: erro de formula comum aos dois
lados. Contra esse valem os casos a mao do criterio 1, o BSM do criterio 2, a soma binomial
fechada que o gerador confere para a europeia, e os parametros que Hull imprime para a
arvore de 5 passos.

Tolerancia: `|producao - referencia| <= 1e-11 * max(1, |referencia|)`.

Medido antes do primeiro teste, nos 42 casos, em Linux x86_64 (Python 3.13) e Linux aarch64
(Python 3.12): maior desvio de preco abaixo de 1.8e-13 nessa mesma escala.

### B2. Criterio 4: como ler "0 excecao nao tipada", e dois acrescimos

A grade inclui pontos em que a arvore e inadmissivel. Em cada ponto o resultado e um numero
finito ou `BinomialRefusal`; qualquer outra excecao reprova. O minimo de 2000 conta so os
pontos precificados. A igualdade da call segue A3.

Acrescimos, os dois medidos antes do primeiro teste:

- put com `r <= 0` e `q >= r` igual a europeia, com a tolerancia de A3;
- simetria: `call(S, K, r, q) = put(K, S, q, r)` na mesma arvore, europeia e americana, com
  a tolerancia de A3. So entra com `r >= 0`, porque a producao recusa rendimento negativo.

O caso proprio de `r < 0` fica definido assim: call com `q = 0`, `r < 0`, dentro do dinheiro
e `sigma >= 0.12` tem americana maior que a europeia por mais de 0.01.

### B3. Criterio 7: regressao sem o digest

Onde se le "digest das europeias inalterado: `840770d25be12b8602c614bd`", leia-se:
**nenhum arquivo de producao que existia no fim da Fase 01 (`1421116`) foi alterado.** O
comando abaixo so pode listar adicoes:

```sh
git diff --name-status 1421116 HEAD -- backend config scripts
```

Motivo: o valor do digest foi obtido em Linux aarch64 e o verificador nunca entrou no
repositorio. Um criterio que so uma maquina consegue conferir nao e criterio. Arquivo
inalterado prova o mesmo em qualquer plataforma, e os testes da Fase 01 contra o oraculo BSM
seguem verdes sem edicao. Os outros tres itens do criterio 7 nao mudam.

Conferido em `1dc7760`: o comando lista tres adicoes (`series_terms.py`, `carry.py` e
`binomial.py`, 499 linhas) e nenhuma modificacao.

Fecha a parte do digest da pendencia "Definicao exata do digest e do procedimento de
comparacao da demo por plataforma". O comando da demo esta em cada cartao.

### B4. Criterio 8: leitura dos itens 1, 2 e 5

"Sem exercicio antecipado" (item 1) e "exercicio so no vencimento" (item 5) sao a mesma
alteracao. Para o item 5 valer como mutante proprio, leia-se: **exercicio comparado so no
ultimo passo antes do vencimento**.

"Desconto errado" (item 2) tem duas formas e as duas entram: sem desconto, e desconto com
`r - q` no lugar de `r`. A segunda so aparece com `q > 0`.

Ficam sete mutantes. Os sete tem de morrer so com o arquivo de teste novo do DL2-PR04.

### B5. Criterio 9: como se mostra a diferenca entre plataformas

Cada plataforma fica a `1e-11` da mesma referencia (B1). Logo duas plataformas diferem entre
si em no maximo `2e-11`, abaixo do `1e-9` do criterio.

Alem disso, o autor registra em macOS e em Linux o SHA-256 da lista hexadecimal dos 84
precos da referencia. SHA igual significa diferenca zero. Medido pelo revisor: lista
identica em Linux x86_64 (Python 3.13.18) e Linux aarch64 (Python 3.12.16), SHA-256
`773a2bcdf3a122bd6662cb4f6e5b26c015106e63b886f43e716243fcee418ef1`.
