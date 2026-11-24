# DL3-PR07D1 — Supercartão: andamento por perna, rótulo da parada e projetado após cancelamento

**Data:** 24/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `1554243` (DL3-PR07B3 integrado)
**PR novo**, em rascunho
**Decisões que este cartão implementa:**

- Francisco, 23/11/2026 (registrada em `DECISOES_POS_PR07A3C_2026-11-23.md`): a boleta
  parada com execução deve aparecer como **«Parada · montagem parcial»**, com as
  quantidades executadas por perna.
- Francisco, sobre os três brutos (22/11/2026): «o que autorizei, o que aconteceu e o que
  ainda pode acontecer».
- Francisco, 24/11/2026: fechar a Fase 3 estendida com os assuntos já abertos.

## 0. Escopo

**O que acontece hoje.** Fatos conferidos no `main`:

- O resumo da sessão mostra ordens e brutos, mas não diz quanto de cada perna foi executado
  nem a que preço. Para saber, é preciso somar o recibo à mão.
- Boleta parada no meio aparece só como «Parada», igual à que parou sem executar nada.
- Depois de um cancelamento humano, a boleta não envia mais nada, mas segue em execução
  enquanto houver ordem viva e mostra como projetado o plano inteiro. Na sessão oficial
  `leilao`, o recibo grava projetado 25,00 quando só 14,50 ainda podiam acontecer.

**O que este cartão entrega.**

1. **Andamento por perna**, no motor e no resumo: assinado, executado, saldo vivo e preço
   médio executado, na ordem assinada das pernas.
2. **Rótulo da parada.** Parada com alguma execução vira «Parada · montagem parcial» ou
   «Parada · desmontagem parcial». Os demais rótulos não mudam.
3. **Projetado após cancelamento humano**: executado mais o saldo das ordens vivas, como já
   é depois do aviso de fato externo.

**O que este cartão não faz.**

- Não versiona o formato do recibo nem fixa o esquema JSON de saída. Segue pendente, para
  antes do primeiro consumidor externo.
- Não muda o recibo em formato: nenhum campo novo. Só o **valor** do projetado gravado
  depois de um cancelamento.
- Não muda livro, plano, sequência de envio, prévia nem resumo criptográfico.
- Não cria tela. O rótulo e as pernas saem no resumo e no log do script.

Nenhuma dependência nova.

## 1. Referência externa

O desenho segue a convenção do protocolo FIX para o estado de uma ordem. Não há código nem
dependência de terceiros; é só a regra de contagem.

| Conceito FIX | Aqui | Regra adotada |
|---|---|---|
| `OrderQty` (38) | `assinado` | quantidade assinada da perna |
| `CumQty` (14) | `executado` | soma das execuções da perna nesta boleta |
| `LeavesQty` (151) | `vivo` | saldo ainda aberto à execução; **zero em ordem morta** |
| `AvgPx` (6) | `preco_medio` | média ponderada pelo volume; ausente sem execução |
| `OrdStatus` 6, cancelamento pendente | ordem com cancelamento solicitado | segue viva e conta no `vivo` até a confirmação |

- Regra geral `OrderQty = CumQty + LeavesQty`, com a exceção de ordem cancelada, expirada
  ou rejeitada, em que `LeavesQty` pode ser zero: dicionário FIX 4.3, relatório de execução
  (<https://www.onixs.biz/fix-dictionary/4.3/msgtype_8_8.html>).
- Ordem parcialmente executada e depois cancelada mantém `CumQty` e zera `LeavesQty`: fórum
  da FIX Trading Community
  (<https://forum.fixtrading.org/t/cancelled-report-with-cumqty-set/2123>).
- Em estratégia de várias pernas, a execução é relatada por perna
  (`MultiLegReportingType` 442 = 2): FIXimate
  (<https://fiximate.fixtrading.org/legacy/en/FIX.4.4/tag442.html>).

**Não verificado pelo planejador:** as páginas `fixtrading.org/guidelines/post-trade/` e
`optionseducation.org`, indicadas por Francisco. A leitura direta não foi autorizada nesta
sessão. O cartão não depende delas. As diretrizes de pós-negociação tratam de alocação e
confirmação, que não existem no simulador.

## 2. Arquivos e tetos

| Arquivo | O que muda | Teto (hoje) |
|---|---|---|
| `backend/derivatives/ticket/engine.py` | `LegProgress`, `legs()`, `label`, projetado após cancelamento | 550 (506) |
| `backend/derivatives/ticket/session.py` | `rotulo` e `pernas` no resumo | 184 (174) |
| `scripts/derivatives_ticket_replay.py` | log com o rótulo do motor | 248 (244) |
| `tests/unit/derivatives/ticket/test_engine.py` | S1 a S6 | — |
| `tests/unit/derivatives/test_ticket_replay_script.py` | S7; oito esperados atualizados | — |
| `docs/specs/derivatives/fase3/DL3-PR07D1.md` | cópia deste cartão | — |

**Não muda:** `sequencing.py`, `state.py`, `receipt.py`, os demais módulos da boleta,
roteiros e fitas, `current_state.md`, arquivos protegidos. Linhas novas com até 100 colunas.

**Testes existentes que mudam: oito, todos em `test_ticket_replay_script.py`, e só eles.**

| Teste | Por quê |
|---|---|
| `test_complete_replay[calmo]`, `[leilao]`, `[rapido]` | o resumo ganha `rotulo` e `pernas`; em `leilao`, além disso, o projetado do recibo e a âncora |
| `test_session_cut_at_hand_verified_step[V3]`, `[V4]`, `[V5]` | o resumo ganha as duas chaves |
| `test_l4_summary_log_names_ticket_state[leilao…]`, `[rapido…]` | o log passa a trazer o rótulo completo |

**Âncoras.** Três não mudam: `calmo` T1 `1d50bba6…`, `rapido` T1 `9ebc9cd5…`, `rapido` T2
`fbcaafa8…`. **Uma muda**, por causa do item 3 do §0:

- `leilao` T1: de `0e95249a66c1eb658d8e34f58ab77e81381cc7d745b6a57de6641def3c488cda`
  para `8592cd742d265332eddf75ea0f0cb9166e53f4db47dbfdd29901e166a43e7bbe`.
- A única diferença no recibo é o registro 9: projetado de `25.00` para `14.50`.

Não existe recibo real gravado; a mudança atinge só material sintético.

## 3. Regra

### 3.1 Motor

**`LegProgress`** — tupla nomeada pública: `symbol`, `side`, `signed`, `executed`, `live`,
`average`.

**`legs() -> tuple[LegProgress, ...]`** — uma linha por perna, **na ordem assinada** da
boleta (a do `draft`, não a do plano).

- `signed`: quantidade da perna.
- `executed`: soma das execuções desta boleta naquela série.
- `live`: soma, nas ordens da perna em estado vivo, de pedido menos executado. Ordem
  cancelada, expirada, rejeitada ou executada conta zero. Ordem com cancelamento solicitado
  ou incerta conta.
- `average`: valor executado dividido pela quantidade executada, com quatro casas; `None`
  sem execução.
- Sem proposta: `EngineRefusal` «boleta sem proposta», como em `gross()`.

**`label`** — propriedade com o rótulo em português.

- O de `TICKET_LABELS_PT` para o estado, sempre.
- Se o estado é `STOPPED` **e** a boleta tem execução: acrescenta « · desmontagem parcial»
  quando alguma dependência do plano é de desmontagem ou zeragem; senão « · montagem
  parcial».

**Projetado.** `gross()` passa a tratar a boleta com cancelamento humano solicitado como já
trata a avisada de fato externo e a encerrada: projetado = executado + saldo das ordens
vivas ao preço-limite. Vale desde o pedido de cancelamento, inclusive no `gross` gravado
nos relatos seguintes.

### 3.2 Resumo e log

Cada boleta do resumo ganha:

- `"rotulo"`: o `label` do motor;
- `"pernas"`: lista na ordem de `legs()`, com `serie`, `lado` (`BUY` ou `SELL`),
  `assinado`, `executado`, `vivo` e `preco_medio` (texto com quatro casas, ou `null`).

O log final do script usa o `label` do motor no lugar do rótulo simples.

## 4. Cenários

Referência dos testes do motor: T1 compra 10 A a 1,00 e vende 10 B a 1,50, foto zerada.
Linhas de `legs()` na forma (série, lado, assinado, executado, vivo, médio). Brutos na
forma (assinado, executado, projetado).

### 4.1 Motor (`test_engine.py`)

**S1 — o andamento acompanha as ordens.**

| t | Passo | A | B | Brutos | Rótulo |
|---|---|---|---|---|---|
| — | proposta | 10, 0, 0, — | 10, 0, 0, — | — | Proposta |
| 2 | confirmação | 10, 0, 10, — | 10, 0, 0, — | — | Em execução |
| 3 | A com venda a 1,00, tamanho 6 | 10, 6, 4, 1.0000 | 10, 0, 6, — | 25; 6,00; 25,00 | |
| 3 | cancelamento humano de `T1:B:1` | | 10, 0, 6, — | 25; 6,00; **19,00** | Em execução |
| 4 | B com compra a 1,50, tamanho 2 | 10, 6, 4, 1.0000 | 10, 2, 0, 1.5000 | 25; 9,00; 13,00 | Em execução |
| 6 | A com venda a 1,00, tamanho 4 | 10, 10, 0, 1.0000 | | 25; 13,00; 13,00 | Parada · montagem parcial |

No t=3, depois do pedido de cancelamento, a boleta segue `WORKING` e `T1:B:1` fica com
cancelamento solicitado: ainda conta 6 no vivo. No t=4 a ordem executa 2 e o cancelamento é
confirmado.

**S2 — o recibo grava o projetado certo depois do cancelamento.** Mesmos passos até t=4. O
`gross` do último relato de `T1:B:1` é
`{"signed": "25.00", "executed": "9.00", "projected": "19.00"}`.

**S3 — preço médio ponderado.** T1 confirmada; A com venda a 0,98, tamanho 3; depois A com
venda a 1,00, tamanho 7. Linha de A: executado 10, vivo 0, médio `0.9940`.

**S4 — parada sem execução não ganha sufixo.** T1 confirmada; cancelamento humano de
`T1:A:1` em t=3; nova cotação de A. `STOPPED`, rótulo «Parada», linha de A 10, 0, 0, —.

**S5 — concluída.** T1 confirmada; A a 1,00; B a 1,50. Rótulo «Concluída».

**S6 — desmontagem parada no meio, na ordem assinada.** Foto e cotações do D8 do
DL3-PR07B3, com a boleta assinada na ordem **vende 10 A, compra 20 B, vende 10 C**. Mesmos
passos do D8. Rótulo «Parada · desmontagem parcial». Linhas, nesta ordem: A venda 10, 10,
0, 2.0000; B compra 20, 10, 0, 1.2000; C venda 10, 0, 0, —.

### 4.2 Sessões oficiais (`test_ticket_replay_script.py`)

**S7 — o resumo das três sessões.**

| Sessão | Boleta | `rotulo` | `pernas` (executado, vivo, médio) | Bruto | Âncora |
|---|---|---|---|---|---|
| `calmo` | T1 | Concluída | A 10, 0, 1.0000; B 10, 0, 1.5000 | — | igual |
| `leilao` | T1 | Parada · montagem parcial | A 4, 0, 1.0000; B 3, 0, 1.5000 | 25,00; 8,50; 8,50 | a nova do §2 |
| `rapido` | T1 | Parada · desmontagem parcial | — | — | igual |
| `rapido` | T2 | Proposta | A 0, 0, `null`; B 0, 0, `null` | — | igual |

Em `calmo`, a lista completa é
`{"serie": "A", "lado": "BUY", "assinado": 10, "executado": 10, "vivo": 0, "preco_medio": "1.0000"}`
e a linha correspondente de B, com `SELL` e `1.5000`.

## 5. Evidência do planejador

- **Fatos de hoje.** Conferidos no `main` `1554243`, inclusive o projetado de 25,00 no
  registro 9 do recibo de `leilao`.
- **Protótipo descartável:** `engine.py` com 544 linhas (38 a mais), `session.py` com 179
  (5 a mais), o script com 243 (1 a menos). `mypy --strict` limpo em `backend/` e no script;
  `pyright` limpo no pacote da boleta.
- **Portão completo no protótipo** (sem `tests/integration`): 11.580 aprovados e 8
  reprovados, que são exatamente os oito testes do §2, antes de atualizados. Nenhum outro
  mudou.
- **Cenários:** S1 a S7 passam no protótipo. No `main` todos falham.
- **Mutantes:** 15 defeitos plantados, um por vez, todos detectados (§6). Um sobreviveu na
  primeira rodada (o 8); por causa dele o S6 usa ordem assinada diferente da do plano.

## 6. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, quem derrubou no
protótipo.

1. O projetado não cai com o cancelamento (S1, S2, S7).
2. O saldo vivo conta ordem morta (S1, S4, S6, S7).
3. O saldo vivo ignora ordem com cancelamento solicitado (S1).
4. O saldo vivo é o pedido inteiro, sem descontar o executado (S1).
5. O executado soma todas as pernas (S1, S6, S7).
6. O preço médio é média simples dos preços (S3).
7. O preço médio é zero em vez de ausente (S1, S4, S6, S7).
8. As pernas saem na ordem do plano, não na assinada (S6).
9. Parada sem execução ganha o sufixo (S4).
10. Qualquer estado com execução ganha o sufixo (S1, S5, S7).
11. Desmontagem rotulada como montagem (S6, S7).
12. Montagem rotulada como desmontagem (S1, S7).
13. O resumo sai sem as pernas (S7).
14. O resumo sai com o rótulo simples (S7).
15. O resumo troca executado e vivo (S7).

## 7. Critérios de parada

Pare e relate se:

- algum esperado do §4 não reproduzir;
- qualquer teste existente mudar de resultado, fora os oito do §2;
- a âncora nova de `leilao` não for a do §2, ou alguma das outras três mudar;
- o recibo de `leilao` diferir do da base em algo além do projetado do registro 9;
- for preciso mudar arquivo de produção fora do §2, ou algum teto estourar;
- for preciso acrescentar campo ao recibo.

## 8. Entrega

1. Commit vermelho com os testes; depois o verde. Envie o vermelho ao GitHub antes do
   verde.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
   `tests/integration` só no contêiner isolado, nunca no Mac com banco vivo.
3. Descrição do PR: cabeça, contagens, linhas dos três arquivos, os 15 mutantes, os oito
   testes atualizados, a comparação dos recibos oficiais com a base (três iguais byte a
   byte; `leilao` com a única diferença declarada), desvios.
4. Copie este cartão para o caminho do §2. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda os cenários do
seu protótipo contra os módulos entregues.

## 9. Depois deste cartão

Com este cartão ficam entregues os assuntos abertos pela DP-03 e pela DP-13 no simulador.
O que resta na fila do `current_state.md` são frentes novas, cada uma com decisão própria
de Francisco: repetir, completar e ajustar estruturas; limite de escala; modalidade B de
garantia; esquema JSON de saída e versão de formato do recibo, antes do primeiro consumidor
externo.
