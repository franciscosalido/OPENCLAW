# Agent-0 Golden Questions

## Purpose

A0-PR03 adds citation-only golden questions for Agent-0. The harness checks
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

## Philosophy

The registry measures before building. Its job is not to prove that an LLM can
answer generic financial textbook questions from parametric memory. A query such
as "what is duration?", "how do you calculate EBITDA?" or "how does Selic affect
inflation?" is too weak for this benchmark because a model can answer it even
when retrieval cites the wrong local document.

Golden financial questions must be adversarial to dense-only retrieval in the
specific sense used by this sprint:

- the answer depends on the synthetic local corpus;
- the expected evidence is checked through `expected_doc_ids`;
- the wording contains document-local context or domain-specific phrasing;
- a semantically nearby but wrong document is a plausible retrieval failure;
- the question remains synthetic-only and contains no real holdings, broker
  data, private documents or position values.

A question belongs in the registry only when it maps to one corpus namespace,
references existing manifest documents, contributes real coverage to the
synthetic corpus and can be evaluated by safe citation metadata alone.

Internal questions:

| ID | Question | Expected Doc |
|---|---|---|
| `iq-001` | `qual o estado atual do GW-07?` | `internal_current_state` |
| `iq-002` | `qual o ultimo alias canonico de embeddings?` | `internal_decisions` |
| `iq-003` | `quais aliases tem timeout maior que 60s?` | `internal_claude_contract` |
| `iq-004` | `segundo o ADR-001 sintetico local, quais componentes definem o RAG-0 local-only e quais tecnologias ficam explicitamente excluidas?` | `internal_adr_rag_local_only` |
| `iq-005` | `no runbook sintetico local de RAG, quais comandos validam ingestao e consulta locais sem usar dados reais?` | `internal_rag_runbook` |

Internal questions cover every enabled synthetic internal document.

Financial questions:

| ID | Question | Expected Doc |
|---|---|---|
| `fq-001` | `segundo o documento sintetico local de curva de renda fixa, quais tres caracteristicas da curva ficticia devem ser recuperadas e por que o exemplo permanece abstrato?` | `financial_renda_fixa_curva` |
| `fq-002` | `no material sintetico local de liquidez em renda fixa, quais tres dimensoes diferenciam a analise e qual restricao sobre emissores reais aparece?` | `financial_renda_fixa_liquidez` |
| `fq-003` | `segundo o documento sintetico local de risco de credito, quais tres eixos hipoteticos estruturam a avaliacao e quais entidades reais sao explicitamente excluidas?` | `financial_renda_fixa_risco_credito` |
| `fq-004` | `no texto sintetico local de crescimento em valuation, como o exemplo educacional trata EBITDA e que tipo de dados o calculo declara nao usar?` | `financial_valuation_crescimento` |
| `fq-005` | `segundo o documento sintetico local de custo de capital, quais tres componentes formam a taxa de desconto hipotetica e qual limite de dados reais e declarado?` | `financial_valuation_custo_capital` |
| `fq-006` | `no material sintetico local de cenarios de valuation, quais tres cenarios para o ativo ficticio devem ser recuperados e quais referencias reais sao proibidas?` | `financial_valuation_cenarios` |
| `fq-007` | `segundo o documento sintetico local de ciclo de juros, quais tres fatores explicam a trajetoria hipotetica e que dado sensivel o texto exclui?` | `financial_macro_ciclo_juros` |
| `fq-008` | `no material sintetico local de balanco de riscos macro, quais tres grupos de risco devem aparecer e qual aviso sobre previsao ou carteira real acompanha o exemplo?` | `financial_macro_balanco_riscos` |
| `fq-009` | `segundo o documento sintetico local de expectativas macro, quais tres propriedades das expectativas ficticias sao comparadas e quais fontes privadas sao excluidas?` | `financial_macro_expectativas` |

Expected document IDs are validated against the A0-PR02 corpus manifests at
harness startup. Missing IDs raise `ValueError`; there is no silent warning.
The financial registry covers every enabled synthetic financial document and
keeps at least two active questions per financial domain.

## Routing

Question IDs define the namespace contract:

- `iq-*` must route to `internal` and `openclaw_internal`.
- `fq-*` must route to `financial` and `openclaw_financial`.

The harness validates the expected collection through
`assert_collection_namespace(...)` before retrieval. `openclaw_knowledge` is not
allowed.

`iq-*` and `fq-*` prefixes are namespace hints. When an `fq-*` question lacks a
domain keyword, routing still preserves `financial` / `openclaw_financial`
instead of silently falling back to `none`; confidence thresholds decide the
route, but the namespace evidence is not discarded.

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
