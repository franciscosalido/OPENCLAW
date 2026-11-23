# DL3-PR08A — Supercartão: resultado da estrutura no vencimento

**Data:** 22/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `5b84f15` (DL3-PR07A2 integrado) · **PR novo**, em rascunho
**Decisão que este cartão implementa:** autorização de Francisco de 22/11/2026 para a análise
de estruturas (`AUTORIZACAO_ANALISE_ESTRUTURAS_2026-11-22.md`), item 1, primeira prova.

## 0. Escopo

Francisco quer olhar uma estrutura e saber **quanto ela ganha ou perde em cada cenário**.
Este cartão entrega o primeiro passo: uma função pura que calcula o resultado **no
vencimento** de uma estrutura de opções do mesmo ativo e do mesmo vencimento, com a
borboleta de calls dele como primeira prova.

Ordem dos cartões desta frente, por decisão de Francisco:

| Cartão | Conteúdo |
|---|---|
| **PR08A (este)** | resultado no vencimento; borboleta de calls com resultado conhecido |
| PR08B | a mesma borboleta montada em parte: posição executada ao lado da planejada |
| depois | borboleta de puts, travas e iron condor; estimativa antes do vencimento conferida com o QuantLib; calendário da B3. Um cartão para cada |

A fila anterior (PR07A3, PR07A4 e PR07B) fica atrás desta, por decisão de Francisco.

**Fora deste cartão:** estimativa antes do vencimento, vencimentos diferentes, ativo-objeto
como perna, margem, exercício antecipado, calendário, gráfico, tela e qualquer ligação com o
motor da boleta. Nenhuma dependência nova. **Nenhum código de terceiros**: implemente pela
definição do §2; não copie nem adapte código do OptionLab ou de outro projeto.

Todos os esperados foram calculados à mão e conferidos por um oráculo descartável do
planejador, que não será entregue.

## 1. Arquivos e tetos

| Arquivo | O que entra | Teto |
|---|---|---|
| `backend/derivatives/pricing/expiry_payoff.py` | módulo novo, só aritmética | 140 linhas |
| `tests/unit/derivatives/test_expiry_payoff.py` | P1–P9 | — |
| `tests/unit/derivatives/ticket/test_engine.py` | H1–H3 (§5), só testes | — |
| `docs/specs/derivatives/fase3/DL3-PR08A.md` | cópia deste cartão | — |
| `docs/specs/derivatives/fase3/AUTORIZACAO_ANALISE_ESTRUTURAS_2026-11-22.md` | cópia byte a byte | — |

SHA-256 da autorização:
`1d8fcdacee1438274328c16f1fd02c8104104503bd7b11238b1bc549e37ee105`.

**Não muda:** nenhum arquivo existente de `backend/`, fixtures, `current_state.md`,
arquivos protegidos. O módulo novo só importa a biblioteca padrão. Ele não importa
`ticket`, `oplab`, `mcp`, `adapters`, rede, relógio nem aleatoriedade.

## 2. Definição

**Perna.** Tipo (`CALL` ou `PUT`), lado (`BUY` ou `SELL`), strike (`Decimal` maior que
zero), quantidade (inteiro maior que zero) e prêmio por unidade (`Decimal` maior ou igual a
zero), que é o preço efetivamente pago ou recebido.

**Estrutura.** De 1 a 8 pernas, mais um multiplicador (inteiro maior que zero, padrão 1) e
custos totais em reais (`Decimal` maior ou igual a zero, padrão 0). Mesmo ativo e mesmo
vencimento são premissa de quem chama.

**Resultado no vencimento**, para um preço final `S` maior ou igual a zero:

- valor intrínseco da call: `max(0, S − strike)`; da put: `max(0, strike − S)`;
- resultado da perna: `sinal × quantidade × multiplicador × (intrínseco − prêmio)`, com
  sinal +1 na compra e −1 na venda;
- resultado da estrutura: soma das pernas menos os custos.

**Entrada.** `sinal × quantidade × multiplicador × prêmio`, somado nas pernas. Positivo é
débito pago; negativo é crédito recebido. É a mesma convenção do `net_limit` da boleta.

**Perfil.** O resultado é linear por trechos, com quebras nos strikes.

- **Ganho máximo e perda máxima:** o maior e o menor resultado em `S = 0` e em cada strike.
  Se a soma de `sinal × quantidade` das calls for positiva, o ganho é **ilimitado**; se for
  negativa, a perda é **ilimitada**. Do lado de baixo o preço para em zero, então nada é
  ilimitado ali.
- **Equilíbrios:** todo `S` maior ou igual a zero em que o resultado é zero, em ordem
  crescente, como fração exata. Num trecho inteiro em zero entram só as duas pontas do
  trecho.

Dinheiro é `Decimal` exato, sem `float`. Equilíbrio é `fractions.Fraction`.

## 3. Contrato público

Nomes fixos, para o teste e para o PR08B:

- `ExpiryLeg`: imutável, com `kind`, `side`, `strike`, `quantity`, `premium`.
- `expiry_leg_results(legs, spot, *, multiplier=1)`: tupla com o resultado de cada perna, na
  ordem das pernas, sem custos.
- `expiry_result(legs, spot, *, multiplier=1, costs=Decimal(0))`: resultado da estrutura.
- `expiry_profile(legs, *, multiplier=1, costs=Decimal(0))`: objeto imutável com
  `net_entry`, `breakevens`, `max_gain`, `max_loss`, `gain_unlimited` e `loss_unlimited`.
  `max_gain` é `None` se, e só se, `gain_unlimited` é verdadeiro. O mesmo vale para
  `max_loss` e `loss_unlimited`. `max_loss` é o menor resultado, com sinal (−2, não 2).
- `PayoffRefusal(ValueError)`: toda entrada inválida.

## 4. Cenários

Multiplicador 1 e custos zero, salvo onde indicado.

**P1 — a borboleta de Francisco.** Compra 1 call 95 a 7,00; vende 2 calls 100 a 3,50;
compra 1 call 105 a 2,00.

| `S` | 90 | 95 | 96 | 97 | 100 | 103 | 104 | 105 | 110 |
|---|---|---|---|---|---|---|---|---|---|
| Resultado | −2,00 | −2,00 | −1,00 | 0,00 | **+3,00** | 0,00 | −1,00 | −2,00 | −2,00 |

Entrada 2,00 (débito). Equilíbrios 97 e 103. Ganho máximo 3,00. Perda máxima −2,00. Nada
ilimitado. Resultado por perna em `S = 100`: −2,00; +7,00; −2,00.

**P2 — a mesma borboleta com quantidades 10, 20 e 10, multiplicador 100 e custos 12,50.**
Resultado em 95: −2.012,50; em 100: +2.987,50; em 105: −2.012,50. Entrada 2.000,00.
Equilíbrios `7761/80` e `8239/80` (97,0125 e 102,9875). Ganho máximo 2.987,50. Perda
máxima −2.012,50.

| # | Estrutura | Resultados | Entrada | Equilíbrios | Ganho máximo | Perda máxima |
|---|---|---|---|---|---|---|
| P3 | compra 1 call 100 a 5,00 | `S`=0: −5; 90: −5; 105: 0; 120: +15 | 5,00 | 105 | **ilimitado** | −5,00 |
| P4 | vende 1 call 100 a 5,00 | 0: +5; 100: +5; 105: 0; 120: −15 | −5,00 | 105 | 5,00 | **ilimitada** |
| P5 | vende 1 put 100 a 5,00 | 0: −95; 95: 0; 100: +5; 120: +5 | −5,00 | 95 | 5,00 | −95,00 |
| P6 | compra 1 put 100 a 5,00 | 0: +95; 95: 0; 100: −5; 120: −5 | 5,00 | 95 | 95,00 | −5,00 |
| P7 | compra 1 call 100 a 5,00; vende 1 call 105 a 5,00 | 0: 0; 100: 0; 102: +2; 105: +5; 120: +5 | 0,00 | 0 e 100 | 5,00 | 0,00 |
| P8 | compra 1 call 100 a 5,00; vende 2 calls 110 a 2,00 | 90: −1; 101: 0; 110: +9; 119: 0; 130: −11 | 1,00 | 101 e 119 | 9,00 | **ilimitada** |

**P9 — recusas.** Cada uma levanta `PayoffRefusal`: nenhuma perna; nove pernas; strike
zero; quantidade zero; prêmio negativo; strike ou prêmio em `float`; `S` negativo; `S` em
`float`; multiplicador zero; custos negativos; tipo ou lado fora dos dois valores.

## 5. Higiene — três testes que faltaram no DL3-PR07A2

Só testes; nenhuma linha de produção muda. Os três já passam no `main`. Os cenários vêm das
contraprovas da skill na cabeça `10076d3`; o planejador rodou o H1 e conferiu o H2 à mão.

| # | Cenário (boleta de referência do `Session`) | `gross()` esperado |
|---|---|---|
| H1 | gatilho armado com o `SPEC` do `test_trigger`; cotação de A às 15:00:00,000001; boleta `EXPIRED` | 25,00; 0,00; **0,00** |
| H2 | confirma às 14:00:02; cotação de A com ask 1,00 e tamanho 2 às 14:00:03 e às 14:00:04; cotação de B com bid 1,54 e tamanho 1 às 14:00:05; cotação de A com ask 1,00 e tamanho 2 às 14:00:06. Boleta `STOPPED`; `T1:A:1` `PARTIAL`, `T1:B:1` `PARTIAL`, `T1:B:2` `LIVE` | 25,00; 7,54; **16,04** |
| H3 | continuação de H2: cancela `T1:B:1` às 14:00:07; a ordem fica `CANCEL_REQUESTED` | igual a H2 |

## 6. Testes e mutantes

Um teste por cenário, com os valores escritos à mão. Compare dinheiro como `Decimal` e
equilíbrio como `Fraction`.

Mutantes obrigatórios, um por vez, cada um derrubando ao menos um teste:

1. Put calculada como call (P5, P6).
2. Sinal da venda igual ao da compra (P1).
3. Prêmio fora do resultado (P1).
4. Quantidade ignorada (P1: a perna vendida vale 2).
5. Multiplicador aplicado também aos custos (P2).
6. Custos fora do resultado (P2).
7. Entrada com o sinal trocado (P3, P4).
8. Ganho ilimitado não detectado (P3); perda ilimitada não detectada (P4, P8).
9. Ilimitado decidido só pela última perna, e não pela soma das calls (P8).
10. `S = 0` fora da busca de máximo e mínimo (P5, P6).
11. Equilíbrio só nos strikes, sem interpolar (P2).
12. Equilíbrio à direita do último strike ausente (P3, P8).
13. Trecho inteiro em zero devolvendo só uma ponta, ou nenhuma (P7).
14. `float` aceito como dinheiro (P9).
15. `EXPIRED` fora da regra terminal do bruto (H1).
16. Duas ordens abertas da mesma série sem somar (H2).
17. `CANCEL_REQUESTED` fora das ordens abertas (H3).

## 7. Critérios de parada

Pare e relate se: algum esperado do §4 ou do §5 não reproduzir; um arquivo existente de
`backend/` precisar mudar; o módulo precisar de import fora da biblioteca padrão; os testes
de arquitetura precisarem de exceção; o módulo passar de 140 linhas.

## 8. Entrega

1. Commit vermelho com os testes; depois o verde.
2. Portão completo em clone limpo no Mac e portão Linux via MCP/Docker na cabeça candidata,
   com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
3. Descrição do PR: cabeça, contagens, linhas do módulo, os 17 mutantes, desvios.
4. Copie este cartão e a autorização para os caminhos do §1. Não edite
   `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor confronta P1 a P8 com o OptionLab **fora do repositório** e registra a versão
usada e qualquer diferença em reais, por perna.

## Revisão adversarial (Claude) — GO na primeira rodada, cabeça `6a8cee4`

Parecer formado antes de ler os relatórios da skill. O portão Linux ARM64 foi executado pelo
implementador; o revisor conferiu o log e rodou também x86_64.

| Verificação do revisor | Resultado |
|---|---|
| Log Linux ARM64 do implementador | 11.303 aprovados, 16 pulados, 261 subtestes; mypy e Pyright sem erro |
| Pytest sem integração, clone limpo, Linux x86_64 | 11.303 aprovados, 16 pulados, 261 subtestes |
| `mypy backend/ --strict` e `pyright backend/`, x86_64 | 0 erros |
| Módulo | 140 linhas (teto 140); só biblioteca padrão; nenhum arquivo existente de `backend/` mudou |
| Oráculo independente do planejador, 20.000 estruturas aleatórias de 1 a 8 pernas | resultado total, por perna, entrada, extremos e equilíbrios sem nenhuma divergência |
| OptionLab 1.9.7, fora do repositório, P1 e P3 a P8 em 70.007 preços | maior diferença 1,4 × 10⁻¹⁴ (ruído de ponto flutuante do OptionLab) |
| 30 mutantes do revisor, um por vez | 30 mortos |
| Arquivos protegidos e fixtures | intactos |

O P2 ficou fora do confronto com o OptionLab porque custo fixo em reais é convenção deste
cartão; ele foi conferido pelo oráculo do planejador e à mão.

Observações, nenhuma bloqueante:

1. **Expoentes decimais muito distantes custam memória e tempo.** O módulo converte tudo
   para inteiros na menor escala. Um strike em `1E+900000000` com prêmio em centavos não
   vira `PayoffRefusal`: trava ou estoura memória. Quem chama com preços em centavos não
   chega perto disso. O próximo cartão que ligar este módulo a dados externos fixa um
   limite de escala.
2. **`except Exception` na leitura da sequência de pernas.** Converte qualquer falha de
   leitura em `PayoffRefusal`. Aceito por estar restrito a essa leitura.
3. **O módulo está no teto.** O PR08B entra em módulo próprio.

Origem: nenhum código de terceiros entrou. A definição é a do §2. O OptionLab 1.9.7 serviu
só de segunda conferência, fora do repositório, pelo implementador e pelo revisor.

Relatórios da skill lidos depois, com SHA-256 conferidos (`2863051c…0fea` e
`3b9388d8…ad4e`): sem bloqueante.
