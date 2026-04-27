# Quimera/OpenClaw LiteLLM Sprint PR Prompts V3

## Sprint Intent

Prepare LiteLLM as the single model gateway while preserving the local-only RAG
pipeline and avoiding runtime behavior changes until the contract is reviewed.

## Mandatory GitHub Workflow

Every PR prompt in this sprint must be executed through GitHub:

1. Sync local `main` with `git pull --ff-only origin main`.
2. Open or update a GitHub Issue before implementation.
3. Create the feature branch from updated `main`.
4. Validate locally.
5. Commit, push, open a GitHub PR, and link the issue.
6. Merge only through GitHub after approval.

Do not treat local `main` as the final integration point. If the working tree is
dirty, preserve or split the work before syncing or replaying branches.

## PR 1: Gateway Prep Contracts

Branch: `feat/gateway-prep-contracts`

Goal: add the gateway decision record, blueprint, setup guide, LiteLLM local
alias config, and domain exceptions without wiring runtime calls yet.

Acceptance:

- `config/litellm_config.yaml` defines `local_chat`, `local_think`,
  `local_rag`, `local_json`, and `local_embed`.
- Chat aliases map to local Ollama/Qwen.
- Embedding alias maps to local Ollama/nomic-embed-text.
- Remote providers are absent or documented only as future placeholders.
- FastAPI is documented as intentionally out of the MVP path.
- RAG remains in Qdrant; only future model calls pass through LiteLLM.
- Gateway domain exceptions do not depend on LiteLLM internals.
- Existing tests still pass.

## Follow-Up PRs

Future PRs should stay small:

- load and validate gateway configuration;
- add a local LiteLLM smoke command;
- route embeddings through the gateway only after RAG behavior is covered;
- route local chat generation through the gateway;
- add sanitization and audit contracts before any remote fallback.

Remote providers remain out of scope until explicit approval.
