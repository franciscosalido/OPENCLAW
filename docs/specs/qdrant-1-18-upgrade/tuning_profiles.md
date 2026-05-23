# Qdrant 1.18 Local-First Tuning Profiles

Status: draft
Scope: Q18-05 declarative tuning contracts only

## Scope

Q18-05 defines serializable local-first Qdrant tuning profiles for future A/B
benchmarks. The profiles are contracts, not operational changes.

This PR does not:

- apply config to Qdrant
- create or update collections
- run benchmarks
- run retrieval
- enable TurboQuant as a default
- export OpenTelemetry data

## Official Qdrant Optimization Background

The Q18 tuning set follows the Qdrant optimization themes already captured in
the Q18 research pack:

1. high speed with lower memory by using quantization
2. high precision with lower memory by using vectors/HNSW on disk
3. high precision with high speed by keeping hot data in RAM and using
   rescoring where quantization is evaluated

These are candidates for Quimera measurement. They are not assumed wins.

## Profiles

| Profile | Memory Goal | Latency Risk | Recall Risk | Default? | Experimental? | Benchmark Required? | Notes |
|---|---|---|---|---|---|---|---|
| `baseline_ram` | high memory control | low | low | no | no | no | Full-precision RAM control profile. |
| `balanced_local` | balanced local | low | low | yes | no | no | Conservative benchmark default. |
| `low_memory` | low memory | medium/high | low/medium | no | no | yes | On-disk dense vectors and HNSW, no quantization. |
| `turboquant_experimental` | low memory quantized | medium | unknown | no | yes | yes | TurboQuant bits4 + rescoring; benchmark before any adoption. |
| `high_precision_disk` | moderate/low memory | high | low | no | no | yes | Disk-backed accuracy-first profile without aggressive quantization. |

## Default Policy

The default profile is `balanced_local`.

TurboQuant is never default before benchmark. The only acceptable path to
promotion is measured evidence from Q18-07 showing recall, NDCG, p50/p95
latency and memory tradeoffs are acceptable.

## TurboQuant Policy

`turboquant_experimental` uses a conceptual TurboQuant `bits4` profile with
rescoring enabled. It is intentionally marked:

- `experimental = true`
- `requires_benchmark = true`
- `benchmark_readiness = experimental_requires_benchmark`

Before adoption, Quimera must compare:

- Recall@10
- NDCG@5
- latency p50
- latency p95
- peak RAM / memory report
- regression rate by query category

No ADR may promote TurboQuant as a default until those numbers exist.

## Search Params

The profile contracts externalize query/search parameters:

- `hnsw_ef`: benchmark-controlled candidate search breadth.
- `exact`: exact search flag for future controlled experiments.
- `quantization_rescore`: whether quantized candidates are rescored.
- `oversampling_factor`: future candidate expansion factor before rescoring.

Unset values mean the benchmark runner or Qdrant defaults control the value.

## Monitoring Handoff

Q18-05 prepares monitoring metadata without scraping endpoints or importing
OpenTelemetry.

Future benchmark code should record:

- `qdrant.profile`
- `qdrant.quantization`
- `qdrant.dense_on_disk`
- `qdrant.hnsw_on_disk`
- `qdrant.hnsw_ef`
- `qdrant.exact`
- `qdrant.quantization_rescore`
- `qdrant.oversampling_factor`
- `qdrant.experimental`

Future monitoring endpoints:

- `/metrics?per_collection=true`
- `/telemetry`

Q18-05 only returns probe config for these endpoints. It does not call them.

## Q18-07 Benchmark Handoff

Each future benchmark summary should include:

- `profile_config`
- `qdrant_server_version`
- `qdrant_client_version`
- `memory_report_available`
- `metrics_endpoint`
- `telemetry_endpoint`
- `latency_p50_ms`
- `latency_p95_ms`
- `recall_at_10`
- `ndcg_at_5`
- `peak_ram_mb`

This allows Q18-07 to compare memory, latency and quality without guessing
which profile generated each result.

## Non-goals

- no Qdrant mutation
- no retrieval changes
- no benchmark execution
- no OpenTelemetry exporter
- no Prometheus scrape
- no Grafana dashboard
- no Docker/config changes
- no TurboQuant default
