# QUIMERA Working Memory Qdrant

PR-10 implements the first hot vector working memory for active agent/session
state.

Canonical contract:

- Qdrant collection `quimera_working_memory` is the hot path.
- Named vector `work-dense` uses size `768`, distance `Cosine`, `on_disk=false`.
- Postgres/pgvector checkpoints are the durable restore source.
- Working memory is not HybridRAG, not semantic cache, and not canonical
  long-term memory.
- Agents must access working memory through repository/MCP/LiteLLM surfaces,
  not direct SDK calls.

Safety:

- No raw prompt, response, answer, chunk, document text, vector, DSN, token,
  password or secret in payloads, logs or reports.
- `safe_summary` is capped at 512 characters.
- All query and cleanup paths are scoped by `agent_id` and `session_id`.

Restore:

- Default restore merges points by ID.
- Replace restore is disabled unless explicitly enabled.
- Replace can only remove points for the same agent/session scope.
