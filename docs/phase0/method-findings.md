# Phase 0 — method findings

Facts about the **method**, learned while building. Instrument-agnostic, no trader
in them. Per-trader numbers live outside this repo (README rule 1).

## Exit-capture tests need tick data, not bars (5 Oct 2026)

Bar-sampled MFE overstates exit capture by roughly **0.33 / √(hold ÷ bar interval)**,
and the bias differs by holding time — so a scalper and a swing trader measured on the
same bars are not comparable (ADR 005, Research Spec §4.2).

Observed consequence on a real retail history: at a median hold of under ten minutes,
1-minute bars would overstate capture by about **+0.12**, and 5-minute bars by **+0.26**.
For a trader of that kind, **E2 and E4′ are not degraded without tick data — they are
impossible.** This makes the week-2 tick-coverage check a go/no-go for two of the
eighteen core tests, not a nice-to-have.

## Established is attainable on a real retail history (5 Oct 2026)

With the §4.6 zone split and the per-test `n_hold` rule, a history of roughly two
thousand round trips yields an isolation zone holding enough condition trades to reach
`P_hold ≥ 0.80` at **θ_hold ≈ 0.25R** — the library's own θ_min. So the strongest tier
is reachable by real traders at the threshold the product claims to detect, not only in
the arithmetic.

## A derived value can be exact where a derived price cannot (5 Oct 2026)

When a broker reports an exact total and a rounded average price, deriving the price and
multiplying back loses the exactness the broker handed us. The authoritative quantity is
the **value**; apportion values, not prices, wherever a figure will be shown to a trader.
Found by the golden fixture on its first run.
