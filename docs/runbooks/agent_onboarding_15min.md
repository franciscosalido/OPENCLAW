# Agent Onboarding In 15 Minutes

## Variables

Required local variables are managed outside version control:

- `QUIMERA_LLM_BASE_URL`
- `QUIMERA_LLM_API_KEY`
- `LITELLM_MASTER_KEY`
- `QUIMERA_POSTGRES_DSN` or local Postgres host variables

## LiteLLM Virtual Key

Ask the human operator for the local LiteLLM virtual key. Never log it and
never paste it into docs.

## MCP Tools

Discover MCP tools through LiteLLM config and local MCP registry. Agentic0 uses
explicit `allowed_tools`; wildcard tools are forbidden.

## Never Do

- DB direto.
- wildcard tools.
- Nível 0 data in spans or logs.
- provider remoto without explicit policy.
- direct Qdrant, Postgres or Ollama bypass from agent runtime.

## Minimum Command

```bash
./run_smoke.sh --quick
```
