# DL3-PR06 — Supercartão: sessão de replay, roteiro de decisões e três sessões completas

**Data:** 22/11/2026 · **Autor:** Claude · **Para:** Codex
**Base:** `main` = `51fd6d2` (DL3-PR05b integrado) · **Branch:** `feat/dl3-pr06-ticket-replay`
**PR:** em rascunho. É o último PR de código da Fase 3.

---

## 0. O que entra e duas decisões de desenho

Entra: um condutor que roda uma fita de replay com várias boletas, um script que faz o papel
do humano a partir de um roteiro em arquivo, três sessões completas com esperado literal, e
os arquivos de saída (recibos e resumo).

**Decisão 1 — o comando não entra em `backend/derivatives/cli.py`.** O `DL3_CARDS.md` previa
isso; mudou. A regra de arquitetura do DL3-PR05a proíbe qualquer módulo de `backend/`, fora
`gate.py`, de emitir decisão. Quem emite decisão no simulador faz o papel do humano e fica
**fora** do produto. Por isso:

- o condutor fica em `backend/derivatives/ticket/session.py` e **nunca** emite decisão;
- o humano simulado fica em `scripts/derivatives_ticket_replay.py`.

A regra de arquitetura do gate **não muda**.

**Decisão 2 — o relatório de fechamento da fase não é deste PR.** O revisor escreve na
integração. Não crie `RELATORIO_FECHAMENTO_FASE3.md` e não edite `current_state.md`.

Fora do escopo: tela, rede, conta real, persistência, editar ou atualizar a boleta pelo
roteiro, desarmar e descartar pelo roteiro, custos.

## 1. Arquivos e limites

| Arquivo | Conteúdo |
|---|---|
| `backend/derivatives/ticket/session.py` | novo, **≤ 150 linhas** (§2) |
| `scripts/derivatives_ticket_replay.py` | novo, **≤ 220 linhas** (§3 e §4) |
| `tests/fixtures/derivatives/synthetic/ticket/sessions/` | os seis arquivos do §5, copiados **byte a byte** |
| `tests/unit/derivatives/ticket/test_session.py` | testes da sessão |
| `tests/unit/derivatives/test_ticket_replay_script.py` | testes do script |
| `tests/architecture/test_ticket_boundaries.py` | regras do §7 |
| `docs/specs/derivatives/fase3/DL3-PR06.md` | cópia deste cartão |

- Teto do PR: **370 linhas de produção** (sessão mais script). Passou: pare e relate.
- Nenhum módulo existente de `backend/` muda. Nenhum esperado de teste existente muda.
- Zero dependência nova. Sem `print`: resumo em arquivo e em `loguru`.
- O script passa em `mypy --strict` chamado sozinho
  (`mypy scripts/derivatives_ticket_replay.py --strict`), além do portão normal.

## 2. Sessão (`session.py`)

```python
class SessionRefusal(ValueError):
    """Fita ou roteiro incompatível com a sessão."""

class ReplaySession:
    def __init__(self, replay: Replay, *, config: TicketSimConfig) -> None: ...
    @property
    def ledger(self) -> DecisionLedger: ...
    def open(self, ticket: str, position: Position, draft: TicketDraft,
             now: datetime) -> TicketEngine: ...
    def engine(self, ticket: str) -> TicketEngine: ...
    def receipt(self, ticket: str) -> Receipt: ...
    def advance_to(self, seq: int) -> None: ...
    def finish(self) -> None: ...
    def check_time(self, at: datetime) -> None: ...
    def summary(self) -> dict[str, object]: ...
```

- **P1 — Peças compartilhadas.** O construtor cria um `BookView`, uma
  `PaperVenue(replay.session_close)`, um `ReservationBook`, um `DecisionLedger` e um
  `AccountHalts`. Todas as boletas da sessão usam essas mesmas instâncias.
- **P2 — `open`.** Id de boleta já aberto nesta sessão, em qualquer conta:
  `SessionRefusal`. Senão cria um `Receipt` e um `TicketEngine` com as peças de P1 e chama
  `propose(draft, now)`. Se o construtor do motor ou `propose` levantar, a exceção sobe e a
  boleta **não** fica registrada.
- **P3 — `advance_to(seq)`.** Processa, na ordem do arquivo, cada evento ainda não
  processado com `event.seq <= seq`. `seq` menor que o `seq` do último evento já processado:
  `SessionRefusal`. `finish()` processa todos os que restam.
- **P4 — Um evento, nesta ordem:** `book.advance(ev)`; `reports = venue.advance(ev)`; para
  cada motor, na ordem em que foi aberto: `on_reports` só com os relatórios cujo `order_id`
  está em `engine.orders`, com `ev.ts`; em seguida `on_market(ev)`.
- **P5 — Fita incompatível.** `VenueRefusal` saindo de `venue.advance` vira
  `SessionRefusal`.
- **P6 — `check_time(at)`.** `at` não pode ser anterior ao `ts` do último evento processado
  nem posterior ao `ts` do próximo evento ainda não processado. Fora disso:
  `SessionRefusal`. Sem evento processado não há limite inferior; sem evento restante não
  há limite superior.
- **P7 — `summary()`** devolve exatamente estas chaves (exemplo abreviado, com uma boleta
  e uma ordem):

```json
{"aviso": "SIMULADO — resultado em papel é teto otimista, não previsão.",
 "eventos": 9,
 "contas_bloqueadas": [],
 "boletas": {"T1": {"conta": "sim", "estado": "COMPLETED", "pausada": false,
   "ordens": {"T1:A:1": {"estado": "FILLED", "executado": 10}},
   "recibo_eventos": 12, "recibo_hash": "<hash do último evento do recibo>"}}}
```

`eventos` = quantos eventos da fita já foram processados. `contas_bloqueadas` = contas das
boletas abertas com `halts.blocked` verdadeiro, em ordem alfabética. `executado` =
`venue.poll(order_id).filled`, ou 0 quando `poll` devolve `None`.

## 3. Roteiro e script

Uso, a partir da raiz do repositório:

```bash
uv run python scripts/derivatives_ticket_replay.py \
  --replay <fita.replay.json> --roteiro <arquivo.roteiro.json> --out <pasta>
```

**Formato do roteiro** (JSON; chave desconhecida ou faltando é roteiro inválido):

```json
{"decision_ttl_s": 60,
 "positions": [ <Position> ],
 "steps": [
  {"after_seq": 2, "at": "2026-11-23T14:00:02Z", "do": "open", "ticket": "T1",
   "account": "sim", "draft": <TicketDraft>},
  {"after_seq": 2, "at": "...", "do": "arm", "ticket": "T1", "spec": <TriggerSpec>},
  {"after_seq": 6, "at": "...", "do": "confirm", "ticket": "T1"},
  {"after_seq": 7, "at": "...", "do": "cancel", "ticket": "T1", "order_id": "T1:A:1"},
  {"after_seq": 4, "at": "...", "do": "reconcile", "ticket": "T1", "order_id": "T1:B:1"},
  {"after_seq": 6, "at": "...", "do": "pause", "ticket": "T1"},
  {"after_seq": 7, "at": "...", "do": "resume", "ticket": "T1"}]}
```

Ações aceitas: só essas sete. `after_seq` = `seq` do último evento que precisa estar
processado antes do passo (0 = nenhum). `at` = instante do passo, com fuso.

**Atenção, fato conferido no `main`:** `Position`, `TicketDraft` e `TriggerSpec` são
estritos. Validar um dicionário Python com listas falha (`tuple_type`). Valide sempre o
**texto JSON** com `model_validate_json`.

**Validação antes de rodar (falhou: roteiro inválido):** `decision_ttl_s` inteiro positivo;
contas únicas em `positions`; `after_seq` não decresce de um passo para o seguinte; todo
passo que não é `open` cita boleta com `open` em passo anterior; a conta do `open` existe
em `positions`.

**Execução.** Para cada passo, na ordem, com `n` = posição do passo começando em 1:

1. `session.advance_to(after_seq)`; depois `session.check_time(at)`;
2. a ação, sempre com `now = at`:

| `do` | Chamada |
|---|---|
| `open` | `session.open(ticket, posição da conta, draft, at)` |
| `confirm` | `engine.confirm(decisão EXECUTE com a prévia atual do motor, at)` |
| `arm` | `engine.arm(spec, decisão ARM com a prévia atual e `spec_digest(spec)`, at)` |
| `cancel` | `engine.cancel(order_id, decisão CANCEL_ORDER com esse `order_id`, at)` |
| `resume` | `engine.resume(decisão RESUME, at)` |
| `pause` | `engine.pause(at)` |
| `reconcile` | `engine.reconcile(order_id, at)` |

Toda decisão é emitida com `gate.issue`: `ticket` = a boleta do passo; `nonce` = `"n"`
seguido de `n` (passo 3 usa `"n3"`); `issued_at` = `at`; `expires_at` = `at` mais
`decision_ttl_s` segundos. Um passo emite no máximo uma decisão.

3. **Recusa não é erro.** Se a ação de um passo que não é `open` levantar `EngineRefusal`,
   `DecisionRefusal`, `SequenceRefusal`, `DeadlineRefusal` ou `TriggerRefusal`, o script
   anota a recusa (passo, ação, boleta, nome da classe da exceção) e **segue** para o
   próximo passo.
4. Depois do último passo: `session.finish()`.

**Entrada inválida.** `ReplayError`, roteiro inválido, `SessionRefusal`, ou qualquer exceção
em um passo `open`: o script registra o motivo em `loguru`, **não escreve nenhum arquivo**
em `--out` e sai com código **2**. Rodou até o fim: código **0**.

`main(argv) -> int` devolve o código; o bloco `__main__` só chama `SystemExit(main())`.

## 4. Saídas em `--out` (só quando o código é 0)

- **`resumo.json`:** o dicionário de `session.summary()` mais a chave `"recusas"`, lista na
  ordem dos passos de `{"passo": n, "acao": do, "boleta": ticket, "erro": nome da classe}`.
  Gravado com `sort_keys=True`, `indent=2`, `ensure_ascii=False` e uma quebra de linha no
  fim.
- **`recibo_<boleta>.jsonl`:** um arquivo por boleta aberta, uma linha por evento do recibo,
  com as chaves `seq`, `ts` (`event.ts.isoformat()`), `kind` (`event.kind.value`),
  `payload` (**o texto**: `event.payload.decode("utf-8")`), `prev_hash` e `hash`. Cada
  linha com `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`.
- Em `loguru` (nível INFO): a linha do aviso e uma linha por boleta com estado final.

## 5. As três sessões

Os seis arquivos estão prontos em `reports/fase03/dl3-pr06/` no Mac. Copie sem alterar
nenhum byte e confira o SHA-256:

| Arquivo | SHA-256 |
|---|---|
| `calmo.replay.json` | `b08cc5dabd9e7461d163628c11dfe30bdc23acec846620a6db4d1998f81cd6f2` |
| `calmo.roteiro.json` | `a03c9ff58bcc0f2f0ae20ee5f1a3c1d5e5a8e2f3c7259b2fd5c1f481b78dc253` |
| `leilao.replay.json` | `6b9c5c3d77709373c751a42edad46b65c8ec33484885d2bc7cd0366c932e3d51` |
| `leilao.roteiro.json` | `9671efd951395f371946af625afa7732338c2fa3ffc1b567b41d1e053a269c8c` |
| `rapido.replay.json` | `1adf9e725b102135e09d7abef5483c0d7e73b574623289b287017f2daa91797e` |
| `rapido.roteiro.json` | `48162f197d3a18b94b849cc6ea72b6041619c22e5afd6f491aa2cd673993bc3e` |

O que cada uma exercita:

- **`calmo`** — trava de abertura (compra A 10 a 1,00; vende B 10 a 1,50). Arma gatilho,
  o gatilho dispara, confirma, pausa, a compra executa pausada, retoma, a venda executa.
- **`leilao`** — abertura em leilão: a primeira confirmação é recusada. Depois confirma,
  compra parcial de 3, venda de 3 executa, novo leilão, pedido de cancelamento, mais 1
  executada no leilão, cancelamento recusado pela venue, expiração no fechamento.
- **`rapido`** — duas desmontagens da mesma posição (A = +10, B = −10). Timeout no envio,
  conta bloqueada, reconciliação, retomada, perda de sequência na fita (do `seq` 5 para o
  7), cancelamento. A segunda boleta é recusada três vezes, por três motivos diferentes.

**Esperado, todos com código de saída 0:**

| Sessão | `eventos` | Boleta | Estado final | Ordens (estado, executado) | Eventos do recibo | `recibo_hash` |
|---|---|---|---|---|---|---|
| `calmo` | 9 | `T1` | `COMPLETED` | `T1:A:1` `FILLED` 10; `T1:B:1` `FILLED` 10 | 12 | `050354936eae64e316000a2f1570845a489dfe87f87f2dc5e70a4ceb742642f7` |
| `leilao` | 11 | `T1` | `STOPPED` | `T1:A:1` `EXPIRED` 4; `T1:B:1` `FILLED` 3 | 12 | `96e50b071fa291d895b4a37a6ad56b460ae1fae33774a4b59290c2f79dc5bd52` |
| `rapido` | 8 | `T1` | `STOPPED` | `T1:B:1` `CANCELLED` 4; `T1:A:1` `FILLED` 4 | 15 | `a81c1cbea973dfd1db5b22b6e6a53ddb0242116442c1387f0cae55d545091cb6` |
| `rapido` | 8 | `T2` | `DRAFT` | nenhuma | 1 | `fbcaafa8eb7934ed7fe77a9f497b676904c5cc1647d42e0b8f5a77da4df3e2b5` |

Em todas: `pausada` falso em toda boleta e `contas_bloqueadas` vazio no fim.

**Sequência de `kind` de cada recibo:**

- `calmo` `T1`: `preview`, `arm`, `trigger`, `confirm`, `start`, `venue_live`, `pause`,
  `venue_fill`, `resume`, `venue_live`, `venue_fill`, `complete`.
- `leilao` `T1`: `preview`, `confirm`, `start`, `venue_live`, `venue_partial`, `venue_live`,
  `venue_fill`, `request_cancel`, `venue_partial`, `venue_cancel_rejected_partial`,
  `venue_expired`, `stop`.
- `rapido` `T1`: `preview`, `confirm`, `start`, `uncertain`, `uncertain`, `reconcile`,
  `venue_partial`, `reconcile`, `pause`, `resume`, `venue_live`, `venue_fill`,
  `request_cancel`, `venue_cancelled`, `stop`.
- `rapido` `T2`: `preview`.

**`recusas` de cada sessão:**

| Sessão | Passo | Ação | Boleta | `erro` |
|---|---|---|---|---|
| `calmo` | — | nenhuma recusa | | |
| `leilao` | 2 | `confirm` | `T1` | `EngineRefusal` |
| `rapido` | 4 | `confirm` | `T2` | `EngineRefusal` |
| `rapido` | 6 | `confirm` | `T2` | `SequenceRefusal` |
| `rapido` | 9 | `confirm` | `T2` | `EngineRefusal` |

**Outros testes obrigatórios sobre as três sessões:**

- rodar cada sessão duas vezes, em pastas diferentes: todos os arquivos saem idênticos byte
  a byte;
- reler cada `recibo_<boleta>.jsonl`, remontar os `ReceiptEvent` e conferir
  `Receipt().verify(eventos, expected_head=recibo_hash)` verdadeiro;
- rodar as três com `socket.socket` trocado por uma função que levanta: passam.

Como conferi: rodei as três fitas e os três roteiros contra as peças reais do `main`
(`51fd6d2`), na ordem de P4 e com as convenções de decisão do §3. Todos os valores das
tabelas acima, inclusive os quatro hashes, saíram dessa execução, duas vezes iguais.
`session.py` e o script ainda não existem; se algum valor não reproduzir, a diferença está
em alguma convenção dos §2 e §3: **pare e relate qual**.

## 6. Entrada inválida e recusas da sessão

| # | Caso | Esperado |
|---|---|---|
| N1 | sessão: `open("T1", …)` e de novo `open("T1", …)` com posição de outra conta | o segundo levanta `SessionRefusal`; `engine("T1")` continua sendo o primeiro |
| N2 | sessão: `advance_to(2)` e depois `advance_to(1)` | `SessionRefusal` |
| N3 | script: `leilao` com o roteiro sem o passo 4 (o `cancel`) | código 2; pasta `--out` sem arquivo. A venue recusa o evento `cancel_rejected` sem pedido pendente (conferido: "recusa sem pedido de cancelamento") |
| N4 | script: `calmo` com o `at` do passo 3 trocado para 14:00:10 (o evento 6 é das 14:00:11) | código 2; nenhum arquivo |
| N5 | script: `calmo` com o `at` do passo 3 trocado para 14:00:14 (o evento 7 é das 14:00:13) | código 2; nenhum arquivo |
| N6 | script: roteiro com um `confirm` de boleta `T9`, que não tem `open` | código 2 |
| N7 | script: roteiro com `after_seq` 6 seguido de `after_seq` 2 | código 2 |
| N8 | script: roteiro com uma chave a mais em um passo | código 2 |
| N9 | script: fita com `seq` repetido | código 2 |
| N10 | script: `calmo` com o símbolo da primeira perna do `open` trocado para `X:A` | código 2; nenhum arquivo |

## 7. Arquitetura

1. `session.py` fica dentro de `ticket/`, então as regras existentes já valem para ele
   (sem rede, sem relógio, sem sorteio, sem emitir decisão). Confirme que os testes
   existentes o alcançam.
2. Novo: `scripts/derivatives_ticket_replay.py` não importa nenhum nome da lista `FORBIDDEN`
   e, de `backend`, só importa módulos de `backend.derivatives.ticket`.
3. Novo: o script não chama relógio do sistema (`datetime.now`, `utcnow`, `today`,
   `time.time`).
4. Novo: em `scripts/`, só esse arquivo importa `gate.issue`.

## 8. Mutantes que devem morrer, um por vez

1. sessão aceitando id de boleta repetido (N1);
2. sessão sem `book.advance` no evento (as três sessões);
3. sessão sem `on_market` (`calmo`: o gatilho não dispara);
4. sessão sem `on_reports` (as três);
5. sessão entregando a todo motor todos os relatórios (`rapido`);
6. `advance_to` processando um evento a mais ou a menos (as três);
7. `check_time` sem o limite inferior (N4);
8. `check_time` sem o limite superior (N5);
9. `VenueRefusal` escapando da sessão (N3: o código tem de ser 2);
10. `executado` vindo da quantidade pedida em vez do `poll` (`leilao`);
11. script com `nonce` fixo (`rapido`);
12. script parando no primeiro passo recusado (`leilao` e `rapido`);
13. script sem anotar a recusa (`leilao`);
14. script escrevendo arquivo quando sai com código 2 (N3, N4, N5, N10);
15. script com `expires_at` anterior a `at` (as três);
16. `payload` do recibo gravado como objeto em vez de texto (releitura com `verify`).

## 9. Critérios de parada

Pare e relate se: algum esperado do §5 não reproduzir; um arquivo do §5 não bater com o
SHA-256; algum módulo existente de `backend/` precisar mudar; a regra de arquitetura do
gate precisar de exceção; `session.py` passar de 150 linhas, o script de 220 ou o PR de 370.

## 10. Entrega

1. Commit vermelho com os testes e os seis arquivos; depois o verde.
2. Portão completo em clone limpo no Mac, mais `mypy --strict` no script. O revisor roda o
   Linux.
3. Descrição do PR: cabeça, contagens, linhas por arquivo, os 16 mutantes, desvios.
4. Copie este cartão para `docs/specs/derivatives/fase3/DL3-PR06.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

## Revisão adversarial (Claude) — duas rodadas, GO na cabeça `029a092`

| Rodada | Cabeça | Parecer | Motivo |
|---|---|---|---|
| 1 | `742b852` | NO-GO | Boletas `T1` e `t1` na mesma sessão, `after_seq=0` ambíguo em fita que começa em zero, pasta de saída reaproveitada, `open` capturando qualquer exceção, propriedade `ledger` sem uso e seis lacunas de teste. Correção no [DL3-PR06B](DL3-PR06B.md) |
| 2 | `029a092` | GO | Sem bloqueante |

Quatro pontos da rodada 1 eram lacunas deste cartão, não erro de implementação: ele não
tratava maiúsculas nos ids, não exigia sequência positiva na fita, mandava capturar
"qualquer exceção" na abertura e definia a propriedade `ledger`, que ninguém usava.

| Verificação do revisor na cabeça `029a092`, clone limpo, Linux x86_64 | Resultado |
|---|---|
| Pytest sem integração | 11.227 aprovados, 16 pulados, 261 subtestes |
| `mypy backend/ --strict`, `mypy --strict` no script e `pyright backend/` | 0 erros |
| Linhas | `session.py` 116 (teto 150), script 220 (teto 220), PR com 336 de produção (teto 370) |
| Três sessões oficiais pela linha de comando, de outro diretório | os quatro hashes do cartão reproduzem |
| 75 mutantes do revisor, um por vez | 64 mortos; 11 vivos, dos quais 3 são lacuna de teste e 8 são equivalentes ou redundantes |
| Sondas de destino: `x/..`, pai que é link quebrado, pai que é arquivo, destino que é link, `../irmao`, barra final, destino vazio | código 2 ou 0 conforme o cartão, sem traceback e sem resíduo |
| Oito processos disputando o mesmo destino | um publica a sessão inteira, sete recebem código 2 |
| Arquivos protegidos, fixtures e módulos existentes de `backend/` | intactos |

Observações, nenhuma bloqueante:

1. **Três comportamentos corretos sem teste.** Destino terminado em `..`, pai que é link
   quebrado e prazo de decisão que estoura a data: a linha de comando devolve 2 nos três,
   mas remover cada tratamento não derruba nenhum teste.
2. **Bloco de caminhos com `..` (14 linhas).** Funciona nos casos sondados, mas quatro
   mutantes sobrevivem nele: há condição que nenhum teste distingue. Recusar
   `..` em `--out` tiraria o bloco inteiro. Candidato à rodada de simplificação (DP-17).
3. **Renomeação exclusiva por `ctypes`.** Vai além do que o cartão pediu (pasta nova e um
   `rename`). Fecha a disputa entre processos e, onde o sistema não oferece a primitiva,
   o comando recusa publicar. Conferido em Linux x86_64 pelo revisor e em macOS e Linux
   arm64 pelo implementador.
4. **Uma linha de teste com 105 colunas** (`test_ticket_replay_script.py`, linha 287).
   Entra como higiene no próximo cartão.
5. **Pai sem permissão de escrita** não foi sondado: o revisor roda como administrador.

Relatórios da skill lidos depois do parecer formado, com SHA-256 conferidos
(`99384157…2ce0` e `2697023d…6e36`): GO técnico, sem bloqueante e sem simplificação com
prova. A pesquisa bibliográfica do implementador não foi reconferida pelo revisor.
