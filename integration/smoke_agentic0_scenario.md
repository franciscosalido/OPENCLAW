# PR-08 Agentic0 Smoke Scenario

1. Build an integration health report.
2. Validate LiteLLM as the only Agentic0 runtime gateway.
3. Validate configured MCP Postgres and MCP Qdrant servers.
4. Prepare deterministic HybridRAG synthetic fixture.
5. Call LiteLLM chat completion with safe IDs and counts only.
6. Generate JSON and Markdown artifacts.

The scenario never sends raw chunks, vectors, prompts, secrets or real data to
artifacts.
