# Trade DNA — Repository Methodology

*Version 1.0 · October 2026 · Adopted 5 Oct 2026 with staged activation (below) · Owner: Engineering Lead*

---

## Status and activation — read before §0

This document is the destination. It is written for a team of ten with cloud infrastructure, a web app and a release process. The repository today has one engineer and two usable tradebooks, and a rule that is written but not followed teaches the team that rules are optional. So every rule below carries a stage, and **only the rules at the current stage are enforced.** Moving a rule to an earlier stage is a one-line PR to this table.

**Current stage: 0.**

| Stage | When | What is enforced |
|---|---|---|
| **0** | Phase 0 — now. One or two engineers | §1 the invariant · §2 the six rules (as habits and one test each, not as CI) · §3 the wall (separate repo; accounts and secret stores split at stage 1) · §4 the hash, checked by `make hash-check` · §5 the layout — a folder is created when its first file exists, never before · §7 immutability and the regeneration test · §8 schema-by-file · §10 the LLM boundary as a design decision · `main` + `feature/*` branches, Conventional Commits · three ADRs (CTR, the wall, the hash) · **§15 as a manual runbook** (`docs/runbooks/data-deletion.md`), because deletion was promised to recruits on 4 Oct · §18 build order |
| **1** | Phase 1 — first paying subscribers | §6 README rule · §9 import-linter in CI · §11 `develop` branch and PR template · §12 CI gates (lint, type, unit, reproducibility, hash, boundaries) · §13 coverage targets · §14 managed secret store, separate from the fund's · §15 the deletion service · faithfulness suite on the composer |
| **2** | Phase 2 — team of ten | §12 nightly Research Gate · `infra/` as Terraform · quarterly secret audit · everything else |

**Two corrections to the text below, applied on adoption:** the hash command on macOS is `shasum -a 256` (Linux: `sha256sum`); the Makefile uses the portable form. The pre-registration file lives at `services/research/prereg/framework_v1.yaml`, as Research Specification §13.1 names it.

---

## 0. Read this first

This document is the constitution of the Trade DNA codebase. It is not a suggestion. It is not a best-practice list. It is the set of rules that make the product's central claim — *every number is reproducible from immutable source data* — true.

Everything in this repo follows from that claim. If a rule below seems excessive, ask: does breaking it make a trader-facing number unreproducible? If yes, the rule stands.

Read all of it once before writing a line of code. Reference individual sections during development. Disagree in a PR against this file, not in the code.

---

## 1. The Fundamental Invariant

> **No computation is allowed to produce an important conclusion unless the system can reproduce it from immutable source data and identify exactly how that conclusion was derived.**

This is the invariant. Every other rule in this document is a mechanism that enforces it.

An "important conclusion" is:
- A Finding
- An Avoidable Loss figure
- A Process Score
- An experiment verdict
- Any number that appears in the show, on the DNA Card, or in an email to a trader

If you cannot trace that number back to the exact raw broker record and the exact code version that produced it, the number is not allowed to leave the research layer.

---

## 2. The Six Rules

These are the six rules that turn the invariant into engineering practice.

### Rule 1 — Raw data is immutable. Forever.

Every raw broker export is stored once, hashed at ingestion, and never modified. Not cleaned. Not reformatted. Not annotated. If the reconstruction logic changes six months from now, the same raw file must reproduce the same CTR — or an explicitly versioned new one.

### Rule 2 — Every transformation is a pure function of its versioned inputs.

`raw + code_version + config_version → output`.

No hidden state. No wall-clock time. No random seed that isn't recorded. No environment variable that isn't in the config. If you run the same code twice, you get the same bytes.

### Rule 3 — Schemas are versioned by file, not by edit.

`ctr_v1.py` stays. `ctr_v2.py` is added. The runner chooses by the version stamp on the input. A schema change is never an edit to an existing file. It is a new file plus a migration path.

### Rule 4 — Determinism is a hard requirement.

Same raw, same code, same config → identical output. Every stage of the pipeline is subject to this. CI tests it on every PR.

### Rule 5 — Research may consume production contracts. Production may never import research.

The `research/` services may read schemas, CTR, and evidence objects from `production/` and `shared/`. The reverse is forbidden. Enforced by `import-linter` in CI.

### Rule 6 — No LLM reads raw data. No LLM writes to the registry. No LLM computes a number.

The LLM reads evidence objects, composes prose, and explains Findings. It cannot access raw trades. It cannot alter the registry. It cannot produce a number that doesn't resolve to a field in an evidence object.

---

## 3. The Wall

This repository contains **product code only**.

Fund code — strategies, order logic, fund research, investor reporting — lives in a **separate repository**, in a **separate GitHub organization**, in a **separate cloud account**.

### What crosses the boundary

Two flows. Both one-directional. Both logged.

| Flow | Direction | Contents | Logged where |
|---|---|---|---|
| **Market data** | Fund → Product (read-only) | Licensed tick history, regime labels, release calendars | Every read is logged in the shared bucket's access log |
| **Aggregate priors** | Fund → Product | A versioned config file: `{move_id, as_offered_prior, as_followed_prior, n_iterations, provenance_note}` | Logged in the DOF ledger |

### What does not cross

- Trader data (never enters the fund environment, ever)
- Fund strategy rules, parameters, or notebooks
- Fund positions, P&L, or investor data
- Product secrets or infrastructure credentials

### The CEO signs the wall

`WALL.md` at the repo root states the boundary and carries the CEO's sign-off. It is updated only by a PR approved by both the CEO and the engineering lead. It is referenced by every architecture decision record that touches data flow.

---

## 4. The Pre-Commitment Hash

The file `services/research/prereg/framework_v1.yaml` is the research protocol. It contains every pre-committed threshold, null generator, tier rule, and family definition. It is the artifact that makes the product's differentiation claim defensible.

### The rules

1. The file is hashed at commit. The hash is stored in `framework_v1.yaml.sha256`.
2. Every evidence object carries the hash.
3. CI verifies that the committed hash matches the file. A mismatch fails the build.
4. A change to the file is a **major version** and requires the CEO's sign-off.
5. The running system checks the hash before writing to the registry. A mismatch refuses the write and logs a P0 incident.

### Why this is a repo rule, not a documentation rule

The pre-commitment hash is what makes every Finding traceable to a specific, frozen, pre-registered protocol. If it can drift silently, the entire claim of the research spec is false. The repo makes drift impossible, not just discouraged.

---

## 5. Directory Structure

```
plus-ev-tradedna/
│
├── README.md                          # Fundamental Invariant + the Six Rules
├── WALL.md                            # The fund/product boundary, signed by CEO
├── CONTRIBUTING.md                    # PR rules, code standards, review process
├── SECURITY.md                        # Security policy, vulnerability reporting
├── LICENSE                            # Proprietary. Not open source.
├── .gitignore
├── .editorconfig
├── pyproject.toml                     # Python deps, pinned versions
├── Makefile                           # Single entry point for common commands
│
├── .github/
│   ├── README.md
│   ├── workflows/
│   │   ├── ci.yml                     # lint + type-check + unit tests
│   │   ├── research-gate.yml          # correctness, leakage, null validation
│   │   ├── hash-check.yml             # pre-commitment hash integrity
│   │   ├── import-boundaries.yml      # production ↛ research enforcement
│   │   └── deploy.yml                 # deploy to staging/production
│   ├── ISSUE_TEMPLATE/
│   └── pull_request_template.md
│
├── docs/
│   ├── README.md
│   ├── adr/                           # Architecture Decision Records
│   ├── architecture/
│   │   ├── system-overview.md
│   │   ├── data-flow.md
│   │   ├── credit-chain.md
│   │   ├── trust-wall.md
│   │   ├── data-immutability.md
│   │   ├── schema-versioning.md
│   │   └── determinism.md
│   ├── research/
│   │   ├── evidence-standard.md
│   │   ├── test-library-v1.md
│   │   ├── null-models.md
│   │   └── four-zones.md
│   ├── product/
│   │   ├── doormat-arc.md
│   │   ├── subscription-arc.md
│   │   └── vocabulary.md
│   └── runbooks/
│       ├── incident-response.md
│       ├── deployment.md
│       └── data-deletion.md
│
├── services/
│   ├── README.md
│   │
│   ├── shared/                        # Contracts used by both research and production
│   │   ├── README.md
│   │   ├── schemas/
│   │   │   ├── ctr_v1.py
│   │   │   ├── evidence_object_v1.py
│   │   │   └── ...
│   │   └── lineage/
│   │       └── credit_chain.py
│   │
│   ├── production/                    # Deterministic pipeline. Varies slowly. Gated.
│   │   ├── README.md
│   │   ├── ctr/                       # Canonical Trade Record
│   │   │   ├── ingestion/
│   │   │   ├── reconstruction/
│   │   │   ├── enrichment/
│   │   │   └── quality/
│   │   ├── registry/                  # Evidence registry
│   │   │   ├── schema/
│   │   │   ├── store/
│   │   │   └── lineage/
│   │   ├── api/                       # HTTP layer
│   │   ├── agent/                     # LLM narration layer
│   │   │   ├── narration/
│   │   │   ├── faithfulness/
│   │   │   └── explain/
│   │   └── deletion/                  # Implements §19.4 of the thesis
│   │       ├── deletion_service.py
│   │       └── audit_log.py
│   │
│   └── research/                      # Exploratory workbench. Varies fast. Gated.
│       ├── README.md
│       ├── prereg/
│       │   ├── framework_v1.yaml
│       │   └── framework_v1.yaml.sha256
│       ├── library/                   # The pre-registered test library
│       ├── models/                    # M1–M6
│       ├── validation/                # Adversarial, nulls, robustness
│       └── evaluation/                # Synthetic, noise, gold standard
│
├── web/
│   ├── README.md
│   ├── src/
│   │   ├── screens/                   # Mirror, Surprise, Edge, Leak, Move, Exit
│   │   ├── components/                # DNA Map, Evidence Drawer, DNA Card
│   │   ├── interest/                  # Reveal engine
│   │   └── styles/
│   └── public/
│
├── data/
│   ├── README.md                      # What is here and what is not
│   ├── fixtures/                      # Small, synthetic, safe to commit
│   ├── golden/
│   │   └── certification_set/         # Frozen, held by validator
│   └── synthetic/
│       └── generator.py
│
├── infra/
│   ├── README.md
│   ├── docker/
│   ├── terraform/
│   └── scripts/
│
└── tests/
    ├── README.md
    ├── reproducibility/               # Runs each transformation twice, compares hashes
    ├── unit/
    ├── integration/
    └── e2e/
```

### Why this structure

- **`shared/` exists because both sides need contracts.** The CTR schema and the credit chain are used by research and production. They live in one place so they cannot drift.
- **`production/` vs `research/` inside `services/`, not at the top level.** The pipeline is one thing. The split is a rate-of-change boundary and a CI-enforced import boundary, not a directory wall.
- **`data/` holds fixtures and goldens only.** No production data. No partner data. No trader data. Ever. Production data lives in the database; trader data never enters the repo.
- **`docs/adr/` captures decisions.** Every architectural decision that constrains the future gets a file.
- **`infra/` is code.** Terraform, Dockerfiles, deployment scripts. Reviewed like code, deployed like code.

---

## 6. README Rules

### Rule: Every directory at depth ≤ 3 has a README.md

Directories at depth 1, 2, and 3 each have a README. Directories deeper than depth 3 inherit context from their nearest documented ancestor and get their own README only if they contain more than 5 files or a non-obvious boundary.

### The README template

Every README follows the same structure. No exceptions.

```markdown
# [Directory Name]

**Purpose.** One sentence. What this directory is for.
**Owner.** [Name or team]. **Last reviewed.** [Date].

## What is here

| File / Directory | What it does |
|---|---|
| `file.py` | One-line description |
| `subdirectory/` | One-line description |

## How to use it

```bash
# The one command you need
make test-research
```

## What it does not do

One or two sentences on the boundary. What is explicitly out of scope.

## Related

- [Parent README](../README.md)
- [Research Specification](../../docs/research/README.md)
```

### Why this rule

An engineer joining the team, or an auditor asking a question, or you six months later — each of them opens a directory and needs to know what it is in under 30 seconds. The READMEs are the memory of the codebase.

### What not to do

Do not write a README that says "This directory contains utility functions." That adds nothing. Either describe what the utilities do and why, or do not write the README — the depth rule will let you skip it.

---

## 7. Data Flow & Immutability

Every transformation is a pure function. The chain is:

```
RAW (immutable, hashed, forever)
 ↓ normalize()                code_version + config_version
NORMALIZED (reproducible from raw)
 ↓ reconstruct()              code_version + broker_schema_version
CANONICAL TRADE RECORD       (reproducible from normalized)
 ↓ enrich()                   code_version + market_data_version
ENRICHED (reproducible from CTR + licensed market data)
 ↓ extract_features()         code_version + feature_set_version
FEATURES (reproducible from enriched)
 ↓ run_test()                 code_version + framework_version
CANDIDATE
 ↓ validate()                 code_version + framework_version
EVIDENCE OBJECT              (carries full lineage)
```

### What immutability means in practice

- Raw broker exports are stored in an object store with a hash. The hash is recorded in the ingestion log. The file is never modified.
- Normalized records are derived. If the normalization code changes, you re-run it from raw. You never patch a normalized record.
- The CTR is derived. If the reconstruction logic changes, you re-run it from normalized. Every CTR version is stored.
- Features are derived. If the feature set changes, you re-extract. Old feature versions are kept for reproducibility.
- Evidence objects carry the lineage hash of everything upstream.

### The regeneration test

For every transformation, CI runs a reproducibility test:

```python
def test_reconstruction_is_deterministic():
    raw = load_fixture("raw_broker_export_v1.json")
    ctr_1 = reconstruct(raw, config=CONFIG_V1)
    ctr_2 = reconstruct(raw, config=CONFIG_V1)
    assert hash(ctr_1) == hash(ctr_2)
    assert ctr_1 == load_fixture("golden_ctr_v1.json")
```

If this test fails on a PR, the PR does not merge. Determinism is not negotiable.

---

## 8. Schema Versioning

### The rule

Schemas are versioned by file, not by edit.

### How it works

```
services/shared/schemas/
├── ctr_v1.py
├── ctr_v2.py            # Added when CTR schema changes
├── evidence_object_v1.py
└── evidence_object_v2.py
```

Every piece of data carries its schema version. The runner reads the version and dispatches to the correct schema class.

### What triggers a new version

- Adding a required field
- Changing a field type
- Removing a field
- Changing the semantics of a field
- Changing the field ordering in a serialized format

### What does not trigger a new version

- Adding an optional field that defaults to `None`
- Adding a docstring
- Refactoring internal logic without changing the schema

### Migration

A new schema version requires a migration path. Old data must remain readable. The migration is either:

- **On read** — the loader handles both versions, dispatches to the right class.
- **On write** — a one-time migration script upgrades all old records. The old records are kept until the new version has been stable for one release cycle.

### Why this matters

A model trained against `ctr_v1` must never silently receive `ctr_v2` data. If the schema changes underneath it, the model's behavior changes without a code change, which is exactly the kind of silent bug this repo exists to prevent.

---

## 9. The Research/Production Split

### The rule

Research may consume production contracts. Production may never import research.

### How it is enforced

`import-linter` in CI, configured in `.importlinter` at the repo root.

```ini
[importlinter]
root_packages =
    services.production
    services.research
    services.shared

[importlinter:contract:1]
name = Production must not import Research
type = forbidden
source_modules = services.production
forbidden_modules = services.research

[importlinter:contract:2]
name = Shared must not import Production or Research
type = forbidden
source_modules = services.shared
forbidden_modules =
    services.production
    services.research
```

Any PR that adds a forbidden import fails CI. No exceptions.

### Why this split

The research layer changes weekly. The production layer changes monthly. If research can leak into production, production becomes a moving target, and every re-score of the historical record becomes impossible because the code that scored it changed.

The split is not about "quality of code." It is about **rate of change** and about keeping the production pipeline a stable, versioned, reproducible artifact.

---

## 10. The LLM Boundary

### The rule

No LLM reads raw data. No LLM writes to the registry. No LLM computes a number.

### The architecture

```
Evidence Object (immutable) 
    ↓
Narration Composer (LLM reads only evidence objects)
    ↓
Faithfulness Check (every number resolves to a field)
    ↓
Composed Prose
```

### What the LLM may do

- Read evidence objects (never raw trades, never features)
- Compose prose around a Finding
- Answer "explain this" questions grounded in the evidence registry
- Draft a pre-registration record for human review

### What the LLM may not do

- Access the raw broker export
- Access the CTR or features directly
- Write to the evidence registry
- Compute any number that appears in the show
- Alter any threshold, tier, or promotion rule

### Enforcement

The `services/production/agent/` directory contains a single entry point that takes an evidence object and returns prose. It does not import the CTR, features, or raw data modules. It cannot, because `import-linter` forbids it.

### The faithfulness gate

Every number in the composed prose must resolve to a field in the retrieved evidence object. If it does not, the screen does not ship. CI runs the faithfulness suite on every PR against the composer.

---

## 11. Git Workflow

### Branches

- `main` — production. Every commit is a release. Protected.
- `develop` — integration. Where PRs land before promotion.
- `feature/*` — one feature, one branch. Short-lived. Deleted on merge.
- `research/*` — exploratory work. Never merges to `main` directly.
- `hotfix/*` — production fixes. Merges to `main` and back to `develop`.

### Commit messages

Follow Conventional Commits:

```
feat(ctr): add Zerodha export parser
fix(research): correct null model stratification
docs(adr): add ADR 007 on credit chain hashing
refactor(production/agent): isolate faithfulness check
```

The first line is under 72 characters. The body explains *why*, not *what*. Reference the issue or ADR number.

### Pull requests

Every PR:

1. Has a description explaining the why, linked to an issue or ADR
2. Passes CI (see §12)
3. Has at least one approval from a code owner
4. Does not reduce test coverage
5. Updates the relevant README if the change affects what a directory contains

### Code review

Reviewers ask:

1. Does this change break the Fundamental Invariant?
2. Does this change touch the pre-commitment hash? If yes, has the CEO signed off?
3. Does this change cross the research/production boundary? If yes, is it via a shared contract?
4. Is determinism preserved? Does the reproducibility test pass?
5. Does the README need an update?
6. Is there an ADR needed for this decision?

If any answer is uncertain, the PR does not merge.

### What not to do

- Do not merge your own PR without review, even a one-line fix.
- Do not force-push to `main` or `develop`.
- Do not add a dependency without a note in `pyproject.toml` explaining why.
- Do not commit a `.env` file, a credential, or a raw broker export.

---

## 12. CI Gates

Every PR runs these gates. Failing any gate blocks merge.

| Gate | What it does | File |
|---|---|---|
| **Lint** | `ruff check` on all Python | `.github/workflows/ci.yml` |
| **Type-check** | `mypy` on `services/` and `web/src/` | `.github/workflows/ci.yml` |
| **Unit tests** | Fast, isolated, no external services | `.github/workflows/ci.yml` |
| **Integration tests** | Cross-service, uses test database | `.github/workflows/ci.yml` |
| **Reproducibility** | Each transformation runs twice, hashes match | `.github/workflows/ci.yml` |
| **Import boundaries** | `import-linter` on `services/` | `.github/workflows/import-boundaries.yml` |
| **Pre-commitment hash** | `sha256sum framework_v1.yaml` matches committed hash | `.github/workflows/hash-check.yml` |
| **Leakage suite** | `L1`, `L2`, `L3` from Research Spec §4.4 | `.github/workflows/research-gate.yml` |
| **Null validation** | Nulls on noise traders, rates in [2%, 8%] | `.github/workflows/research-gate.yml` |
| **Faithfulness** | 100% numeric resolution on the composer | `.github/workflows/research-gate.yml` |

The **Research Gate** (§15 of the Research Spec) runs nightly and on PRs that touch `services/research/` or `services/production/registry/`.

---

## 13. Testing Strategy

Four layers, in this order of speed.

### Unit tests (`tests/unit/`)

Fast. No external services. No database. Test each function in isolation. Target: < 1 second per test, < 10 seconds total.

### Integration tests (`tests/integration/`)

Test services together. Use a real Postgres in a container. Test the CTR pipeline end-to-end on a fixture. Target: < 2 minutes total.

### Reproducibility tests (`tests/reproducibility/`)

For every transformation, run it twice on the same input and compare hashes. Compare against golden fixtures for the CTR, features, and evidence objects.

### End-to-end tests (`tests/e2e/`)

Run the full doormat flow on a synthetic trader: upload → reconstruct → enrich → run tests → evidence → show. Runs on demand and nightly. Target: < 5 minutes.

### What gets tested

Every public function in `services/production/` and `services/shared/` has a unit test. Every transformation has a reproducibility test. Every test in the research library has a validation test on synthetic ground truth.

### What does not need a test

Trivial getters and setters. Config loading that just reads a file. Framework glue code. If you would write a test that just calls the function and asserts the return value, skip it — it will be covered by the integration tests.

### Coverage target

80% for `services/production/`. 60% for `services/research/` (the experimental parts change too fast to enforce coverage). 100% for `services/shared/schemas/` (schema bugs are the most expensive).

---

## 14. Secrets & Environment

### The rule

Secrets are stored in a managed secret store. Never in `.env` files. Never in CI variables that are readable by fork PRs. Never in the repository.

### What goes where

| Type | Where |
|---|---|
| Database credentials | AWS Secrets Manager (or GCP equivalent) |
| API keys for market data | Same |
| LLM provider API keys | Same |
| JWT signing keys | Same, rotated quarterly |
| Encryption keys | KMS, not Secrets Manager |
| Non-secret config | Versioned YAML in `infra/config/` |

### Local development

Developers run against a local mock environment. The mock uses fixture data and stub services. No real credentials are on developer machines.

### The wall

The product environment and the fund environment have **separate secret stores**. No credential grants access to both. This is checked at provisioning time and audited quarterly.

---

## 15. The Deletion Service

§19.4 of the thesis specifies the deletion process. It is implemented in `services/production/deletion/`.

### What the service does

1. Receives a deletion request from an authenticated trader.
2. Revokes all broker connections.
3. Deletes the CTR, features, evidence objects, and Trader Model.
4. Removes the trader from future population priors (effective at next prior recomputation).
5. Retains the consent ledger rows and the deletion record itself (legal proof).
6. Writes to the audit log (append-only, never deleted).
7. Sends a confirmation email that names what was removed and what was retained, with the reason.

### The audit log

Every deletion is a row in an append-only table. The table is immutable. It records the request timestamp, the completion timestamp, what was deleted, what was retained, and the reason.

### The test

The deletion service has an integration test that verifies every step. The test runs on every PR that touches `services/production/deletion/` or `services/shared/schemas/`.

### Why this is a repo rule

The wall is not a promise. It is a service that runs. Without the service, deletion is a policy. With it, deletion is a fact that can be audited.

---

## 16. ADR Convention

Every architectural decision that constrains the future gets an Architecture Decision Record in `docs/adr/`.

### Format

```markdown
# ADR 001: The Canonical Trade Record

**Status.** Accepted. **Date.** 2026-10-05. **Deciders.** Engineering Lead, Research Lead, CEO.

## Context

Broker exports are fills, not round trips. Every downstream analysis needs round trips. Without a canonical representation, each analysis interprets the export differently.

## Decision

Build a CTR layer that reconstructs fills → positions → round trips deterministically.

## Consequences

- Every downstream service reads from the CTR, not from raw exports.
- The CTR schema is versioned.
- Reconstruction logic changes are major versions.
- The CTR must be reproducible from raw + code + config.

## Alternatives considered

- **Interpret exports on the fly.** Rejected: every analysis re-implements the reconstruction, and they drift.
- **Store round trips from the broker.** Rejected: brokers do not export round trips; they export fills.
```

### Rules

- ADRs are immutable. A decision that changes gets a new ADR that supersedes the old one. The old one stays, marked "Superseded by ADR 007."
- Every ADR has a number, a status, and a date.
- Every ADR lists at least one alternative considered and why it was rejected.

### When to write one

- A new service or module
- A new schema version
- A change to the pre-commitment file
- A cross-boundary data flow
- A choice between two reasonable technical options
- Any decision someone might reasonably ask "why did we do this?" about in six months

### When not to write one

- Bug fixes with obvious causes
- Dependency updates
- Test additions
- Style changes

---

## 17. The Makefile

The single entry point for common commands. Everyone uses `make`. No one memorizes long commands.

```makefile
.PHONY: help dev test test-unit test-integration test-repro test-e2e lint type-check research-gate hash-check clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

dev: ## Start local development environment
	docker compose up

test: test-unit test-integration test-repro ## Run fast tests

test-unit: ## Run unit tests
	pytest tests/unit -x -q

test-integration: ## Run integration tests
	pytest tests/integration -x -q

test-repro: ## Run reproducibility tests
	pytest tests/reproducibility -x -q

test-e2e: ## Run end-to-end tests
	pytest tests/e2e -x -q

lint: ## Lint all Python
	ruff check .

type-check: ## Type-check Python and TypeScript
	mypy services/
	cd web && npm run type-check

research-gate: ## Run the full Research Gate locally
	python -m services.research.evaluation.gate

hash-check: ## Verify pre-commitment hash
	@sha256sum -c services/research/prereg/framework_v1.yaml.sha256

clean: ## Remove build artifacts and caches
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
```

### Why this matters

An engineer opens the repo, types `make help`, and sees every command available. No wiki. No "ask someone." The Makefile is the manual.

---

## 18. What to Build First

Do not start with the show. Do not start with the API. Start with the schemas.

The order of operations for the first two weeks:

| Day | What | Why |
|---|---|---|
| 1 | `services/shared/schemas/ctr_v1.py` | Every downstream stage depends on this |
| 2 | `services/shared/schemas/evidence_object_v1.py` | Every Finding is written as one of these |
| 3 | `services/shared/lineage/credit_chain.py` | Every number resolves through this |
| 4 | `services/research/prereg/framework_v1.yaml` + `.sha256` | The pre-commitment file, hashed |
| 5 | `tests/reproducibility/` fixtures for the CTR | The regression guard for everything downstream |
| 6 | `services/production/ctr/ingestion/` for one broker | The first real data path |
| 7 | `services/production/ctr/reconstruction/` — fills → round trips | The first real transformation |
| 8 | `.github/workflows/ci.yml` + `hash-check.yml` + `import-boundaries.yml` | The gates that protect everything |
| 9 | `services/research/library/` — the first test (B2) | The first end-to-end research run |
| 10 | `services/production/registry/` — the evidence store | The first persistent artifact |

Everything else waits until these exist and pass their tests.

### What not to do

- Do not start with `web/`. The show is not the product. The show is the wrapper around the product.
- Do not start with `api/`. An endpoint without an engine is a stub.
- Do not start with the LLM narration. The LLM narrates evidence objects that do not exist yet.

---

## 19. The One Rule That Matters Most

If you remember nothing else from this document, remember this:

> **No computation is allowed to produce an important conclusion unless the system can reproduce it from immutable source data and identify exactly how that conclusion was derived.**

Everything else — the six rules, the directory structure, the CI gates, the pre-commitment hash, the wall, the deletion service — is a mechanism that enforces this. When you are unsure what to do in a given situation, ask: *does this make a trader-facing number more reproducible, or less?* If less, do not do it.

---

## 20. How to Use This Document

- **On your first day:** read sections 1, 2, 3, 5, 18.
- **Before your first PR:** read sections 6, 11, 12, 16.
- **Before touching the research layer:** read sections 4, 9, 10.
- **Before touching data:** read sections 7, 8, 13.
- **Before touching secrets, deletion, or the wall:** read sections 14, 15.
- **When you are unsure:** read section 19.

This document is versioned in `docs/methodology.md`. A change to it is a PR. A change that affects the wall, the pre-commitment file, or the fundamental invariant requires sign-off from the CEO and the engineering lead.

---

*End of methodology. The document is now v1.0. Freeze it. The first commit to the repository should be this file and the root README. Everything else builds on top.*