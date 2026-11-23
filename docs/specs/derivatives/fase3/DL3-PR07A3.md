# DL3-PR07A3 — Supercartão: cada boleta vende coberta só pelas próprias compras

**Data:** 23/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `719cebb` (DL3-PR08E integrado) · **PR novo**, em rascunho
**Decisão que este cartão implementa:** resolução R-A de Francisco, de 22/11/2026: «Padrão: a
boleta usa só as compras dela mesma como cobertura.»

## 0. Escopo

**O que acontece hoje.** O livro de reservas soma as compras de proteção de **todas** as
boletas da conta. Uma boleta pode vender coberta por compra de outra, sem autorização e sem
registro de origem. Dois fatos conferidos no `main`:

- **Sobra de boleta parada.** A T1 compra 10 A, vende 6 B e para. A T2 (compra 10 A, vende
  10 B) é confirmada e envia na hora uma venda de 4 B, antes de qualquer compra dela
  executar.
- **Boleta pausada.** A T1 compra 10 A e está pausada. A T2 é confirmada e envia venda de 10
  B com a proteção da T1. Quando a T1 é retomada, não tem mais o que vender e vai a
  `STOPPED`.

**O que muda.** A venda de uma boleta só é liberada por compras executadas **dela mesma**.
Vale para a montagem (a compra protege a venda) e para a desmontagem (a recompra libera a
venda da proteção).

**O que este cartão não faz.** Não cria autorização para usar proteção de outra boleta. Isso
é o cartão seguinte, DL3-PR07A3B, com as duas decisões de Francisco de 23/11/2026: só vale a
sobra de boleta já parada, e a boleta que usa a sobra pode ser só de venda. Entre os dois
cartões, a sobra de uma boleta não é usada por nenhuma outra.

Também fora: motor, prévia, resumo criptográfico, recibo, roteiro de replay. Nenhuma
dependência nova.

## 1. Arquivos e tetos

| Arquivo | O que muda | Teto |
|---|---|---|
| `backend/derivatives/ticket/sequencing.py` | só `ReservationBook._capacity` | 368 linhas (hoje 366) |
| `tests/unit/derivatives/ticket/test_sequencing.py` | quatro testes mudam (§3.1); V1, V2, V3 e V6 entram | — |
| `tests/unit/derivatives/ticket/test_engine.py` | V4 e V5 entram | — |
| `docs/specs/derivatives/fase3/DL3-PR07A3.md` | cópia deste cartão | — |

**Não muda:** `engine.py` e os demais módulos da boleta; o formato do recibo e da prévia;
`scripts/derivatives_ticket_replay.py`; `current_state.md`; arquivos protegidos. **As âncoras
oficiais das sessões `calmo`, `leilao` e `rapido` não mudam.**

## 2. Regra

Para a venda de uma perna da boleta T, protegida pela série S:

- **Compras que contam:** as execuções de compra de S **feitas pela própria T**.
- **Vendas que descontam:** as ordens de venda **da própria T** cobertas por S, pelo saldo
  vivo mais o executado.
- O resto do cálculo fica como está: teto pela quantidade da perna, menos o que a T já
  enviou; arredondamento para baixo ao lote; na desmontagem, o teto pelo saldo comprado da
  conta.

**O que continua por conta, sem mudança:** a capacidade de recompra de uma posição vendida,
a unicidade de cada execução, a foto de posição e o bloqueio por divergência.

Atualize o comentário do trecho: ele hoje diz que uma recompra libera uma proteção
«inclusive entre boletas».

## 3. Cenários

Auxiliares dos próprios arquivos de teste: plano de referência (compra A 10 a 1,00; vende B
10 a 1,50), `close_plan()` para a desmontagem (vende A 10, recompra B 10) e a `Session` do
`test_engine`.

### 3.1 Testes existentes que mudam

Só estes quatro, todos em `test_sequencing.py`. Renomeie quando o nome deixar de dizer a
verdade.

| Teste de hoje | O que passa a afirmar |
|---|---|
| `test_s09_cancel_and_late_fill` | a T1 compra 3 e reserva 3; a T2 nunca consegue reservar. Depois de 2 executadas e 1 liberada: disponível da T1 = 1 e da T2 = 0; a T1 reserva essa 1 e fica com 0 |
| `test_reservations_race_and_failed_release` | a corrida passa a ser entre oito ordens **da mesma boleta** que comprou 3: exatamente uma vence. No fim, disponível da boleta = 2 e de outra boleta = 0 |
| `test_partial_execution_sequences_conserve_shared_protection` | duas boletas, cada uma com as próprias compras: em todas as 1.296 sequências de quatro eventos (comprar 1, comprar 2, reservar 1, reservar 2, executar, liberar), o disponível de cada boleta é compras − vendas − vivas **dela**, e o de uma terceira boleta é sempre 0 |
| `test_equivalent_position_row_order_preserves_coverage` | com 3 compradas pela T1: disponível da T1 = 3 e da T2 = 0, nas duas ordens de linhas |

### 3.2 Testes novos no livro (`test_sequencing.py`)

**V1 — outra boleta não recebe nada.** A T1 compra 4 A. Disponível: T1 = 4, T2 = 0. Reserva
de 1 pela T2: `SequenceRefusal`. O disponível da T1 continua 4.

**V2 — cada boleta tem o próprio saldo.** A T1 compra 4 e a T2 compra 6.

| Passo | Disponível T1 | Disponível T2 |
|---|---|---|
| T1 reserva 3 | 1 | 6 |
| 2 dessas executam | 1 | 6 |
| a 1 restante é liberada | 2 | 6 |
| T2 tenta reservar 7 | recusa | — |
| T2 reserva 6 | 2 | 0 |

**V3 — a desmontagem também é por boleta.** Com `close_plan()`: a T1 recompra 4 B.
Disponível para vender A: T1 = 4, T2 = 0. A T2 recompra 6 e a T1 reserva 4: T1 = 0, T2 = 6.

**V6 — dois pares na mesma boleta não se misturam.** Posição com os pares (A protege B) e
(C protege D). A T1 compra 2 A e 2 C e reserva a venda de 2 B. Disponível da T1: B = 0 e
D = 2. Depois que as 2 B executam, continua B = 0 e D = 2. Este cenário já passa hoje; entra
porque nenhum teste o fixava.

### 3.3 Testes novos no motor (`test_engine.py`)

**V4 — a sobra de uma boleta parada não é usada.**

1. T1 confirmada. A compra de 10 A executa. A venda de B executa 6.
2. O saldo da venda é cancelado. T1 em `STOPPED`, ordem `T1:B:1` em `CANCELLED`.
3. T2 confirmada. Ordens da T2: só `T2:A:1`, aberta. Pedidos à venue até aqui, na ordem:
   `T1:A:1` 10; `T1:B:1` 10; `T2:A:1` 10. **Hoje** haveria também `T2:B:1` de 4.
4. A compra da T2 executa 3. Entra `T2:B:1`, de 3.

**V5 — a boleta pausada conserva a própria proteção.**

1. T1 confirmada e pausada antes de a compra executar. A compra de 10 A executa. Disponível:
   T1 = 10, T2 = 0.
2. T2 confirmada. Ordens da T2: só `T2:A:1`, aberta. O disponível não muda. **Hoje** a T2
   enviaria `T2:B:1` de 10.
3. T1 retomada. T1 em `WORKING`, com `T1:B:1` aberta. Pedidos à venue, na ordem: `T1:A:1`
   10; `T2:A:1` 10; `T1:B:1` 10. **Hoje** a T1 iria a `STOPPED` sem vender.

## 4. Evidência do planejador

- **Fatos de hoje.** Os dois comportamentos do §0 foram reproduzidos no `main` `719cebb` com
  roteiros de fatos.
- **Protótipo descartável.** A mudança coube em uma linha a mais (367). Os dez cenários do §3
  passam no protótipo. No `main` de hoje, nove falham e V6 passa.
- **Portão completo no protótipo:** só os quatro testes do §3.1 mudam de resultado. Os testes
  das âncoras das sessões continuam passando.
- **Mutantes:** oito defeitos plantados, um por vez, todos detectados pelos cenários do §3.
  Um deles (M4) passava por todos os testes anteriores; V6 o detecta.

## 5. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, quem derrubou no
protótipo do planejador.

1. Compras de todas as boletas contam (V1, V4, V5).
2. Vendas de todas as boletas descontam (V2, V3).
3. Venda executada não desconta (V2).
4. Vendas de outra série da mesma boleta descontam (V6).
5. Compras contadas pela série vendida, em vez da série de proteção (V1).
6. A desmontagem conta compras de todas as boletas (V3).
7. Só as outras boletas contam (V2).
8. Saldo vivo não desconta (V2).

## 6. Critérios de parada

Pare e relate se:

- algum esperado do §3 não reproduzir;
- outro teste, além dos quatro do §3.1, mudar de resultado;
- alguma âncora de sessão mudar;
- qualquer arquivo de produção além de `sequencing.py` precisar mudar, ou o teto estourar.

## 7. Entrega

1. Commit vermelho com os testes; depois o verde.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
   `tests/integration` só no contêiner isolado.
3. Descrição do PR: cabeça, contagens, linhas de `sequencing.py`, os 8 mutantes, as âncoras
   conferidas, desvios.
4. Copie este cartão para o caminho do §1. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda os cenários do
seu protótipo contra o módulo entregue.

## 8. Depois deste cartão

**DL3-PR07A3B — autorização para usar a sobra de outra boleta.** Decisões de Francisco de
23/11/2026:

1. **Só sobra de boleta parada.** A T2 só usa compras que a boleta de origem não vendeu e
   não pode mais vender. Nunca tira proteção de boleta em execução.
2. **A boleta que usa a sobra pode ser só de venda.** Exemplo: «vender 4 B, cobertas por 4 A
   compradas pela T1». A regra geral fica: venda até as compras próprias mais o autorizado.

A autorização nomeia a série, a boleta de origem e a quantidade máxima, entra na prévia
assinada, e o recibo registra a origem e a quantidade usada. Depois vêm PR07A4 e PR07B.

## Revisão adversarial (Claude) — GO na primeira rodada, cabeça `f0485d0`

Pela regra de processo de Francisco, o revisor **não executou a suíte, a tipagem nem os
mutantes** desta cabeça. Leu o diff, conferiu as evidências pelo SHA-256 e rodou os cenários
do seu protótipo, escrito antes do cartão.

| Verificação | Resultado | Quem |
|---|---|---|
| Suíte sem integração, Linux x86_64 e macOS | 11.422 aprovados, 16 pulados, 261 subtestes nos dois | implementador; logs conferidos |
| mypy estrito e Pyright, nos dois sistemas | 0 erros | implementador; logs conferidos |
| Commit vermelho | as nove falhas previstas | implementador; log conferido |
| 8 mutantes do §5, nos dois sistemas | todos detectados | implementador; logs conferidos |
| Integração | só no contêiner Linux isolado | implementador; evidências conferidas |
| Manifesto de 72 evidências (`822c733c…9c9f`) e hashes dos dois relatórios | conferem | revisor |
| Diff | quatro arquivos; em produção, só `_capacity`; `sequencing.py` com 366 linhas (teto 368) | revisor |
| Âncoras das sessões | nenhum hash tocado no diff dos testes; os testes das âncoras passam nos logs | revisor |
| Cópia do cartão | SHA-256 `8fde3d6e…8dc1`, igual ao publicado | revisor |
| Dez cenários do protótipo do planejador contra o módulo entregue | todos aprovados | revisor |

A mudança de produção é equivalente à do protótipo do planejador.

Limite desta revisão: sem mutantes próprios do revisor nesta cabeça.

Observações, nenhuma bloqueante. As duas vêm da skill e são lacunas de teste em
invariantes que já existiam antes deste cartão; o código trata os dois casos corretamente:

1. **Uma compra protegendo duas pernas de venda da mesma boleta.** Nenhum teste distingue
   o saldo da série protetora do saldo de cada perna.
2. **Recompra confirmada acima do total vendido da conta.** Nenhum teste fixa a recusa do
   livro nesse caminho.

As duas entram no DL3-PR07A3B, que mexe no mesmo livro.

Relatórios da skill lidos depois de formado o parecer, com SHA-256 conferidos
(`50091562…aa75` e `ab652914…a04e`): GO, sem bloqueante.
