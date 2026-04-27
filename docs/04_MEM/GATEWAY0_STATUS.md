# Gateway-0 Sprint — Status para Retomada

> Arquivo gerado ao fim da sessão 2026-04-26.
> Leia este arquivo antes de qualquer operação git amanhã.

---

## Estado atual do repositório (crítico)

**Todos os branches apontam para o mesmo commit:** `e0ac81a` — RAG-07.
**Nenhum dos commits Gateway-0 foi gravado ainda.**
O trabalho existe no working tree como arquivos modificados/untracked mas **zero commits**.

### Por que?

`git index.lock` — Claude Code mantém o lock do git index durante sessões ativas.
O lock impede operações de staging e commit.

### Primeiro comando de amanhã (obrigatório)

```bash
rm /Users/fas/projetos/OPENCLAW/.git/index.lock
git status --short --branch   # confirmar que está limpo
```

---

## Todos os arquivos pendentes de commit (working tree atual)

### Modificados (M) — alterações sobre arquivos já commitados em RAG-07

| Arquivo | Pertence a |
|---|---|
| `.gitignore` | GW-03 |
| `backend/rag/generator.py` | GW-03 (routing + fix crítico) |
| `backend/rag/prompt_builder.py` | RAG-07 (shared validation import) |
| `config/rag_config.yaml` | GW-03 (endpoint + alias semântico) |
| `docs/04_MEM/AGENT_CONTEXT.md` | GW-03 (handoff session) |
| `docs/04_MEM/current_state.md` | GW-03 |
| `docs/04_MEM/decisions.md` | GW-03 |
| `docs/04_MEM/next_actions.md` | GW-03 |
| `scripts/rag_ask_local.py` | RAG-07 (shared validation) |
| `tests/unit/test_generator.py` | GW-03 (gateway client mocks) |

### Untracked (??) — arquivos novos, nunca commitados

| Arquivo/Dir | Pertence a |
|---|---|
| `backend/__init__.py` | GW-01 |
| `backend/gateway/` | GW-01 (config, health, errors, __init__) + GW-03 (client) + GW-04 (messages) |
| `config/litellm_config.yaml` | GW-01 |
| `docs/ADR/0001-litellm-as-initial-model-gateway.md` | GW-01 |
| `docs/GATEWAY_SETUP.md` | GW-03 |
| `docs/architecture/` | GW-01 |
| `docs/guides/` | GW-03 (OPENCLAW_LITELLM_RUNTIME.md) |
| `docs/sprints/` | GW-01 |
| `infra/` | GW-02 (litellm_config.yaml, start_litellm.sh, requirements.txt, README.md) |
| `scripts/__init__.py` | GW-01 |
| `scripts/check_litellm_gateway.sh` | GW-02 |
| `scripts/test_opencraw_litellm_runtime.sh` | GW-02/GW-04 (expandido) |
| `tests/smoke/test_gateway_runtime_smoke.py` | GW-04 |
| `tests/unit/test_gateway_client.py` | GW-03 |
| `tests/unit/test_gateway_config.py` | GW-01 |
| `tests/unit/test_gateway_errors.py` | GW-01 |
| `tests/unit/test_gateway_health.py` | GW-01 |
| `tests/unit/test_litellm_infra_scripts.py` | GW-02 |
| `uv.lock` | GW-01 (uv sync com dev deps PEP 735) |

---

## Sequência de commits para amanhã

```bash
cd ~/projetos/OPENCLAW
rm .git/index.lock   # ← obrigatório primeiro

# Confirmar branch
git checkout feat/gateway-route-opencraw-litellm
git status --short --branch

# ── COMMIT 1: GW-01 ──────────────────────────────────────────────────────────
git add \
  backend/__init__.py \
  scripts/__init__.py \
  backend/gateway/config.py \
  backend/gateway/health.py \
  backend/gateway/errors.py \
  backend/gateway/__init__.py \
  config/litellm_config.yaml \
  tests/unit/test_gateway_config.py \
  tests/unit/test_gateway_health.py \
  tests/unit/test_gateway_errors.py \
  docs/ADR/0001-litellm-as-initial-model-gateway.md \
  docs/architecture/ \
  docs/sprints/ \
  uv.lock

git commit -m "feat(gateway): GW-01 — Pydantic schema, semantic health checks, stable error taxonomy (closes #20)"

# ── COMMIT 2: GW-02 ──────────────────────────────────────────────────────────
git add \
  infra/ \
  scripts/check_litellm_gateway.sh

git commit -m "feat(gateway): GW-02 — LiteLLM operational config, start script, supply-chain guards (closes #21)"

# ── COMMIT 3: GW-03 ──────────────────────────────────────────────────────────
git add \
  backend/gateway/client.py \
  backend/rag/generator.py \
  backend/rag/prompt_builder.py \
  config/rag_config.yaml \
  .gitignore \
  docs/GATEWAY_SETUP.md \
  docs/guides/ \
  tests/unit/test_gateway_client.py \
  tests/unit/test_generator.py \
  scripts/rag_ask_local.py \
  docs/04_MEM/AGENT_CONTEXT.md \
  docs/04_MEM/current_state.md \
  docs/04_MEM/decisions.md \
  docs/04_MEM/next_actions.md

git commit -m "feat(gateway): GW-03 — route OpenClaw runtime through LiteLLM, validation-before-resource fix (closes #22)"

# ── COMMIT 4: GW-04 ──────────────────────────────────────────────────────────
git add \
  backend/gateway/messages.py \
  scripts/test_opencraw_litellm_runtime.sh \
  tests/smoke/test_gateway_runtime_smoke.py \
  docs/04_MEM/GATEWAY0_STATUS.md

git commit -m "feat(gateway): GW-04 — validate_chat_messages consolidation, observability, optional smoke tests"

# ── Push e PR ────────────────────────────────────────────────────────────────
git push origin feat/gateway-route-opencraw-litellm

gh pr create \
  --base main \
  --title "feat(gateway): Gateway-0 — LiteLLM routing, validation, infra, smoke tests (GW-01–04)" \
  --body "Implements full Gateway-0 sprint (GW-01 through GW-04).
Closes #20, #21, #22.

## Commits
- GW-01: Pydantic schema, health checks, stable error taxonomy
- GW-02: LiteLLM operational config, start script, supply-chain exclusions
- GW-03: GatewayChatClient + routing + validation-before-resource fix
- GW-04: validate_chat_messages consolidation + observability + smoke tests

## Validação
- 115/115 tests pass (2 skipped — smoke, expected)
- mypy --strict: 0 erros (40 files)
- pyright: 0 erros
- rg '_validate_messages': 0 resultados

## Pendente (GW-05)
- Per-alias timeout (local_think 120s vs local_chat)
- Embed routing via local_embed"

gh pr merge --merge --delete-branch

git checkout main
git pull --ff-only origin main
git log --oneline --decorate -5
```

---

## Resumo de cada PR (GW-01 a GW-04)

### GW-01 — Contratos e base do gateway
**Issue:** #20 | **Branch:** `feat/gateway-prep-contracts`

Cria os contratos de base antes de qualquer infraestrutura:
- `backend/gateway/config.py`: schema Pydantic v2 para `litellm_config.yaml`. Rejeita URLs não-localhost, exige 5 aliases obrigatórios (`local_chat`, `local_think`, `local_rag`, `local_json`, `local_embed`).
- `backend/gateway/health.py`: `check_gateway_services()` verifica Ollama rodando + modelos carregados (base-name matching para variantes quantizadas como `qwen3:14b-instruct-q4_K_M`).
- `backend/gateway/errors.py`: taxonomia estável de 8 exceções, todas subclasses de `GatewayError`, com `alias`/`provider` kwargs e `to_log_context()`.
- 35 testes (25 config + 10 health).
- `config/litellm_config.yaml`: config de referência com 5 aliases, URLs localhost hardcoded.

**Validação local:** 98/98 testes, mypy 0, pyright 0.

---

### GW-02 — Infraestrutura operacional LiteLLM
**Issue:** #21 | **Branch:** `feat/gateway-install-health`

Cria a camada operacional local do LiteLLM com guards de segurança:
- `infra/litellm/litellm_config.yaml`: usa `os.environ/OLLAMA_API_BASE` (não hardcoded). 5 aliases. `master_key` via env.
- `infra/litellm/start_litellm.sh`: recusa `LITELLM_HOST=0.0.0.0`, `OLLAMA_API_BASE` remoto, `LITELLM_MASTER_KEY` ausente. `set -euo pipefail`.
- `infra/litellm/requirements.txt`: `litellm[proxy]>=1.83.0,<2.0.0,!=1.82.7,!=1.82.8` (exclusões de supply chain — versões comprometidas no PyPI em março/2026).
- `infra/litellm/README.md`: inclui seção "Future Directions" documentando sequência de integração MCP.

---

### GW-03 — Routing do runtime OpenClaw → LiteLLM
**Issue:** #22 | **Branch:** `feat/gateway-route-opencraw-litellm`

Roteia todas as chamadas de geração pelo gateway:
- `backend/gateway/client.py`: `GatewayRuntimeConfig` (frozen dataclass com `.from_env()` e `.validated()`); `GatewayChatClient` (async httpx, mapeia erros para domain exceptions, api_key nunca aparece em exceções).
- `backend/rag/generator.py`: **fix crítico** — `.validated()` chamado antes de `httpx.AsyncClient()`. Sem o fix, ambientes com `ALL_PROXY=socks5h://` crashavam antes da validação da api_key.
- `config/rag_config.yaml`: `generation.endpoint` → gateway; `generation.model` → `local_rag`.
- `docs/guides/OPENCLAW_LITELLM_RUNTIME.md`: todos os 6 env vars, startup, troubleshooting.
- 4 testes com `MockTransport` — sem dependência de LiteLLM real.

---

### GW-04 — Consolidação, observabilidade e smoke tests opcionais
**Issue:** parte de #20 | **Branch:** `feat/gateway-runtime-smoke`

Fecha as pendências técnicas do sprint:
- `backend/gateway/messages.py`: `validate_chat_messages()` — função compartilhada. Elimina duplicação entre `client.py` e `generator.py`.
- `backend/gateway/client.py`: `_log_gateway_call()` emite `logger.debug` com alias, host (netloc only), latência, status, categoria de erro. Sem prompt, sem api_key.
- `scripts/test_opencraw_litellm_runtime.sh`: expandido para testar os 4 aliases com prompts sintéticos. Output truncado + comentário de dado sintético.
- `tests/smoke/test_gateway_runtime_smoke.py`: skipado por default; `RUN_LITELLM_SMOKE=1` para ativar. Testa 4 aliases + endpoint `/models`. Sem Qdrant, sem embeddings, sem dados reais.

**Validação:** 115/115 tests, 2 skipped (smoke, esperado). mypy 0, pyright 0.

---

## Issues criados hoje

| Issue | Título | Estado |
|---|---|---|
| #20 | [GW-01] Gateway contracts | open |
| #21 | [GW-02] Gateway infra | open |
| #22 | [GW-03] Gateway routing | open |

## Próximo sprint: GW-05

Pendências registradas:
1. Per-alias timeout: `local_think` (120s) vs `local_chat` (30s) — mesmo `timeout_seconds` global hoje.
2. Routing de embeddings via `local_embed`.
3. Integration test `LocalGenerator → GatewayChatClient` sem mocks.
