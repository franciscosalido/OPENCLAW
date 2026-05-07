# Agent-0 Controlled Corpus Ingestion

## Purpose

A0-PR01 adds a contract-first ingestion path for curated Agent-0 corpus
documents. The default behavior is verification only: validate the manifest,
reject unsafe documents, fingerprint raw files, parse local content, deduplicate
by exact hash, reuse the RAG chunker, and emit a sanitized report.

The sprint uses synthetic corpus documents only. It does not ingest real
financial data, private documents, portfolio data, broker data or production
sources.

## Manifest Schema

The source of truth is `data/corpus/manifest.yaml`.

Each document declares:

- `source_id`
- `doc_id`
- `origin_path`
- `source_type`: `md` or `pdf`
- `domain`
- `language`: `pt-BR`
- `license`
- `contains_pii`
- `curation_status`: `approved`, `pending` or `rejected`
- `ingestion_policy`: `internal` or `financial`
- `enabled`

Optional fields:

- `expected_hash`
- `expected_normalized_text_hash`
- `notes`

Paths are relative to `data/corpus`. Absolute paths and path traversal are
rejected. Disabled documents are skipped. Documents marked with
`contains_pii: true` are rejected before parsing.

## Verify-Only Default

Run:

```bash
uv run python scripts/ingest_corpus.py --manifest data/corpus/manifest.yaml --report-out /tmp/openclaw_ingest_verify.json
```

Verify-only validates, fingerprints, parses, sanitizes, deduplicates, chunks and
reports. It does not call Qdrant mutating methods such as collection creation,
upsert or delete.

## Commit Semantics

Commit mode is explicit:

```bash
uv run python scripts/ingest_corpus.py --commit --manifest data/corpus/manifest.yaml
```

`--commit` requires an explicit `--manifest`. Pending, rejected, PII, duplicate,
parser-failed or hash-mismatched documents block commit by default. A future
writer can be attached through the pipeline commit-store abstraction; the CLI
does not connect to live Qdrant in this PR.

`--collection` is accepted only with `--commit`.

## PII Policy

The sanitizer rejects:

- manifest-declared PII via `contains_pii: true`
- CPF with punctuation
- CPF without punctuation
- email address
- Brazilian phone with DDD

Reports include only the safe rejection category and never the matched string.

## Report Schema

The report includes:

- `run_id`
- `timestamp_utc`
- `mode`
- `manifest_path_relative`
- `manifest_sha256`
- `total_documents`
- `enabled_documents`
- `approved_documents`
- `rejected_documents`
- `skipped_documents`
- `duplicate_documents`
- `parsed_documents`
- `chunked_documents`
- `coverage`
- `p50_ingestion_ms`
- `p95_ingestion_ms`
- `per_document`

Each document entry includes:

- `doc_id`
- `source_id`
- `source_type`
- `domain`
- `ingestion_policy`
- `status`
- `rejection_reason`
- `file_sha256`
- `normalized_text_sha256`
- `chunk_count`
- `latency_ms`

## Forbidden Fields

Reports must not contain these key names anywhere:

`text`, `raw_text`, `normalized_text`, `chunk`, `chunks`, `chunk_text`,
`vector`, `vectors`, `embedding`, `embeddings`, `payload`, `prompt`, `answer`,
`api_key`, `authorization`, `headers`, `secret`, `raw_exception`,
`exception_message`, `traceback`, `local_absolute_path`, `username`.

## Synthetic Corpus Limitation

The included corpus contains ten small Markdown fixtures in PT-BR across
`macroeconomia`, `renda_fixa`, `valuation` and `internal`. PDF parsing is
implemented only through an already-available `pypdf` dependency. No PDF
fixture or new parser dependency is added in this PR.

## p95 Metric

`p50_ingestion_ms` and `p95_ingestion_ms` are computed over successfully chunked
documents. The measured window covers local file hash, parsing, PII scan,
normalized-text hash and chunking. It does not include Qdrant, embeddings,
remote calls or live services.

## Rollback and No-Op Behavior

Verify-only mode is a no-op for Qdrant and can be rerun safely. Removing the
manifest entries or disabling documents stops future ingestion attempts without
deleting or rewriting any vector collection. Commit wiring remains isolated
behind explicit mode and an injected store abstraction.

## PR02 Follow-Ups

Before any real Qdrant write path is enabled, PR02 should add:

- `ingested_at` to the committed chunk metadata/report contract.
- A constrained `financial_domain` field with `null`, `macroeconomia`,
  `renda_fixa` and `valuation`, replacing the current free-form PR01 `domain`
  where appropriate.
- A real-document PII policy that treats `contains_pii: false` as an explicit
  curator attestation, because unformatted CPF regex detection can collide with
  legitimate 11-digit financial identifiers.
- An optional PDF dependency such as `pypdf>=4.0` before PDFs become accepted
  corpus inputs beyond fail-safe parser-unavailable behavior.
- Dynamic ingestion chunk config loading, instead of relying only on the PR01
  defaults that currently mirror the RAG chunker constants.
