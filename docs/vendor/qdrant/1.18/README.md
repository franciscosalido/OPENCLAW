# Qdrant 1.18 Vendor Notes

Snapshot date: 2026-05-23

Purpose: curated docs index for Q18 planning, not a full documentation mirror.

## Sources

| Topic | Source URL | Retrieval date | Reason |
|---|---|---:|---|
| Qdrant 1.18 release notes | https://qdrant.tech/blog/qdrant-1.18.x/ | 2026-05-23 | release-level feature overview |
| Qdrant GitHub release | https://github.com/qdrant/qdrant/releases/tag/v1.18.0 | 2026-05-23 | full changelog reference |
| Qdrant docs tree | https://qdrant.tech/documentation/ | 2026-05-23 | official documentation entry point |
| Vectors and named vectors | https://qdrant.tech/documentation/manage-data/collections/ | 2026-05-23 | update vector schema in v1.18 |
| Quantization / TurboQuant | https://qdrant.tech/documentation/manage-data/quantization/ | 2026-05-23 | TurboQuant and scalar comparison |
| Optimize performance | https://qdrant.tech/documentation/operations/optimization/ | 2026-05-23 | performance tuning entry point |
| Hybrid queries | https://qdrant.tech/documentation/search/hybrid-queries/ | 2026-05-23 | RRF and DBSF query API |
| Collections | https://qdrant.tech/documentation/manage-data/collections/ | 2026-05-23 | collection schema and vector configuration |
| Points / payload | https://qdrant.tech/documentation/manage-data/points/ | 2026-05-23 | point update and vector payload behavior |
| Configuration | https://qdrant.tech/documentation/operations/configuration/ | 2026-05-23 | runtime configuration reference |
| Administration | https://qdrant.tech/documentation/operations/administration/ | 2026-05-23 | low memory mode and strict mode |
| Security / audit tracing | https://qdrant.tech/documentation/operations/security/ | 2026-05-23 | tracing IDs in audit logs |
| API reference - delete vectors | https://api.qdrant.tech/api-reference/points/delete-vectors | 2026-05-23 | point-level named vector deletion |
| qdrant-client PyPI | https://pypi.org/project/qdrant-client/ | 2026-05-23 | Python client 1.18.0 distribution metadata |

## Stored Excerpts

None in this PR.

See also: `docs/specs/qdrant-1-18-upgrade/qdrant_1_18_research.md` for
curated feature assessment.

## Rules

- Do not vendor full docs.
- Do not scrape the entire site.
- Record source URL and retrieval date for each page.
- Prefer official docs and release notes.
- Treat this directory as an index, not as an offline source of truth.
