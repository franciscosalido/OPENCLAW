# Lab de Derivativos DL-PR01 - Vendor models OpLab, dominio normalizado e qualidade

Branch: `feat/dl-pr01-vendor-domain-quality`
GitHub Issue: pendente (card READ-DO de 2026-11-05 autoriza o PR diretamente)
Status: Initial SDD

## Objective

DL-PR01 transforma as respostas brutas da OpLab (modelos do fornecedor,
`extra="allow"`) em um dominio normalizado e imutavel (`extra="forbid"`,
`Decimal` para precos e strikes, datetimes sempre com fuso, zero distinto de
ausente), com flags de qualidade deterministicas e procedencia herdada
worst-of do carimbo do adaptador — sem precificacao, sem HTTP, sem MCP.

This PR does not implement BSM/IV/gregas (DL-PR02/03), transporte
HTTP/allowlist/orcamento (DL-PR04), `ChainService` e fixture sintetica
(DL-PR05), servidor MCP (DL-PR06), CLI (DL-PR07), persistencia, calendario de
feriados, dependencias novas, nem edicao em `CLAUDE.md`, `AGENTS.md`,
`.claude/` ou `pyproject.toml`.

## Files

- `backend/derivatives/oplab/{__init__,vendor_models}.py` — espelho literal
  da doc OpLab v3 (`VendorOption`, `VendorStock`, `VendorInterestRate`,
  `VendorMarketStatus`; `ConfigDict(extra="allow", frozen=True)`),
  `unknown_fields` e parsers com `VendorPayloadError` sanitizado (a mensagem
  nunca inclui o payload bruto).
- `backend/derivatives/domain/{__init__,models}.py` — enums (`OptionKind`,
  `ExerciseStyle`, `SpotSource`), `OptionContract`, `Quote` (+`mid`),
  `QualityFlags`, `SpotObservation`, `RateObservation`, `OptionRow`, `Chain`
  (`schema_version=quimera-derivatives-chain-v1`).
- `backend/derivatives/domain/quality.py` — `assess_quality` pura com `now`
  injetado e limiares do modelo `Quality` existente em
  `config/derivatives_config_model.py` (reutilizado, nao duplicado).
- `backend/derivatives/adapters/{__init__,normalize}.py` — `epoch_ms_to_datetime`,
  `money`, `quote_from_vendor`, `contract_from_vendor`, `spot_from_vendor`,
  `rate_from_vendor`, `normalize_chain`; warning unico por nome de campo
  desconhecido no escopo da chamada.
- `.gitignore` — exatamente uma linha nova: `.claude/settings.local.json`
  (estado local do Claude Code; `.claude/` em si permanece intocado).
- `tests/unit/derivatives/{conftest,test_vendor_models,test_normalize,test_quality,test_domain_models}.py`
  e extensao de `tests/architecture/test_derivatives_boundaries.py`.

## Decisions inside scope

- **`normalize.py` mora em `backend/derivatives/adapters/`**, nao no pacote
  de dominio: o card permitia as duas formas; em `adapters/` o teste de
  arquitetura fica uniforme (nada no pacote de dominio importa
  `backend.derivatives.oplab`, sem excecoes). O ADR-0023 lista `normalize` na
  arquitetura alvo sob o pacote de dominio; a localizacao fisica muda, o
  contrato nao.
- **`ProvenanceStamp` entra na `Chain` como dataclass stdlib validado
  nativamente pelo pydantic v2** (sem `arbitrary_types_allowed`, sem
  `TypeAdapter`): e a opcao mais simples que passa `mypy --strict`, e o
  `__post_init__` do dataclass continua rejeitando `captured_at` naive.
- **Errata do card (§3.7):** `epoch_ms_to_datetime(1620423900000)` e
  `2021-05-07T21:45:00+00:00`, nao `22:25:00` como o card afirmava
  (aritmetica verificada em sessao: 1620423900 s = 18754 dias + 78300 s).
  O teste fixa o valor correto.
- **`caplog` → sink loguru:** o repo nao tem bridge loguru→logging; o teste
  de "1 warning por nome" usa um sink de lista do proprio loguru, provando o
  mesmo comportamento.
- **Sem fallback `category`→`type` em `contract_from_vendor`:** `category` e
  obrigatorio no `VendorOption` (como na doc), logo o fallback seria codigo
  morto; `OptionKind(opt.category)` direto.
- **Formatacao compacta deliberada** nos 4 modulos novos (1 linha em branco
  entre blocos de topo, kwargs empacotados) para respeitar o teto de producao
  do card (A4 < 400 linhas); resultado: 396 linhas adicionadas em `backend/`.

## Acceptance

- A1 `pytest tests/ --ignore=tests/integration` rc 0; 81 testes coletados em
  `tests/unit/derivatives` (>= 60).
- A2 `mypy backend/ --strict` 0 erros; `pyright backend/` 0 erros.
- A3 diff vazio contra `main` em `CLAUDE.md`, `AGENTS.md`, `.claude/`,
  `pyproject.toml`, `uv.lock`; `.gitignore` com exatamente 1 linha nova.
- A4 producao (`backend/`) adicionada < 400 linhas (396).
- A5 nenhum `datetime.now(`/`utcnow(` em `backend/derivatives/` (teste de
  arquitetura fixa a regra).
- A6 nenhum artefato de `docs/rag/` ou `evaluation/` no diff.
- A7 fixture documental PETR3 normaliza com valores exatos: `bid=0.02`,
  `ask=None`, `last=None`, `strike=9.21`, `expiry=2021-05-21`, AMERICAN;
  spot `24.71` (STOCK_ENDPOINT) / `23.93` (OPTION_LAST_TRADE); SELIC com
  `compounding_assumed=True`; `purpose=test` herdado.

## Out of scope

BSM, IV, gregas, conversao monetaria, transporte HTTP, token, orcamento,
allowlist em runtime, `ChainService`, fixture sintetica, servidor MCP, CLI,
persistencia, calendario de feriados (o arquivo `config/b3_holidays_2026.yaml`
que apareceu no working tree durante a sessao fica fora deste PR).
