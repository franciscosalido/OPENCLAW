# DL3-PR07E1 — Supercartão: formato versionado do recibo e do resumo, e esquema de saída da prévia

**Data:** 24/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `6b8d09c` (DL3-PR07D1 integrado)
**PR novo**, em rascunho. **Último cartão da Fase 3 estendida.**
**Decisões que este cartão implementa:**

- Francisco, 23/11/2026 (Texto 1 de `DECISOES_POS_PR07A3C_2026-11-23.md`): para o JSON,
  **«corrigir antes do primeiro consumidor externo da prévia»**; e «quem define o JSON que
  representa a prévia autorizada pelo Francisco?» — **«o QUIMERA»**, em **«contrato
  versionado»**.
- Lição registrada na revisão do DL3-PR07A3D: o formato do recibo mudou sem número de
  versão, e o leitor novo passou a recusar recibos gravados antes. Versão de formato antes
  de existir dado real.
- Francisco, 24/11/2026: fechar a Fase 3 estendida.

## 0. Escopo

**O que acontece hoje.** Fatos conferidos no `main`:

- O esquema de saída da prévia, `Preview.model_json_schema(mode="serialization")`, é
  `{"additionalProperties": true, "type": "object"}`. Não descreve campo nenhum. A causa é o
  serializador que omite a cobertura vazia.
- As linhas do recibo gravadas pelo script e o `resumo.json` não trazem versão de formato.
  Nos últimos cartões o resumo ganhou chaves (fatos externos, rótulo, pernas) e o recibo
  mudou de valor (projetado), sempre sem número.
- Não existe leitor das linhas gravadas. Quem quiser conferir um arquivo de recibo tem de
  remontar os eventos à mão.

**O que este cartão entrega.**

1. **Esquema de saída da prévia** com os campos enumerados, e um arquivo de esquema
   versionado no repositório, preso por teste ao que o código gera.
2. **Versão de formato** em cada linha de recibo e no resumo. Começa em 1.
3. **Leitor das linhas do recibo**, que recusa formato desconhecido, linha alterada e cadeia
   quebrada, e confere a âncora quando ela é informada.

**O que este cartão não faz.**

- **Não muda nenhuma âncora.** A versão fica no envelope da linha, fora do conteúdo
  encadeado. Os quatro hashes de recibo são os de hoje.
- Não cria esquema para o resumo nem para os eventos do recibo além da prévia. O resumo
  ganha só o número; o esquema dele vem quando houver consumidor.
- Não cria migração de formato antigo: não existe recibo real gravado.
- Não muda motor, livro, sessão (fora uma chave), plano nem regra de negócio.
- Não toca em `pyproject.toml` nem em `uv.lock`.

Nenhuma dependência nova.

## 1. Referência externa

| Fonte | O que sustenta aqui |
|---|---|
| FIX, `ApplVerID` (1128): a versão da aplicação é informada no cabeçalho e vale para cada ocorrência de mensagem (<https://fiximate.fixtrading.org/en/FIX.Latest/msg40.html>) | a versão vai no envelope de **cada linha**, não uma vez por arquivo nem dentro do conteúdo |
| Fórum da FIX Trading Community sobre exigir `ApplVerID` em toda mensagem: dispensa manter estado da versão (<https://forum.fixtrading.org/t/require-applverid-on-all-fixt-messages/5022>) | o leitor decide linha a linha, sem depender de contexto |
| FIX, relatório de execução: `OrderQty = CumQty + LeavesQty`, com saldo zero em ordem morta (<https://www.onixs.biz/fix-dictionary/4.3/msgtype_8_8.html>) | já adotado no DL3-PR07D1; é o conteúdo que o formato 1 congela |
| OIC e FINRA, *Understanding Assignment*: numa estratégia de várias pernas, uma perna pode ser exercida sozinha, e cabe ao investidor agir sobre a perna que limita o risco (<https://www.optionseducation.org/news/trading-options-understanding-assignment>) | justifica o registro de fato externo (`exercise`) fazer parte do formato 1 |
| OIC, *Exercising Options*: a designação pode ocorrer dias ou semanas antes do vencimento (<https://www.optionseducation.org/optionsoverview/exercising-options>) | idem: o fato pode chegar com a boleta em execução |

**Não verificado pelo planejador:** a página `fixtrading.org/guidelines/post-trade/` e a
página inicial `optionseducation.org`. A leitura direta não foi autorizada nesta sessão,
em duas tentativas. As fontes acima vieram por busca. As diretrizes de pós-negociação do
FIX tratam de alocação e confirmação entre instituições, que não existem no simulador; o
cartão não depende delas.

## 2. Arquivos e tetos

| Arquivo | O que muda | Teto (hoje) |
|---|---|---|
| `backend/derivatives/ticket/models.py` | cobertura vazia omitida pelo campo, não pelo serializador | 220 (220) |
| `backend/derivatives/ticket/receipt.py` | `RECEIPT_FORMAT`, `dump_rows`, `load_rows` | 196 (150) |
| `backend/derivatives/ticket/session.py` | `SUMMARY_FORMAT` e a chave `formato` | 183 (179) |
| `scripts/derivatives_ticket_replay.py` | grava as linhas com `dump_rows` | 243 (243) |
| `docs/specs/derivatives/fase3/schemas/previa.schema.json` | **novo**: o esquema de saída | — |
| `tests/unit/derivatives/ticket/test_state_receipt.py` | V2 a V4 | — |
| `tests/unit/derivatives/ticket/test_models.py` | V1 | — |
| `tests/unit/derivatives/test_ticket_replay_script.py` | três esperados atualizados | — |
| `docs/specs/derivatives/fase3/DL3-PR07E1.md` | cópia deste cartão | — |

**Não muda:** `engine.py`, `sequencing.py`, `state.py`, `digest.py`, os demais módulos,
roteiros e fitas, `current_state.md`, arquivos protegidos. Linhas novas com até 100 colunas.

**Testes existentes que mudam: três, e só eles** — `test_complete_replay[calmo]`,
`[leilao]` e `[rapido]`. As linhas do recibo ganham `"formato":1` e o resumo ganha
`"formato": 1`. Os hashes dos eventos e as quatro âncoras ficam iguais.

## 3. Regra

### 3.1 Esquema de saída da prévia (`models.py`)

O campo `coverage` passa a se omitir sozinho quando vazio
(`Field(..., exclude_if=...)`), e o serializador de modelo que fazia isso sai. O corpo
gravado da prévia continua idêntico, byte a byte: cobertura vazia não aparece; cobertura
com autorizações aparece, ordenada.

Com isso o esquema de saída enumera os campos, com `additionalProperties` falso.

**Arquivo de esquema.** `previa.schema.json` é exatamente
`json.dumps(Preview.model_json_schema(mode="serialization"), sort_keys=True, indent=2,
ensure_ascii=False)` mais uma quebra de linha. SHA-256 esperado, com o pydantic travado no
`uv.lock` (2.13.3): `04108cb0c5ecdb33f20608916c86ae12e3c34b5bd48ca272dda7afcae93d6e31`.

`exclude_if` existe a partir do pydantic 2.12. O `uv.lock` trava 2.13.3; o `pyproject.toml`
declara piso 2.10 e é arquivo protegido. Não o altere: relate na descrição do PR.

### 3.2 Formato do recibo (`receipt.py`)

- **`RECEIPT_FORMAT = 1`**.
- **`dump_rows(receipt) -> Iterator[str]`** — uma linha por evento, JSON canônico (chaves
  ordenadas, sem espaços, UTF-8 sem escape), com exatamente as chaves `formato`, `hash`,
  `kind`, `payload`, `prev_hash`, `seq`, `ts`. É a linha de hoje com `formato` a mais.
- **`load_rows(lines, *, expected_head=None) -> tuple[ReceiptEvent, ...]`**. Recusas, todas
  `ReceiptError`:

| Situação | Mensagem |
|---|---|
| linha que não é objeto JSON; chave a mais ou a menos; linha diferente da forma canônica; `seq`, `ts` ou `payload` de tipo errado; `kind` ou `ts` ilegível | «linha de recibo inválida» |
| `formato` que não é o inteiro `RECEIPT_FORMAT` (inclui booleano, texto, fracionário, nulo) | «formato de recibo desconhecido» |
| nenhuma linha; cadeia que não verifica; âncora informada diferente da última | «recibo vazio, adulterado ou incompleto» |

A verificação da cadeia é a de `Receipt.verify`, inclusive a releitura das prévias. Sem
`expected_head`, um recibo truncado no fim é aceito: só a âncora externa detecta
truncamento, como o `Receipt` já documenta.

### 3.3 Resumo (`session.py`) e script

- **`SUMMARY_FORMAT = 1`**; `summary()` ganha a chave `"formato"` com esse valor.
- O script grava os recibos e o arquivo de fatos com `dump_rows`.

## 4. Cenários

**V1 — o esquema de saída descreve a prévia.**

- `type` `object`; `additionalProperties` falso.
- Propriedades, em ordem alfabética: `coverage`, `digest`, `environment`, `gross_cap`,
  `legs`, `net_limit`, `order_validity`, `partial_exposure`, `quote_snapshot_id`,
  `send_deadline`, `version`.
- `required`: `legs`, `net_limit`, `gross_cap`, `send_deadline`, `order_validity`,
  `quote_snapshot_id`, `partial_exposure`, `digest`.
- Em `$defs`: `Leg` com `additionalProperties` falso; `CoverageGrant` com `required`
  `series`, `origin`, `quantity`.
- O esquema de saída de `TicketDraft` também tem `additionalProperties` falso.
- O arquivo do §2 é igual ao texto gerado.

**V2 — as três sessões oficiais vão e voltam.** Para `calmo`, `leilao` e `rapido`:

- `resumo.json` tem `"formato": 1`;
- toda linha de recibo tem `formato` 1 e exatamente as sete chaves;
- `load_rows` com a âncora da boleta devolve os eventos; o último hash é a âncora e a
  quantidade é o `recibo_eventos` do resumo;
- sem a última linha: com a âncora, «recibo vazio, adulterado ou incompleto»; sem a âncora,
  aceito com uma linha a menos.

Âncoras: `calmo` T1 `1d50bba6…`; `leilao` T1 `8592cd74…`; `rapido` T1 `9ebc9cd5…`;
`rapido` T2 `fbcaafa8…`. As quatro iguais às de hoje.

**V3 — o leitor recusa.** Sobre o recibo de `calmo`:

| Alteração | Mensagem |
|---|---|
| `formato` da primeira linha em 2, 0, `"1"`, `true`, `1.0`, `null` | «formato de recibo desconhecido» |
| linha sem `formato`; com chave `extra`; com espaço no fim; com `"formato": 1` (espaço); `[]`; `{`; vazia | «linha de recibo inválida» |
| segunda linha com `kind` `nope`; `ts` `ontem`; `seq` `"2"`; `payload` 3 | «linha de recibo inválida» |
| segunda linha com `seq` 5; `ts` um segundo depois; `kind` `stop`; `prev_hash` zerado; `payload` com `T1` trocado por `T2` | «recibo vazio, adulterado ou incompleto» |
| nenhuma linha; duas primeiras linhas trocadas; `ts` da primeira sem fuso | «recibo vazio, adulterado ou incompleto» |

**V4 — a linha só ganhou uma chave.** No recibo da T1 de `rapido`, cada linha começa por
`{"formato":1,"hash":"` e, tirando `formato`, é idêntica à linha canônica de hoje.

## 5. Evidência do planejador

- **Fatos de hoje.** Conferidos no `main` `6b8d09c`, inclusive o esquema genérico.
- **Protótipo descartável:** `receipt.py` com 191 linhas (41 a mais), `session.py` com 181
  (2 a mais), `models.py` com 212 (8 a menos), o script com 239 (4 a menos). `mypy --strict`
  limpo em `backend/` e no script; `pyright` limpo no pacote da boleta.
- **Portão completo no protótipo** (sem `tests/integration`): 11.594 aprovados e 3
  reprovados, que são exatamente os três testes do §2, antes de atualizados. Com a troca do
  serializador, os 643 testes da boleta e do script passaram sem tocar em âncora.
- **Cenários:** V1 a V4 passam no protótipo. No `main` todos falham.
- **Mutantes:** 13 defeitos plantados, um por vez, todos detectados (§6).

## 6. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, quem derrubou no
protótipo.

1. A linha sai sem o formato (V2, V3, V4).
2. O leitor aceita qualquer formato (V3).
3. O leitor aceita formato booleano ou fracionário (V3).
4. O leitor aceita chave a mais ou a menos (V3).
5. O leitor aceita linha não canônica (V3).
6. O leitor não confere a cadeia (V2, V3).
7. O leitor ignora a âncora esperada (V2).
8. O leitor aceita recibo vazio (V3).
9. O leitor aceita `seq` como texto (V3).
10. O resumo sai sem o formato (V2).
11. O esquema de saída volta a ser genérico (V1).
12. A cobertura vazia passa a sair na prévia (V2 e testes existentes: muda o digest).
13. A cobertura some sempre (V1 e testes existentes).

## 7. Critérios de parada

Pare e relate se:

- algum esperado do §4 não reproduzir, inclusive o SHA-256 do arquivo de esquema;
- alguma âncora ou hash de evento mudar;
- qualquer teste existente mudar de resultado, fora os três do §2;
- o corpo gravado de alguma prévia mudar em um byte;
- for preciso mudar arquivo de produção fora do §2, tocar em arquivo protegido, ou algum
  teto estourar.

## 8. Entrega

1. Commit vermelho com os testes; depois o verde. Envie o vermelho ao GitHub antes do
   verde.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
   `tests/integration` só no contêiner isolado, nunca no Mac com banco vivo.
3. Descrição do PR: cabeça, contagens, linhas dos quatro arquivos, os 13 mutantes, os três
   testes atualizados, os hashes de evento das sessões oficiais comparados com a base, a
   versão do pydantic usada, desvios.
4. Copie este cartão para o caminho do §2. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda os cenários do
seu protótipo contra os módulos entregues.

## 9. Depois deste cartão

**A Fase 3 estendida termina aqui.** O que fica são frentes novas, cada uma abrindo com
decisão de Francisco, e nenhuma é continuação obrigatória:

- repetir, completar e ajustar estruturas;
- histórico persistente, com a conferência da foto nova;
- foto com quantidade por par;
- limite de escala; modalidade B de garantia;
- esquema do resumo, quando houver consumidor.

Regra a partir de agora: mudança de formato do recibo ou do resumo sobe o número e diz o
que mudou.

## Adendo autorizado por Francisco — 24/11/2026

Em V2, sem âncora, retirar a última linha é aceito se restar ao menos um evento.
Se o recibo ficar vazio, o leitor o recusa, com ou sem âncora. Isso inclui T2 de `rapido`.
