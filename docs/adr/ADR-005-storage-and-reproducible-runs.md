# ADR 005: Storage, and the environment for charged runs

**Status.** Accepted. **Date.** 2026-10-05. **Deciders.** Founder/CEO, Engineering.

## Context
Two kinds of data with two shapes: the **lake** (raw exports, CTR, features, enriched trades — written once, read by analysis) and the **registry** (evidence objects — transactional, append-only, read by the show). Phase 0 runs on one machine; Phase 1 has a product and a server.

## Decision
| Store | Phase 0 | Phase 1 | Why |
|---|---|---|---|
| **Lake** | Parquet files, every file hashed and the hash recorded; **DuckDB** for queries | Same | Columnar, compressed, deterministic; no server to run or secure |
| **Registry** | **SQLite**, append-only, transactional | **Postgres 16**, planned migration | SQLite handles Phase 0 volume; the schema is written portable (no SQLite-specific SQL, no single-writer assumptions) so the migration is a move, not a rewrite |
| **Raw exports** | Immutable folder outside the repo, hashed at ingestion (Methodology §7) | Object store, same rule | Never modified, never committed |
| **Market data from the fund** | A **read-only folder** the fund exports Parquet into; every read logged with file hash and timestamp | A read-only bucket in the product's cloud account, same log | One-way, logged; the wall (ADR 002) |
| **Charged runs** (week-7 isolation read, the gate, any run whose result is recorded in the DOF ledger) | **Docker**, pinned base-image digest recorded in the run manifest beside the framework hash | Same | "Same bytes across machines" must be true for the runs that count. Daily development uses `uv sync` on the engineer's machine; Docker is not a daily requirement |
| **Cache** | Content-addressed: every stage's output keyed by the hash of its inputs | Same | A re-run after a code change skips unchanged stages; the second run of a history is a lookup |
| **Parallelism** | `ProcessPoolExecutor` across tests, sized to cores | Plus a warm worker pool and async I/O for the product | Phase 0 compute (~330k model fits) is about a day on 8 cores; no cloud needed |

## Consequences
- Two stores, two purposes; nothing is forced into the wrong shape.
- The Dockerfile lives at `infra/docker/Dockerfile`; its digest is pinned at the first charged run and recorded in `manifest.json`.
- Terraform, a cloud account and the bucket arrive with the first cloud resource, not before.

## Alternatives considered
- **Postgres from day one** — a server to run, back up and secure before there is a product. Rejected for Phase 0.
- **One store for everything** — DuckDB is the wrong shape for append-only transactional writes; SQLite is the wrong shape for columnar analysis. Rejected.
- **Docker for all development** — on a Mac, JAX inside a container is slower and the friction buys nothing until a run is charged. Rejected; Docker for charged runs only.
