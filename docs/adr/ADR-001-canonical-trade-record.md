# ADR 001: The Canonical Trade Record

**Status.** Accepted. **Date.** 2026-10-05. **Deciders.** Founder/CEO, Engineering.

## Context
Broker exports are fills, in a different layout per broker. Six files collected on 4–5 Oct came in five different shapes; three were P&L statements with no fills at all. Every downstream test needs round trips, and needs them computed the same way for every broker.

## Decision
One adapter per broker turns its export into a single Canonical Trade Record (`services/shared/schemas/ctr_v1.py`): fills → positions → round trips, deterministically, with contract identity (symbol **and** expiry), timestamps, fees, and typed missingness (Research Spec §4.2, §4.5). An export that lacks a required field is refused with the reason, never patched.

## Consequences
- Every test reads the CTR, never a raw export.
- The CTR schema is versioned by file; reconstruction changes are major versions.
- The CTR must be regenerable from raw + code + config (Methodology §7).

## Alternatives considered
- **Interpret each export on the fly.** Rejected: every test re-implements reconstruction and they drift.
- **Ask brokers for round trips.** Rejected: brokers export fills.
