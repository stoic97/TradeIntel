# ADR-006 — The sampler for the research models

*Status: **Accepted**, 10 October 2026 · Revisit at step C, on divergence behaviour, not speed · Decided by: founder as ruler · Evidence: `docs/phase0/adr-006-benchmark.json`*

## Context

Every research test reads a posterior. The engine needs one sampler, chosen before
the library is built, because changing it later moves every number a trader sees and
is therefore a charged change (Developer Manual 2.2).

Two candidates: **NumPyro** on jax, and **PyMC** with the **nutpie** sampler. The
question was framed as a speed question, because doubt D8 put the compute budget at
an assumed 2 s/fit and feared several days per corpus pass.

A benchmark comparing two implementations written by the same hand measures the hand,
so both were checked against the **closed-form posterior** of the conjugate core of
M1 — exact linear algebra, not each other (`services/research/models/`).

## Decision

**PyMC + nutpie is the default sampler.**

**Speed is explicitly not the reason.** It is the reason nothing else had to be traded
away for it.

Both backends stay in the registry (`ce.BACKENDS`), both build from one
`ConditionalEffectSpec`, and every result carries the spec's digest. Switching is an
afternoon, and that cheapness is the real insurance against this ADR being wrong.

## Evidence

Measured 10 Oct 2026, one machine, 1,000 draws and 1,000 warmup on 4 chains, four
problem sizes, four fits each, reproduced twice within 3%.

| Backend | s/fit | ESS/sec | ESS/draws | max r-hat | divergences |
|---|---|---|---|---|---|
| numpyro | 0.93 | ~1,960 | 43–49% | 1.0033 | 0 |
| pymc_nutpie | **0.67** | **~3,700** | **54–64%** | 1.0027 | 0 |

Both matched the exact posterior within 5 Monte Carlo standard errors on every
parameter, across five sampler seeds, with no detectable bias in either the mean or
the spread.

Three findings beyond the headline:

1. **Per-fit time is flat in n.** 100 to 3,000 trades is a 30× increase in data for a
   3–6% increase in time. Cost is sampler overhead — warmup, tree building — not
   likelihood evaluation. **Longer histories are nearly free.**
2. **Compilation is a one-off process cost**, about 1.2 s on the first fit and 0.1 s
   at each new data size. An earlier draft of the benchmark script asserted that
   nutpie recompiled on every call and warned the comparison was skewed; its own
   timings contradicted that, and the claim was in the committed record before it was
   checked. Hoisting compilation out of the fit loop would buy nothing.
3. **nutpie's advantage is adaptation, not just arithmetic.** It returns more
   independent draws from the same nominal count, which narrows every interval the
   two-part promotion criterion reads.

## Consequences

**Doubt D8 is resolved, and the assumption was wrong in our favour.** One full corpus
pass is 2,224 histories × 18 tests = **40,032 fits** → **7.4 hours serial, 0.9 hours
on 8 cores**. Ten passes is a working day. Three things follow:

- Compute stops being a planning constraint anywhere in Phase 0.
- Research Spec §14's requirement to re-score the entire history on every major
  version is free, not something to budget around.
- No reason to shorten histories, subsample, or approximate for speed. If a shortcut
  is ever proposed for performance, this ADR is the answer.

**What this does not cover, and must not be read as covering.** One model, one
condition, sigma known, one machine. It says nothing about the hierarchical model of
step C, where partial pooling creates a funnel geometry that both samplers can
struggle with, and nothing about vectorising many traders into one call — which jax
can do and PyMC cannot. That lever was never needed, because the serial cost came in
low enough.

## What would reverse this

- **Step C's SBC shows divergences on the hierarchical model with nutpie that
  NumPyro does not have.** This is the likely reversal, and it is a correctness
  reason, not a speed one.
- A later model needs vectorisation across traders in one call. Not currently needed
  at 0.9 h per pass, so this would follow from a change of scope, not of hardware.
- nutpie's reproducibility fails under a condition the current tests do not cover.
  Identical summaries from identical seeds are asserted today; a failure there would
  breach Research Spec §12.1 and outrank every number above.

## Rejected alternatives

- **NumPyro.** Fully viable and 5 percentage points behind on nothing that matters at
  this scale. Kept in the registry, tested on every run, and the first thing to try if
  step C goes badly.
- **Deferring the decision until step C.** Rejected: the hierarchical model has to be
  written in one library's idiom first, and writing it twice to avoid choosing is more
  work than switching once if this is wrong.
- **Writing our own sampler.** Not seriously considered. A hand-rolled statistic is a
  statistic that itself needs validating, which is the same reason ArviZ computes
  r-hat and effective sample size here rather than us.
