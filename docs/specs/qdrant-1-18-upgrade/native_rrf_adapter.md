# Q18-06 Native RRF Adapter

Status: draft
Scope: experimental comparison adapter only

## Scope

Q18-06 compares Python `RRFFusion` against Qdrant native RRF / Weighted RRF
concepts using the same dense+sparse benchmark collection contract.

This PR creates an opt-in adapter and offline comparison helpers. It does not
change production retrieval behavior.

## Rule of Gold

Python RRFFusion continua fonte de verdade.

Qdrant native RRF and native Weighted RRF are experimental benchmark backends.
Native scores are diagnostic. They are not the primary equivalence criterion.

## Qdrant Query API Pattern

The future live path uses Qdrant Query API prefetch with the same named vectors
defined in Q18-04:

- sparse prefetch: `using="sparse"`
- dense prefetch: `using="dense"`
- fusion query: native RRF

The conceptual prefetch order is:

```python
prefetch_order = ("sparse", "dense")
```

Weighted RRF weights must follow prefetch order. For example:

```python
semantic_hybrid = {"dense": 1.30, "sparse": 1.00, "k": 60.0}
weights_for_qdrant = [1.00, 1.30]  # sparse first, dense second

lexical_hybrid = {"dense": 1.00, "sparse": 1.40, "k": 60.0}
weights_for_qdrant = [1.40, 1.00]  # sparse first, dense second
```

## Score Comparison Policy

Do not compare exact RRF scores as the primary equivalence metric.

Reasons:

- Qdrant native RRF can use zero-based internal ranks.
- Python `RRFFusion` uses the Quimera deterministic rank contract.
- Tie-break behavior can differ while top-k overlap remains acceptable.
- Native scores can be scaled or represented differently by the server.

Compare:

- overlap_at_k
- jaccard_at_k
- order_equal
- set_equal
- rank_delta_mean
- rank_delta_max
- tie_break_notes
- latency_python_ms
- latency_native_ms

## Dual-Profile MCP Future Design

RAG-03 should start with one MCP server and two retrieval tools, not two
mandatory TCP ports.

Suggested future tools:

```python
async def semantic_hybrid_search(query_hash: str, top_k: int = 10) -> object:
    ...

async def lexical_hybrid_search(query_hash: str, top_k: int = 10) -> object:
    ...
```

Both tools should use:

- same Qdrant collection
- same named vectors: `dense` and `sparse`
- same metadata
- same payload validation
- same Python `RRFFusion` source of truth until benchmark approval

Differences:

- `semantic_hybrid_search` uses dense-heavy `semantic_hybrid`
- `lexical_hybrid_search` uses sparse-heavy `lexical_hybrid`

Fallback:

- ambiguous query style routes to `neutral`
- native Qdrant failure returns Python RRF in laboratory fallback helpers

## Query Style Heuristic

The deterministic classifier uses no LLM and no network.

Signals:

- tickers such as `PETR4` and `MXRF11`
- financial acronyms: `CRI`, `CRA`, `CDI`, `IPCA`, `CDB`, `FII`, `ETF`, `LCI`,
  `LCA`, `DY`, `FGC`
- numeric/coded tokens
- uppercase ratio
- long natural-language question shape

Examples:

| Query shape | Profile |
|---|---|
| `MXRF11 DY CDI` | `lexical_hybrid` |
| `qual fundo imobiliario parece adequado para renda mensal?` | `semantic_hybrid` |
| `renda fixa` | `neutral` |

## Observability

Events and attributes must not log query literal, payloads, vectors,
embeddings or chunk text.

Allowed fields:

- `query_id`
- `query_hash`
- `profile_name`
- overlap/order metrics
- latency metrics
- backend names
- Qdrant server/client versions

OpenTelemetry-compatible attributes are plain dictionaries only. Q18-06 does
not import or configure OpenTelemetry.

## Non-goals

- No MCP server in Q18-06.
- No live MCP tools.
- No DBSF.
- No reranker.
- No ColBERT or multivectors.
- No collection mutation.
- No ingest/upsert.
- No native RRF default.
- No replacement of Python `RRFFusion`.

## Acceptance

- Adapter opt-in.
- Python default preserved.
- Divergences are serializable and safe.
- Tests are offline.
- Docs state that MCP is future-only.
- Python RRFFusion continua fonte de verdade.
