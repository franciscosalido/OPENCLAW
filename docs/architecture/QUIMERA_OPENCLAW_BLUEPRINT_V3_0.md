# Quimera/OpenClaw Blueprint V3.0

## Product Identity

Quimera is the product. OpenClaw is the repository.

The platform is local-first, security-first, and multi-agent. Local services are
the default path for model calls, retrieval, and deterministic computation.

## Target MVP Architecture

- Ollama runs local models.
- Qwen 3.0 14B is the primary local chat/reasoning model.
- `nomic-embed-text` provides local embeddings.
- Qdrant stores local RAG vectors.
- Python owns deterministic orchestration, validation, retrieval, prompt
  construction, and mathematical co-processing.
- LiteLLM becomes the single model gateway for model calls.
- GitHub remains the source of truth for issues, branches, and pull requests.

## Operational Source Of Truth

GitHub is the final integration surface for OpenClaw work. Local branches are
work areas, not the source of merge truth.

For every tracked change:

- sync local `main` from GitHub with `git pull --ff-only origin main`;
- open or update a GitHub Issue before implementation;
- create a feature branch from updated `main`;
- validate locally;
- commit and push the feature branch;
- open a GitHub PR to `main`;
- link the PR to the issue;
- merge only in GitHub after approval.

Local merges into `main` are not considered final integration.

## Gateway Boundary

LiteLLM is introduced as a model-call gateway, not as the owner of RAG state.

Gateway aliases:

| Alias | Purpose | Initial mapping |
| --- | --- | --- |
| `local_chat` | Default local chat | Ollama/Qwen |
| `local_think` | Local reasoning calls | Ollama/Qwen |
| `local_rag` | RAG answer synthesis | Ollama/Qwen |
| `local_json` | Structured local responses | Ollama/Qwen |
| `local_embed` | Embeddings for retrieval | Ollama/nomic-embed-text |

RAG remains in Qdrant:

- documents are chunked in Python;
- embeddings are generated locally;
- vectors are written to Qdrant;
- retrieval and context packing remain Python responsibilities;
- only model calls move behind the gateway in a later PR.

## Explicit Non-Goals for Gateway-0

- No remote provider routing.
- No FastAPI service.
- No quant tools.
- No real portfolio data.
- No secret handling beyond documenting that secrets must not be committed.
- No change to existing RAG runtime behavior.

## Security Levels

Level 0 never leaves the machine: real portfolio data, balances, credentials,
personal data, private documents, and sensitive logs.

Level 1 can leave only after sanitization: abstracted scenarios, anonymized
errors, synthetic examples, and generic architecture questions.

Level 2 is safe for remote: public documentation, generic code structure, toy
examples, and non-sensitive educational material.

Gateway-0 enables only the local path.
