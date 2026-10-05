# ADR 003: The pre-commitment hash

**Status.** Accepted. **Date.** 2026-10-05. **Deciders.** Founder/CEO, Research.

## Context
The product's differentiation claim (Research Spec §2, §15) is that every test was fixed before any trader's data was seen. A claim like that needs proof that the rules did not drift.

## Decision
Part I of the Research Specification is written as `services/research/prereg/framework_v1.yaml`. At the Phase 0 kickoff all seats agree it, `make hash-lock` writes `framework_v1.yaml.sha256`, and both are committed. `make hash-check` verifies them; at Stage 1 CI does. Any later change is a major version with a decision-log row and CEO sign-off. Every evidence object carries the hash.

## Alternatives considered
- **Keep the rules in the spec document only.** Rejected: prose cannot be hashed into an evidence object, and a document can be edited without anyone noticing.
