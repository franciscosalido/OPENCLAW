# Agent-0 Golden Questions

This directory contains the stable synthetic question registry for the Agent-0
golden benchmark harness.

## Filosofia

The registry exists to measure before building. In RAG-1A, the hypothesis is:

> dense-only retrieval can miss Brazilian financial corpus details when the
> query depends on exact identifiers, domain-specific wording, synthetic local
> facts or narrowly scoped document evidence; the project must measure that gap
> before introducing any hybrid retrieval layer.

The benchmark is not meant to prove that a language model can answer generic
finance questions from parametric memory. Questions such as "what is duration?"
or "how do you calculate EBITDA?" are weak benchmark items because the model can
answer them without retrieving the right local document. They do not expose
whether the retriever found the intended evidence.

A useful golden question is adversarial in a specific way:

- The answer must depend on the synthetic local corpus, not on general model
  knowledge.
- The expected document must be verifiable through `expected_doc_ids`.
- The wording should include a concrete domain clue that can stress retrieval:
  document-local phrasing, exact financial terminology, corpus-specific context
  or a detail that would be ambiguous without the right citation.
- Dense-only should have a plausible failure mode, such as confusing nearby
  concepts, over-weighting semantic similarity, or missing an exact domain term.
- The question must remain safe: synthetic-only, no real holdings, no private
  documents, no broker data and no position values.

Acceptance criteria for adding or keeping a question in this registry:

- It maps to exactly one corpus namespace and collection.
- `expected_doc_ids` references existing documents in the matching corpus
  manifest.
- It is answerable only with the intended local evidence.
- It contributes coverage to a real domain or document already present in the
  synthetic corpus.
- It avoids generic textbook prompts unless the local document adds a specific
  synthetic detail that must be recovered.
- It can be evaluated by citation presence without serializing question text,
  answer text, chunks, prompts, vectors, payloads or secrets into reports.

A0-PR03 uses only the split citation manifests:

- `internal_questions.yaml`
- `financial_questions.yaml`

Current registry shape:

- 5 internal questions cover every enabled document in
  `data/corpus/internal/manifest.yaml`.
- 9 financial questions cover every enabled document in
  `data/corpus/financial/manifest.yaml`.
- Financial coverage is balanced across the current synthetic domains:
  `renda_fixa`, `valuation` and `macroeconomia`.
- The financial registry includes the specialized documents for credit risk,
  balance of macro risks, macro expectations and cost of capital.
- The dry-run harness validates citation contracts only; it does not generate
  answers and does not call live retrieval services.

The pre-existing `questions.yaml` file belongs to the older Gateway golden
question harness and uses a different schema. It is not an A0-PR03
super-manifest and is not loaded by `scripts/run_golden_questions.py`.

Reports are written to `tests/golden/reports/` and are intentionally ignored by
Git. Do not commit generated reports unless a future baseline-update issue
explicitly authorizes it.

Baseline policy:

- The registry is synthetic-only.
- No real tickers, companies, funds, portfolios or private data are allowed.
- Dry-run reports are useful for schema validation only.
- The first live baseline should preferably use the median of 3 local runs.
- Live baseline publication is deferred until an explicit future decision.
