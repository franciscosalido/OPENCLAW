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
