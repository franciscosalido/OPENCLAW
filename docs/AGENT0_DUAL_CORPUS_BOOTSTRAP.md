# Agent-0 Dual Corpus Bootstrap

## Purpose

A0-PR02 separates Agent-0 bootstrap into two controlled corpora and two Qdrant
collections:

- internal corpus -> `openclaw_internal`
- financial corpus -> `openclaw_financial`

The bootstrap path wraps the A0-PR01 ingestion pipeline. It does not duplicate
manifest validation, parsing, sanitization, fingerprinting, deduplication or
chunking.

## Corpus Roots

The independent roots are:

- `data/corpus/internal/`
- `data/corpus/financial/`

Each root has its own `manifest.yaml`. There is no dual or super manifest.
Manifest paths are relative to their corpus root and must remain under
`data/corpus/`. Symlinks are not used.

## Collection Mapping

The namespace mapping is closed:

| Corpus | Collection |
|---|---|
| `internal` | `openclaw_internal` |
| `financial` | `openclaw_financial` |

The bootstrap CLI does not accept arbitrary collection names. The collection
guard rejects empty names, `openclaw_knowledge` and any name outside the
allowlist.

## Verify-Only Default

Run internal verification:

```bash
uv run python scripts/bootstrap_corpus.py --corpus internal --verify-only --report-out /tmp/openclaw_internal_bootstrap.json
```

Run financial verification:

```bash
uv run python scripts/bootstrap_corpus.py --corpus financial --verify-only --report-out /tmp/openclaw_financial_bootstrap.json
```

Verify-only validates, parses, sanitizes, fingerprints, chunks and reports. It
does not instantiate the Qdrant commit store and does not mutate Qdrant.

## Commit Semantics

Commit is explicit:

```bash
uv run python scripts/bootstrap_corpus.py --corpus internal --commit
uv run python scripts/bootstrap_corpus.py --corpus financial --commit
```

Commit mode writes only to the mapped collection for the selected corpus. The
namespace guard runs before collection creation or upsert. Pending, rejected,
PII, duplicate or hash-mismatched documents remain blocked by the A0-PR01
pipeline.

## Idempotence

Bootstrap idempotence is document-hash based:

- matching `file_sha256` -> `skip_unchanged`
- matching `normalized_text_sha256` -> `skip_unchanged`

The collection existing by itself is not enough to skip documents. Hashes must
match document metadata.

## Metadata

Committed chunks carry safe metadata:

- `corpus`
- `namespace`
- `collection_name`
- `source_id`
- `doc_id`
- file and normalized text hashes
- active embedding backend/model/dimensions/contract/alias

Financial documents must declare `financial_domain` as one of
`macroeconomia`, `renda_fixa` or `valuation`.

## Query Dry-Run Metrics

Bootstrap reports include offline query dry-run p95 metrics for both mapped
collections:

- `internal_query_p95_ms`
- `financial_query_p95_ms`
- `query_dry_run_p95_ms` for the selected corpus

The dry-run uses fake local embedding/search planning only. It does not call
Qdrant and does not generate LLM answers.

## Reports

Reports are sanitized and include counts for parsed, chunked, embedded,
upserted, skipped unchanged, rejected, duplicates, coverage and p50/p95
ingestion timing.

Reports must not include text, chunks, vectors, embeddings, payloads, prompts,
answers, API keys, authorization headers, raw exceptions, tracebacks, absolute
paths or usernames.

## Rollback

Rollback is collection-local. Drop or ignore only:

- `openclaw_internal`
- `openclaw_financial`

The bootstrap path must not touch `openclaw_knowledge`.
