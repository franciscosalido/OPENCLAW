# DL3-PR05a — Supercartão: decisão humana (gate) e gatilho de aviso

**Data:** 22/11/2026 · **Autor:** Claude · **Para:** Codex · **Base:** `main` = `0bec461`
**Branch:** `feat/dl3-pr05a-gate-trigger` · **PR em rascunho**
**Substitui** a parte de `gate.py` e `trigger.py` da seção "DL3-PR05" de `DL3_CARDS.md`.
As "Regras comuns" daquele arquivo valem. O motor (`engine.py`) e os 22 cenários ficam para
o **DL3-PR05b**, que terá cartão próprio depois que este for integrado.

**Por que dividi:** o motor depende do formato exato da decisão e do gatilho. Escrever o
cartão do motor com esses dois já integrados evita esperado calculado sobre código que
ainda não existe.

---

## 0. Como este cartão foi conferido

- Tudo o que depende de código já em `main` foi conferido contra `0bec461`: versão e
  resumo da prévia depois de edições (§3, K5 e K6), comportamento de `BookView` com
  negócio e com lacuna de sequência (§4).
- `gate.py` e `trigger.py` não existem. As tabelas K, A e E são comparações diretas de
  igualdade e de fronteira, sem máquina de estados no meio. Reli cada linha contra as
  regras do §3 e do §4.
- Regra de sempre: esperado que não reproduzir, **pare e relate**.

## 1. Objetivo

Dois módulos puros e pequenos:

- **`gate.py`**: o único lugar onde nasce uma decisão humana, e o livro que impede que ela
  seja usada duas vezes, fora do prazo ou para outra coisa.
- **`trigger.py`**: o "Engatilhar" da ADR-0024. Vigia uma condição e avisa. Nunca envia.

## 2. Não-objetivos e limites

- Motor, recibo, envio, reserva, CLI, tela, autenticação real (Touch ID, senha).
- **Nenhuma mudança** em `models.py`, `digest.py`, `state.py`, `receipt.py`,
  `sequencing.py`, `replay.py`, `guards.py`, `venue.py`, `paper_venue.py`, nem em
  `config/`.
- Sem relógio do sistema e sem sorteio: `now`, `nonce` e prazos vêm do chamador.
- Teto: **250 linhas de produção** somando os dois módulos.

## 3. `gate.py`

### 3.1 Tipos

- `Action`: `EXECUTE`, `CANCEL_ORDER`, `ARM`, `DISARM`, `DISCARD`, `RESUME`.
- `HumanDecision` (imutável, `extra="forbid"`): `action`, `ticket`, `nonce`, `issued_at`,
  `expires_at`, `digest`, `version`, `order_id`, `spec_digest`. Os quatro últimos são
  opcionais e seguem a tabela abaixo.
- `DecisionRefusal(ValueError)`.

| Ação | Prende, além de `ticket` e `nonce` | Campos que devem ser nulos |
|---|---|---|
| `EXECUTE` | `digest` e `version` da prévia | `order_id`, `spec_digest` |
| `ARM` | `digest` e `version` da prévia, e `spec_digest` do gatilho | `order_id` |
| `CANCEL_ORDER` | `order_id` | `digest`, `version`, `spec_digest` |
| `DISARM`, `DISCARD`, `RESUME` | nada mais | os quatro |

`version` entra junto do resumo porque o resumo não inclui a versão: editar de A para B e
voltar a A recupera o mesmo resumo (nota do DL3-PR01). Com a versão presa, a decisão antiga
não volta a valer.

### 3.2 Emissão

`issue(action, *, ticket, nonce, issued_at, expires_at, preview=None, order_id=None,
spec_digest=None) -> HumanDecision`. Recusa com `DecisionRefusal`:

| ID | Entrada | Motivo |
|---|---|---|
| I1 | `ticket` ou `nonce` vazio | identidade ausente |
| I2 | `issued_at` ou `expires_at` sem fuso | tempo inválido |
| I3 | `expires_at` igual ou anterior a `issued_at` | tempo inválido |
| I4 | `EXECUTE` sem `preview` | vínculo ausente |
| I5 | `ARM` sem `preview` ou sem `spec_digest` | vínculo ausente |
| I6 | `CANCEL_ORDER` sem `order_id` | vínculo ausente |
| I7 | `RESUME` (ou `DISARM`, `DISCARD`) com `preview`, `order_id` ou `spec_digest` | vínculo indevido |
| I8 | `EXECUTE` com `order_id` ou `spec_digest` | vínculo indevido |

Em D0 a emissão é uma função local. Autenticação real é D2 e não entra aqui.

### 3.3 Consumo

`DecisionLedger().consume(decision, *, action, ticket, now, preview=None, order_id=None,
spec_digest=None) -> None`. Confere **nesta ordem** e recusa no primeiro que falhar:

1. ação diferente da pedida ⇒ "ação divergente";
2. boleta diferente ⇒ "boleta divergente";
3. `now` antes de `issued_at` ⇒ "decisão ainda não válida";
4. `now` depois de `expires_at` ⇒ "decisão vencida" (igual a `expires_at` ainda vale);
5. `nonce` já consumido neste livro ⇒ "decisão já usada";
6. vínculo: resumo ⇒ "resumo divergente"; versão ⇒ "versão divergente"; ordem ⇒ "ordem
   divergente"; gatilho ⇒ "gatilho divergente", nessa ordem.

Só o consumo **aceito** marca o `nonce` como usado. Recusa não consome.

### 3.4 Tabela de consumo

Boleta de referência `T1`: compra de A, 10 a 1,00; venda de B, 10 a 1,50; prévia `P1` com
versão 1. Decisão `X1 = issue(EXECUTE, ticket="T1", nonce="n1", issued_at=14:00,
expires_at=14:05, preview=P1)`. Toda "decisão nova" abaixo é igual a `X1`, trocando só o
`nonce` e o que a linha disser. Salvo indicação, o consumo é às 14:01, para `T1`, com `P1`.

| ID | Consumo | Esperado |
|---|---|---|
| K1 | `X1`, `EXECUTE`, `T1`, 14:01, `P1` | aceita |
| K2 | `X1` de novo, mesmos argumentos | recusa: decisão já usada |
| K3 | decisão nova (`n2`), às 14:05:00 exatos | aceita |
| K3b | decisão nova (`n3`), às 14:05:00,000001 | recusa: decisão vencida |
| K4 | decisão nova (`n4`), às 13:59:59 | recusa: decisão ainda não válida |
| K4b | decisão nova (`n4b`), às 14:00:00 exatos | aceita |
| K5 | decisão nova (`n5`) emitida para `P1`; no consumo, apresenta-se a prévia com o limite da compra editado para 0,99 (versão 2) | recusa: resumo divergente |
| K6 | decisão nova (`n6`) emitida para `P1`; no consumo, apresenta-se a prévia depois de editar a quantidade 10 → 20 → 10 (versão 3, **mesmo resumo de `P1`**) | recusa: versão divergente |
| K7 | decisão nova (`n7`), consumida para a boleta `T2` | recusa: boleta divergente |
| K8 | decisão nova (`n8`) de `EXECUTE`, consumida como `CANCEL_ORDER` | recusa: ação divergente |
| K9 | `CANCEL_ORDER` da ordem `o1` (`n9`), consumida para `o2` | recusa: ordem divergente |
| K9b | a mesma decisão `n9`, consumida para `o1` | aceita (a recusa de K9 não consumiu) |
| K10 | `ARM` com `spec_digest = "aaa"` (`n10`), consumida com `"bbb"` | recusa: gatilho divergente |
| K11 | duas decisões diferentes com o mesmo `nonce = "n11"`: a primeira é aceita | a segunda recusa: decisão já usada |
| K12 | decisão vencida **e** de outra boleta | recusa: boleta divergente (a ordem das conferências) |

K5 e K6 foram conferidos em `main`: a edição do limite muda o resumo e leva à versão 2; a
ida e volta da quantidade leva à versão 3 com o resumo original.

## 4. `trigger.py`

### 4.1 Tipos

- `TriggerSpec` (imutável): `symbol`, `source ∈ {BID, ASK, SIMPLE_TRADE, STRATEGY_TRADE}`,
  `direction ∈ {AT_OR_ABOVE, AT_OR_BELOW}`, `threshold` (preço no passo de 0,01, positivo),
  `min_size` (inteiro ≥ 1), `armed_until` (instante com fuso).
- `spec_digest(spec) -> str`: SHA-256 de uma forma canônica. Propriedades exigidas: mesmo
  resumo para `Decimal("1.00")` e `Decimal("1.0")` e para o mesmo instante em fusos
  diferentes; resumo diferente quando qualquer um dos seis campos muda.
- `TriggerState`: `ARMED`, `FIRED`, `EXPIRED`, `DISARMED`.
- `Outcome`: `NONE`, `FIRED`, `EXPIRED`.
- `TriggerRefusal(ValueError)`.

### 4.2 Regras

`Trigger(spec).arm(book, now)`, depois `on_event(event, book) -> Outcome` para cada evento
do replay. **O chamador aplica `book.advance(event)` antes de `on_event`.**

1. **Armar** confere **nesta ordem** e recusa no primeiro que falhar: `now` igual ou
   depois de `armed_until` ("prazo vencido"); não há foto do símbolo ("sem cotação"); foto
   com `sequence_ok` falso ("perda de sequência"); fase diferente de `CONTINUOUS` ("fora do
   contínuo"); livro travado ou cruzado, `bid >= ask` com os dois lados presentes ("livro
   inválido"); fonte `BID` ou `ASK` com **a condição já verdadeira** na foto ("condição já
   verdadeira").
2. Para fonte de negócio (`SIMPLE_TRADE`, `STRATEGY_TRADE`) não existe "já verdadeira": o
   livro não guarda negócio. Arma, e dispara no primeiro negócio qualificado depois.
3. **Só dispara em `ARMED`.** Dispara uma vez. Depois de `FIRED`, `EXPIRED` ou `DISARMED`,
   `on_event` devolve `NONE` para sempre. Não rearma.
4. **Expira** no primeiro evento com `ts` **depois** de `armed_until`. Evento com `ts`
   igual a `armed_until` ainda é avaliado.
5. **Dado inválido não dispara** e mantém `ARMED`. A validade é julgada na **foto atual do
   símbolo do gatilho**, para qualquer fonte: foto ausente; `sequence_ok` falso; fase
   diferente de `CONTINUOUS`; livro travado ou cruzado (`bid >= ask` com os dois lados
   presentes). Vale também para fonte de negócio: negócio com o símbolo em leilão não
   dispara.
6. **Condição**, avaliada só em evento do símbolo e da fonte do gatilho:
   - `BID`: `QuoteEvent` com `bid` presente, `bid_size >= min_size` e `bid` contra o limiar;
   - `ASK`: `QuoteEvent` com `ask` presente, `ask_size >= min_size` e `ask` contra o limiar;
   - `SIMPLE_TRADE`: `TradeEvent` com `kind = SIMPLE`, `size >= min_size`, `price` contra o
     limiar;
   - `STRATEGY_TRADE`: `TradeEvent` com `kind = STRATEGY`, idem.
   `AT_OR_BELOW`: valor `<=` limiar. `AT_OR_ABOVE`: valor `>=` limiar.
7. `disarm()` leva a `DISARMED` a partir de `ARMED`; em qualquer outro estado, recusa.
8. **O gatilho não envia, não reserva, não grava recibo e não consome decisão.** Só devolve
   o resultado. Quem age é o motor (DL3-PR05b), e só depois de nova decisão humana.

### 4.3 Tabela de armar

Gatilho `G`: símbolo A, fonte `ASK`, `AT_OR_BELOW`, limiar 1,00, `min_size` 10,
`armed_until` 15:00. `now` = 14:00 salvo indicação.

| ID | Livro de A ao armar | Esperado |
|---|---|---|
| A1 | bid 0,95 × 50, ask 1,02 × 50, `CONTINUOUS` | arma |
| A2 | ask 1,00 × 50 | recusa: condição já verdadeira |
| A3 | ask 1,00 × 9 | arma (tamanho abaixo do mínimo: a condição não é verdadeira) |
| A4 | sem foto de A | recusa: sem cotação |
| A5 | foto com `sequence_ok` falso | recusa: perda de sequência |
| A6 | fase `AUCTION` | recusa: fora do contínuo |
| A7 | livro de A1, `now` = 15:00 | recusa: prazo vencido |
| A8 | fonte `STRATEGY_TRADE`, livro de A1 | arma |
| A9 | bid 1,00 × 50, ask 1,00 × 50 | recusa: livro inválido (antes de "condição já verdadeira") |

### 4.4 Tabela de eventos

Cada linha parte do gatilho `G` recém-armado sobre o livro de A1, salvo indicação. Horário
do evento 14:30 salvo indicação.

| ID | Evento | Resultado | Estado depois |
|---|---|---|---|
| E1 | cotação de A, ask 1,01 × 50 | `NONE` | `ARMED` |
| E2 | cotação de A, ask 1,00 × 50 | `FIRED` | `FIRED` |
| E3 | cotação de A, ask 1,00 × 9 | `NONE` | `ARMED` |
| E4 | cotação de A, ask 0,99 × 10 | `FIRED` | `FIRED` |
| E5 | cotação de B, ask 0,90 × 50 | `NONE` | `ARMED` |
| E6 | cotação de A, ask 0,99 × 50, fase `AUCTION` | `NONE` | `ARMED` |
| E7 | cotação de A, ask 0,99 × 50, com lacuna de sequência antes | `NONE` | `ARMED` |
| E7b | depois de E7, outra cotação de A, ask 0,99 × 50, sem lacuna | `NONE` | `ARMED` |
| E8 | cotação de A, bid 1,00, ask 1,00 | `NONE` | `ARMED` |
| E9 | negócio de A a 0,90 × 100, `SIMPLE` | `NONE` | `ARMED` |
| E10 | cotação de A, ask 0,99 × 50, às 15:00:00 exatos | `FIRED` | `FIRED` |
| E11 | cotação de A, ask 0,99 × 50, às 15:00:00,000001 | `EXPIRED` | `EXPIRED` |
| E12 | depois de E2, cotação de A, ask 0,98 × 50 | `NONE` | `FIRED` |
| E13 | depois de E11, cotação de A, ask 0,98 × 50 | `NONE` | `EXPIRED` |
| E14 | `disarm()`, depois cotação de A, ask 0,99 × 50 | `NONE` | `DISARMED` |
| E15 | fonte `STRATEGY_TRADE`, limiar 0,50, `min_size` 1: negócio de A a 0,45 × 5, `SIMPLE` | `NONE` | `ARMED` |
| E16 | mesmo gatilho de E15: negócio de A a 0,45 × 5, `STRATEGY` | `FIRED` | `FIRED` |
| E17 | fonte `SIMPLE_TRADE`, limiar 0,50, `min_size` 1: negócio de A a 0,45 × 5, `STRATEGY` | `NONE` | `ARMED` |
| E18 | mesmo gatilho de E17: negócio de A a 0,45 × 5, `SIMPLE` | `FIRED` | `FIRED` |
| E19 | fonte `BID`, `AT_OR_ABOVE`, limiar 1,50, `min_size` 10, símbolo B, livro inicial de B: bid 1,45 × 50, ask 1,60 × 50. Cotação de B, bid 1,49 × 50, ask 1,60 × 50 | `NONE` | `ARMED` |
| E20 | mesmo gatilho de E19: cotação de B, bid 1,50 × 50, ask 1,60 × 50 | `FIRED` | `FIRED` |
| E21 | fonte `STRATEGY_TRADE` como E15: negócio de A a 0,45 × 5, `STRATEGY`, **com lacuna de sequência antes** | `NONE` | `ARMED` |
| E22 | fonte `STRATEGY_TRADE` como E15: cotação de A em `AUCTION`; depois negócio de A a 0,45 × 5, `STRATEGY` | `NONE`; `NONE` | `ARMED` |

E7b: a perda de sequência é permanente no replay, então o gatilho fica armado e mudo até
expirar. E15 a E18 são o cenário S12 do SDD. E21: negócio também não dispara depois de
perda de sequência, porque a foto do símbolo fica com `sequence_ok` falso.

Comportamento de `BookView` conferido em `main`: negócio não altera a foto; a lacuna marca
a foto como `sequence_ok` falso e isso persiste nas cotações seguintes.

## 5. Arquitetura

Acrescente a `tests/architecture/test_ticket_boundaries.py`:

1. Em `backend/`, fora de `ticket/gate.py`, nenhum módulo importa nem chama `issue` de
   `ticket.gate`, nem constrói `HumanDecision(...)` diretamente. (O CLI vai precisar de
   `issue` no DL3-PR06; a exceção entra naquele cartão.)
2. `ticket/trigger.py` não importa diretamente `ticket.venue`, `ticket.paper_venue`,
   `ticket.sequencing`, `ticket.receipt` nem `ticket.gate`, e não contém chamada a
   atributo de nome `submit`, `request_cancel` ou `reserve`.

As regras existentes (rede, LLM, MCP, relógio, sorteio) continuam valendo com os dois
módulos novos.

## 6. Testes e mutantes

- Um teste por linha das tabelas I, K, A e E, com o esperado literal.
- `spec_digest`: as propriedades do §4.1, um teste por campo.

Mutantes que devem morrer, um por vez, listados na descrição do PR:

1. gate: aceitar `nonce` repetido;
2. gate: recusa consumir o `nonce` (morre em K9b);
3. gate: `>` por `>=` no vencimento (K3) e `<` por `<=` no início (K4, com um caso em
   `issued_at` exato, que deve ser aceito);
4. gate: não comparar a versão (K6); não comparar o resumo (K5);
5. gate: não comparar a boleta (K7); a ação (K8); a ordem (K9); o gatilho (K10);
6. gate: trocar a ordem das conferências (K12);
7. gate: cada linha de I1 a I8 removida;
8. trigger: armar com condição já verdadeira (A2);
9. trigger: ignorar `min_size` (A3, E3);
10. trigger: disparar em leilão (E6, E22), com sequência perdida (E7, E21), em livro travado
    (E8); armar com livro travado (A9);
11. trigger: disparar por evento de outra fonte (E9, E15, E17) ou de outro símbolo (E5);
12. trigger: `>` por `>=` na expiração (E10, E11);
13. trigger: disparar duas vezes (E12); rearmar depois de expirar (E13);
14. trigger: inverter a direção (E19, E20).

## 7. Critérios de parada

Pare e relate se: algum esperado não reproduzir com a regra escrita; for preciso tocar em
arquivo fora de `gate.py`, `trigger.py`, seus testes, o teste de arquitetura e o cartão; o
total passar de 250 linhas de produção.

## 8. Entrega

1. Commit vermelho com as tabelas; depois o verde.
2. Portão completo em clone limpo no Mac. O revisor roda o Linux.
3. Descrição do PR: cabeça, contagens, linhas por arquivo, mutantes, desvios.
4. Copie este cartão para `docs/specs/derivatives/fase3/DL3-PR05a.md`. Não edite
   `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` na cabeça publicada e os dois relatórios fora do Git, com
   SHA-256 na descrição. PR em rascunho.

## Revisão e integração — 22/11/2026 (Claude)

Cabeça `ea16d77`: **GO** na primeira rodada, formado antes de ler os relatórios da skill.
Nenhuma parada por erro do cartão e nenhum teste do revisor acrescentado.

| Verificação do revisor, clone limpo, Linux x86_64 | Resultado |
|---|---|
| Pytest sem integração | 11.093 aprovados, 16 pulados, 261 subtestes |
| `mypy backend/ --strict` e `pyright backend/` | 0 erros |
| Linhas de produção | 247, teto de 250 |
| Cartão copiado | idêntico ao publicado |
| 36 mutantes do revisor nos dois módulos | todos mortos |

Relatórios da skill lidos depois do parecer formado, com SHA-256 conferidos
(`fcccd94d…6f2d` e `aba066ea…c19a`): seguir para revisão humana, sem bloqueante.
