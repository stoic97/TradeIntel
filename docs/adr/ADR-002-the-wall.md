# ADR 002: The fund/product wall

**Status.** Accepted. **Date.** 2026-10-05. **Deciders.** Founder/CEO.

## Context
PlusEV runs systematic strategies on MCX. TradeDNA reads retail traders' histories on the same market. Thesis §19 and Research Spec §12.2 require that trader data never enters the fund and that the fund never produces behavioural priors.

## Decision
TradeIntel is a separate repository from `plus_ev_code_base`. Two flows cross, both one-way and logged: market data (tick history, the fund's regime definition, release calendars) fund → product; and a versioned config of aggregate move-type priors fund → product. Nothing crosses product → fund. At Stage 1 the two get separate accounts and secret stores (Methodology §3, §14).

## Consequences
- No fund code, data or credentials in this repo; no trader data in the fund's.
- `WALL.md` at the root states this and carries the CEO's sign-off when the accounts are split.

## Alternatives considered
- **One monorepo with directory boundaries.** Rejected: a directory is not a wall; a repo with separate access is.
