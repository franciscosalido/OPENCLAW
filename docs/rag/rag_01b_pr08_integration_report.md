# RAG-01B PR-08 Integration Report

Status: `skipped`
Correlation ID: `eb12379051ee493baf9ca588399a8ccf`

## Services

- `litellm`: `fail`
- `ollama`: `ok`
- `postgres`: `fail`
- `qdrant`: `fail`

## HybridRAG

- quality_mode: `offline_synthetic_fixture`
- quality_evidence: `deterministic_rrf_fixture`
- live_quality_checked: `False`
- quality_warning: `live_nomic_hybrid_validation_required`
- dense_ok: `True`
- sparse_ok: `True`
- hybrid_ok: `True`

## Latency

- measurement_mode: `degraded_no_live_stack`
- sample_count: `0`
- p95_ms: `None`
- p95_warning: `not_measured_stack_unavailable`

## Agentic0

- final status: `skipped`
- model: `qwen3-local`

## Warnings

- litellm model introspection unavailable
- litellm unavailable; LLM synthesis skipped

## PR-09 Handoff

- Multi-agent permissions, Kronos and autonomous tool-use hardening.
