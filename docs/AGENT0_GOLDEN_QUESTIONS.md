# Agent-0 Golden Questions

## Purpose

A0-PR03 adds six citation-only golden questions for Agent-0. The harness checks
whether retrieval evidence cites the expected document from the expected
dual-corpus collection. It does not generate answers and does not judge answer
quality.

This PR depends on A0-PR02 bootstrap contracts:

- internal corpus -> `openclaw_internal`
- financial corpus -> `openclaw_financial`

## Question Manifests

Golden questions live in two independent manifests:

- `tests/golden/internal_questions.yaml`
- `tests/golden/financial_questions.yaml`

There is no super-manifest.

Internal questions:

| ID | Question | Expected Doc |
|---|---|---|
| `iq-001` | `qual o estado atual do GW-07?` | `internal_current_state` |
| `iq-002` | `qual o ultimo alias canonico de embeddings?` | `internal_decisions` |
| `iq-003` | `quais aliases tem timeout maior que 60s?` | `internal_claude_contract` |

Financial questions:

| ID | Question | Expected Doc |
|---|---|---|
| `fq-001` | `o que e duration de renda fixa?` | `financial_renda_fixa_curva` |
| `fq-002` | `como calcular o EBITDA?` | `financial_valuation_crescimento` |
| `fq-003` | `como a Selic afeta a inflacao?` | `financial_macro_ciclo_juros` |

Expected document IDs are validated against the A0-PR02 corpus manifests at
harness startup. Missing IDs raise `ValueError`; there is no silent warning.

## Routing

Question IDs define the namespace contract:

- `iq-*` must route to `internal` and `openclaw_internal`.
- `fq-*` must route to `financial` and `openclaw_financial`.

The harness validates the expected collection through
`assert_collection_namespace(...)` before retrieval. `openclaw_knowledge` is not
allowed.

## Citation Contract

`Citation` is a frozen dataclass with only safe retrieval metadata:

- `question_id`
- `source_id`
- `doc_id`
- `chunk_id`
- `corpus`
- `collection_name`
- `origin_path`
- `score`
- `rank`
- `retrieval_mode`
- optional `chunk_index`

It never includes answer text, question text, chunk text, vectors, embeddings,
payloads or prompts.

## Dry-Run Mode

Dry-run is the default:

```bash
uv run python scripts/run_golden_questions.py --dry-run --report-out /tmp/openclaw_golden_questions.json
```

Dry-run uses a fake retriever backed by the corpus manifests. It performs no
Qdrant calls, no Ollama calls, no LiteLLM calls and no LLM generation.

## Smoke Mode

Smoke mode is opt-in only:

```bash
RUN_GOLDEN_SMOKE=1 uv run python scripts/run_golden_questions.py --smoke
```

A0-PR03 does not wire a live retriever. Future smoke work may add a real
retriever, but it must still avoid answer generation and preserve the sanitized
report contract. In this PR, `--smoke` exits with code `2` even when
`RUN_GOLDEN_SMOKE=1` is present because the live retriever is intentionally not
wired yet.

## Report Schema

The report contains:

- `run_id`
- `timestamp_utc`
- `mode`
- `total_questions`
- `enabled_questions`
- `skipped_questions`
- `evaluated_questions`
- `passed`
- `failed`
- `coverage`
- `citation_hit_rate`
- `p50_query_ms`
- `p95_query_ms`
- `per_question`

`coverage` is the executed-question coverage: enabled/evaluated questions
divided by total loaded questions. It is separate from `citation_hit_rate`,
which is passed citation checks divided by evaluated questions.

Per-question rows contain only:

- `question_id`
- `expected_corpus`
- `expected_collection`
- `expected_doc_ids`
- `citation_present`
- `matched_doc_ids`
- `latency_ms`
- `status`
- `failure_reason`

Forbidden report keys include answer, text, query, question, raw text,
normalized text, chunks, chunk text, retrieved text, vectors, embeddings,
payloads, prompts, API keys, authorization headers, raw exceptions, tracebacks,
absolute paths and usernames.
