# DL3-PR07A2 — Supercartão: os três brutos e a série de proteção

**Data:** 22/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `ba939a1` (DL3-PR07A1 integrado) · **PR novo**, em rascunho
**Decisões que este cartão implementa:** visibilidade do PR07A (registro de decisões, Revisão
2, Parte C) e duas decisões de Francisco de 22/11/2026, no §0.

## 0. Escopo e decisões

Este cartão é **só visibilidade**. Nenhum estado, nenhuma ordem, nenhuma quantidade e nenhuma
recusa muda. Só entram números novos no recibo, no resumo e numa consulta do motor.

Decisões de Francisco para este cartão:

1. **Bruto projetado mostra só o que ainda pode executar.** Enquanto a boleta ainda pode
   enviar, conta tudo que falta ao preço assinado. Depois que ela para, conta só o saldo das
   ordens que continuam abertas.
2. **Da origem da cobertura, entra só a série de proteção.** Separar compra própria de
   compra de outra boleta, e a autorização disso na prévia, ficam no cartão seguinte, porque
   mudam quem pode vender e o conteúdo assinado.

Sequência atualizada: **PR07A2 (este)**; PR07A3, cobertura própria ou de outra boleta e
autorização na prévia; PR07A4, DP-13; depois PR07B.

Decisão do planejador, que Francisco pode vetar: **a prévia assinada não muda de formato.**
O bruto assinado já está nela (`gross_cap`). O projetado da prévia sai das pernas assinadas e
é lido pela consulta do motor e pelo `resumo.json`. Assim nenhum evento `preview` e nenhum
resumo criptográfico muda.

Todos os esperados foram conferidos: os de "hoje" no `main` `ba939a1`; os novos num
protótipo descartável do planejador, que não será entregue, e por conta à mão. Exceção: B7
e B8 saem direto da definição do §2 e não foram rodados no protótipo.

## 1. Arquivos e tetos

| Arquivo | O que muda | Linhas hoje → teto |
|---|---|---|
| `backend/derivatives/ticket/sequencing.py` | cálculo puro dos três brutos | 337 → 370 |
| `backend/derivatives/ticket/engine.py` | consulta `gross()`, registros no recibo (§3, §4) | 410 → 445 |
| `backend/derivatives/ticket/session.py` | `bruto` no resumo de cada boleta | 116 → 122 |
| `tests/unit/derivatives/ticket/test_engine.py` | B0–B3, B6–B8 | — |
| `tests/unit/derivatives/test_ticket_replay_script.py` | B4, B5 e as âncoras novas | — |
| `docs/specs/derivatives/fase3/DL3-PR07A2.md` | cópia deste cartão | — |

**Não mudam:** `models.py`, `digest.py`, `receipt.py`, `gate.py`, `guards.py`, `state.py`,
`paper_venue.py`, `replay.py`, `venue.py`, `trigger.py`, o script de replay, fixtures,
`current_state.md`, arquivos protegidos. Produção do PR: no máximo **70 linhas** (o protótipo
do planejador usou 57).

## 2. Definições

Tudo em `Decimal` exato. Os valores são da **boleta**, não da conta.

- **Bruto assinado** (`signed`): o `gross_cap` da versão vigente. É o que foi autorizado.
- **Bruto executado** (`executed`): soma de preço real × quantidade das execuções que o
  motor já aplicou nesta boleta. Relatório pendente de ordem incerta só entra depois da
  conciliação.
- **Bruto projetado** (`projected`): executado + soma, por perna, de **quantidade que ainda
  pode executar × preço assinado da perna**. A quantidade que ainda pode executar depende do
  estado da boleta:
  - boleta em `DRAFT`, `ARMED`, `TRIGGERED`, `CONFIRMED`, `WORKING` ou `UNCERTAIN`: a
    quantidade da perna menos o que já executou nela;
  - boleta em `COMPLETED`, `STOPPED`, `DENIED` ou `EXPIRED`: só o saldo (pedido menos
    executado) das ordens da perna ainda abertas. Aberta é a ordem em `PENDING_SEND`,
    `LIVE`, `PARTIAL`, `CANCEL_REQUESTED` ou `UNCERTAIN`.

No primeiro regime o projetado é o número que o motor já compara com o `gross_cap`. Ele pode
passar do assinado quando uma venda executa a preço melhor; é isso que faz o motor parar.

## 3. Onde os três aparecem

**Consulta.** `TicketEngine.gross()` devolve um objeto com os atributos `signed`, `executed`
e `projected`, pelo estado atual da boleta. Antes da primeira prévia, recusa com
`EngineRefusal`.

**Recibo.** Entra a chave `gross`, um objeto com exatamente as chaves `signed`, `executed` e
`projected`. Cada valor é **texto decimal com duas casas** (`"25.00"`, `"7.62"`). Ela entra:

- em todo registro `venue_partial` e `venue_fill`, com os valores **depois** daquela
  execução, pelo estado da boleta naquele momento;
- em todo registro que leva a boleta a `COMPLETED` ou `STOPPED`: `complete`, `stop` e o
  `reconcile` da boleta quando o destino é um desses dois. Nesses, o projetado já usa a
  regra do estado de destino.

Em nenhum outro registro.

**Resumo.** Em `resumo.json`, cada boleta ganha `"bruto"`, com as chaves `assinado`,
`executado` e `projetado`, texto decimal com duas casas, pela consulta no fim da sessão.

Lembrete de arquitetura: o motor não acessa atributo privado de outro objeto. `_asdict` de
uma tupla nomeada conta como privado e derruba o teste de arquitetura.

## 4. Série de proteção

No registro que traz `request` de uma ordem de **venda**, entra a chave `protection`, com o
símbolo da série cuja compra executada libera aquela venda (o que `protection_for` já
devolve). Ordem de compra não ganha a chave. Na montagem, é a série comprada. Na
desmontagem, é a série vendida que foi recomprada.

## 5. Cenários

`Session` e auxiliares do `test_engine`. Boleta de referência: compra A 10 a 1,00; vende B
10 a 1,50; bruto assinado 25. Em todos os registros abaixo `signed` é `25.00`.

**B0.** Boleta de referência só proposta: `gross()` = assinado 25, executado 0, projetado 25.

**B1 — venda a preço melhor e parada por limite** (é o cenário L1 que já existe). Confirma
às 14:00:02; cotação de A com ask 1,00 e tamanho 3 às 14:00:03; cotação de B com bid 1,54
às 14:00:04; cotação de A com ask 1,00 e tamanho 7 às 14:00:05.

| Seq | Registro | Ordem | `executed` | `projected` | Outro |
|---|---|---|---|---|---|
| 5 | `venue_partial` | `T1:A:1`, 3 a 1,00 | 3.00 | 25.00 | |
| 6 | `venue_live` | `T1:B:1` | — | — | `protection` = `A` |
| 7 | `venue_fill` | `T1:B:1`, 3 a 1,54 | 7.62 | **25.12** | |
| 8 | `venue_fill` | `T1:A:1`, 7 a 1,00 | 14.62 | 25.12 | |
| 9 | `stop` | | 14.62 | **14.62** | |

Depois, `gross()` = 25; 14,62; 14,62.

**B2 — parada por limite com recompra ainda aberta.** Posição A = +10, B = −10. `T1` é a
boleta de desmontagem do `Session` (vende A 10 a 1,00; compra B 10 a 1,50; bruto 25).
Confirma às 14:00:02; cotação de B com ask 1,50 e tamanho 3 às 14:00:03; cotação de A com
bid 1,04 e ask 1,10 às 14:00:04; cotação de B com ask 1,50 e tamanho 3 às 14:00:05.

| Seq | Registro | Ordem | `executed` | `projected` | Outro |
|---|---|---|---|---|---|
| 5 | `venue_partial` | `T1:B:1`, 3 a 1,50 | 4.50 | 25.00 | |
| 6 | `venue_live` | `T1:A:1` | — | — | `protection` = `B` |
| 7 | `venue_fill` | `T1:A:1`, 3 a 1,04 | 7.62 | 25.12 | |
| 8 | `venue_partial` | `T1:B:1`, 3 a 1,50 | 12.12 | 25.12 | |
| 9 | `stop` | | 12.12 | **18.12** | |

Aí `T1` está `STOPPED`, com `T1:B:1` `PARTIAL` (6 executadas, 4 abertas) e `T1:A:1`
`FILLED` (3). O projetado de 18,12 é 12,12 mais as 4 abertas a 1,50. Os envios da sessão
são `T1:B:1` com 10 e `T1:A:1` com 3. Tudo isso, menos a chave `gross`, já vale hoje.

**B2b — continuação de B2.** Cotação de B com ask 1,50 e tamanho 4 às 14:00:06: registro 10,
`venue_fill` de `T1:B:1`, com `executed` 18.12 e `projected` 18.12. `T1` segue `STOPPED`.

**B3 — outra continuação de B2 (teste que faltou no DL3-PR07A1).** No ponto de B2, cotação
de abertura de A às 14:00:05 e uma segunda boleta de desmontagem com quantidade 1 (líquido
0,50, bruto 2,50, prazo 15:00, validade `CLOSE`) confirma às 14:00:06: recebe
`SequenceRefusal` e a decisão não é gasta. **Já vale hoje.** O teste existe para matar o
mutante 17.

**B4 — sessões oficiais.** Mesmos eventos, estados e quantidades de hoje, mais:

| Sessão | Seq, registro e ordem | `executed` | `projected` | Outro |
|---|---|---|---|---|
| `calmo` | 8 `venue_fill` `T1:A:1` | 10.00 | 25.00 | |
| | 10 `venue_live` `T1:B:1` | — | — | `protection` = `A` |
| | 11 `venue_fill` `T1:B:1` | 25.00 | 25.00 | |
| | 12 `complete` | 25.00 | 25.00 | |
| `leilao` | 5 `venue_partial` `T1:A:1` | 3.00 | 25.00 | |
| | 6 `venue_live` `T1:B:1` | — | — | `protection` = `A` |
| | 7 `venue_fill` `T1:B:1` | 7.50 | 25.00 | |
| | 9 `venue_partial` `T1:A:1` | 8.50 | 25.00 | |
| | 12 `stop` | 8.50 | **8.50** | |
| `rapido`, `T1` | 7 `venue_partial` `T1:B:1` | 6.00 | 25.00 | |
| | 11 `venue_live` `T1:A:1` | — | — | `protection` = `B` |
| | 12 `venue_fill` `T1:A:1` | 10.00 | 25.00 | |
| | 15 `stop` | 10.00 | **10.00** | |

`bruto` no resumo (assinado, executado, projetado): `calmo` `T1` 25.00, 25.00, 25.00;
`leilao` `T1` 25.00, 8.50, 8.50; `rapido` `T1` 25.00, 10.00, 10.00; `rapido` `T2` (em
proposta) 25.00, 0.00, 25.00.

**B5 — cortes V3, V4 e V5 que já existem.** `bruto` esperado: V3, `T1` em `DRAFT`: 25.00,
0.00, 25.00. V4, `T1` em `UNCERTAIN`: 25.00, **0.00**, 25.00, mesmo com a venue mostrando 4
executadas na ordem incerta; `T2`: 25.00, 0.00, 25.00. V5, `T1` em `STOPPED`: 25.00, 10.00,
10.00.

**B6.** `gross()` num motor que ainda não recebeu proposta: `EngineRefusal`.

**B7.** Boleta de referência proposta e descartada (`DENIED`): `gross()` = 25; 0; 0.

**B8 — parada pela conciliação.** Montagem R1 do DL3-PR07A1 (`T1` com bruto assinado 50,
`timeout` não registrado, `reconcile` de `T1:C:1` às 14:00:03). O registro `reconcile` da
boleta, com estado `STOPPED`, traz `gross` com `signed` 50.00, `executed` 0.00 e `projected`
0.00. O `reconcile` da ordem não traz `gross`.

## 6. O que muda e o que não muda

**Não mudam:** a sequência de tipos de registro de cada recibo; estados, ordens,
quantidades, recusas e envios; todo evento `preview`, byte a byte; todo resumo
criptográfico de prévia; os testes existentes, fora os seis listados abaixo.

**Mudam por desenho:** os recibos que têm execução ou parada, e os três `resumo.json`.
Valores novos, calculados pelo protótipo do planejador com o formato do §3 e do §4:

| Âncora de recibo | Valor |
|---|---|
| `calmo` `T1` | `1d50bba66aa2db714bf7006da415c39f083bc9e4374ebdbc9b94305b3356236b` |
| `leilao` `T1` | `0e95249a66c1eb658d8e34f58ab77e81381cc7d745b6a57de6641def3c488cda` |
| `rapido` `T1` | `9ebc9cd5b584f12b7e67be1ba7ba9a7da94c7a42a531c0d0105409404ba60344` |
| `rapido` `T2` | **igual a hoje:** `fbcaafa8eb7934ed7fe77a9f497b676904c5cc1647d42e0b8f5a77da4df3e2b5` |
| corte V5, `T1` | `9cb640c966b1cb040a61ac0bdb8665fe890784a14773424bd01b8ce95af48f99` |
| cortes V3 e V4 | **iguais a hoje** (`474a8476…aabc`, `6bf3c975…9ead` e `fbcaafa8…e2b5`) |

| Arquivo | SHA-256 |
|---|---|
| `calmo/recibo_T1.jsonl` | `ebf3165782b866e70b4bd2dfbd98eb68df71eefb2858d9fc836d83728965bb2f` |
| `calmo/resumo.json` | `a88051d426b6cffbab28168684cb24e8d6822ce3d91aa553819b08d4e39acfcc` |
| `leilao/recibo_T1.jsonl` | `53ce4994119b39390e59ffdecd36d99bcf559f434cc5157bc9f0a8784ca67b40` |
| `leilao/resumo.json` | `21c78632e8831e52c837732a0ae6a5d40704b0a613bfc2e55edb0b890bbf90d8` |
| `rapido/recibo_T1.jsonl` | `5535e7df1d10bea0234d5d062fef8d0a165a19f43a4141cfb141c6865eae51cc` |
| `rapido/recibo_T2.jsonl` | **igual a hoje:** `d2a17c541e2820a978e91b18b4252272009cb2aa8a3dc984c3123fb7a6bf8328` |
| `rapido/resumo.json` | `3d894d5f3d4d71305f03778a6e74ae9ae91bd10e9e2d405c6ab8c19c35c7611d` |

Se a implementação seguir o §3 e o §4 à letra e algum valor não bater, **pare e relate**: o
erro pode ser do cartão.

Testes existentes que mudam por desenho, e só eles: `test_complete_replay` nas três sessões
e `test_session_cut_at_hand_verified_step` em V3, V4 e V5.

## 7. Testes e mutantes

Um teste por cenário B0 a B8, com o nome do cenário e os valores escritos à mão. Compare
`gross()` como `Decimal`; compare o recibo como texto de duas casas.

Mutantes obrigatórios, um por vez, cada um derrubando ao menos um teste:

1. Executado pelo preço assinado em vez do preço real (B1: 7,50 no lugar de 7,62).
2. Executado sem multiplicar pela quantidade.
3. Projetado sempre pelo saldo total, sem a regra do estado terminal (B1, `leilao`).
4. Regra do estado terminal ignorando ordem aberta (B2: 12,12 no lugar de 18,12).
5. Regra do estado terminal aplicada também a `WORKING` (B1, seq 7).
6. Saldo da ordem aberta sem descontar o executado (B2).
7. Registro `stop` calculado pelo estado anterior à parada (B1: 25,12 no lugar de 14,62).
8. Execução depois da parada calculada pela regra não terminal (B2b).
9. `gross` ausente em `complete` ou em `stop` (B4).
10. `gross` ausente no `reconcile` que para a boleta, ou presente no da ordem (B8).
11. `gross` presente em registro que não é execução nem parada (B4: as âncoras do §6).
12. Assinado trocado pelo projetado da prévia (B1: 25,12 e 25,00 têm de aparecer juntos).
13. Valor sem as duas casas (`"25"` no lugar de `"25.00"`).
14. Execução pendente de ordem incerta contada no executado (B5, V4).
15. `protection` em ordem de compra, ou ausente na de venda (B4).
16. `protection` com o símbolo da própria venda (B4: `B` no lugar de `A` em `calmo`).
17. Liberar a ocupação de toda compra ao parar, em vez de só a que nunca teve ordem (B3).
18. `DENIED` tratado pela regra não terminal (B7: 25 no lugar de 0).

## 8. Critérios de parada

Pare e relate se: algum "já vale hoje" não reproduzir no `main` `ba939a1`; algum valor do
§6 não bater; um evento `preview` ou um resumo criptográfico mudar; um teste existente fora
dos seis do §6 precisar mudar; um arquivo da lista "não mudam" precisar mudar; algum teto
do §1 estourar; os testes de arquitetura precisarem de exceção.

## 9. Entrega

1. Commit vermelho com os testes; depois o verde.
2. Portão completo em clone limpo no Mac, mais `mypy --strict` no script. Por orientação de
   Francisco, o Codex executa também o portão Linux via MCP/Docker na cabeça candidata e
   entrega ao Claude o SHA, a arquitetura efetiva, a imagem, os comandos, os resultados e o
   manifesto de evidências. Claude analisa esses resultados e fica dispensado de repetir a
   execução. O alvo do cartão é Linux x86_64. Se a imagem disponível executar em ARM64,
   o laudo identifica ARM64 e registra separadamente a situação de x86_64.
3. Descrição do PR: cabeça, contagens, linhas por arquivo, os 18 mutantes, desvios.
4. Copie este cartão para o caminho do §1. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.
