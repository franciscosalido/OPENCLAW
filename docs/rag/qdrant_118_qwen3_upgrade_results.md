# Qdrant 1.18 + Qwen3 Embedding — Benchmark Results

**Status:** Inconclusive — Qwen3 embedding model not yet available locally  
**Generated:** 2026-05-24  
**Sprint:** Q18 Rebenchmark A2A  

---

## Context

The previous Q18 benchmark used `nomic-embed-text` (768 dimensions) as the
embedding model. This document records the re-benchmark using `Qwen3-Embedding-0.6B`
(1024 dimensions) as specified in the project's embedding roadmap.

---

## Embedding Models

| Property | Nomic (previous) | Qwen3 (target) |
|---|---|---|
| Model | `nomic-embed-text` | `Qwen/Qwen3-Embedding-0.6B` |
| Dimensions | 768 | 1024 |
| Provider | ollama | ollama |
| Query instruction | No | Yes |
| Collection | `quimera_benchmark_hybrid_118_nomic` | `quimera_benchmark_hybrid_118_qwen3` |
| Status | Available ✅ | Not installed ❌ |

---

## Qwen3 Availability

Probed on 2026-05-24:

```json
{
  "available": false,
  "error": "http_404",
  "expected_dimensions": 1024,
  "model": "Qwen/Qwen3-Embedding-0.6B",
  "provider": "ollama"
}
```

**Action required:** `ollama pull Qwen/Qwen3-Embedding-0.6B`

---

## Benchmark Infrastructure Changes (This Sprint)

### Bug Fixes

**A. `qdrant_client.__version__` — Already Fixed**  
`check_qdrant_118_readiness.py` already uses `importlib.metadata.version("qdrant-client")` correctly.

**B. `AsyncQdrantClient.search` — Already Fixed**  
`run_q18_benchmark_profile.py` already uses `query_points()` for all search operations.

**C. `_assert_safe_text` false positive — Fixed This Sprint**  
The safety guard was blocking `dense_vector_name` and `sparse_vector_name` metadata
fields due to substring matching of `"dense_vector"` without quotes. Fixed to use
quoted JSON key matching `'"dense_vector"'` so only exact data keys are rejected.

### New Capabilities

1. **`evaluation/probe_embedding_model.py`** — Detects embedding model availability
   and reports safe dimension/latency metadata. Supports Ollama, TEI, and
   OpenAI-compatible providers.

2. **Qwen3 profiles in runner** — 9 new profiles (`qdrant_118_qwen3_*`) added to
   `run_q18_benchmark_profile.py`. Each uses:
   - `Qwen/Qwen3-Embedding-0.6B` as the embedding model
   - 1024 dimensions
   - `quimera_benchmark_hybrid_118_qwen3` as the collection
   - Query instruction enabled

3. **Separate collections** — Nomic and Qwen3 use distinct collections to prevent
   dimension mixing. The collection name is validated against a whitelist.

4. **Qwen3 comparison scenarios** — 6 new scenarios added to `COMPARISONS`:
   - `qdrant_113_vs_118_qwen3_baseline`
   - `qdrant_118_qwen3_baseline_vs_balanced`
   - `qdrant_118_qwen3_python_rrf_vs_native_rrf`
   - `qdrant_118_qwen3_no_quant_vs_turboquant`
   - `qdrant_118_qwen3_dense_only_vs_hybrid`
   - `qdrant_118_nomic_vs_qwen3_embedding` ← embedding comparison

5. **`decide_qwen3_embedding()` function** — Separate decision logic for the Qwen3
   embedding evaluation, decoupled from the Qdrant version upgrade decision.

---

## Decisions

| Question | Decision | Evidence |
|---|---|---|
| Qdrant 1.18 accepted? | Deferred (from previous Q18-07) | See `qdrant_118_upgrade_results.md` |
| Qwen3 as default embedding? | **Inconclusive — model not available** | No benchmark data |
| Python RRF as ground truth? | **Yes** | Unchanged from Q18-07 |
| Native RRF experimental? | **Yes** | Unchanged from Q18-07 |
| TurboQuant experimental? | **Yes** | Unchanged from Q18-07 |

---

## Next Steps

1. Install Qwen3 embedding:
   ```bash
   ollama pull Qwen/Qwen3-Embedding-0.6B
   ```

2. Probe embedding:
   ```bash
   uv run python evaluation/probe_embedding_model.py \
     --provider ollama \
     --model Qwen/Qwen3-Embedding-0.6B
   ```

3. Run Qwen3 baseline:
   ```bash
   RUN_Q18_BENCHMARK_PROFILE=1 \
   uv run python evaluation/run_q18_benchmark_profile.py \
     --profile qdrant_118_qwen3_python_rrf \
     --output evaluation/results/qdrant_118_qwen3_python_rrf.json \
     --execute
   ```

4. Run all Qwen3 profiles and aggregator.

5. Update this document and ADR-0003 with actual results.

---

## Limitations

- No Qwen3 benchmark data exists yet.
- The Nomic baseline artifacts (`qdrant_118_*.json`) remain the operative ground truth.
- This document will be updated when Qwen3 embedding is installed and benchmarks are run.
- Do not promote Qwen3 based on expected dimensions alone — actual recall/NDCG evidence required.

---

## ADR References

- [ADR-018: Qdrant 1.18 Upgrade](../ADR/ADR-018-qdrant-118-upgrade.md)
- [ADR-0003: Qwen3 Embedding Baseline](../ADR/0003-qwen3-embedding-baseline.md)
