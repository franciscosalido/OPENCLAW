# QUIMERA Stack Runbook — Boot, Health Check e Diagnóstico

> Documento gerado em 2026-05-27. Atualizar após qualquer mudança de infraestrutura.

---

## Stack Overview

| Serviço  | Porta  | URL                          | Processo         |
|----------|--------|------------------------------|------------------|
| Qdrant   | 6333   | http://127.0.0.1:6333        | docker container |
| Ollama   | 11434  | http://127.0.0.1:11434       | nohup background |
| LiteLLM  | 4000   | http://127.0.0.1:4000        | nohup background |

---

## Boot Rápido

```bash
cd ~/projetos/OPENCLAW
bash start_quimera.sh          # sobe tudo
bash start_quimera.sh --status # apenas verifica
```

O script cuida de: subir Qdrant via docker compose, iniciar Ollama em background, derivar variáveis de ambiente e iniciar LiteLLM.

---

## Boot Manual (passo a passo)

Se o script falhar, execute manualmente nesta ordem:

### 1. Qdrant
```bash
docker compose -f docker/docker-compose.qdrant.yml up -d
curl -s http://127.0.0.1:6333/healthz          # esperado: "healthz check passed"
curl -s http://127.0.0.1:6333/ | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])"
curl -s http://127.0.0.1:6333/collections | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print([c['name'] for c in d['result']['collections']])"
```

### 2. Ollama
```bash
nohup ollama serve > logs/ollama.log 2>&1 &
curl -s http://127.0.0.1:11434/api/tags | python3 -c \
  "import sys,json; [print(m['name']) for m in json.load(sys.stdin)['models']]"
```

### 3. LiteLLM
```bash
# IMPORTANTE: derivar vars antes de chamar litellm diretamente
set -a && source .env && set +a
export LITELLM_LOCAL_CHAT_MODEL="ollama_chat/${QWEN_MODEL:-qwen3:14b}"
export LITELLM_LOCAL_EMBED_MODEL="ollama/${EMBED_MODEL:-nomic-embed-text}"

nohup infra/litellm/.venv/bin/litellm \
  --config infra/litellm/litellm_config.yaml \
  --host 127.0.0.1 --port 4000 \
  > logs/litellm.log 2>&1 &
```

---

## Health Checks

### Qdrant
```bash
curl -s http://127.0.0.1:6333/healthz                 # "healthz check passed"
curl -s http://127.0.0.1:6333/                        # versão
curl -s http://127.0.0.1:6333/collections             # lista collections
```

### Ollama
```bash
curl -s http://127.0.0.1:11434/api/tags               # modelos disponíveis
curl -s http://127.0.0.1:11434/api/ps                 # modelos na RAM
```

### LiteLLM
```bash
# Sem autenticação (liveliness apenas):
curl -s http://127.0.0.1:4000/health/liveliness       # "I'm alive!"

# Com autenticação (health completo com status dos endpoints):
MASTER=$(grep "^LITELLM_MASTER_KEY=" .env | head -1 | cut -d= -f2-)
curl -s -H "Authorization: Bearer ${MASTER}" http://127.0.0.1:4000/health | python3 -m json.tool

# Modelos disponíveis:
curl -s -H "Authorization: Bearer ${MASTER}" http://127.0.0.1:4000/models | \
  python3 -c "import sys,json; [print(m['id']) for m in json.load(sys.stdin)['data']]"
```

---

## Smoke Tests Funcionais

### Embedding (quimera_embed / local_embed)
```bash
MASTER=$(grep "^LITELLM_MASTER_KEY=" .env | head -1 | cut -d= -f2-)
curl -s -X POST http://127.0.0.1:4000/v1/embeddings \
  -H "Authorization: Bearer ${MASTER}" \
  -H "Content-Type: application/json" \
  -d '{"model": "quimera_embed", "input": "teste"}' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['data'][0]['embedding']), 'dimensões')"
# esperado: 768 dimensões
```

### Chat (local_chat)
```bash
MASTER=$(grep "^LITELLM_MASTER_KEY=" .env | head -1 | cut -d= -f2-)
curl -s --max-time 90 -X POST http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer ${MASTER}" \
  -H "Content-Type: application/json" \
  -d '{"model": "local_chat", "messages": [{"role":"user","content":"Responda: OK"}], "max_tokens": 5}' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
# primeira chamada pode demorar 30-60s (qwen3:14b carregando na RAM)
```

---

## Aliases LiteLLM Disponíveis

| Alias          | Modelo base          | Timeout | Propósito                        |
|----------------|----------------------|---------|----------------------------------|
| `local_chat`   | ollama_chat/qwen3:14b| 30s     | chat padrão, think=false         |
| `local_think`  | ollama_chat/qwen3:14b| 120s    | raciocínio extended              |
| `local_rag`    | ollama_chat/qwen3:14b| 60s     | síntese de respostas RAG         |
| `local_json`   | ollama_chat/qwen3:14b| 30s     | respostas JSON estruturadas      |
| `quimera_embed`| ollama/nomic-embed-text | 30s  | embeddings canônicos (768d)      |
| `local_embed`  | ollama/nomic-embed-text | 30s  | alias de compatibilidade (768d)  |

---

## Problemas Conhecidos e Soluções

### BUG 1 — LiteLLM: `healthy=4 unhealthy=2` (embedding endpoints)

**Sintoma:** `curl /health` retorna `unhealthy_count: 2` para `quimera_embed` e `local_embed`.

**Causa:** O health check interno do LiteLLM envia uma requisição de *completion* (`/api/generate`) para todos os modelos, incluindo os de embedding. O modelo `nomic-embed-text` não suporta `/api/generate` — só `/api/embed`. Erro: `"nomic-embed-text" does not support generate`.

**Impacto:** NENHUM. Os endpoints de embedding real (`POST /v1/embeddings`) funcionam corretamente, retornando vetores de 768 dimensões. O health check do LiteLLM é um falso positivo para modelos de embedding via `ollama/` prefix.

**Solução permanente futura:** Atualizar `litellm_config.yaml` para usar `mode: embedding` no `model_info` dos aliases de embedding (aguarda release do LiteLLM que suporte health check específico por modalidade).

**Workaround atual:** Usar `/health/liveliness` como indicador de vida e testar embedding diretamente no smoke test.

---

### BUG 2 — `start_quimera.sh`: falso negativo no health check do LiteLLM (CORRIGIDO)

**Sintoma:** O script reportava "LiteLLM PARADO" mesmo com o gateway rodando.

**Causa:** `curl -fs http://127.0.0.1:4000/health` retorna HTTP 401 nas versões recentes do LiteLLM quando `master_key` está configurado. O curl via `-f` interpreta 401 como falha.

**Fix aplicado:** Todas as verificações de liveliness trocadas para `/health/liveliness` (endpoint público, sem auth). Afetava: `status_only()`, `wait_for`, e o health check final (linhas 112, 221, 260, 274, 295).

---

### BUG 3 — `start_quimera.sh` fallback sem iTerm2: variáveis derivadas ausentes

**Sintoma:** LiteLLM inicia mas falha ao carregar modelos porque `LITELLM_LOCAL_CHAT_MODEL` e `LITELLM_LOCAL_EMBED_MODEL` não estão definidos.

**Causa:** O `litellm_config.yaml` usa `os.environ/LITELLM_LOCAL_CHAT_MODEL` e `os.environ/LITELLM_LOCAL_EMBED_MODEL`. O `source .env` não define essas variáveis — elas são derivadas em `start_litellm.sh`. O fallback do `start_quimera.sh` chamava `litellm` diretamente sem derivar essas variáveis.

**Fix aplicado:** Adicionado export das variáveis derivadas antes de chamar litellm no fallback (e no iTerm2 path).

---

### ERRO — `.env` com comentários inline

**Sintoma:** `grep LITELLM_MASTER_KEY .env | cut -d= -f2-` captura comentários na chave.

**Causa:** `.env` tem comentário multi-linha antes ou após o valor.

**Fix:** Sempre usar `grep "^LITELLM_MASTER_KEY=" .env | head -1 | cut -d= -f2-`.

---

## Parar Serviços

```bash
# Parar tudo
pkill ollama
pkill -f "litellm"
docker compose -f docker/docker-compose.qdrant.yml down

# Verificar que parou
lsof -iTCP:6333 -iTCP:4000 -iTCP:11434 -sTCP:LISTEN
```

---

## Logs

| Serviço  | Log                   |
|----------|-----------------------|
| Qdrant   | `docker compose -f docker/docker-compose.qdrant.yml logs` |
| Ollama   | `logs/ollama.log`     |
| LiteLLM  | `logs/litellm.log`    |

---

## Collections Qdrant (estado em 2026-05-27)

| Collection                    | Propósito                          |
|-------------------------------|------------------------------------|
| `openclaw_financial`          | corpus financeiro                  |
| `openclaw_internal`           | corpus interno                     |
| `openclaw_knowledge`          | knowledge vault geral              |
| `quimera_benchmark_hybrid_118`| benchmarks Qdrant v1.18 híbrido    |

---

## Pré-requisitos (instalação única)

```bash
brew install docker ollama
ollama pull nomic-embed-text
ollama pull qwen3:14b
cd infra/litellm && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env   # preencher LITELLM_MASTER_KEY e QUIMERA_LLM_API_KEY
```
