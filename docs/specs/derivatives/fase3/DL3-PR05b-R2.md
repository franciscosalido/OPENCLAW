# DL3-PR05b-R2 — Supercartão de correção: identidade das ordens e lacunas de teste

**Data:** 22/11/2026 · **Autor:** Claude · **Para:** Codex
**PR:** #161, mesma branch, em rascunho · **Cabeça revisada:** `79e49f8` · **Base:** `main` = `e48e8ac`
**Complementa** o `DL3-PR05b.md` e o `DL3-PR05b-R1.md`. O que este cartão não cita continua
valendo como está neles.

---

## 0. Parecer

**NO-GO, por pouco.** Os quatro bloqueantes do R1 estão corrigidos: refiz minhas quatro
sondas e nenhuma reproduz mais. Portão no Linux sobre `79e49f8`: 11.150 aprovados, 16
pulados; mypy estrito e Pyright com zero erros. Rodei 47 mutantes meus: 39 morrem, 8
sobrevivem. Li os relatórios da skill depois (SHA-256 conferido).

| Nível | Id | Achado | Quem achou |
|---|---|---|---|
| Crítico | — | nenhum | |
| Bloqueante | B5 | Boleta `T` com símbolo `X:A` e boleta `T:X` com símbolo `A` geram o mesmo `order_id` | skill; reproduzi |
| Regra do repositório | N2 | `AccountHalts.hold` e `release` sem docstring; linhas acima de 100 colunas | skill e revisor |
| Lacuna de teste | G1–G8 | nove mutantes sobrevivem (cinco da skill, quatro só meus) | skill e revisor |
| Sugestão | S1 | campo `_account` duplicado | skill; opcional |

**B5 é lacuna do meu cartão:** o DL3-PR05b fixou o formato `"{ticket}:{símbolo}:{n}"` sem
restringir os caracteres. Nenhuma lacuna G1–G8 é defeito: a produção atual já dá o
resultado esperado em todas.

## 1. Arquivos e limites

| Arquivo | Mudança |
|---|---|
| `backend/derivatives/ticket/engine.py` | R17 (§2), duas docstrings, linha 279 em ≤ 100 colunas. Continua ≤ 400 linhas (hoje 379) |
| `tests/unit/derivatives/ticket/test_engine.py` | I1–I3, G1, G2, G5, G7, G8, novos; linhas 17 e 411 em ≤ 100 colunas |
| `tests/unit/derivatives/ticket/test_sequencing.py` | G3, G4, G6, novos |

- Nenhum outro arquivo muda. `sequencing.py` e `state.py` ficam como estão.
- Nenhum esperado de teste existente muda. Se algum precisar mudar, pare e relate.
- Teto do PR continua em 480 linhas de produção (hoje 421).

## 2. Regra nova do motor

**R17 — Identificadores sem separador.** O `order_id` continua `"{ticket}:{símbolo}:{n}"`.
Para ele ser único, o id da boleta e o símbolo de cada perna só podem ter letras, dígitos,
`_`, `.` e `-`, com pelo menos um caractere (`^[A-Za-z0-9._-]+$`).

- Id de boleta fora da regra: `EngineRefusal` **no construtor** de `TicketEngine`.
- Símbolo de perna fora da regra: `EngineRefusal` em `propose`, **antes** de `plan_legs` e
  de qualquer registro no recibo.

**N2.** Docstring em `AccountHalts.hold` e em `AccountHalts.release`. Nenhuma linha acima de
100 colunas nos arquivos do §1.

**S1** continua opcional.

## 3. Sessão de referência

A do DL3-PR05b §5 e os acréscimos do R1 §4 (`P`, `P′`, `D10`, boleta de referência).
Acréscimos deste cartão:

- **Posição `Q`:** A = +10, B = −10, C = +10, D = −10; pares (A protege B) e (C protege D).
- **`D10cd`:** vende C 10 a 1,00, compra D 10 a 1,50; `net_limit` +5,00; `gross_cap` 25,00.
- Evento "com os valores da abertura": A 0,95 × 50 / 1,02 × 50; B 1,45 × 50 / 1,55 × 50.
- 15:00:00 é o prazo de envio da sessão de referência.

## 4. Cenários, com o esperado

### 4.1 Identidade (código novo)

| # | Passos | Esperado |
|---|---|---|
| I1 | construir `TicketEngine` com id `"T:X"`; com `"T#1"`; com `"T 1"`; com `""` | `EngineRefusal` no construtor, nas quatro |
| I2 | motor com id `"T-1_a.b"`; propõe a boleta de referência; confirma às 14:00:02 | proposta e confirmação aceitas; `orders` tem a chave `T-1_a.b:A:1` |
| I3 | motor `"T1"`; posição com `X:A` = 0 e B = 0, par (`X:A` protege B); propõe compra de `X:A` 10 a 1,00 e venda de B 10 a 1,50 | `EngineRefusal`; `preview` é `None`; recibo sem nenhum registro |

### 4.2 Lacunas de teste (a produção atual já passa em todas)

| # | Passos | Esperado |
|---|---|---|
| G1 | `T1` e `T2` com `D10` e `P`; evento `timeout` (`submit`, **não** registrada) às 14:00:02; `T1` confirma; `reconcile` de `T1:B:1` às 14:00:03; `T2` confirma às 14:00:03 | Depois da confirmação: `T1` `UNCERTAIN`, conta bloqueada. Depois do `reconcile`: `poll` devolve `None`; `T1:B:1` `REJECTED`; `T1` `STOPPED`; conta liberada. `T2` é aceita e `T2:B:1` fica `LIVE` |
| G2 | `T1` com `D10` e `P` confirma; evento de B às 21:00:00 com os valores da abertura; depois, `admissible(D10 com P, T2)` direto no livro da sessão | `T1:B:1` `EXPIRED`; `T1` `STOPPED`; o `admissible` é aceito |
| G3 | livro novo: `admit(D10 com P, T1)`; `admit(D10 com P na conta sim2, T2)` | os dois são aceitos |
| G4 | livro novo: `admit(D10 com Q, T1)`; `admit(D10cd com Q, T2)` | os dois são aceitos |
| G5 | livro de teste cuja `confirm_release` sempre levanta `SequenceRefusal`; `T1` de referência confirma; ev3 A ask 1,00; `cancel` de `T1:B:1` às 14:00:03; ev4 B com os valores da abertura | Antes do `cancel`: `T1:A:1` `FILLED`, `T1:B:1` `LIVE`. Depois do ev4, sem exceção: `T1:B:1` `CANCELLED`, igual ao `poll` (`CANCELLED`, 0 executadas, 0 de saldo); no recibo, `VENUE_CANCELLED` e, logo depois, `DIVERGENCE` e `STOP`; `halts.blocked("sim")` verdadeiro; `verify()` verdadeiro; boleta `STOPPED` |
| G6 | livro novo: `admit(D10 com P, T1)`; `admissible(D10 com P′, T2)` | o `admissible` recusa com `SequenceRefusal` ("foto divergente; conciliação necessária") |
| G7 | `T1` de referência proposta; `pause` às 14:00:02; confirma às 14:00:02 | `EngineRefusal`; boleta `DRAFT`; `orders` vazio; decisão não gasta; recibo só com `PREVIEW` e `PAUSE` |
| G8 | `T1` de referência confirma; ev3 A ask 1,00 **às 15:00:00**; ev4 B com os valores da abertura, **também às 15:00:00** | Depois do ev3: compra `FILLED`; nenhuma venda (a cotação de B está vencida); boleta `WORKING`; 1 envio no total. Depois do ev4: venda `T1:B:1` de 10 a 1,50 enviada com horário 15:00:00; boleta `WORKING` |

Como conferi: executei G1 a G8 contra `79e49f8` com as peças reais e todos dão exatamente
o esperado acima. I1 a I3 dependem de código novo; conferi que a cabeça atual **aceita** a
proposta de I3 (é o que a R17 passa a recusar) e que `"T-1_a.b"` é texto válido para a
decisão. Esperado que não reproduzir: **pare e relate**.

## 5. Mutantes que devem morrer, um por vez

1. `reconcile` resolvendo para `REJECTED` sem contabilizar no livro (G1);
2. compra `EXPIRED` sem `settle_buy` (G2);
3. ocupação ignorando a conta (G3);
4. ocupação ignorando o símbolo (G4);
5. recusa do livro ignorada quando o relatório não tem execução (G5);
6. `admit` sem registrar plano e foto (G6);
7. `confirm` ignorando a pausa (G7);
8. prazo de envio exclusivo no envio, `>=` no lugar de `>` (G8, ev4);
9. prazo de envio exclusivo no fechamento, `<` no lugar de `<=` (G8, ev3);
10. construtor sem conferir o id da boleta (I1);
11. `propose` sem conferir o símbolo (I3).

Os 20 grupos do DL3-PR05b e os 18 do R1 continuam obrigatórios na cabeça nova.

## 6. Critérios de parada

Pare e relate se: algum esperado do §4 não reproduzir; algum esperado de teste existente
precisar mudar; `engine.py` passar de 400 linhas; for preciso tocar em arquivo fora do §1.

## 7. Limitação registrada (não corrigir neste PR)

O id da boleta precisa ser único na sessão inteira, em todas as contas. Quem cria os
motores garante isso. O DL3-PR06 (replay por linha de comando) vai recusar id repetido.

## 8. Entrega

1. Mesma branch e mesmo PR #161, em rascunho. Commit vermelho com I e G; depois o verde.
   No vermelho só I1 e I3 falham: G1 a G8 e I2 já passam, e isso é o esperado.
2. Portão completo em clone limpo no Mac. O revisor roda o Linux.
3. Descrição do PR atualizada: cabeça, contagens, linhas de produção, mutantes (20 + 18 + 11).
4. Copie este cartão para `docs/specs/derivatives/fase3/DL3-PR05b-R2.md`. Não edite
   `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça nova, relatórios fora do Git,
   SHA-256 na descrição.
