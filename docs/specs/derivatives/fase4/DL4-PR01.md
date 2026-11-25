# DL4-PR01 — Supercartão: contrato de visão da boleta (M1)

**Data:** 25/11/2026 · **Autor:** Claude (planejador) · **Implementa:** Codex
**Base:** `main` com o DL4-PR00 integrado (PR #186). O protótipo foi medido sobre a árvore
de `8aea7c9`. Antes de começar, confira que `git diff 8aea7c9 origin/main --stat` só lista
`docs/04_MEM/`. Se listar outra coisa, pare e relate.
**PR novo**, em rascunho. Um cartão, uma revisão.

**Origem:**

- Blueprint da Fase 4, §6 (M1, «contrato de visão») e §9; plano de PRs do colaborador,
  cartão «DL4-PR01».
- Decisões de Francisco de 24/11/2026: **L3**, mercado adverso é só o que
  `guards.assess` já emite; **L4**, o risco aparece em dois números com rótulos distintos.
- Parecer do DL4-PR00 (N-1): este cartão declara a linha de base de `tests/integration`.

## 0. Escopo

**O que acontece hoje.** Fatos conferidos na árvore de `8aea7c9`:

- Não existe leitura da boleta para humano. `ReplaySession.summary()` é um resumo
  genérico, sem cotação, sem guarda e sem motivo de recusa.
- O motor só diz por que não avança **quando alguém tenta confirmar**: `confirm` confere
  estado, pausa, conta, prazos, mercado, limites e reservas, e levanta três tipos de
  recusa (`EngineRefusal`, `DeadlineRefusal`, `SequenceRefusal`). Não há consulta sem
  efeito.
- `assess` devolve os motivos de todas as pernas numa lista só, sem dizer de qual perna.
  O nível `CAUTION` nunca chega a quem chama o motor.
- Livro, configuração e foto da conta são privados do motor e da sessão.

**O que este cartão entrega.**

1. **Leitura sem efeito no motor.** `TicketEngine.reading(now)` devolve os fatos que a
   confirmação conferiria, sem consumir decisão nem ocupar reserva. `confirm` passa a usar
   o mesmo trecho de conferência: há uma fonte só.
2. **Contrato de visão.** `ticket_view(session, ticket, now)`, função pura em módulo novo,
   devolve um modelo de tela versionado (`formato` 1) com pernas, custo, dois riscos,
   cotação e guarda por perna, guarda do conjunto e situação de avanço com o motivo
   literal do motor.
3. **Esquema publicado** do JSON de saída, conferido byte a byte.

**O que este cartão não faz.**

- **Não tem tela**, HTML, terminal nem script novo. Isso é o DL4-PR03.
- **Não muda regra do motor.** A ordem e o texto das recusas de `confirm` ficam iguais.
  As 4 âncoras e os 7 arquivos das sessões oficiais não mudam.
- Não cria roteiro de BOVA11 (DL4-PR02), não mostra execução por perna, ordens nem os
  três brutos (DL4-PR05; lá o `formato` sobe para 2).
- Não calcula spread de mercado, preço médio, mid, margem nem custo de corretagem.
- Não formata dinheiro para leitura (R$, vírgula). O dinheiro sai como o motor o guarda.
- Não toca `summary()`, o recibo, o esquema da prévia nem `scripts/`.

Nenhuma dependência nova. Nenhum arquivo protegido.

## 1. Referência externa

Não há matéria de FIX nem de OIC neste cartão. O resultado no vencimento vem de
`backend/derivatives/pricing/expiry_payoff.py`, já conferido contra conta à mão e
OptionLab no DL3-PR08A e no DL3-PR08C. Este cartão não recalcula payoff; só chama
`expiry_profile`.

## 2. Arquivos e tetos

| Arquivo | O que muda | Teto (protótipo) |
|---|---|---|
| `backend/derivatives/ticket/engine.py` | `CONFIRMABLE`, `Reading`, `_admissible`, `reading`; `confirm` usa `_admissible` | 580 (575; hoje 544) |
| `backend/derivatives/ticket/view.py` | **novo**: modelos e `ticket_view` | 210 (200) |
| `tests/unit/derivatives/ticket/test_view.py` | **novo**: V1 a V15 | — |
| `docs/specs/derivatives/fase4/schemas/visao.schema.json` | **novo**, gerado | — |
| `docs/specs/derivatives/fase4/DL4-PR01.md` | cópia deste cartão | — |

**Não muda:** `session.py`, `guards.py`, `sequencing.py`, `models.py`, `scripts/`,
roteiros e fitas, `previa.schema.json`, `current_state.md`. Linhas novas com até 100
colunas.

**Nenhum teste existente muda.** Se algum mudar de resultado, é parada (§7).

## 3. Regra

### 3.1 Motor (`engine.py`)

- `CONFIRMABLE = (T.DRAFT, T.TRIGGERED)`, pública. `confirm` e a visão usam a mesma
  constante.
- `_admissible(now) -> LegPlan`: o trecho que hoje abre `confirm`, **na mesma ordem e com
  os mesmos textos**: estado; «boleta pausada»; «conta em estado incerto»;
  `check_deadlines`; bloqueio de mercado; «limites assinados»;
  `reservations.admissible`. Devolve o plano.
- `confirm` vira: `plan = self._admissible(now)`, depois o consumo da decisão e o resto,
  sem mudança.
- `Reading(NamedTuple)`: `position`, `quotes` (uma `BookSnapshot | None` por perna
  assinada), `guards` (um `GuardResult` por perna, de `assess((leg,), …)`), `market`
  (`assess` de todas as pernas) e `refusal` (`str | None`).
- `reading(now) -> Reading`: sem proposta, `EngineRefusal("boleta sem proposta")`. Chama
  `_admissible` e guarda em `refusal` o texto de `EngineRefusal`, `DeadlineRefusal` ou
  `SequenceRefusal`. Não captura mais nada.

`reading` usa `admissible`, que só consulta; **nunca** `admit`.

### 3.2 Visão (`view.py`)

`ticket_view(session, ticket, now) -> TicketView`. Primeiro `session.check_time(now)`;
depois `session.engine(ticket)`. Boleta desconhecida continua `KeyError`, como em
`session.engine`. Modelos `_Frozen` (estritos, imutáveis, campo extra recusado).

| Campo | Origem | Regra |
|---|---|---|
| `formato` | constante | `1` literal |
| `aviso` | constante | «SIMULADO — dados sintéticos em replay; nenhuma ordem real.» |
| `boleta`, `conta` | argumento; `reading.position.account` | |
| `instante` | `now` | normalizado para UTC |
| `estado`, `rotulo`, `pausada` | `engine.state`, `engine.label`, `engine.paused` | o rótulo é o do motor, com «· montagem parcial» quando houver |
| `versao`, `resumo`, `foto_cotacao`, `prazo_envio`, `validade_ordens` | `engine.preview` | cópia |
| `pernas[]` | `preview.legs`, na ordem assinada | ver abaixo |
| `custo` | `preview` | `liquido_assinado` = `net_limit` com o sinal do motor; `natureza` = `DEBITO` se > 0, `CREDITO` se < 0, `ZERO`; `bruto_teto` = `gross_cap` |
| `risco.exposicao_montagem` | `preview.partial_exposure` | cópia |
| `risco.vencimento` | `expiry_profile` | ver 3.3 |
| `mercado` | `reading.market` | `nivel` e `motivos` literais |
| `avanco` | `engine.state`, `reading.refusal` | ver 3.4 |

Cada perna: `serie`, `lado`, `lado_rotulo` («Compra»/«Venda»), `quantidade`, `lote`,
`preco_limite`; da foto, `ativo`, `tipo`, `strike`, `vencimento`; `cotacao` (ou `null`);
`guarda` (`nivel`, `motivos`).

`cotacao`: `compra`, `compra_qtd`, `venda`, `venda_qtd`, `fase`, `instante`, `idade_s`.
`idade_s = (now - ts).total_seconds()`. Série sem cotação dá `cotacao: null`, com a chave
presente. Lado vazio dá preço `null` e quantidade 0.

**Dinheiro sai sem reescrita.** Os campos copiados do motor são o mesmo `Decimal`. No
JSON, `Decimal("1E+2")` sai `"1E+2"` e `Decimal("2.5E+1")` sai `"25"` (é o `str` do
Python; o protótipo errou esse esperado na primeira tentativa). Formatar é da tela.

### 3.3 Resultado no vencimento (L4)

`pior_resultado` e `melhor_resultado` são os extremos **com sinal** de `expiry_profile`
(positivo é ganho), com cada perna ao seu preço-limite e à quantidade assinada. Strike e
prêmio entram quantizados a 0,01, para a saída ter sempre duas casas.
`perda_ilimitada` e `ganho_ilimitado` dizem por extenso quando o extremo é `null`.

**O rótulo é «pior resultado», não «perda máxima».** Na sessão `calmo` o pior resultado é
`5.00`, um ganho.

O perfil só vale para montagem a partir de posição zerada. Fora disso, `vencimento` é
`null` e `vencimento_indisponivel` traz o motivo, conferido nesta ordem:

1. `preview.coverage` não vazio → «cobertura cedida por outra boleta»
2. alguma série da boleta com saldo inicial diferente de zero → «posição inicial não nula»
3. ativos ou vencimentos diferentes → «séries de ativos ou vencimentos diferentes»
4. algum multiplicador diferente de 1 → «multiplicador diferente de 1»
5. algum strike ou preço-limite com `adjusted() > 15` → «valores fora da escala do perfil»
6. `PayoffRefusal` → o texto da recusa

O item 5 fecha, só para a visão, a pendência «limite de escala em `expiry_payoff`»: com
preço `1E+200000` o perfil levou 2 s no protótipo, e cresce com o expoente. O item 4 existe
porque o motor trata quantidade em unidades e não multiplica a exposição; mostrar um
perfil multiplicado ao lado de uma exposição não multiplicada seria incoerente.

### 3.4 Avanço (L3)

| Condição | `situacao` | `motivo` |
|---|---|---|
| `engine.state` fora de `CONFIRMABLE` | `NAO_SE_APLICA` | `null` |
| dentro, `reading.refusal` é `None` | `PODE_CONFIRMAR` | `null` |
| dentro, com recusa | `BLOQUEADA` | o texto do motor, sem edição |

**A visão não decide.** Ela não olha `mercado.nivel` para montar o avanço. `CAUTION` não
bloqueia. O motivo sai como o motor escreve, inclusive repetido por perna
(«leilão, leilão»); a tela usa a guarda por perna para dizer qual.

## 4. Cenários

Sessões oficiais executadas pelo roteiro até o passo indicado (`_read` e `_act` do
script). «Sintética» é fita montada no teste: A a 14:00:00 (0,95 × 1,02, 50/50) e B a
14:00:01 (1,45 × 1,55, 50/50), contínuas; foto A call 10, B call 11, ETF, 15/01/2027,
saldo 0, par A/B; prazos 15:00 e 21:00; boleta T1 aberta no último evento.

**V1 — treze fotos literais.** Estado, rótulo, avanço, guarda do conjunto e, por perna,
(nível, motivos, idade em s).

| Sessão, passos, boleta | Instante (avanço até) | Esperado |
|---|---|---|
| calmo 1, T1 | 14:00:02 | DRAFT «Proposta»; PODE_CONFIRMAR; OK; A (OK, 2.0), B (OK, 1.0) |
| calmo 2, T1 | 14:00:02 | ARMED «Engatilhada»; NAO_SE_APLICA; OK; idem |
| calmo 2, T1 | 14:00:12 (seq 6) | TRIGGERED «Gatilho atingido»; PODE_CONFIRMAR; OK; 2.0 e 1.0 |
| calmo 5, T1 | 21:00:00 (seq 9) | COMPLETED «Concluída»; NAO_SE_APLICA; BLOCKED (cotação vencida); A (OK, 0.0), B (BLOCKED cotação vencida, 25186.0) |
| leilao 1, T1 | 14:00:02 | DRAFT; BLOQUEADA «leilão, leilão»; BLOCKED (leilão, leilão); A (BLOCKED leilão, 2.0), B (BLOCKED leilão, 1.0) |
| leilao 1, T1 | 14:00:07 | DRAFT; BLOQUEADA «cotação vencida, leilão, cotação vencida, leilão»; cada perna BLOCKED (cotação vencida, leilão), 7.0 e 6.0 |
| leilao 4, T1 | 14:05:06 | WORKING «Em execução»; NAO_SE_APLICA; BLOCKED (leilão, pouca profundidade); A (BLOCKED leilão, 1.0), B (CAUTION pouca profundidade, 2.0) |
| leilao 4, T1 | 21:00:00 (seq 11) | STOPPED «Parada · montagem parcial»; NAO_SE_APLICA; BLOCKED (cotação vencida); A (BLOCKED, 24600.0), B (OK, 0.0) |
| rapido 3, T2 | 14:00:02 | DRAFT; BLOQUEADA «conta em estado incerto»; **OK**; 2.0 e 1.0 |
| rapido 3, T1 | 14:00:02 | UNCERTAIN «Boleta em estado incerto»; NAO_SE_APLICA; OK |
| rapido 5, T2 | 14:00:03 | DRAFT; BLOQUEADA «recompra excede a posição vendida disponível»; CAUTION (pouca profundidade); A (OK, 3.0), B (CAUTION, 0.0) |
| rapido 8, T2 | 14:00:06 | DRAFT; BLOQUEADA «perda de sequência, pouca profundidade, perda de sequência»; A (BLOCKED perda de sequência, pouca profundidade, 2.0), B (BLOCKED perda de sequência, 1.0) |
| rapido 9, T1 | 21:00:00 (seq 9) | STOPPED «Parada · desmontagem parcial»; NAO_SE_APLICA; BLOCKED (perda de sequência, cotação vencida, perda de sequência); 0.0 e 25193.0 |

**V2 — a visão prevê o motor.** Para cada um dos 7 passos `confirm` dos três roteiros:
projetar imediatamente antes, depois executar o passo. Se o motor recusar, a visão dizia
`BLOQUEADA` com `motivo == str(exceção)`. Se aceitar, dizia `PODE_CONFIRMAR`.

| Sessão, passo | Visão |
|---|---|
| calmo 3 | PODE_CONFIRMAR |
| leilao 2 | BLOQUEADA «leilão, leilão» |
| leilao 3 | PODE_CONFIRMAR |
| rapido 3 | PODE_CONFIRMAR |
| rapido 4 | BLOQUEADA «conta em estado incerto» |
| rapido 6 | BLOQUEADA «recompra excede a posição vendida disponível» |
| rapido 9 | BLOQUEADA «perda de sequência, pouca profundidade, perda de sequência» |

**V3 — fronteira da idade, por perna.** `calmo`, só a abertura, avanço até seq 8, sem
confirmar. Às 14:00:18: A 5.0 e B 4.0, tudo OK, PODE_CONFIRMAR (igual ao limite passa). Às
14:00:19: A (BLOCKED cotação vencida, 6.0), B (OK, 5.0); BLOQUEADA «cotação vencida». Às
14:00:18 mais 1 microssegundo: A já vencida.

**V4 — ordem das recusas.** Mesma sessão do V3. Às 15:00:00: «cotação vencida, cotação
vencida» (prazo ainda vale). Às 15:00:01: «prazo de envio vencido», com `mercado.nivel`
BLOCKED. Depois de `pause`: `pausada` verdadeiro e «boleta pausada». Sintética com
`net_limit` `-5.01`: BLOQUEADA «limites assinados», mercado OK. A mesma com B em leilão:
«leilão» (mercado antes de limites).

**V5 — ausência não é zero.** Sintética aberta só com a cotação de A (seq 1), às 14:00:00:
perna B com `cotacao` `null` (chave presente no JSON), guarda BLOCKED («sem cotação»);
avanço «sem cotação». Sintética com A sem oferta de venda: `venda` `null`, `venda_qtd` 0,
guarda («livro incompleto»).

**V6 — cautela não bloqueia.** Sintética com A 0,80 × 1,02 e 3 na venda: mercado CAUTION
(«spread aberto», «pouca profundidade»); A CAUTION, B OK; PODE_CONFIRMAR. Confirmando de
fato, a boleta vai a WORKING.

**V7 — dois riscos, com sinal.**

| Boleta | `custo` | `exposicao_montagem` | `pior` / `melhor` |
|---|---|---|---|
| calmo: compra 10 A a 1,00; vende 10 B a 1,50 | `-5.00`, CREDITO, teto `25.00` | `10.00` | `5.00` / `15.00` |
| sintética: compra 10 A a 1,50; vende 10 B a 1,00; líquido `5.00` | `5.00`, DEBITO, teto `25.00` | `15.00` | `-5.00` / `5.00` |
| sintética: as duas a 1,00; líquido `0.00` | ZERO | — | — |

Conta à mão da segunda: abaixo de 10, perde o débito, 10 × (1,00 − 1,50) = −5,00; acima
de 11, 10 × (11 − 10) − 5,00 = +5,00.

**V8 — perfil indisponível.** `rapido` 2, T1: `exposicao_montagem` `15.00`, `vencimento`
`null`, «posição inicial não nula». Sintética com multiplicador 2: «multiplicador
diferente de 1». Sintética com duas compras, B vencendo em 19/02/2027, sem pares:
«séries de ativos ou vencimentos diferentes». Sintética de uma compra de 1 A com preço
`1E+15` (líquido e teto `1E+17`): perfil disponível; com `1E+16`: «valores fora da escala
do perfil». Nos dois, `exposicao_montagem` é o próprio preço.

**V9 — uma perna só.** Sintética: compra 10 A a 1,00, sem pares, líquido e teto `10.00`.
`pior_resultado` `-10.00`, `perda_ilimitada` falso, `melhor_resultado` `null`,
`ganho_ilimitado` verdadeiro.

**V10 — notação exponencial.** Sintética de débito com preços `15E-1` e `1.0E+0`, líquido
`5`, teto `1E+2`, strikes `1E+1` e `11.000`. O `vencimento` no JSON é exatamente
`"-5.00"` / `"5.00"`. `custo` no JSON é `{"liquido_assinado": "5", "natureza": "DEBITO",
"bruto_teto": "1E+2"}`. `preco_limite` das pernas: `1.5` e `1.0`. Strikes: `1E+1` e
`11.000`. Os campos copiados são iguais aos da prévia.

**V11 — a visão não muda nada.** As três sessões inteiras, com a visão projetada antes e
depois de cada passo, para toda boleta aberta: `summary()` e os recibos saem iguais aos
da execução sem visão, com as 4 âncoras (`1d50bba66aa2`, `8592cd742d26`, `9ebc9cd5b584`,
`fbcaafa8eb79`). `rapido` 2: projetar T2, T1, T2, T1 dá PODE_CONFIRMAR nas quatro (a
leitura de uma boleta não ocupa a recompra da outra). Duas projeções seguidas são iguais.

**V12 — relógio do replay.** `calmo` 1: instante sem fuso, 14:00:00 (antes do último
evento) e 14:00:06 (depois do próximo) dão `SessionRefusal`. Boleta `T9`: `KeyError`.
11:00:02 em −03:00 dá a mesma visão que 14:00:02Z, e o JSON traz
`"2026-11-23T14:00:02Z"`.

**V13 — guarda do conjunto.** Nas 13 fotos do V1: `mercado.motivos` é a concatenação dos
motivos das pernas, e `mercado.nivel` é o pior nível das pernas.

**V14 — seis respostas só com o JSON.** Um leitor de teste que usa só `json.loads` e
dicionários, sem importar os modelos, responde as seis perguntas da prova de uso.

| Pergunta | calmo 1, T1, 14:00:02 | leilao 1, T1, 14:00:07 | rapido 3, T2, 14:00:02 |
|---|---|---|---|
| pernas | Compra 10 A (CALL 10) a 1.00; Venda 10 B (CALL 11) a 1.50 | idem | Venda 10 A (CALL 10) a 1.00; Compra 10 B (CALL 11) a 1.50 |
| líquido e bruto | recebe no mínimo 5.00; bruto até 25.00 | idem | paga no máximo 5.00; bruto até 25.00 |
| riscos | desembolso se só a compra executar 10.00; pior resultado no vencimento 5.00 | idem | desembolso se só a compra executar 15.00; vencimento indisponível: posição inicial não nula |
| idade e foto | A 2.0 s, B 1.0 s; foto calmo-2 | A 7.0 s, B 6.0 s; foto leilao-2 | A 2.0 s, B 1.0 s; foto rapido-2 |
| mercado | OK: sem aviso | BLOCKED: cotação vencida, leilão, cotação vencida, leilão | OK: sem aviso |
| avança? | pode confirmar | não avança: (o mesmo motivo) | não avança: conta em estado incerto |

`calmo` 2 (ARMED): «não se aplica: Engatilhada».

**V15 — JSON e esquema.** `model_validate_json(model_dump_json())` devolve a mesma visão.
Chaves do topo, nesta ordem: `formato`, `aviso`, `boleta`, `conta`, `instante`, `estado`,
`rotulo`, `pausada`, `versao`, `resumo`, `foto_cotacao`, `prazo_envio`,
`validade_ordens`, `pernas`, `custo`, `risco`, `mercado`, `avanco`. Campo extra e
`formato` 2 são recusados. `additionalProperties` falso no topo e em todo objeto de
`$defs`. `TicketView.model_json_schema(mode="serialization")`, serializado com
`sort_keys=True, indent=2, ensure_ascii=False` mais quebra de linha, é igual byte a byte
ao arquivo publicado. No protótipo o SHA-256 é `a63d4508c126…`. **Se você renomear campo
ou classe, o hash muda: gere o seu e declare.** Mudar nome de campo do §3.2 é desvio e
pede adendo.

## 5. Evidência do planejador

Árvore de `8aea7c9`, Linux x86_64, Python 3.12.3, pydantic 2.14.4.

- **Protótipo:** `engine.py` com 575 linhas (31 a mais), `view.py` com 200. O patch vai anexo
  a este cartão (`DL4-PR01_PROTOTIPO.patch`, SHA-256 `4e8788952d08…`) e aplica limpo sobre
  `8aea7c9` com `git apply`. É referência: pode ser reescrito, desde que §3, §4 e §6 se
  cumpram.
- **Portão completo no protótipo** (`pytest tests/ -q --ignore=tests/integration
  --timeout=120`): **11.684 aprovados, 16 pulados**, código 0. São os 11.657 da base mais
  27 novos (13 do V1 e 14 dos demais). Nenhum teste existente mudou.
- `mypy backend/ --strict`: limpo em 183 arquivos. `pyright backend/`: 0 erros.
  `tests/architecture`: passa, inclusive as fronteiras da boleta.
- **Sessões oficiais** pelo script, base × protótipo: os 7 arquivos idênticos byte a byte.
- **RED:** só com o arquivo de teste, a coleta falha por
  `ModuleNotFoundError: backend.derivatives.ticket.view`.
- **Mutantes:** 24 plantados, 24 detectados (§6). Dois sobreviveram na primeira rodada e
  o planejador reforçou V10 e V11 por causa deles; estão marcados.
- **Defeito do próprio protótipo, pego pela borda:** o esperado de `2.5E+1` estava errado
  (§3.2).

**Não conferido pelo planejador:** Mac arm64; `tests/integration`; o contêiner
`openclaw-sandbox`.

## 6. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, quem derrubou no
protótipo.

*Visão:*

1. Os dois riscos trocados ou iguais (V7, V8, V10, V14).
2. Avanço ignora a recusa: verde sob bloqueio (V1, V2, V3, V4, V5, V14).
3. Série sem cotação vira cotação zerada (V5).
4. A visão bloqueia por `CAUTION` (V6).
5. Natureza invertida (V7, V10, V14).
6. Idade com o sinal trocado (V1, V3, V14).
7. A visão decide sozinha quem é confirmável, por exemplo ARMED (V1, V14).
8. Perfil calculado com posição inicial não nula (V8, V14).
9. Perfil ignora o multiplicador (V8).
10. Perfil sem limite de escala (V8).
11. Strike sem quantizar (V10) — sobreviveu à primeira rodada.
12. Pior e melhor trocados (V7, V9, V14).
13. Visão sem `check_time` (V12).
14. Guarda do conjunto tirada só da primeira perna (V1, V13, V14).
15. Guardas das pernas em ordem trocada (V1, V3, V5, V6, V13).
16. `formato` 2 (todos).
17. Campo extra aceito (V15).
18. Rótulo tirado de `TICKET_LABELS_PT`, sem o sufixo de parada parcial (V1).

*Motor:*

19. `reading` chama `admit` em vez de `admissible` (V11) — sobreviveu à primeira rodada.
20. `_admissible` pula a pausa (V4).
21. `reading` não captura `SequenceRefusal` (V1, V2, V11, V13).
22. `reading` não captura `DeadlineRefusal` (V4).
23. Prazo e mercado em ordem trocada (V4).
24. Guarda por perna calculada com todas as pernas (V1, V3, V6, V13).

## 7. Critérios de parada

Pare e relate se:

- a árvore da `main` diferir de `8aea7c9` fora de `docs/04_MEM/`;
- algum esperado do §4 não reproduzir;
- **qualquer teste existente mudar de resultado** ou a contagem de pulos mudar;
- alguma das 4 âncoras ou algum dos 7 arquivos das sessões mudar;
- o texto ou a ordem de alguma recusa de `confirm` mudar;
- for preciso tocar em arquivo de produção fora do §2, em `session.py` ou em `guards.py`;
- `mypy --strict`, `pyright` ou `tests/architecture` deixar de sair limpo;
- **`tests/integration` der resultado diferente da linha de base** (§8).

Se a borda contrariar o gabarito, pare e peça adendo. Não mude o esperado em silêncio.

**Reversão:** o PR é aditivo, fora o refatoramento de `confirm`. Reverter o commit verde
inteiro devolve a base.

## 8. Entrega

1. Commit vermelho só com `test_view.py`. Envie ao GitHub antes do verde.
2. Commit verde com `engine.py`, `view.py` e o esquema.
3. Portão no Mac arm64 em clone limpo da cabeça candidata: `uv sync --locked`, a suíte,
   `mypy backend/ --strict` e `pyright backend/`. Esperado: **11.684 aprovados, 16
   pulados**. Se você escrever mais testes que os 27, declare a contagem.
4. Portão Linux no contêiner isolado, com imagem construída do lock da cabeça.
5. **Linha de base de `tests/integration`** (só no contêiner, nunca no Mac com banco
   vivo): a `main` tem 4 falhas conhecidas, registradas no pacote do DL4-PR00
   (`DL4-PR00-8aea7c9.zip`: 215 aprovados, 18 pulados, 4 falhas). O esperado aqui é
   **as mesmas 4, pelos mesmos IDs**. Falha a mais ou a menos é parada. As 4 **não** são
   deste cartão e não devem ser corrigidas nele.
6. Sessões oficiais base × candidato pelo script: os 7 SHA-256, iguais.
7. Esquema: o hash do esquema **gerado** na cabeça, não só o do arquivo gravado.
8. Para o revisor e na descrição do PR: cabeça, arquitetura, imagem, versões, comandos,
   logs, contagens, linhas de `engine.py` e `view.py`, os 24 mutantes, desvios.
9. Copie este cartão para o caminho do §2. Não edite `docs/04_MEM/current_state.md`.
10. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora
    do Git, SHA-256 na descrição.
11. **Adendo só entra na cópia versionada com a autorização de Francisco colada na
    descrição do PR**, com data.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda por conta
própria o V2, o V11 e os mutantes 2, 19 e 23.

## 9. Decisões do planejador que Francisco pode vetar

Não são de L3 nem de L4. O protótipo as assumiu; se alguma estiver errada, diga antes de
o Codex começar.

| # | Decisão | Por quê |
|---|---|---|
| D1 | O motivo sai literal, inclusive repetido («leilão, leilão») | a visão não edita o motor; a guarda por perna diz qual |
| D2 | Perfil no vencimento só para montagem a partir de posição zerada | numa desmontagem, o perfil das pernas da boleta não é o risco da posição |
| D3 | Multiplicador diferente de 1 deixa o perfil indisponível | o motor não multiplica a exposição; os dois números ficariam incoerentes |
| D4 | Dinheiro sem formatação na visão | formatar é da tela (DL4-PR03), que terá de tratar `1E+2` |
| D5 | Execução por perna, ordens e brutos ficam para o DL4-PR05, com `formato` 2 | o M1 é ver e decidir; acompanhar é M2 |
| D6 | Boleta desconhecida continua `KeyError` | é o que `session.engine` já faz; mudar seria mexer na sessão |

**Correção ao que o planejador disse antes:** o gabarito das 18 perguntas da prova de uso
do M1 vai no **DL4-PR02**, porque depende dos três roteiros de BOVA11 que só existem lá.
O que este cartão antecipa é o V14: as seis perguntas respondidas só com o JSON, nas três
sessões oficiais.

## 10. Depois deste cartão

DL4-PR02: três roteiros sintéticos de trava de BOVA11 (calmo, cotação vencida, mercado
adverso), com o gabarito das 18 respostas escrito antes do GREEN e conferido por
`ticket_view`. O V3 já mostra que a fita `calmo` oficial produz cotação vencida em
14:00:19 sem mudar o simulador; a dúvida do §12 da blueprint está respondida.

Pendência separada, sem cartão aberto: as 4 falhas de `tests/integration` na `main`.
Precisam de cartão próprio antes do M4.

## Adendo 1

DL4-PR01 — Adendo 1, autorizado por Francisco em 25/11/2026. `ticket_view` não depende do contexto decimal do chamador. Em `view.py`, strike e preço-limite são quantizados a 0,01 com contexto explícito `Context(prec=MAX_PREC, Emin=MIN_EMIN, Emax=MAX_EMAX)`, como em `guards.py` e `sequencing.py`. Como `Money` já está no passo de 0,01, a quantização é exata e não escolhe arredondamento. Teste novo **V16**: na sessão `calmo`, passo 1, às 14:00:02, a visão gerada com precisão 3 (armadilhas padrão) e com precisão 3 sem a armadilha `InvalidOperation` é igual byte a byte à gerada no contexto padrão, com pior resultado `5.00` e melhor resultado `15.00`. **Mutante 25**: quantizar sem contexto explícito faz o V16 falhar. Contagem esperada: 28 testes focais e **11.685 aprovados, 16 pulados**. Nenhum outro arquivo muda. Depois, retomar os portões do §8.
