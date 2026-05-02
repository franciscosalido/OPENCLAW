# Gateway-1 Done Criteria

Gateway-1 is complete only when the opt-in proof-of-life smoke validates the local stack as a unit without remote providers, Qdrant mutation, real data, or sensitive logging.

| ID | Description | Component | Mandatory | Failure Meaning |
| --- | --- | --- | --- | --- |
| G1-01 dry_run_runner_ok | Agent-0 dry-run executes offline and returns the stable safe schema. | Agent-0 runner | true | The runner contract is not available without live services. |
| G1-02 local_urls_only | Ollama, Qdrant and LiteLLM URLs are localhost or 127.0.0.1 only. | Safety guard | true | The smoke could call a remote service and must stop. |
| G1-03 ollama_probe_ok | Ollama responds to read-only `GET /api/tags`. | Ollama | true | Local model runtime is not reachable. |
| G1-04 qdrant_probe_ok | Qdrant responds to read-only `GET /healthz`. | Qdrant | true | Local vector store is not reachable. |
| G1-05 litellm_probe_ok | LiteLLM responds to `GET /v1/models` and exposes required local aliases. | LiteLLM gateway | true | Local gateway or alias contract is not ready. |
| G1-06 local_chat_runner_ok | Agent-0 live default path returns safe schema through `local_chat`. | Agent-0 local chat | true | Default local execution is not operational. |
| G1-07 rag_path_or_explicit_fallback_ok | Agent-0 `--rag` succeeds via `local_rag` or explicitly falls back to `local_chat`. | Agent-0 RAG | true | RAG path neither works nor degrades honestly. |
| G1-08 forced_qdrant_degradation_ok | Injected Qdrant-like failure triggers the GW-17 fallback contract without stopping Qdrant. | Agent-0 fallback | true | Degraded-state safety is not reproducible. |
| G1-09 policy_block_no_model_call_ok | Policy block refuses before any model call. | Routing policy | true | Blocked requests may still execute models. |
| G1-10 sanitized_output_ok | Structured outputs contain no prompt, question, chunks, vectors, payloads or secrets. | Safety audit | true | Smoke artifacts may leak sensitive content. |
| G1-11 summary_report_written_ok | A structured JSON summary is written even when failures occur where possible. | Operator report | true | Operators cannot inspect proof-of-life outcome. |

Generated proof-of-life summaries are local artifacts and must not be committed.
