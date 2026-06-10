# Runbook — code-sandbox-mcp ("Server disconnected" no Claude Desktop)

> Última verificação: 2026-06-10 · macOS arm64 · binário `v1.0.0` em
> `/Users/fas/.local/share/code-sandbox-mcp/code-sandbox-mcp`

## Sintoma

Claude Desktop mostra **"Server disconnected"** para `code-sandbox-mcp`. O log MCP traz:

```
Warning  Failed to check for updates — Get https://api.github.com/.../releases/latest: dial tcp ...:443 i/o timeout
Server transport closed unexpectedly, this is likely due to the process exiting early.
```

## Causa raiz (confirmada)

O binário faz **auto-update check** contra `api.github.com` na inicialização.
Quando `api.github.com` está inacessível (timeout/firewall/rede), o processo
**morre antes de completar o handshake MCP** → "process exiting early".

Diagnóstico que confirma o bloqueio seletivo do host:

```bash
curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" --max-time 8 https://github.com       # 200, ~0.2s
curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" --max-time 15 https://api.github.com   # 000, timeout
```

A resposta `protocolVersion: "2024-11-05"` do servidor (mesmo quando o cliente
pede `2025-11-25`) **NÃO é o problema** — é a negociação/downgrade normal do
MCP, que o Claude Desktop aceita.

## Correção

Adicionar a flag `-no-update` aos `args` em
`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
"code-sandbox-mcp": {
  "command": "/Users/fas/.local/share/code-sandbox-mcp/code-sandbox-mcp",
  "args": ["-no-update"],
  "env": { "DEFAULT_IMAGE": "openclaw-sandbox", "WORKSPACE_PATH": "/Users/fas/projetos/OPENCLAW" }
}
```

Depois: **Cmd+Q no Claude Desktop e reabrir** (o config só recarrega no boot).

### ⚠️ Armadilhas

- **Env vars não resolvem.** `NO_UPDATE_CHECK` / `DISABLE_UPDATE_CHECK` / `UPDATE_CHECK`
  são ignoradas — o binário é Go e só lê a flag CLI `-no-update` (um traço só).
- Flags válidas do binário: `-install`, `-no-update`. Não existe `--version`.
- Não precisa de upgrade do binário; e não dá para baixar release nova enquanto
  `api.github.com` estiver fora.

## Validação manual (sem reiniciar o app)

```bash
{ printf '%s\n' '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"sim","version":"1.0"}}}'
  printf '%s\n' '{"jsonrpc":"2.0","method":"notifications/initialized"}'
  printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
} | DEFAULT_IMAGE=openclaw-sandbox WORKSPACE_PATH=/Users/fas/projetos/OPENCLAW \
    /Users/fas/.local/share/code-sandbox-mcp/code-sandbox-mcp -no-update &
PID=$!; sleep 6; kill $PID 2>/dev/null
```

**Sucesso:** `initialize` responde rápido (sem travar 15s), stderr limpo, e
`tools/list` retorna as 7 tools: `sandbox_initialize`, `sandbox_exec`,
`write_file_sandbox`, `copy_file`, `copy_file_from_sandbox`, `copy_project`,
`sandbox_stop`. (Pré-requisito: Docker rodando + imagem `openclaw-sandbox:latest`.)

## Imagem do sandbox (`openclaw-sandbox:latest`)

O MCP **ignora o parâmetro `image`** e sempre sobe `DEFAULT_IMAGE=openclaw-sandbox`.
Logo, o ambiente dentro do sandbox é exatamente o que estiver buildado nessa tag.

> ⚠️ **Regressão histórica (corrigida 2026-06-10):** a tag estava stale com
> **Python 3.14.4**, sem `node` e sem `postgresql-client-18` — divergia do
> projeto (que exige 3.12). Toda execução no sandbox rodava no Python errado.

Fonte da verdade: `Dockerfile.openclaw-sandbox` (pinado por digest em
`python:3.12-slim` = 3.12.13; dois guards de build abortam se a base sair da
série 3.12). Deps vêm de `uv.lock` → `/opt/openclaw-venv`.

**Rebuild reproduzível (Docker Compose):**

```bash
docker compose -f docker/docker-compose.sandbox.yml build
```

**Verificação pós-build:**

```bash
docker run --rm openclaw-sandbox:latest python --version   # Python 3.12.13
docker run --rm openclaw-sandbox:latest pg_dump --version  # 18.x
docker run --rm openclaw-sandbox:latest node --version     # v20.x (Pyright)
```
