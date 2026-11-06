# Lab de Derivativos DL-PR02 - Calendarios 3.0.0, dias uteis e convencoes temporais

Branch: `feat/dl-pr02-calendar-conventions`
GitHub Issue: pendente (card READ-DO de 2026-11-06 autoriza o PR diretamente)
Status: Initial SDD

## Objective

DL-PR02 da ao Lab uma nocao de tempo auditavel: carrega os bundles de
calendario 3.0.0 (`config/calendars/`) uma vez por processo, conta dias
uteis entre datas com convencao explicita e recusa do desconhecido
(`CalendarCoverageError`), converte contagem em fracao de ano e taxa em
continua, e deriva o candidato de vencimento mensal (3a sexta civil,
*preceding*) — tudo offline, deterministico, sem precificar nada.

This PR does not implement BSM/gregas (DL-PR03), IV (DL-PR04), cliente HTTP
(DL-PR05), persistencia em PostgreSQL, calendarios dos EUA/SIFMA/Fedwire
(Fase 2), `market_context_day`, Qlib, nem altera o formato dos YAMLs.
Renumeracao decidida em 2026-11-06: o antigo DL-PR02 (BSM + gregas) foi
dividido — DL-PR02 = tempo, DL-PR03 = BSM + gregas, DL-PR04 = IV, DL-PR05 =
cliente OpLab, DL-PR06 = ChainService + latencia, DL-PR07 = servidor MCP,
DL-PR08 = CLI (opcional).

## Files

- `config/calendars/` — versionado byte a byte neste PR: 3 bundles 3.0.0
  (2026-2028), PDF de evidencia OC 041/2026 (errata), `SHA256SUMS`,
  `README.md` (uma linha adicionada registrando o versionamento).
- `config/derivatives_config_model.py` + `config/derivatives.yaml` —
  `Conventions` perde `holidays_file` (sem consumidor) e ganha
  `calendars_dir`, `trading_calendar_id`, `financial_calendar_id`,
  `day_count_calendar`(+`_assumed`), `interval_convention`(+`_assumed`) e
  `year_basis` (252|365).
- `backend/derivatives/pricing/{__init__,calendar}.py` — `CalendarId`,
  `CalendarError`/`CalendarCoverageError`/`CalendarIntegrityError`,
  `TradingCalendar` (dataclass congelado), `load_calendar_bundle` (JSON
  estrito: chave duplicada e NaN/Infinity recusados; `schema_version` e
  `year` conferidos; SHA-256 opcional), `build_calendar` (ano com qualquer
  `unknown` fica inteiro fora da cobertura; projecao lida e ignorada com
  log), `load_calendars`, `business_days_between` (bissecao, sem laco
  diario), `is_business_day` (recusa fora da cobertura, nunca `False` por
  desconhecimento), `third_friday_preceding`.
- `backend/derivatives/pricing/conventions.py` — `year_fraction`,
  `continuous_rate`, `TimeToExpiry` + `time_to_expiry`,
  `model_assumptions` (chaves que `Chain.model_assumptions` carrega).
- `tests/unit/derivatives/{test_calendar,test_conventions}.py`, extensao de
  `test_config.py` e `tests/architecture/test_derivatives_boundaries.py`;
  fixture sintetica `tests/fixtures/derivatives/calendars_bad/`.

## Decisions inside scope

- **`json.load` estrito, nunca `yaml.safe_load`:** os bundles 3.0.0 sao JSON
  estrito dentro de `.yaml`; `json` le cada um em dezenas de ms, `yaml`
  levaria ~2 s por arquivo. Teste de arquitetura proibe `import yaml` em
  `pricing/`.
- **Hash da fonte anexado ao bundle carregado:** `load_calendar_bundle`
  grava o SHA-256 dos bytes lidos na chave reservada `_source_sha256` do
  dicionario devolvido; `build_calendar` a propaga para
  `TradingCalendar.source_sha256`. Bundles sinteticos de teste sem a chave
  continuam validos (tupla fica vazia).
- **`version_ids` registram o que foi lido, nao o que entrou na cobertura:**
  um ano inteiramente `unknown` (B3 2027/2028) fica fora de
  `coverage_years`, mas sua `version_id` permanece na proveniencia do
  calendario construido.
- **Tupla ordenada por chamada em `business_days_between`:** a ordenacao de
  `open_days` (<= ~750 datas) e feita na chamada; sem cache global implicito,
  coerente com "o objeto e passado adiante".
- **`third_friday_preceding` com recuo limitado a 31 dias:** evita laco
  infinito em calendario sintetico degenerado; o recuo real da B3 e de 1-3
  dias.
- **Errata do card (§A1):** o card estimava "hoje ~117" testes coletados em
  `tests/unit/derivatives`; a base real pos-DL-PR01 era 81 (registrada em
  `docs/04_MEM/current_state.md`). O alvo de coleta >= 150 foi mantido e
  atingido com testes substantivos adicionais (159 coletados), nao com
  enchimento.
- **Hashes canonicos internos (`integrity.*_sha256`) nao verificados:** a
  especificacao de canonizacao dentro do arquivo nao foi validada como
  inequivoca; item nomeado no BACKLOG. A integridade externa e dada pelo
  `SHA256SUMS` (shasum) e pelo parametro `expected_sha256`.

## Acceptance evidence

- `pytest tests/ --ignore=tests/integration` rc 0; coleta de
  `tests/unit/derivatives` >= 150.
- `mypy backend/ --strict` 0; `pyright backend/` 0;
  `mypy config/derivatives_config_model.py --strict` 0.
- `shasum -a 256 -c SHA256SUMS` OK apos o commit (nenhum byte alterado nos 3
  YAMLs nem no PDF).
- Os 14 fechamentos de seg-sex de 2026 (Quadro A do OC 041/2026) aparecem
  literalmente em `test_b3_2026_closed_weekdays_match_quadro_a` e batem com
  `closed_weekdays`.
- Producao <= 300 linhas (`backend/` + `config/derivatives_config_model.py`).
