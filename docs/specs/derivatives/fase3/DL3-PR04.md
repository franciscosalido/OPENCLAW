# DL3-PR04 — Supercartão: venue simulada, replay, travas de mercado e os dois prazos

**Data:** 22/11/2026 · **Autor:** Claude · **Para:** Codex · **Base:** `main` = `88b7033`
**Branch:** `feat/dl3-pr04-paper-venue` · **PR em rascunho**
**Substitui** a seção "DL3-PR04" de `DL3_CARDS.md`. As "Regras comuns" daquele arquivo valem.
**Leia antes:** `SDD_FASE3_BLUEPRINT.md` §4 e §6, ADR-0024 G1, G3a e G5, `current_state.md`.

---

## 0. Três lições das revisões anteriores, que viram regra aqui

1. **Esperado escrito à mão.** Nenhum teste calcula o esperado a partir do código que
   testa. Todas as tabelas deste cartão já trazem o número.
2. **Toda guarda tem um teste que morre sem ela.** O revisor vai remover cada `if` de
   recusa, um por vez. Guarda sem teste volta como NO-GO.
3. **Parar no primeiro esperado que não reproduz.** Este cartão foi calculado à mão, sem
   código para conferir. Se uma tabela estiver errada, pare e relate; não ajuste.

## 1. Objetivo

Dar ao motor da boleta um lugar determinístico onde ordens vivem, executam, são canceladas
e expiram, e um juiz que diz se o mercado permite enviar. Tudo offline, sem relógio do
sistema e sem sorteio.

## 2. Não-objetivos

Motor, gate humano, gatilho, CLI, recibo, tela. Modelo de fila, impacto de preço, custos e
emolumentos (custo conhecido = 0 neste PR). Ordem a mercado. Trava de volatilidade (a ADR
exige números homologados; fica registrada como pendência). Qualquer rede, token ou conta.
Mudança em `models.py`, `digest.py`, `state.py`, `receipt.py`, `sequencing.py`.

## 3. Arquivos e orçamento

| Arquivo | Conteúdo |
|---|---|
| `ticket/replay.py` | Eventos do replay e leitor da fixture |
| `ticket/guards.py` | Foto do livro, travas de mercado, conferência dos dois prazos |
| `ticket/venue.py` | Protocolo `ExecutionVenue` e tipos de ordem, relatório e consulta |
| `ticket/paper_venue.py` | Simulador |
| `config/ticket_sim.yaml`, `config/ticket_sim_config_model.py` | Parâmetros sintéticos |
| `tests/unit/derivatives/ticket/test_replay.py`, `test_guards.py`, `test_paper_venue.py` | Testes |
| `tests/fixtures/derivatives/synthetic/ticket/*.json` | Fixtures |
| `tests/architecture/test_ticket_boundaries.py` | Duas regras novas (§9) |

Teto: **400 linhas de produção**. Se passar, **divida sem pedir**: PR04a com `replay.py`,
`guards.py` e configuração; PR04b com `venue.py` e `paper_venue.py`. Cada um com seu portão.

Tudo síncrono: não há entrada e saída além de ler um arquivo local pequeno.

## 4. Replay (`replay.py`)

**Fixture.** Um arquivo JSON:

```json
{"session_close": "2026-11-23T21:00:00+00:00",
 "events": [
  {"seq": 1, "ts": "2026-11-23T14:00:00+00:00", "type": "quote", "symbol": "A",
   "bid": "0.95", "bid_size": 50, "ask": "1.02", "ask_size": 50, "phase": "CONTINUOUS"},
  {"seq": 2, "ts": "...", "type": "trade", "symbol": "A", "price": "0.90", "size": 100,
   "kind": "SIMPLE"},
  {"seq": 3, "ts": "...", "type": "auction_fill", "symbol": "A", "price": "1.00", "size": 1},
  {"seq": 4, "ts": "...", "type": "cancel_rejected", "order": "o1"},
  {"seq": 5, "ts": "...", "type": "timeout", "call": "submit", "registered": true}
 ]}
```

**Tipos** (imutáveis, `extra="forbid"`): `QuoteEvent`, `TradeEvent`, `AuctionFill`,
`CancelRejected`, `VenueTimeout`. `phase ∈ {CONTINUOUS, AUCTION, SUSPENDED}`.
`kind ∈ {SIMPLE, STRATEGY}`. `bid` e `ask` podem ser nulos (lado vazio), com tamanho 0.

**Leitor** `load_replay(path) -> Replay(session_close, events)`. Recusa com `ReplayError`:

| Entrada | Motivo |
|---|---|
| Dinheiro como número JSON (`"bid": 0.95`) | dinheiro só como texto decimal |
| Preço fora do passo de 0,01, zero ou negativo | preço inválido |
| Tamanho negativo, ou lado nulo com tamanho diferente de 0 | tamanho inválido |
| `ts` sem fuso, ou menor que o do evento anterior | tempo inválido |
| `seq` repetido ou decrescente | sequência inválida |
| Chave desconhecida, `type` desconhecido, chave duplicada | formato inválido |

**Lacuna de sequência não é erro de leitura.** `seq` 1, 2, 4 carrega normalmente. O evento
de `seq` 4 fica marcado `gap_before=True`. Quem decide o que fazer é a trava (§6).

## 5. Venue (`venue.py` e `paper_venue.py`)

### 5.1 Tipos

- `VenueOrder(order_id, symbol, side, quantity, limit_price, lot_size, valid_until)`.
- `VenueReport(order_id, event, quantity, price, ts)`: `event` é um `Event` de `state.py`
  (`VENUE_LIVE`, `VENUE_PARTIAL`, `VENUE_FILL`, `VENUE_CANCELLED`,
  `VENUE_CANCEL_REJECTED_LIVE`, `VENUE_CANCEL_REJECTED_PARTIAL`, `VENUE_EXPIRED`,
  `VENUE_REJECTED`, `UNCERTAIN`). `quantity` e `price` só em execução.
- `OrderSnapshot(state: OrderState, filled: int, remaining: int)`.
- `VenueRefusal(ValueError)`: pedido impossível (ordem desconhecida, ordem já terminal).

### 5.2 Protocolo `ExecutionVenue`

```python
def accepts_validity(self, valid_until: datetime) -> bool: ...
def submit(self, order: VenueOrder, now: datetime) -> VenueReport: ...
def request_cancel(self, order_id: str, now: datetime) -> None: ...
def poll(self, order_id: str) -> OrderSnapshot | None: ...   # None = ordem desconhecida
```

Sem método de ordem a mercado. Sem método que altere preço ou quantidade.

### 5.3 `PaperVenue(session_close)` — regras, na ordem em que valem

`advance(event) -> tuple[VenueReport, ...]` consome **um** evento do replay. O teste dirige o
replay e chama `submit` e `request_cancel` entre um evento e outro.

1. **Envio.** `submit` devolve `VENUE_LIVE`. A ordem **não** casa com a cotação que já
   estava na tela: só com cotações que chegarem depois.
2. **Rejeição no envio**, com `VENUE_REJECTED` e sem registrar a ordem: validade que a venue
   não garante; quantidade não múltipla do lote; `order_id` repetido; `now` igual ou depois
   de `session_close`.
3. **Casamento, só em `QuoteEvent` com fase `CONTINUOUS`**, para as ordens vivas daquele
   símbolo, na ordem de chegada: compra executa se `ask <= limite`, ao preço `ask`; venda
   executa se `bid >= limite`, ao preço `bid`. A quantidade é o mínimo entre o saldo da
   ordem e o tamanho exibido que sobrou **naquele evento**. Saldo zerado ⇒ `VENUE_FILL`;
   senão `VENUE_PARTIAL`.
4. **Nunca por `TradeEvent`.** Negócio não executa ordem, seja `SIMPLE` ou `STRATEGY`.
5. **Fase `AUCTION` ou `SUSPENDED`:** nenhuma execução por cotação. Só `AuctionFill`
   executa: ordens vivas do símbolo, na ordem de chegada, compra com `limite >= preço`,
   venda com `limite <= preço`, até o tamanho do evento, ao preço do evento.
6. **Cancelamento.** `request_cancel` só registra o pedido. A confirmação sai no **próximo
   `QuoteEvent` em `CONTINUOUS` do mesmo símbolo, depois do casamento desse evento**:
   `VENUE_CANCELLED` para o saldo. Se o casamento zerou a ordem, sai só `VENUE_FILL`.
   Em leilão o pedido fica pendente. `CancelRejected(order)` devolve
   `VENUE_CANCEL_REJECTED_LIVE` se nada executou, `VENUE_CANCEL_REJECTED_PARTIAL` se já
   executou algo, e apaga o pedido. `CancelRejected` para ordem sem pedido pendente é
   erro de fixture: `advance` levanta `VenueRefusal`.
7. **Expiração.** No primeiro evento com `ts >= session_close`, toda ordem não terminal
   recebe `VENUE_EXPIRED`, antes de qualquer casamento desse evento.
8. **Timeout.** `VenueTimeout(call="submit", registered)` arma a próxima chamada de
   `submit`: ela devolve `UNCERTAIN`. Se `registered` é verdadeiro, a ordem ficou viva e
   `poll` mostra; se falso, `poll` devolve `None`.
9. **Lacuna de sequência não para a venue.** A bolsa simulada não depende do nosso feed:
   ordem já viva continua casando depois da lacuna.
10. **`accepts_validity`:** verdadeiro só para `valid_until == session_close` (validade
    "dia"). Qualquer outro instante, falso.

**Invariante a testar em todos os cenários:** para cada relatório emitido,
`transition(estado_da_ordem, relatório.event)` é aceito pela tabela de `state.py`. O teste
mantém o estado de cada ordem aplicando os relatórios e o `REQUEST_CANCEL` local. Depois de
um `UNCERTAIN`, o teste consulta `poll` e resolve com `reconcile(..., evidence="poll")`
antes de aplicar o relatório seguinte (V11): é o caminho que o motor vai usar.

## 6. Travas de mercado (`guards.py`)

- `BookSnapshot(symbol, bid, bid_size, ask, ask_size, phase, ts, sequence_ok)`.
- `BookView`: mantém a última foto por símbolo a partir dos eventos. Depois de um evento
  com `gap_before=True`, **todas** as fotos ficam com `sequence_ok=False` até o fim do
  replay. Não há ressincronização neste PR.
- `assess(legs, book, now, config) -> GuardResult(level, reasons)`, com
  `level ∈ {OK, CAUTION, BLOCKED}`. Vale o pior nível entre as pernas. `reasons` em ordem
  fixa: pela ordem das pernas e, dentro da perna, pela ordem da tabela.

Parâmetros **sintéticos, não homologados**, em `config/ticket_sim.yaml`:
`max_quote_age_s: 5.0`, `max_spread_ticks: 10`. Sem default no modelo; inteiro onde é
inteiro, float onde é float, sem coerção.

Perna de referência: **compra de A, 10 unidades, limite 1,00**. Compra olha o lado `ask`;
venda olha o lado `bid`.

| ID | Foto de A | Idade | Fase | Nível | Motivo |
|---|---|---:|---|---|---|
| G1 | bid 0,95 × 50, ask 1,00 × 50 | 1 s | CONTINUOUS | OK | — |
| G2 | igual | 5 s exatos | CONTINUOUS | OK | — |
| G3 | igual | 5,000001 s | CONTINUOUS | BLOCKED | cotação vencida |
| G4 | igual | 1 s | AUCTION | BLOCKED | leilão |
| G5 | igual | 1 s | SUSPENDED | BLOCKED | suspensão |
| G6 | bid 1,00, ask 1,00 | 1 s | CONTINUOUS | BLOCKED | livro inválido |
| G7 | bid 1,01, ask 1,00 | 1 s | CONTINUOUS | BLOCKED | livro inválido |
| G8 | bid 0,95 × 50, ask nulo × 0 | 1 s | CONTINUOUS | BLOCKED | livro incompleto |
| G9 | sem foto de A | — | — | BLOCKED | sem cotação |
| G10 | G1 com `sequence_ok=False` | 1 s | CONTINUOUS | BLOCKED | perda de sequência |
| G11 | bid 0,90, ask 1,00 (10 ticks) | 1 s | CONTINUOUS | OK | — |
| G12 | bid 0,89, ask 1,00 (11 ticks) | 1 s | CONTINUOUS | CAUTION | spread aberto |
| G13 | ask 1,00 × 9 | 1 s | CONTINUOUS | CAUTION | pouca profundidade |
| G14 | ask 1,00 × 10 | 1 s | CONTINUOUS | OK | — |
| G15 | venda de B, 10: bid 1,50 × 9, ask 1,55 × 50 | 1 s | CONTINUOUS | CAUTION | pouca profundidade |
| G16 | duas pernas: A como G12, B como G4 | 1 s | — | BLOCKED | spread aberto; leilão |
| G17 | idade negativa (foto com `ts` depois de `now`) | −1 s | CONTINUOUS | BLOCKED | tempo inválido |

G8: para **venda** de A com o mesmo livro (bid presente, ask nulo), o nível é OK se o resto
permitir; o lado que importa é o `bid`. Sem os dois lados não há spread a medir.

`assess` não tem parâmetro nem caminho para cancelamento. A trava nunca bloqueia cancelar:
isso é testado na venue (cenário V7: pedido de cancelamento aceito em leilão).

## 7. Os dois prazos (`guards.py`)

`check_deadlines(draft, now, venue) -> None`, levantando `DeadlineRefusal` com motivo.
`session_close` = 21:00.

| ID | Prazo de envio | Validade da ordem | Agora | Resultado |
|---|---|---|---|---|
| D1 | 15:00 | 21:00 | 14:00 | aceita |
| D2 | 15:00 | 21:00 | 15:00:00 exatos | aceita |
| D3 | 15:00 | 21:00 | 15:00:00,000001 | recusa: prazo de envio vencido |
| D4 | 21:00 | 21:00 | 14:00 | aceita |
| D5 | 21:30 | 21:00 | 14:00 | recusa: prazo de envio depois da validade |
| D6 | 15:00 | 20:00 | 14:00 | recusa: validade que a venue não garante |
| D7 | 15:00 | 21:00 | 21:00 | recusa: prazo de envio vencido |

Vencido o prazo de envio, nada novo é enviado. Ordem já enviada **não** é cancelada: segue
até a validade nativa (cenário V9). Isso fecha a nota "ordem entre prazo e validade" do
`current_state.md`, sem tocar em `models.py`.

## 8. Cenários da venue, com o esperado

Convenções: fase `CONTINUOUS` salvo indicação; `o1` = compra de A, 10 @ 1,00, lote 1;
`s1` = venda de B, 10 @ 1,50, lote 1; ordens enviadas depois do evento 1; tamanhos de quem
não importa = 50.

| ID | Eventos depois do envio | Relatórios, na ordem | `poll` ao final |
|---|---|---|---|
| V1 | ask de A 1,00 × 50 | `VENUE_FILL` 10 @ 1,00 | FILLED, 10, 0 |
| V2 | ask de A 0,98 × 50 | `VENUE_FILL` 10 @ **0,98** | FILLED, 10, 0 |
| V3 | ask 1,00 × 3; ask 1,00 × 4; ask 1,01 × 100; ask 0,99 × 100 | `PARTIAL` 3 @ 1,00; `PARTIAL` 4 @ 1,00; nada; `FILL` 3 @ 0,99 | FILLED, 10, 0; total pago **9,97** |
| V4 | negócio de A a 0,90 × 100, `SIMPLE`; depois `STRATEGY`; ask continua 1,02 | nada | LIVE, 0, 10 |
| V5 | `s1`: bid de B 1,50 × 6; bid 1,55 × 10 | `PARTIAL` 6 @ 1,50; `FILL` 4 @ 1,55 | FILLED, 10, 0; total recebido **15,20** |
| V6 | `o1` = compra 5 @ 1,00 e `o2` = compra 5 @ 1,00, nessa ordem; ask 1,00 × 7 | `FILL` de `o1` 5; `PARTIAL` de `o2` 2 | `o1` FILLED; `o2` PARTIAL, 2, 3 |
| V7 | ask 1,00 × 3; cotação de A em `AUCTION` com ask 1,00 × 100; `request_cancel(o1)`; `auction_fill` de A 1,00 × 1; `cancel_rejected` de `o1` | `PARTIAL` 3; nada; (pedido aceito, sem relatório); `PARTIAL` 1; `VENUE_CANCEL_REJECTED_PARTIAL` | PARTIAL, **4, 6** |
| V8 | `s1` viva; `request_cancel(s1)`; bid de B 1,50 × 4 | `PARTIAL` 4 @ 1,50; depois `VENUE_CANCELLED` | CANCELLED, 4, 0 |
| V8b | `s1` viva; `request_cancel(s1)`; bid de B 1,40 × 50 | `VENUE_CANCELLED` | CANCELLED, 0, 0 |
| V8c | `s1` viva; `request_cancel(s1)`; bid de B 1,50 × 10 | `VENUE_FILL` 10; **sem** `VENUE_CANCELLED` | FILLED, 10, 0 |
| V8d | `o1` viva; `request_cancel(o1)`; cotação de **B** (outro símbolo) | nada | o pedido segue pendente; LIVE, 0, 10 |
| V9 | `o1` com 3 executadas; evento com `ts` = 21:00 e ask 1,00 × 50 | `VENUE_EXPIRED`; nenhuma execução nesse evento | EXPIRED, 3, 0 |
| V10 | `submit` com `valid_until` = 20:00 | `VENUE_REJECTED` | `poll` devolve `None` |
| V11 | `timeout(submit, registered=true)`; `submit(o1)`; `poll`; ask 1,00 × 50 | `UNCERTAIN`; `poll` = LIVE, 0, 10; depois `FILL` 10 | FILLED, 10, 0 |
| V11b | `timeout(submit, registered=false)`; `submit(o1)` | `UNCERTAIN` | `poll` devolve `None` |
| V12 | `o1` viva; evento com lacuna de sequência e ask 1,00 × 50 | `FILL` 10 @ 1,00 | FILLED; `BookView` com `sequence_ok=False` |
| V13 | lote 3: compra 9 @ 1,00; ask 1,00 × 4 | `PARTIAL` 4 | PARTIAL, 4, 5 |
| V14 | `request_cancel` de ordem desconhecida; de ordem `FILLED`; `submit` com `order_id` repetido | `VenueRefusal`; `VenueRefusal`; `VENUE_REJECTED` | — |

Notas de cálculo: V3 = 3 × 1,00 + 4 × 1,00 + 3 × 0,99 = 9,97. V5 = 6 × 1,50 + 4 × 1,55 =
15,20. V7 reproduz o exemplo da ADR: 4 executadas e 6 de saldo. V13: a venue executa a
quantidade exibida, mesmo fora do múltiplo do lote; o lote vale no envio, não na execução.

Em `remaining`, ordem `CANCELLED` ou `EXPIRED` mostra 0: o saldo foi baixado.

## 9. Arquitetura

Acrescente a `tests/architecture/test_ticket_boundaries.py`:

1. Nenhum módulo de `backend/derivatives/ticket/` importa `random`, `secrets`, `time`,
   `asyncio` ou `threading`, exceto `threading` em `sequencing.py`, que já existe.
2. Nenhum módulo do pacote chama `datetime.now`, `datetime.utcnow`, `datetime.today` ou
   `date.today`. O tempo vem do evento ou do parâmetro `now`.

As regras de rede, LLM e MCP continuam valendo e devem passar com os módulos novos.

## 10. Testes e mutantes

- Um teste por linha das tabelas G, D e V, com o esperado literal.
- Leitor: um teste por linha da tabela de recusas, mais a lacuna que carrega.
- O invariante do §5.3 em todos os cenários V.
- Determinismo: rodar V3 e V7 duas vezes produz relatórios idênticos.

Mutantes que devem morrer, um por vez, listados na descrição do PR:

1. casar no envio com a cotação que já estava na tela;
2. executar pelo último negócio;
3. executar por cotação em leilão;
4. ignorar o tamanho exibido;
5. executar ao limite em vez do preço do livro (morre em V2);
6. confirmar cancelamento no próprio pedido, sem evento;
7. confirmar cancelamento antes do casamento (morre em V8);
8. emitir `VENUE_CANCELLED` depois de `VENUE_FILL` (morre em V8c);
9. cancelar por cotação de outro símbolo (morre em V8d);
10. casar antes de expirar (morre em V9);
11. aceitar validade diferente do fechamento;
12. parar a venue na lacuna de sequência;
13. trava: `<=` por `<` na idade (G2) e na contagem de ticks (G11);
14. trava: olhar o lado errado do livro (G15);
15. trava: `sequence_ok` ignorado;
16. prazos: `<=` por `<` em D2; aceitar D5; aceitar D6;
17. leitor: aceitar dinheiro como número; aceitar `ts` decrescente.

## 11. Critérios de parada

Pare e relate se: algum esperado das tabelas não reproduzir com a regra escrita; a tabela
de `state.py` recusar um relatório da venue; for preciso tocar em arquivo fora do §3.

## 12. Entrega

1. Commit vermelho com as tabelas G, D e V; depois o verde.
2. Portão completo em clone limpo no Mac. O revisor roda o Linux.
3. Descrição do PR: cabeça, contagens, linhas de produção por arquivo, mutantes, desvios.
4. Copie este cartão para `docs/specs/derivatives/fase3/DL3-PR04.md`. Não edite
   `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` na cabeça publicada e os dois relatórios fora do Git, com
   SHA-256 na descrição. PR em rascunho.

## 13. Base da escolha do modelo de execução

Preencher ordem limitada "no toque" do preço é otimista; simuladores sérios só preenchem
quando o mercado atravessa a ordem (arXiv 2409.12721; material educativo NexusFi, viés
comercial). Ordem passiva executada tende a ser seguida de movimento contrário (arXiv
2407.16527). As fontes tratam de futuros e ações, não de opções da B3 (baixo nível de
evidência para o nosso caso). Daí as escolhas conservadoras: casar só com cotação
posterior ao envio, só pelo livro, só pela quantidade exibida. O resultado em papel é
teto otimista, não previsão. Quant StackExchange segue bloqueado para as ferramentas do
revisor e não foi consultado.
# DL3-PR04 — Adendo 1: invariante de estado por tentativa de envio (V14)

**Data:** 22/11/2026 · **Autor:** Claude · **Para:** Codex · **Base:** `main` = `88b7033`
**Altera** o invariante do §5.3 e a linha V14 do §8 do supercartão `DL3-PR04`. O resto vale.

## O erro foi do cartão

O invariante dizia "estado da ordem" por `order_id`. No `submit` repetido de V14, o
`VENUE_REJECTED` cairia sobre o estado da ordem original (`LIVE` ou `FILLED`), e a tabela
de `state.py` recusa essa transição, com razão. O Codex parou no critério de parada.

## Autorização

**Autorizada** a proposta do Codex, sem alteração em `state.py`.

1. **Invariante, nova redação.** O estado é acompanhado por **tentativa de envio**. Cada
   chamada de `submit` abre uma tentativa em `PENDING_SEND`, e o relatório devolvido por
   aquela chamada é aplicado a essa tentativa. Relatórios posteriores (`advance`) são
   aplicados à ordem registrada com aquele `order_id`. Uma tentativa rejeitada termina em
   `REJECTED` e não toca a ordem registrada.
2. **V14, nova redação.** Com `o1` registrada e viva:

| Passo | Esperado |
|---|---|
| `request_cancel` de ordem desconhecida | `VenueRefusal` |
| `submit` de novo com `order_id = "o1"` | `VENUE_REJECTED`; a tentativa vai de `PENDING_SEND` a `REJECTED` |
| `poll("o1")` logo depois | LIVE, 0, 10: a ordem original não mudou |
| ask de A 1,00 × 50 | `VENUE_FILL` 10 @ 1,00 para a ordem original |
| `poll("o1")` | FILLED, 10, 0 |
| `request_cancel("o1")`, já `FILLED` | `VenueRefusal` |
| `submit` de novo com `order_id = "o1"`, original `FILLED` | `VENUE_REJECTED`; `poll("o1")` segue FILLED, 10, 0 |

Mutante a acrescentar à lista do §10: o `submit` repetido substituir ou zerar a ordem
original (morre no terceiro e no último passo).

## Conferência dos outros cenários com a nova redação

- **V10** (validade não garantida): a tentativa vai de `PENDING_SEND` a `REJECTED`; não há
  ordem registrada; `poll` devolve `None`. Sem mudança.
- **V11b** (timeout sem registro): a tentativa vai a `UNCERTAIN`; `poll` devolve `None`; o
  teste resolve com `reconcile(UNCERTAIN, REJECTED, evidence="poll")`, que a tabela aceita.
- **V11** (timeout com registro): a tentativa vai a `UNCERTAIN`; `poll` mostra LIVE; o
  teste resolve com `reconcile(UNCERTAIN, LIVE, evidence="poll")` e segue pela ordem
  registrada.

Se algum desses três não reproduzir, pare e relate.

## Revisão e integração — 22/11/2026 (Claude)

Cabeça `fc4a6cf`: **GO** na primeira rodada, formado antes de ler os relatórios da skill.
O cartão teve um erro meu no V14 (invariante por identificador em vez de por tentativa),
corrigido pelo Adendo 1 antes da implementação.

| Verificação do revisor, clone limpo, Linux x86_64 | Resultado |
|---|---|
| Pytest sem integração, com o teste do revisor | 11.012 aprovados, 16 pulados, 261 subtestes |
| `mypy backend/ --strict` e `pyright backend/` | 0 erros |
| Linhas de produção e configuração | 398, teto de 400 |
| Sorteio do revisor: 4.000 sessões, 48.348 relatórios | a tabela de `state.py` aceita todos; execução sempre dentro do limite e da quantidade; `poll` coerente |
| 42 mutantes do revisor | 41 mortos; 1 equivalente |

O mutante equivalente deixa de limpar o pedido de cancelamento ao expirar: depois do
fechamento a venue ignora qualquer evento, então a diferença não é observável numa
sessão em ordem. O revisor acrescentou um teste para a lacuna L1 do parecer da skill
(política de horário no fechamento da sessão). Relatórios lidos depois do parecer
formado, com SHA-256 conferidos (`e811b538…d558` e `e1852a2a…3698`): GO, sem bloqueante.
