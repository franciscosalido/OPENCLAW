# PKD-00X - QUIMERA MCP Memory Fabric over LiteLLM

## Resumo executivo

Este PKD documenta a arquitetura canonica para acesso plug-and-play a memoria do
QUIMERA por todos os nos e agentes:

```text
Agent Nodes
  -> LiteLLM Proxy MCP Gateway
  -> QUIMERA Memory MCP Server
  -> Memory Repository
  -> PostgreSQL 18.4 / Qdrant
```

A decisao operacional e:

- O QUIMERA Memory MCP Server proprio e o contrato canonico de memoria.
- O server deve ser implementado com MCP Python SDK / FastMCP.
- LiteLLM Proxy e o gateway de entrada para agentes, chaves, times e permissoes.
- Docker MCP Toolkit/Gateway e permitido como camada auxiliar de
  desenvolvimento, empacotamento, catalogo ou MCPs externos.
- Docker MCP Toolkit/Gateway nao e o control plane canonico da memoria QUIMERA.
- Agentes nao acessam PostgreSQL nem Qdrant diretamente.

## Contexto

O QUIMERA possui memoria hibrida:

- PostgreSQL 18.4:
  - memoria temporal;
  - sessions;
  - turns;
  - agent_states;
  - entity_mentions;
  - futuro entity graph leve;
  - memoria relacional de longa duracao.
- Qdrant:
  - memoria vetorial;
  - Hybrid RAG;
  - semantic cache;
  - dense/sparse;
  - RRF/reranking.
- LiteLLM:
  - gateway LLM;
  - gateway MCP;
  - controle por key/team/org;
  - endpoint fixo para MCP tools.
- Ollama / Qwen3:
  - LLM local;
  - geracao e raciocinio local-first.
- MCP:
  - protocolo padrao de tools, resources e prompts para agentes;
  - transport principal: Streamable HTTP;
  - versao alvo: 2025-11-25;
  - endpoint interno recomendado: `/mcp`.

## Arquitetura

```text
Agent Node A / Agent Node B / CODEX / COWORK / UI
    |
    v
LiteLLM Proxy / MCP Gateway :4000
    |
    v
QUIMERA Memory MCP Server :7151/mcp
    |
    v
backend/memory repository layer
    |
    v
PostgreSQL 18.4 + Qdrant
```

LiteLLM e o ponto de entrada para agentes. O Memory MCP Server e o contrato
semantico de memoria. A repository layer encapsula `asyncpg` e Qdrant. Bancos
nao sao expostos aos agentes. Docker MCP e auxiliar, nao canonico.

## Portas e caminhos

| Componente | Porta / path | Papel |
|---|---:|---|
| LiteLLM Proxy | `4000` | LLM Gateway, MCP Gateway, auth e permissoes |
| QUIMERA Memory MCP Server | `7151`, `/mcp` | Contrato Streamable HTTP interno de memoria |
| PostgreSQL | `5432` | Memoria relacional-temporal, sem acesso direto por agentes |
| Qdrant | `6333` | Memoria vetorial, sem acesso direto por agentes |
| Docker MCP Gateway | opcional | Dev, catalogo, empacotamento e MCPs externos |

O QUIMERA Memory MCP Server deve fazer bind apenas em `127.0.0.1` ou rede
interna Docker. Ele nunca deve ser exposto publicamente sem auth.

## Contrato MCP

Tools iniciais read-only:

- `quimera.memory.health`
- `quimera.memory.session.get`
- `quimera.memory.turns.recent`
- `quimera.memory.agent_state.get`
- `quimera.memory.entity_mentions.for_turn`
- `quimera.memory.context.pack`

Tools write-gated:

- `quimera.memory.session.create`
- `quimera.memory.turn.append`
- `quimera.memory.agent_state.upsert`
- `quimera.memory.entity_mention.record`

Politica padrao:

- `read_tools_enabled = true`;
- `write_tools_enabled = false` por padrao;
- write tools exigem capability explicita;
- nenhuma tool retorna SQL bruto;
- nenhuma tool retorna connection string;
- nenhuma tool retorna embedding bruto;
- nenhuma tool retorna prompt bruto;
- nenhuma tool retorna secret;
- logs nao podem conter content bruto de turns, API keys, DSN ou vetores.

## Tool principal: context pack

`quimera.memory.context.pack` e o hipocampo operacional do QUIMERA: compacta
contexto util para um agente sem expor detalhes internos de banco, vetores ou
prompts sensiveis.

Entrada sugerida:

```json
{
  "agent_id": "string",
  "session_id": "uuid | null",
  "task_id": "string | null",
  "budget_tokens": "int",
  "include_recent_turns": "bool",
  "include_agent_state": "bool",
  "include_entities": "bool",
  "include_vector_hints": "bool"
}
```

Saida sugerida:

```json
{
  "schema_version": "quimera-context-pack-v1",
  "agent_id": "...",
  "session_id": "...",
  "recent_turns": [],
  "agent_state": {},
  "entities": [],
  "vector_hints": [],
  "memory_warnings": [],
  "redaction_applied": true
}
```

## Seguranca

- Validar `Origin` em Streamable HTTP.
- Fazer bind local em `127.0.0.1` ou rede interna Docker.
- Usar auth via LiteLLM para agentes.
- Usar allowlist de tools por key/team/org.
- Separar tools read-only e write.
- Manter write tools desligadas por padrao.
- Nao logar DSN.
- Nao logar senha.
- Nao logar prompt bruto.
- Nao logar embedding bruto.
- Nao expor PostgreSQL/Qdrant aos agentes.
- Usar IDs e `schema_version` em todo payload.
- Retornar sempre resposta sanitizada.

## Fronteira com Docker MCP

Docker MCP pode ser usado para:

- empacotar MCP servers;
- rodar MCP servers externos em containers;
- facilitar onboarding de desenvolvedores;
- usar catalogo/profile local;
- experimentos;
- integracao com ferramentas de terceiros.

Docker MCP nao deve ser usado para:

- definir o contrato canonico da memoria QUIMERA;
- substituir LiteLLM como gateway de agentes;
- permitir acesso direto aos bancos;
- decidir permissoes sem passar pela politica QUIMERA;
- virar dependencia obrigatoria do core memory path.

Referencia operacional: Docker MCP Catalog and Toolkit
<https://docs.docker.com/ai/mcp-catalog-and-toolkit/>.

## Nao-objetivos

Este PKD nao implementa:

- servidor MCP;
- endpoints REST;
- gRPC;
- migrations;
- schema SQL;
- Qdrant cache;
- Docker MCP profile;
- TimescaleDB;
- pgvector;
- Kronos;
- GraphRAG.
