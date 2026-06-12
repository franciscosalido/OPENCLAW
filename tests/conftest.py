"""conftest.py — configurações globais de teste para o projeto OpenClaw.

Este arquivo é carregado automaticamente pelo pytest antes de qualquer test.
"""

from __future__ import annotations

import warnings

# ---------------------------------------------------------------------------
# Suprimir warning de versão do qdrant-client em contexto de testes.
#
# Contexto técnico:
#   - qdrant-client instalado: 1.18.0 (versão mais recente no PyPI em jun/2026)
#   - servidor Qdrant: 1.18.2
#   - Compatibilidade: SIM — is_compatible() verifica apenas major.minor;
#     1.18.x == 1.18.x passa o check com folga.
#
# Causa do warning (PR #1168 do qdrant-client):
#   A partir da 1.17.1, o check de versão roda em um daemon thread separado para
#   não bloquear clientes async. O thread faz httpx.get(rest_uri) em background.
#   Quando o QdrantClient é criado durante inicialização de um teste e encerrado
#   rapidamente (fixture teardown ou self.skipTest()), o daemon thread pode disparar
#   num momento em que a conexão já foi encerrada ou o event loop foi destruído,
#   levantando uma Exception capturada pelo bloco `except Exception` em
#   qdrant_remote.py:290 → gera o UserWarning mesmo sendo versões compatíveis.
#
# Ação necessária:
#   Remover este filtro quando qdrant-client >= 1.18.2 estiver disponível no PyPI
#   (executar: uv lock --upgrade-package qdrant-client)
# ---------------------------------------------------------------------------
warnings.filterwarnings(
    "ignore",
    message=r"Failed to obtain server version\..*",
    category=UserWarning,
)
