# ADR 004: Language, runtime and environment

**Status.** Accepted. **Date.** 2026-10-05 (revised the same day after review). **Deciders.** Founder/CEO, Engineering.

## Context
Phase 0 needs an importer, a trade-record schema and 18 research tests in eight weeks, built by one or two engineers. The product's Technical Design (API, database, deployment, show, LLM layer) is a week-8 document written from Phase 0 evidence. This ADR fixes the language, runtime and dependency discipline. The settled stack as a whole is in `docs/architecture/tech-stack.md`.

A first draft of this ADR said the product would "reuse the fund's regime code and tick loaders directly" and therefore match the fund's Python and library versions. That was wrong on two counts: Methodology §3 forbids fund code in the product repo, and matching the fund's numpy would have risked making the Bayesian stack uninstallable. **The fund's outputs cross the wall as data** (ADR 002); the product never imports fund code.

## Decision
| Concern | Choice |
|---|---|
| Language | **Python 3.11.** The minor version is pinned in `pyproject.toml` (`requires-python == "3.11.*"`) and `.python-version`; the exact patch is whatever `uv` resolves at lock time and is recorded in `uv.lock`. A Python version bump is a charged change (it can move a float's last bit through a dependency). |
| Environment | **uv**, with `uv.lock` committed. `pyproject.toml` carries bounded ranges (never `>=` without an upper bound); **`uv.lock` is the exact pin.** Same code + same lock → same bytes. |
| Dependency changes | A major-version bump of any runtime dependency is a charged change: pre-registered, run against the corpora, zero tier changes or it is a major version (Methodology §14). |
| Fund code | **None in this repo.** Regime labels, calendars and tick extracts arrive as Parquet data from the fund (ADR 002). Version parity with the fund is therefore not required. |

## Consequences
- The Canonical Trade Record (ADR 001) is the stability boundary; tooling below it may change at a minor version.
- Versions are chosen for the product's needs (JAX/NumPyro compatibility at the benchmark), not the fund's.
- `uv sync` reproduces the environment on any machine; Docker (ADR 005) wraps it for charged runs.

## Alternatives considered
- **R** — stronger statistics, no team skill, weak for production. Rejected.
- **Julia / Rust / Go** — speed without the statistics ecosystem. Rejected.
- **venv + pip, no lockfile** — "same deps" becomes a wish. Rejected.
- **Pin to the fund's exact versions** — couples the product to fund code the repo may not contain, and to a numpy the Bayesian stack may not accept. Rejected.
