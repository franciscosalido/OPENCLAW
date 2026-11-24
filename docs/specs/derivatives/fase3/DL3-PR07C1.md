# DL3-PR07C1 — Supercartão: cota do plano na proteção disputada

**Data:** 24/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `429ff92` (DL3-PR07A6 integrado)
**PR novo**, em rascunho
**Origem:** pendência registrada na revisão do DL3-PR07B2 e mantida no estado atual: «a
repartição do plano não é cota no livro. Quando duas vendas da mesma boleta usam a mesma
proteção, a primeira pode tomar mais do que o plano lhe destinou e a estrutura termina
parcial.» Regra já em vigor desde o DL3-PR07B2: cada unidade comprada protege uma só
vendida.

## 0. Escopo

**O que acontece hoje.** Fatos conferidos no `main`, com o exemplo do §3:

- O plano decide quanto cada venda toma de cada proteção, mas guarda só os pares (venda,
  proteção). A quantidade se perde.
- No livro, o teto de uma venda numa proteção é o saldo comprado e o total da perna. Se a
  proteção disputada executa primeiro, a venda que chega antes leva tudo.
- No exemplo: B deveria tomar 5 de C e levou 10. D ficou sem proteção, nunca foi enviada, e
  a boleta parou com 44,00 executados de 46,00 e 5 de A sobrando. Não houve venda
  descoberta.

**O que este cartão entrega.**

1. O plano passa a guardar a quantidade de cada dependência.
2. No livro, quando **outra venda do plano também usa a proteção**, a venda fica limitada à
   parte que o plano lhe destinou naquela proteção.
3. Proteção que só uma venda usa segue como hoje: a venda pode tomar dela até o total da
   perna.

**O que este cartão não faz.**

- Não muda o motor, o recibo, a prévia, o resumo criptográfico nem a ordem de envio.
- Não muda o formato de `dependencies`.
- Não reparte de novo a parte de uma venda que foi cancelada ou recusada.
- Não muda a repartição do plano: continua na ordem assinada das compras.
- Borboleta, trava, zeragem e venda com sobra autorizada não mudam de comportamento.

Nenhuma dependência nova.

## 1. Arquivos e tetos

| Arquivo | O que muda | Teto (hoje) |
|---|---|---|
| `backend/derivatives/ticket/sequencing.py` | `quotas` e `quota` no plano; teto no livro | 480 (462) |
| `tests/unit/derivatives/ticket/test_sequencing.py` | Q1 a Q6 | — |
| `tests/unit/derivatives/ticket/test_engine.py` | Q7 | — |
| `docs/specs/derivatives/fase3/DL3-PR07C1.md` | cópia deste cartão | — |

**Não muda:** `engine.py`, `session.py`, os demais módulos da boleta, o script, roteiros e
fitas, `current_state.md`, arquivos protegidos. Linhas novas com até 100 colunas.

**Nenhum teste existente muda de resultado.** Em especial, segue passando
`test_b2_all_orders_share_signed_sale_limit_across_sources`: com uma só venda, a proteção
não é disputada. As quatro âncoras e os recibos oficiais não mudam.

## 2. Regra

**Plano (`LegPlan`).** Campo novo, depois de `dependencies`:

- `quotas: tuple[int, ...]` — uma quantidade por dependência, na mesma ordem. É o que a
  repartição tomou naquele passo; na zeragem, a quantidade da venda.

Método novo:

- `quota(leg, source) -> int` — teto da venda naquela proteção.
  - Se **nenhuma outra venda** do plano usa `source`: a quantidade da perna.
  - Senão: a quantidade que o plano destinou ao par (venda, proteção).

**Livro.** Na capacidade de uma venda, o teto passa a ser o menor entre três:

1. o saldo livre da proteção, como hoje;
2. a quantidade da perna menos o que a venda já ocupa em todas as proteções, como hoje;
3. `quota(leg, source)` menos o que a venda já ocupa **nesta** proteção (vivo mais
   executado).

Saldo liberado por cancelamento confirmado volta para a mesma parte. Dentro da parte de
cada uma, vale quem chega primeiro.

## 3. Cenários

Foto da conta `sim`: A, B, C e D zeradas; A protege B, C protege B, C protege D.
Boleta, nesta ordem: compra 10 A a 2,00; vende 15 B a 1,20; compra 10 C a 0,60; vende 5 D a
0,40; `net_limit` 6; `gross_cap` 46.
Plano: B toma 10 de A e 5 de C; D toma 5 de C. C é disputada; A não é.

### 3.1 Plano e livro (`test_sequencing.py`)

**Q1 — o plano guarda as quantidades.**

| Plano | `dependencies` | `quotas` | `quota` |
|---|---|---|---|
| boleta acima | (B,A), (B,C), (D,C) | `(10, 5, 5)` | B em A: 15; B em C: 5; D em C: 5 |
| mesmas pernas na ordem C, D, A, B | (D,C), (B,C), (B,A) | `(5, 5, 10)` | — |
| asa já existente: `wing_draft(6, net="5.80", gross="20.20")` | — | `(5, 1)` | B em A: 6; B em C: 6 |
| zeragem já existente: `zeroing_draft(7)`, A com 7 e B com 2 | (A,A) | `(7,)` | A em A: 7 |

**Q2 — a proteção disputada respeita a parte de cada venda.** Compra de 10 C executada.

| Passo | B em C | D em C | B em A |
|---|---|---|---|
| início | 5 | 5 | 0 |
| reserva de 6 para B em C | recusa «reserva indisponível» | | |
| reserva de 5 para B em C | 0 | 5 | |
| reserva de 5 para D em C | | 0 | |
| compra de 10 A executada | | | 10 |
| reserva de 10 para B em A | 0 | | 0 |

**Q3 — a asa própria primeiro não invade a disputada.** Compras de 10 A e 10 C executadas.
Reserva de 10 para B em A → B em A 0, B em C 5, D em C 5. Reserva de 5 para B em C → B em C
0, D em C 5. **Já passa no `main`**; protege a conta do ocupado por proteção (mutante 6).

**Q4 — o liberado volta para a mesma parte.** Compra de 10 C executada. Reserva de 5 para B
em C; execução de 2; cancelamento confirmado dos 3 → B em C 3, D em C 5.

**Q5 — compra parcial: quem chega primeiro, dentro da sua parte.** Compra de 5 C executada
→ B em C 5, D em C 5. Reserva de 5 para D → B em C 0. Mais 5 de C executados → B em C 5, D
em C 0. **Já passa no `main`**; é guarda de regressão.

**Q6 — sem disputa, só o total da perna limita.** O cenário do teste existente citado no
§1: asa com venda de 6 B, 5 de A e 5 de C comprados; reserva de 5 em C primeiro → sobra 1
em A. **Já passa no `main`**; se o teste existente já o cobre por inteiro, basta declarar.

### 3.2 Motor (`test_engine.py`)

**Q7 — a estrutura fecha quando a asa disputada executa primeiro.**

| t | Passo | Esperado | Hoje |
|---|---|---|---|
| 1 | cotações: C 0,55/0,65; D 0,35/0,45; A 1,95/2,05; B 1,15/1,25 | — | — |
| 2 | confirmação | `T1:A:1` e `T1:C:1` vivas | igual |
| 3 | C 0,55/0,60 | C executada; saem `T1:B:1` de 5 e `T1:D:1` de 5, as duas com proteção C | sai só `T1:B:1`, de 10 |
| 4 | A 1,95/2,00 | sai `T1:B:2` de 10, proteção A; 5 ordens ao todo | `T1:B:2` de 5; 4 ordens |
| 5–6 | B 1,20/1,30; D 0,40/0,50 | `COMPLETED`; bruto executado `46.00` | `STOPPED`; `44.00` |

## 4. Evidência do planejador

- **Fatos de hoje.** A coluna «Hoje» do Q7 foi observada no `main` `429ff92`.
- **Primeira tentativa descartada.** Aplicar a parte do plano a toda proteção quebrava o
  teste existente do §1 e piorava o caso de uma venda só: unidades compradas ficavam
  paradas sem ninguém mais para usá-las. Por isso a regra vale só na proteção disputada.
- **Protótipo descartável:** `sequencing.py` com 475 linhas (13 a mais). `mypy --strict`
  limpo em `backend/`; `pyright` limpo no pacote da boleta.
- **Portão completo no protótipo** (sem `tests/integration`): 11.567 aprovados, 16 pulados,
  a mesma contagem do `main`. Nenhum teste existente mudou; as âncoras passam.
- **Cenários:** Q1 a Q7 passam no protótipo. No `main`, Q1, Q2, Q4 e Q7 falham; Q3, Q5 e Q6
  já passam.
- **Mutantes:** 13 defeitos plantados, um por vez, todos detectados (§5).

## 5. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, quem derrubou no
protótipo.

1. O livro não aplica a cota (Q2, Q4, Q7).
2. A cota vale mesmo sem disputa (Q1, Q6 e o teste existente do §1).
3. A cota nunca vale: toda proteção tratada como sem disputa (Q1, Q2, Q4, Q7).
4. A cota soma todas as vendas da proteção (Q1, Q2, Q4, Q7).
5. A cota soma todas as proteções da venda (Q1, Q2, Q4, Q7).
6. O ocupado conta todas as proteções da venda (Q3).
7. O ocupado ignora o executado (Q4).
8. O ocupado ignora o saldo vivo (Q2).
9. O plano grava o que faltava, não o que tomou (Q1).
10. A zeragem não grava quantidade (Q1).
11. As quantidades saem fora da ordem das dependências (Q1).
12. O total da perna deixa de limitar (Q6 e testes existentes).
13. O ocupado conta ordens de outras boletas (testes existentes).

## 6. Critérios de parada

Pare e relate se:

- algum esperado do §3 não reproduzir, inclusive a coluna «Hoje» do Q7 na base;
- qualquer teste existente mudar de resultado;
- alguma âncora ou recibo de sessão oficial mudar;
- for preciso mudar arquivo de produção fora do §1, ou o teto estourar;
- for preciso mudar o formato de `dependencies` ou o motor.

## 7. Entrega

1. Commit vermelho com os testes; depois o verde. Q3, Q5 e Q6 nascem verdes: declare isso.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
   `tests/integration` só no contêiner isolado, nunca no Mac com banco vivo.
3. Descrição do PR: cabeça, contagens, linhas de `sequencing.py`, os 13 mutantes, as âncoras
   e os recibos oficiais comparados byte a byte, desvios.
4. Copie este cartão para o caminho do §1. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda os cenários do
seu protótipo contra os módulos entregues.

## 8. Depois deste cartão

A fila do `current_state.md`: desmontagem e zeragem de borboleta; apresentação da montagem
parcial e do projetado depois de cancelamento humano; repetir, completar e ajustar
estruturas.

## Revisão adversarial (Claude) — GO na primeira rodada, cabeça `ee572b6`

Pela regra de processo de Francisco, o revisor **não executou a suíte, a tipagem nem os
mutantes** desta cabeça. Leu o diff, conferiu as evidências pelo SHA-256 e rodou os cenários
do seu protótipo, escrito antes do cartão, mais duas sondas próprias.

| Verificação | Resultado | Quem |
|---|---|---|
| Suíte sem integração, Linux x86_64 e macOS | 11.574 aprovados, 16 pulados, 261 subtestes nos dois | implementador; logs conferidos |
| mypy estrito e Pyright, nos dois sistemas | 0 erros | implementador; logs conferidos |
| Commit vermelho `aacd5f0` antes do verde | Q1, Q2, Q4 e Q7 falham na base; Q3, Q5 e Q6 já passavam, como o cartão previa | implementador; log conferido |
| Testes focais antigos | 623 com resultado idêntico por nome; 7 novos aprovados | implementador; log conferido |
| 13 mutantes do §5 e 1 adicional, nos dois sistemas | todos detectados | implementador; logs conferidos |
| Integração | só no contêiner Linux isolado: 31 aprovados, 206 pulados | implementador; evidência conferida |
| Manifesto de 108 evidências (`718d2245…b0de`) e hashes dos dois relatórios | conferem | revisor (18 arquivos) e Francisco (todos, no Mac) |
| `DIFF.patch` das evidências aplicado sobre a base | mesma árvore da cabeça | revisor |
| Diff | quatro arquivos; `sequencing.py` com 477 linhas (teto 480) | revisor |
| Âncoras, recibos e resumos das sessões oficiais | iguais entre base e cabeça | implementador; log conferido |
| Cópia do cartão | igual à publicada | revisor |
| 7 cenários do protótipo do planejador contra o módulo entregue | todos aprovados | revisor |
| 2 sondas do revisor (abaixo) | aprovadas | revisor |

A implementação é equivalente à do protótipo do planejador. Uma diferença, aceita:
`quota` recusa com «proteção ausente no plano» quando a proteção consultada não é da venda.
O livro já devolvia zero antes de chegar a essa consulta; a recusa protege a chamada direta.

Sondas do revisor na cabeça:

1. Duas boletas com o mesmo plano na mesma conta: cada uma tem as suas partes; a reserva de
   uma não consome a parte da outra.
2. Reserva parcial dentro da parte (3 de 5): sobram 2; proteção que não é da venda dá zero.

Limite desta revisão: sem mutantes próprios do revisor nesta cabeça.

Relatórios da skill lidos depois de formado o parecer, com SHA-256 conferidos
(`054fee48…d222` e `36d88eeb…70f7`): sem bloqueante; nenhuma simplificação qualificada.

