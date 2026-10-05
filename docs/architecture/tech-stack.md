# Tech stack — settled 5 October 2026

*The reference. Decisions and their alternatives live in `docs/adr/` (001–005); this page is what they add up to. Stage markers follow `docs/methodology.md`.*

Two independent proposals (an internal one and an outside engineer's review) converged on the same core. The differences were about how much to set up before the first line of code, and one assumption — matching the fund's library versions so the product could run fund code — which was corrected: **fund outputs cross the wall as data; the product never imports fund code** (ADR 002, ADR 004).

## The stack

```
Language      Python 3.11 — minor pinned; exact patch recorded in uv.lock at lock time        ADR 004
Environment   uv + committed uv.lock; bounded ranges in pyproject, exact pins in the lock      ADR 004
Container     Docker, pinned base digest — for charged runs, not daily development            ADR 005
Data lake     Parquet (every file hashed) · DuckDB for queries                                ADR 005
Registry      SQLite (Phase 0) → Postgres 16 (Phase 1), schema written portable               ADR 005
Validation    pydantic v2, strict=True, extra='forbid' on every schema in services/shared     ADR 001
Tables        pandas + numpy; versions chosen for the product (JAX-compatible), not the fund   ADR 004
Bayesian      NumPyro (JAX), pending a benchmark vs PyMC + nutpie at the first model          ADR 006 (to write)
Concurrency   ProcessPoolExecutor across tests · content-addressed cache                     ADR 005
Testing       pytest · ruff · mypy on services/shared from day one · hypothesis on the
              load-bearing transformations                                                    Methodology §13
Lineage       hashlib sha256; every evidence object carries the framework hash               ADR 003
Market data   Fund → product as Parquet DATA, one-way, logged; folder now, bucket at stage 1  ADR 002, 005
Git           GitHub, a separate org from the fund, main + short-lived feature branches        ADR 002
CI            Stage 0: ruff · unit tests · hash-check. Stage 1: reproducibility,
              import-boundaries, research-gate, benchmark, deploy                             Methodology §12
```

## Decided now vs deferred

| Layer | Decided now | Deferred | Trigger |
|---|---|---|---|
| Language, environment | Python 3.11, uv + lock | — | — |
| Validation | pydantic strict | — | — |
| Lake, registry | Parquet + DuckDB; SQLite | Postgres 16 | Phase 1 |
| Tables | pandas | polars | Phase 1, on evidence (polars refuses silent nulls — philosophically aligned with "no silent drops") |
| Bayesian | NumPyro as the default | Final choice | The benchmark: M1 on one synthetic trader, 500 trades; wall time, ESS/s, R̂, divergences. Cleanest diagnostics wins, not nominal speed |
| Docker | Dockerfile with pinned digest | — | Digest pinned at the first charged run |
| CI | Three jobs | Four more | Stage 1 |
| Cloud, Terraform, bucket | — | All | First cloud resource |
| Product runtime (warm pool, async I/O, ≤ 90 s p95 per upload) | — | All | Technical Design, week 8 |
| LLM layer | Adapter pattern as a design rule | Provider, faithfulness suite | Stage 1; ADR when the layer exists |
| Frontend | — | TypeScript, React/Next.js, mobile-first web | Phase 1 |

## Compute budget for Phase 0
18 tests × ~8 robustness fits ≈ 150 fits per history. ~2,200 histories (20 partners, ~1,200 synthetic, 1,000 noise) ≈ 330,000 fits. At ~2 s per fit on 8 cores that is about **one day of wall time** on a single machine. No cloud is needed for Phase 0; the budget is restated with measured fits-per-hour after the benchmark.

## Build order
Schema (`ctr_v1.py`) → first broker adapter → reproducibility test → synthetic generator → **the Bayesian benchmark** → first model (M1) → first research test (B2). Docker and the three CI jobs are added alongside, not before. The benchmark cannot run before the schema and generator exist, so it is not step one.
