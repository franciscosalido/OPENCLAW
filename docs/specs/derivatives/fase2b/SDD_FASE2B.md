# SDD - Fase 02, Marco 2B - ponte americana

Autor: Claude (2026-11-19). Autoridade: ADR-0026. Base: `main` em `ff0c1be`.
Implementa: Codex. Revisa e integra: Claude. Estado de prontidao: A, sem mudanca.

## Objetivo

Ao fim do marco, uma linha americana da chain sintetica sai com preco e volatilidade
implicita calculados pela arvore CRR, ou com uma recusa que diz exatamente qual precondicao
faltou. Tudo offline, atras de uma chave desligada por padrao.

## Criterios de aceite

1. **Ancoras da ponte (DL2B-PR01).** Com `steps = 200`, a ponte reproduz a media dos pares
   `crr_06`/`crr_07` e `crr_16`/`crr_17` da referencia do 2A, dentro de
   `1e-11 * max(1, ref)`.
2. **Recusas (DL2B-PR01).** 100% das linhas da tabela de recusas do cartao devolvem o motivo
   exato, com preco, gregas e regime nulos. Nenhuma excecao escapa da ponte para entrada de
   tipo valido.
3. **Fonte unica do rendimento (DL2B-PR01).** Em 100% dos resultados suportados, as chaves
   `dividend_yield` e `strike_adjusted_by_exchange_assumed` nao aparecem nas hipoteses, e
   `carry_dividend_yield` e o valor usado na arvore.
4. **Erro de discretizacao declarado (DL2B-PR01).** Nos 12 casos do cartao, com
   `steps = 400` e `S = 100`, o preco da ponte fica a no maximo 0.01 do valor de referencia
   de alta resolucao. Medido antes do cartao: 0.0030.
5. **Isolamento (DL2B-PR01 a 03).** Um unico modulo de producao importa binomial, termos e
   carry; zero modulo importa a ponte ate o DL2B-PR04.
6. **IV americana (DL2B-PR02).** Ida e volta: preco da ponte com `sigma` conhecido, invertido,
   devolve `sigma` com erro absoluto <= 1e-6, em pelo menos 40 casos. Tempo por inversao
   medido no Mac e registrado. O limite de tempo e fixado no cartao, antes do codigo.
7. **Origem dos termos (DL2B-PR03).** 100% das series sem registro, com registro vencido ou
   com registro divergente do contrato sao recusadas com motivo proprio.
8. **Ligacao (DL2B-PR04).** Chave desligada: saida da demo identica byte a byte a de
   `ff0c1be`, por plataforma. Chave ligada: toda linha americana tem preco ou motivo de
   recusa especifico, e nenhuma linha europeia muda.
9. **Regressao (todos).** Suite verde; nenhum arquivo de producao existente em `ff0c1be` e
   alterado antes do DL2B-PR04; CLI padrao devolve `LIVE_NOT_ACTIVATED`.
10. **Disciplina (todos).** No maximo 400 linhas de producao por PR; zero dependencia nova;
    arquivos protegidos intactos; contagem igual em macOS e Linux.

## Nao-objetivos do marco

Gregas americanas. Dividendo discreto. Richardson, suavizacao, Leisen-Reimer, Tian ou
qualquer troca de arvore. Bjerksund-Stensland. Superficie de volatilidade. Persistencia.
Homologacao com dado real (estado B). Ativacao para agentes (estado C). Ordens.

## Riscos e mitigacao

| Risco | Mitigacao |
|---|---|
| Rendimento contado duas vezes (strike ajustado e `q > 0`) | Trava do DL2-PR02 e criterio 3 |
| Ler a diferenca entre `N` e `N + 1` como limite de erro | ADR-0026, regra 3 |
| IV americana lenta demais em Python puro | Criterio 6 mede antes de ligar; D1 e D4 do ADR |
| Excecao na guarda vira porta aberta | Excecao por caminho fixo; teste com importador intruso |
| Ponte vista como preco de mercado | Estado A; hipoteses e modelo em todo resultado |
| Termos vencidos usados em silencio | Criterio 7; ate la a ponte so recebe termos do chamador |

## Plano

| PR | Entrega testavel |
|---|---|
| DL2B-PR01 | `price_american_contract` pura; criterios 1 a 5 |
| DL2B-PR02 | `american_implied_vol`; criterio 6; medicao para D1 e D4 |
| DL2B-PR03 | registro e resolvedor de termos e carry; criterio 7 |
| DL2B-PR04 | chave, ligacao na chain, MCP e CLI; criterios 8 e 9; fechamento |

## Pendencias

- D1 a D4 do ADR-0026.
- Vigencia dos termos frente a data de avaliacao: a ponte do DL2B-PR01 nao confere data.
  Fica para o DL2B-PR03.

## Adendo 1 (2026-11-20) - depois da Revisao 1 do ADR-0026

Autor: Claude, com as decisoes de Francisco de 2026-11-20. Nao reescreve o texto acima; onde
houver conflito, vale este adendo.

### A1. Criterio 6: teto de tempo

O limite de tempo do criterio 6 fica fixado: **210 ms de CPU por inversao com 200 passos no
Mac**. A medicao (nove inversoes depois de um aquecimento; minimo, mediana e maximo) e
registrada no cartao de cada PR que tocar o solver. Nao e teste automatico.

O resto do criterio 6 nao muda e vale para toda serie americana, sem caminho a parte para
call sem rendimento.

### A2. Criterio 8: o que e a chave

A chave sao dois argumentos da demo offline, exigidos em conjunto: `american_demo` e
`series_registry`. O numero de passos e opcional: ausente, vale o padrao de
`config/american_iv.yaml`. Com a chave desligada, informar passos e erro de argumento.

### A3. Criterio 11, novo: um motor por numero (DL2B-PR04)

Em 100% das linhas americanas suportadas da demo mista:

- o motor do preco e o de cada volatilidade implicita principal sao a arvore CRR, e o nome
  dele esta no resultado;
- o preco do modelo reproduz o mid por unidade com diferenca de ate 1e-7;
- as hipoteses da chain trazem o numero de passos usado e a origem dele.

E, na arvore de codigo: a ponte nao importa o solver de volatilidade da Fase 01 nem o BSM.

### A4. Criterio 12, novo: passos padrao (DL2B-PR04)

`config/american_iv.yaml` traz `default_steps: 200`. Campo ausente, nao inteiro ou fora de
1 a 4999 recusa a demo mista sem dados, e nao afeta a demo padrao.

### A5. Criterio 13, novo: motor de sombra (DL2B-PR04)

Em 100% das linhas americanas suportadas da demo mista, o resultado interno da linha traz a
volatilidade implicita do BSM europeu sobre o mesmo mid por unidade e o mesmo rendimento
resolvido, ou o motivo de nao ter sido calculada. Com a sombra ligada ou desligada por
mutacao, preco, volatilidades principais e motivo de recusa de toda linha sao identicos.

As hipoteses da chain trazem o nome do motor de sombra, quantas linhas foram comparadas e a
maior diferenca absoluta de volatilidade entre os dois motores.

### A6. Criterio 14, novo: cotacao que nao sustenta uma volatilidade unica (DL2B-PR04)

Linha americana com um lado da cotacao ausente, cotacao velha, ou preco que nao reage a
volatilidade nao publica volatilidade unica: sai recusada com motivo proprio. Quando ha os
dois lados, a linha publica as tres volatilidades (compra, meio e venda), nunca so a do meio.

### A7. Pendencias

D1 e D2 saem da lista. Ficam D3 e D4.
