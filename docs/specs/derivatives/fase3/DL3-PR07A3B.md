# DL3-PR07A3B — Supercartão: autorização para usar a sobra de uma boleta parada (camada pura)

**Data:** 23/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `b14b941` (DL3-PR07A3 integrado) · **PR novo**, em rascunho
**Decisões que este cartão implementa:**

- Resolução R-A de Francisco, de 22/11/2026: o padrão é a boleta usar só as próprias compras;
  usar proteção de outra boleta é escolha explícita na prévia, que nomeia a série, a boleta
  de origem e a quantidade máxima, e faz parte da confirmação.
- Decisões de Francisco de 23/11/2026: (1) **só vale a sobra de boleta já parada**; (2) **a
  boleta que usa a sobra pode ser só de venda** — venda até as compras próprias mais o
  autorizado.

## 0. Escopo

**O que acontece hoje.** Depois do DL3-PR07A3, a venda de uma boleta só é liberada pelas
compras dela mesma. A sobra de uma boleta parada (o que ela comprou e não vendeu) não pode
ser usada por nenhuma outra. Uma boleta só de venda é recusada no plano.

**O que este cartão entrega.** A autorização passa a existir em três lugares, todos sem
efeito no motor:

1. **Versão assinada.** A boleta e a prévia ganham a lista de autorizações. A lista entra no
   resumo criptográfico e no corpo da prévia gravado no recibo.
2. **Plano.** A quantidade autorizada soma à proteção da série. Uma boleta só de venda passa
   a ter plano quando a autorização cobre a venda.
3. **Livro de reservas.** O livro passa a saber que uma boleta parou, calcula a sobra dela e
   a reserva com exclusividade para quem tem autorização, até o teto autorizado.

**O que este cartão não faz.** O motor **recusa** qualquer boleta com autorização, com
mensagem própria. A ligação do motor (parar a boleta no livro, enviar a venda coberta pela
sobra, mostrar indisponibilidade, registrar no recibo a origem e a quantidade usada) é o
cartão seguinte, DL3-PR07A3C (§8). Dividi o trabalho em dois PRs para que cada revisão caiba
em uma leitura; o custo é um PR a mais na fila.

Também fora: roteiro de replay, sessão, estado, corretora de papel. Nenhuma dependência nova.

## 1. Arquivos e tetos

| Arquivo | O que muda | Teto (hoje) |
|---|---|---|
| `backend/derivatives/ticket/models.py` | modelo da autorização; campo na versão assinada | 216 (195) |
| `backend/derivatives/ticket/digest.py` | a lista entra no resumo quando não está vazia | 48 (43) |
| `backend/derivatives/ticket/sequencing.py` | plano, livro e exposição parcial | 406 (366) |
| `backend/derivatives/ticket/engine.py` | só a recusa em `_propose` | 435 (432) |
| `tests/unit/derivatives/ticket/test_models.py` | W1 e W2 | — |
| `tests/unit/derivatives/ticket/test_sequencing.py` | W3 a W13, W15 e W16 | — |
| `tests/unit/derivatives/ticket/test_engine.py` | W14 | — |
| `docs/specs/derivatives/fase3/DL3-PR07A3B.md` | cópia deste cartão | — |

**Não muda:** `receipt.py`, `state.py`, `session.py`, `replay.py`, `paper_venue.py`,
`scripts/derivatives_ticket_replay.py`, `current_state.md`, arquivos protegidos.

**Nenhum teste existente muda de resultado.** As âncoras oficiais das sessões `calmo`,
`leilao` e `rapido` não mudam, e o recibo de uma boleta sem autorização continua idêntico
byte a byte.

## 2. Regra

### 2.1 Autorização (`models.py`)

Modelo público `CoverageGrant`, imutável, com três campos:

| Campo | Regra |
|---|---|
| `series` | série de proteção; texto não vazio, convertido para maiúsculas |
| `origin` | boleta de origem; o mesmo alfabeto do identificador de boleta do motor (`A-Z a-z 0-9 . _ -`), ao menos um caractere |
| `quantity` | inteiro positivo; é o **máximo** que a boleta pode usar |

A versão assinada (boleta e prévia) ganha o campo `coverage`: tupla de até **4**
autorizações, vazia por padrão. Duas autorizações com o mesmo par (série, origem) são
recusadas na validação, com «autorização de cobertura duplicada».

**Serialização.** Com a lista vazia, a chave `coverage` **não aparece** na serialização do
modelo. É isso que mantém idênticos os recibos e as âncoras de hoje. Com a lista preenchida,
a chave aparece com os três campos de cada autorização, na ordem em que foram informadas.

### 2.2 Resumo criptográfico (`digest.py`)

Com a lista vazia, os bytes canônicos são os de hoje. Com a lista preenchida, entra a chave
`coverage` com as autorizações **ordenadas por (série, origem)**, cada uma com `origin`,
`quantity` e `series`. A ordem em que o usuário informou as autorizações não muda o resumo.

### 2.3 Plano (`plan_legs` e `partial_exposure`)

- A quantidade autorizada de uma série **soma** às compras da própria boleta nessa série. A
  venda cabe quando compras próprias + autorizado ≥ quantidade vendida.
- A série autorizada precisa constar da foto de posição. Se não constar: «série sem
  evidência».
- Toda autorização precisa proteger alguma venda da boleta. Se a série autorizada não
  protege nenhuma: «autorização sem venda correspondente».
- Boleta só de venda **sem** autorização continua recusada como hoje.
- `partial_exposure` aceita boleta sem compra **quando há autorização**; o resultado é só o
  custo conhecido. Sem compra e sem autorização, a recusa de hoje permanece.

### 2.4 Livro de reservas (`ReservationBook`)

**Parar.** Método público novo `close(account, ticket)`: marca a boleta como parada. Boleta
que o livro não conhece naquela conta: «boleta desconhecida». Repetir a chamada não muda
nada.

**Sobra.** A sobra de uma boleta de origem em uma série é: compras executadas dela nessa
série, menos tudo o que já foi coberto por essas compras (saldo vivo mais executado), seja
em ordens da própria origem, seja em ordens de outras boletas autorizadas.

**Quem pode vender com o quê.** `available` e `reserve` ganham o parâmetro nomeado
`origin`, opcional.

| Chamada | Regra |
|---|---|
| sem `origin` | compras da própria boleta, como hoje. **Boleta parada: 0** |
| com `origin` | o menor entre a sobra da origem e (autorizado − já usado por esta boleta nessa origem e série). Vale **0** se a origem não estiver parada, se a origem for a própria boleta ou se a boleta não tiver autorização para aquele par (série, origem) |

Nos dois casos o resto do cálculo fica como está: teto pela quantidade da perna menos o que
a boleta já enviou, arredondamento ao lote e, na desmontagem, o teto pelo saldo comprado da
conta. O «já usado» conta o saldo vivo e o executado.

Cada ordem reservada guarda a origem da cobertura (a própria boleta, quando não há
`origin`). A reserva continua exclusiva: conferir e ocupar na mesma seção crítica.

**Admissão.** `admissible` e `admit` recusam o plano quando, para alguma autorização:

- a origem é a própria boleta ou não está parada: «boleta de origem não parada»;
- a sobra da origem naquela série é zero ou menor: «sobra indisponível».

A admissão não reserva a sobra. Quem reserva é `reserve`, no envio.

### 2.5 Motor (`engine.py`)

`_propose` recusa a boleta com autorização, depois de validar o modelo e antes de planejar,
com `EngineRefusal("autorização de cobertura ainda não disponível no motor")`. Nenhuma
prévia é gravada.

## 3. Cenários

Auxiliares de `test_sequencing.py`: `BUY` (compra A 10 a 1,00), `SELL` (vende B 10 a 1,50),
`draft`, `position()` (conta `sim`, A protege B), `close_plan()`. Use a conta `sim`.

**Livro de sobra** (usado de W4 a W12): a T1, com o plano de referência (`BUY`, `SELL`), é
admitida, compra 10 A, reserva e executa a venda de 6 B, e é parada. **Sobra da T1 em A: 4.**

**Boleta só de venda** de `n` B: uma perna (vende B `n` a 1,50), líquido `−1,50 × n`, bruto
`1,50 × n`, com a autorização (A, T1, `n`), salvo indicação.

### 3.1 Versão assinada

**W1 — modelo.**

- `CoverageGrant(series="a", origin="T1", quantity=4)` resulta em (`A`, `T1`, 4).
- Recusas de validação: origem `"T 1"`, `"T1:x"` e vazia; quantidade 0 e `True`; série vazia.
- Boleta de referência sem autorização: `coverage == ()`.
- Duas autorizações (A, T1), de 4 e de 2, na mesma boleta: recusa.
- Cinco autorizações (origens T0 a T4): recusa. Quatro: aceita.

**W2 — resumo e recibo.** Prévias feitas da boleta de referência com
`partial_exposure=Decimal("10")`:

| Prévia | Esperado |
|---|---|
| sem autorização | resumo `d258890d354ab0aabd95f2ae8e4fee95aa1f05e5afd102082d8f8141bd27c0af` (o mesmo do `main`); `coverage` ausente da serialização e dos bytes canônicos |
| autorizações (A, T9, 2) e (A, T1, 4), nessa ordem | resumo `f61d4551b8be2caec9f54774d536acf5fbc2655578555dc4843862de3e86a84e` |
| as mesmas, na ordem inversa | o mesmo resumo `f61d4551…a84e` |
| (A, T1, 5) e (A, T9, 2) | resumo diferente |

Os bytes canônicos da segunda prévia contêm, literalmente:
`"coverage":[{"origin":"T1","quantity":4,"series":"A"},{"origin":"T9","quantity":2,"series":"A"}]`

Recibo com as duas primeiras prévias: o corpo da primeira não tem a chave `coverage`; o da
segunda tem `[{"series":"A","origin":"T9","quantity":2},{"series":"A","origin":"T1","quantity":4}]`
(ordem informada); o recibo verifica.

### 3.2 Plano

**W3.** Foto padrão, salvo indicação.

| Boleta | Esperado |
|---|---|
| só venda 4 B, autorização (A, T1, 4) | pernas: só a venda; dependências `(("B", "A", False),)`; proteção da venda: `A` |
| só venda 4 B, sem autorização (líquido −6, bruto 6) | «pareamento ausente ou ambíguo» |
| só venda 5 B, autorização de 4 | «quantidade de proteção insuficiente» |
| compra 1 A a 1,00 + venda 5 B (líquido −6,50, bruto 8,50), autorização de 4 | aceita; dependências `(("B", "A", False),)` |
| referência + autorização (B, T1, 4) | «autorização sem venda correspondente» |
| referência + autorização (Z, T1, 4) | «série sem evidência» |
| só venda 4 A a 1,00 (líquido −4, bruto 4), autorização (B, T1, 4), foto A +10 e B −10 | dependências `(("A", "B", True),)` |

Exposição parcial da boleta só de venda de 4 B: `0`; com custo conhecido `0,07`: `0,07`. Sem
autorização: recusa, como hoje.

### 3.3 Livro

**W4 — a origem precisa estar parada.** Livro de sobra **sem** parar a T1. T2 só de venda de
4 B:

- `admissible` da T2: «boleta de origem não parada».
- Disponível da T2 com origem T1: 0. Reserva de 1 com origem T1: recusa.
- Disponível da T1 (própria): 4.

**W5 — a sobra depois de parar.** Livro de sobra. T2 e T3 só de venda de 4 B.

| Passo | Esperado |
|---|---|
| início | T1 própria: 0; reserva de 1 pela T1: recusa. T2 própria: 0; T2 com origem T1: 4 |
| T2 é admitida e tenta reservar 4 **sem** origem | recusa |
| T2 reserva 4 com origem T1 | T2 com origem T1: 0 |
| `admissible` da T3 | «sobra indisponível» |
| da ordem da T2, 1 executa e 3 são liberadas | T2 com origem T1: 3 |
| `admissible` da T3 | aceita; T3 com origem T1: 3 |

**W6 — a autorização é um teto.** Livro de sobra. T2 só de venda de 3 B, autorização de 3:
disponível com origem T1 = 3. Reserva 2: fica 1. As 2 executam: continua 1. T3 só de venda
de 8 B, autorização de 8: disponível com origem T1 = 2.

**W7 — teto menor que a sobra, com compras próprias.** Livro de sobra. T2: compra 2 A a 1,00
e vende 5 B a 1,50 (líquido −5,50, bruto 9,50), autorização (A, T1, 3). T2 admitida.

| Passo | T2 própria | T2 com origem T1 |
|---|---|---|
| início | 0 | 3 |
| reserva 3 com origem T1 e as 3 executam | 0 | 0 |
| a T2 compra 2 A | 2 | 0 |

No fim, uma T3 só de venda de 4 B vê 1 com origem T1.

**W8 — compras próprias mais o autorizado.** Livro de sobra. T2: compra 6 A a 1,00 e vende
10 B (líquido −9, bruto 21), autorização (A, T1, 4). T2 admitida.

| Passo | T2 própria | T2 com origem T1 |
|---|---|---|
| início | 0 | 4 |
| reserva 4 com origem T1; a T2 compra 6 A | 6 | 0 |
| reserva 6 sem origem | 0 | 0 |

**W9 — origem errada, boleta desconhecida, outra conta.** Livro de sobra.

- T2 só de venda de 4 B com autorização (A, **T2**, 4): `admissible` da T2 recusa com
  «boleta de origem não parada»; disponível com origem T2: 0.
- `close("sim", "T9")` e `close("outra", "T1")`: «boleta desconhecida».
- T2 só de venda com autorização (A, **T9**, 4): disponível com origem T1: 0.
- Plano só de venda feito com a foto da conta `outra`: `admissible` recusa com «boleta de
  origem não parada»; disponível com origem T1: 0.

**W10 — boleta parada não usa a própria sobra.** Livro novo. T1 com a boleta de referência
mais a autorização (A, T1, 4). A T1 compra 10 A (direto por `confirm_buy`).

| Passo | T1 própria | T1 com origem T1 |
|---|---|---|
| depois da compra | 10 | 0 |
| depois de `close` | 0 | 0 |

`admissible` desse plano para a T1, depois de parada: «boleta de origem não parada».

**W11 — corrida.** Livro de sobra. Oito boletas (T2 a T9) só de venda de 4 B tentam, em
paralelo, reservar 4 com origem T1. Exatamente uma consegue.

**W12 — execução tardia da origem aumenta a sobra.** Livro de sobra com a T1 comprando 6 e
vendendo 6 (sobra 0). `admissible` da T2: «sobra indisponível». Chega mais uma execução de
compra de 2 A da T1: `admissible` aceita e o disponível com origem T1 é 2.

**W13 — desmontagem.** Livro novo. T1 com `close_plan()` é admitida, recompra 4 B e é
parada. T2: só venda de 4 A a 1,00 (líquido −4, bruto 4), autorização (B, T1, 4), mesma
foto. Disponível com origem T1: 4. T2 admitida reserva 4: fica 0.

### 3.4 Motor

**W14.** Motor da T2 com a foto padrão. `propose` de uma boleta só de venda de 4 B:
`EngineRefusal` com «autorização de cobertura ainda não disponível no motor». O motor fica
sem prévia e o recibo sem eventos.

### 3.5 Duas lacunas de teste herdadas do DL3-PR07A3

Os dois cenários **já passam no `main`**; entram porque nenhum teste os fixava.

**W15 — uma compra protege duas vendas da mesma boleta.** Foto com A, B e C; A protege B e
A protege C. T1: compra 10 A, vende 4 B e 6 C a 1,50 (líquido −5, bruto 25).

| Passo | Disponível B | Disponível C |
|---|---|---|
| 5 A compradas | 4 | 5 |
| reserva 4 B | 0 | 1 |
| mais 5 A compradas | 0 | 6 |
| as 4 B executam | 0 | 6 |

**W16 — recompra não passa do vendido da conta.** Com `close_plan()` (B vendida em 10): a T1
recompra 4, a T2 recompra 6, a T3 tenta recomprar 1: «execuções excedem posição vendida».

## 4. Evidência do planejador

- **Protótipo descartável** sobre o `main` `b14b941`: 62 linhas líquidas a mais nos quatro
  arquivos de produção (`models` 214, `digest` 47, `sequencing` 403, `engine` 434). Tipagem estrita
  limpa no pacote da boleta.
- **Portão completo no protótipo** (sem `tests/integration`): 11.422 aprovados, 16 pulados,
  a mesma contagem do `main`. Nenhum teste existente mudou; as âncoras das sessões seguem
  passando.
- **Cenários do §3:** os 16 passam no protótipo. W15 e W16 passam também no `main` intacto.
- **Resumos do W2:** calculados no protótipo; o da prévia sem autorização é o mesmo do
  `main`.
- **Mutantes:** 24 defeitos plantados, um por vez, todos detectados (§5). Na primeira rodada
  quatro sobreviveram; W7 e W10 entraram por causa deles.

## 5. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, quem derrubou no
protótipo.

**Versão assinada**

1. Lista vazia aparece na serialização da prévia (W2).
2. O resumo ignora a autorização (W2).
3. O resumo depende da ordem informada (W2).
4. Autorização duplicada aceita (W1).
5. Origem aceita qualquer texto (W1).

**Plano**

6. Autorização sem venda correspondente aceita (W3).
7. A autorização não soma à proteção (W3 e quase todos do livro).
8. Série autorizada fora da foto aceita (W3).
9. Exposição parcial recusa a boleta só de venda autorizada (W3).
10. Exposição parcial aceita boleta só de venda sem autorização (W3).

**Livro**

11. Sobra de origem ainda não parada é liberada (W4).
12. A admissão não exige origem parada (W4, W9).
13. Boleta parada continua vendendo com as próprias compras (W5, W10).
14. O teto da autorização é ignorado (W7).
15. O uso já executado não conta no teto (W7).
16. A sobra não desconta o que outra boleta já tomou (W5, W6, W7, W8, W11).
17. A ordem coberta pela sobra é registrada como cobertura própria (W5, W6, W7, W8, W11).
18. A origem igual à própria boleta é aceita no cálculo (W10).
19. A origem igual à própria boleta é aceita na admissão (W10).
20. A admissão ignora a sobra zerada (W5, W12).
21. A admissão troca «zero ou menor» por «menor que zero» (W5, W12).
22. A autorização de uma origem vale para outra (W9).
23. Parar boleta desconhecida é aceito (W9).

**Motor**

24. O motor aceita boleta com autorização (W14).

## 6. Critérios de parada

Pare e relate se:

- algum esperado do §3 não reproduzir, em especial os dois resumos do W2;
- qualquer teste existente mudar de resultado, ou alguma âncora de sessão mudar;
- o recibo de uma boleta sem autorização deixar de ser idêntico ao de hoje;
- for preciso mudar arquivo de produção fora do §1, ou algum teto estourar;
- W15 ou W16 falharem (seria defeito do `main`, não deste cartão).

## 7. Entrega

1. Commit vermelho com os testes; depois o verde. W15 e W16 nascem verdes: declare isso.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
   `tests/integration` só no contêiner isolado, nunca no Mac com banco vivo.
3. Descrição do PR: cabeça, contagens, linhas dos quatro arquivos, os 24 mutantes, os dois
   resumos do W2, as âncoras conferidas, desvios.
4. Copie este cartão para o caminho do §1. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda os cenários do
seu protótipo contra os módulos entregues.

## 8. Depois deste cartão

**DL3-PR07A3C — o motor passa a usar a autorização.**

- Ao parar sem divergência, o motor para a boleta no livro (`close`).
- No envio da venda, o motor usa primeiro as compras próprias e depois a sobra autorizada,
  reservando com exclusividade. Se outra boleta levou a sobra, mostra indisponibilidade.
- O recibo registra, em cada ordem coberta por sobra, a origem e a quantidade usada.
- A edição da prévia conserva a autorização.
- A recusa do §2.5 sai.
- Uma sessão nova no roteiro de replay, com âncora própria; as três atuais não mudam.

Depois: DL3-PR07A4 (relato contraditório e evento externo) e DL3-PR07B (zeragem e borboleta
no motor).
