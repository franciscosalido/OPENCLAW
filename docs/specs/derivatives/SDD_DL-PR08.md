# Lab de Derivativos DL-PR08 - CLI fino `quimera chain`

Branch: `feat/dl-pr08-cli` (empilhada sobre `review/fase01-claude-dots`)
GitHub Issue: pendente (item opcional do prompt v1 §7; pedido por Francisco
em 2026-11-19)
Status: implementado; aguarda PR e revisao

## Objective

Uma segunda porta, de terminal, para as **mesmas** funcoes que atendem as
tools MCP. O CLI nao tem logica propria: despacha para `chain_tool` ou
`demo_tool` e escreve a resposta como um unico documento JSON em stdout.

```bash
uv run quimera chain BOVA11 2026-11-19 --provider offline_fixture   # demo, exit 0
uv run quimera chain BOVA11 2026-11-19                              # live, exit 3
uv run python -m backend.derivatives.cli chain BOVA11 2026-11-19    # sem o script
```

Nao-objetivos: novos subcomandos (`estrutura`, `holding`), provedor ao vivo,
framework de CLI, saida tabular, escolha de diretorio de fixture.

## Files

- `backend/derivatives/cli.py` (70 linhas): `build_parser`, `run_chain`,
  `exit_code`, `main(argv, *, clock)`, `run` (ponto de entrada do console).
- `pyproject.toml`: `[project.scripts] quimera = "backend.derivatives.cli:run"`.
  E a unica mudanca em arquivo protegido da Fase 1, prevista no plano
  somente para este PR; nenhuma dependencia entra e `uv lock --check` passa.
- Testes: `test_cli.py` (23) e uma fronteira nova de arquitetura.

## Contrato

| Chamada | Resposta em stdout | Exit |
|---|---|---|
| `--provider offline_fixture`, entrada valida | envelope da demo, `DEMO_TEST_DATA`, `purpose=test` | 0 |
| `--provider live` (padrao) | `LIVE_NOT_ACTIVATED`, sem cotacao | 3 |
| demo com data/simbolo invalidos ou fora da fixture | `ok=false` + codigo constante | 1 |
| uso invalido (argumento a mais, opcao inexistente) | nada em stdout; uso em stderr | 2 |

## Decisoes dentro do escopo

- **Padrao e `live`.** Sem a flag, o CLI nunca serve fixture; e resposta sem
  cotacao nunca e exit 0, para um script nao confundi-la com dado.
- **A flag e o opt-in do operador.** No MCP a demo depende do ambiente do
  processo porque quem chama e um agente; no terminal quem chama e o
  operador, e a flag explicita cumpre o mesmo papel. A saida continua
  rotulada `DEMO_TEST_DATA` / `synthetic` / `test`.
- **Sem opcao de caminho, URL, token ou diretorio.** A fixture e a captura
  versionada e verificada por hash (`DemoFixture`); um teste de arquitetura
  proibe essas opcoes no modulo.
- **Reuso direto das funcoes das tools.** A saida do CLI e identica, byte a
  byte apos o parse, a resposta de `derivatives_chain_demo`. Custo: importar
  o modulo do servidor (~0,4 s no boot); beneficio: uma unica barreira.
- **`main` nao mexe em logging; `run` sim.** O ponto de entrada do console
  limita o loguru a WARNING em stderr. Chamadas em processo (testes) nao
  alteram os handlers globais.
- **`argparse`**, sem framework e sem `print`.

## Acceptance evidence (Linux aarch64, Python 3.12.16, `uv.lock`)

- `quimera chain BOVA11 2026-11-19 --provider offline_fixture`: JSON valido
  em stdout (100 linhas, ~67 KB), stderr vazio, exit 0.
- `pytest tests/ --ignore=tests/integration` sobre `origin/main` `aec9b8e`:
  rc 0, 8.081 passed, 15 skipped; arvore limpa apos a suite. Lab +
  arquitetura: 5.944 passed em 3 ordens.
- `mypy backend/ --strict`: 0 erros (156 arquivos); `pyright backend/`: 0.
- Producao: 70 linhas (<= 400); 0 linhas > 100 colunas.

## O que nao esta demonstrado

- `uv run quimera ...` com o script instalado no ambiente do Mac (aqui foi
  exercitado `python -m backend.derivatives.cli`; o teste confere que a
  entrada do `pyproject.toml` aponta para um callable importavel).
- Colisao do nome `quimera` com outro executavel no PATH do Mac.
