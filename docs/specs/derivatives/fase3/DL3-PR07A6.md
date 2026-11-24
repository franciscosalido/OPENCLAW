# DL3-PR07A6 — Supercartão: entrada do fato externo pela sessão e pelo roteiro (DP-13, 2ª parte)

**Data:** 23/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `d8ba166` (DL3-PR07A5 integrado)
**PR novo**, em rascunho
**Decisões que este cartão implementa:**

- DP-13 de Francisco (Revisão 2, 22/11/2026): «Já um exercício ou enquadramento confirmado
  pela corretora é **fato externo legítimo**. Deve compor a posição conciliada mesmo que
  nenhuma boleta o tenha originado.» E, na mesma decisão: «Duplicata idêntica é reconhecida
  uma vez.»
- Francisco, 23/11/2026: a boleta da série atingida para de enviar; a conta não bloqueia.
- Francisco, sobre os três brutos (22/11/2026): «o que autorizei, o que aconteceu e o que
  ainda pode acontecer».

## 0. Escopo

**O que acontece hoje.** Fatos conferidos no `main`:

- O livro sabe congelar uma série e o motor sabe reagir ao aviso (DL3-PR07A5), mas nada em
  produção chama as duas funções. Não há passo de fato externo no roteiro.
- Não existe registro do fato fora do recibo de uma boleta. Um fato numa conta sem boleta
  não fica em lugar nenhum.
- Uma boleta avisada, com ordem ainda viva, segue em execução e mostra como projetado o
  volume inteiro do plano, embora a venda não possa mais sair. No exemplo da revisão do
  DL3-PR07A5: projetado 25,00 com só a compra de 10,00 viva.

**O que este cartão entrega.**

1. **Sessão.** Uma entrada única para o fato: confere, registra, congela a série na conta e
   avisa **todas** as boletas daquela conta, nessa ordem e no mesmo passo.
2. **Registro sem boleta de origem.** Um registro encadeado da sessão, com conta, série,
   tipo, quantidade com sinal e instante. Repetição idêntica é reconhecida uma vez;
   repetição com conteúdo diferente é recusada.
3. **Roteiro e saída.** Passo `external` no roteiro; arquivo `fatos_externos.jsonl` e chave
   `fatos_externos` no resumo, **só quando houver fato**.
4. **Projetado.** A partir do aviso, o projetado da boleta é o executado mais o saldo das
   ordens vivas: o que ainda pode acontecer.
5. O teste que faltou no DL3-PR07A5: boleta já parada não ganha registro.

**O que este cartão não faz.**

- **Não aplica a quantidade.** O fato fica registrado com a quantidade; saldos e capacidades
  não mudam na sessão. A série segue congelada até a foto nova.
- **Foto nova.** Conferir que a foto seguinte é a anterior mais execuções mais fatos exige
  histórico entre sessões: é do cartão de histórico persistente.
- Não cancela ordem, não bloqueia conta, não descongela.
- **Projetado depois de cancelamento humano.** Tem o mesmo otimismo (conferido: 25,00
  projetados com a venda em cancelamento) e fica como está: mexer nele pode mudar recibos
  oficiais. Vai para o cartão de apresentação.
- Rótulos em português dos tipos de fato: não há tela que os mostre ainda.

Nenhuma dependência nova.

## 1. Arquivos e tetos

| Arquivo | O que muda | Teto (hoje) |
|---|---|---|
| `backend/derivatives/ticket/session.py` | `external`, `facts`, tipos de fato, chave no resumo | 174 (119) |
| `backend/derivatives/ticket/engine.py` | projetado a partir do aviso; conferência de identificador pública | 508 (505) |
| `scripts/derivatives_ticket_replay.py` | passo `external`; arquivo de fatos | 252 (222) |
| `tests/unit/derivatives/ticket/test_session.py` | F1 a F4 | — |
| `tests/unit/derivatives/ticket/test_engine.py` | F5 a F7 | — |
| `tests/unit/derivatives/test_ticket_replay_script.py` | F8 a F11 | — |
| `docs/specs/derivatives/fase3/DL3-PR07A6.md` | cópia deste cartão | — |

**Não muda:** `sequencing.py`, `state.py`, `receipt.py`, `models.py`, `digest.py`, os demais
módulos da boleta, os roteiros e fitas oficiais, `current_state.md`, arquivos protegidos.
Linhas novas com até 100 colunas.

**Nenhum teste existente muda de resultado.** As quatro âncoras, os recibos e os resumos
das sessões oficiais não mudam, e a saída delas não ganha arquivo.

## 2. Regra

### 2.1 Sessão (`ReplaySession`)

**`external(account, symbol, fact, kind, quantity, now) -> None`**

Conferências, todas antes de qualquer efeito; recusa é `SessionRefusal`:

| Conferência | Mensagem |
|---|---|
| `symbol` e `fact` no alfabeto dos identificadores | a do motor, repassada |
| `account` é texto não vazio | «conta inválida» |
| `kind` é `exercise` ou `compliance` | «tipo de fato desconhecido» |
| `quantity` é inteiro (não booleano) diferente de zero | «quantidade do fato inválida» |
| `now` é instante com fuso | «instante sem fuso» |
| mesmo `fact` com conta, série, tipo ou quantidade diferentes | «fato repetido com conteúdo diferente» |

O mesmo `fact` com o mesmo conteúdo, de novo: não faz nada. O instante não entra na
comparação.

Efeitos, nesta ordem:

1. grava no registro da sessão um evento `external` com `account`, `fact`, `kind`, `symbol`
   e `quantity`;
2. congela a série na conta, no livro;
3. chama `on_external(fact, now)` em **toda** boleta aberta naquela conta, na ordem de
   abertura.

`quantity` é a variação do saldo da série, com sinal. Vendida de 10 exercida em 4: `+4`.

**`facts`** — propriedade com o registro encadeado dos fatos da sessão. É um `Receipt`, o
mesmo tipo do recibo da boleta: mesma cadeia, mesma verificação.

**`FACT_KINDS = ("exercise", "compliance")`** — os dois tipos que a DP-13 nomeia.

**Resumo.** Quando houver fato, `summary()` ganha
`"fatos_externos": {"eventos": <quantos>, "hash": <hash do último>}`. Sem fato, a chave não
existe.

### 2.2 Motor

- **Projetado.** `gross()` passa a tratar a boleta avisada como trata a parada: projetado =
  executado + saldo das ordens vivas. Vale desde o aviso, inclusive no `gross` gravado em
  cada relato da venue depois dele.
- **Identificador.** `_check_id_component` passa a ser pública, `check_id_component`, com
  docstring. A sessão a usa. Comportamento igual.

### 2.3 Roteiro e saída (`scripts/derivatives_ticket_replay.py`)

Passo novo, sem `ticket`:

```json
{"after_seq": 4, "at": "2026-11-23T14:00:07Z", "do": "external", "account": "sim",
 "symbol": "B", "fact": "f1", "kind": "exercise", "quantity": 4}
```

- Na leitura do roteiro: a conta tem de estar nas fotos e a série tem de estar na foto
  daquela conta. Senão, «conta ou série ausente na foto».
- Na execução: o passo passa pela conferência de sequência e de instante dos demais e chama
  `session.external`. `SessionRefusal` interrompe o replay, como na abertura recusada.
- Na saída: `fatos_externos.jsonl`, no formato de linha dos recibos, **só quando houver
  fato**. O resumo recebe a chave da sessão.

## 3. Cenários

Fita `calmo`. Foto das contas `sim` e `outra`: a do roteiro `calmo`, com A em `+10` e B em
`-10`. Boleta: a do roteiro `calmo` (compra 10 A a 1,00; vende 10 B a 1,50; bruto assinado
25,00). Instantes em 23/11/2026, 14:00:SS UTC.

### 3.1 Sessão (`test_session.py`)

**F1 — o fato chega a todas as boletas da conta, e só a elas.**

| Passo | Esperado |
|---|---|
| até o evento 2; T1 e T2 em `sim`, T3 em `outra`, abertas e confirmadas em :02 | `T1:A:1`, `T2:A:1` e `T3:A:1` vivas |
| até o evento 4; `external("sim", "B", "f1", "exercise", 4)` em :07 | recibos de T1 e T2 com um `external` cada, `{"ticket": …, "fact": "f1", "series": ["B"]}`; T3 sem |
| registro da sessão | um evento `external`, instante :07, conteúdo `{"account": "sim", "fact": "f1", "kind": "exercise", "symbol": "B", "quantity": 4}`; cadeia verificável |
| fim da fita | T1 e T2 `STOPPED`, só com a ordem de A; T3 `COMPLETED`, com A e B |
| brutos no resumo | T1 e T2: assinado `25.00`, executado `10.00`, projetado `10.00`; T3: `25.00` nos três |
| resumo | `fatos_externos` = `{"eventos": 1, "hash": <o do evento>}`; `contas_bloqueadas` vazia |

**F2 — boleta aberta depois do fato.** Até o evento 2;
`external("sim", "B", "f1", "compliance", -2)` em :02. T1 em `sim`: abre, e a confirmação é
recusada com «série com fato externo; foto nova necessária»; fica `DRAFT`, sem `external`
no recibo. T2 em `outra`: confirma e fica `WORKING`. O resumo tem `fatos_externos`.

**F3 — repetição.** As três boletas do F1. `f1` em :03 e o mesmo `f1` em :04 → um evento
na sessão, um `external` em T1. O mesmo `f1` mudando, um de cada vez, a quantidade (5), a
série (A), a conta (`outra`) ou o tipo (`compliance`) → «fato repetido com conteúdo
diferente»; a sessão segue com um evento e T3 sem `external`. Depois `f2` em A de `sim`,
`exercise`, −1 → dois eventos na sessão; T1 segue com um `external` só. Resumo:
`{"eventos": 2, "hash": <o do segundo>}`; cadeia verificável.

**F4 — fato inválido não deixa efeito.** Até o evento 2. Um por vez, com a mensagem da
tabela do §2.1: série `B:1`; fato `f 1`; conta vazia; conta `None`; tipo `assignment`;
quantidade `0`, `True` e `1.0`. Em seguida, instante sem fuso → «instante sem fuso». Depois
de cada recusa: registro vazio, resumo sem a chave, T1 em `sim` confirma e fica `WORKING`
(nada congelou), e `f1` válido ainda é aceito e chega a T1.

### 3.2 Motor (`test_engine.py`)

Referência dos testes do motor: T1 compra 10 A a 1,00 e vende 10 B a 1,50, foto zerada.

**F5 — o projetado cai no aviso.** T1 confirmada: projetado `25`. Fato em B em t=3 →
`WORKING`, brutos (assinado, executado, projetado) = `25`, `0`, `10`. t=4: A com venda a
1,00, tamanho 6 → A parcial; brutos `25`, `6.00`, `10.00`; o `gross` gravado nesse relato é
`{"signed": "25.00", "executed": "6.00", "projected": "10.00"}`.

**F6 — a venda viva continua no projetado.** T1 confirmada; t=3: A com venda a 1,00,
tamanho 6 (sai `T1:B:1` de 6). Fato em B em t=4 → brutos `25`, `6.00`, `19.00`: 6 executados,
4 de A vivos, 6 de B vivos a 1,50.

**F7 — boleta parada não ganha registro.** T1 compra 10 A, vende 6 B, cancela o resto e
para. Fato em A, `on_external("f1")` em t=6 → `STOPPED` e recibo idêntico ao de antes.
**Já passa no `main`**; fecha a lacuna da revisão do DL3-PR07A5.

### 3.3 Roteiro (`test_ticket_replay_script.py`)

**F8 — saída com fato.** Roteiro, com as duas fotos:

| Passo | Sequência e instante |
|---|---|
| abre T1 em `sim` e T3 em `outra`; confirma as duas | depois do 2, :02 |
| `external`: `sim`, B, `f1`, `exercise`, 4 | depois do 4, :07 |
| abre T4 em `sim`; confirma T4 | depois do 4, :08 |

Esperado: código 0. Arquivos: `fatos_externos.jsonl`, `recibo_T1.jsonl`, `recibo_T3.jsonl`,
`recibo_T4.jsonl`, `resumo.json`. O arquivo de fatos tem uma linha: `seq` 1, `kind`
`external`, `ts` `2026-11-23T14:00:07+00:00`, conteúdo do F1. Resumo: `fatos_externos` com
1 evento e o hash da linha; T1 `STOPPED`, T3 `COMPLETED`, T4 `DRAFT`; `recusas` =
`[{"passo": 7, "acao": "confirm", "boleta": "T4", "erro": "SequenceRefusal"}]`; brutos de
T1 `25.00`, `10.00`, `10.00`.

**F9 — passo inválido não publica nada.** Roteiro com T1 aberta e confirmada e o passo do
F8 alterado, um por vez: conta `ausente`; série `Z`; série `B:1`; tipo `assignment`;
quantidade `0`, `"4"`, `1.5` e `true`; fato `f 1`; campo `ticket` a mais. Esperado: código
2 e nenhum diretório de saída. **Já passa no `main`**, porque o passo ainda não existe.

**F10 — repetição no roteiro.** O passo do F8 seguido do mesmo com quantidade 5 → código 2,
nada publicado. O passo do F8 duas vezes, idêntico → código 0 e uma linha no arquivo.

**F11 — sessão oficial sem fato.** O `calmo` oficial → arquivos `recibo_T1.jsonl` e
`resumo.json`, só; o resumo não tem `fatos_externos`. **Já passa no `main`.**

## 4. Evidência do planejador

- **Fatos de hoje.** Conferidos no `main` `d8ba166`, inclusive o projetado de 25,00 depois
  de cancelamento humano.
- **Protótipo descartável:** `session.py` com 168 linhas (49 a mais), `engine.py` com 506
  (1 a mais), o script com 247 (25 a mais). `mypy --strict` limpo em `backend/` e no script;
  `pyright` limpo no pacote da boleta.
- **Portão completo no protótipo** (sem `tests/integration`): 11.529 aprovados, 16 pulados,
  a mesma contagem do `main`. Nenhum teste existente mudou; as âncoras passam.
- **Cenários:** F1 a F11 passam no protótipo. No `main`, F1 a F6, F8 e F10 falham; F7, F9
  e F11 já passam.
- **Mutantes:** 27 defeitos plantados, um por vez, todos detectados (§5).
- **Mutante descartado por ser equivalente:** avisar também as boletas de outras contas. O
  motor só grava se o livro disser que a série do plano está congelada na conta dele.

## 5. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, quem derrubou no
protótipo.

**Sessão**

1. Só a primeira boleta da conta é avisada (F1).
2. Nenhuma boleta é avisada (F1, F3, F4).
3. A série não é congelada no livro (F1, F2, F3, F4, F8).
4. A série é congelada em todas as contas abertas (F1, F8).
5. O fato não entra no registro da sessão (F1, F2, F3, F8, F10).
6. Repetição idêntica é registrada de novo (F3, F10).
7. Repetição com conteúdo diferente é aceita em silêncio (F3, F10).
8. A comparação da repetição ignora a quantidade (F3, F10).
9. A comparação da repetição ignora a conta (F3).
10. O tipo de fato não é conferido (F4).
11. Quantidade zero é aceita (F4, F9).
12. Quantidade booleana ou fracionária é aceita (F4).
13. Instante sem fuso é aceito (F4).
14. A série não é conferida (F4).
15. O identificador do fato não é conferido (F4).
16. Conta vazia é aceita (F4).
17. A série é congelada antes das conferências (F4).
18. O resumo sempre traz a chave dos fatos (F4, F11).
19. O resumo traz o hash do primeiro fato (F3).

**Motor**

20. O projetado não cai com o aviso (F5, F6).
21. Boleta parada ganha registro (F7).

**Roteiro**

22. O arquivo de fatos é sempre publicado (F11).
23. O arquivo de fatos nunca é publicado (F8, F10).
24. O roteiro não confere conta e série na foto (F9).
25. O roteiro só confere a conta (F9).
26. O passo de fato não chama a sessão (F8, F9, F10).
27. O fato vai para a conta errada (F8).

## 6. Critérios de parada

Pare e relate se:

- algum esperado do §3 não reproduzir;
- qualquer teste existente mudar de resultado;
- alguma âncora, recibo, resumo ou lista de arquivos de sessão oficial mudar;
- for preciso mudar arquivo de produção fora do §1, ou algum teto estourar;
- for preciso alterar saldo, capacidade ou foto pela quantidade do fato;
- F7, F9 ou F11 falharem no `main` (seria defeito já integrado).

## 7. Entrega

1. Commit vermelho com os testes; depois o verde. F7, F9 e F11 nascem verdes: declare isso.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
   `tests/integration` só no contêiner isolado, nunca no Mac com banco vivo.
3. Descrição do PR: cabeça, contagens, linhas dos três arquivos, os 27 mutantes, as âncoras,
   os recibos, os resumos e a lista de arquivos das sessões oficiais comparados byte a
   byte, desvios.
4. Copie este cartão para o caminho do §1. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda os cenários do
seu protótipo contra os módulos entregues.

## 8. Depois deste cartão

Com este cartão a DP-13 fica entregue no simulador, menos a conferência da foto nova, que
depende de histórico persistente. Em seguida, a fila do `current_state.md`:

- cota por dependência no livro;
- desmontagem e zeragem de borboleta;
- apresentação: montagem parcial com executado por perna, e o projetado depois de
  cancelamento humano;
- repetir, completar e ajustar estruturas.

## Revisão adversarial (Claude) — GO na primeira rodada, cabeça `7588cf1`

Pela regra de processo de Francisco, o revisor **não executou a suíte, a tipagem nem os
mutantes** desta cabeça. Leu o diff, conferiu as evidências pelo SHA-256 e rodou os cenários
do seu protótipo, escrito antes do cartão, mais cinco sondas próprias.

| Verificação | Resultado | Quem |
|---|---|---|
| Suíte sem integração, Linux x86_64 e macOS | 11.567 aprovados, 16 pulados, 261 subtestes nos dois | implementador; logs conferidos |
| mypy estrito e Pyright, nos dois sistemas | 0 erros | implementador; logs conferidos |
| Commits vermelhos antes dos verdes | F1 a F6, F8 e F10 falham na base; F7, F9 e F11 já passavam, como o cartão previa | implementador; logs conferidos |
| Testes focais antigos | 585 com resultado idêntico por nome; 38 novos aprovados | implementador; log conferido |
| 27 mutantes do §5 e 4 adicionais, nos dois sistemas | todos detectados | implementador; logs conferidos |
| Integração | só no contêiner Linux isolado: 31 aprovados, 206 pulados | implementador; evidência conferida |
| Manifesto de 144 evidências (`b3d04866…c288`) e hashes dos dois relatórios | conferem | revisor (23 arquivos) e Francisco (todos, no Mac) |
| `DIFF.patch` das evidências aplicado sobre a base | mesma árvore da cabeça | revisor |
| Diff | sete arquivos; `session.py` 174 (teto 174), `engine.py` 506 (teto 508), script 244 (teto 252) | revisor |
| Âncoras, recibos, resumos e lista de arquivos das sessões oficiais | iguais entre base e cabeça | implementador; log conferido |
| Cópia do cartão | igual à publicada, salvo a quebra de linha final | revisor |
| 27 casos do protótipo do planejador (F1 a F11) contra os módulos entregues | todos aprovados | revisor |
| 5 sondas do revisor (abaixo) | todas aprovadas | revisor |

Diferenças em relação ao protótipo do planejador, todas aceitas:

1. `facts` devolve uma **cópia** do registro, não o objeto interno.
2. O instante é normalizado para `datetime` nativo, preservando o fuso; instante que não
   cabe em UTC vira recusa da sessão, sem efeito.
3. O tipo do fato é conferido só na sessão; o roteiro o aceita como texto e a sessão recusa.

Sondas do revisor na cabeça:

1. Escrever na cópia de `facts` não muda o registro nem o resumo.
2. Subclasse de `datetime` com fuso: gravada como instante nativo, e a boleta é avisada.
3. Roteiro `rapido` oficial com um fato em B enquanto a ordem da T1 está incerta: a T1
   grava o fato, concilia, não envia mais nada e para; a T2 é recusada na confirmação.
4. Passo de fato com instante depois do próximo evento: recusado, nada publicado.
5. Roteiro só com o fato, sem boleta: publica o resumo e o arquivo de fatos.

Defeito do cartão do planejador, achado pela skill numa cabeça intermediária e corrigido
pelo implementador antes desta: o §2.1 mandava expor o registro de fatos como o próprio
`Receipt`, que tem `append` público. Quem consultasse podia acrescentar um fato sem congelar
a série. O protótipo do planejador tinha o mesmo defeito e os 27 mutantes não o cobriam.

Observação não bloqueante, anterior a este PR: `ReplaySession.receipt(ticket)` ainda devolve
o recibo interno da boleta, com a mesma exposição. Fica registrada no estado atual.

Limite desta revisão: sem mutantes próprios do revisor nesta cabeça.

Relatórios da skill lidos depois de formado o parecer, com SHA-256 conferidos
(`cb0e0361…8356` e `01c63a0f…7a4d`): sem bloqueante; nenhuma simplificação qualificada.

