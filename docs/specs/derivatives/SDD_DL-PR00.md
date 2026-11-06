# Lab de Derivativos DL-PR00 - Fundacao (ADR-0023, provenance, config, fixtures)

Branch: `feat/dl-pr00-derivatives-foundation`
GitHub Issue: pendente (card READ-DO de 2026-11-05 autoriza o PR diretamente)
Status: Initial SDD

## Objective

DL-PR00 cria a fundacao do Laboratorio de Derivativos sem nenhuma logica de
mercado: ADR-0023 (Fase 1, aceito), ADR-0024 (reversao de corretora,
PROPOSED, nao assinado), pacote `backend/derivatives/` com procedencia e
configuracao de processo, par `config/derivatives.yaml` +
`config/derivatives_config_model.py`, fixtures documentais da OpLab v3 com
manifesto de hashes, backlog da fase e testes que fixam esses contratos.

This PR does not implement vendor models, normalizacao, BSM, IV, cliente
HTTP, servidor MCP, CLI, nenhuma dependencia nova e nenhuma edicao em
`CLAUDE.md`, `AGENTS.md`, `.claude/` ou `pyproject.toml`.

## Files

- `docs/adr/ADR-0023-laboratorio-derivativos-fase1.md` — decisoes 1-8,
  estados A/B/C, convencoes como hipoteses, barreira anti-fixture, seguranca
  do token, pendencias de homologacao.
- `docs/adr/ADR-0024-reversao-proibicao-corretora.md` — PROPOSED; so muda de
  estado com commit assinado por Francisco alterando `CLAUDE.md`.
- `docs/specs/derivatives/BACKLOG.md` — nao-objetivos da Fase 1 e itens
  nomeados fora de escopo.
- `backend/derivatives/{__init__,provenance,config}.py` — enums de
  procedencia/proposito/prontidao, heranca worst-of, `ProvenanceStamp`,
  dataclass de config de processo + loader com env injetavel,
  `forbid_network`.
- `config/derivatives.yaml` + `config/derivatives_config_model.py` —
  contrato declarativo validado (pydantic, `extra="forbid"`): convencoes,
  qualidade, orcamento, allowlist OpLab, parametros de IV.
- `tests/fixtures/derivatives/documental/` — 7 exemplos byte a byte da doc
  OpLab v3, `README.md` de origem/data e `manifest.json` com SHA-256.
- `tests/unit/derivatives/{test_provenance,test_config,test_fixtures_documental}.py`
  e `tests/architecture/test_derivatives_boundaries.py`.

## Acceptance

- A1 `pytest tests/ --ignore=tests/integration` rc 0; >= 15 testes coletados
  no escopo do Lab.
- A2 `mypy backend/ --strict` 0 erros; `pyright backend/` 0 erros; modelo de
  config verificado em separado se `config/` nao estiver no gate.
- A3 diff vazio contra `main` em `CLAUDE.md`, `AGENTS.md`, `.claude/`,
  `pyproject.toml`, `uv.lock`.
- A4 linhas de producao adicionadas (`backend/` + `config/*.py`) < 400.
- A5 ADR-0024 contem `PROPOSED` e nao contem a palavra reservada de aceite.
- A6 manifesto confere nos dois sentidos (disco <-> manifesto, hashes).
- A7 `backend/derivatives/` nao importa `httpx` (nenhuma rede possivel).

## Out of scope

Chamadas reais a OpLab, token, rotas de ordens, vendor models, normalizacao,
precificacao, IV, transporte HTTP, orcamento de requisicoes, servidor MCP,
CLI, fixture sintetica, protocolo de latencia, dependencias novas.
