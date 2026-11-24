# DL3-PR07A5 — Supercartão: fato externo legítimo, reação do livro e do motor (DP-13, 2ª parte)

**Data:** 24/11/2026 (UTC) · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `3a4de80` (DL3-PR07B2 integrado)
**PR novo**, em rascunho
**Decisões que este cartão implementa:**

- DP-13 de Francisco (Revisão 2, 22/11/2026): «Já um exercício ou enquadramento confirmado
  pela corretora é **fato externo legítimo**. Deve compor a posição conciliada mesmo que
  nenhuma boleta o tenha originado. Durante o bloqueio, o sistema continua recebendo fatos.»
- Francisco, 23/11/2026, em resposta ao planejador: fato externo legítimo numa série que
  uma boleta em execução usa → a boleta **para de enviar**, mantém as ordens já enviadas e
  contabiliza as execuções. O fato **não bloqueia a conta**: só afeta as boletas da série
  atingida. Em nenhum caso o sistema cancela ordem sozinho.

## 0. Escopo

**O que acontece hoje.** Fatos conferidos no `main`:

- O livro só conhece execuções que vieram de ordens de boletas. Não há onde registrar um
  fato sem ordem de origem.
- A foto de uma conta é fixa durante a vida do livro: foto diferente é recusada com «foto
  divergente; conciliação necessária».
- Logo, depois de um exercício ou enquadramento, a foto fica velha e nada impede o motor de
  continuar enviando com base nela. Os 11 cenários do §3 falham no `main`.

**O que este cartão entrega: a reação.** A regra mínima é: *o fato congela a série naquela
conta para envios novos, até haver foto nova.*

1. **Livro.** Registra que uma série de uma conta teve fato externo. A partir daí: não
   reserva venda nova que use a série, como vendida ou como proteção; não empresta sobra
   dessa série; recusa boleta nova que use a série. O que já existia segue contabilizado.
2. **Motor.** Avisado do fato, a boleta que usa a série grava o fato no recibo, uma vez, e
   não envia mais nada, de nenhuma perna. As ordens vivas ficam; as execuções entram; sem
   ordem viva, a boleta para. A conta não bloqueia. Nenhuma ordem é cancelada pelo sistema.
3. Um tipo novo de registro no recibo: `external`.

**O que este cartão não faz.**

- **Quem chama.** A entrada do fato pela sessão e pelo roteiro, o aviso a todos os motores
  da conta e o registro do fato no nível da conta (tipo, série, quantidade) são do próximo
  cartão. Aqui nada em produção chama as duas funções novas: sessões, roteiros e recibos
  oficiais não mudam.
- **Não compõe a posição.** Não altera saldos nem capacidades pela quantidade do fato. O
  congelamento é a resposta conservadora enquanto a foto nova não chega.
- **Não descongela.** Foto nova é livro novo; no simulador, sessão nova.
- **Compra de motor não avisado.** Compra não passa pelo livro antes do envio. O livro
  segura venda nova e admissão; quem garante que todo motor da conta é avisado é o próximo
  cartão, com teste próprio.
- Não muda prévia, resumo criptográfico, modelos nem conferência de relatos.

Nenhuma dependência nova.

## 1. Arquivos e tetos

| Arquivo | O que muda | Teto (hoje) |
|---|---|---|
| `backend/derivatives/ticket/state.py` | `Event.EXTERNAL = "external"` | 152 (150) |
| `backend/derivatives/ticket/sequencing.py` | séries com fato no livro; capacidade e admissão | 466 (443) |
| `backend/derivatives/ticket/engine.py` | `on_external`; parada de envio | 512 (490) |
| `tests/unit/derivatives/ticket/test_sequencing.py` | E1 e E2 | — |
| `tests/unit/derivatives/ticket/test_engine.py` | E3 a E11 | — |
| `docs/specs/derivatives/fase3/DL3-PR07A5.md` | cópia deste cartão | — |

**Não muda:** `models.py`, `digest.py`, `receipt.py`, `report_check.py`, `venue.py`,
`session.py`, os demais módulos da boleta, `scripts/derivatives_ticket_replay.py`, os
roteiros, `current_state.md`, arquivos protegidos. Linhas novas com até 100 colunas.

**Nenhum teste existente muda de resultado.** As quatro âncoras e os recibos das sessões
oficiais não mudam.

## 2. Regra

### 2.1 Livro (`ReservationBook`)

**`freeze(account: str, symbol: str) -> None`** — registra o par conta e série. Repetir não
muda nada. Não confere a foto: a conta pode ainda não ter boleta no livro. Vale só para
aquela conta.

**`frozen(plan: LegPlan) -> tuple[str, ...]`** — as séries do plano com fato na conta do
plano, em ordem crescente. «Séries do plano» são as das pernas e as proteções que aparecem
nas dependências, inclusive proteção que vem só de sobra autorizada. Vazio quando não há.

**Capacidade.** `available` devolve 0 quando a série da perna vendida **ou** a proteção
consultada tem fato. Vale para saldo próprio e para sobra emprestada. `reserve` então recusa
pelo caminho de hoje, «reserva indisponível».

**Admissão.** `admissible` e `admit` recusam com
**«série com fato externo; foto nova necessária»** quando `frozen(plan)` não é vazio. A
conferência vem depois das de identidade e de foto, antes das de autorização de sobra.

**O que não muda.** `confirm_buy`, `confirm_sale`, `confirm_release`, `settle_buy` e
`close`: tudo o que trata de ordem já existente segue igual.

Atenção: a trava do livro não é reentrante. A conferência interna da admissão não pode
chamar o método público que pega a trava.

### 2.2 Motor (`TicketEngine`)

**`on_external(fact: str, now: datetime) -> None`**

1. `fact` passa pela mesma conferência de identificador da boleta e do símbolo. Inválido é
   `EngineRefusal`, sempre, qualquer que seja o estado.
2. Não faz nada, e não grava nada, se: a boleta não tem plano; já gravou um fato; o estado
   não é `WORKING` nem `UNCERTAIN`; `frozen(plan)` do livro é vazio.
3. Caso contrário grava **um** registro `external` com `ticket`, `fact` e `series` (a lista
   devolvida pelo livro) e, daí em diante, não envia mais nenhuma ordem, de nenhuma perna,
   inclusive de séries sem fato.
4. O destino segue a regra de hoje: `WORKING` enquanto houver ordem viva; sem ordem viva,
   `COMPLETED` se tudo executou, senão `STOPPED`.

A conta não é bloqueada. Nenhuma ordem é cancelada. Retomar depois de pausa não reenvia.
Boleta em rascunho, armada ou disparada não grava: a confirmação é recusada pela admissão.

## 3. Cenários

Referência, já existente nos testes: T1 compra 10 A a 1,00 e vende 10 B a 1,50; foto com A
e B zeradas, A protege B; conta `sim`. Os tempos são segundos depois das 14:00:00.

### 3.1 Livro (`test_sequencing.py`)

**E1 — a série com fato não aceita envio novo; o que existia segue.** Foto com A, B, C e D
zeradas, A protege B e C protege D, nas contas `sim` e `outra`. T1 de referência admitida
nas duas.

| Passo | Esperado |
|---|---|
| `outra`: compra de 10 A executada | — |
| `sim`: compra de 10 A executada; reserva de 4 B para `T1:B:1` | disponível 6; `frozen` = `()` |
| `freeze("sim", "B")` | `frozen` = `("B",)`; disponível 0 |
| reserva de 1 para `T1:B:2` | recusa «reserva indisponível» |
| `confirm_sale("sim", "T1:B:1", "x1", 3)` e `confirm_release("sim", "T1:B:1", 1)` | aceitas |
| T2 com as mesmas pernas, em `sim` | `admissible` recusa «série com fato externo; foto nova necessária» |
| T3 compra 10 C e vende 10 D, em `sim` | admissível; `frozen` = `()` |
| T1 da conta `outra` | `frozen` = `()`; disponível 10 |

**E2 — fato na proteção também zera a venda; a lista sai em ordem.** Foto de referência; T1
com a compra de 10 A executada. `freeze("sim", "A")` → `frozen` = `("A",)`, disponível 0.
Depois `freeze` de C, de B e de B outra vez → `frozen` = `("A", "B")`.

### 3.2 Motor (`test_engine.py`)

Em todos, o fato entra por `freeze` no livro da sessão e, em seguida, `on_external`.

**E3 — para de enviar, mantém as ordens, a conta segue livre.**

| t | Passo | Esperado |
|---|---|---|
| 3 | cotação de A com venda a 1,00, tamanho 6 | A parcial; `T1:B:1` de 6 a 1,50 enviada |
| 4 | fato em B; `on_external("f1")` **duas vezes** | um só `external`, com `{"ticket": "T1", "fact": "f1", "series": ["B"]}`; estado `WORKING`; conta não bloqueada |
| 5 | cotação de A com venda a 1,00, tamanho 4 | A executada; 2 ordens enviadas ao todo; disponível para B = 0 |
| 6 | cotação de B com compra a 1,50, tamanho 4 | B parcial; bruto executado `16.00` |
| 6–7 | cancelamento humano de `T1:B:1`; nova cotação de B | `STOPPED`; 2 ordens enviadas ao todo |

**E4 — fato antes de a venda sair.** T1 confirmada. t=3: fato em B, `on_external("f1")`.
t=4: A com venda a 1,00 → A executada, 1 ordem enviada ao todo, `STOPPED`. Últimos três
registros: `external`, `venue_fill`, `stop`. Bruto executado `10.00`.

**E5 — fato em série que a boleta não usa.** T1 confirmada. t=3: fato em C,
`on_external("f1")` → nenhum `external`. t=4: A com venda a 1,00 → `T1:B:1` de 10 a 1,50
enviada em t=4.

**E6 — boleta nova em série com fato.** Fato em B antes de tudo. T1 proposta; confirmação
em t=2 → `SequenceRefusal` «série com fato externo; foto nova necessária». Estado `DRAFT`;
recibo só com a prévia; `on_external("f1")` não grava. A decisão não foi gasta: o registro
de decisões ainda a aceita.

**E7 — boleta concluída não ganha registro; identificador é conferido.** T1 concluída (A
em t=3 com venda a 1,00; B em t=4 com compra a 1,50). Fato em B, `on_external("f1")` em t=5
→ recibo igual. `on_external("f 1")` → `EngineRefusal`.

**E8 — sobra de série com fato não é emprestada.** T1 compra 10 A, vende 6 B, cancela o
resto e para: sobra 4 de A. Outra boleta enxerga 4 dessa sobra. Fato em A → enxerga 0. T2,
só venda de 4 B com autorização de 4 de A da T1: confirmação em t=6 recusada com a mensagem
do E6.

**E9 — boleta pausada não volta a enviar.** T1 confirmada; pausa em t=2; A com venda a 1,00
em t=3. Fato em B, `on_external("f1")` em t=4; retomada humana em t=5. Esperado: `STOPPED`,
1 ordem enviada ao todo, últimos três registros `external`, `stop`, `resume`.

**E10 — fato na proteção que não é perna.** T1 parada com sobra de 4 de A (como no E8). T2,
só venda de 4 B com a autorização, confirmada em t=5: `T2:B:1` viva. Fato em A,
`on_external("f2")` em t=6 → último registro da T2 é `external` com
`{"ticket": "T2", "fact": "f2", "series": ["A"]}`; estado `WORKING`. t=7: B com compra a
1,50, tamanho 1; cancelamento humano de `T2:B:1`. t=8: nova cotação de B → `STOPPED`; bruto
executado `1.50`.

**E11 — a boleta inteira para, inclusive na série sem fato.** Foto do E1. Cotações de C
(compra 0,95, venda 1,02) e de D em t=1. T1: compra 10 A a 1,00, vende 10 B a 1,50, compra
10 C a 1,00, vende 10 D a 1,50; `net_limit` −10, `gross_cap` 50.

| t | Passo | Esperado |
|---|---|---|
| 2 | confirmação | `T1:A:1` e `T1:C:1` vivas |
| 3 | fato em B; `on_external("f1")` | — |
| 4 | C com venda a 1,00 | C executada |
| 5 | A com venda a 1,00 | A executada |
| fim | — | 2 ordens enviadas ao todo (nenhuma venda de B nem de D); `STOPPED`; um `external` com `series` `["B"]`; conta não bloqueada; disponível para B e para D = 0 |

## 4. Evidência do planejador

- **Fatos de hoje.** Conferidos no `main` `3a4de80`: a recusa de foto diferente e a
  ausência de entrada para fato sem ordem.
- **Protótipo descartável:** `sequencing.py` com 461 linhas (18 a mais), `engine.py` com 506
  (16 a mais), `state.py` com 151 (1 a mais). `mypy --strict` limpo em `backend/`; `pyright`
  limpo no pacote da boleta.
- **Portão completo no protótipo final** (sem `tests/integration`): 11.513 aprovados, 16
  pulados, a mesma contagem do `main`. Nenhum teste existente mudou; as âncoras passam.
- **Cenários:** E1 a E11 passam no protótipo. No `main`, os 11 falham.
- **Mutantes:** 17 defeitos plantados, um por vez, todos detectados (§5). Quatro
  sobreviveram na primeira rodada (5, 6, 9 e 10); por causa deles entraram a segunda conta
  do E1, o E10 e o E11.

## 5. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, quem derrubou no
protótipo.

**Livro**

1. Série com fato ainda reserva (E1, E2, E3, E8).
2. Só a série vendida trava, não a proteção (E2, E8).
3. Só a proteção trava, não a série vendida (E1, E3).
4. A admissão aceita série com fato (E1, E6, E8).
5. O fato vale para todas as contas (E1).
6. `frozen` ignora a proteção do plano (E8, E10).
7. `frozen` devolve todas as séries do plano quando uma tem fato (E1, E2, E3, E10, E11).
8. `frozen` devolve as séries fora de ordem (E2).

**Motor**

9. O motor não para de enviar (E11).
10. O motor continua em execução sem nada a enviar (E11).
11. O fato não é gravado no recibo (E3, E4, E9, E10, E11).
12. O fato é gravado mais de uma vez (E3).
13. Boleta de outra série também para (E5).
14. Boleta concluída ou em rascunho ganha registro (E6, E7).
15. O fato bloqueia a conta (E3, E11).
16. O identificador do fato não é conferido (E7).
17. O recibo não traz a série do fato (E3, E10, E11).

## 6. Critérios de parada

Pare e relate se:

- algum esperado do §3 não reproduzir;
- qualquer teste existente mudar de resultado;
- alguma âncora ou recibo de sessão oficial mudar;
- for preciso mudar arquivo de produção fora do §1, ou algum teto estourar;
- a implementação precisar que a sessão, o roteiro ou o script chamem as funções novas
  (isso é o próximo cartão);
- for preciso cancelar ordem ou bloquear a conta para algum cenário fechar.

## 7. Entrega

1. Commit vermelho com os testes; depois o verde. Os 11 cenários nascem vermelhos.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
   `tests/integration` só no contêiner isolado, nunca no Mac com banco vivo.
3. Descrição do PR: cabeça, contagens, linhas dos três arquivos, os 17 mutantes, as âncoras
   e os recibos oficiais comparados byte a byte, desvios.
4. Copie este cartão para o caminho do §1. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda os cenários do
seu protótipo contra os módulos entregues.

## 8. Depois deste cartão

- **DL3-PR07A6 — entrada do fato:** passo de fato externo no roteiro e na sessão; registro
  no nível da conta (tipo, série, quantidade), sem boleta de origem; aviso a **todos** os
  motores da conta no mesmo passo do congelamento, com teste de que nenhum fica de fora;
  como a foto nova entra. É aí que a compra de motor não avisado deixa de ser possível.
- Em seguida, a fila registrada no `current_state.md`: cota por dependência no livro;
  desmontagem e zeragem de borboleta; apresentação da montagem parcial; repetir, completar
  e ajustar estruturas.

## Revisão adversarial (Claude) — GO na primeira rodada, cabeça `a6b1f07`

Pela regra de processo de Francisco, o revisor **não executou a suíte, a tipagem nem os
mutantes** desta cabeça. Leu o diff, conferiu as evidências pelo SHA-256 e rodou os cenários
do seu protótipo, escrito antes do cartão, mais quatro sondas próprias.

| Verificação | Resultado | Quem |
|---|---|---|
| Suíte sem integração, Linux x86_64 e macOS | 11.529 aprovados, 16 pulados, 261 subtestes nos dois | implementador; logs conferidos |
| mypy estrito e Pyright, nos dois sistemas | 0 erros | implementador; logs conferidos |
| Commit vermelho `1ade63f` antes do verde | os 11 cenários falham na base | implementador; log conferido |
| Testes focais antigos | 569 com resultado idêntico por nome; 16 novos aprovados | implementador; log conferido |
| 17 mutantes do §5 e 4 adicionais, nos dois sistemas | todos detectados | implementador; logs conferidos |
| Integração | só no contêiner Linux isolado: 31 aprovados, 206 pulados | implementador; evidência conferida |
| Manifesto de 126 evidências (`a5399403…b7ce`) e hashes dos dois relatórios | conferem | revisor (26 arquivos) e Francisco (todos, no Mac) |
| `DIFF.patch` das evidências aplicado sobre a base | mesma árvore da cabeça | revisor |
| Diff | seis arquivos; `sequencing.py` 462 (teto 466), `engine.py` 505 (teto 512), `state.py` 151 (teto 152) | revisor |
| Âncoras e recibos das sessões | iguais byte a byte entre base e cabeça | implementador; log conferido |
| Cópia do cartão | SHA-256 `92fbc4e7…8703`, igual ao publicado | revisor |
| 11 cenários do protótipo do planejador (E1 a E11) contra os módulos entregues | todos aprovados | revisor |
| 4 sondas do revisor (abaixo) | todas aprovadas | revisor |

A implementação é equivalente à do protótipo do planejador. Duas diferenças, as duas
aceitas: o destino `STOPPED` por fato externo é um retorno próprio, depois da conferência
de conclusão; e o registro no recibo vem **antes** de a boleta marcar que parou, como já é
na pausa.

Sondas do revisor na cabeça:

1. Primeiro aviso com a boleta já parada: o recibo não muda.
2. Boleta armada: o aviso não grava; o gatilho dispara; a confirmação é recusada com
   «série com fato externo; foto nova necessária» e nada é enviado.
3. Relógio sem fuso no aviso: o recibo recusa, nada é gravado e a boleta **não** fica
   marcada; o aviso repetido com relógio válido grava e para. Sem efeito sem registro.
4. Segundo fato, em outra série da mesma boleta: não gera segundo registro.

Lacunas do cartão do planejador, não bloqueantes:

1. **Estado parado sem teste versionado** (achado da skill, reproduzido pela sonda 1). O
   §5 não tinha mutante que aceitasse `STOPPED` entre os estados que gravam; o E7 só cobre a
   boleta concluída. A produção está certa. A asserção entra no próximo cartão.
2. **Estado incerto fora dos cenários do cartão.** O implementador cobriu por conta própria
   (teste de conciliação da ordem incerta e mutante adicional).
3. **Bruto projetado durante a parada** (nota da skill). No E4, com a compra de 10 viva, a
   boleta segue em `WORKING` e o projetado mostra 25, embora a venda de 15 não possa mais
   sair; ao parar, cai para 10. A regra do DL3-PR07A2 foi respeitada; a apresentação é que
   fica otimista. Entra no próximo cartão.

Limite desta revisão: sem mutantes próprios do revisor nesta cabeça.

Relatórios da skill lidos depois de formado o parecer, com SHA-256 conferidos
(`24e0c8bb…ddae` e `b1b34d3c…4e70`): sem bloqueante. A simplificação opcional S1 (fundir o
retorno de `STOPPED` na condição seguinte) não foi aplicada: o retorno próprio é mais legível
e custa duas linhas.

