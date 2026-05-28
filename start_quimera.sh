#!/usr/bin/env bash
# =============================================================================
# QUIMERA — Boot completo do stack local
# =============================================================================
#
# USO:
#   bash start_quimera.sh                → sobe tudo (Qdrant + Ollama + LiteLLM)
#   bash start_quimera.sh --status       → verifica estado atual de todos os serviços
#   bash start_quimera.sh --smoke        → smoke test funcional: embed + chat end-to-end
#   bash start_quimera.sh --stop         → para todos os serviços limpo
#   bash start_quimera.sh --restart-litellm → reinicia só o LiteLLM (caso mais comum)
#   bash start_quimera.sh --help         → mostra essa ajuda
#
# ORDEM DE BOOT:
#   1. Valida .env e LITELLM_MASTER_KEY
#   2. Qdrant v1.18.1  (docker compose, porta 6333)
#   3. Ollama          (daemon + modelos nomic-embed-text + qwen3:14b)
#   4. LiteLLM         (nova aba do iTerm2, porta 4000)
#   5. Health check    (valida todos os serviços via /health/liveliness)
#   6. Status final    (resumo do stack com versão Qdrant)
#
# NOTA: /health do LiteLLM exige Bearer token. Usar /health/liveliness para
# verificações automáticas. Embedding aparece "unhealthy" no health autenticado
# por limitação do LiteLLM — é falso positivo, embeddings funcionam normalmente.
#
# PREREQUISITOS (instalar uma vez):
#   brew install docker ollama
#   ollama pull nomic-embed-text
#   ollama pull qwen3:14b
#   cd infra/litellm && pip install -r requirements.txt --target .venv/lib/...
#   (ou: cd infra/litellm && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt)
#
# =============================================================================

set -euo pipefail

# ── Configuração ──────────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_COMPOSE_FILE="${REPO_ROOT}/docker/docker-compose.qdrant.yml"
LITELLM_DIR="${REPO_ROOT}/infra/litellm"
ENV_FILE="${REPO_ROOT}/.env"
LOG_DIR="${REPO_ROOT}/logs"

QDRANT_URL="http://127.0.0.1:6333"
OLLAMA_URL="http://127.0.0.1:11434"
LITELLM_URL="http://127.0.0.1:4000"

EMBED_MODEL="nomic-embed-text"
CHAT_MODEL="qwen3:14b"

# ── Cores ─────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

ok()   { printf "       ${GREEN}✅ %s${RESET}\n" "$1"; }
warn() { printf "       ${YELLOW}⚠️  %s${RESET}\n" "$1"; }
err()  { printf "       ${RED}❌ %s${RESET}\n" "$1"; }
info() { printf "       ${CYAN}→  %s${RESET}\n" "$1"; }

# ── Helpers ───────────────────────────────────────────────────────────────────
wait_for() {
    local url="$1" label="$2" max="${3:-20}"
    for i in $(seq 1 "$max"); do
        if curl -fs --max-time 2 "$url" > /dev/null 2>&1; then
            return 0
        fi
        sleep 1
        printf "       ... aguardando %s (%d/%d)\n" "$label" "$i" "$max"
    done
    return 1
}

check_env_file() {
    if [[ ! -f "$ENV_FILE" ]]; then
        err ".env não encontrado em ${REPO_ROOT}"
        info "Execute: cp .env.example .env e preencha LITELLM_MASTER_KEY e QUIMERA_LLM_API_KEY"
        exit 1
    fi
    # shellcheck disable=SC1090
    set -a && source "$ENV_FILE" && set +a
    if [[ -z "${LITELLM_MASTER_KEY:-}" ]]; then
        err "LITELLM_MASTER_KEY não está definido no .env"
        exit 1
    fi
}

# ── Modo --status (só verifica, não sobe nada) ────────────────────────────────
status_only() {
    printf "\n${BOLD}QUIMERA — STATUS DOS SERVIÇOS${RESET}\n"
    printf "%-20s %-10s %s\n" "SERVIÇO" "STATUS" "ENDPOINT"
    printf "%-20s %-10s %s\n" "───────" "──────" "────────"

    # Qdrant
    if curl -fs --max-time 2 "${QDRANT_URL}/healthz" > /dev/null 2>&1; then
        COLS=$(curl -s "${QDRANT_URL}/collections" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); print(','.join(c['name'] for c in d['result']['collections']))" 2>/dev/null || echo "?")
        printf "${GREEN}%-20s %-10s %s${RESET}\n" "Qdrant" "OK" "${QDRANT_URL} [${COLS}]"
    else
        printf "${RED}%-20s %-10s %s${RESET}\n" "Qdrant" "PARADO" "${QDRANT_URL}"
    fi

    # Ollama
    if curl -fs --max-time 2 "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; then
        MODELS=$(curl -s "${OLLAMA_URL}/api/tags" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); print(','.join(m['name'] for m in d.get('models',[])))" 2>/dev/null || echo "?")
        printf "${GREEN}%-20s %-10s %s${RESET}\n" "Ollama" "OK" "${OLLAMA_URL} [${MODELS}]"
        # Modelos carregados em memória
        PS=$(curl -s "${OLLAMA_URL}/api/ps" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); ms=d.get('models',[]); print(','.join(m['name'] for m in ms) if ms else 'nenhum na RAM')" 2>/dev/null || echo "?")
        printf "  ${CYAN}%-18s %-10s %s${RESET}\n" "  └ na memória" "" "${PS}"
    else
        printf "${RED}%-20s %-10s %s${RESET}\n" "Ollama" "PARADO" "${OLLAMA_URL}"
    fi

    # LiteLLM — /health exige Bearer token; /health/liveliness é público
    if curl -fs --max-time 2 "${LITELLM_URL}/health/liveliness" > /dev/null 2>&1; then
        printf "${GREEN}%-20s %-10s %s${RESET}\n" "LiteLLM" "OK" "${LITELLM_URL}"
    else
        printf "${YELLOW}%-20s %-10s %s${RESET}\n" "LiteLLM" "PARADO" "${LITELLM_URL}"
    fi

    printf "\n"
    exit 0
}

# ── Help ──────────────────────────────────────────────────────────────────────
show_help() {
    sed -n '2,30p' "$0" | grep "^#" | sed 's/^# \?//'
    exit 0
}

# ── Modo --stop (para todos os serviços limpo) ────────────────────────────────
stop_all() {
    printf "\n${BOLD}QUIMERA — PARANDO TODOS OS SERVIÇOS${RESET}\n\n"

    # LiteLLM
    if pgrep -f "litellm" > /dev/null 2>&1; then
        pkill -f "litellm" && ok "LiteLLM parado" || warn "Falha ao parar LiteLLM"
    else
        info "LiteLLM já estava parado"
    fi

    # Ollama — só para o daemon se ele foi iniciado por nós
    if curl -fs --max-time 2 "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; then
        if pkill -f "ollama serve" > /dev/null 2>&1; then
            ok "Ollama daemon parado"
        else
            warn "Ollama não parou (pode ser gerenciado pelo sistema — normal se instalado via brew services)"
        fi
    else
        info "Ollama já estava parado"
    fi

    # Qdrant
    if [[ -f "${DOCKER_COMPOSE_FILE}" ]]; then
        if docker compose -f "${DOCKER_COMPOSE_FILE}" ps --quiet 2>/dev/null | grep -q .; then
            docker compose -f "${DOCKER_COMPOSE_FILE}" down 2>/dev/null && ok "Qdrant parado" || warn "Falha ao parar Qdrant"
        else
            info "Qdrant já estava parado"
        fi
    fi

    printf "\n${GREEN}Stack QUIMERA encerrado.${RESET}\n\n"
    exit 0
}

# ── Modo --smoke (verifica embed + chat end-to-end) ───────────────────────────
smoke_test() {
    printf "\n${BOLD}QUIMERA — SMOKE TEST FUNCIONAL${RESET}\n\n"

    # Carrega .env para ter LITELLM_MASTER_KEY
    if [[ -f "${ENV_FILE}" ]]; then
        # shellcheck disable=SC1090
        set -a && source "${ENV_FILE}" && set +a
    fi

    if [[ -z "${LITELLM_MASTER_KEY:-}" ]]; then
        err "LITELLM_MASTER_KEY não encontrado — necessário para smoke test"
        exit 1
    fi

    local FAIL=0

    # ── Smoke 1: Qdrant health ──────────────────────────────────────────────
    printf "${BOLD}[1/3] Qdrant${RESET}\n"
    if curl -fs --max-time 3 "${QDRANT_URL}/healthz" > /dev/null 2>&1; then
        ok "Qdrant responde em ${QDRANT_URL}"
    else
        err "Qdrant não responde — rode: bash start_quimera.sh"
        FAIL=1
    fi

    # ── Smoke 2: Embedding (quimera_embed → nomic-embed-text → 768d) ───────
    printf "\n${BOLD}[2/3] Embedding (quimera_embed)${RESET}\n"
    EMBED_RESP=$(curl -s --max-time 15 \
        -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
        -H "Content-Type: application/json" \
        -d '{"model":"quimera_embed","input":"smoke test QUIMERA embedding"}' \
        "${LITELLM_URL}/v1/embeddings" 2>/dev/null || echo "CURL_ERROR")

    if echo "${EMBED_RESP}" | grep -q "CURL_ERROR\|error\|Error" && ! echo "${EMBED_RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if 'data' in d else 1)" 2>/dev/null; then
        err "Embedding falhou — verifique LiteLLM e Ollama"
        info "Resposta: ${EMBED_RESP:0:200}"
        FAIL=1
    else
        DIMS=$(echo "${EMBED_RESP}" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); v=d['data'][0]['embedding']; print(len(v))" 2>/dev/null || echo "?")
        if [[ "${DIMS}" == "768" ]]; then
            ok "Embedding OK — ${DIMS} dimensões (nomic-embed-text ✅)"
        else
            err "Dimensões inesperadas: ${DIMS} (esperado 768)"
            FAIL=1
        fi
    fi

    # ── Smoke 3: Chat (local_chat → qwen3:14b) ─────────────────────────────
    printf "\n${BOLD}[3/3] Chat (local_chat)${RESET}\n"
    info "Enviando prompt mínimo — pode levar 15-30s na primeira chamada..."
    CHAT_RESP=$(curl -s --max-time 60 \
        -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
        -H "Content-Type: application/json" \
        -d '{"model":"local_chat","messages":[{"role":"user","content":"Responda apenas: QUIMERA OK"}],"max_tokens":20}' \
        "${LITELLM_URL}/v1/chat/completions" 2>/dev/null || echo "CURL_ERROR")

    if echo "${CHAT_RESP}" | python3 -c \
        "import sys,json; d=json.load(sys.stdin); t=d['choices'][0]['message']['content']; print(f'Resposta: {t[:80]}')" 2>/dev/null; then
        ok "Chat OK — qwen3:14b respondeu via local_chat"
    else
        err "Chat falhou — verifique LiteLLM e Ollama"
        info "Resposta: ${CHAT_RESP:0:300}"
        FAIL=1
    fi

    printf "\n"
    if [[ $FAIL -eq 0 ]]; then
        printf "${GREEN}${BOLD}Smoke test PASSOU ✅ — stack operacional.${RESET}\n\n"
    else
        printf "${RED}${BOLD}Smoke test FALHOU ❌ — verifique os erros acima.${RESET}\n\n"
        exit 1
    fi
    exit 0
}

# ── Modo --restart-litellm (reinicia só o LiteLLM) ────────────────────────────
restart_litellm() {
    printf "\n${BOLD}QUIMERA — REINICIANDO LITELLM${RESET}\n\n"

    # Carrega .env
    if [[ -f "${ENV_FILE}" ]]; then
        # shellcheck disable=SC1090
        set -a && source "${ENV_FILE}" && set +a
    fi
    if [[ -z "${LITELLM_MASTER_KEY:-}" ]]; then
        err "LITELLM_MASTER_KEY não encontrado em ${ENV_FILE}"
        exit 1
    fi

    # Para instância existente
    if pgrep -f "litellm" > /dev/null 2>&1; then
        info "Parando LiteLLM existente..."
        pkill -f "litellm" && sleep 2 && ok "LiteLLM parado"
    else
        info "Nenhuma instância LiteLLM em execução"
    fi

    # Verifica venv
    if [[ ! -f "${LITELLM_DIR}/.venv/bin/litellm" ]]; then
        err "venv do LiteLLM não encontrado em ${LITELLM_DIR}/.venv"
        info "Execute: cd infra/litellm && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi

    # Derivar vars para litellm_config.yaml
    _QWEN="${QWEN_MODEL:-qwen3:14b}"
    _EMBED="${EMBED_MODEL:-nomic-embed-text}"
    export LITELLM_LOCAL_CHAT_MODEL="${LITELLM_LOCAL_CHAT_MODEL:-ollama_chat/${_QWEN}}"
    export LITELLM_LOCAL_EMBED_MODEL="${LITELLM_LOCAL_EMBED_MODEL:-ollama/${_EMBED}}"

    # Inicia (iTerm2 ou fallback background)
    LITELLM_TAB_CMD="cd ${REPO_ROOT} && set -a && source .env && set +a && export LITELLM_LOCAL_CHAT_MODEL=ollama_chat/\${QWEN_MODEL:-qwen3:14b} && export LITELLM_LOCAL_EMBED_MODEL=ollama/\${EMBED_MODEL:-nomic-embed-text} && infra/litellm/.venv/bin/litellm --config infra/litellm/litellm_config.yaml --host 127.0.0.1 --port 4000"

    if command -v osascript > /dev/null 2>&1; then
        info "Abrindo nova aba LiteLLM no iTerm2..."
        osascript - "${LITELLM_TAB_CMD}" <<'APPLESCRIPT'
on run argv
    set cmdLiteLLM to item 1 of argv
    tell application "iTerm2"
        set w to current window
        tell w
            set tLiteLLM to (create tab with default profile)
            tell tLiteLLM
                tell current session
                    set name to "⚡ LiteLLM :4000"
                    write text cmdLiteLLM
                end tell
            end tell
            select first tab
        end tell
    end tell
end run
APPLESCRIPT
    else
        warn "iTerm2 não detectado — iniciando LiteLLM em background"
        (cd "${REPO_ROOT}" && set -a && source .env && set +a && \
         export LITELLM_LOCAL_CHAT_MODEL="ollama_chat/${QWEN_MODEL:-qwen3:14b}" && \
         export LITELLM_LOCAL_EMBED_MODEL="ollama/${EMBED_MODEL:-nomic-embed-text}" && \
         infra/litellm/.venv/bin/litellm \
           --config infra/litellm/litellm_config.yaml \
           --host 127.0.0.1 --port 4000 \
           > "${LOG_DIR}/litellm.log" 2>&1) &
        info "Log: logs/litellm.log"
    fi

    info "Aguardando LiteLLM iniciar (até 45s)..."
    if wait_for "${LITELLM_URL}/health/liveliness" "LiteLLM" 45; then
        ok "LiteLLM reiniciado em ${LITELLM_URL}"
    else
        err "LiteLLM não respondeu em 45s"
        info "Verifique a aba '⚡ LiteLLM :4000' ou logs/litellm.log"
        exit 1
    fi

    printf "\n${GREEN}${BOLD}LiteLLM reiniciado com sucesso ✅${RESET}\n\n"
    exit 0
}

# ── Parse args ────────────────────────────────────────────────────────────────
case "${1:-}" in
    --status) status_only ;;
    --smoke)  smoke_test ;;
    --stop)   stop_all ;;
    --restart-litellm) restart_litellm ;;
    --help|-h) show_help ;;
esac

# =============================================================================
# BOOT SEQUENCE
# =============================================================================

mkdir -p "$LOG_DIR"

printf "\n"
printf "${BOLD}╔══════════════════════════════════════════════════╗${RESET}\n"
printf "${BOLD}║       QUIMERA — BOOT SEQUENCE (stack local)      ║${RESET}\n"
printf "${BOLD}╚══════════════════════════════════════════════════╝${RESET}\n"
printf "\n"

# ── PASSO 1: Carregar .env ────────────────────────────────────────────────────
printf "${BOLD}[ 1/6 ] Carregando variáveis de ambiente (.env)...${RESET}\n"
check_env_file
ok ".env carregado — LITELLM_MASTER_KEY presente"

# ── PASSO 2: Qdrant ───────────────────────────────────────────────────────────
printf "\n${BOLD}[ 2/6 ] Qdrant (vector database)...${RESET}\n"

if curl -fs --max-time 2 "${QDRANT_URL}/healthz" > /dev/null 2>&1; then
    ok "Qdrant já está rodando em ${QDRANT_URL}"
else
    info "Subindo Qdrant via docker compose..."
    docker compose -f "$DOCKER_COMPOSE_FILE" up -d 2>>"${LOG_DIR}/qdrant.log"
    if wait_for "${QDRANT_URL}/healthz" "Qdrant" 20; then
        ok "Qdrant iniciado"
    else
        err "Qdrant não respondeu após 20s — verifique: docker compose -f docker/docker-compose.qdrant.yml logs"
        exit 1
    fi
fi

# Verificar collections
COLLECTIONS=$(curl -s "${QDRANT_URL}/collections" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); cols=d['result']['collections']; print(f\"{len(cols)} collections: {', '.join(c['name'] for c in cols)}\" if cols else 'VAZIO — rode bootstrap_corpus.py')" 2>/dev/null || echo "?")
info "Collections: ${COLLECTIONS}"

if echo "$COLLECTIONS" | grep -q "VAZIO"; then
    warn "Corpus não ingerido! Execute depois:"
    info "QUIMERA_RAG_EMBEDDING_BACKEND=direct_ollama uv run --env-file .env python scripts/bootstrap_corpus.py --corpus internal --commit"
    info "QUIMERA_RAG_EMBEDDING_BACKEND=direct_ollama uv run --env-file .env python scripts/bootstrap_corpus.py --corpus financial --commit"
fi

# ── PASSO 3: Ollama daemon ────────────────────────────────────────────────────
printf "\n${BOLD}[ 3/6 ] Ollama (runtime de modelos locais)...${RESET}\n"

if curl -fs --max-time 2 "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; then
    ok "Ollama já está rodando em ${OLLAMA_URL}"
else
    info "Iniciando Ollama em background..."
    nohup ollama serve > "${LOG_DIR}/ollama.log" 2>&1 &
    if wait_for "${OLLAMA_URL}/api/tags" "Ollama" 15; then
        ok "Ollama iniciado (log: logs/ollama.log)"
    else
        err "Ollama não respondeu após 15s — verifique logs/ollama.log"
        exit 1
    fi
fi

# ── PASSO 4: Modelos Ollama ───────────────────────────────────────────────────
printf "\n${BOLD}[ 4/6 ] Verificando modelos Ollama...${RESET}\n"

for MODEL in "$EMBED_MODEL" "$CHAT_MODEL"; do
    if curl -s "${OLLAMA_URL}/api/tags" | python3 -c \
        "import sys,json; d=json.load(sys.stdin); names=[m['name'] for m in d.get('models',[])]; exit(0 if any('${MODEL}' in n for n in names) else 1)" 2>/dev/null; then
        ok "${MODEL} disponível"
    else
        warn "${MODEL} não encontrado — baixando agora..."
        ollama pull "$MODEL"
        ok "${MODEL} baixado"
    fi
done

# Mostrar o que está carregado na RAM
PS_OUTPUT=$(curl -s "${OLLAMA_URL}/api/ps" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); ms=d.get('models',[]); [print(f'  {m[\"name\"]} ({round(m.get(\"size\",0)/1e9,1)}GB)') for m in ms]" 2>/dev/null || true)
if [[ -n "$PS_OUTPUT" ]]; then
    info "Modelos carregados na RAM:"
    echo "$PS_OUTPUT"
else
    info "Nenhum modelo na RAM ainda (serão carregados na primeira chamada)"
fi

# ── PASSO 5: LiteLLM gateway ──────────────────────────────────────────────────
printf "\n${BOLD}[ 5/6 ] LiteLLM gateway (porta 4000)...${RESET}\n"

# /health exige Bearer token no LiteLLM ≥1.x — usar /health/liveliness (sem auth)
if curl -fs --max-time 2 "${LITELLM_URL}/health/liveliness" > /dev/null 2>&1; then
    ok "LiteLLM já está rodando em ${LITELLM_URL}"
else
    # Verificar se o venv do LiteLLM existe
    if [[ ! -f "${LITELLM_DIR}/.venv/bin/litellm" ]]; then
        err "venv do LiteLLM não encontrado. Execute uma vez:"
        info "cd infra/litellm && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi

    # Derivar vars que litellm_config.yaml referencia via os.environ/
    # (start_litellm.sh faz isso — aqui replicamos para o fallback sem iTerm2)
    _QWEN="${QWEN_MODEL:-qwen3:14b}"
    _EMBED="${EMBED_MODEL:-nomic-embed-text}"
    export LITELLM_LOCAL_CHAT_MODEL="${LITELLM_LOCAL_CHAT_MODEL:-ollama_chat/${_QWEN}}"
    export LITELLM_LOCAL_EMBED_MODEL="${LITELLM_LOCAL_EMBED_MODEL:-ollama/${_EMBED}}"

    # Comando para a aba — inclui variáveis derivadas necessárias para litellm_config.yaml
    LITELLM_TAB_CMD="cd ${REPO_ROOT} && set -a && source .env && set +a && export LITELLM_LOCAL_CHAT_MODEL=ollama_chat/\${QWEN_MODEL:-qwen3:14b} && export LITELLM_LOCAL_EMBED_MODEL=ollama/\${EMBED_MODEL:-nomic-embed-text} && infra/litellm/.venv/bin/litellm --config infra/litellm/litellm_config.yaml --host 127.0.0.1 --port 4000"

    if command -v osascript > /dev/null 2>&1; then
        info "Abrindo aba LiteLLM na janela atual do iTerm2..."
        osascript - "${LITELLM_TAB_CMD}" "${REPO_ROOT}" <<'APPLESCRIPT'
on run argv
    set cmdLiteLLM to item 1 of argv
    tell application "iTerm2"
        -- Usa a janela já existente (criada pelo boot script)
        set w to current window
        tell w
            -- Tab: LiteLLM gateway
            set tLiteLLM to (create tab with default profile)
            tell tLiteLLM
                tell current session
                    set name to "⚡ LiteLLM :4000"
                    write text cmdLiteLLM
                end tell
            end tell
            -- Volta para a primeira aba (boot/status)
            select first tab
        end tell
    end tell
end run
APPLESCRIPT
        info "Aguardando LiteLLM iniciar (até 45s — é normal demorar)..."
        if wait_for "${LITELLM_URL}/health/liveliness" "LiteLLM" 45; then
            ok "LiteLLM iniciado em ${LITELLM_URL}"
        else
            warn "LiteLLM ainda não respondeu — veja a aba '⚡ LiteLLM :4000' para erros."
        fi
    else
        # Fallback: background com log (sem iTerm2)
        warn "iTerm2 não detectado — iniciando LiteLLM em background"
        (cd "${REPO_ROOT}" && set -a && source .env && set +a && \
         export LITELLM_LOCAL_CHAT_MODEL="ollama_chat/${QWEN_MODEL:-qwen3:14b}" && \
         export LITELLM_LOCAL_EMBED_MODEL="ollama/${EMBED_MODEL:-nomic-embed-text}" && \
         infra/litellm/.venv/bin/litellm \
           --config infra/litellm/litellm_config.yaml \
           --host 127.0.0.1 --port 4000 \
           > "${LOG_DIR}/litellm.log" 2>&1) &
        info "Log: logs/litellm.log"
        if wait_for "${LITELLM_URL}/health/liveliness" "LiteLLM" 45; then
            ok "LiteLLM iniciado em background"
        else
            warn "LiteLLM ainda não respondeu — verifique logs/litellm.log"
        fi
    fi
fi

# ── PASSO 6: Health check final ───────────────────────────────────────────────
printf "\n${BOLD}[ 6/6 ] Health check final...${RESET}\n"

ALL_OK=true

curl -fs --max-time 3 "${QDRANT_URL}/healthz" > /dev/null 2>&1 \
    && ok "Qdrant ${QDRANT_URL}" \
    || { err "Qdrant não responde"; ALL_OK=false; }

curl -fs --max-time 3 "${OLLAMA_URL}/api/tags" > /dev/null 2>&1 \
    && ok "Ollama ${OLLAMA_URL}" \
    || { err "Ollama não responde"; ALL_OK=false; }

curl -fs --max-time 5 "${LITELLM_URL}/health/liveliness" > /dev/null 2>&1 \
    && ok "LiteLLM ${LITELLM_URL}" \
    || { warn "LiteLLM ${LITELLM_URL} (pode ainda estar subindo)"; }

# ── RESUMO FINAL ──────────────────────────────────────────────────────────────
printf "\n"
if $ALL_OK; then
    printf "${GREEN}${BOLD}╔══════════════════════════════════════════════════╗${RESET}\n"
    printf "${GREEN}${BOLD}║         QUIMERA STACK — PRONTO ✅                ║${RESET}\n"
    printf "${GREEN}${BOLD}╠══════════════════════════════════════════════════╣${RESET}\n"
    printf "${GREEN}${BOLD}║  Qdrant   → http://127.0.0.1:6333/dashboard     ║${RESET}\n"
    printf "${GREEN}${BOLD}║  Ollama   → http://127.0.0.1:11434              ║${RESET}\n"
    printf "${GREEN}${BOLD}║  LiteLLM  → http://127.0.0.1:4000              ║${RESET}\n"
    printf "${GREEN}${BOLD}║  Embed    → quimera_embed (nomic, 768d)         ║${RESET}\n"
    printf "${GREEN}${BOLD}║  Chat     → local_chat / local_rag (qwen3:14b)  ║${RESET}\n"
    printf "${GREEN}${BOLD}╚══════════════════════════════════════════════════╝${RESET}\n"
else
    printf "${YELLOW}${BOLD}╔══════════════════════════════════════════════════╗${RESET}\n"
    printf "${YELLOW}${BOLD}║   QUIMERA STACK — PARCIALMENTE INICIADO ⚠️       ║${RESET}\n"
    printf "${YELLOW}${BOLD}║   Verifique os erros acima antes de continuar.  ║${RESET}\n"
    printf "${YELLOW}${BOLD}╚══════════════════════════════════════════════════╝${RESET}\n"
fi

printf "\n${BOLD}COMANDOS ÚTEIS:${RESET}\n"
printf "  Status dos serviços:   ${CYAN}bash start_quimera.sh --status${RESET}\n"
printf "  Smoke test E2E:        ${CYAN}bash start_quimera.sh --smoke${RESET}\n"
printf "  Parar tudo:            ${CYAN}bash start_quimera.sh --stop${RESET}\n"
printf "  Reiniciar só LiteLLM:  ${CYAN}bash start_quimera.sh --restart-litellm${RESET}\n"
printf "  Testes unitários:      ${CYAN}uv run pytest tests/unit/ -v${RESET}\n"
printf "  Baseline PR-03:        ${CYAN}QUIMERA_RAG_EMBEDDING_BACKEND=direct_ollama uv run --env-file .env python evaluation/run_dense_baseline.py${RESET}\n"
printf "  Dashboard Qdrant:      ${CYAN}open http://127.0.0.1:6333/dashboard${RESET}\n"
printf "\n"
