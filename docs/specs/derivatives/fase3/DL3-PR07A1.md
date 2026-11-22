# DL3-PR07A1 — Supercartão: fechamento, ocupação nunca enviada e rótulos

**Data:** 22/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `9aa7503` (Fase 3 fechada) · **PR novo**, em rascunho
**Decisões que este cartão implementa:** DP-14, DP-12 e DP-15 (registro de decisões, Revisão 2)
**Revisão 2 do cartão (22/11/2026):** rótulos de ordem do §4 decididos por Francisco. Substitui
a versão de SHA-256 `8be611f8…1563`. Fora o §4, só uma quebra de linha no §3.

## 0. Por que "A1"

Francisco autorizou o PR07A com seis frentes: origem da cobertura, os três brutos, DP-12,
DP-13, DP-14 e DP-15. Juntas elas não cabem num PR revisável, e duas delas mudam o formato
do recibo. O planejador cortou o PR07A em três, na ordem:

| Cartão | Conteúdo | Recibos oficiais |
|---|---|---|
| **PR07A1 (este)** | DP-14 (instante do fechamento), DP-12 (ocupação nunca enviada), DP-15 (rótulos) e higiene | **não mudam um byte** |
| PR07A2 | origem da cobertura; bruto assinado, executado e projetado na prévia e no recibo | mudam; âncoras refixadas |
| PR07A3 | DP-13 (relatório contraditório e evento externo) | a definir no cartão |

Este cartão **não** implementa visibilidade nem DP-13. Não crie campo novo na prévia, evento
novo no recibo nem tipo novo de evento na fita.

Todos os esperados deste cartão foram conferidos pelo planejador: os de "hoje" rodando o
`main` `9aa7503`; os de "depois" num protótipo descartável de cerca de 20 linhas, que não
será entregue. Com o protótipo, os 430 testes do pacote passam sem alteração e as três sessões
oficiais saem idênticas byte a byte.

## 1. Arquivos e tetos

| Arquivo | O que muda | Linhas hoje → teto |
|---|---|---|
| `backend/derivatives/ticket/guards.py` | regra nova em `check_deadlines` (§2) | 92 → 96 |
| `backend/derivatives/ticket/engine.py` | janela de envio única (§2) e liberação ao parar (§3) | 393 → 412 |
| `backend/derivatives/ticket/state.py` | dois dicionários de rótulos (§4) | 144 → 150 |
| `scripts/derivatives_ticket_replay.py` | linha final do log com rótulo (§4) | 220 → 222 |
| `tests/unit/derivatives/ticket/test_engine.py` | F1–F5, F2b, R1–R6 | — |
| `tests/unit/derivatives/ticket/test_guards.py` | F7 | — |
| `tests/unit/derivatives/ticket/test_paper_venue.py` | F6 | — |
| `tests/unit/derivatives/ticket/test_state_receipt_reviewer.py` | L1–L3 no lugar dos dois testes de rótulo atuais | — |
| `tests/unit/derivatives/test_ticket_replay_script.py` | L4, H2, H3 | — |
| `docs/specs/derivatives/fase3/DL3-PR07A1.md` | cópia deste cartão | — |
| `docs/specs/derivatives/fase3/DECISOES_PRODUTO_DP01-DP19_R2.md` | cópia byte a byte (H1) | — |

**Não mudam:** `sequencing.py`, `paper_venue.py`, `session.py`, `receipt.py`, `models.py`,
`gate.py`, `replay.py`, `venue.py`, `digest.py`, `trigger.py`, fixtures, `current_state.md`,
arquivos protegidos. Produção do PR: no máximo **45 linhas** novas ou alteradas.

## 2. DP-14 — instante do fechamento

**Hoje:** no instante exato do fechamento, com prazo de envio e validade iguais a ele,
`check_deadlines` aceita. A decisão humana é gasta, a ordem sai e a venue rejeita.

**Regras**

- **G1.** `check_deadlines` recusa com `DeadlineRefusal` quando `now >= draft.order_validity`.
  A ordem das quatro conferências fica: prazo de envio vencido; prazo depois da validade;
  **validade encerrada (nova)**; validade que a venue não garante.
- **G2.** O motor tem uma única condição de "janela de envio aberta":
  `now <= send_deadline` **e** `now < order_validity`. Ela vale em `_drive`, antes de cada
  envio, e em `_destination`. O motor nunca chama `venue.submit` com a janela fechada.
- **G3.** A venue não muda: ela já rejeita envio com `now >= fechamento`. Só ganha teste.
- **G4.** O instante exato do **prazo de envio** continua permitido (`now == send_deadline`
  envia). Os testes atuais disso não podem mudar.

**Cenários.** `NOW` = 14:00:00, `CLOSE` = 21:00:00, do `test_guards`. Boleta de referência
do `Session` (compra A 10 a 1,00; vende B 10 a 1,50), com `send_deadline = order_validity =
CLOSE`. Cotações de abertura de A em `CLOSE − 4 s` e de B em `CLOSE − 3,5 s`. As decisões
precisam de `expires_at` depois de `CLOSE`: emita com `issue`, não com `Session.dec`.

| # | Ação | Hoje | Esperado depois |
|---|---|---|---|
| F1 | `confirm` em `CLOSE − 1 µs` | aceito | aceito; boleta `WORKING`; `T1:A:1` `LIVE`; 1 envio; recibo `preview confirm start venue_live` |
| F2 | `confirm` em `CLOSE` | aceito; decisão gasta; `T1:A:1` `REJECTED`; boleta `STOPPED` | `DeadlineRefusal`; boleta `DRAFT`; sem ordens; 0 envios; recibo só `preview`; a mesma decisão ainda é consumível direto no `DecisionLedger` |
| F2b | F2 com a boleta de desmontagem (posição A = +10, B = −10; vende A, compra B) e uma segunda boleta igual | aceito | `DeadlineRefusal`; 0 envios; `ReservationBook.admissible` do plano da segunda boleta não recusa |
| F3 | `confirm` em `CLOSE + 1 µs` | `DeadlineRefusal` | igual a hoje; boleta `DRAFT`; 0 envios; decisão não gasta |
| F4 | `confirm` e `pause` em `CLOSE − 3 s`; cotação de A com ask 1,00 em `CLOSE − 2 s`; cotação de abertura de B em `CLOSE − 1 s`; `resume` com decisão em `CLOSE` | 2 envios; `T1:B:1` `REJECTED`; recibo termina em `resume venue_rejected stop` | **1 envio**; ordens só `T1:A:1` `FILLED`; boleta `STOPPED`; recibo `preview confirm start venue_live pause venue_fill resume stop` |
| F5 | F4 com `resume` em `CLOSE − 1 µs` | 2 envios; `T1:B:1` `LIVE` | igual a hoje: 2 envios; `T1:B:1` `LIVE` com 10 a 1,50; boleta `WORKING` |
| F6 | `PaperVenue(CLOSE).submit` de uma ordem válida em `CLOSE − 1 µs`, `CLOSE` e `CLOSE + 1 µs` | `venue_live`, `venue_rejected`, `venue_rejected` | igual a hoje |
| F7 | `check_deadlines` direto: (a) `now = CLOSE − 1 µs`; (b) `now = CLOSE`; (c) `now = CLOSE + 1 µs`, os três com prazo e validade em `CLOSE`; (d) `now` = prazo = 15:00, validade `CLOSE` | (b) aceita | (a) aceita; (b) recusa; (c) recusa; (d) aceita |

## 3. DP-12 — ocupação de compra nunca enviada

**Hoje:** a boleta ocupa todas as suas recompras ao confirmar. Se ela para sem nunca enviar
uma delas, a ocupação fica presa até o fim da sessão e bloqueia outra boleta.

**Regra R.** Quando a boleta entra em `STOPPED`, cada perna de **compra** do plano que
nunca teve ordem tem a ocupação liberada no livro de reservas. Vale nos dois caminhos que
levam a `STOPPED`: pelo laço de envio e pela conciliação. Nenhum outro estado libera:
`UNCERTAIN`, `WORKING` (pausada ou não) e conta bloqueada por divergência mantêm a ocupação.

- `ReservationBook.settle_buy` já faz o que a regra pede (conserva só o executado, dentro da
  seção crítica do livro). Para perna nunca enviada o executado é zero. Por isso
  `sequencing.py` não muda. Se você concluir que precisa mudar, **pare e relate**.
- Sem evento novo no recibo: a parada já está registrada e a perna não tem ordem.
- Compra enviada, parcial ou incerta continua como hoje.

**Cenários R1, R2, R3, R5 e R6 — mesma montagem.** Posição da conta `sim`: A = +10,
B = −10, C = −10, D = +10; pares `(A, B)` e `(D, C)`. Cotações de abertura do `Session` para
A e B; de C e D em 14:00:01, com o padrão do `Session` para série que não é A (bid 1,45;
ask 1,55).

- `T1`: compra C 10 a 1,50; compra B 10 a 1,50; vende D 10 a 1,00; vende A 10 a 1,00;
  líquido 10; bruto 50; prazo 15:00; validade `CLOSE`.
- `T2` e `T3`: boleta de desmontagem do `Session` (vende A 10 a 1,00; compra B 10 a 1,50).
- Evento `timeout` de `submit` às 14:00:02, sequência 3. `T1` confirma às 14:00:02.

| # | Passos | Hoje | Esperado depois |
|---|---|---|---|
| R2 | `timeout` **não registrado**; `T1` confirma; `T2` confirma às 14:00:02 | `T1` `UNCERTAIN` com só `T1:C:1` enviada; `T2` recebe `EngineRefusal`, decisão não gasta | igual a hoje |
| R5 | no mesmo ponto, `admissible` do plano de `T2` | recusa | **recusa** (incerta não libera) |
| R1 | `T1.reconcile("T1:C:1")` às 14:00:03; `T2` confirma com decisão nova às 14:00:03; cotação de B com ask 1,50 às 14:00:04; cotação de A com bid 1,00 às 14:00:05 | `T1` `STOPPED`, `T1:C:1` `REJECTED`, conta desbloqueada; **`T2` recebe `SequenceRefusal`** | `T1` igual; **`T2` aceita**; `T2:B:1` com 10; no fim `T2` `COMPLETED`; envios da sessão, na ordem: `T1:C:1` 10, `T2:B:1` 10, `T2:A:1` 10 |
| R3 | depois de `T2` confirmar em R1, `T3` confirma às 14:00:03 | — | `SequenceRefusal`; decisão de `T3` não gasta |
| R6 | `timeout` **registrado**; `T1` confirma; `T1.reconcile("T1:C:1")` às 14:00:03 (fica `WORKING`, pausada, `T1:C:1` `LIVE`); cancela `T1:C:1` às 14:00:03; cotação de C com ask 1,60 e cotações de abertura de A e B às 14:00:04; `T2` confirma às 14:00:05 | `T1` `STOPPED` pelo laço de envio, recibo terminando em `pause request_cancel venue_cancelled stop`; **`T2` recebe `SequenceRefusal`** | `T1` igual; **`T2` aceita**, `T2:B:1` `LIVE` |

**Cenário R4 — parcial preserva o executado.** Posição A = +10, B = −10. `T1` é a boleta
de desmontagem e confirma às 14:00:02. Cotação de B com ask 1,50 e tamanho 4 às 14:00:03;
cancela `T1:B:1` às 14:00:03; cotação de B com ask 1,60 e de A com bid 1,00 às 14:00:04.
Aí `T1` está `STOPPED`, com `T1:B:1` `CANCELLED` (4 executadas) e `T1:A:1` `FILLED` (4).
Uma segunda boleta de desmontagem com quantidade 6 (líquido 3, bruto 15, prazo 15:00,
validade `CLOSE`) confirma às 14:00:05 e é aceita. Com quantidade 7 (líquido 3,50, bruto
17,50) recebe `SequenceRefusal`. Isso já vale hoje e tem de continuar valendo.

## 4. DP-15 — rótulos em português

**Hoje:** `LABELS_PT` junta os dois enums. `EXPIRED` e `UNCERTAIN` existem nos dois e
recebem o mesmo texto.

**Regra.** Dois dicionários imutáveis em `state.py`, `TICKET_LABELS_PT` e
`ORDER_LABELS_PT`, um por enum. `LABELS_PT` deixa de existir. Os códigos internos não mudam.
**Os textos abaixo estão decididos por Francisco (22/11/2026). Use-os exatamente como estão,
com a mesma grafia e os mesmos acentos.**

| Estado da boleta | Rótulo | Estado da ordem | Rótulo |
|---|---|---|---|
| `DRAFT` | Proposta | `PENDING_SEND` | Envio pendente |
| `ARMED` | Engatilhada | `LIVE` | Ordem aberta |
| `TRIGGERED` | Gatilho atingido | `PARTIAL` | Ordem parcialmente executada |
| `CONFIRMED` | Confirmada | `FILLED` | Ordem totalmente executada |
| `WORKING` | Em execução | `CANCEL_REQUESTED` | Cancelamento solicitado |
| `COMPLETED` | Concluída | `CANCELLED` | Ordem cancelada |
| `STOPPED` | Parada | `EXPIRED` | Ordem expirada |
| `DENIED` | Negada | `REJECTED` | Ordem rejeitada |
| `EXPIRED` | Boleta expirada | `UNCERTAIN` | Ordem em estado incerto |
| `UNCERTAIN` | Boleta em estado incerto | | |

Motivos de Francisco para os quatro rótulos de ordem que mudaram em relação ao padrão:

- `LIVE` é **"Ordem aberta"**. "Ordem viva" não serve: dentro do motor, "viva" já nomeia um
  grupo de cinco estados, que inclui cancelamento solicitado e estado incerto.
- `PARTIAL` é **"Ordem parcialmente executada"** e `FILLED` é **"Ordem totalmente
  executada"**, para separar 4 de 10 de 10 de 10 só pelo texto.
- `REJECTED` é **"Ordem rejeitada"**. "Negada" fica reservado à decisão humana sobre a boleta.
- A boleta de montagem continua **"Concluída"**: as ordens podem estar totalmente executadas
  e a posição da estratégia seguir em aberto.

**O rótulo descreve o estado atual; a quantidade conta o que aconteceu.** Uma ordem de 10
com 4 executadas mostra "Cancelamento solicitado" depois do pedido. Se mais 2 executarem
antes da confirmação, ela termina como "Ordem cancelada", com 6 de 10 executadas. Nenhum
rótulo embute quantidade. Esse comportamento já existe no motor e não muda neste cartão.

A linha final do log da linha de comando passa de `T1: COMPLETED` para
`T1: Concluída (COMPLETED)`. **O `resumo.json` não muda**: ele guarda códigos.

| # | Teste |
|---|---|
| L1 | os dois dicionários conferidos estado por estado contra a tabela, escrita à mão no teste |
| L2 | o rótulo de `EXPIRED` e o de `UNCERTAIN` diferem entre boleta e ordem |
| L3 | `state.py` não tem mais `LABELS_PT`, e cada dicionário cobre o enum inteiro |
| L4 | log das três sessões oficiais: `T1: Concluída (COMPLETED)` em `calmo`; `T1: Parada (STOPPED)` em `leilao`; `T1: Parada (STOPPED)` e `T2: Proposta (DRAFT)` em `rapido` |

## 5. Higiene

- **H1.** Copie `reports/fase03/DECISOES_PRODUTO_DP01-DP19_2026-11-22_R2.md` para
  `docs/specs/derivatives/fase3/DECISOES_PRODUTO_DP01-DP19_R2.md`, byte a byte. SHA-256:
  `2c0eb6a1d3cc1dbe59fcd5ae28331e06cf8c0c2a9276aa79a54115b0a24300a9`. Não edite a Revisão 1.
- **H2.** `tests/unit/derivatives/test_ticket_replay_script.py`, linha 287: quebrar para
  no máximo 100 colunas.
- **H3.** Três testes para recusas que já funcionam e não têm teste. Nenhuma linha de
  produção muda por causa deles.

| # | Entrada | Esperado (já vale hoje) |
|---|---|---|
| H3a | `--out <tmp>/x/..`, com `x` ausente | código 2; `<tmp>` continua vazio |
| H3b | `<tmp>/link` é link para `<tmp>/missing`, que não existe; `--out <tmp>/link/novo` | código 2; `<tmp>` contém só `link`; `missing` não foi criado |
| H3c | roteiro de `calmo` com `decision_ttl_s` igual a `10**18` | código 2; nada publicado |

## 6. O que não pode mudar

1. As quatro âncoras de recibo das sessões oficiais.
2. Os sete arquivos das sessões oficiais, byte a byte:

| Arquivo | SHA-256 |
|---|---|
| `calmo/recibo_T1.jsonl` | `ea940b02293901d9ce41cbc5d16ec3ab992c0d3454750fb26fa727f0efb5e125` |
| `calmo/resumo.json` | `887ee7dcace0e16f733d47651aed6970653551106e807ae84662531baf8e4ab0` |
| `leilao/recibo_T1.jsonl` | `458497b9f6738ec27a619eb7201ee3363d406c6837b6bb396f9ff4ee1387394b` |
| `leilao/resumo.json` | `68e439f8df6f997ff226d56eacdf027f757d65b0826c59e4416b606a998dc9fe` |
| `rapido/recibo_T1.jsonl` | `9af6c056850fbf4bcb288a9f2438e32101b45fb3d7468d3c7dd8c5e5beb09428` |
| `rapido/recibo_T2.jsonl` | `d2a17c541e2820a978e91b18b4252272009cb2aa8a3dc984c3123fb7a6bf8328` |
| `rapido/resumo.json` | `7be5ef78b5822548b914a5c78ad7e8daa9e2c9f365fd656093101b4d645e7673` |

3. Os testes existentes do pacote da boleta, do script e da arquitetura. Só dois mudam
   por desenho: os dois testes de rótulo de `test_state_receipt_reviewer.py`, trocados por
   L1–L3. Qualquer outro teste existente que precise mudar: **pare e relate**.

## 7. Testes e mutantes

Um teste por linha das tabelas dos §§2 a 5, com o nome do cenário. Onde a tabela diz
"envios", conte as chamadas a `venue.submit`. Onde diz "decisão não gasta", consuma a mesma
decisão direto no `DecisionLedger` e veja que funciona.

Mutantes obrigatórios, um por vez, cada um derrubando ao menos um teste:

1. `check_deadlines` sem a regra nova (F2, F7).
2. A regra nova com `>` no lugar de `>=` (F2).
3. A regra nova conferida depois de consumir a decisão (F2).
4. A regra nova conferida depois de ocupar o livro (F2b).
5. `_drive` enviando com a validade encerrada (F4).
6. `_destination` ignorando a validade (F4: a boleta ficaria `WORKING`).
7. Janela de envio com `now < send_deadline` (os testes atuais do prazo exato).
8. Janela de envio fechando antes da validade (F1, F5).
9. Sem liberação ao parar (R1, R6).
10. Liberação só no caminho da conciliação (R6).
11. Liberação só no caminho do laço de envio (R1).
12. Liberação também em `UNCERTAIN` (R5).
13. Um dicionário de rótulos único (L2).
14. Sem a recusa de destino terminado em `..` (H3a).
15. Sem a recusa de pai que é link quebrado (H3b).
16. Sem o tratamento do prazo que estoura a data (H3c).

## 8. Critérios de parada

Pare e relate se: algum "hoje" das tabelas não reproduzir no `main` `9aa7503`; algum
arquivo do §6 mudar; um teste existente fora dos dois de rótulo precisar mudar;
`sequencing.py` ou outro arquivo da lista "não mudam" precisar mudar; algum teto do §1
estourar; a regra do gate nos testes de arquitetura precisar de exceção.

## 9. Entrega

1. Commit vermelho com os testes; depois o verde.
2. Portão completo em clone limpo no Mac, mais `mypy --strict` no script. O revisor roda o
   Linux x86_64.
3. Descrição do PR: cabeça, contagens, linhas por arquivo, os 16 mutantes, desvios.
4. Copie este cartão e a Revisão 2 do registro para os caminhos do §1. Não edite
   `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.
