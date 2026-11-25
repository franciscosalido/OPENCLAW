# DL4-PR02 — Supercartão: três roteiros de trava de BOVA11 e o gabarito do M1

**Data:** 25/11/2026 · **Autor:** Claude (planejador) · **Implementa:** Codex
**Base:** `main` = `565136d` (DL4-PR01 integrado, PR #188)
**PR novo**, em rascunho. **Só fixtures e testes: nenhum arquivo de produção muda.**

**Origem:**

- Blueprint da Fase 4, §6 (M1, cartão «roteiros oficiais novos de trava de BOVA11») e §2
  (prova de uso: 3 replays, 6 perguntas cada, 18 respostas).
- Plano de PRs do colaborador, cartão «DL4-PR02».
- Decisão de Francisco de 24/11/2026 (L3): mercado adverso é só o que o simulador já
  recusa hoje.
- DL4-PR01, §9: o gabarito das 18 perguntas é escrito aqui, antes da tela.

## 0. Escopo

**O que acontece hoje.** Fatos conferidos em `565136d`:

- As três sessões oficiais (`calmo`, `leilao`, `rapido`) usam séries «A» e «B» sobre
  «ETF», 10 unidades e lote 1. Servem ao motor, não a uma prova de uso: não parecem uma
  boleta que Francisco reconheça.
- `ticket_view` existe e prevê o motor (DL4-PR01), mas não há roteiro de trava de BOVA11
  nem gabarito gravado.
- A blueprint (§12) deixou em aberto se o simulador de hoje reproduz «cotação vencida» e
  «mercado adverso» sem mudança. **Reproduz.** O protótipo deste cartão não tocou em
  produção.

**O que este cartão entrega.**

1. **Três sessões sintéticas de trava de BOVA11**, cada uma com fita e roteiro:
   `bova_calmo`, `bova_vencida` e `bova_adverso`.
2. **O gabarito da prova de uso do M1**: 6 perguntas fixas e, para uma foto de cada sessão,
   as 6 respostas. São as 18 respostas que a tela do DL4-PR03 terá de permitir a Francisco
   dar sem abrir JSON.
3. **Testes** que prendem os bytes, conferem as respostas pela visão e provam que a visão
   prevê o motor em cada confirmação roteirizada.

**O que este cartão não faz.**

- Não muda `backend/`, `config/` nem `scripts/`. Se algum esperado só fechar mexendo em
  produção, é parada (§7).
- Não altera as três sessões oficiais nem os testes existentes.
- Não faz tela, HTML nem formatação de dinheiro (DL4-PR03).
- Não cria condição nova de mercado. As três situações usam só guardas de `assess`.
- Não ensaia gatilho, cancelamento, execução parcial nem parada no meio. Isso é do M2 e
  do M3, com roteiros próprios.
- Não usa dado real, OpLab, rede nem token. **Tudo é sintético**, e o gabarito diz isso.

Nenhuma dependência nova. Nenhum arquivo protegido.

## 1. Referência externa

Conferida pelo planejador em 25/11/2026.

- **B3, contrato de opções sobre ETF:** o vencimento mensal é a 3ª sexta-feira do mês de
  vencimento. 15/01/2027 é a 3ª sexta de janeiro e consta como pregão aberto em
  `config/calendars/b3_calendar_2027.yaml`. 25/11/2026, dia das fitas, também.
- **Código da série:** raiz de 4 letras, letra do mês (A a L para call, M a X para put) e
  o número da série. As fixtures seguem o gerador sintético do repositório
  (`series_symbol`): strike vezes dez. Call de janeiro 150,00 é `BOVAA1500`; put de janeiro
  145,00 é `BOVAM1450`. **É convenção sintética do projeto, não código real listado.**
- **Pydantic 2.14** (documentação oficial, conceitos «Strict Mode» e «JSON»):
  - em modo estrito, a validação a partir de JSON é mais frouxa que a de Python: data,
    instante e `Decimal` em texto são aceitos em `model_validate_json`. É o caminho que
    `_read` e `load_replay` já usam; por isso os valores vão como texto nas fixtures;
  - **chave duplicada em JSON não é erro para o Pydantic: vale a última.** `_read` e
    `load_replay` já recusam duplicata por conta própria. O gabarito é lido com
    `json.loads` puro, então o teste B2 confere duplicata à mão.

Lote de 100 e passo de R$ 0,01 são os que a fixture sintética de BOVA11 do repositório já
usa (`contract_size: 100`). O contrato da B3 para esses dois pontos **não foi relido**
nesta sessão.

## 2. Arquivos

Todos novos. Em `tests/fixtures/derivatives/synthetic/ticket/sessions/`:

| Arquivo | SHA-256 |
|---|---|
| `bova_calmo.replay.json` | `ff7494c11c1adc7b859c43768a4834f48ff12cda0013c49eb7a11bfc8d540cfa` |
| `bova_calmo.roteiro.json` | `dbd5d784e65402c78ac615beb679686ee420f7fd1e968c44b29e0d132881c30c` |
| `bova_vencida.replay.json` | `14583cfd46bd80135db6c69ba0bcbed3e9e577f2d92708cc89dfcbd4f4afb880` |
| `bova_vencida.roteiro.json` | `2f4f35f2996c2f09cbdf4f2963824cc96791c159bae27a3e933fada2549363cc` |
| `bova_adverso.replay.json` | `70409a55ca91e06d3de77fb4cc37e0593aa5162a2708cd6296b12642fc5cbd48` |
| `bova_adverso.roteiro.json` | `83aabe19890f6fd21c9f6390d02faa6dbe640e875422f4f34ccccc7e865ab5d3` |
| `bova.gabarito.json` | `5a788938e8618f3141003c110d88337bd128bf4aac23068a3a4f731f43095803` |

Mais `tests/unit/derivatives/ticket/test_bova_sessions.py` (B1 a B8) e a cópia deste
cartão em `docs/specs/derivatives/fase4/DL4-PR02.md`.

**Os sete arquivos saem do patch anexo** (`DL4-PR02_PROTOTIPO.patch`, SHA-256
`69c0cf76b954…`, aplica limpo sobre `565136d` com `git apply`). **Os bytes são parte do
contrato:** não reformate, não reordene chaves, não troque a quebra de linha final. O §3
descreve o conteúdo para quem revisa; o hash decide.

**Não muda:** nenhum arquivo de produção, nenhum teste existente, nenhuma das três sessões
oficiais, `current_state.md`.

## 3. As três sessões

Comum às três: pregão sintético de 25/11/2026; fechamento às 21:00:00Z; prazo de envio
15:00:00Z; validade das ordens 21:00:00Z; conta `sim`; foto com as duas séries, ativo
`BOVA11`, vencimento 15/01/2027, multiplicador 1, saldo 0; um par (proteção, vendida);
lote 100; boleta `T1` aberta depois do evento 2, às 14:00:02Z; TTL da decisão 60 s. Toda
cotação tem os dois lados e tamanhos múltiplos de 100.

### 3.1 `bova_calmo` — trava de alta com calls, a débito

| | Compra | Venda |
|---|---|---|
| Série | `BOVAA1500` (call 150,00) | `BOVAA1550` (call 155,00) |
| Quantidade e limite | 100 a 4,20 | 100 a 2,10 |

Líquido `210.00` (débito), teto bruto `630.00`.

Fita: (1) 14:00:00 `BOVAA1500` 4,15 × 4,20, 500/500; (2) 14:00:01 `BOVAA1550`
2,10 × 2,15, 500/500; (3) 14:00:04 repete a 1; (4) 14:00:05 repete a 2. Tudo contínuo.

Roteiro: abre; **confirma às 14:00:03** (aceita). A compra executa no evento 3 e a venda
no 4. Termina «Concluída».

### 3.2 `bova_vencida` — trava de alta com puts, a crédito

| | Compra (proteção) | Venda |
|---|---|---|
| Série | `BOVAM1450` (put 145,00) | `BOVAM1500` (put 150,00) |
| Quantidade e limite | 200 a 1,90 | 200 a 3,90 |

Líquido `-400.00` (crédito), teto bruto `1160.00`.

Fita: (1) 14:00:00 `BOVAM1450` 1,85 × 1,90; (2) 14:00:01 `BOVAM1500` 3,90 × 3,95;
(3) **14:00:09 só a `BOVAM1500` se renova**; (4) 14:00:12 `BOVAM1450` se renova;
(5) 14:00:14 `BOVAM1450`; (6) 14:00:15 `BOVAM1500`. Tudo contínuo, 500/500.

Roteiro: abre; **confirma às 14:00:10, depois do evento 3** (recusada: a perna comprada
está com 10 s, acima do limite de 5 s); **confirma às 14:00:13, depois do evento 4**
(aceita). Compra no evento 5, venda no 6. Termina «Concluída».

### 3.3 `bova_adverso` — trava de alta com calls, a débito

| | Compra | Venda |
|---|---|---|
| Série | `BOVAA1550` (call 155,00) | `BOVAA1600` (call 160,00) |
| Quantidade e limite | 200 a 2,15 | 200 a 0,95 |

Líquido `240.00` (débito), teto bruto `620.00`.

Fita: (1) 14:00:00 `BOVAA1550` 1,80 × 2,15, **só 100 na venda** (spread de 0,35 e
profundidade menor que a boleta); (2) 14:00:01 `BOVAA1600` 0,95 × 1,00 **em leilão**;
(3) 14:00:04 `BOVAA1600` contínua; (4) 14:00:05 `BOVAA1550` igual à 1.

Roteiro: abre; **confirma às 14:00:03** (recusada). Não há segunda tentativa: a boleta
termina «Proposta», com recibo de 1 evento.

### 3.4 Gabarito (`bova.gabarito.json`)

Chaves, nesta ordem: `formato` (1), `natureza` (`SINTETICO`), `aviso`, `perguntas` (6),
`fotos` (3). Cada foto: `sessao`, `passos`, `avanca_ate`, `boleta`, `instante`,
`respostas` (6).

**As seis perguntas:**

1. O que a boleta compra e o que vende, em que quantidade e a que preço-limite?
2. Quanto paga ou recebe no líquido, e qual é o teto bruto?
3. Quanto desembolsa se só a compra executar, e qual é o pior resultado no vencimento?
4. Qual é a idade da cotação de cada perna, e de que foto veio a proposta?
5. Como está o mercado para esta boleta?
6. A boleta pode ser confirmada agora? Se não, por quê?

**As três fotos** (todas com 1 passo executado, boleta `T1`):

| | `bova_calmo` | `bova_vencida` | `bova_adverso` |
|---|---|---|---|
| avança até / instante | 2 / 14:00:02Z | 3 / 14:00:10Z | 2 / 14:00:02Z |
| 1 | Compra 100 BOVAA1500 (CALL 150.00) a 4.20; Venda 100 BOVAA1550 (CALL 155.00) a 2.10 | Compra 200 BOVAM1450 (PUT 145.00) a 1.90; Venda 200 BOVAM1500 (PUT 150.00) a 3.90 | Compra 200 BOVAA1550 (CALL 155.00) a 2.15; Venda 200 BOVAA1600 (CALL 160.00) a 0.95 |
| 2 | paga no máximo 210.00; bruto até 630.00 | recebe no mínimo 400.00; bruto até 1160.00 | paga no máximo 240.00; bruto até 620.00 |
| 3 | desembolso se só a compra executar 420.00; pior resultado no vencimento -210.00 | desembolso se só a compra executar 380.00; pior resultado no vencimento -600.00 | desembolso se só a compra executar 430.00; pior resultado no vencimento -240.00 |
| 4 | BOVAA1500 2.0 s, BOVAA1550 1.0 s; foto bova-calmo-2 | BOVAM1450 10.0 s, BOVAM1500 1.0 s; foto bova-vencida-2 | BOVAA1550 2.0 s, BOVAA1600 1.0 s; foto bova-adverso-2 |
| 5 | OK: sem aviso | BLOCKED: cotação vencida | BLOCKED: spread aberto, pouca profundidade, leilão |
| 6 | pode confirmar | não avança: cotação vencida | não avança: spread aberto, pouca profundidade, leilão |

As respostas são, letra por letra, a saída do leitor independente `answers` do
`test_view.py` (V14 do DL4-PR01) sobre o JSON da visão. O dinheiro sai sem formatação
(«210.00»); formatar é do DL4-PR03, e a comparação com o que Francisco disser é por valor.

## 4. Cenários

**B1 — fixtures coerentes** (uma vez por sessão). As pernas da boleta são as séries da
foto. Cada série tem o código que `raiz + letra do mês + strike × 10` dá para o seu tipo,
vencimento e strike. Ativo `BOVA11`, multiplicador 1, saldo 0. Vencimento numa sexta entre
os dias 15 e 21. Lote 100, quantidade múltipla de 100, igual nas duas pernas. Preço-limite
no passo de 0,01. Ambiente `SIMULATED`. Validade igual ao fechamento da fita. Fita sem
salto de sequência; todo evento é cotação do dia 25/11/2026, com compra menor que venda e
tamanhos múltiplos de 100.

**B2 — bytes presos.** Os sete SHA-256 do §2. O gabarito não tem chave duplicada; tem as
chaves do §3.4 na ordem; `formato` 1 e `natureza` `SINTETICO`; as 6 perguntas literais; as
3 fotos com (sessão, passos, avança até, boleta, instante) do §3.4; 18 respostas, iguais
às do §3.4, **escritas também no arquivo de teste** (o gabarito não pode ser conferido só
contra si mesmo).

**B3 — a visão dá as 18 respostas.** Para cada foto: executar os passos, avançar a fita,
projetar `ticket_view` no instante e passar o JSON pelo leitor `answers`. O resultado é
igual às 6 respostas da foto.

**B4 — conta à mão.** Às 14:00:02, depois do evento 2:

| Sessão | Líquido | Teto | Desembolso | Pior | Melhor |
|---|---|---|---|---|---|
| `bova_calmo` | `210.00` DEBITO | `630.00` | `420.00` | `-210.00` | `290.00` |
| `bova_vencida` | `-400.00` CREDITO | `1160.00` | `380.00` | `-600.00` | `400.00` |
| `bova_adverso` | `240.00` DEBITO | `620.00` | `430.00` | `-240.00` | `760.00` |

Nenhum extremo ilimitado; `vencimento_indisponivel` nulo. Conferência:

- calmo: 100 × 4,20 = 420 e 100 × 2,10 = 210; líquido 210, bruto 630. Abaixo de 150
  perde o débito, −210. Acima de 155 ganha 100 × 5 − 210 = 290.
- vencida: compra 200 × 1,90 = 380; vende 200 × 3,90 = 780; recebe 400, bruto 1.160.
  Acima de 150 fica com o crédito, +400. Abaixo de 145 perde 200 × 5 − 400 = 600.
- adverso: 200 × 2,15 = 430 e 200 × 0,95 = 190; líquido 240, bruto 620. Abaixo de 155,
  −240. Acima de 160, 200 × 5 − 240 = 760.

**B5 — a visão prevê cada confirmação roteirizada.** Projetar imediatamente antes de cada
passo `confirm` e depois executá-lo. Recusa do motor implica visão `BLOQUEADA` com
`motivo == str(exceção)`.

| Sessão, passo | Visão |
|---|---|
| `bova_calmo` 2 | PODE_CONFIRMAR |
| `bova_vencida` 2 | BLOQUEADA «cotação vencida» |
| `bova_vencida` 3 | PODE_CONFIRMAR |
| `bova_adverso` 2 | BLOQUEADA «spread aberto, pouca profundidade, leilão» |

**B6 — a guarda diz qual perna, e muda com a fita.** (avanço; mercado; por perna: nível,
motivos, idade)

| Sessão, passos, avança até, instante | Esperado |
|---|---|
| calmo 1, 2, 14:00:02 | PODE_CONFIRMAR; OK; (OK, 2.0) e (OK, 1.0) |
| vencida 1, 3, 14:00:10 | BLOQUEADA; BLOCKED; (BLOCKED cotação vencida, 10.0) e (OK, 1.0) |
| vencida 2, 4, 14:00:13 | PODE_CONFIRMAR; OK; (OK, 1.0) e (OK, 4.0) |
| adverso 1, 2, 14:00:02 | BLOQUEADA; BLOCKED; (CAUTION spread aberto, pouca profundidade, 2.0) e (BLOCKED leilão, 1.0) |
| adverso 2, 3, 14:00:04 | PODE_CONFIRMAR; **CAUTION**; (CAUTION spread aberto, pouca profundidade, 4.0) e (OK, 0.0) |

A última linha é o caso que a tela terá de mostrar bem: o leilão acabou, o aviso da
perna comprada continua, e a boleta pode avançar.

**B7 — o script oficial executa cada sessão até um recibo fixo.** `main` devolve 0.

| Sessão | Estado | Executado | Preço médio | Brutos (assinado, executado, projetado) | Eventos | Âncora | Recusas |
|---|---|---|---|---|---|---|---|
| `bova_calmo` | COMPLETED «Concluída» | 100 e 100 | `4.2000`, `2.1000` | 630.00, 630.00, 630.00 | 8 | `de7b45d3c7ed…` | nenhuma |
| `bova_vencida` | COMPLETED «Concluída» | 200 e 200 | `1.9000`, `3.9000` | 1160.00, 1160.00, 1160.00 | 8 | `cc91c71f6943…` | passo 2, `EngineRefusal` |
| `bova_adverso` | DRAFT «Proposta» | 0 e 0 | nulo, nulo | 620.00, 0.00, 620.00 | 1 | `43c254c9e797…` | passo 2, `EngineRefusal` |

Âncoras completas:
`de7b45d3c7ed06b4c527a9cbc1036de57ad7a9d9126ce06740c353f0bf0da67e`,
`cc91c71f694372eae35436f2cc7f6685ba9625c0595678f1d7af0af027d1584a`,
`43c254c9e7975fa62d8e2c86a3b72a60ff25d5a8d8e69ada1e3d5edbd8d7137d`.
Nenhum saldo vivo, nenhuma conta bloqueada. A saída tem só `recibo_T1.jsonl` e
`resumo.json`; a última linha do recibo traz a âncora.

**B8 — contexto decimal de quem chama.** Sob `Context(prec=3)`, com a armadilha de
`InvalidOperation` ligada e desligada, as 18 respostas saem iguais. É a lição do Adendo 1
do DL4-PR01 aplicada ao gabarito.

## 5. Evidência do planejador

`565136d`, Linux x86_64, Python 3.12.3, pydantic 2.14.4.

- **Nenhum arquivo de produção mudou** no protótipo. A dúvida do §12 da blueprint está
  respondida: o simulador de hoje produz as três situações.
- **Portão completo no protótipo** (`pytest tests/ -q --ignore=tests/integration
  --timeout=120`): **11.697 aprovados, 16 pulados, 261 subtestes**, código 0. São os
  11.685 da base mais 12 novos (B1 e B7 contam três cada).
- `mypy --strict` no arquivo de teste: limpo. Não há o que conferir em `backend/`.
- **Sessões oficiais** pelo script, com as fixtures novas presentes: os 7 arquivos
  idênticos byte a byte aos da base.
- **Saídas das sessões novas** (12 primeiros do SHA-256 de `recibo_T1.jsonl` e de
  `resumo.json`): calmo `1a597f0ee502` e `c9af46632d06`; vencida `6edace5ba315` e
  `a128dbc5a206`; adverso `376844ee7ba7` e `9dfbc5a4abb0`.
- **RED:** só com o arquivo de teste, sem as fixtures, tudo falha por arquivo ausente.
- **Mutantes:** 20 plantados, 20 detectados (§6).
- **Erro do próprio protótipo, corrigido antes do cartão:** na primeira versão da
  `bova_vencida` o crédito (380) coincidia com o desembolso (380). Dois números iguais com
  significados diferentes estragam a pergunta 3; o preço da vendida passou a 3,90.

**Não conferido pelo planejador:** Mac arm64; `tests/integration`; o contêiner
`openclaw-sandbox`; o contrato da B3 para lote e passo de preço (§1).

## 6. Mutantes obrigatórios

Um por vez, sobre as fixtures. Cada um tem de derrubar ao menos um teste **além do B2**,
salvo os dois últimos. Entre parênteses, quem derrubou no protótipo, fora o B2.

1. vencida: a cotação nova do evento 3 cai na perna comprada (B3, B5, B6, B7, B8).
2. adverso: sem leilão (B3, B5, B6, B7, B8).
3. adverso: profundidade suficiente, 200 (B3, B5, B6, B8).
4. adverso: spread fechado, compra a 2,10 (B3, B5, B6, B8).
5. calmo: líquido folgado, 220 (B3, B4, B7, B8).
6. vencida: sinal do líquido trocado (B3, B4, B7, B8).
7. calmo: quantidade 200 na compra (B1, B3 a B8).
8. calmo: strike 151 na foto (B1, B3, B4, B8).
9. gabarito: uma resposta editada (B3, B8).
10. adverso: par invertido (B3 a B8).
11. gabarito: foto da vencida às 14:00:09 (B3, B8).
12. vencida: segunda confirmação antes da cotação nova (B5, B7).
13. calmo: vencimento numa quinta (B1).
14. vencida: put com letra de call, `BOVAA1450` (B1, B7).
15. calmo: lote 1 (B1, B7).
16. calmo: multiplicador 100 (B1, B3 a B8).
17. calmo: fita sem o evento 4, a venda não executa (B7).
18. adverso: o leilão não termina no evento 3 (B6).
19. gabarito: pergunta reescrita (só B2).
20. gabarito: chave duplicada (só B2).

## 7. Critérios de parada

Pare e relate se:

- a `main` não for `565136d`;
- algum SHA do §2 não bater depois de aplicar o patch;
- algum esperado do §4 não reproduzir;
- **for preciso tocar em qualquer arquivo de produção**;
- qualquer teste existente mudar de resultado ou a contagem de pulos mudar;
- alguma das 4 âncoras oficiais ou algum dos 7 arquivos das sessões oficiais mudar;
- `tests/integration` der resultado diferente da linha de base (§8).

Se a borda contrariar o gabarito, pare e peça adendo. **Não mude resposta, fita nem
roteiro para fazer passar:** o gabarito foi gravado antes de propósito.

**Reversão:** o PR só acrescenta arquivos. Reverter o commit devolve a base.

## 8. Entrega

1. Commit vermelho só com `test_bova_sessions.py`. Envie ao GitHub antes do verde.
2. Commit verde com os sete arquivos de fixture, sem mais nada.
3. Portão no Mac arm64 em clone limpo e portão Linux no contêiner isolado, com imagem do
   lock da cabeça. Esperado: **11.697 aprovados, 16 pulados**. `mypy backend/ --strict` e
   `pyright backend/` limpos, como na base.
4. **Linha de base de `tests/integration`** (só no contêiner): as mesmas 4 falhas
   conhecidas da `main`, pelos mesmos IDs, como no pacote do DL4-PR01. Falha a mais ou a
   menos é parada.
5. Os 7 SHA-256 das fixtures na cabeça; os SHA-256 de `recibo_T1.jsonl` e `resumo.json`
   das três sessões novas, Mac e Linux; os 7 arquivos das sessões oficiais, base ×
   candidato.
6. Para o revisor e na descrição do PR: cabeça, arquitetura, imagem, versões, comandos,
   logs, contagens, os 20 mutantes, desvios.
7. Copie este cartão para o caminho do §2. Não edite `docs/04_MEM/current_state.md`.
8. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição. **Rode-as no ambiente do lock** (pydantic 2.14.4): no
   DL4-PR01 os pareceres locais usaram 2.13.3.
9. **Adendo só entra na cópia versionada com a autorização de Francisco colada na
   descrição do PR**, com data.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda por conta
própria o B3, o B5 e os mutantes 1, 9 e 11.

## 9. Decisões do planejador que Francisco pode vetar

| # | Decisão | Por quê |
|---|---|---|
| D1 | As três sessões usam boletas diferentes (call a débito, put a crédito, call a débito) | boleta igual nas três tornaria 9 das 18 respostas repetição |
| D2 | A foto do `bova_adverso` junta leilão na vendida com spread aberto e pouca profundidade na comprada | mostra bloqueio e cautela na mesma tela, cada um na sua perna |
| D3 | O `bova_adverso` termina «Proposta», sem segunda tentativa | execução parcial é assunto do M2 e do M3, com roteiro próprio |
| D4 | As respostas do gabarito trazem o dinheiro sem formatação | é a saída literal da visão; a tela formata, e a comparação é por valor |
| D5 | Os códigos das séries seguem o gerador sintético do projeto (strike × 10) | coerência com a fixture de BOVA11 que já existe; não são códigos reais |

## 10. Depois deste cartão

DL4-PR03: a tela HTML estática, lendo só o JSON de `ticket_view`, e a prova de uso do M1
feita por Francisco contra este gabarito. Dois pontos já anotados para aquele cartão:

- a tela formata dinheiro e terá de tratar notação exponencial (`1E+2`);
- quando a tela passar a **ler** a visão, endurecer o `formato`: hoje `Literal[1]` aceita
  `true` e `1.0` na leitura (nota N-1 do parecer do DL4-PR01).

Pendência separada, sem cartão aberto: as 4 falhas de `tests/integration` na `main`.
