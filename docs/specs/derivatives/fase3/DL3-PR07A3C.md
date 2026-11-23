# DL3-PR07A3C — Supercartão: o motor passa a usar a sobra autorizada de uma boleta parada

**Data:** 23/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `dccb2a9` (DL3-PR07A3B integrado) · **PR novo**, em rascunho
**Decisões que este cartão implementa:**

- Resolução R-A de Francisco, de 22/11/2026: no envio o livro reconfere e reserva a sobra com
  exclusividade; se outra boleta levou o saldo, o motor mostra indisponibilidade; o recibo
  registra a origem e a quantidade efetivamente usada.
- Decisões de Francisco de 23/11/2026: só vale a sobra de boleta já parada; a boleta que usa
  a sobra pode ser só de venda.

## 0. Escopo

**O que acontece hoje.** Depois do DL3-PR07A3B, a autorização existe na prévia assinada, no
plano e no livro de reservas, mas o motor recusa qualquer boleta com autorização. Nenhuma
boleta parada é marcada como parada no livro, então nenhuma sobra pode ser usada.

**O que este cartão entrega.**

1. O motor aceita a boleta com autorização.
2. Ao parar, o motor marca a boleta como parada no livro. A sobra dela passa a existir.
3. No envio da venda, o motor usa as compras próprias e depois a sobra autorizada, com
   reserva exclusiva por origem.
4. O recibo registra a origem em cada ordem coberta por sobra e em cada execução dela.
5. O livro ganha uma trava: boleta parada não reserva nada, nem a sobra de outra.
6. Três testes que faltaram no DL3-PR07A3B (o código já está certo).

**O que este cartão não faz.**

- **Boleta concluída não cede sobra.** Só a boleta em `STOPPED` é marcada. É a leitura
  literal de «boleta já parada». Se Francisco quiser incluir a concluída, é mudança pequena
  em outro cartão.
- Não cria sessão oficial nova no roteiro de replay. Os cenários usam a `Session` do
  `test_engine`. As três sessões oficiais e as quatro âncoras não mudam.
- Não muda o `resumo.json`, a prévia, o resumo criptográfico nem o formato do recibo de
  boletas sem autorização.
- Não remove `releasable_quantity`, hoje sem chamador em produção. Fica como está.

Nenhuma dependência nova.

## 1. Arquivos e tetos

| Arquivo | O que muda | Teto (hoje) |
|---|---|---|
| `backend/derivatives/ticket/engine.py` | aceitar a autorização, parar no livro, envio por origem, recibo | 451 (434) |
| `backend/derivatives/ticket/sequencing.py` | só a trava em `ReservationBook._capacity` | 402 (401) |
| `tests/unit/derivatives/ticket/test_engine.py` | X1 a X12; três testes mudam (§3.1) | — |
| `tests/unit/derivatives/ticket/test_sequencing.py` | K2, K3 e K4 | — |
| `tests/unit/derivatives/ticket/test_models.py` | K1 | — |
| `docs/specs/derivatives/fase3/DL3-PR07A3C.md` | cópia deste cartão | — |

**Não muda:** `models.py`, `digest.py`, `receipt.py`, `state.py`, `session.py`, `replay.py`,
`paper_venue.py`, `scripts/derivatives_ticket_replay.py`, `current_state.md`, arquivos
protegidos.

## 2. Regra

### 2.1 Aceitar

`_propose` deixa de recusar a boleta com autorização. O plano e a exposição parcial seguem
as regras do DL3-PR07A3B. A edição da prévia já conserva a autorização; X8 fixa isso.

### 2.2 Parar no livro

Quando a boleta entra em `STOPPED` **e não há divergência aberta na conta**, o motor chama
`close(conta, boleta)` no livro. É a mesma condição que hoje libera a ocupação das compras
nunca enviadas, pelos mesmos dois caminhos (laço de envio e conciliação).

- Com divergência aberta na conta, a boleta **não** é marcada. A sobra dela não é usada.
- Boleta em `COMPLETED` **não** é marcada.

### 2.3 Enviar a venda

Para cada perna de venda, o motor percorre as fontes de cobertura **nesta ordem**:

1. as compras da própria boleta;
2. cada autorização cuja série é a proteção da perna, **na ordem assinada**.

Para cada fonte com disponível maior que zero, o motor envia **uma ordem** com essa
quantidade, reservada no livro com a origem correspondente. O resto fica como hoje: a
numeração das ordens da série continua em sequência (`T2:B:1`, `T2:B:2`…); cada ordem passa
pela conferência dos limites assinados antes de sair, e a boleta para se não passar; pausa,
bloqueio de conta, cancelamento, janela de envio e bloqueio de mercado interrompem o laço.

### 2.4 Continuar ou parar

Sem ordem viva e sem ter completado, a boleta continua em `WORKING` enquanto houver
disponível em **qualquer** fonte de alguma venda não rejeitada. Se não houver, para, como
hoje. Consequência: a boleta que depende de uma sobra tomada por outra vende o que existe e
para.

### 2.5 Confirmar

Nada muda no código da confirmação. A admissão do livro já recusa com `SequenceRefusal`
(«boleta de origem não parada», «sobra indisponível») **antes** de a decisão ser gasta. A
boleta fica em `DRAFT` e a mesma decisão pode ser usada depois.

### 2.6 Recibo

Só para ordem coberta por sobra:

- o registro do pedido ganha `origin` (a boleta de origem), ao lado de `protection`;
- cada registro de execução dessa ordem ganha `origin`, ao lado de `quantity`.

Ordem coberta por compras próprias **não** tem a chave `origin`. É isso que mantém os
recibos de hoje idênticos.

### 2.7 Trava no livro

`_capacity` devolve **0** para uma boleta parada em qualquer chamada, com ou sem `origin`.
Hoje a boleta parada com autorização ainda vê a sobra de outra.

## 3. Cenários

Auxiliares: os de `test_engine.py` (`Session`, `at`, `NOW`, `END`, `CLOSE`) e os de
`test_sequencing.py`. Toda boleta nova usa prazo de envio `END` e validade `CLOSE`.

**T1 parada com sobra 4** (o início do V4): T1 de referência confirmada em `at(2)`; A com
oferta a 1,00 em 3 (a compra de 10 executa); B com demanda a 1,50 e tamanho 6 em 4; cancela
`T1:B:1` em 4; cotação de B em 5. T1 em `STOPPED`, `T1:B:1` em `CANCELLED`, **sobra de 4 A**.

**Boleta só de venda** de `n` B: vende B `n` a 1,50, líquido `−1,50 × n`, bruto `1,50 × n`,
autorização (A, T1, `n`), salvo indicação.

**Sobra vista por terceiro:** disponível, no livro, para uma boleta só de venda de 10 B com
autorização de 10 naquela origem.

### 3.1 Testes existentes que mudam

| Teste de hoje | O que passa a afirmar |
|---|---|
| `test_s08_cancel_partial_sale` | depois de parar: disponível próprio da T1 = **0** (hoje 6); sobra da T1 vista por terceiro = 6. O resto fica igual |
| `test_c6_rejected_sale_is_final` | depois de parar: disponível próprio da T1 = **0** (hoje 10); sobra da T1 vista por terceiro = 10. O resto fica igual |
| `test_w14_engine_refuses_coverage_before_planning_or_recording` | sai; X1 o substitui |

### 3.2 Motor (`test_engine.py`)

**X1 — boleta só de venda usa a sobra; o recibo diz de onde veio.** T1 parada com sobra 4.
Sobra vista por terceiro: 4. T2 só de venda de 4 B.

1. Prévia da T2: autorização (A, T1, 4); exposição parcial 0.
2. Confirmação em `at(5)`: T2 em `WORKING`, ordens `{T2:B:1: LIVE}`. Terceiro pedido à venue:
   `T2:B:1`, 4 a 1,50, em `at(5)`. Sobra vista por terceiro: 0.
3. Registro do pedido no recibo da T2: `protection` = `A`, `origin` = `T1`, quantidade 4.
4. B com demanda a 1,50, tamanho 3, em 6: execução `T2:B:1#1`, `quantity` 3, `price`
   `1.50`, `origin` `T1`; bruto executado `4.50`.
5. B com demanda a 1,50, tamanho 1, em 7: execução `T2:B:1#2`, `quantity` 1, `origin` `T1`;
   bruto executado `6.00`. T2 em `COMPLETED`.
6. Sequência do recibo da T2: `preview confirm start venue_live venue_partial venue_fill
   complete`. Os dois recibos verificam. Nenhum registro do recibo da T1 tem `origin`.

**X2 — sobra tomada: recusa na confirmação, decisão preservada.** T1 parada com sobra 4. T2
e T3 só de venda de 4 B. T2 confirmada em `at(5)`.

1. T3 confirma em `at(5)`: `SequenceRefusal` «sobra indisponível». T3 em `DRAFT`, sem
   ordens, nenhum pedido novo à venue, recibo só com a prévia.
2. Cancela `T2:B:1` em 5; cotação de B em 6. T2 em `STOPPED`.
3. T3 confirma em `at(6)` **com a mesma decisão**: aceita. `T3:B:1`, 4 a 1,50, em `at(6)`.

**X3 — origem em execução não cede.** T1 confirmada e pausada em `at(2)`; a compra executa
em 3. T2 só de venda de 4 B confirma em `at(3)`: `SequenceRefusal` «boleta de origem não
parada»; T2 em `DRAFT`, sem ordens. T1 retomada em `at(4)`: `T1:B:1`, 10 a 1,50, `LIVE`.

**X4 — sobra agora, compras próprias depois.** T1 parada com sobra 4. T2: compra 6 A a 1,00
e vende 10 B a 1,50 (líquido −9, bruto 21), autorização (A, T1, 4). Exposição parcial 6.

1. Confirmação em `at(5)`: dois pedidos, nesta ordem: `T2:A:1` 6 a 1,00; `T2:B:1` 4 a 1,50.
2. A com oferta a 1,00, tamanho 6, em 6: `T2:A:1` em `FILLED`; entra `T2:B:2`, 6 a 1,50.
3. Recibo: pedido de `T2:B:1` com `origin` `T1`; pedido de `T2:B:2` com `protection` `A` e
   **sem** `origin`.
4. B com demanda a 1,50, tamanho 10, em 7: T2 em `COMPLETED`. Execuções de venda: `T2:B:1`
   4 com `origin` `T1`; `T2:B:2` 6 sem `origin`.

**X5 — na mesma passada, compras próprias primeiro.** T1 parada com sobra 4.

1. T2 só de venda de 2 B, autorização (A, T1, 2), confirmada em `at(5)`.
2. T3: compra 6 A e vende 10 B (líquido −9, bruto 21), autorização (A, T1, 4), confirmada em
   `at(5)`: pedidos `T3:A:1` 6 a 1,00 e `T3:B:1` 2 a 1,50. T3 pausada em `at(5)`.
3. A com oferta a 1,00, tamanho 6, em 6: `T3:A:1` em `FILLED`.
4. Cancela `T2:B:1` em 6; cotação de B em 7: T2 em `STOPPED`. Cinco pedidos à venue até aqui.
5. T3 retomada em `at(8)`: dois pedidos, **nesta ordem**: `T3:B:2` 6 a 1,50 (sem `origin`);
   `T3:B:3` 2 a 1,50 (`origin` `T1`). O pedido de `T3:B:1` tem `origin` `T1`.

**X6 — duas origens, na ordem assinada.** T1 parada com sobra 4. T2 de referência confirmada
em `at(5)`; A com oferta a 1,00 em 6; B com demanda a 1,50, tamanho 7, em 7; cancela
`T2:B:1` em 7; cotação de B em 8. T2 em `STOPPED`. Sobras vistas por terceiro: T1 = 4,
T2 = 3.

T3 só de venda de 5 B, autorizações (A, **T2**, 2) e (A, **T1**, 3), nessa ordem. Confirmação
em `at(8)`: dois pedidos novos, nesta ordem: `T3:B:1` 2 a 1,50 (`origin` `T2`); `T3:B:2` 3 a
1,50 (`origin` `T1`). Sobras vistas por terceiro depois: T1 = 1, T2 = 1.

**X7 — quem usou sobra e parou também é parado no livro.** T1 parada com sobra 4. T2 só de
venda de 4 B confirmada em `at(5)`; cancela `T2:B:1` em 5; cotação de B em 6. T2 em
`STOPPED`. No livro: T2 com origem T1 = 0; sobra da T1 vista por terceiro = 4; sobra da T2
vista por terceiro = 0.

**X8 — a edição conserva a autorização.** T1 parada com sobra 4. T2 só de venda de 4 B.
Editar a quantidade da perna para 2 em `at(5)`: prévia na versão 2, autorização (A, T1, 4)
intacta. Editar para 5: `SequenceRefusal` «quantidade de proteção insuficiente»; a versão
continua 2.

**X9 — conta com divergência não marca a boleta.** Como a T1 parada com sobra 4, mas com a
divergência da conta `sim` registrada depois do cancelamento e antes da cotação de B em 5.
T1 em `STOPPED`; sobra vista por terceiro: 0. Liberada a divergência, a T2 só de venda de 4 B
confirma em `at(5)`: `SequenceRefusal` «boleta de origem não parada».

**X10 — boleta concluída não cede.** T1: compra 10 A a 1,00 e vende 6 B a 1,50 (líquido 1,
bruto 19), confirmada em `at(2)`; A com oferta a 1,00 em 3; B com demanda a 1,50, tamanho 6,
em 4. T1 em `COMPLETED`. Sobra vista por terceiro: 0. T2 só de venda de 4 B confirma em
`at(5)`: `SequenceRefusal` «boleta de origem não parada»; T2 em `DRAFT`.

**X11 — pausada, a boleta espera a sobra que voltou.** T1 parada com sobra 4.

1. T2: só venda de 2 B a **1,60** (líquido −3,20, bruto 3,20), autorização (A, T1, 2),
   confirmada em `at(5)`.
2. T3 só de venda de 4 B confirmada em `at(5)`: pedido `T3:B:1`, **2** a 1,50. T3 pausada em
   `at(5)`.
3. Cancela `T2:B:1` em 5; cotação de B em 6: T2 em `STOPPED`; `T3:B:1` segue `LIVE`.
4. B com demanda a 1,50, tamanho 10, em 7: `T3:B:1` em `FILLED`. T3 continua em `WORKING`,
   com uma só ordem.
5. T3 retomada em `at(8)`: pedido `T3:B:2`, 2 a 1,50, `origin` `T1`.

**X12 — vende o que existe e para.** Passos 1 e 2 do X11, sem pausar a T3. B com demanda a
1,50, tamanho 10, em 6: `T3:B:1` em `FILLED`; `T2:B:1` segue `LIVE`; T3 em `STOPPED`, com uma
só ordem. Último registro do recibo da T3: `stop`, com bruto executado `3.00`, projetado
`3.00` e assinado `6.00`.

### 3.3 Livro e resumo

K1, K2 e K3 **já passam no `main`**; entram porque nenhum teste os fixava.

**K1 — o resumo ordena por série e depois por origem** (`test_models.py`). Prévia de
referência com `partial_exposure=Decimal("10")` e as autorizações (B, T1, 1) e (A, T9, 2),
nas duas ordens: o mesmo resumo,
`364d378948c544bc1afbe75e4f6b7d50b3c9f7e7fd86386f919adfc9971a601e`. Os bytes canônicos
contêm, literalmente:
`"coverage":[{"origin":"T9","quantity":2,"series":"A"},{"origin":"T1","quantity":1,"series":"B"}]`

**K2 — boletas de mesmo nome em contas diferentes.** Conta `sim`: T1 compra 10, vende 6 e é
parada. Conta `outra`: T1 é admitida e compra 7, sem parar. Um terceiro só de venda de 8 B
com autorização (A, T1, 8):

| Passo | Conta `sim` | Conta `outra` |
|---|---|---|
| início | 4 | 0 |
| depois de `close("outra", "T1")` | 4 | 7 |

**K3 — teto por origem, duas origens na mesma série.** L1 compra 5 e L2 compra 7; as duas
são paradas, sem vendas. T: só venda de 8 B, autorizações (A, L2, 5) e (A, L1, 3), admitida.

| Passo | Com origem L1 | Com origem L2 |
|---|---|---|
| início | 3 | 5 |
| reserva 2 com origem L1 | 1 | 5 |
| dessa ordem, 1 executa e 1 é liberada | 2 | 5 |

**K4 — boleta parada não reserva nada.** T1 compra 10, vende 6 e é parada. T2 só de venda de
4 B admitida: com origem T1 = 4. Depois de `close("sim", "T2")`: com origem T1 = 0; reserva
de 1 com origem T1: «reserva indisponível». Um terceiro continua vendo 4.

## 4. Evidência do planejador

- **Protótipo descartável** sobre o `main` `dccb2a9`: `engine.py` com 448 linhas (14 a
  mais) e `sequencing.py` com as mesmas 401. Tipagem estrita limpa.
- **Portão completo no protótipo** (sem `tests/integration`): só os três testes do §3.1
  mudam de resultado; os outros 11.435 passam, com 16 pulados. As âncoras das sessões seguem
  passando.
- **Cenários do §3:** os 16 passam no protótipo. No `main` de hoje, X1 a X12 e K4 falham;
  K1, K2 e K3 passam.
- **Mutantes:** 19 defeitos plantados, um por vez, todos detectados (§5).

## 5. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, quem derrubou no
protótipo.

**Motor**

1. A boleta parada não é marcada no livro (X1, X2, X4 a X7, X11, X12).
2. A boleta é marcada mesmo com divergência na conta (X9).
3. A boleta concluída também é marcada (X10).
4. O motor continua recusando a autorização (X1 a X12).
5. O motor só usa compras próprias (X1, X2, X4 a X7, X11, X12).
6. A sobra é usada antes das compras próprias (X5).
7. As origens são percorridas na ordem inversa (X6).
8. A reserva sai sem a origem (X1 e outros).
9. A quantidade da venda ignora a origem (X1 e outros).
10. A ordem do motor não guarda a origem (X1, X4, X5, X6, X11).
11. O pedido no recibo sai sem `origin` (X1, X4, X5, X6, X11).
12. A execução no recibo sai sem `origin` (X1, X4).
13. O pedido de ordem própria ganha `origin` (X1, X4, X5).
14. A execução de ordem própria ganha `origin` (X1, X4).
15. A decisão de continuar ou parar ignora a sobra disponível (X11).

**Livro e resumo**

16. A boleta parada ainda reserva a sobra de outra (K4, X7).
17. A sobra soma ordens de outra conta (K2).
18. O resumo ordena só pela origem (K1).
19. O teto de uma origem conta o uso de outra (K3, X5, X6).

## 6. Critérios de parada

Pare e relate se:

- algum esperado do §3 não reproduzir, em especial o resumo do K1;
- outro teste, além dos três do §3.1, mudar de resultado;
- alguma âncora de sessão mudar, ou o recibo de uma boleta sem autorização deixar de ser
  idêntico ao de hoje;
- for preciso mudar arquivo de produção fora do §1, ou algum teto estourar;
- K1, K2 ou K3 falharem no `main` (seria defeito já integrado).

## 7. Entrega

1. Commit vermelho com os testes; depois o verde. K1, K2 e K3 nascem verdes: declare isso.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
   `tests/integration` só no contêiner isolado, nunca no Mac com banco vivo.
3. Descrição do PR: cabeça, contagens, linhas dos dois arquivos, os 19 mutantes, o resumo do
   K1, as âncoras e os recibos oficiais comparados byte a byte, desvios.
4. Copie este cartão para o caminho do §1. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda os cenários do
seu protótipo contra os módulos entregues.

## 8. Depois deste cartão

DL3-PR07A4 (DP-13: relato contraditório e evento externo) e DL3-PR07B (DP-02 e DP-03:
zeragem e borboleta no motor). Atrás deles: limite de escala em `expiry_payoff` e
`pre_expiry`, e a modalidade B de garantia do Adendo 1.

## Revisão adversarial (Claude) — GO na primeira rodada, cabeça `527e070`

Pela regra de processo de Francisco, o revisor **não executou a suíte, a tipagem nem os
mutantes** desta cabeça. Leu o diff, conferiu as evidências pelo SHA-256 e rodou os cenários
do seu protótipo, escrito antes do cartão, e quatro sondas próprias.

| Verificação | Resultado | Quem |
|---|---|---|
| Suíte sem integração, Linux x86_64 e macOS | 11.456 aprovados, 16 pulados, 261 subtestes nos dois | implementador; logs conferidos |
| mypy estrito e Pyright, nos dois sistemas | 0 erros | implementador; logs conferidos |
| Commit vermelho | X1 a X12, K4 e os dois testes alterados falham; K1 a K3 passam na base | implementador; logs conferidos |
| Testes antigos do motor contra a cabeça | só S08, C6 e W14 mudam de resultado | implementador; log conferido |
| 19 mutantes do §5 e 3 adicionais, nos dois sistemas | todos detectados | implementador; logs conferidos |
| Integração | só no contêiner Linux isolado: 31 aprovados, 206 pulados | implementador; evidências conferidas |
| Manifesto de 116 evidências (`d8885f84…4c37`) e hashes dos dois relatórios | conferem | revisor (28 arquivos) e Francisco (os 116, no Mac) |
| Diff | seis arquivos; `engine.py` com 447 linhas (teto 451) e `sequencing.py` com 402 (teto 402) | revisor |
| Âncoras e recibos das sessões | os quatro recibos e os três resumos iguais byte a byte entre base e cabeça | implementador; log conferido |
| Cópia do cartão | SHA-256 `e1fbe7cf…9703`, igual ao publicado | revisor |
| 16 cenários do protótipo do planejador contra os módulos entregues | todos aprovados | revisor |
| 4 sondas do revisor (lista abaixo) | todas aprovadas | revisor |

A implementação é equivalente à do protótipo do planejador.

Sondas do revisor, escritas antes de ler os relatórios da skill: execução parcial durante o
cancelamento de ordem coberta por sobra (1 executada com origem `T1`; as 3 restantes só
voltam à sobra depois do cancelamento confirmado); ordem incerta coberta por sobra,
conciliada como viva; ordem incerta sem registro na venue, que devolve a sobra inteira;
recibo de boleta sem autorização sem a chave `origin`.

Limite desta revisão: sem mutantes próprios do revisor nesta cabeça.

Observações. A primeira é falha de desenho do planejador e precisa de correção no próximo
cartão; nenhuma bloqueia esta integração, que cumpre o cartão:

1. **A prioridade entre origens não está presa ao resumo criptográfico (nota da skill;
   desenho do planejador).** O DL3-PR07A3B fez o resumo ordenar as autorizações por série e
   origem, de modo que a ordem informada não o altera. Este cartão fez o motor usar as
   origens «na ordem assinada». Resultado: duas prévias com as mesmas autorizações em ordens
   diferentes têm o mesmo resumo e prioridades diferentes. A decisão humana é presa ao
   resumo, então a prioridade que o humano viu não está coberta por ela. Hoje não há efeito
   operacional (simulador D0; o motor confirma a prévia que ele mesmo guarda; o recibo
   preserva a prévia inteira). Correção no próximo cartão: o resumo passa a respeitar a
   ordem informada.
2. **Execução durante o cancelamento (skill).** Nenhum teste versionado fixa a origem na
   execução que chega com o cancelamento pedido. A cabeça se comporta corretamente, pela
   sonda da skill e pela do revisor. O teste entra no próximo cartão.

Relatórios da skill lidos depois de formado o parecer, com SHA-256 conferidos
(`100b85f2…4624` e `fb596644…46e2`): sem bloqueante.
