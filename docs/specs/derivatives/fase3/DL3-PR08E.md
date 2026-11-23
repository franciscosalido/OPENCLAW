# DL3-PR08E — Supercartão: calendário oficial da B3 de 2027

**Data:** 23/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `fbf9c49` (DL3-PR08D e Adendo 1 da ADR-0024 integrados) · **PR novo**, em
rascunho
**Decisão que este cartão implementa:** autorização de Francisco de 22/11/2026 para a análise
de estruturas, item 3 («use o calendário da bolsa que rege o contrato»).

## 0. Escopo

Os três arquivos de calendário existem desde a Fase 1 (DL-PR02): 2026, 2027 e 2028. Mas o
pregão da B3 só está confirmado em 2026. Em 2027 as 365 linhas da B3 estão como `unknown`,
com uma projeção separada que o carregador nunca promove, à espera do calendário oficial.
Por isso, hoje, qualquer conta de dias úteis que entre em 2027 é recusada.

A B3 publicou o calendário de 2027 em 17/11/2026. **As 12 datas oficiais sem pregão são
exatamente as 12 da nossa projeção.** O próprio arquivo define o gatilho de promoção:
publicação oficial, reconciliação de todas as datas, nova revisão e validação do carregador.
Este cartão faz isso.

**Não há mudança de código.** O carregador já passa a cobrir 2027 quando nenhuma linha da B3
daquele ano estiver `unknown`.

**Fora deste cartão:** 2028 (segue `unknown`; a B3 não publicou); horário intradiário (a
Quarta-feira de Cinzas continua contando como dia útil inteiro); vencimentos semanais;
ligação do calendário com a estimativa; mudança de esquema ou do carregador. Nenhuma
dependência nova. Nenhum código de terceiros.

## 1. Arquivos

| Arquivo | O que muda |
|---|---|
| `config/calendars/b3_calendar_2027.yaml` | nova revisão (r4), conforme o §3 |
| `config/calendars/evidence_b3_oc_057_2026.pdf` | novo: o PDF oficial, sem alteração |
| `config/calendars/SHA256SUMS` | hash novo do arquivo de 2027 e linha do PDF novo |
| `config/calendars/README.md` | linha de 2027 e registro da conferência |
| `tests/unit/derivatives/test_calendar.py` | cinco testes mudam (§4.1) e nove entram (§4.2) |
| `docs/specs/derivatives/fase3/DL3-PR08E.md` | cópia deste cartão |

**Não muda:** `backend/` inteiro; os arquivos de 2026 e de 2028, byte a byte; o PDF de 2026;
a versão de esquema `3.0.0`; `current_state.md`; arquivos protegidos.

## 2. Fonte oficial

**Ofício Circular 057/2026-VNC**, de 17/11/2026: «Calendário de feriados em 2027 e
funcionamento da B3 em 10/02/2027 (Quarta-feira de Cinzas)». Publicado na página de ofícios
da B3. Lido pelo planejador em 23/11/2026:

`https://www.b3.com.br/data/files/30/44/54/98/ECAE1A108E6A2C1AAC094EA8/OC 057-2026-VNC CALENDARIO DE FERIADOS EM 2027 E FUNCIONAMENTO DA B3 EM 10022027 QUARTAFEIRA DE CINZAS_PT.pdf`

**Quadro A — dias sem sessão de negociação em 2027:**

| Data | Dia | Motivo |
|---|---|---|
| 01/01/2027 | sexta | Confraternização Universal |
| 08/02/2027 | segunda | Carnaval |
| 09/02/2027 | terça | Carnaval |
| 26/03/2027 | sexta | Sexta-feira Santa |
| 21/04/2027 | quarta | Tiradentes |
| 27/05/2027 | quinta | Corpus Christi |
| 07/09/2027 | terça | Independência |
| 12/10/2027 | terça | Nossa Senhora Aparecida |
| 02/11/2027 | terça | Finados |
| 15/11/2027 | segunda | Proclamação da República |
| 24/12/2027 | sexta | Véspera de Natal, sem sessão de negociação |
| 31/12/2027 | sexta | sem sessão de negociação |

- **Quadro B:** 25/01/2027 e 09/07/2027 têm pregão normal.
- **10/02/2027:** há pregão, com sessão contínua das 13h às 17h55. Conta como dia útil.
- 01/05, 20/11 e 25/12 caem em sábado em 2027 e não aparecem no quadro.

Baixe o PDF dessa URL, sem alterar os bytes. Registre tamanho, número de páginas e SHA-256.
Releia o Quadro A no PDF. **Se qualquer data diferir da tabela acima, pare e relate.**

## 3. A revisão r4 do arquivo de 2027

O modelo é o arquivo de 2026, que já descreve um ano oficial. Regras:

1. **Identidade e histórico.** `bundle_id` `quimera-calendars-2027-<AAAAMMDD>-r4`.
   `revision`: número 4, `supersedes_bundle_id` `quimera-calendars-2027-20261106-r3`,
   `previous_file_sha256`
   `eae6b7dadf91ba9c562c77cd39ca81f7d0ad058bacfffbd843664f35da5a947b`, e `change_summary`
   dizendo o que foi promovido e o resultado da reconciliação.
2. **Versão da B3.** `version_id` novo; `supersedes_version_id`
   `B3_LISTED_TRADING:2027:20261106:r1`; `evidence_state` `official_schedule`;
   `primary_source_id` `B3_OC057_2026`; `source_published_on` `2026-11-17`;
   `scheduled_business_days` 249; `projection_id` nulo.
3. **Dias da B3.** As 365 linhas de `calendar_day` da B3 deixam de ser `unknown`. Cada uma
   fica igual à linha da mesma data na projeção da r3, em todos os campos de
   `calendar_day`, menos `version_id`. Relate a reconciliação: 365 de 365.
4. **Projeção.** `calendar_day_projection` e `projection_registry` ficam vazios, como em
   2026. A r3 continua no histórico do Git.
5. **Evidência dos fechamentos.** As 12 linhas da B3 em `closure_evidence` passam a
   `evidence_state` `official`, `source_id` `B3_OC057_2026`, `inference` nulo.
6. **Catálogo.** Entra `B3_OC057_2026` em `evidence_catalog`: B3, documento oficial,
   publicado em 2026-11-17, a URL do §2 e o `content_sha256` do PDF.
7. **Auditoria do documento.** `source_document_audit` descreve o OC 057: número, data,
   páginas, bytes, SHA-256 e páginas relidas.
8. **Candidatos de vencimento.** As 24 linhas de `expiry_candidate` usam a versão nova da
   B3, com `candidate_state` `derived_from_published_rules` e `projection_id` nulo. As datas
   não mudam.
9. **Contexto de mercado.** Versão de contexto nova. `b3_is_trading_day` verdadeiro em 249
   dias e falso em 116. As colunas dos Estados Unidos não mudam.
10. **Aceite.** `b3_official_business_days` 249; `b3_projected_business_days` nulo;
    `expected_projection_rows` 0; `business_days_by_calendar.B3_LISTED_TRADING` 249.
11. **Preservação.** Ficam iguais à r3, como objetos lidos: a seção `contract`; as tabelas
    `calendar`, `dim_date`, `expiry_rule` e `calendar_event`; todas as linhas de
    `calendar_day` e de `calendar_version` das outras cinco identidades.
12. **Integridade.** Os quatro hashes de `integrity` são recalculados com as mesmas
    definições. Diga na descrição do PR a composição exata de `evidence_sha256`: o
    planejador reproduziu os outros três na r3, mas não esse.
13. **Formato.** O mesmo da r3: JSON estrito, um espaço de recuo, nova linha no fim.

O roteiro que gera a r4 fica fora do Git, nas evidências, com SHA-256 na descrição do PR.

## 4. Testes

Todos em `tests/unit/derivatives/test_calendar.py`, com o calendário real do repositório.

### 4.1 Testes existentes que mudam

Mudam só estes cinco. O protótipo do planejador confirmou que são os únicos afetados.

| Teste de hoje | O que passa a afirmar |
|---|---|
| `test_b3_2026_closed_weekdays_match_quadro_a` | compara só as datas de 2026 com o Quadro A de 2026 |
| `test_b3_coverage_is_only_2026` | cobertura da B3 é 2026 e 2027 (N4) |
| `test_b3_count_into_2027_raises_coverage_error` | a contagem que entra em 2027 funciona (N5); a recusa passa a ser a de 2028 (N4) |
| `test_b3_projection_2027_never_promoted_to_open_days` | vira o teste sintético N9 |
| `test_third_friday_out_of_coverage_refused` | a recusa passa a ser a de 2028 (N4) |

Renomeie quando o nome deixar de dizer a verdade.

### 4.2 Testes novos

**N1.** A B3 tem 249 dias abertos em 2027.

**N2.** Os fechamentos em dia de semana de 2027 são exatamente as 12 datas do Quadro A.

**N3.** São dia útil: 10/02/2027, 25/01/2027 e 09/07/2027. Não são: 24/12/2027 e
31/12/2027. Os sábados 01/05, 20/11 e 25/12/2027 não são dia útil e não entram em
`closed_weekdays`.

**N4.** `coverage_years` da B3 é `{2026, 2027}`. Levantam `CalendarCoverageError` citando
2028: `is_business_day` em 03/01/2028; `third_friday_preceding(2028, 1)`; a contagem de
20/12/2027 a 10/01/2028.

**N5 — contagens que atravessam o ano.**

| De | Até | `(D0,Dv]` | `[D0,Dv)` |
|---|---|---|---|
| 20/12/2026 | 10/01/2027 | 11 | 11 |
| 30/12/2026 | 04/01/2027 | 1 | 1 |
| 01/01/2027 | 31/12/2027 | 249 | 249 |
| 01/01/2026 | 31/12/2027 | 496 | 496 |

**N6 — quando incluir o dia inicial ou o final muda a conta.**

| De | Até | `(D0,Dv]` | `[D0,Dv)` |
|---|---|---|---|
| 05/02/2027 | 09/02/2027 | 0 | 1 |
| 05/02/2027 | 10/02/2027 | 1 | 1 |

**N7.** `third_friday_preceding` em 2027, de janeiro a dezembro: 15/01, 19/02, 19/03, 16/04,
21/05, 18/06, 16/07, 20/08, 17/09, 15/10, 19/11 e 17/12. Nenhuma recua.

**N8.** `time_to_expiry` de 23/11/2026 a 15/01/2027, com `Conventions()`: 35 dias úteis;
fração de ano 35/252; convenção `(D0,Dv]`; calendário `B3_LISTED_TRADING`; não é dia de
vencimento.

**N9 — a projeção nunca é promovida pelo carregador.** Arquivo sintético de um ano com
linhas da B3 `unknown` e uma projeção preenchida com dias abertos: `coverage_years` vazio e
`open_days` vazio.

## 5. Evidência do planejador

- **Fonte primária.** Li o OC 057/2026-VNC na página oficial. O Quadro A é o do §2.
- **Projeção da r3.** Os 12 fechamentos projetados em dia de semana são iguais aos 12
  oficiais, e a projeção tem 249 dias abertos.
- **Protótipo descartável.** Promovi as 365 linhas no arquivo de 2027 e rodei o portão sem
  integração: só os cinco testes do §4.1 mudam de resultado.
- **Dois caminhos para os esperados.** Um oráculo de datas puro (dias de semana menos os
  fechamentos oficiais) e o módulo real sobre o protótipo deram os mesmos números em todas
  as verificações do §4.2.
- **Segunda conferência.** A biblioteca `exchange_calendars` 4.13.3, calendário BVMF, fora
  do repositório: 247 sessões em 2026 e 249 em 2027, as mesmas datas dos quadros oficiais.
- **Hashes internos da r3.** Reproduzi `contract_sha256`, `data_sha256` e
  `envelope_sha256`.

## 6. Mutantes obrigatórios

Um por vez, sobre o arquivo de 2027 ou o carregador, com o `SHA256SUMS` ajustado quando o
mutante for de dados. Cada um derruba ao menos um teste.

1. 27/05/2027 marcado como aberto (N1, N2).
2. 10/02/2027 marcado como fechado (N1, N3).
3. 25/01/2027 marcado como fechado (N1, N3).
4. 24/12/2027 marcado como aberto (N1, N3).
5. Uma linha da B3 de 2027 de volta a `unknown` (N4).
6. As linhas da B3 de 2028 promovidas a dias de semana abertos (N4).
7. Arquivo de 2027 alterado sem atualizar o `SHA256SUMS` (carga recusada).
8. Carregador promovendo a projeção quando o ano está `unknown` (N9).
9. Carregador contando o dia inicial em `(D0,Dv]` (N6).

## 7. Critérios de parada

Pare e relate se:

- o PDF baixado não trouxer exatamente as 12 datas do §2;
- alguma linha da projeção da r3 diferir do oficial;
- algum esperado do §4 não reproduzir;
- outro teste, além dos cinco do §4.1, mudar de resultado;
- qualquer arquivo de `backend/`, ou os arquivos de 2026 e de 2028, precisar mudar;
- o esquema do próprio arquivo, ou as suas restrições de referência, impedirem alguma regra
  do §3.

## 8. Entrega

1. Um commit com dados, evidência e testes. A prova de força é a tabela de mutantes.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
   `tests/integration` só no contêiner isolado.
3. Descrição do PR: cabeça, contagens, SHA-256 do PDF e do arquivo novo, a reconciliação
   365 de 365, os 9 mutantes, a composição de `evidence_sha256`, desvios.
4. Copie este cartão para o caminho do §1. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Com um conferidor
próprio, compara a r4 com a r3 (regra 11 do §3), recalcula os hashes internos, confere as
linhas da B3 com o Quadro A e com a `exchange_calendars`, e confere o hash do PDF nos três
lugares em que ele aparece.

## 9. Depois deste cartão

A frente de análise de estruturas fica com o limite de escala pendente. PR07A3, PR07A4 e
PR07B seguem na fila, e depois deles o cartão da margem (Adendo 1 da ADR-0024).
