#!/usr/bin/env bash
# =============================================================
# OPENCLAW — claude-mem setup script
# Instala e configura o sistema de memória persistente
# para Claude Code neste projeto.
# =============================================================

set -e

echo "\n🧠 OPENCLAW — claude-mem setup"
echo "================================"

# 1. Verificar Node.js >= 18
NODE_VERSION=$(node -v 2>/dev/null | sed 's/v//' | cut -d. -f1)
if [ -z "$NODE_VERSION" ] || [ "$NODE_VERSION" -lt 18 ]; then
  echo "❌ Node.js 18+ é necessário. Instale via https://nodejs.org"
  exit 1
fi
echo "✅ Node.js $(node -v) detectado"

# 2. Instalar claude-mem globalmente
echo "\n📦 Instalando claude-mem..."
npx claude-mem@latest install

# 3. Verificar se o worker está rodando
echo "\n🔍 Verificando worker de memória..."
sleep 2
if curl -sf http://localhost:37777/api/health > /dev/null 2>&1; then
  echo "✅ Worker claude-mem rodando em localhost:37777"
else
  echo "⚠️  Worker não detectado — rode: npx claude-mem start"
fi

# 4. Mostrar localização do banco de dados
DB_PATH="$HOME/.claude-mem/claude-mem.db"
if [ -f "$DB_PATH" ]; then
  echo "\n✅ Banco de dados: $DB_PATH"
  echo "   Tamanho: $(du -sh $DB_PATH | cut -f1)"
else
  echo "\n📁 Banco de dados será criado em: $DB_PATH"
fi

# 5. Verificar hooks globais
HOOKS_PATH="$HOME/.claude/hooks.json"
if [ -f "$HOOKS_PATH" ]; then
  echo "✅ Hooks registrados em: $HOOKS_PATH"
else
  echo "⚠️  hooks.json não encontrado em $HOOKS_PATH"
fi

echo "\n🚀 Setup completo! Abra Claude Code neste diretório:"
echo "   cd $(pwd) && claude"
echo ""
