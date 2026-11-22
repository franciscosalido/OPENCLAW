# DL3-PR05b — Supercartão: o motor da boleta

**Data:** 22/11/2026 · **Autor:** Claude · **Para:** Codex · **Base:** `main` = `e48e8ac`
**Branch:** `feat/dl3-pr05b-ticket-engine` · **PR em rascunho**
**Substitui** a parte de `engine.py` da seção "DL3-PR05" de `DL3_CARDS.md`. As "Regras
comuns" daquele arquivo valem. Leia antes: `current_state.md`, ADR-0024 (G1 a G5) e os
cartões `DL3-PR03`, `DL3-PR04` e `DL3-PR05a` no repositório.

---

## 0. Como este cartão foi conferido

O motor só cola peças que já existem em `main`. Por isso conferi contra `e48e8ac`, chamando
as peças reais na ordem de cada cenário:

- plano de pernas, exposição e limites assinados da boleta de referência e da desmontagem;
- nível da trava de mercado em cada horário citado (14:00:02, :03, :04, :05, :06, :07, :08,
  :10 e :12);
- relatórios da venue para as fitas de S01, S03, S04, S05, S07, S08, S09, S15, S19, S21 e
  S22, e o que `poll` devolve depois;
- quantidade disponível no livro de reservas em S01, S04, S08 e S09;
- cada transição de boleta e de ordem usada aqui, na tabela de `state.py`;
- os textos de recusa das peças existentes citados no §6.

O que **não** existe para conferir é a cola: a ordem das checagens do motor e o estado final
da boleta. Isso está escrito como regra no §4, e os estados finais do §6 seguem dessas
regras. Esperado que não reproduzir: **pare e relate**.

## 1. Objetivo

`TicketEngine`: uma boleta, do rascunho ao fim, obedecendo a G1–G5 da ADR-0024 contra a
venue simulada. O motor não decide o que operar e não inventa preço: cumpre a versão que o
humano confirmou.

## 2. Arquivos, limites e não-objetivos

| Arquivo | Mudança |
|---|---|
| `backend/derivatives/ticket/engine.py` | novo, **≤ 400 linhas** |
| `backend/derivatives/ticket/state.py` | **só** dois membros novos em `Event`: `PAUSE = "pause"` e `RESUME = "resume"`. Nenhuma linha nas tabelas de transição |
| `tests/unit/derivatives/ticket/test_engine.py` e fixtures | novos |
| `tests/architecture/test_ticket_boundaries.py` | regras do §7 |

Não-objetivos: CLI, tela, custos e emolumentos (custo conhecido = 0), preenchimento
automático de preço pelo livro, zerar posição comprada, borboleta, persistência do recibo,
autenticação real. Nenhuma outra mudança em módulos existentes.

Se o motor não couber em 400 linhas, pare e relate a contagem. Não comprima linhas.

## 3. Interface

```python
class EngineRefusal(ValueError): ...

class AccountHalts:                      # um objeto por sessão, compartilhado entre motores
    def blocked(self, account: str) -> bool: ...

class TicketEngine:
    def __init__(self, ticket: str, position: Position, *, venue: ExecutionVenue,
                 book: BookView, reservations: ReservationBook, ledger: DecisionLedger,
                 halts: AccountHalts, receipt: Receipt, config: TicketSimConfig) -> None: ...
    state: TicketState                   # começa em DRAFT
    preview: Preview | None
    orders: Mapping[str, OrderState]     # por order_id
    paused: bool

    def propose(self, draft: TicketDraft, now: datetime) -> None: ...
    def edit(self, field: FieldRef, value: object, now: datetime) -> None: ...
    def refresh(self, suggestion: MarketSuggestion, now: datetime) -> None: ...
    def arm(self, spec: TriggerSpec, decision: HumanDecision, now: datetime) -> None: ...
    def disarm(self, decision: HumanDecision, now: datetime) -> None: ...
    def discard(self, decision: HumanDecision, now: datetime) -> None: ...
    def confirm(self, decision: HumanDecision, now: datetime) -> None: ...
    def cancel(self, order_id: str, decision: HumanDecision, now: datetime) -> None: ...
    def pause(self, now: datetime) -> None: ...
    def resume(self, decision: HumanDecision, now: datetime) -> None: ...
    def reconcile(self, order_id: str, now: datetime) -> None: ...
    def on_reports(self, reports: Sequence[VenueReport], now: datetime) -> None: ...
    def on_market(self, event: ReplayEvent) -> None: ...
```

- `order_id` = `"{ticket}:{símbolo}:{n}"`, com `n` começando em 1 por símbolo.
- Identificador de execução para o livro de reservas = `"{order_id}#{k}"`, com `k` = 1, 2, …
  na ordem dos relatórios de execução daquela ordem.
- O motor **não** chama `venue.advance`. Quem dirige a sessão (teste ou CLI) faz, para cada
  evento, nesta ordem: `book.advance(ev)`; `reports = venue.advance(ev)`; para cada motor,
  `on_reports` com os relatórios das ordens dele e `now = ev.ts`; depois `on_market(ev)`.

## 4. Regras

**R1 — Propor.** `propose` vale uma vez, em `DRAFT` sem prévia. `plan_legs(draft, position)`
tem de aceitar. A prévia usa `partial_exposure(draft)`. Grava `PREVIEW` no recibo.

**R2 — Editar e atualizar.** `edit` e `refresh` só em `DRAFT` ou `TRIGGERED`. Cada versão
nova refaz o plano e a prévia e grava novo `PREVIEW`. `refresh` que não muda nada não grava.

**R3 — Decisão por último.** Em toda ação com decisão, `ledger.consume` é a **última**
checagem. Ação recusada antes disso não gasta o `nonce`.

**R4 — Confirmar.** Checagens, nesta ordem; a primeira que falhar levanta `EngineRefusal`
(ou a recusa própria da peça) e nada muda:

1. estado em `DRAFT` ou `TRIGGERED`;
2. boleta não pausada;
3. conta não bloqueada em `halts`;
4. `check_deadlines(draft, now, venue)`;
5. `assess(draft.legs, book, now, config)` diferente de `BLOCKED` (`CAUTION` passa);
6. `within_signed_limits(draft, (), primeira perna do plano, known_costs=0)`;
7. `ledger.consume(decision, action=EXECUTE, ticket, now, preview)`.

Passando: `CONFIRM`, `START`, e envio de **todas as pernas de compra**, na ordem do plano.

**R5 — Antes de cada envio.** Imediatamente antes de qualquer `venue.submit`, o motor
revalida: estado `WORKING`; não pausada; conta não bloqueada; nenhum cancelamento humano
nesta boleta; `now <= send_deadline`; `assess` de **todas as pernas da boleta** diferente de
`BLOCKED`; `within_signed_limits(draft, execuções, perna com a quantidade a enviar,
known_costs=0)`. Para venda: quantidade = `reservations.available(...)`; se for zero, não
envia; se for positiva, `reserve` e depois `submit`. Falha em qualquer item ⇒ **não envia
agora** e tenta de novo no próximo `on_reports` ou `on_market`. Exceção: limites assinados
falsos ⇒ `STOP`.

O preço e a quantidade enviados são os assinados. O motor nunca altera limite.

**R6 — Relatórios.** Para cada relatório de ordem desta boleta: aplica `transition` ao
estado da ordem; grava no recibo; execução de compra ⇒ `confirm_buy`; execução de venda ⇒
`confirm_sale`; venda que termina com saldo vivo (cancelada, expirada, rejeitada) ⇒
`confirm_release` do saldo. O retorno de `venue.submit` também é um relatório e segue esta
regra. Depois tenta envios (R5) e fecha (R7).

**R7 — Fechar.** Com a boleta em `WORKING` e **nenhuma ordem viva**:

- todas as pernas executadas por inteiro ⇒ `COMPLETE`;
- senão, se ainda pode haver envio (sem cancelamento humano, `now <= send_deadline` e
  alguma venda com `available > 0`) ⇒ continua `WORKING`;
- senão ⇒ `STOP`.

"Ordem viva" = `PENDING_SEND`, `LIVE`, `PARTIAL`, `CANCEL_REQUESTED` ou `UNCERTAIN`.

**R8 — Cancelar.** `cancel` exige ordem desta boleta em `LIVE` ou `PARTIAL`; consome
`CANCEL_ORDER` da ordem; aplica `REQUEST_CANCEL`; chama `venue.request_cancel`; marca
"cancelamento humano". **Nunca** é bloqueado por trava de mercado, pausa ou conta bloqueada.
Depois de um cancelamento humano a boleta não envia mais nada.

**R9 — Estado incerto.** `submit` que devolve `UNCERTAIN`: a ordem vai a `UNCERTAIN`, a
boleta recebe `UNCERTAIN`, a conta entra em `halts`. Relatórios posteriores dessa ordem são
**guardados** sem aplicar e sem reenviar nada. `reconcile(order_id, now)` consulta `poll`:

- `None` ⇒ a ordem resolve para `REJECTED` (só se não houver relatório guardado);
- senão ⇒ resolve para `LIVE` e aplica os relatórios guardados, em ordem, pela R6. O
  resultado tem de bater com `poll` em estado e quantidade executada; se não bater,
  `EngineRefusal` e a ordem continua `UNCERTAIN`.

Resolvida a última ordem incerta: a conta sai de `halts`; a boleta resolve por
`reconcile` para `WORKING` se ainda houver ordem viva, senão para o que a R7 indicar
(`WORKING`, `COMPLETED` ou `STOPPED`). Se o destino for `WORKING`, fica **pausada**.
Retomar exige decisão `RESUME`. Cada resolução grava `RECONCILE` no recibo.

**R10 — Pausar e retomar.** `pause` vale em qualquer estado, grava `PAUSE`, não chama a
venue. `resume` exige nenhuma ordem `UNCERTAIN`; consome `RESUME`; grava `RESUME`; tenta
envios.

**R11 — Engatilhar.** `arm` em `DRAFT`: primeiro `Trigger(spec).arm(book, now)`; depois
consome `ARM` com a prévia e `spec_digest(spec)`; aplica `ARM`. `disarm` em `ARMED`:
consome `DISARM`, desarma, aplica `DENY`. `discard` em `DRAFT` ou `TRIGGERED`: consome
`DISCARD`, aplica `DENY`.

**R12 — Mercado.** `on_market(event)`: em `ARMED`, repassa ao gatilho; `FIRED` ⇒ aplica
`TRIGGER` e grava **um** registro; `EXPIRED` ⇒ aplica `EXPIRE`. O disparo não envia nada e
não muda preço. Em `WORKING`, tenta envios (R5) e fecha (R7).

**R13 — Recibo.** Todo relatório da venue, toda mudança de estado da boleta e toda prévia
entram no recibo. Dinheiro vai como **texto decimal**. `receipt.verify()` é verdadeiro ao
fim de todo cenário.

**R14 — O que o motor nunca faz.** Construir decisão; chamar `issue`; reenviar ordem depois
de `UNCERTAIN`; cancelar por conta própria; mandar ordem com preço ou quantidade diferente
do assinado; decidir pelo texto de uma recusa.

## 5. Sessão de referência

- Horário inicial 14:00:00. Fechamento 21:00. Prazo de envio 15:00. Validade 21:00.
- Conta `sim`. Posição: A = 0, B = 0, par (A protege B), calls do mesmo vencimento.
- Boleta `T1`: **compra de A, 10 a 1,00; venda de B, 10 a 1,50**; lote 1; `net_limit`
  −5,00 (compras menos vendas: 10,00 − 15,00); `gross_cap` 25,00. Exposição parcial 10,00.
- Livro de abertura: evento 1 (14:00:00) A bid 0,95 × 50, ask 1,02 × 50; evento 2
  (14:00:01) B bid 1,45 × 50, ask 1,55 × 50. Fase `CONTINUOUS`.
- Confirmação às **14:00:02**, salvo indicação. Nesse instante a trava devolve `OK`.
- Eventos seguintes de um em um segundo: evento 3 às 14:00:03, evento 4 às 14:00:04, etc.
- Tamanho não citado = 50. Lado não citado = o do livro de abertura.
- `arm`, `discard` e `pause` às **14:00:02**, salvo indicação. `reconcile` e `resume` no
  horário do último evento do cenário (em S19 e S20, 14:00:03; a trava devolve `OK`).
- Decisões: emitidas pelo teste com `issue`, válidas de 14:00:00 a 15:00:00, um `nonce`
  por decisão, salvo indicação.
- Nos esperados, nome com `VENUE_` é **relatório**; os demais (`FILLED`, `PARTIAL`,
  `CANCELLED`, `EXPIRED`…) são **estado** da ordem ou da boleta no motor.

## 6. Cenários, com o esperado

"Compra" = ordem `T1:A:1`. "Venda" = ordem `T1:B:1`.

| # | Passos depois da abertura | Esperado |
|---|---|---|
| S01 | confirma; ev3 A ask 1,00; ev4 B bid 1,50 | Compra `FILLED`, 10 a 1,00; venda enviada às 14:00:03 com 10 a 1,50; venda `FILLED`, 10 a 1,50; boleta `COMPLETED`. Recibo, na ordem: `PREVIEW`, `CONFIRM`, `START`, `VENUE_LIVE`, `VENUE_FILL`, `VENUE_LIVE`, `VENUE_FILL`, `COMPLETE` |
| S02 | igual a S01, com as duas séries do tipo `PUT` | igual a S01 |
| S03 | confirma; ev3 A ask 1,00; ev4 B bid 1,49; evento com horário 21:00 | Venda nunca executa; no fechamento chega `VENUE_EXPIRED` e a venda fica `EXPIRED`; boleta `STOPPED`; comprado 10, vendido 0 |
| S04 | confirma; ev3 A ask 1,00 × 3 | Compra `PARTIAL` 3; venda enviada com **3**; `available` = 0; boleta `WORKING` |
| S05 | S04; ev4 A em `AUCTION`, ask 1,00 × 100; `cancel` da compra; ev5 `auction_fill` de A 1,00 × 1; ev6 `cancel_rejected` da compra | Compra: `CANCEL_REQUESTED`, depois `PARTIAL` com **4 executadas e 6 de saldo**; nenhuma ordem nova depois da venda de 3; boleta `WORKING` |
| S06 | `discard` em `DRAFT` | boleta `DENIED`; `orders` vazio; nenhuma chamada à venue |
| S07 | confirma; `cancel` da compra; ev3 A ask 1,02 | Antes do ev3 a compra está `CANCEL_REQUESTED`; depois, `CANCELLED`; boleta `STOPPED` |
| S08 | S01 até a venda enviada; `cancel` da venda; ev4 B bid 1,50 × 4 | No ev4 chegam `VENUE_PARTIAL` de 4 e `VENUE_CANCELLED`, nessa ordem; a venda passa por `CANCEL_REQUESTED` e termina `CANCELLED` com 4 executadas; os dois relatórios no recibo; **nenhuma venda nova**, embora `available` volte a 6; boleta `STOPPED`; comprado 10, vendido 4 |
| S09 | duas boletas `T1` e `T2` iguais, mesma conta, mesmo livro de reservas; as duas confirmam, `T1` primeiro; ev3 A ask 1,00 × 3 | `T1:A:1` `PARTIAL` 3; `T2:A:1` segue `LIVE`; `T1` envia venda de 3; `T2` não envia venda (`available` = 0) |
| S10 | `arm` (ASK de A ≤ 1,00, mínimo 10, até 15:00); ev3 A ask 1,00; ev4 A ask 0,99; confirma às 14:00:05 | Depois do ev3: `TRIGGERED`, **um** registro `TRIGGER`, `orders` vazio. Depois do ev4: igual. Depois da confirmação: `WORKING`, compra `LIVE` |
| S11 | ev3 A ask 1,00; `arm` às 14:00:04, antes do ev4, com o gatilho de S10; ev4 A ask 1,02; `arm` às 14:00:05 **com a mesma decisão** | Primeiro `arm` recusa ("condição já verdadeira") e a boleta segue `DRAFT`; o segundo é aceito e a boleta vai a `ARMED` |
| S12 | `arm` (STRATEGY_TRADE de A ≤ 0,50, mínimo 1, até 15:00); ev3 negócio de A 0,45 × 5 `SIMPLE`; ev4 negócio de A 0,45 × 5 `STRATEGY` | Depois do ev3: `ARMED`. Depois do ev4: `TRIGGERED` |
| S13 | `arm` como S10; evento de A às 15:00:00,000001 | boleta `EXPIRED`; `confirm` posterior recusa |
| S14 | (a) confirma às 14:00:10, sem cotação nova. (b) ev de A 14:00:10 e de B 14:00:11 com o livro de abertura; confirma às 14:00:12 **com a mesma decisão**. (c) com a compra viva, ev A em `AUCTION`; `cancel` da compra | (a) recusa ("cotação vencida"), boleta `DRAFT`, `orders` vazio. (b) aceita. (c) `cancel` aceito: compra `CANCEL_REQUESTED` |
| S15 | S04; evento de A às **15:00:01**, ask 1,00 × 50; evento com horário 21:00 | `VENUE_FILL` de 7 e a compra fica `FILLED`; **nenhuma venda nova** (prazo de envio vencido); existe só a venda de 3; no fechamento ela expira e a boleta vai a `STOPPED`; comprado 10, vendido 0 |
| S16 | boleta com validade 20:00; confirma | recusa ("validade que a venue não garante"); `orders` vazio; a decisão não foi gasta |
| S17 | `edit` do limite da compra para 0,99; `refresh` sugerindo 1,01 para o mesmo campo; confirma com decisão emitida para a versão 1; confirma com decisão emitida para a versão 2 | Versão 2 depois do `edit`; o `refresh` não muda nada; a primeira confirmação recusa ("resumo divergente"); a segunda é aceita e a compra sai a **0,99** |
| S18 | confirma; confirma de novo com a mesma decisão | a segunda recusa pelo estado; existe uma única ordem de compra |
| S19 | evento `timeout` (`submit`, registrada) às 14:00:02; confirma; ev A ask 1,00 às 14:00:03; `T2` tenta confirmar; `reconcile` da compra; `resume` com decisão | Compra `UNCERTAIN`, boleta `UNCERTAIN`; o `VENUE_FILL` é guardado e nenhuma venda sai; `T2` recusa ("conta em estado incerto") sem gastar decisão; depois do `reconcile`: compra `FILLED`, boleta `WORKING` e pausada, conta liberada; depois do `resume`: venda de 10 enviada. Existe uma única ordem de compra |
| S20 | confirma; `pause`; ev3 A ask 1,00; `resume` com decisão | Depois de `pause`: compra segue `LIVE` na venue. Depois do ev3: compra `FILLED`, nenhuma venda. Depois de `resume`: venda de 10 enviada |
| S21 | posição A = +10, B = −10; boleta: **vende A 10 a 1,00, compra B 10 a 1,50**, líquido +5,00, bruto 25,00; confirma; ev3 B ask 1,50; ev4 A bid 1,00, ask 1,05 | Primeira ordem é a **compra de B** (`T1:B:1`); depois do ev3, venda de A enviada (`T1:A:1`); depois do ev4, `COMPLETED`. Exposição parcial 15,00 |
| S22 | S01 até a venda enviada; ev4 B bid 1,49; ev5 B bid 1,49; evento com horário 21:00 | Existe uma única ordem de venda, sempre a **1,50**; nunca executa; no fechamento expira; boleta `STOPPED` |

Casos extras do motor:

| # | Passos | Esperado |
|---|---|---|
| X1 | `T1` com `net_limit` −5,01 (as pernas dão −5,00); confirma | recusa (`within_signed_limits` falso); `orders` vazio; decisão não gasta |
| X2 | venue de teste que rejeita todo envio; confirma | compra `REJECTED`; boleta `STOPPED`; nenhuma venda |
| X3 | confirma; evento de A às 14:00:07, ask 1,00; evento de B às 14:00:08, bid 1,45 | Depois do primeiro: compra `FILLED`, **nenhuma venda** (cotação de B com 6 s), boleta `WORKING`. Depois do segundo: venda de 10 enviada |
| X4 | `edit` em `ARMED` | recusa pelo estado |
| X5 | `cancel` de ordem de outra boleta; de ordem `FILLED` | recusa nas duas; decisão não gasta |
| X6 | `resume` com ordem ainda `UNCERTAIN` | recusa; decisão não gasta |
| X7 | S04; ev4 A em `AUCTION`, ask 1,00 × 100; ev5 `auction_fill` de A 1,00 × 1 (sem cancelamento) | Compra `PARTIAL` com 4 executadas; `available` = 1, mas **nenhuma venda nova** enquanto A está em leilão; existe só a venda de 3; boleta `WORKING` |
| X8 | livro de abertura com B bid 1,44, ask 1,55 (11 ticks); confirma | a trava devolve `CAUTION` ("spread aberto") e a confirmação é **aceita**; compra `LIVE` |

Textos entre aspas vêm das peças existentes e são literais (`DeadlineRefusal`,
`DecisionRefusal`, `TriggerRefusal`, motivos de `assess`). A exceção é "conta em estado
incerto", que é recusa do próprio motor: o texto é livre e o teste confere o tipo
(`EngineRefusal`) e que nada mudou.

Notas de conferência: em S05 a trava devolve `BLOCKED` ("leilão") às 14:00:04 e ainda às
14:00:06; em S14(a) devolve `BLOCKED` ("cotação vencida", uma vez por perna); em S08 o
livro de reservas devolve 6 disponíveis depois da liberação, e o motor não usa por causa do
cancelamento humano; em S09 a ordem de `T1` chega antes e leva as 3 unidades exibidas.

## 7. Arquitetura

Em `tests/architecture/test_ticket_boundaries.py`:

1. `engine.py` pode importar de `ticket.gate` apenas `Action`, `DecisionLedger`,
   `DecisionRefusal` e `HumanDecision`. A regra existente sobre `issue` e sobre construir
   `HumanDecision` continua valendo e deve passar com o motor.
2. `engine.py` não importa `ticket.paper_venue`; de `ticket.replay` importa só o tipo
   `ReplayEvent`; e não contém chamada a atributo de nome `advance`.
3. Nenhum módulo de `backend/derivatives/mcp/` importa `ticket` (regra já existente).

## 8. Testes e mutantes

- Um teste por cenário S01–S22 e por caso X, com o esperado literal e nome do cenário.
- Em todo cenário: `receipt.verify()` verdadeiro; todo valor monetário do recibo é texto.
- S06, S10 (até o disparo), S11, S13, S14(a), S16 e X1: contar chamadas a `submit` = 0.

Mutantes que devem morrer, um por vez:

1. consumir a decisão antes das outras checagens (S14, S16, X1);
2. pular `check_deadlines` (S16); pular `assess` na confirmação (S14);
3. `CAUTION` tratado como bloqueio na confirmação (X8);
4. enviar as vendas junto com as compras (S04);
5. liberar venda pelo enviado em vez do executado (S04);
6. `assess` só da perna enviada em vez de todas (X7);
7. enviar depois do prazo de envio (S15);
8. enviar com a boleta pausada (S20); `pause` chamar a venue;
9. enviar depois de cancelamento humano (S08);
10. trava de mercado bloquear `cancel` (S14c);
11. aplicar relatório em ordem `UNCERTAIN` (S19); reenviar depois de `UNCERTAIN`;
12. não bloquear a conta em estado incerto (S19);
13. `reconcile` aceitar resultado que não bate com `poll`;
14. não pausar depois de reconciliar (S19);
15. gatilho disparado enviar ordem (S10); registrar `TRIGGER` duas vezes;
16. `arm` consumir a decisão antes de armar (S11);
17. mudar o limite da venda quando não executa (S22);
18. `STOP` em vez de continuar `WORKING` quando a trava é temporária (X3);
19. `COMPLETE` sem todas as pernas executadas por inteiro (S03, S08);
20. gravar dinheiro como número no recibo.

## 9. Critérios de parada

Pare e relate se: algum esperado do §6 não reproduzir com as regras do §4; a tabela de
`state.py` recusar uma transição que as regras pedem; o motor passar de 400 linhas; for
preciso tocar em arquivo fora do §2.

## 10. Entrega

1. Commit vermelho com os cenários; depois o verde.
2. Portão completo em clone limpo no Mac. O revisor roda o Linux.
3. Descrição do PR: cabeça, contagens, linhas de produção, mutantes, desvios.
4. Copie este cartão para `docs/specs/derivatives/fase3/DL3-PR05b.md`. Não edite
   `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` na cabeça publicada e os dois relatórios fora do Git, com
   SHA-256 na descrição. PR em rascunho.

---

## Revisão adversarial (Claude) — três rodadas, GO na cabeça `9f5db3c`

| Rodada | Cabeça | Parecer | Motivo |
|---|---|---|---|
| 1 | `3f4d4e1` | NO-GO | Duas boletas na mesma recompra, foto divergente depois do envio, recusa do livro derrubando o lote, venda rejeitada reenviada sem limite. Correção no DL3-PR05b-R1 |
| 2 | `79e49f8` | NO-GO | Colisão de `order_id` com `:` no id ou no símbolo, duas docstrings, linhas longas e nove mutantes vivos. Correção no DL3-PR05b-R2 |
| 3 | `9f5db3c` | GO | Sem achado |

Três dos bloqueios da rodada 1 e o da rodada 2 eram lacunas deste cartão, não erro de
implementação: ele não previa duas boletas disputando a mesma recompra, não mandava
conferir a foto antes de gastar a decisão, não dizia o que fazer com venda rejeitada e
fixou o formato do `order_id` sem restringir os caracteres.

| Verificação do revisor na cabeça `9f5db3c`, clone limpo, Linux x86_64 | Resultado |
|---|---|
| Pytest sem integração | 11.173 aprovados, 16 pulados, 261 subtestes |
| `mypy backend/ --strict` e `pyright backend/` | 0 erros |
| Linhas | `engine.py` 393 (teto 400), `sequencing.py` 337 (teto 360), PR com 435 de produção (teto 480) |
| 55 mutantes do revisor em `engine.py` e `sequencing.py` | todos mortos (na rodada 2, 8 de 46 sobreviviam) |
| Sondas dos bloqueios das rodadas 1 e 2 | nenhuma reproduz |
| 6.000 sessões aleatórias, motor e `PaperVenue` reais | estado da ordem igual ao da venue, recibo íntegro, nenhum envio depois do prazo, cobertura por conta e teto de recompra respeitados |

Relatórios da skill lidos depois do parecer formado, com SHA-256 conferidos
(`9ba2ea47…8256` e `30497b94…0e96`): GO para o simulador D0, sem bloqueante.
