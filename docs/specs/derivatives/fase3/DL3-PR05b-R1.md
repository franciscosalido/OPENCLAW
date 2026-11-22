# DL3-PR05b-R1 — Supercartão de correção do motor da boleta

**Data:** 21/11/2026 · **Autor:** Claude · **Para:** Codex
**PR:** #161, mesma branch, em rascunho · **Cabeça revisada:** `3f4d4e1` · **Base:** `main` = `e48e8ac`
**Complementa** o `DL3-PR05b.md`. O que este cartão não cita continua valendo como está lá.

---

## 0. Parecer e origem dos achados

**NO-GO.** Portão no Linux sobre `3f4d4e1`: 11.132 aprovados, 16 pulados; mypy estrito e
Pyright com zero erros. Os 30 cenários do DL3-PR05b passam. Reproduzi os bloqueios com as
peças reais antes de ler os relatórios da skill (SHA-256 conferido).

B1, B2 e B4 são **lacunas do meu cartão**, não erro de implementação: o DL3-PR05b não previa
duas boletas disputando a mesma recompra, não mandava conferir a foto da posição antes de
gastar a decisão e não dizia o que fazer com venda rejeitada.

| Nível | Id | Achado | Quem achou |
|---|---|---|---|
| Crítico | — | nenhum | |
| Bloqueante | B1 | Duas desmontagens da mesma posição vendida de 10 enviam 20 de recompra; a segunda execução não entra no recibo | skill e revisor |
| Bloqueante | B2 | Foto de posição divergente só é recusada depois de gastar o `nonce` e enviar a compra | skill e revisor |
| Bloqueante | B3 | Recusa do livro ao aplicar um relatório derruba o lote, perde o fato da venue e deixa `reconcile` sem saída | skill e revisor |
| Bloqueante | B4 | Venda rejeitada pela venue é reenviada a cada chamada (8 ordens de venda em 4 eventos) | revisor |
| Não bloqueante | N1 | O motor mexe no atributo privado `_pending` de `AccountHalts` | revisor |
| Lacuna de teste | L1, L2, L3 | três mutantes sobrevivem (L3 é o "A1" do relatório v0.2) | skill |
| Sugestão | S1 | campo `_account` duplica `self._position.account` | skill; opcional |

## 1. Arquivos e limites

| Arquivo | Mudança |
|---|---|
| `backend/derivatives/ticket/sequencing.py` | três métodos novos em `ReservationBook` e uma condição em `confirm_buy` (§2). Arquivo ≤ 360 linhas (hoje 299) |
| `backend/derivatives/ticket/engine.py` | regras do §3. Continua ≤ 400 linhas (hoje 351) |
| `backend/derivatives/ticket/state.py` | só `Event.DIVERGENCE = "divergence"`. Nenhuma linha nas tabelas de transição |
| `tests/unit/derivatives/ticket/test_sequencing.py` | K1–K7, novos |
| `tests/unit/derivatives/ticket/test_engine.py` | C1–C6 e L1–L3, novos |
| `tests/architecture/test_ticket_boundaries.py` | regra de N1 (§3) |

- **Nenhum esperado de teste existente muda.** Se algum precisar mudar, pare e relate.
- Teto deste PR: **480 linhas de produção** (hoje 353). O teto sobe por este cartão, porque a
  correção toca dois módulos. Não divida o PR e não comprima linhas. Passou do teto: pare e
  relate a contagem.
- Nenhum outro módulo muda.

## 2. Livro de reservas: admissão e ocupação de compra

**Ocupação** = quanto uma boleta ainda pode comprar de um símbolo. Chave: (conta, boleta,
símbolo). Três métodos novos em `ReservationBook`:

```python
def admissible(self, plan: LegPlan, *, ticket: str) -> None: ...
def admit(self, plan: LegPlan, *, ticket: str) -> None: ...
def settle_buy(self, account: str, ticket: str, symbol: str) -> None: ...
```

**A1 — `admissible`.** Sob a trava do livro: faz as checagens de `_check(plan, ticket)`; e,
para cada perna de **compra** cujo saldo inicial do símbolo é **negativo** (recompra), exige

`ocupação das outras boletas da conta naquele símbolo + leg.quantity ≤ −saldo inicial`.

Falhou qualquer checagem: `SequenceRefusal`. **Não registra nada**, aceitando ou recusando.

**A2 — `admit`.** Mesmas checagens de A1. Recusando, não registra nada. Aceitando, registra
o plano e a foto (o que `_remember` faz hoje) e grava a ocupação de **cada** perna de compra
do plano = `leg.quantity`. Repetir `admit` para a mesma boleta e o mesmo plano é aceito e
não soma ocupação.

**A3 — `settle_buy`.** A ocupação daquela (conta, boleta, símbolo) passa a ser **o que a
boleta já comprou** naquele símbolo. Sem ocupação registrada: `SequenceRefusal`.

**A4 — `confirm_buy`.** Quando existe ocupação para a (conta, boleta, símbolo),
`total + quantity` não pode passar dela; passou: `SequenceRefusal`. Quando não existe
(boleta nunca admitida), vale exatamente o comportamento de hoje.

Compra de abertura (saldo inicial ≥ 0) não tem teto entre boletas: S09 continua igual.

## 3. Motor

**R4 — Confirmar (substitui a lista do DL3-PR05b).** Itens 1 a 6 iguais. Depois:

7. `reservations.admissible(plan, ticket=…)`;
8. `ledger.consume(…)`, que continua sendo a última checagem.

Passando as oito: `reservations.admit(plan, ticket=…)` e só então `CONFIRM`, `START` e os
envios. Se `admit` recusar nesse ponto (não acontece no replay síncrono), a recusa sobe e
**nada é enviado**.

**R6 — Relatórios (substitui).** Para cada relatório de ordem desta boleta, nesta ordem:

1. **o fato primeiro:** aplica `transition` ao estado da ordem, soma o executado e grava o
   relatório no recibo;
2. **depois o livro:** execução de compra ⇒ `confirm_buy`; execução de venda ⇒
   `confirm_sale`; venda em estado final com saldo ⇒ `confirm_release` do saldo; compra em
   estado final (`FILLED`, `CANCELLED`, `EXPIRED`, `REJECTED`) ⇒ `settle_buy`;
3. se o livro recusar (`SequenceRefusal`) em qualquer chamada do passo 2 ⇒ R15, e as
   chamadas de livro que faltavam **daquele relatório** não são tentadas.

O retorno de `venue.submit` é um relatório e segue esta regra. Depois de aplicar o lote,
tenta envios (R5) e fecha (R7).

**R15 — Divergência contábil (nova).** Quando o livro recusa no passo 2 da R6:

- o fato fica: estado da ordem e executado iguais aos da venue, relatório no recibo;
- grava `DIVERGENCE` no recibo, com o `order_id`, **logo depois** daquele relatório;
- a conta entra em bloqueio que o motor **não libera** nesta sessão;
- **nenhuma exceção** sai de `confirm`, `on_reports`, `on_market`, `resume` ou `reconcile`
  por esse motivo; os demais relatórios do lote são aplicados normalmente.

**R9 — Estado incerto (ajuste).** `reconcile` aplica os relatórios guardados pela R6, com a
R15 valendo. Terminando, a ordem deixa de estar `UNCERTAIN` e a marca de incerteza
**daquela ordem** sai de `halts`; o bloqueio da R15, se houve, permanece. Resolução para
`REJECTED` conta como estado final no passo 2 da R6. O resto da R9 não muda.

**R16 — Rejeição é definitiva (nova).** Perna que já teve uma ordem `REJECTED` não recebe
novo envio. Na R7, essa perna não conta em "ainda pode haver envio".

**N1 — `AccountHalts` com interface pública.**

```python
class AccountHalts:
    def blocked(self, account: str) -> bool: ...
    def hold(self, account: str, key: str) -> None: ...
    def release(self, account: str, key: str) -> None: ...
```

`blocked` é verdadeiro enquanto a conta tiver alguma chave em `hold`. A incerteza usa o
`order_id` como chave. A divergência (R15) usa uma chave própria, que o motor nunca passa a
`release`. Regra de arquitetura nova: em `engine.py`, todo acesso a atributo iniciado por
`_` tem como objeto o nome `self` (em `x._y`, `x` é `self`). Nomes entre dois sublinhados
(`__nome__`) ficam fora da regra.

**S1** é opcional. Se aplicar, nenhum esperado muda.

## 4. Sessão de referência

A do DL3-PR05b §5 (abertura, horários, decisões válidas de 14:00:00 a 15:00:00, confirmação
às 14:00:02 salvo indicação). Acréscimos:

- **Posição `P`:** A = +10, B = −10, par (A protege B).
- **`D10`** (a boleta de S21): vende A 10 a 1,00, compra B 10 a 1,50; `net_limit` +5,00;
  `gross_cap` 25,00. **`D6`** e **`D7`**: iguais, com quantidade 6 e 7 nas duas pernas;
  `net_limit` +3,00 e +3,50; `gross_cap` 15,00 e 17,50. `plan_legs` aceita as três com `P`.
- **Posição `P′`:** A = +12, B = −10, mesmo par. `plan_legs` aceita `D10` com `P′`.
- **Boleta de referência** = a `T1` do DL3-PR05b (compra A 10 a 1,00, vende B 10 a 1,50;
  posição A = 0, B = 0).
- **Livro de teste:** subclasse de `ReservationBook` cuja **primeira** chamada a
  `confirm_buy` levanta `SequenceRefusal`; as demais chamadas seguem o livro real.
- Nos esperados, nome com `VENUE_` é relatório; os demais são estado no motor.

## 5. Cenários, com o esperado

### 5.1 Livro (`test_sequencing.py`), conta `sim`, livro novo em cada cenário

| # | Passos | Esperado |
|---|---|---|
| K1 | `admit(D10 com P, T1)`; `admissible(D10 com P, T2)` | a segunda recusa (`SequenceRefusal`) |
| K2 | `admit(D10 com P, T1)`; `confirm_buy` de 4 de B para T1; `settle_buy("sim", "T1", "B")`; `admissible(D6 com P, T2)`; `admissible(D7 com P, T2)` | `D6` é aceita (4 + 6 = 10); `D7` recusa (4 + 7 = 11) |
| K3 | K2 até o `settle_buy`; `confirm_buy` de mais 1 de B para T1 | recusa |
| K4 | `admissible(D10 com P, T1)`; `admissible(D10 com P′, T2)` | as duas são aceitas (a primeira não registrou foto) |
| K5 | `admit` da boleta de referência para T1 e depois para T2 | as duas são aceitas |
| K6 | `admit(D10 com P, T1)` duas vezes; `admissible(D10 com P, T1)` | as três são aceitas |
| K7 | `admit(D10 com P, T1)`; `admit(D10 com P, T2)`; `settle_buy("sim", "T2", "B")` | o segundo `admit` recusa; o `settle_buy` recusa (nada foi registrado para T2) |

### 5.2 Motor (`test_engine.py`)

| # | Passos depois da abertura | Esperado |
|---|---|---|
| C1 (B1) | `T1` e `T2`, as duas com `D10` e `P`, mesma conta e mesmo livro; `T1` confirma; `T2` confirma; ev3 B ask 1,50 | `T1` aceita e envia `T1:B:1`. `T2` recusa com `SequenceRefusal`, segue `DRAFT`, `orders` vazio, decisão não gasta; até aqui `submit` foi chamado 1 vez. Depois do ev3, sem exceção: `T1:B:1` `FILLED`; venda `T1:A:1` de 10 a 1,00 enviada; `submit` chamado 2 vezes no total |
| C2 (B1) | C1 até a recusa de `T2`; `cancel` de `T1:B:1`; ev3 B com os valores da abertura; `T2` confirma às 14:00:03 **com a mesma decisão** | No ev3 chega `VENUE_CANCELLED`; `T1:B:1` `CANCELLED`; `T1` `STOPPED`. `T2` é aceita e envia `T2:B:1` de 10 a 1,50 |
| C3 (B2) | `T1` de referência confirma; ev3 A ask 1,00; `T2` = boleta de referência com posição A = +5, B = 0 na mesma conta; `T2` confirma às 14:00:03 | `T2` recusa com `SequenceRefusal` ("foto divergente; conciliação necessária"), segue `DRAFT`, `orders` vazio, decisão não gasta; nenhum `submit` de ordem `T2:…` |
| C4 (B3) | livro de teste; `T1` de referência confirma; ev3 A ask 1,00; `T2` de referência confirma às 14:00:03 | O ev3 não levanta exceção. `T1:A:1` `FILLED`, igual ao `poll` (`FILLED`, 10 executadas, 0 de saldo). No recibo de `T1`: `VENUE_FILL` de 10 a "1.00" e, logo depois, `DIVERGENCE`; `verify()` verdadeiro. `halts.blocked("sim")` verdadeiro. Nenhuma venda enviada. `T1` `STOPPED`. `T2` recusa (`EngineRefusal`) sem gastar decisão |
| C5 (B3) | livro de teste; evento `timeout` (`submit`, registrada) às 14:00:02; `T1` de referência confirma; ev A ask 1,00 às 14:00:03; `reconcile` da compra; `reconcile` da compra de novo | O primeiro `reconcile` retorna sem exceção: compra `FILLED`, igual ao `poll`; no recibo, `VENUE_FILL` e, logo depois, `DIVERGENCE`; `verify()` verdadeiro; boleta `STOPPED`; `halts.blocked("sim")` verdadeiro. O segundo `reconcile` recusa (`EngineRefusal`) e nada muda |
| C6 (B4) | venue de teste que rejeita todo envio de **venda**; `T1` de referência confirma; ev3 A ask 1,00; ev4 B e ev5 A com os valores da abertura | Compra `FILLED`. Existe **uma única** ordem de venda, `T1:B:1`, `REJECTED`. Depois do ev3 a boleta já está `STOPPED`. ev4 e ev5 não geram ordem. Comprado 10, vendido 0 |
| L1 | `T1` de referência confirma; ev3 A ask 1,00 × 3; ev4 B bid 1,54; ev5 A ask 1,00 × 7 | A venda de 3 executa a **1,54**. Depois do ev5 a boleta está `STOPPED`: bruto projetado 10,00 + 4,62 + 10,50 = 25,12 > 25,00. Envios, só dois: `T1:A:1` de 10 e `T1:B:1` de 3 |
| L2 | S20, medindo **todas** as chamadas à venue (qualquer método) imediatamente antes e depois de `pause` | nenhuma chamada nova |
| L3 | `T1` de referência confirma; ev3 A ask 1,00 × 3; ev4 B bid 1,50 × 3; ev5 A ask 1,00 × 4; `cancel` de `T1:B:2` às 14:00:05; ev6 B bid 1,45 | Envios: `T1:A:1` de 10, `T1:B:1` de 3, `T1:B:2` de 4. `T1:B:1` `FILLED`; `T1:B:2` `CANCELLED`; `available` da venda = 4; boleta `WORKING`; `verify()` verdadeiro |

Como conferi: K e C1–C6 dependem de código que ainda não existe; os esperados seguem das
regras dos §2 e §3. Conferi contra `3f4d4e1` o que já existe: `plan_legs` de `D6`, `D7`,
`D10` e de `P′`; `VENUE_CANCELLED` no evento de B com cancelamento pendente; trava `OK` às
14:00:03 em C2 e C3; `available` = 0 sem compra creditada; o texto de recusa de C3; o
`poll` de C4 e C5. L1 e L3 foram executados na cabeça atual e já dão esse resultado.
Esperado que não reproduzir: **pare e relate**.

## 6. Mutantes que devem morrer, um por vez

1. `admissible` depois de `consume` (C1: decisão gasta);
2. pular `admissible` (C1 e C3);
3. `admissible` registrando plano ou foto (K4);
4. ocupação ignorando as outras boletas (K1);
5. ocupação contando a própria boleta (K6);
6. `settle_buy` zerando a ocupação em vez de baixá-la ao comprado (K2, `D7`);
7. não chamar `settle_buy` em compra cancelada (C2);
8. `confirm_buy` ignorando a ocupação (K3);
9. `admit` registrando mesmo quando recusa (K7);
10. recusa do livro descartando o fato da venue (C4);
11. recusa do livro levantando exceção (C4 e C5);
12. divergência sem bloquear a conta (C4, `T2`);
13. `reconcile` liberando o bloqueio da divergência (C5);
14. reenviar venda rejeitada (C6);
15. retirar a reavaliação de limites antes do envio (L1);
16. `pause` consultando a venue (L2);
17. liberar pelo total do símbolo em vez do saldo da ordem (L3);
18. motor acessando atributo privado de outro objeto (teste de arquitetura).

Os 20 grupos do DL3-PR05b continuam obrigatórios na cabeça nova.

## 7. Critérios de parada

Pare e relate se: algum esperado do §5 não reproduzir com as regras dos §2 e §3; algum
esperado de teste existente precisar mudar; `engine.py` passar de 400 linhas,
`sequencing.py` de 360 ou o PR de 480 de produção; for preciso tocar em arquivo fora do §1.

## 8. Limitações registradas (não corrigir neste PR)

- Ocupação de perna de compra que nunca foi enviada só sai no fim da sessão.
- O bloqueio da R15 não tem liberação: a saída é uma sessão nova com a posição conciliada.
- Relatório impossível da venue (transição inválida) ainda levanta exceção. A `PaperVenue`
  não emite isso (invariantes do DL3-PR04); o tratamento fica para o degrau D1.

## 9. Entrega

1. Mesma branch e mesmo PR #161, em rascunho. Commit vermelho com K, C e L; depois o verde.
2. Portão completo em clone limpo no Mac. O revisor roda o Linux.
3. Descrição do PR atualizada: cabeça, contagens, linhas de produção por arquivo, mutantes
   (os 20 grupos antigos e os 18 deste cartão), desvios.
4. Copie este cartão para `docs/specs/derivatives/fase3/DL3-PR05b-R1.md`. Não edite
   `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça nova, relatórios fora do Git,
   SHA-256 na descrição.
