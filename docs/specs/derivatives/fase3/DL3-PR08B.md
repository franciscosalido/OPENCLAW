# DL3-PR08B — Supercartão: a estrutura montada em parte

**Data:** 23/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `de8492c` (DL3-PR08A integrado) · **PR novo**, em rascunho
**Decisão que este cartão implementa:** autorização de Francisco de 22/11/2026 para a análise
de estruturas, item 2 (montagem parcial), na parte de análise.

## 0. Escopo

Francisco quer ver **lado a lado a estrutura planejada e a posição formada pelas execuções
confirmadas, aos preços efetivos**, e saber o que ainda depende de execução. Este cartão
entrega isso como função pura, sobre o módulo de resultado no vencimento do DL3-PR08A.

Junto com o DL3-PR08A, é o primeiro critério de sucesso que Francisco fixou: a borboleta com
resultado conhecido e a mesma borboleta montada só em parte.

**Fora deste cartão:** ligação com o motor da boleta e com o recibo; regra de cobertura
(isso é do livro de reservas, no PR07A3 e no PR07B); custos; estimativa antes do
vencimento; vencimentos diferentes; calendário; tela. Nenhuma dependência nova. Nenhum
código de terceiros.

Entram **só execuções confirmadas**. Ordem enviada, ordem aberta e pedido de cancelamento
não são execução e não aparecem na posição executada.

Todos os esperados foram calculados à mão e conferidos pelo oráculo descartável do
planejador.

## 1. Arquivos e tetos

| Arquivo | O que muda | Teto |
|---|---|---|
| `backend/derivatives/pricing/partial_position.py` | módulo novo | 90 linhas |
| `backend/derivatives/pricing/expiry_payoff.py` | parâmetro `max_legs` (§2) | 140 → 150 linhas |
| `tests/unit/derivatives/test_partial_position.py` | E1–E9 | — |
| `tests/unit/derivatives/test_expiry_payoff.py` | E10 | — |
| `docs/specs/derivatives/fase3/DL3-PR08B.md` | cópia deste cartão | — |

**Não muda:** o resto de `backend/`, fixtures, `current_state.md`, arquivos protegidos. O
módulo novo importa só a biblioteca padrão e o `expiry_payoff`.

## 2. Mudança no módulo do DL3-PR08A

Uma série pode ter execuções a preços diferentes, e cada preço vira uma perna da posição
executada. Por isso o limite de oito pernas não serve para a posição executada.

`expiry_leg_results`, `expiry_result` e `expiry_profile` ganham o parâmetro nomeado
`max_legs`: inteiro de 1 a 64, padrão 8. Com o padrão, nada muda. Fora de 1 a 64, ou sem
ser inteiro, `PayoffRefusal`. A estrutura **planejada** continua limitada a oito pernas.

## 3. Definição

**Plano.** De 1 a 8 pernas planejadas. Cada uma tem um símbolo (texto não vazio, único no
plano) e uma perna `ExpiryLeg` cujo prêmio é o **preço assinado**.

**Execução.** Símbolo, quantidade (inteiro maior que zero) e preço efetivo por unidade
(`Decimal` maior ou igual a zero). Tipo, lado e strike vêm da perna planejada do símbolo.

**Posição executada.** As execuções são agrupadas por símbolo e preço, somando as
quantidades. Cada grupo vira uma `ExpiryLeg` com o preço efetivo como prêmio. A ordem das
pernas é a ordem do plano e, dentro do símbolo, preço crescente.

**Pendente.** Por símbolo, quantidade planejada menos quantidade executada, na ordem do
plano, só quando maior que zero.

**Visão.** `partial_view(plan, executions, *, multiplier=1)` devolve um objeto imutável com:

- `planned`: o `ExpiryProfile` do plano, aos preços assinados;
- `executed_legs`: as pernas da posição executada (tupla vazia se nada executou);
- `executed`: o `ExpiryProfile` da posição executada, ou `None` se nada executou;
- `pending`: tupla de pares (símbolo, quantidade).

Nomes fixos: `PlannedLeg` (`symbol`, `leg`), `Execution` (`symbol`, `quantity`, `price`),
`PartialView`, `partial_view`. Toda entrada inválida levanta `PayoffRefusal`.

## 4. Cenários

Plano em todos, salvo indicação: a borboleta de Francisco. `C95`: compra 1 call 95 a 7,00.
`C100`: vende 2 calls 100 a 3,50. `C105`: compra 1 call 105 a 2,00. Multiplicador 1.
Perfil planejado em todos: entrada 2,00; equilíbrios 97 e 103; ganho máximo 3,00; perda
máxima −2,00.

| # | Execuções confirmadas | Posição executada | Pendente |
|---|---|---|---|
| E1 | nenhuma | `executed` é `None`; `executed_legs` vazia | `C95` 1; `C100` 2; `C105` 1 |
| E2 | `C95` 1 a 7,00; `C100` 1 a 3,50 | entrada 3,50; equilíbrio `197/2` (98,5); ganho máximo 1,50; perda máxima −3,50; nada ilimitado. Resultado em 90: −3,50; em 100: +1,50; em 110: +1,50 | `C100` 1; `C105` 1 |
| E3 | `C100` 2 a 3,50 | entrada −7,00; equilíbrio `207/2` (103,5); ganho máximo 7,00; **perda ilimitada**. Resultado em 100: +7,00; em 110: −13,00 | `C95` 1; `C105` 1 |
| E4 | `C95` 1 a 7,00; `C100` 2 a 3,50 | entrada 0,00; equilíbrios 0, 95 e 105; ganho máximo 5,00; **perda ilimitada**. Resultado em 90: 0; em 100: +5,00; em 110: −5,00 | `C105` 1 |
| E5 | `C95` 1 a 6,90; `C100` 1 a 3,60; `C100` 1 a 3,40; `C105` 1 a 2,00 | quatro pernas, com `C100` a 3,40 antes de `C100` a 3,60; entrada 1,90; equilíbrios `969/10` e `1031/10`; ganho máximo 3,10; perda máxima −1,90. Resultado em 95: −1,90; em 100: +3,10; em 105: −1,90 | nada |
| E6 | `C105` 1 a 2,00 | entrada 2,00; equilíbrio 107; **ganho ilimitado**; perda máxima −2,00 | `C95` 1; `C100` 2 |
| E7 | `C100` 1 a 3,50 e, em outra execução, `C100` 1 a 3,50 | uma perna só: vende 2 calls 100 a 3,50 (mesmo resultado de E3) | `C95` 1; `C105` 1 |

**E8 — nove preços na mesma série.** Plano de uma perna: `L`, compra 9 calls 100 a 5,00.
Nove execuções de 1 unidade, a 4,91, 4,92, até 4,99. Posição executada com nove pernas;
entrada 44,55; equilíbrio `2099/20` (104,95); ganho ilimitado; perda máxima −44,55.
Pendente: nada. Perfil planejado: entrada 45,00; equilíbrio 105; perda máxima −45,00.

**E9 — recusas.** Cada uma levanta `PayoffRefusal`: plano vazio; plano com nove pernas;
símbolo repetido no plano; símbolo vazio; execução de símbolo que não está no plano;
execução além do planejado (`C95` 2); quantidade zero; preço negativo; preço em `float`;
mais de 64 pares de símbolo e preço.

**E10 — `max_legs` no módulo de resultado.** Nove pernas com o padrão: `PayoffRefusal`,
como hoje. As mesmas nove com `max_legs=9`: aceito. `max_legs` igual a 0, 65, `True` ou
`8.0`: `PayoffRefusal`.

## 5. Testes e mutantes

Um teste por cenário, com os valores escritos à mão. Compare dinheiro como `Decimal` e
equilíbrio como `Fraction`.

Mutantes obrigatórios, um por vez, cada um derrubando ao menos um teste:

1. Posição executada pelo preço assinado em vez do preço efetivo (E5).
2. Quantidade executada trocada pela planejada (E2).
3. Lado ou tipo da execução não herdado do plano (E3).
4. Execuções do mesmo símbolo e preço não somadas (E7).
5. Execuções do mesmo símbolo a preços diferentes fundidas numa perna só (E5).
6. Ordem das pernas executadas diferente da definida (E5).
7. Pendente sem descontar o executado (E2).
8. Pendente listando símbolo já completo (E5).
9. `executed` diferente de `None` sem execução (E1).
10. Execução além do planejado aceita (E9).
11. Símbolo fora do plano aceito (E9).
12. Posição executada limitada a oito pernas (E8).
13. Plano aceitando nove pernas (E9).
14. `max_legs` padrão diferente de 8, ou limite superior ignorado (E10).
15. Perfil planejado calculado com as execuções (E5: o planejado segue 2,00 de entrada).

## 6. Critérios de parada

Pare e relate se: algum esperado do §4 não reproduzir; os testes existentes do
`test_expiry_payoff.py` precisarem mudar; outro arquivo existente de `backend/` precisar
mudar; algum import fora da biblioteca padrão e do `expiry_payoff` for necessário; os
testes de arquitetura precisarem de exceção; algum teto do §1 estourar.

## 7. Entrega

1. Commit vermelho com os testes; depois o verde.
2. Portão completo em clone limpo no Mac e portão Linux via MCP/Docker na cabeça candidata,
   com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
3. Descrição do PR: cabeça, contagens, linhas por arquivo, os 15 mutantes, desvios.
4. Copie este cartão para o caminho do §1. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor confronta E2 a E8 com o oráculo próprio e com o OptionLab fora do repositório.
