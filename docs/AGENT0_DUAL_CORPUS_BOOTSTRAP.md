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

The original PR01 file `data/corpus/manifest.yaml` may still exist in the
repository. It is the legacy single-corpus Agent-0 ingestion manifest from
A0-PR01, not a dual-corpus or super manifest. A0-PR02 bootstrap entrypoints are
only:

- `data/corpus/internal/manifest.yaml`
- `data/corpus/financial/manifest.yaml`

`scripts/bootstrap_corpus.py` resolves manifests from those two closed roots
and must not read `data/corpus/manifest.yaml`.

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

All synthetic documents versioned in A0-PR02 pin `expected_hash` in their
corpus manifest. The value is the SHA256 of the raw file bytes. Verify-only
runs reject a document before chunking if the current file hash differs from
the pinned manifest value. This keeps the synthetic bootstrap corpus
deterministic and gives reviewers a simple tamper-detection gate.

After the first successful real `--commit` run, re-check the committed document
metadata against the manifest and re-pin `expected_hash` only if the versioned
source files intentionally changed. This keeps drift detection tied to the
curated corpus rather than to stale local reports.

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

Report file writing is intentionally owned by `scripts/bootstrap_corpus.py`.
`run_bootstrap()` returns a sanitized report object and performs no report file
I/O. This keeps the orchestration layer deterministic and makes CLI output
handling explicit.

## Legacy Qdrant Default

The older RAG store still defines `DEFAULT_COLLECTION_NAME` as
`openclaw_knowledge` for pre-existing RAG code paths. A0-PR02 does not change
that legacy default. The dual-corpus bootstrap path never relies on it:

- `scripts/bootstrap_corpus.py` derives the collection from the closed corpus
  mapping.
- `QdrantIngestionCommitStore` validates the mapped collection before creating
  a vector store.
- `CollectionGuard.assert_collection_namespace(...)` rejects
  `openclaw_knowledge`, empty names and arbitrary names for bootstrap commits.

Changing the legacy default is a separate migration concern outside A0-PR02.

## Sync Commit Boundary

The commit store is deliberately synchronous in A0-PR02. `_embed_chunks()` uses
`asyncio.run()` as a bridge around the existing async embedder contract and the
code comment at that call site marks the async-runtime footgun. Before wiring
bootstrap commit into FastAPI, pytest-asyncio or any already-running event
loop, replace that bridge with an async-safe commit path.

Open a GitHub follow-up issue for that replacement before any async integration
lands. The issue should cover the async-safe API shape, tests that run inside an
already-running event loop and proof that commit still writes only to the
mapped dual-corpus collection.

## Rollback

Rollback is collection-local. Drop or ignore only:

- `openclaw_internal`
- `openclaw_financial`

The bootstrap path must not touch `openclaw_knowledge`.
