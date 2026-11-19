# Lab de Derivativos DL-PR05 - Cliente OpLab Market (allowlist, orcamento, erros)

Branches: `feat/dl-pr05a-oplab-routes-errors-budget` (Parte A) e
`feat/dl-pr05b-oplab-transport-client` (Parte B, empilhada sobre a A)
GitHub Issue: pendente (card READ-DO `DL-PR05_CARD.md` de 2026-11-06)
Status: Parte A implementada; Parte B em seguida

## Objective

Um cliente OpLab **somente Market, somente GET, somente HTTPS, somente host
exato e rotas enumeradas**, com transporte plugavel (fixture agora, HTTP
depois, mesmo contrato), orcamento de requisicoes por credencial, taxonomia
de erros que separa credencial/assinatura/permissao/limite/indisponibilidade,
`Retry-After` honrado sem retry, e procedencia atribuida pelo adaptador.
Tudo provado offline: nenhuma chamada real, nenhum token real.

Nao-objetivos: `ChainService` e latencia (PR06), MCP (PR07), rotas do
dominio de ordens, token em query string, cache, Redis, retries.

## Errata ao card: divisao em duas partes

O card previa um PR unico com producao <= 400 linhas e mandava parar e propor
divisao se passasse. A implementacao completa mediu **444 linhas** (97 + 73 +
72 + 141 + 61). Em vez de comprimir linhas, o PR foi dividido no corte
natural de dependencias:

| Parte | Modulos | Producao | Rede/token |
|---|---|---|---|
| A | `errors.py`, `routes.py`, `budget.py` | 242 linhas | nenhum `httpx`, nenhum token |
| B | `transport.py`, `client.py` | 202 linhas | unico ponto de `httpx` e `OPLAB_TOKEN` |

A Parte A e pura (sem I/O) e nao altera nenhuma fronteira existente. A Parte B
e a unica que relaxa a fronteira de `httpx` (so em `oplab/transport.py`).

## Parte A - Files

- `backend/derivatives/oplab/errors.py`: `OplabError` (so metadados seguros:
  `message_safe`, `status`, `route`, `retry_after_s`, `next_eligible_at`) e
  11 subclasses; `parse_retry_after` (segundos inteiros ou HTTP-date; ilegivel
  vira `None`); `classify_status` devolve a excecao tipada **sem levantar**.
- `backend/derivatives/oplab/routes.py`: `MarketRoute` (4 rotas),
  constantes `ALLOWED_METHOD/SCHEME/HOST`, `BASE_PATH`, `render_route`
  (`symbol` em `[A-Z0-9]{4,12}`; parametro ausente/desconhecido e recusa) e
  `assert_allowed` (dupla lista enum + YAML).
- `backend/derivatives/oplab/budget.py`: `credential_key` (SHA-256 dos 8
  primeiros caracteres), `RequestBudget` (janelas deslizantes por segundo e
  por minuto, `block_until`, `snapshot`), `BudgetSnapshot`.
- Testes: `test_oplab_routes.py`, `test_oplab_errors.py`,
  `test_oplab_budget.py`; tres fronteiras novas em
  `tests/architecture/test_derivatives_boundaries.py`.

## Parte A - Decisoes dentro do escopo

- **Allowlist positiva.** `assert_allowed` so aceita caminho que case, por
  `fullmatch`, com o padrao de uma rota do enum presente no YAML. Tudo o mais
  e recusa por construcao; nao ha lista de proibidos a manter em dia.
- **Dupla lista.** O YAML pode restringir (remover rota) e nunca ampliar:
  rota no YAML fora do enum nunca casa (`/market/options/bs` testado).
- **Dominio de ordens.** Alem da allowlist, qualquer segmento `domain`
  (qualquer caixa) e recusado explicitamente. O literal com barra nao aparece
  em codigo de producao; o teste de fronteira existente continua valendo.
- **Host exato.** Comparacao de `netloc` inteiro: porta, userinfo, sufixo,
  prefixo e caixa diferentes sao recusados (`ForbiddenHostError`).
- **Query e fragmento proibidos**, inclusive `?` vazio: nao ha parametro de
  query enumerado para nenhuma rota, e o token so viaja em header.
- **Mensagens de recusa nao ecoam a URL** (uma URL recusada pode conter
  segredo em query string).
- **429 sem `Retry-After` -> 300 s; 503 sem header -> 1 s** (limites
  publicados). `Retry-After` ilegivel (`1.5`, `-5`, texto) cai no mesmo
  bloqueio publicado, que e o lado conservador para 429.
- **Demais 5xx -> `UnavailableError` sem janela; 4xx nao mapeado ->
  `OplabError` base.** So 429/503 carregam `next_eligible_at`.
- **Orcamento nunca dorme.** `acquire` levanta `BudgetExceededError` com
  `next_eligible_at`; tentativa recusada nao consome orcamento; relogio que
  anda para tras e tratado de forma conservadora (conta como janela atual).
- **Uma instancia de `RequestBudget` por credencial**, criada pela raiz de
  composicao. Nao ha registro global de orcamentos nesta fase.

## Parte A - Acceptance evidence (Linux aarch64, Python 3.12.16, `uv.lock`)

- `QUIMERA_DERIV_FORBID_NETWORK=1 pytest tests/ --ignore=tests/integration`:
  rc 0, 7.873 passed, 15 skipped (com o JSON legado do Qwen3 presente e
  `docs/adr` resolvivel, como no checkout do Mac).
- `pytest tests/unit/derivatives tests/architecture`: 5.736 passed; coleta
  de `tests/unit/derivatives`: 5.704 (>= 1000).
- `mypy backend/ --strict`: 0 erros (147 arquivos); `pyright backend/`: 0.
- Producao da Parte A: 242 linhas novas; 0 linhas > 100 colunas.
- Protegidos intocados; nenhuma dependencia nova; `OPLAB_TOKEN` e `httpx`
  continuam ausentes de `backend/derivatives/` nesta parte.

## O que nao esta demonstrado

- Comportamento contra a API real (estado B): formatos reais de
  `Retry-After`, limites efetivos e corpo dos erros da OpLab.
- A base desta branch e `feat/dl-pr04-implied-vol` (`629df7e`), ainda nao
  mergeada em `main`; apos o merge do PR #131 a branch deve ser rebaseada.
