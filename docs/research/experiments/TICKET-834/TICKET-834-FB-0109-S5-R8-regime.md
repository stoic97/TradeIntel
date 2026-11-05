# FB-0109 → S5 `regime_expectancy` and R8 `vol_leverage_coupling` · routed, blocked

*Runner: Harshad · Ruler: Pawan · Shared rules: [`_common.md`](_common.md)*

**The claim (T-001):** R8 and S5 wait on market-regime labels.

**Status.** Both are already in the core library, pre-registered as written:
- **S5:** M6, N-S, θ_min 0.25 R, n_min 20 per cell, move RK-2, with regimes from the fund's definition, unchanged.
- **R8:** M4/M1, N-S, θ_min log 1.25 and 0.25 R, n_min 30 per regime, move RK-2.

There is nothing to pre-register. The claim is a dependency, and it is correct: `docs/deferrals.md` **TD-011** says both run on stand-in labels until the fund's regime and volatility labels cross as data under ADR-002, and that has to happen before either result is published.

**Kill, in addition to `_common.md`:** no S5 or R8 result is shown, or counted toward a tier, while TD-011 is open. A run on stand-in labels is a machinery check, not evidence.

**Ruling (Pawan):** ______ · date ______
