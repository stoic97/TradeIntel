# PlusEV–TradeDNA · Research Specification — v1.0 (freeze candidate)

*3 October 2026 · Supersedes Draft 2.1 · Child of Product Thesis v1.4 — Baseline (frozen; T§) · Workbook v1.1 (frozen; B§) · Owner: research lead · Ruler: CEO*

**Status.** This is the version the CEO asked for after the walkthrough: every conflict the walkthrough found is resolved here, with the decision and its reason recorded in Annex I. It is frozen on upload to project knowledge. One recommendation stands beside the freeze rather than against it: Draft 2.1 was never reviewed by outside eyes, and every earlier freeze in this project followed a review round, so a single external review of this version before the week-1 kickoff is cheap insurance. If that review finds nothing material, nothing moves; if it does, the fix is a v1.1 before any data is seen, which costs nothing.

**Read this first.** Draft 1 was a research programme written before a single real trade had been seen. Two reviews attacked it from opposite directions — one said it was over-engineered for Phase 0, the other said parts of the machinery were wrong. Both were right, and checking the arithmetic found something neither caught: **the experiment engine as specified could not measure anything.** Draft 2 fixed the mathematics and cut the programme to what eight weeks can produce. Draft 2.1 closed the thesis conflict and applied two further reviews. **Then the CEO walked the document one concept at a time, and the walkthrough found a real defect in every concept it touched** — six for six. v1.0 is the result of resolving them and of reading the remaining sections against those resolutions.

**What changed in v1.0.** Each row is a decision, not a polish; the reasoning is in Annex I.

| # | Change | Where |
|---|---|---|
| 1 | **The scope is crude first, end to end, then everything Indian retail trades.** With the instrument's own price series held in-house, the four tests the old selection rule excluded for needing licensed market data are buildable; the regime definition is the fund's own, unchanged | §9, §12.2, Annex H |
| 2 | **One threshold anchored to the library bar.** A conditional test's practical threshold θ_min is the condition effect whose whole-history drag equals δ_pool — **0.25R** at the reference prevalence — derived, no longer a 0.10R/0.15R literature habit | §5.2, §9, Annex A |
| 2b | **The promotion criterion is two-part** — *is it real* (P(θ beyond 0) ≥ 0.95) and *is it big enough* (the shrunk median beyond θ_min) — replacing Draft 2.1's single *P(θ beyond θ_min) ≥ 0.95*, which passed a genuine 0.5R leak only 53% of the time at 60 condition trades. The new form passes it 80% and a noise trader 5% | §5.2 |
| 3 | **The hold-out is sized at the effect the training zone conservatively claims**, not at θ_min — so a large leak on a moderate history can reach Established, which is what §4.6 promised and the 2.1 rule silently prevented | §4.6 |
| 4 | **A null reports its minimum detectable effect.** "No problem found" is said only when the test could have found an effect at θ_min; otherwise the trader is told the size of leak that was ruled out and the size that was not | §5.4a, §5.6 |
| 5 | **E4 replaced by E4′ (late loss accrual)** — the recorded stop is intent, which trade data cannot contain; the price path can say how much of a loss arrived after the trade was already as bad as his typical loss | §9, Annex A |
| 6 | **The core grows from thirteen to eighteen tests plus the Edge Map**: R7 and S11 promoted; S6, S10 and R11 added for crude; B6 retired as covered by B12. Two are conditional on fills or stop orders being present in the export | §9, Annex A, Annex B |
| 7 | **Every core test has a planted synthetic behaviour**, because recall on a test with no planted truth is unmeasured and an unmeasured recall cannot sit behind a gate | §12.2 |
| 8 | **MFE resolution is part of a test's version identity.** Bar-sampled MFE overstates exit capture by roughly 0.33/√(hold ÷ bar), differently for a scalper than a swing trader; E2 and E4′ need tick or 1-second data, and the contract actually traded, never a stitched series | §4.2, §9 |
| 9 | **Five starter move types, with a pre-registered merge** (B12 validated → the daily limit replaces the pause rule), all deletion or cap rules, all always-permitted. The adherence auto-stop is gone, because there is no adherence verdict to stop on | §8, §11 |
| 10 | **Recurring data is named as the precondition for the measurement architecture.** A read-only broker connection is the subscription's data path from Phase 1 — corrected at freeze from "Phase 2 with a rate trigger", because the bias in manual supply exists at every rate and a rate trigger cannot catch it. Connectors are built in Phase 0 weeks 5–8; manual months carry a sensitivity bound into any pooled read | §7.8, §13.2, Annex H |
| 11 | **The Research Gate reconciled with the walkthrough**: "medium effect" (undefined) replaced by explicit sizes; the recall gate tests the engine's calibration rather than the physics; confirmation is of the described fact, never a cause; "top three" means ranked by hold-out-validated effect; the feasibility gate reads on n_min with the n_hold share beside it | §15, §12.3 |
| 12 | The thesis touches this version creates are listed in one place for a single v1.5 pass | Annex J |
| 13 | **A founder-written LLM baseline is measured on the same noise corpora the engine is gated on** (added at freeze). Within five points on false positives and the differentiation claim goes to the thesis log. Nothing committed moved; one measurement was added | §2, §15, Annex H |
| 14 | **The asset is regenerability, not the Findings** (added at freeze): raw inputs retained immutably, every major version re-scores the whole history so the population dataset lives on one version, and a record that cannot be regenerated blocks the gate. The last addition before freeze; nothing further changes without Phase 0 evidence | §14 |

**The document is in three parts, and they have different jobs.**

| Part | What it is | Who reads it | Status |
|---|---|---|---|
| **I — The Commitment** | The rules that must be fixed before any real trader's data is seen. This is what gets signed and hashed at the week-1 kickoff. | Everyone. ~40 minutes. | Fixed at kickoff; changing it is a major version |
| **II — The Phase 0 Programme** | What the eight weeks actually build and measure. Deliberately small. | Research lead, engineer, trader, CEO | Executed, then rewritten by its own results |
| **III — Annex** | Protocols, templates, the candidate register, references. Reference material, not reading material. | Whoever is implementing the thing they need | Grows during Phase 0 |

**Every rule carries two labels, and they are independent.** Draft 1 conflated them.

- **Layer** — when it is fixed: **PRE-COMMIT** (before data; changing it later is a major version) · **CALIBRATE** (measured during Phase 0) · **DEFER** (not built in Phase 0 at all).
- **Provenance** — where the value came from: **derived** (falls out of arithmetic or a definition) · **literature** (an external anchor, cited) · **inherited** (from the frozen thesis or the fund's own loop) · **arbitrary** (our judgement, with nothing behind it yet).

The combination that Draft 1 hid is **PRE-COMMIT + arbitrary**: a number we must fix before looking precisely *because* we do not know it. That is not dishonest — it is what commit-before-measure means. It is dishonest only if unlabelled. Every arbitrary value below is labelled, and each has exactly one revision window: on synthetic and fund corpora, before the first partner's data is read (§13.2).

---

# Part I — The Commitment

## 1. Scope

**What this document decides.** What counts as evidence; how the engine tries to kill its own findings; when a claim may be called true; how a change in a trader is measured; and who may move a bar.

**What it does not decide.** The show (Experience Specification) · architecture and infrastructure (Technical Design) · what Phase 1 ships (PRD) · pricing and go-to-market (Strategy) · the Trader Promise's wording (thesis).

**Conflicts.** Where this document and the thesis disagree, the thesis wins and the disagreement becomes a decision-log row. Draft 2's one material conflict (§7.6) was closed by thesis v1.4. v1.0 creates no new conflict; it creates **touches** — wording the thesis should carry to match decisions it has already accepted in principle — and those are listed in Annex J for one amendment pass.

**Instrument scope — DECIDED 3 Oct.** Phase 0 and the first end-to-end product test run on **MCX crude** only. The product extends to the rest of what Indian retail trades after the machinery has been proved on crude. What transfers is the machinery; what does not transfer is calibration — every prevalence, effect size and reference value established on crude traders is crude-specific and is re-established per instrument family as a gate, never assumed (Annex H).

**The five separations** — a reader should always be able to name which one a section serves:

```
CAN WE COMPUTE IT?      Correctness          §4, §12.1
IS IT ACTUALLY TRUE?    Statistical validity §5, §6, §12.3
DOES HE AGREE?          Recognition          §12.4   — recognition is not accuracy (§12.4)
DOES IT HELP?           Utility              §7, Phase 2
DID IT CAUSE IT?        Causality            §7.5
```

## 2. The non-negotiables

Twelve product Laws are in the thesis. These are their research-layer translations, plus one the walkthrough added — each is a rule the engine can violate, and each violation has a name in the audit.

| # | Rule | Forbids, concretely |
|---|---|---|
| R1 | **Evidence before narrative** | A number in the show that does not resolve to an evidence-object field |
| R2 | **Fact ≠ hypothesis** | A mechanism rendered as a diagnosis |
| R3 | **Discovery ≠ confirmation** | A candidate reaching a trader without the gates |
| R4 | **Runner ≠ ruler** | Whoever produced a result issuing its verdict |
| R5 | **Absence of evidence ≠ bad process** | A zero where a sub-score has no Findings |
| R6 | **No per-trader fitting** | A threshold chosen because it made this trader significant |
| R7 | **The confirmatory family closes before the data opens** | A test added mid-run and reported as pre-registered |
| R8 | **Real isolation is read once** | A second look that is not logged as a second degree of freedom |
| R9 | **Every number carries its lineage** | A Finding that cannot be recomputed from its stamp |
| R10 | **Correctness before utility** | A screen tuned on progression while its numbers are unverified |
| R11 | **The instrument can be wrong; the bar cannot be moved by taste** | "It was close, call it a pass." The one exception is the fund's: decompose the failure from evidence, show the *instrument* is miscalibrated for the mechanism, record the ruling the same day |
| R12 | **Nothing here produces a trade** | Any Finding whose action is buy, sell, or hold a position |
| R13 | **Trade data cannot contain intent** (added v1.0, §11.1a) | Any sentence that attributes a behaviour to his intention, in either direction — "revenge", "tilt", "your plan", "your system". The engine describes magnitude and consistency as facts and never selects a cause |

**Pre-commitment is the product's structural difference from any after-the-fact analysis of the same file (added at freeze).** Every test in this document is written and hashed before any trader's data is seen, and a trader may be shown the hash. A capable model reading his CSV decides what to test after reading it; that is the garden of forking paths, and at realistic clustering it names a leak in 58% of noise histories where the pre-committed shuffle test names one in 4% (§5.4). The claim is measured rather than asserted — §15 carries the baseline.

**The fund's vocabulary applies unchanged**, because the team already obeys it: dark lane (moves no result; proof is byte-identical output; merges freely) versus charged lane (can move a result; pre-registered, run once, verdicted by someone else); commit before measure; blast radius by content; a monotone slope under perturbation is a fitted point — remove the knob, do not refit it; zero degradation anywhere is a red flag.

## 3. Research objects and the output contract

```
Research Framework → Research Test → Candidate Result → Evidence Object → Finding
   → Prescription → Experiment → (counts and accounting at trader level; Verdict at pooled level only, §7.5) → Trader Model Version
```

**The Research Output Contract — PRE-COMMIT · inherited.** No downstream system may consume a Candidate Result as a Finding. Only an Evidence Object with a tier and a complete gate record leaves the research layer, and only through the registry. Narration, Next Best Move, the Process Score and the DNA Card read the registry and nothing else. An Exploratory object may be narrated as "worth watching" and may never produce a prescription.

Every test returns a status — `not_applicable · unavailable · insufficient_data · null_with_mde · candidate_killed · exploratory · likely · established` — with the estimate, interval, samples, hold-out result, robustness record, limitations and economic significance. A test that cannot run says why; a conditional test whose fields the export lacks says `unavailable`, never null (§9); a test that ran and found nothing says what size of effect it ruled out (§5.4a). It never returns silence. Field-by-field computation is in Annex C.

## 4. Data

### 4.1 Lineage
```
broker export (hashed) → raw event → normalised event → position → round trip (CTR)
  → market-enriched event → feature vector → candidate → evidence object → Finding
```
Every arrow is a deterministic, versioned function; every stage stores the hash of what it consumed.

### 4.2 CTR correctness — PRE-COMMIT · derived from the golden set

| Property | Gate |
|---|---|
| Round-trip fidelity | ≥ 99.5% matched on (instrument, entry, exit, quantity, net P&L within ₹1) against the **frozen certification set** — ≥ 200 hand-verified round trips per broker, held by the validator and distinct from the development fixtures engineering works against (§12.1) |
| Fees | Net P&L within 0.5% of the broker's own statement across 30 days (Indian charge model: brokerage, STT, exchange charges, SEBI fees, stamp duty, GST) |
| Unresolved positions | Flagged, never forced; excluded from R-based tests; rate reported |
| No silent drops | raw = mapped + quarantined + rejected, or the import fails |
| Determinism | Identical hash across runs and platforms |
| **Contract identity** (added v1.0) | Every round trip carries the **specific contract traded** — symbol **and expiry** — never a bare "CRUDEOIL". Crude rolls monthly, and MFE/MAE must be computed against the contract he held; a stitched continuous series is forbidden as a price source for any per-trade outcome. An export that cannot resolve the contract marks the trip `contract_unresolved` and it is excluded from E2 and E4′, with the rate reported |
| **Price-path resolution** (added v1.0) | MFE, MAE and capture are computed from **tick or 1-second** data for the contract and the holding interval, and the resolution used is stored on the feature. Bar-sampled MFE overstates capture by roughly 0.33/√(hold ÷ bar interval) — +0.09 for a 15-minute hold on 1-minute bars, +0.21 on 5-minute bars — and the bias differs by holding time, so two traders measured on bars are not comparable. 1-minute bars are acceptable only for holds of 45 minutes or more, and then only with the bias recorded. A change of resolution is a **major** version |
| **Fills and orders** (added v1.0) | Where the export carries them, per-fill rows (time, price, quantity) and order types (SL / SL-M / market / limit) are preserved and typed; where it does not, the fields are `unavailable` (§4.5) and the two conditional tests R7 and R11 do not run. Which brokers carry them is a week-2 count (Annex H) |

### 4.3 Point-in-time — PRE-COMMIT · inherited
Every market feature carries `available_at`; it may be attached to a trade at t only if `available_at ≤ t`. Trailing statistics use bars that closed before t. Regime labels are trailing only — no centred smoothing, no whole-day labels for intraday trades. Cross-trade state uses round trips **resolved** before t. Outcome features (MFE, MAE, capture) are outcomes only, never conditions.

**Leakage classes — the compile-time guard.** C0 known at entry · C1 trailing market state · C2 cross-trade state from resolved trips · C3 this trade's own outcome · C4 anything using information after entry. The feature registry refuses to register C4 and refuses any test using C3 as a condition.

### 4.4 The leakage test — PRE-COMMIT · derived (**corrected**)
Draft 1 said: shift every feature's `available_at` forward one bar and require zero tier changes. That is wrong, and the second review caught it. A legitimate trailing feature *should* change when you deny it its most recent closed bar — that measures power, not leakage. The correct invariant is reproducibility from the past plus a working detector:

| Test | Construction | Gate |
|---|---|---|
| **L1 · Reproducibility from history alone** | Recompute every feature at time t from an information set truncated at t, independently of the production path | Bit-identical to the production value, on 50 histories, every feature |
| **L2 · Positive control (does the detector work?)** | Deliberately inject future information into a feature (same-day high; the trade's own outcome; a centred moving average) | The registry or L1 must **detect every injected case**. A detector that misses one is broken and blocks the gate |
| **L3 · Sensitivity, reported not gated** | Shift `available_at` forward one bar and record which tests change tier | Reported as fragility: a Finding that depends entirely on the most recent bar is flagged, not killed |

### 4.5 Missingness — PRE-COMMIT · inherited
Typed, never imputed for a behavioural fact: `unavailable` (broker does not export it) · `unknown` · `not_applicable` · `reconstruction_failure` · `market_gap`. Enrichment gaps are declared, never filled from a proxy instrument without a pre-registered mapping. The **data-quality score** (0–100: P0 completeness, resolved-trip share, market coverage, fee reconciliation, span, count) is a diagnosis input; below 60 the answer is "Not enough evidence yet — data," with the specific fixes.

### 4.6 The four zones — PRE-COMMIT · derived (**arithmetic corrected**)
The fund's Training / Embargo / Isolation / Reserve architecture, applied to each trader's history in trade order. Draft 1 asserted "isolation ≥ 30 ⟹ ≥ 90 trades," which is false at a 25% split — 25% of 90 is 22.5. The allocation is now an algorithm:

```
N            = reconstructed round trips
isolation    = clamp( round(0.25 · N), 30, 200 )
embargo      = max( round(0.05 · N), one full trading day )
training     = N − isolation − embargo
```

**The tier requirement is per test, in condition trades — DECIDED 1 Oct, and it replaces a blanket trade count.**

Draft 2.1 as first written said *"Established needs N ≥ 120 trades"*, derived from isolation ≥ 30. That number does not work, and the error was setting the zone minimum (30 trades) and the hold-out bar (P_hold ≥ 0.80) independently and never checking that they meet. They do not:

> At N = 120 the isolation zone holds 30 trades. For a condition occurring in 20% of trades, that is **6 condition trades**. With 6, even a large 0.5R effect reaches only **P_hold = 0.78** — below the 0.80 bar. **No Established Finding is attainable at 120 trades.**

A blanket history length was always the wrong unit, because what the hold-out test actually needs is **condition trades inside the isolation zone**, and that depends on the test's own prevalence and effect size. The rule:

> **Established requires the isolation zone to contain at least `n_hold` trades in the test's condition**, where `n_hold` is the smallest count at which an effect of size **θ_hold** reaches P_hold ≥ 0.80, computed at the trader's own measured σ_R and comparison-group ratio. It is derived per test and per trader by a pre-registered formula, never chosen.

**What θ_hold is — corrected in v1.0.** Draft 2.1 sized the hold-out at the test's practical threshold θ_min. That contradicted the paragraph beneath it: with θ_min at 0.15R, a session test needed about 78 condition trades in isolation — 1,500 trades of history — so even a 0.8R session leak could never reach Established, when the whole point of the rule was that *large effects on adequate histories* do. The hold-out is a replication check, and a replication is sized at the effect it is asked to replicate:

> **θ_hold = max( θ_min , the 20th percentile of the shrunk training-zone posterior )**

The training zone has already been shrunk toward zero (§5.5), and its lower quantile is used rather than its median because a candidate that reached the hold-out is the one most likely to have been flattered by selection. The isolation fit itself remains prior-only (§5.2) — the training estimate sizes the check, it never enters it.

At σ_R = 1.4 with a comparison group four times the condition group:

| θ_hold | Condition trades needed in isolation | History needed at 20% prevalence | at 10% | at 40% |
|---|---|---|---|---|
| 1.0R | 2 | 40 | 80 | 20 |
| 0.8R | 3 | 60 | 120 | 30 |
| **0.5R** | **7** | **140** | 280 | 70 |
| 0.4R | 11 | 220 | 440 | 110 |
| 0.3R | 20 | 400 | 800 | 200 |
| **0.25R** (= θ_min for conditional R tests, §5.2) | **28** | **560** | 1,120 | 280 |

**What this means, and it is a product fact rather than a footnote.** Established attaches naturally to **large effects on adequate histories** and essentially never to small ones. A trader with 150 trades whose post-loss leak the training zone conservatively puts at 0.5R can earn Established on it; the same trader will never earn it on a 0.3R session effect, whatever we do. That is the correct behaviour, not a limitation: our strongest claim is reserved for his biggest problems, which are the only ones worth leading a show with, and a 0.3R effect remaining Likely is honest because it is not what is hurting him.

**Consequently (T§12.4 hand-off, decided 1 Oct): Likely is the doormat's normal headline tier, and Established is what a large leak on a long history earns.** The arc never changes; only the words and the confidence badge do. Phase 0 still counts the distribution — what share of partners clear each test's `n_hold` (§12.3) — but the product no longer depends on that share being high. Lowering the hold-out bar to raise the share was considered and **rejected**: choosing a threshold so that more traders clear it is selecting the bar from the outcome, which is the single thing this document exists to prevent.

| Tier | Zone requirement |
|---|---|
| **Established** | Isolation contains ≥ `n_hold` condition trades for that test at its θ_hold, **and** training ≥ 60 trades |
| **Likely** | Isolation ≥ 20 trades with ≥ 3 condition trades, **and** training ≥ 40 trades — the ceiling whenever `n_hold` is not met |
| Below that | Exploratory ceiling; the diagnosis states which Findings would firm up, and at roughly what trade count |

**Zone discipline.** Discovery runs on training only. Embargo separates a state that began in training from leaking into isolation. **Isolation on a real trader's history is read once, at the end of Phase 0, on the final framework version** (§13.2) — not on every intermediate iteration, which was Draft 1's mistake and would have frozen the calibration into two or three expensive shots. Synthetic isolation reads are unlimited: nothing is spent, because the data is generated. Reserve is everything arriving after the diagnosis; it is what the experiment measures.

## 5. The Evidence Standard

### 5.1 Claim levels — PRE-COMMIT · inherited
L1 historical association ("was associated with") · L2 robust pattern ("persists across slices") · L3 research hypothesis ("may represent" — only attached to a validated pattern, only from that test's pre-registered mechanism vocabulary) · L4 validated intervention ("changing this produced" — only after a PASS).

### 5.2 Tiers — PRE-COMMIT · arbitrary values, revisable once on corpora (**hold-out separation corrected**)

Draft 1 let `P_full` — computed on training **plus** isolation — decide promotion, while also using isolation as the confirmation. That is double-dipping: the hold-out influenced the criterion that claimed to validate against it. The second review was right, and the fix is a clean separation:

```
PROMOTION EVIDENCE            (decides the tier)
  P_train  : P(θ beyond 0, pre-registered direction | training only)      — is it real?
  m_train  : the shrunk training-posterior median, compared with θ_min    — is it big enough to matter?
  P_hold   : P(θ beyond 0, pre-registered direction | isolation only, prior only — no training posterior)
  ρ        : robustness (§5.3)
  q        : BH-adjusted null p-value within family (§5.4)
  n, ε, s  : samples, economic significance, first-half/second-half sign agreement

FINAL MAGNITUDE               (displayed after promotion; may never change the tier)
  θ̂_full  : pooled training + isolation posterior
```

**The promotion criterion is two-part (corrected in v1.0).** Draft 2.1 defined P_train as *P(θ beyond θ_min)* — the posterior had to put 95% of its mass beyond the practical threshold. That conflates two questions, *is it real* and *is it large*, and it is far weaker than it looks: for a genuine 0.5R leak with 60 condition trades it passed only 53% of the time at θ_min = 0.15R, and would pass 34% at the anchored 0.25R. The criterion is now the standard region-of-practical-equivalence form ([Kruschke 2018](https://journals.sagepub.com/doi/10.1177/2515245918771304)): **confident the effect is real, and its best estimate is practically meaningful.** The same 0.5R leak at 60 condition trades now passes 80% of the time, and a noise trader passes 5% — before BH, the hold-out and robustness take their further cuts.

| Tier | Requires all of | Ceiling |
|---|---|---|
| **Established** | P_train ≥ 0.95 · m_train beyond θ_min · P_hold ≥ 0.80 · ρ ≥ 0.80 · q ≤ 0.05 · n ≥ n_min · ε · s agree | Needs ≥ `n_hold` condition trades in isolation for that test (§4.6) — so large effects on adequate histories, rarely small ones; impossible for a leakage-flagged test |
| **Likely** | P_train ≥ 0.80 · m_train beyond θ_min · P_hold ≥ 0.65 · ρ ≥ 0.60 · q ≤ 0.10 · n ≥ n_min · ε | The ceiling whenever `n_hold` is not met (§4.6) |
| **Exploratory** | P_train ≥ 0.60 · n ≥ n_min/2 · no kill · P_hold ≥ 0.40 | "Worth watching" only; never a prescription; never in the Process Score |
| **Not enough evidence yet** | Anything else | Stores which gate failed and what would resolve it |

**Kills override tiers:** a sign flip at a neighbouring threshold; P_hold < 0.50 after P_train ≥ 0.95 (the classic overfit signature); a broken model diagnostic.

**θ_min — the practical threshold, anchored in v1.0 (PRE-COMMIT · derived).** Draft 2.1 carried 0.10R and 0.15R as practical thresholds for conditional R tests, from literature habit. Neither had a reason. The threshold now has one: **a conditional effect is worth reporting when the drag it puts on the whole history equals the library bar.** δ_pool is 0.05R per trade (§7.4); at the reference prevalence of 20%, that is a conditional effect of **0.25R**, and that is θ_min for every test whose outcome is R under a condition. For level tests (R1, E2, E4′, S12) and ratio tests (B1, E5, R2, R8's size half) θ_min keeps its own unit and is listed in Annex A. θ_min is compared with the shrunk training median (m_train), not with the posterior's 95% bound — the two-part criterion above — so raising it from 0.15R to 0.25R costs nothing in power for a real 0.5R leak and simply stops a 0.2R effect from being called a Finding. The hold-out requirement is sized separately at θ_hold (§4.6). Three uses of one number were tangled in 2.1 — the posterior floor, the hold-out size and the null's power target — and they are now three named quantities: **θ_min, θ_hold, MDE** (§5.4a).

**Why a bar this high.** The library runs many hypotheses per trader, and finance's answer to a crowded hypothesis space is a far higher bar than nominal significance ([Harvey, Liu & Zhu 2016](https://academic.oup.com/rfs/article/29/1/5/1843824); [Bailey & López de Prado 2014](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)). The numbers above are our judgement, not a measurement. What makes them defensible is not their provenance but their audit: **on 1,000 noise traders, the realised false-Established rate must be ≤ 5%** (§12.3). If it is not, these values move — once, on corpora, before any partner read.

### 5.3 Robustness — PRE-COMMIT · inherited (**denominator closed in 2.1**)

**The problem with ρ = passed / applicable, as Draft 2 wrote it.** A test with two applicable perturbations can score 1.0 while another survives eight. The denominator becomes a hidden selection channel: a narrow test looks more robust than a broad one because less was asked of it. Fixed by splitting the set and requiring a minimum.

**Mandatory — every candidate, no exceptions. A candidate for which any of these cannot be computed cannot reach Established.**

| # | Perturbation | Pass condition |
|---|---|---|
| P1 | Temporal halves of training | Same sign in both; P(θ beyond 0) ≥ 0.70 in each |
| P4 | Threshold sweep ±25% on every numeric threshold in the condition | No sign flip. A monotone dose–response supports; a flip kills |
| P5 | Winsorised (2.5/97.5) versus raw | Same sign; the gap reported |
| P6 | Drop the three largest-magnitude R trades | Same sign. If the effect vanishes it is about concentration, not the condition, and is re-routed to the concentration test |
| P7 | Stationary block bootstrap, 500 resamples, mean block 5 ([Politis & Romano 1994](https://doi.org/10.1080/01621459.1994.10476870)) | Sign stability ≥ 0.80 |

**Conditional — applied where the trader's data supports them, each needing its own minimum.**

| # | Perturbation | Applies when | Pass condition |
|---|---|---|---|
| P2 | Leave-one-instrument-out | ≥ 2 instruments each with ≥ 15% of trades | Same sign in every fold |
| P3 | Leave-one-session-out | ≥ 2 sessions each with ≥ 20 trades | Same sign in every fold |
| P8 | Leave-one-regime-out | ≥ 2 regimes each with ≥ 20 trades | Same sign in every fold |

**The rule — PRE-COMMIT.** ρ = (mandatory passed + conditional passed) / (5 + conditional applicable). **Established requires all five mandatory passed and at least one conditional applicable and passed**; ρ alone is never sufficient. The evidence object records which conditionals were inapplicable and why, so a thin-slice Finding is visibly thin rather than silently flattered.

**`suspiciously_stable` — a review flag, never a kill (clarified in 2.1).** An effect that does not move at all under every perturbation is flagged, because real effects usually bend — but some genuine relationships are legitimately stable, and the flag is not evidence of a bug. The protocol: the research lead checks three things within the week — whether the condition and the outcome share an input (a construction artefact), whether the perturbations actually changed the sample they were meant to change (the blast-radius check), and whether the effect is carried by a handful of trades that every fold happens to contain. If all three come back clean, the Finding is promoted with the flag retained in its record. The flag is never a reason to demote on its own.

### 5.4 Null models — PRE-COMMIT · derived (**algorithms written out in 2.1**)

**Why a null at all.** A trader's outcomes cluster in time, and a condition like "after two losses" is defined by the sequence itself. The question is not "is the difference non-zero" but "would this trader's own trades, with the hypothesised link broken and everything else intact, produce a difference this large by chance." That is a negative control ([Lipsitch, Tchetgen Tchetgen & Cohen 2010](https://pubmed.ncbi.nlm.nih.gov/20335814/)), and it is what turns "try to kill the insight" into a computation.

**Draft 2's N-S was wrong as written, and the second review caught it.** It said to resample "within (instrument × session × volatility tercile) strata" for a test asking whether *session* predicts outcome. Resampling inside a session cannot break the link between session and outcome — there is nothing left to shuffle. The error came from stating invariants without stating the algorithm. Each generator now says exactly what is shuffled and what is held.

**N-B · the sequence null.** For Behaviour tests whose condition is built from prior outcomes or prior actions.
> Within each trading day, hold every trade's timestamp, instrument, session, size and market state exactly as they are; randomly permute **which outcome landed on which trade**. Then recompute the condition from the permuted sequence and re-estimate the effect. *Holds:* the day, the day's total result, every trade's market context, the trader's activity pattern. *Breaks:* the correspondence between a prior loss and this trade's result. 2,000 draws.

**N-S · the context null.** For Strategy and Risk tests conditioned on a market or temporal context — session, regime, instrument, volatility.
> Hold each trade's context label exactly where it is — a 10:05 trade stays a first-hour trade in a high-volatility regime. Permute the **outcomes** across trades **within blocks that share everything except the tested context**: for a session test, within (instrument × volatility tercile × day-of-week), so first-hour and last-hour trades exchange outcomes only when they are otherwise comparable. *Holds:* the real character of each session and regime, and the market state attached to every trade. *Breaks:* the association between the tested context and the outcome. Where a block holds fewer than 8 trades it is pooled with its nearest neighbour on the untested dimensions, and the pooling is recorded. 2,000 draws.

**N-E · the execution null.** For Execution tests.
> Hold the trade, its instrument, its session and its own realised MFE/MAE path. Replace the trader's actual exit point with one drawn uniformly from the feasible exit points along that same path. *Holds:* the opportunity each trade offered. *Breaks:* the trader's skill in choosing when to leave — the "random exit" counterfactual. 2,000 draws.

**N-C · the cell null.** For Edge Map cells.
> Compare the observed cell's mean against the distribution of means from same-size random cells drawn within the same dimension, holding the dimension's real structure. *Breaks:* the cell's identity. 2,000 draws.

**The nulls are themselves validated — PRE-COMMIT, a gate and not an open question.** Each generator runs on both classes of noise trader (§12.2), and its realised false-positive rate at each tier must sit inside **[2%, 8%]** for a nominal 5%. Outside that band the null is broken — too liberal invents Findings, too conservative hides them — and it is fixed before Phase 1 rather than carried as a caveat. **The adversarial noise class is the one that matters here:** a null that looks well-calibrated on i.i.d. noise and fails on realistically clustered noise has not been tested.

**What the shuffle test does and does not establish — PRE-COMMIT · derived (added after the walkthrough, 2 Oct).** Two misreadings are easy and both are costly, so they are ruled out here rather than left to the reader.

- **A pass does not name a mechanism.** It establishes that the gap is not a fluke of sequencing. It is silent on cause, and at least three causes produce an identical pass: the trader's own behaviour changed (he sized up, he re-entered faster); his edge genuinely degrades in the conditions that happen to follow losses (volatility clustering); or his costs rise in those conditions (spreads, slippage). Only the first makes a behavioural prescription correct — see the mechanism requirement in §11.
- **A failure has two meanings and they must never be conflated.** Either the clustering explains the gap (no pattern), or a pattern exists and the test could not see it. **The second is common.** Measured on simulated traders who genuinely carry a 0.5R post-loss leak, with the adversarial market structure of §12.2:

| His history | Condition trades | Shuffle test catches him | **Missed** |
|---|---|---|---|
| 200 | 39 | 40% | **60%** |
| 300 | 59 | 57% | **43%** |
| 500 | 97 | 78% | 22% |
| 800 | 162 | 88% | 12% |
| 1,200 | 242 | 97% | 3% |

### 5.4a The confident-null rule — PRE-COMMIT · derived (added 2 Oct, **restated as the MDE rule in v1.0**)

Draft 2.1 triggered "Not enough evidence yet" only when a test could not **run** (n below n_min). It said nothing about a test that runs, finds nothing, and never had the power to find anything — so a trader with 300 trades and a real leak would have been told no problem was found, which is wrong for 43% of such traders (§5.4). The 2 Oct fix made the null binary: "no problem found" if powered at θ_min, otherwise a gap. With θ_min now 0.25R (§5.2), that binary would put almost every null into the gap state — a confident null at 0.25R needs roughly 2,000 trades — which is honest but tells the trader nothing. The rule in v1.0 tells him what *was* ruled out:

> **Every null result carries the minimum detectable effect (MDE) — the smallest effect the test had 80% power to find at his realised sample, one-sided in the pre-registered direction, with the measured 1.65× shuffle inflation.** If MDE ≤ θ_min the result is reported as **"no problem found."** Otherwise it is reported as **"no leak larger than [MDE] found; smaller ones cannot be ruled out at your history,"** with the approximate additional trades that would bring the MDE down to θ_min.

This is §7.5's principle applied to a null: describe what the data could and could not see; never let silence pass for a clean bill. The MDE is computed from the trader's realised condition and comparison counts and his measured σ_R; it is stored on the evidence object as `mde_at_sample` alongside `power_at_theta_min`.

| Effect we would want to rule out | Condition trades for a confident null | Total history at 20% prevalence | at 10% |
|---|---|---|---|
| 1.0R | 25 | 125 | 250 |
| 0.8R | 40 | 196 | 391 |
| **0.5R** | **100** | **500** | 1,000 |
| 0.4R | 157 | 782 | 1,563 |
| 0.3R | 278 | 1,389 | 2,778 |
| **0.25R** (θ_min) | **400** | **2,000** | 4,000 |

So a trader with 500 trades at 20% prevalence is told: *"no post-loss leak larger than 0.5R; we cannot rule out one smaller than that yet."* He learns the size of problem he does not have, which is a real fact about him, and the honesty is in the second clause.

**Read the implication honestly: a confident "you do not have this problem" needs a longer history than a confident "you do."** Establishing a leak takes a handful of condition trades in the isolation zone (§4.6); ruling one out at θ_min takes thousands of trades. That asymmetry is real, it is not a defect of our method, and the product must never hide it behind silence.

### 5.5 Multiplicity — PRE-COMMIT · literature (**overstatement corrected in 2.1**)

Draft 2 said multiplicity was "controlled structurally by hierarchical priors and procedurally by BH." The first half was overstated: shrinkage stabilises estimates, it is not a false-discovery guarantee. Three distinct mechanisms, each doing only what it actually does:

| Mechanism | What it does | What it does **not** do |
|---|---|---|
| **Hierarchical shrinkage** toward a zero-centred prior ([Gelman, Hill & Yajima 2012](https://arxiv.org/abs/0907.2478)) | Pulls weak and noisy estimates toward zero; reduces overfitting; stabilises small samples | Control the false-discovery rate |
| **Benjamini–Hochberg** on the null p-values within each family — F-Strategy, F-Risk, F-Execution, F-Behaviour, F-Cells — at q = 0.05 for Established, 0.10 for Likely | Controls the declared FDR, under its assumptions | Hold if the p-values are miscalibrated, which is why the nulls are validated (§5.4) |
| **The noise corpora** (§12.3) | Measures the realised end-to-end false-discovery behaviour of the whole pipeline | Fix anything by itself — it is the audit, not the control |

The guarantee we stand behind is the third: the measured false-Established rate on noise traders, including the adversarial class. The first two are how we try to earn it.

**Researcher degrees of freedom — what cannot change after a real trader's results are seen at a version:** the test list, every condition and comparison, thresholds, controls, null generators and their algorithms, the robustness set and its mandatory/conditional split, the tier thresholds, the family definitions.


### 5.6 The honest gaps — PRE-COMMIT · inherited
**Not enough evidence yet — data:** quality < 60, or < 50 round trips, or market coverage below 50%. **Not enough evidence yet — this question:** a specific test is under its minimum and could not run; the object records exactly what would resolve it, in trades. **A null that ran is never a gap state:** it is reported with its MDE — what was ruled out and what was not (§5.4a) — because a trader who learns he has no leak larger than 0.5R has learned something true. **No demonstrated edge yet:** adequate data (≥ 100 trips, ≥ 3 months, quality ≥ 60) and no Strategy test reaches Likely with positive expectancy and P(E > 0) < 0.60 overall. The third is a Finding in its own right with a protective move.

## 6. Statistics

### 6.1 The catalogue — PRE-COMMIT method · CALIBRATE parameters
Five models in Phase 0, not nine. The rest are named in Annex D and built when a test needs them.

| ID | For | Model |
|---|---|---|
| **M1** | Conditional expectancy (is R different under a condition?) | Robust hierarchical regression, Student-t errors, **day-level random intercepts** (§6.2); pre-registered controls; never the condition itself |
| **M2** | Rates (re-entry within k minutes; stop moved) | Hierarchical logistic with day-level intercepts; reported in percentage points at his baseline rate |
| **M3** | Latencies and durations | Log-normal on log t, M1 structure, right-censored at session end; reported as a ratio |
| **M4** | Sizes | Regression on log(size / trailing 20-trade median), M1 structure; reported as a ratio |
| **M6** | Edge Map cells | Cell effects as exchangeable random effects within each dimension; broad → narrow, a dimension added only when the level above reaches Likely; n ≥ 20 per cell |

**Diagnostics, every fit:** R̂ < 1.01 · bulk ESS > 400 · zero divergences · posterior predictive check on the R distribution's tails and sign rate. A failed fit is `candidate_killed:diagnostics`, never a caveat.

### 6.2 Serial dependence — PRE-COMMIT · derived (**new; Draft 1 assumed it away**)
Student-t handles fat tails. It does not handle the fact that trades arrive in sequence, cluster within days, and share a market state — and the second review was right that Draft 1's intervals were therefore too narrow. Three measures, in order:

1. **Day-level random intercepts** in M1–M4. Trades within a day share a state; the model says so.
2. **The block bootstrap is the interval authority.** For every promoted Finding, the stationary block bootstrap interval (P7) is computed alongside the model interval. **If the model interval is narrower, the model interval is widened to match.** We never report the narrower of two honest answers.
3. **A pre-registered dependence audit.** Across the corpora, the median ratio of model width to bootstrap width is measured per model. A ratio below 0.85 means the model class is systematically overconfident and is fixed at a major version, not patched per Finding.

### 6.3 Priors — PRE-COMMIT structure · CALIBRATE values (**fund-corpus overreach removed**)
Draft 1 named the limit of the fund's algo corpus and then used it for behavioural priors anyway. That is a category error and it is now a rule:

> **The fund's algo corpus may never produce a prior for a Behaviour- or Risk-family test, and may never enter the Process Score reference population.** Algorithms do not revenge-trade unless coded to; one strategy on one instrument run by one team is not a population of retail discretionary traders.

Consequently, in Phase 0–1 behavioural tests run with **weakly-informative global priors** — effectively close to flat — and hierarchical pooling delivers its benefit only when the real population arrives (≥ 50 traders per stratum; §12.2). The cost is honest and must be stated in the diagnosis: **population-informed estimation is a Phase 2 capability, so the honest-gap rate in Phase 0–1 will be higher than the thesis's steady state assumes.** That is the small-sample unknown (T§23.2) meeting its bill.

Starting values: α ~ N(0, 0.5) · θ ~ N(0, 0.25) global, tightened only by real population data · σ ~ HalfNormal(2) · ν ~ Gamma(2, 0.1) · β ~ N(0, 0.3). Fingerprint strata (instrument class × frequency band × holding band) are defined now and populated later.

### 6.4 What validates the machinery — PRE-COMMIT · literature (**SBC's authority bounded**)
Two suites, and the distinction matters:

- **SBC** ([Talts et al. 2018](https://arxiv.org/abs/1804.06788)) — draw from the prior, simulate, fit, check the true parameter's rank is uniform across 1,000 replications. **What it licenses:** the inference machinery recovers parameters *under our own assumed model*. **What it does not license:** that the model is right. A wrong model can pass SBC beautifully.
- **M-SIM · misspecification suite** — synthetic traders generated by processes our models do **not** assume: heteroskedastic variance, autocorrelated outcomes, regime-switching means, clustered heavy tails, non-linear state dependence, systematic missingness. The question is not whether the point estimate is right but **whether the uncertainty stays calibrated**: 80% intervals must cover in [72%, 88%].

A model that passes SBC and fails M-SIM is a model whose intervals lie. Both gates, or the model does not ship.

### 6.5 Bounds and minimums — PRE-COMMIT · inherited
Winsorisation at 2.5/97.5 of the trader's own R for reporting, with the raw figure always shown and a gap > 30% treated as a concentration Finding. Every trader-facing currency number is the conservative 5th percentile of its posterior; every R number shows its 80% interval. Minimums: per test 30 condition / 60 comparison (**arbitrary**, and §12.3 will show how often they bite) · per cell 20 · per zone §4.6.

## 7. Measuring change — the part Draft 1 got wrong

### 7.1 The arithmetic that forced the rewrite — derived
Neither review checked whether the experiment engine could measure its own target. It cannot. For a within-trader comparison of two windows, the trades needed **per window** to detect a shift δ in per-trade R at 80% power:

| σ_R | δ = 0.05R | 0.10R | 0.15R | 0.30R | 0.50R | 0.75R |
|---|---|---|---|---|---|---|
| 1.0 | 4,947 | 1,237 | 550 | 137 | 49 | 22 |
| **1.4** (typical retail) | **9,695** | **2,424** | **1,077** | **269** | **97** | **43** |
| 2.0 | 19,786 | 4,947 | 2,198 | 550 | 198 | 88 |

Draft 1's δ_floor was **0.05R**, with N capped at 150. At σ = 1.4 that needs 9,695 trades per window — sixty-five times the cap. **Every experiment would have returned "not yet measurable."** The floor was arbitrary, the cap was arbitrary, and nobody multiplied them together.

The three honest endpoints, for the same intervention (a pause rule on a leak occupying 20% of trades with a 0.5R conditional effect):

| Endpoint | What it asks | Trades per window | Verdict |
|---|---|---|---|
| **Overall ΔE** | Did his per-trade expectancy rise 0.10R? | **2,424** | Not measurable per trader, ever, in a retention window |
| **Conditional outcome** | Did expectancy in the leak state improve by 0.5R? | **485** (97 in-state) | Not measurable in a month; a quarterly read for an active trader |
| **Process metric** | Did he follow the rule — 10% → 80% compliance? | **25–40** | Measurable inside one month |
| **Pooled across traders** | Does this move type work? | **10–63 traders** at 40–80 trades each | Entirely feasible in Phase 2 |

### 7.2 The consequence — PRE-COMMIT · inherited from T§11.2 (decided 1 Oct)
> **Efficacy is a population question. Adherence is an individual question.**

The trader-level experiment's **primary endpoint is the process metric** — did he follow the rule, measured on eligible occasions. Its **secondary endpoint is the deterministic avoided-cost accounting** (§7.3). **ΔE remains the North Star** and is read where it can be read: a quarterly per-trader read once enough Reserve trades exist, and — the read that actually establishes whether a move works — **pooled across traders per move type**, which needs tens of traders rather than thousands of one trader's trades (§7.4 sizes it).

This is not a retreat from rigour; it is rigour arriving at an honest answer. A verdict a trader can reach in a month, that means what it says, beats a verdict he can never reach.

### 7.3 Avoided-cost accounting — PRE-COMMIT · derived (**new**)
The strongest honest statement to an individual trader is not a hypothesis test. It is an accounting identity with one estimated rate:

> *"In the last 40 trades you hit 12 post-loss situations. You took 2. Over your history, trades in that state cost you between ₹1,800 and ₹4,100 each. The 10 you skipped were worth at least ₹18,000."*

The counting carries no sampling error; the only uncertainty is the historical conditional rate, already estimated with its interval in the diagnosis. Reported as a conservative bound, framed as "at least", and — this is the rule — **labelled as accounting, not as proof that he improved.** Whether skipping those trades made him better overall is the ΔE question, and the honest answer is the quarterly and population read.

### 7.4 δ_min and N — PRE-COMMIT · derived (**the circularity fixed in 2.1**)

**My error in Draft 2.** I wrote δ_min = φ · max(|P&L_baseline|, fees_baseline) / (N · median risk unit), then said to compute δ_min and derive N from it. But N sits in δ_min's denominator. Iterating it does not converge — from N = 40 it goes to 38,781, then past 10⁹. The second review caught it; it is a real bug and the patch they proposed (fix an N_ref independently) removes the circularity but not the problem: at N_ref = 60 the rule still demands 87,257 trades. The formula was dressing an unmeasurable bar in arithmetic.

**The actual fix is to scope δ_min to the level where it means something.** There are three thresholds, and Draft 2 collapsed them into one:

| Threshold | Where it applies | How it is set | Circular? |
|---|---|---|---|
| **No trader-level threshold at all** | What the trader is told | Nothing. He is given his adherence counts and the avoided-cost accounting as facts (§7.5, DECIDED 2 Oct). The eligible-occasion count still governs *when there is enough to report* — about 5–7 occasions (§7.1) | No — nothing is being declared |
| **δ_pool — the library bar** | The pooled read per move type | **Economic, per move type, independent of any trader's window: 0.05R — DECIDED 2 Oct.** The mean effect below which a move is not worth recommending. At a ₹5,000 risk unit and 40 trades a month that is ₹10,000 a month, about 24% a year on a ₹5 lakh account — the smallest improvement no trader would ignore. The study is sized in *traders* | No — N here is a count of traders, not of his trades |
| **The quarterly read** | A per-trader ΔE report, once Reserve trades allow | **No pre-set bar at all.** ΔE is reported with its interval, and when the interval is too wide to decide, that is the finding: *"not yet decidable — your interval spans −0.1 to +0.3."* | No — nothing is being fitted, because nothing is being declared |

**Why no bar on the quarterly read.** Setting a bar we cannot clear would make every read a failure; setting one we *can* clear would mean choosing the bar from the power, which is the exact sin this document exists to prevent. Reporting the interval honestly is the only option that is neither.

**Sizing the pooled read — against the bar, not against zero (corrected 2 Oct).** Draft 2.1 sized the study as though the test were "is the effect different from zero". It is not: the test is whether the pooled **lower bound clears δ_pool**, so the sample depends on the **gap** between a move's true effect and the bar — not on the bar's height. Adopters needed, at 60-trade windows:

| Move's true effect | bar 0.03R | **bar 0.05R (decided)** | bar 0.10R | bar 0.20R |
|---|---|---|---|---|
| 0.10R | 86 | **168** | never | never |
| 0.15R | 31 | **44** | 176 | never |
| 0.20R | 17 | **21** | 47 | never |
| 0.30R | 8 | **9** | 14 | 55 |
| 0.50R | 4 | **4** | 5 | 9 |

*"never"* means the move's true effect lies below the bar, so it correctly fails however many adopters it has.

**This is why the bar is low.** A low bar is *cheaper* to clear, not dearer, because a genuinely good move sits far above it and a wide gap is easy to prove. The working value of 0.10R carried in Draft 2.1 was **rejected on 2 Oct**: it would have needed 176 adopters to certify a move worth ₹30,000 a month to a trader, so it retired valuable moves for want of affordable evidence.

**A move that fails to certify is parked, not deleted — DECIDED 2 Oct.** Its evidence, adopters and pooled estimate are retained, and it is re-tested as adopters accumulate. **δ_pool decides what we recommend, never what we remember.** A move parked at 40 adopters may certify at 90 without any new thinking, and a move whose estimate drifts toward zero as adopters accumulate is retired with that record attached.

**These remain planning figures, not results.** They assume a between-trader spread of half the effect, which we have not measured. A Phase 1 power simulation on real adoption data replaces them, and until it runs no pooled verdict is issued (Annex H).

**N at the trader level** is the eligible occasions needed before the adherence counts are worth reporting, capped at N_max = min(150 trades, 90 days at his frequency). Above the cap the honest output is *"not yet measurable at your frequency"* and the low-frequency path applies (§12.5).

### 7.5 What a trader is told, and what the pooled read uses — PRE-COMMIT · derived (**rewritten 2 Oct**)

Draft 2.1 gave each experiment an `ADOPTED / PARTIAL / NOT_ADHERED` label gated on an **80% follow-rate**. That number was arbitrary, and its real defect was not its height but that we cannot measure which side of it a trader is on: a trader whose true follow-rate is 75% measures above 80% between 21% and 34% of the time depending on his occasion count. Two traders four occasions apart in fifty would receive different verdicts on the luck of the draw. A threshold we cannot resolve is a coin flip wearing a verdict's clothes.

**DECIDED 2 Oct: there is no trader-level verdict. The trader is told what happened.**

> *"You hit 12 post-loss moments. You traded 1. Over your previous 40 trades, you'd have traded 11 of them. The 10 you skipped were worth at least ₹18,000 at your own historical rate."*

Counts and an accounting, both exact in the part that matters, no pass and no fail. This is the same principle as §11.1a applied to adherence: **describe, do not judge.** It also removes the cliff rather than relocating it.

**Adherence still matters to the research layer, and it enters as a weight rather than a gate.** A pooled estimate that mixes traders who ran the rule with traders who ignored it is diluted toward zero, so adherence cannot simply be discarded. But excluding a trader at 78% while keeping one at 82% imports the cliff into the statistics. Instead, adherence is **modelled**:

| Estimate | What it answers | How |
|---|---|---|
| **As-offered effect** | What happens when we give this move to a trader like him, in the real world where people only partly comply | All adopters included, whatever their follow-rate. This is the number the business should plan on |
| **As-followed effect** | What the rule does when it is actually followed | Adherence enters the pooled model as a covariate and the effect is read at full adherence. This is the number that tells us whether the *rule* is sound |

Both are reported for every move type, and the gap between them is itself informative: a move with a strong as-followed effect and a weak as-offered effect is not a bad rule, it is a rule people cannot keep — which is a design problem, not an evidence problem, and it routes to the Experience Specification rather than to the library.

**The assumption, stated.** Reading the effect at full adherence assumes the dose–response is roughly monotone — more compliance, more effect — and that adherence is not itself caused by the thing we are measuring. Neither is guaranteed. A trader may comply more *because* things are going well, which would flatter the as-followed number. The guard is that the as-offered estimate carries no such assumption, so the two are never collapsed into one figure, and δ_pool (§7.4) is judged against the **as-offered** effect — the conservative one.

**Efficacy labels remain, at the pooled level only**, where an error averages across hundreds of traders rather than landing on one person's screen: `NOT_YET_MEASURABLE` (the default, and not a failure) · `PASS` (as-offered lower bound above δ_pool) · `NO_PRACTICAL_EFFECT` (likely positive, below the bar — the move's priority drops, the Finding stands) · `REFUTED` (interval excludes benefit — the Finding is demoted) · `HARMFUL` (interval excludes zero the wrong way — the move leaves the library at once) · `INCONCLUSIVE` (interval spans the bar — extend once, then park).

**A thesis touch this creates.** T§11.2 as amended on 1 October says a trader-level verdict *is decided on* the process metric and the avoided-cost accounting. Under this decision there is no trader-level verdict to decide. The minimal rewording, for the decision log: *"A trader-level experiment is reported rather than verdicted: the trader sees his adherence counts and the avoided-cost accounting as facts. Adherence enters the pooled read as a weight, not a gate."* | J11 | T§ differentiation · T§22 | The moat statement is sharpened from *"evidence-backed"* to *"pre-committed and measured"*: every test fixed and hashed before his data is seen; the engine's error rate published from noise corpora; five tests computed from data not in his file. And one kill-class finding is added: if the founder-written LLM baseline matches the engine's false-positive rate on realistic noise within five points, the diagnosis has no validity moat (§15). The 30-minute test — *could he reproduce this feature with a chat and his CSV?* — belongs in the PRD as a feature filter, not here | §2, §15 |

| J12 | T§ competition · T§19 · T§23.2 | **The likeliest copier is a broker, not a frontier lab.** A broker holds every trade as it happens — the recurring-data precondition of §7.8, with no re-upload, no trigger and no selection bias — and has distribution. The thesis's competitive section should treat brokers as the primary threat and, separately, as the channel; and the moat statement should name the one asset that stays unique after 1,000 traders and ten years: the intervention–adherence–outcome record on validated fingerprints, scored on one framework version. Everything else — tests, models, the evidence standard, the show — is copyable | §14 (regenerability), reviews of 3 Oct |

Nothing else in v1.4 moves.

**Guardrails and confounds, unchanged.** Drawdown behaviour, execution quality and the avoidable-loss rate may not worsen beyond 10% relative. A shift in instrument mix (> 30 pp), holding band, sizing regime (± 50%) or a framework major version during the window flags the pooled contribution as confounded and that trader's window is excluded from the pooled read with the reason recorded.

### 7.6 What each design may claim — PRE-COMMIT · literature
**Association** (replay): "in your history, this rule would have changed the result, assuming everything else unchanged" — illustration, and the ceiling rather than the expectation (§11.3). **Single-subject** (the live window, an N-of-1 interrupted series with a frozen baseline and a pre-registered decision rule — [AHRQ 2014](https://effectivehealthcare.ahrq.gov/products/n-1-trials/research-2014-5)): "you followed this rule, and these situations were avoided," with the assumptions visible. **Population** (target-trial emulation — [Hernán & Robins 2016](https://academic.oup.com/aje/article-abstract/183/8/758/1739860): eligibility, assignment by randomisation among equally ranked moves, staggered starts, outcome and analysis all fixed before the data): "this move type improves traders like you." Only the third establishes that a move works, and it is a Phase 2 deliverable.

**One more permitted statement, from thesis v1.4 — the conditional forward figure.** The product may state the arithmetic implication of the trader's own measured rates: *"your trades outside this condition averaged +0.12R and inside it −0.4R; if those rates hold, operating only outside it puts your average at +0.12 instead of −0.05."* Three rules bind it in the research layer. The figure uses the **shrunk posterior**, never the raw conditional mean, because the condition singled out as his best is the one most likely to have been flattered by selection. The conditional is shown rather than buried. And it is always phrased as staying out of the negative zone, never as trading more inside the positive one — concentration invites forced marginal setups that degrade the edge being protected. It is a statement about his own process, never a forecast of returns or of the market.

### 7.7 The thesis conflict — **closed** (T§23.1, 1 October 2026)
Draft 2 raised this as an open decision. It is now decided and the thesis is amended to v1.4; the rule below is inherited, not proposed:

> A trader-level experiment verdict is decided on the process metric and the avoided-cost accounting. Trader Improvement keeps its definition and is read where it is measurable: a per-trader quarterly review, and a pooled read per move type that determines whether a move stays in the library. The company North Star is the share of move types with a pooled pass plus the share of traders meeting their process threshold.

Two consequences this document now carries rather than flags. **The Phase 2 gate needs two target numbers** — a share of traders whose adherence counts show they actually ran a rule, and a share of move types with a pooled pass — both set before Phase 2 starts and owned by product with research (T§23.1). **The Experience Specification's wording is gated on research sign-off**, because an external "PASS" that means `ADOPTED` is not what a trader hears as passed (§7.5).

### 7.8 Recurring data — the precondition, and a pre-committed trigger (added v1.0)

Everything in §7 after the diagnosis — adherence counts, avoided-cost accumulation, the quarterly read, the pooled read — needs the trader's trades **after** the diagnosis. The free doormat reads one upload and can never measure change; the measurement architecture exists only for traders who keep supplying data. That makes recurring data supply the precondition for the loop rather than a Phase 2 line item, and it was under-priced in every draft before this one.

**What is known and what is not.** Whether a trader *subscribes* after the doormat is the thesis's willingness-to-pay unknown and is not this document's question. Whether a *paying subscriber* supplies a complete month of trades each month is a separate unknown — a repeated manual action at a moment of no particular motivation, not a decision — and **no value is assumed for it here.** It is recorded in Annex H as a Phase 1 measurement.

**What does not depend on the rate: the missingness is not random.** A bad month is itself a reason not to upload. So whatever share of months goes missing, the missing ones over-represent bad months, and both the avoided-cost accumulation and the pooled read bias upward by an amount the data we hold cannot estimate — because the correction would need the months we do not have. A read-only broker connection supplies the month whether it was good or bad, and that is the whole argument for it: a validity argument that holds at any supply rate strictly between zero and one, not a convenience argument.

**DECIDED 3 Oct, corrected the same evening — PRE-COMMIT · derived.** The first version of this paragraph kept broker connections in Phase 2 and ran Phase 1 on manual re-uploads, with a trigger that moved connections up if fewer than 70% of subscribers supplied a complete month. A review of v1.0 pointed at the inconsistency and it is real: the paragraph above says the bias exists at every supply rate, and the trigger measured the rate. **A rate trigger cannot catch a bias that is present at every rate.** The decision was cost-driven and the cost was overstated — crude-first puts the partners on a handful of brokers, and India's broker APIs expose read-only trade books, so the connectors are weeks of work inside Phase 0, not a Phase 2 programme. The research layer's requirement is therefore stated as what it is:

> **A read-only broker connection is the subscription's data path from Phase 1. Manual upload is the doormat's path and a fallback, never the primary path for a paying subscriber.**

Three consequences. The data engineer builds read-only connectors for the brokers the design partners actually use in weeks 5–8 (§13.2), so Phase 1 opens with them. A month supplied manually is accepted and carries a `supply_bias` flag: it enters the trader's own adherence counts and avoided-cost accounting unflagged, because those are facts about trades we hold, but it enters a pooled read only with the sensitivity bound — the as-offered effect (§7.5) computed a second time under the assumption that his missing months were his worst — and both figures are reported. **What is measured instead of the old trigger** is the share of paying subscribers connected by the end of their first month; the 70% stays as the labelled-arbitrary bar for that count, and below it the Experience Specification treats connection friction as its first problem — a product finding, where the old trigger would have produced a data-architecture finding a year late. "Complete" keeps its meaning: a month reconciles to the broker statement under §4.2; a partial export is a missing month. The Phase 2 version of this decision is preserved in Annex I so that the reversal is visible rather than silent.

**The record starts with the first experiment, not with Phase 2.** The pooled *read* needs tens of adopters and waits (§7.4); the *rows* do not. A Phase 0 partner who adopts a move at his concierge session is the first row of the intervention–adherence–outcome record, and the schema (Annex C, with the experiment fields) is fixed now so that the first row and the ten-thousandth are comparable (§14, regenerability).

## 8. The risk envelope — PRE-COMMIT · inherited
Fixed from the baseline window before any experiment starts, and the rule is blocked if the replay raises any of: r_max (95th percentile risk per trade, currency and % equity) · q_max (position size, leverage) · n_day (95th percentile trades per day) · L_win (worst rolling N-trade loss under the rule). A rule whose replay cannot bound all four is `uncertain_risk` and is never surfaced. **Safety pause (renamed from auto-stop in v1.0):** a window whose drawdown exceeds the baseline maximum or L_win is paused and surfaced to the trader as a fact — *"your drawdown has passed the level your history showed; the rule is paused until you choose to resume."* Draft 2.1 also stopped a window on adherence below 50% over 10 occasions; **that stop is removed**, because §7.5 decided there is no trader-level adherence verdict, and a trader who is not following a rule is as-offered data (§7.5), not a failed experiment. Every move type carries a class — **always permitted** (deletion or cap rules, which only remove or reduce exposure) / **conditional** (rules that change exits or add exposure, needing the price path and an assumed fill) / **never** — assigned at library admission by the in-house trader and the research lead, and re-checked per trader by the screen. All five Phase 0 starter move types are always-permitted (§11.1).

---

# Part II — The Phase 0 Programme

**The one question Phase 0 answers:** *does the engine find something true that a real trader confirms and can act on?* Everything below is sized to answer that in eight weeks. Draft 1's programme — 43 tests, 9 models, 15 moves, a full Process Score — was a year of engineering wearing an eight-week label, and would have spent Phase 0 proving infrastructure instead of learning the product.

## 9. The core library — eighteen tests and the Edge Map

**Selection rule (PRE-COMMIT · derived; rewritten in v1.0).** A test is in the core only if it has high prevalence in retail histories, a plausibly large effect, **no dependence on data beyond the trader's own trades, the traded instrument's own price series (held in-house for crude), and public calendars**, and a move attached. Draft 2.1's rule said "no dependence on market data we may not license" and then listed four tests that depended on exactly that — the walkthrough caught the contradiction. The crude-first decision (§1) dissolves it: we hold the price series, so market context is no longer a licence question, and the regime labels come from **the fund's existing regime definition, unchanged** — pre-committed for another purpose, so it cannot have been tuned to produce trader findings, and a market-data convention rather than a behavioural prior, so the §12.2 wall holds. Everything else goes to the candidate register (Annex B) and is built when the core has earned it.

**Two classes.** *Unconditional* tests run on every history; *conditional* tests run only where the export carries fills or stop orders (§4.2) and otherwise report `unavailable`, never a null.

| ID | Test | Condition → outcome | Model · null | Move | Seed / anchor | Class |
|---|---|---|---|---|---|---|
| **B1** | Post-loss latency | prior loss → time to next entry | M3 · N-B | PL-1 | revenge trader | unconditional |
| **B2** | Post-loss expectancy | ≥ 2 prior losses → R | M1 · N-B | PL-1 | [Coval & Shumway 2005](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2005.00723.x); [Liu et al. 2010](https://pubsonline.informs.org/doi/10.1287/mnsc.1090.1131) | unconditional |
| **B5** | Sequence decay | nth trade of the day → R | M6 · N-B | DL-1 | [Barber & Odean 2000](https://doi.org/10.1111/0022-1082.00226); overtrader | unconditional |
| **B12** | Day-outcome after a bad start | first two trips lost → the day's net R | M1 · N-S | DL-1 | added 2 Oct (§11.1b) | unconditional |
| **R1** | Size dispersion and tail | CV of risk per trade; share of loss from worst 5% | Fact + bootstrap | RK-1 | AUTOPSY risk profile | unconditional |
| **R2** | Post-loss size change | prior loss → log size ratio | M4 · N-B | PL-1 (merged) | size-up trader | unconditional |
| **R7** | Stop discipline | stop order placed → moved away or cancelled before fill; outcome of those trips | M2/M1 · N-B | RK-1 | promoted 3 Oct — adherence is now load-bearing (§7.5) | **conditional** (stop orders) |
| **R8** | Volatility–leverage coupling | vol tercile → leverage; high-vol → R | M4/M1 · N-S | RK-2 | high-vol trader | unconditional |
| **R11** | Adding to losers | same-direction fill while the open position is at a loss → final R of the trip | M1 · N-B | RK-3 | added 3 Oct — "averaging" is endemic in Indian retail | **conditional** (fills) |
| **E2** | Exit capture | capture ratio on winners vs reference | M1 · N-E | EX-1 *(Phase 1)* | scared winner; AUTOPSY Cat_5 | unconditional (tick data) |
| **E4′** | Late loss accrual | losers whose MAE reached his own median loss → extra loss beyond that point | M1 · N-E | EX-2 *(Phase 1)* | replaces E4, 3 Oct — the recorded stop is intent | unconditional (tick data) |
| **E5** | Holding asymmetry | winner vs loser duration ratio | M3 · N-E | EX-1/EX-2 *(Phase 1)* | disposition effect; [Odean 1998](https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00072) | unconditional |
| **S1** | Session expectancy | crude session bucket → R | M6 · N-S | SS-1 | session trader | unconditional |
| **S5** | Regime expectancy | fund regime label → R | M6 · N-S | RK-2 | fragile trader | unconditional |
| **S6** | Overnight carry | position held across the session close → R | M1 · N-S | OV-1 | added 3 Oct — crude gaps on the US close and on inventory data | unconditional |
| **S10** | Scheduled-event trading | trade overlapping a release window (EIA, API, OPEC) → R | M1 · N-S | EV-1 | added 3 Oct — "trading the inventory" is the crude retail habit | unconditional (public calendar) |
| **S11** | Edge persistence | his last 100 trades vs the 100 before → R | M1 · N-B (window-level) | PR-1 | promoted 3 Oct — turns "no edge yet" into "edge decaying" | unconditional |
| **S12** | Overall edge | P(E > 0), regime-standardised | M1 | PR-1 | powers "no demonstrated edge yet" | unconditional |

Plus **C1 — the Edge Map cell family** as the foundation of the map, broad → narrow.

**What left and why.** E4 (loss extension past the recorded stop) is replaced: the stop is intent, and trade data cannot contain intent (§11.1a) — a trader with a mental stop has no stop in any export. E4′ asks the price path a question it can answer: on losers that got as bad as his typical loss, how much more did he lose after that point? B6 (daily-loss-limit behaviour) is retired from the register as the same question as B12.

**What is crude-specific and must be re-established per instrument family.** S1's buckets — *morning (9:00–12:00) · afternoon (12:00–17:00) · US overlap (17:00 to close)* — are MCX crude's sessions, not equity's. S10's calendar is crude's. S6 matters for crude because the Indian session closes while the US one is open. The prevalences and effect sizes of all eighteen on crude traders say nothing about index-option traders (§1, Annex H).

**Where the founder's field knowledge enters.** The three crude-specific additions are my judgement from the structure of the market, not a measurement; the Phase 0 feasibility count (§15) measures how often each core test actually reaches its minimum on partner histories, and a test that starves is diagnosed and cut there. The register remains open to a behaviour the in-house trader or the founder has watched and does not see listed — it enters through Annex B as a one-line question and is promoted through §13.3.

**Five of the eighteen cannot be computed from the trader's own CSV at all** — E2, E4′, R8, S5 and S10 need the contract's tick history, the fund's regime labels or the release calendar — which is the doormat's immediate data edge over any analysis of the file alone (§15, the baseline). S12 is not optional: it is what makes the honest-gap state a research result rather than a UX apology. S11 is its companion: *no demonstrated edge* and *an edge that was there and is decaying* are different findings with different moves. Full protocols are in Annex A; the protocol form is unchanged from Draft 1 — that part was right.

**The candidate register (Annex B)** holds the rest as one-line questions with their seeds. They are not built, not pre-registered, and not validated in Phase 0. They enter through the lifecycle (§13.3) when the core has proved the machinery works.

## 10. What Phase 0 does **not** build

| Deferred | Why | When |
|---|---|---|
| **The Process Score** — mapping, weights, reference population, band propagation, gaming suite | The most complex thing in Draft 1 and the least urgent. Phase 0 needs one thing: does a Finding land? A score that compresses Findings is meaningless before there are Findings, and its reference population does not exist | Structure fixed now (Annex E); calibrated in Phase 1; public on the Card only after convergent and predictive validity (T§A2) |
| **Nine statistical models** | Five cover the eighteen core tests — the additions reuse M1, M2 and M6 | The rest with the tests that need them |
| **Fifteen intervention moves** | Zero have evidence anyone adopts them. Phase 0 defines **five starter move types** (§11.1) and should *output* the two or three that partners actually adopted, not *input* fifteen | §11 |
| **The full synthetic grid** (5,000 histories × behaviour × size × prevalence × length) | Generating it is weeks. Every core test gets one planted behaviour and nothing else varies beyond effect size and history length (§12.2) | §12.2 |
| **Population priors and fingerprint strata** | No population exists (§6.3) | Phase 2 |
| **Pooled reads per move type** | They need tens of adopters, and Phase 0 has 20–50 design partners with no live experiments. **The record they read from starts earlier**: a partner who adopts a move at his concierge session is its first row (§7.8) | Phase 2 for the read; the rows from the first adoption |
| **The hypothesis inbox and exploratory cohort** | No confirmatory baseline to protect yet. **Its Phase 0 substitute is the candidate register** (Annex B): a proposal from any source — a researcher, the in-house trader, a language model — is written there as a one-line question with its seed, and goes no further until the core has proved the machinery | Phase 1 |

**The Process Score's structure is still fixed now** (Annex E: Findings map to sub-scores by family; Established full weight, Likely half, Exploratory zero; effect- and sample-weighted contributions; a band propagated from the contributing posteriors; no band, no score; an unscored sub-score is never zero). Fixing the structure costs nothing and prevents a Phase 1 improvisation. Calibrating it costs the whole of Phase 0. **And one rule from the second review, accepted without qualification: synthetic traders may never define the reference population.** They test whether the score behaves; they cannot say what 50 means for a real person. Until the real population is large enough, the score is labelled *provisional, non-comparable* and shown without a population anchor — or not shown.

## 11. The starter interventions — five move types, offered as a set

**Where a move comes from — the direction of the logic (T§10, v1.4).** The engine first establishes which of the trader's conditions carry validated positive expectancy and which carry validated negative. The rule follows: *operate inside the validated positive conditions, stay out of the validated negative ones.* **A move is never the output of a search for whichever rule most improves his history** — that is curve-fitting a trader's past, and it is the same sin as freezing the best parameter of a sweep.

### 11.1 The starter set — DECIDED 3 Oct

Five move types, written as six rules because the post-loss type has two alternates (PL-1 and DL-1) that are never offered together. Each is offered to a trader only when its own test validates at ≥ Likely for him; the set he sees is the subset that validated, merged by overlap (§11.2). All are deletion or cap rules — they only remove or shrink exposure — so all are **always permitted** (§8), every replay is deterministic, and none needs an assumed fill.

| Move | Rule | Requires | Process metric (the trader-level endpoint) |
|---|---|---|---|
| **PL-1** | After 2 losses: wait 30 minutes, and return at normal size | B1 or B2 ≥ Likely, **merged with R2 where R2 ≥ Likely** | Eligible post-loss occasions handled per the rule — a count, no target (§7.5) |
| **DL-1** | After the day's first two losses: done for the day | B12 ≥ Likely | Qualifying days on which no further trade was taken — a count |
| **RK-1** | Risk cap per trade at his own median | R1 ≥ Likely, or R7 ≥ Likely | Trades inside the cap — a count |
| **SS-1** | No-Trade Zone: skip a validated-negative session bucket | S1 ≥ Likely, θ ≤ −θ_min | Trades in that bucket — a count |
| **EV-1** | No new positions from 15 minutes before to 30 minutes after a scheduled release (EIA, API, OPEC) | S10 ≥ Likely, θ ≤ −θ_min | Release windows on which no position was opened — a count |
| **OV-1** | No positions held across the session close | S6 ≥ Likely, θ ≤ −θ_min | Sessions closed flat — a count |

**The pre-registered merge — PL-1 and DL-1 act on overlapping trades.** A trade after the day's second loss is in both rules' sets. By §11.2 they are never offered side by side. The merge rule, fixed now: **if B12 validates, DL-1 replaces PL-1** (a day that is already going badly after two losses is the stronger finding and the daily limit subsumes the pause); **if only B1/B2 validate, PL-1 is offered.** One rule, one adherence count, one avoided-cost figure, whichever way it goes. EV-1 and SS-1 overlap when the validated-negative session bucket is the US overlap, which contains the EIA window; the interaction check (§11.2) decides merge or sequence per trader from the trade-level diff of the two replays.

**What is not in the starter set, and why.** RK-2 (regime cap) and RK-3 (no adding to losers) are implied by R8/S5 and R11 and are built as move types in Phase 0, but they enter the offered set only after the in-house trader has written their replay and risk envelope (week 5–6) — RK-3 in particular needs fill-level replay. **The exit moves EX-1 and EX-2 move from "out of Phase 0" to Phase 1 candidates**: with tick-resolution crude data their replays can be bounded (the Annex H question is answered by the data decision), but they are conditional-class — they change where he leaves a trade and assume a fill — and the first eight weeks are for moves whose risk envelope is trivially bounded. Draft 2 listed PL-1 and PL-2 separately; they are one rule, because they act on the same trades and the Risk DNA finding says he sizes up *because* he just lost — two competing rules over one set of trades are never offered (§11.2).

### 11.1a Describe the behaviour; never claim the cause — PRE-COMMIT · derived (added 2 Oct, **rewritten the same day**)

**What was withdrawn, and why.** An earlier version of this section claimed that the *consistency* of a behaviour separates a trader who followed his own plan from one who lost control, citing a simulation with no misclassification. **That simulation was circular:** its "systematic" trader was defined as low-variance and its "reactive" trader as high-variance, so showing that variance separates them proved nothing about real traders. The reasoning fails on contact with two ordinary cases — a compulsive martingale gambler doubles after every loss and is *perfectly consistent with no plan at all*, while a discretionary trader whose plan says "size up when the setup is strong" is *erratic entirely by design*.

**The underlying rule, and it is not negotiable: trade-level data cannot contain intent.** A tradebook records what a trader did, never why. Intent sits in the same category as emotion, which T§5.3 already forbids us from claiming. No statistic computed from fills recovers it.

**So the engine describes and does not diagnose — DECIDED 2 Oct.** Two facts are reported, both computed, neither interpreted:

| Reported | Example | Status |
|---|---|---|
| **Magnitude** — how much the behaviour changes in the state | "After a loss your next position is 1.8× your usual size" | Fact |
| **Consistency** — how reliably it happens | "You do this on 9 of every 10 occasions" | Fact. Informative to the trader; **not a classifier** |

Consistency keeps its place as a *described* quantity because a trader benefits from knowing whether his pattern is regular or erratic. It loses its diagnostic role entirely: it may not select a branch, label a cause, or gate a prescription.

**Forbidden language, extending T§5.3.** Never "revenge", "tilt", "lost control", "undisciplined", "emotional" — and now also **never "your plan", "your system", or "your rule"**, because we do not know what they are. A sentence that attributes the behaviour to his intention, in either direction, is outside what the data supports.

**The prescription does not need the cause — only the language would have.** Capping size after a loss is risk-reducing whether the size-up is his plan or his reaction, so the move is offered on risk-reduction grounds alone (§8) and the trader decides whether it conflicts with something he intends. This is why the "ask him one question" option was **considered and rejected on 2 Oct**: it would have bought only a change of wording, at the cost of friction inside a show whose first principle is that the machine works harder than the user.

**Where intent legitimately arrives: the dispute path, unprompted.** A trader who marks a Finding **"right facts, wrong reading"** has told us it is his intention, in his own time and without being asked. T§6.1 already handles it — that label demotes the interpretive layer while keeping the pattern, and re-scopes the Finding. **That is the only channel through which intent may enter a Trader Model.** It is volunteered, never solicited, and never inferred.

### 11.1b The day-level test — PRE-COMMIT (added 2 Oct)

**B12 · Day-outcome after a bad start.** *Do days that open with two losses end worse than days that do not?* Unit: the trading day, not the trade. Condition: the first two resolved round trips of the day were losses. Outcome: the day's net result in R. Model M1 with day-level observations; null N-S stratified on weekday and volatility tercile (the within-day shuffle cannot see this effect — see below). Minimum: 20 qualifying days and 40 comparison days. θ_min = 0.5R per day (**arbitrary**). Implied move: DL-1, the daily limit, which replaces PL-1 when B12 validates (§11.1).

**Why it is needed.** The within-day shuffle preserves each day's total by construction, so damage that spreads across a whole day is largely invisible to it: measured detection falls from 61% to 35% when the leak degrades the rest of the day rather than one specific trade. A day-level *null* was tested as the remedy and **rejected** — shuffling whole days against each other preserves the within-day link entirely and fires on 0.8% of everything, real leaks included. A null that does not break the link under test has no power at all. The remedy is a test whose **unit** is the day, which is what B12 is.

### 11.2 Offering the set — overlap, not count (T§10, v1.4)
The whole set is offered and the trader may adopt all of it, provided every move is risk-reducing. The constraint is overlap:

- **Disjoint trade sets run in parallel**, each measured separately. Post-loss and last-hour states collide on roughly 3% of trades, so each rule keeps its own adherence count and its own avoided-cost figure.
- **Same trade set → merged into one rule before being offered**, with one adherence count and one avoided-cost figure.
- **Attribution is unaffected by how many he adopts**, because both reported quantities are per-rule counts rather than inferences: adherence is counted against each rule's own eligible occasions, and every avoided trade is assigned to **exactly one** rule by the same mutually-exclusive assignment that stops Avoidable Loss double-counting overlapping leaks (Annex F). The assignment rule is pre-registered per pair of overlapping moves.
- **Overlap is computed, not assumed:** the interaction check is the trade-level diff of the two replays — the blast-radius rule. Two moves whose replays touch more than 10% of the same trades are treated as overlapping and merged or sequenced.

### 11.3 Replay — illustration, never evidence, never a selector (T§10, v1.4)
- **It may not rank.** "Impact" in the Next Best Move ranking is the Finding's **hold-out-validated effect size**, never the replay's improvement, which is an in-sample fitted quantity. A rule chosen because its replay looked best is a fitted rule.
- **It is a ceiling, not an expectation.** A deletion replay assumes the removed trades would not have been replaced — which a compulsive trader would have done. The copy says "would have been worth up to", never "will be worth".
- **Assumptions, stated.** Deletion replays assume no substitution; scaling replays assume no market impact at retail size; exit replays need the tick-resolution MFE/MAE path for the contract traded (§4.2) and are refused without it.
- **Every replay reports** its bootstrap interval, the trades it touched, and the maximum loss under the rule — the inputs to the risk screen — and is labelled in-sample wherever it appears.

## 12. Evaluation

### 12.1 Correctness — the gates that do not depend on anyone's opinion
CTR fidelity, fees, feature unit tests, metric golden tests (§4.2) · the leakage suite L1–L3 (§4.4) · SBC and M-SIM on every shipped model (§6.4) · null validation on noise traders (§5.4). These need no users and no market judgement, and they are built first because everything downstream is meaningless without them.

**Determinism — split in 2.1.** Draft 2 required "identical hashes across runs and platforms" for everything. That is right for data transformation and wrong for posterior computation, where a legitimate floating-point difference between platforms would fail the whole Research Gate.

| Layer | Standard |
|---|---|
| **Data artifacts** — raw events, the CTR, features, charge calculations | Exact canonical hash, identical across runs and across platforms. A difference is a bug |
| **Statistical outputs** — posteriors, tiers, scores | Canonical serialisation after fixed rounding and fixed ordering, with declared tolerances: tier assignments and promotion decisions must be **identical**; posterior summaries must agree to the reported precision (3 significant figures) and their intervals to within 1% relative. Seeds are fixed per (trader, test, version) and the container image is pinned and recorded in the lineage |

A tier that flips across platforms is a failure whatever the tolerances say — the decision must be reproducible even where the twelfth decimal place is not.

**The golden set splits in two (2.1).** Draft 2 had engineers building the importer against the same 200 hand-verified round trips used to certify it — a miniature version of the train/test leakage the document forbids elsewhere. From now: **development fixtures** (≥ 100 round trips per broker) are open to engineering throughout; the **certification set** (≥ 200 per broker, drawn from different accounts and different months) is frozen, held by the validator, and opened once per framework version at the gate. A failure on certification is a real failure and is not patched by adding its cases to the fixtures.

### 12.2 The three corpora — ranked, not equal
The second review was right that Draft 1 gave five things equal billing. There are three, and they answer different questions with different authority:

| | **Synthetic** | **Fund corpus** | **Design partners** |
|---|---|---|---|
| **Answers** | Can the engine recover what we planted, and stay silent on noise? | Are the computations right on data whose truth we know? | Is any of this true and useful in the messy world? |
| **Authority** | Test-bed. Proves the machinery, never the product | Correctness only | **The truth.** The only corpus that can fail the product |
| **Licenses** | Recall, false-positive rates, interval coverage, Avoidable Loss bounds, null validation | CTR and feature correctness; session/regime/exit research; market-context calibration; a **weak prior on move-type effectiveness** for the Phase 2 pooled read, labelled algorithmic | Everything about whether a Finding lands |
| **Forbidden** | Defining a reference population; standing in for recognition | Behavioural priors; the Process Score reference; any behavioural claim | — |
| **Size in Phase 0** | 153 cells × 8 seeds ≈ **1,200 histories**, plus **1,000 noise traders in two classes** | 100+ algo iterations, inside the fund's environment | 20–50 partners, **all MCX crude** |

**The synthetic generator.** The fund's own crude tick history as the market layer; a base policy with a tunable edge; **one planted behaviour per core test — seventeen**, because a test with no planted truth has no measured recall, and an unmeasured recall cannot sit behind a gate (§15). Draft 2.1 planted six and left seven core tests with no ground truth; that was the grid being sized by generation effort rather than by what the gate needs. The seventeen reduce to **three mechanisms** — a drift shift under a condition flag (B2, B5, B12, R8's R half, S1, S5, S6, S10, S11), a size multiplier under a condition flag (R2, R8's size half, R1, R11), and an exit-timing modification along the path (B1, E2, E4′, E5, R7) — so the generator is three policy hooks and seventeen flag definitions, not seventeen generators. S12 needs no planted behaviour; its truth is the noise class. The grid: **17 behaviours × 3 effect sizes × 3 history lengths = 153 cells, × 8 seeds per cell ≈ 1,200 histories.** Each history is generated **twice from the same seeds, with and without the behaviour** — the twin run is what gives the true avoidable cost and the true conditional effect. The effect sizes planted are **θ_min, 2θ_min and 4θ_min** for each test's own unit (0.25R, 0.5R, 1.0R for conditional R tests), so recall is read at the threshold the product claims to detect and at the sizes it leads a show with.

**Two classes of noise trader (new in 2.1).** Draft 2 said noise traders "carry no state dependence and a zero edge," and the second review was right that an i.i.d. zero-edge trader is too easy to be a negative control — a pipeline can pass it while only being good at avoiding false positives on unrealistically clean data.

| Class | Construction | What it tests |
|---|---|---|
| **Clean null** (400) | Zero edge, no state dependence, trades drawn independently | The floor: does the pipeline invent Findings from nothing at all? |
| **Adversarial null** (600) | Zero edge and **no planted behaviour**, but realistic structure: volatility clustering from the real market layer, autocorrelated outcomes, regime switching, clustered losses, heavy tails, a trade frequency that drifts over the history, and a changing instrument mix | The real test: does the pipeline mistake market structure for trader behaviour? |

**The gates (§12.3) are read on the adversarial class**, with the clean class reported alongside. A null generator, a tier threshold or a model whose error rate is fine on clean noise and wrong on adversarial noise has not been validated.

**The boundary (PRE-COMMIT · inherited from T§19):** the fund's corpus stays inside the fund's environment; only pattern types, calibration curves and aggregate parameters leave it; nothing from a trader ever enters it. **The CEO signs this line specifically.** Its intervention-outcome rows have one purpose and no other: each algo iteration's *what changed → what happened to expectancy, drawdown and risk per trade* becomes a weakly-informative prior on **move-type effectiveness** for the Phase 2 pooled read, labelled algorithmic and down-weighted accordingly. It is never a prior on human behaviour.

### 12.3 Statistical gates — CALIBRATE targets, PRE-COMMIT procedures (**"medium effect" removed in v1.0**)

Draft 2.1 wrote "recall ≥ 80% at medium effect, n = 300" and never defined *medium*. Worse, our own §5.4 table shows a 0.5R leak at 300 trades is caught 57% of the time — so if medium meant 0.5R, the gate was set above what the arithmetic permits and Phase 0 would have failed in week 8 by construction. A gate must test the engine, not the physics. Two gates replace the one line:

- **Recall on powered histories.** For each core test, on synthetic histories where the planted effect is **2θ_min** and the condition count is at or above the count at which that effect is detectable with 80% power (the §5.4a table; 100 condition trades for 0.5R), recall at ≥ Likely must be **≥ 80%**. This is the engine being asked to find what it was given enough data to find.
- **Honesty below power.** On synthetic histories **below** that count, the engine must report the null with an MDE at or above the planted effect — *"no leak larger than X found"* where X ≥ the planted size — in **≥ 95%** of runs. This is the engine being asked not to claim a clean bill it cannot support. Together with the first gate it means the reported MDE is calibrated: when the engine says it could not see something, it could not.

The full set: those two · false-Established ≤ 5% and false-Likely ≤ 15% per noise trader-run · interval coverage within ±5 pp of nominal · null false-positive rates inside [2%, 8%] · Avoidable Loss coverage ≥ 95% and median recovery ≥ 0.5 on twin runs at 2θ_min on powered histories · M-SIM coverage in [72%, 88%]. **The recall-versus-sample curve for every test is reported** in the scorecard at θ_min, 2θ_min and 4θ_min — it is the single most useful thing the Experience Specification can be handed, because it says what each trader's history can and cannot show.

**The measurement Draft 1 avoided:** how often does `insufficient_data` fire on real histories? Thirty trades in a condition is thin, and on a 200-trade history a 20%-prevalence condition yields 40. Phase 0 reports, per core test, **the share of partner histories that reach n_min at all** (can the test run?) and, beside it, the share whose isolation zone clears that test's `n_hold` (can it reach Established?) — two different quantities since Concept 1, reported as two columns. If the core tests fire on fewer than half of real partners, the library is wrong for the market — and that is a Phase 0 finding, not a Phase 1 surprise.

### 12.4 Recognition — and it is not accuracy
A trader saying "yes, that's me" is **recognition**, not correctness. Accuracy belongs to known truth. Phase 0 measures **user-confirmation rate** (Accurate / Not sure / Wrong per Finding type and tier), **dispute rate** and **upheld-dispute rate**. The thesis's "user-confirmed accuracy ≥ 80%" maps to **user-confirmation rate ≥ 80%**; the research layer uses the precise wording and the Experience Specification follows.

**The sampling problem, closed in 2.1.** The product computes everything and reveals by interest — so if confirmation is measured only on the Findings the reveal engine chose to surface, we create a feedback loop: better reveal ranking → higher confirmation → apparent research success, with the engine's actual accuracy unmeasured. The fix is a **pre-registered recognition sample**: a stratified random sample of **eligible** Findings — drawn by tier and by DNA, independently of presentation ranking — is put to the trader for labelling in every concierge session and, from Phase 1, in a sampled share of sessions. The confirmation rates in the scorecards are computed on that sample. Rates from surfaced-only Findings are recorded separately and are never the reported figure.

**The expert panel — three questions, not one number (separated in 2.1).** Three to five independent traders and researchers (not PlusEV staff; the fund's own researchers form a separate internal panel for the fund corpus), blind, 20 anonymised histories with the Mirror facts and the trade list, no engine output, 45 minutes each. Draft 2 collapsed the result into a single "agreement" figure across mixed material, which the second review rightly rejected: experts cannot establish ground truth for a synthetic history, because the generator already holds it.

| Histories | The question it answers | Metric |
|---|---|---|
| **10 partner histories** | Does the engine find what a skilled human finds in real, messy data? | Agreement — Jaccard overlap between the engine's three Established/Likely Findings **ranked by hold-out-validated effect** and the panel consensus (≥ 2 experts) on his **costliest patterns** — a described behaviour and its cost, never a cause (§11.1a); precision; actionability of the engine's top move, rated blind to origin |
| **5 synthetic with planted behaviours** | Does the engine find what is *known* to be there? And how do experts compare? | Recall against the generator's ground truth, for the engine and for the panel separately. **The ground truth is the generator's, never the panel's** |
| **5 adversarial-noise histories** | Does either invent findings where there is nothing? | False-positive count, engine and panel reported separately |

**Inter-rater κ among the experts is reported as the ceiling** on the partner histories — the engine cannot be expected to agree with experts more than they agree with each other, and a low κ is itself the finding. The three numbers are never averaged into one.

### 12.5 Low-frequency traders — the measurement, then the decision (new in 2.1)
A trader needs roughly **5 trades a week** to produce a readable adherence count inside two months; at 3 a week it is about 14 weeks, at 1 a week nearly a year. The thesis targets traders with 100–2,000 trades, a band that includes people the loop cannot serve on that timetable. The diagnosis works for all of them — it reads the history they already have — but the improvement loop does not.

Draft 2 named the state and moved on. **2.1 makes it a Phase 0 measurement, due week 5:** the share of design partners trading ≥ 5, 3–5, and < 3 times a week, and the distribution of eligible-occasion rates for the core moves at each. The segmentation decision is then made on that number, from three options already identified — a per-opportunity move class whose metric counts eligible occasions rather than trades; a longer-horizon framing with interim process reporting; or an explicit statement that the loop serves active traders and everyone else gets the diagnosis. **The research layer's position is that none of the three is chosen before the count exists.**

## 13. The eight weeks

### 13.1 Week 1 — the commitment
One session: research lead, in-house trader, data engineer, CEO. Before any external data is ingested, Part I is signed, written to `services/research/prereg/framework_v1.yaml`, hashed, and the hash recorded in the decision log and the kickoff minutes. Also week 1, in parallel: the **AUTOPSY portability audit** — which categories generalise to external tradebooks and which are strategy-specific — because it is the single highest-variance unknown in the plan and it decides whether Phase 0 is eight weeks or a rebuild; the CTR specification and data contract v1, **with contract identity and price-path resolution as correctness requirements** (§4.2); the start of the trademark search; and **the recruitment count** — twenty MCX crude design partners with adequate histories named by the end of week 2, or the recruitment-only widening in §15 applies.

### 13.2 Weeks 2–7 — build, then measure

| Weeks | Work | Output |
|---|---|---|
| 2–3 | Synthetic generator (three mechanisms, seventeen flags) and noise traders; golden set from the first partner exports (ten per broker); CTR fidelity, fees, determinism, the leakage suite; **the week-2 data checks** — which brokers' crude exports carry contract/expiry, fills and stop orders, and the tick-history coverage for the contracts partners traded | CTR v1 passing §12.1; corpus A; the conditional tests' go/no-go |
| 3–4 | SBC and M-SIM on M1–M4, M6; null validation on noise traders; **the first concierge reports, by hand, on 3–5 partner histories, training zone only**; **the R-on-options convention written down** (Annex H) before the CTR schema freezes, even though options are out of scope | Models that ship; the first evidence that anything lands; a schema that will not need tearing up |
| 4–5 | The eighteen core tests on corpora A and B; recall-versus-sample curves at θ_min, 2θ_min, 4θ_min; false positives, coverage, MDE calibration; retire or split what fails; Avoidable Loss calibration on twin runs; **the trade-frequency count (§12.5)** and the n_min / n_hold shares (§12.3) | The core library with per-test scorecards; the segmentation evidence; the feasibility count |
| 5–6 | Risk classes with the in-house trader; replays and overlap checks for the six starter rules, including the PL-1/DL-1 merge and the EV-1/SS-1 interaction; RK-2 and RK-3 replays written; operating characteristics of the process endpoint by simulation; the safety-pause thresholds; **read-only broker connectors for the brokers the partners use, started here and finished by week 8** (§7.8) | The starter intervention set; Phase 1 opens connected |
| 6–7 | Expert panel; all concierge reports and interviews (recognition of described facts on the pre-registered sample, comprehension, fairness of Avoidable Loss); **the single isolation read across all partner histories, on the final framework version** | Recognition rates; the Established Findings |

**The isolation rule, corrected.** Draft 1's "read once per trader per framework version" plus a heavyweight version process would have allowed two or three shots at the design in eight weeks — which, as the first review said, is not how research gets done. The rule now: **the engine iterates freely on training zones and on synthetic corpora throughout; real-trader isolation is read exactly once, in week 7, on the final framework version.** Every intermediate iteration is free because it never touches the hold-out. The DOF ledger records that single read.

**Partner data has three different uses, and Draft 2 tangled two of them (clarified in 2.1).**

| Use | Which data | The rule |
|---|---|---|
| **Calibration** | Partner **training zones**, openly and repeatedly, weeks 3–7 | Free. Look as often as you like, change what you like — nothing is being validated. Every look is still a charged run with a pre-registration and a ruler, because the parameters it sets are decision-relevant |
| **Validation** | Partner **isolation zones**, once, week 7, final version | One DOF. Nothing after it changes without a major version |
| **Population validation** | Phase 1's traders, as a population | Phase 1, not Phase 0 |

**So the first framework version will be substantially revised by Phase 0's partner data, and that is the design, not a failure.** It is also why the arbitrary PRE-COMMIT values get exactly one revision window on synthetic and fund corpora *before* partner training data is opened (§1): the synthetic corpus is calibrated by our own assumptions and cannot be the last word, the fund corpus is one strategy on one instrument, and the partner training zones are the first independent evidence we get.

**The first concierge reports happen in week 3, by hand, not in week 6 after the infrastructure is perfect.** That is the first review's best point and it is accepted: if nothing lands on five histories done by hand, no amount of machinery will save it. **But "by hand" means manual execution, never researcher discretion (2.1):** the analyst runs the same pre-registered core protocol, applies the same tier thresholds, fills the same evidence-object template, and records what was skipped and why. Anything else turns week 3 into a loophole — patterns discovered informally, the library quietly reshaped around whatever looked promising, then formalised afterwards as if pre-registered. **Manual execution, automatic rules.**

### 13.3 Week 8 — finalise
Write the calibrated values in; the starter moves partners actually adopted, with the evidence for the choice; the recall-versus-sample curves and the vocabulary hand-off to the Experience Specification; the open questions carried forward; the Research Gate result. Version: **Research Specification v1.1 — calibrated**, the build floor for the Technical Design and the PRD. (This document is v1.0, the pre-data commitment; v1.1 is the same document with Phase 0's measurements written into its CALIBRATE slots and nothing in its PRE-COMMIT layer moved without a logged major version.)

**Every section has an artifact** — code, schema, a pre-registration file, or a written rule in the repo. A section with no artifact is not done.

## 14. Governance

**Seats.** Research lead owns the library, models, priors and corpora — and never rules on a run he produced. The **CEO rules** verdicts on charged runs, major versions and the monthly measurement review — and never runs the analysis he rules on. The **in-house trader** owns intervention mechanisms and risk classes, and gives the cold read on a Finding *before* seeing its result. The **data engineer** owns the CTR, the feature registry and determinism. The **validator** (a second researcher, or the lead for tests he did not write) reads isolation results and records DOF. **Product** owns screen and ritual scorecards, and never touches a tier.

**Commit before measure**, with the fund's one exception: a committed bar may be reinterpreted only by decomposing the failure from evidence and showing the *instrument* is miscalibrated for the mechanism — recorded the same day, with the repair ticketed.

**The DOF ledger** records every decision-relevant look at data that cannot be re-drawn: the week-7 isolation read, every live-experiment verdict, every look at partner results during calibration. A threshold changed after a look is visible there before it is visible anywhere else.

**Pre-registrations live in git.** Never only on a desktop, never only in a chat — the fund has lost records both ways.

**The asset is regenerability, not the Findings — added at freeze, 3 Oct (PRE-COMMIT · derived).** If anything compounds over years it is the record of what was found on whom, what was offered, what was followed, and what happened — and that record is worth nothing if year-one entries were scored under one framework and year-three entries under another, because the population read then compares incomparable things. Three rules follow. **Raw broker exports and the price paths used are retained immutably, hashed, forever**; a Finding is a derived object and may be discarded and rebuilt, the inputs may not. **Every major version re-scores the entire history** — every trader, every zone, every experiment — so that the population dataset exists on exactly one framework version at any time; the previous version's scores are kept beside it, labelled, for the compatibility audit, and never mixed into a pooled read. **A record that cannot be regenerated bit-for-bit from retained inputs is a lineage failure and blocks the gate** (§15 Class D), whatever its content. The cost is compute, which is cheap; the alternative is a dataset that cannot answer the only question it exists for.

**The AI protocol.** Agents may propose research questions, prioritise which library tests to run first, run the pre-registered library, attempt to kill candidates with the pre-registered kill set, and draft narration from evidence objects. They may not add or alter a confirmatory test, change a threshold, prior, null generator or promotion rule, touch isolation, or write to the registry outside the gates. Every agent action is logged with the agent's version.

**Versions — severity by blast radius, not by file type (corrected in 2.1).** A **major** moves on: a test added or removed; a condition, comparison, threshold, null generator or its algorithm changed; a promotion rule or tier threshold changed; a model class changed; the Avoidable Loss method, the process-threshold rule or δ_pool changed. Draft 2 called a prior update a *minor*, which was too permissive — a prior change can move posteriors enough to demote an Established Finding, alter Avoidable Loss, shift the Process Score and re-rank Next Best Move. The rule now follows the fund's own blast-radius law:

> **A prior update, or any change nominally minor, is minor only when a pre-registered compatibility run on the corpora demonstrates zero tier changes and no material change to any trader-facing number. Otherwise it is a major.** The compatibility run is the evidence, not the changer's judgement.

Genuine minors: a copy change, a new feature no confirmatory test uses, a performance refactor with byte-identical output — the dark lane. Majors require pre-registration of the change with its blast radius, a corpora run, the leakage suite, the gold-standard re-run where behaviour tests change, and the CEO's sign-off.

## 15. The Research Gate

**What it is.** The research system is validated enough to enter the product build. Draft 2 called this "proving the engine is correct", which the second review rightly flagged as collapsing four different kinds of evidence into one word — partner confirmation and narration quality are not correctness in any statistical sense. The gate is therefore read in **four classes**, and all four must clear. They map onto the five separations in §1.

**Class A — Correctness.** *Can we compute it?* No users, no judgement, no market.
```
CTR fidelity ≥ 99.5% on the frozen certification set, zero silent drops, fees within 0.5%
AND  determinism: exact hashes on data artifacts; tier assignments identical across platforms (§12.1)
AND  leakage L1 bit-identical on every feature, and L2 detects every injected violation
AND  every feature unit test and metric golden test exact
```

**Class B — Statistical validity.** *Is it actually true?* Read on the **adversarial** noise class, with the clean class reported alongside. (The recall lines were rewritten in v1.0: "medium effect" was undefined, and at the one size our own table gives, the old line was unreachable — §12.3.)
```
SBC passes and M-SIM interval coverage in [72%, 88%] for every shipped model
AND  null generators' false-positive rates inside [2%, 8%]
AND  recall ≥ 80% at ≥ Likely for a planted effect of 2·θ_min, on histories whose condition
     count reaches the 80%-power count for that effect (§5.4a), per core test
AND  below that count, the null is reported with MDE ≥ the planted effect in ≥ 95% of runs
AND  false-Established ≤ 5% and false-Likely ≤ 15% per trader-run
AND  effect-size calibration: interval coverage within ±5 pp of nominal
AND  Avoidable Loss coverage ≥ 95%, median recovery ≥ 0.5 on twin runs at 2·θ_min, powered histories
AND  Process Score test–retest ICC ≥ 0.70 and band coverage ≥ 75%   [internal use only]
```

**Class C — Recognition.** *Does a skilled human, and the trader himself, agree with what was described?* Since §11.1a the engine describes a behaviour and never names its cause, so **confirmation is of the described fact** — *"after a loss your next position is 1.8× your usual size, on 9 of 10 occasions"* — and the trader is never asked to confirm a reason. A dispute marked *"right facts, wrong reading"* is a confirmation of the fact and a demotion of the interpretive layer (T§6.1), not a non-confirmation.
```
≥ 60% of design partners confirm the fact of a non-obvious Established or Likely Finding   [thesis gate]
AND  user-confirmation rate ≥ 80% on the PRE-REGISTERED sample, not on surfaced-only Findings (§12.4)
AND  expert agreement ≥ 70% on the three Findings ranked highest by HOLD-OUT-VALIDATED EFFECT (§11.3)
     on PARTNER histories — agreement that these are his costliest patterns, never on cause —
     reported against inter-rater κ
AND  engine false positives ≤ 5% on the adversarial-noise histories in the panel
```

**Class D — Fidelity and lineage.** *Is what we say traceable to what we computed?*
```
narration: 100% numeric resolution, ≥ 98% entailment, ≥ 99% refusal correctness
AND  every production Finding carries its full lineage, including the price-path resolution used (§4.2)
AND  the kickoff hash matches the shipped framework, or every diff is a logged major version
```

**One feasibility gate, which belongs to none of the four.** `the unconditional core tests reach n_min on ≥ 50% of partner histories` (§12.3), with two columns reported beside it: the share clearing each test's `n_hold` for Established, and — for the two conditional tests — the share of partner exports that carry fills or stop orders at all. It is not a question about the engine but about whether the library fits the market. The 50% is **arbitrary** and is there to force the count rather than to be defended: at 40% the honest response is not to lower the bar but to ask which tests are starving and why — thin histories, exports without fills, or conditions too rare among crude retail traders to be worth a test. That diagnosis is the deliverable, and it changes the library rather than the gate.

**A second feasibility question that precedes the gate: the partners exist.** Crude-only recruitment makes the design-partner pool the binding risk of Phase 0 (§1, Annex H). Twenty crude partners with adequate histories are named as the floor before week 2 commits; below it, the instrument set is widened *for recruitment only*, with crude kept as the validation instrument and the non-crude histories used for correctness and calibration, never for the week-7 isolation read.

**The baseline the engine must be measured against — added at freeze, 3 Oct (PRE-COMMIT · procedure; reported, with one pre-committed consequence).** The founder's question before freezing was the right one: *what does this engine have over a capable language model given the same CSV?* The research layer's answer is four things, and only one is computation — every test was fixed and hashed before any trader's data was seen, where a model's analysis of a CSV is after the fact by construction; the engine's error rates are measured on noise, where a model's are unknown rather than worse; a null is reported with what it could not see, as a gated output; and five of the eighteen tests need the contract's tick history, the fund's regime labels and the release calendar, which are not in his CSV. Those are claims, and claims are measured here:

- **The baseline.** A frontier model with a code interpreter is given each history and asked to find the trader's biggest leak, with the sample, the effect and its confidence. **The prompt is written by the founder** — the person most sceptical of the engine — so the baseline is the strongest one we can give it, not a strawman; it is pre-registered with the rest of Part I and may not change after the first result. It runs on the 600 adversarial noise traders and on the planted synthetic histories at 2θ_min, once, on the same corpora the engine is gated on.
- **What is measured, the same way for both.** The share of noise traders in which a confident "biggest leak" is named (the false-positive rate); recall on the planted behaviours; and the share of stated numbers that resolve against the ground-truth features (the hallucination rate, which for the engine is gated at 100% resolution).
- **The consequence, fixed now.** The comparison is reported in the week-8 scorecard. **If the baseline's false-positive rate on adversarial noise is within five points of the engine's, the diagnosis layer has no validity moat**, and that is a thesis finding for the decision log (T§22 territory), not a footnote. The Phase 0 engine does not pass or fail on it; the product's differentiation claim does.

What the baseline cannot be given, and is not: the price-path layer, the pre-commitment, or a second month of the trader's data. Those are the edge, and a comparison that handed them over would be measuring nothing. A model's breadth — it will notice something outside the eighteen — is real and is used: §14 lets it propose into the candidate register, exploratory and labelled, never a Finding until it survives the gates.

**What the gate does not prove:** that any of it helps. Utility is Phase 2's question, answered by the pooled reads (§7.2). A gate that claimed otherwise would be the category error this document is built to prevent.

**If the gate fails,** the thesis's kill criteria decide (T§22). The most likely failure is not a broken model — it is Class C or the feasibility gate: the engine works and the market does not have the histories to feed it. That is a finding about the market, not about the code, and it is better to own it in week 8 than in Phase 2.

---

# Part III — Annex

Reference material. Nobody reads this end to end; it is looked up.

## Annex A — The eighteen core tests, in protocol form

Every test carries the same fields. B2 is written out in full as the template; the others are given in the compact form, with the omitted fields identical in kind. Three quantities appear per test and are not interchangeable (§5.2): **θ_min** is the practical floor the posterior must clear; **θ_hold** (§4.6) sizes the hold-out from the training estimate and is computed per trader, so it has no column; **MDE** (§5.4a) is reported on every null and is computed per trader, so it has no column either.

### A.1 · B2 — post-loss expectancy (the template)
```yaml
test_id: B2
family: Behaviour
research_question: Does the trader's risk-adjusted result fall on trades entered after consecutive losses?
hypothesis: {parameter: theta, direction: "<", practical_threshold: -0.25}   # derived: delta_pool / reference prevalence (§5.2)
population: round trips with >= 2 same-day prior round trips resolved before entry
condition:  {definition: two most recent resolved trips before entry were losses net of fees,
             features: [prior_losses_today], leakage_class: C2}
comparison: {definition: all other round trips, matching: [instrument, vol_tercile]}
outcome:    {feature: R, leakage_class: C3}                # secondary: currency shortfall, for Avoidable Loss
model: M1                                                  # day-level random intercepts (§6.2)
controls: [instrument, vol_tercile, session_bucket]        # pre-registered; never the condition
null_model: N-B                                            # preserves day/instrument/session/times/sizes; destroys outcome order
family_for_fdr: F-Behaviour
minimum_sample: {n_condition: 30, n_comparison: 60}        # arbitrary; §12.3 measures how often it bites
holdout: standard four-zone (§4.6); P_hold from isolation only
robustness: {standard: [P1..P8], sweeps: [{k_losses: [1,3]}, {window: [same_day, within_60min]}]}
kills: [sign_flip_in_sweep, holdout_reversal, failed_diagnostics]
economic_significance: {min_pct_realised_pnl: 0.02, min_currency: 5000}
mechanism_vocabulary: [B1 faster re-entry, R2 larger size]  # attached only if that test is itself >= Likely
product_language:
  L1: "Trades after two losses were associated with a lower result (X R vs Y R, n = N)."
  L2: "...and this held across instruments, sessions and your last N trades."
implied_moves: [PL-1]                                      # PL-2 merged into PL-1; DL-1 replaces PL-1 if B12 validates (§11.1)
null_reporting: MDE at 80% power, one-sided, shuffle-inflated 1.65x; "no problem found" only if MDE <= 0.25 (§5.4a)
risk_note: process observation; implied moves are pause and size rules, never trades
seed: ["B§11 revenge trader", "Coval & Shumway 2005", "Liu et al. 2010"]
owner: research_lead ; status: pre_registered ; test_version: 1.0.0
```

### A.2 · The other seventeen

θ_min for every conditional R test is **0.25R** (§5.2 — derived from δ_pool at 20% reference prevalence; the 0.10R/0.15R values of Draft 2.1 are withdrawn). Level and ratio tests keep their own units. Sessions, calendars and regime labels are MCX crude's (§9).

| ID | Condition | Comparison | Outcome | Model · null | θ_min | n_min | Sweeps | Moves | Class |
|---|---|---|---|---|---|---|---|---|---|
| **B1** | prior trip was a loss | prior trip won or flat | time to next entry | M3 · N-B | ratio ≤ 0.67 | 30/30 | loss ∈ {any negative, > 0.5R} | PL-1 | unconditional |
| **B5** | nth trade of the day, n ∈ {1,2,3,4,5+} | all trades | R | M6 · N-B | 0.25R | 40 days | bucket edges ±1 | DL-1 | unconditional |
| **B12** | first two resolved trips of the day were losses | days without that start | the day's net R (unit = the day) | M1 · N-S | 0.5R/day (arbitrary) | 20 days / 40 days | "two losses" ∈ {1, 3}; first-N ∈ {2, 3} | DL-1 | unconditional |
| **R1** | — (level test) | stratum reference | CV of risk per trade; share of loss in worst 5% | Fact + bootstrap | CV ≥ 0.6; share ≥ 40% | 50 | percentile ∈ {5, 10} | RK-1 | unconditional |
| **R2** | prior trip was a loss | prior trip won or flat | log(risk / trailing 20-trip median) | M4 · N-B | log 1.25 | 30/30 | loss definition; 1 vs 2 prior | PL-1 (merged) | unconditional |
| **R7** | a stop order was placed on the trip | — | rate at which the stop was moved away from price or cancelled before fill; R on those trips vs trips whose stop held | M2 / M1 · N-B | 15 pp; 0.25R | 30 trips with stops | "moved" tolerance ∈ {1, 2} ticks | RK-1 | **conditional** (stop orders in export) |
| **R8** | fund volatility regime | across regimes | log(leverage); R in the high regime | M4 / M1 · N-S | log 1.25; 0.25R | 30/regime | regime boundaries ±10% | RK-2 | unconditional |
| **R11** | a same-direction fill arrived while the open position was at a loss | trips with no such fill | final R of the trip; MAE after the add | M1 · N-B | 0.25R | 30/60 | "at a loss" ∈ {any, > 0.5R} | RK-3 | **conditional** (fills in export) |
| **E2** | — (level test) | c_ref (CALIBRATE on crude partners; crude population median later) | capture = realised / MFE on winners, **tick resolution** | M1 · N-E | c_ref | 40 winners | winner ∈ {> 0, > 0.2R} | EX-1 *(Phase 1)* | unconditional (tick) |
| **E4′** | loser whose MAE reached his own median losing magnitude L_med | — (level: a trader who leaves at L_med scores 0) | extra loss beyond −L_med, in R, **tick resolution** | M1 · N-E | 0.25R | 30 such losers | L_med ∈ {median, 60th pct} | EX-2 *(Phase 1)* | unconditional (tick) |
| **E5** | winners | losers | holding duration ratio | M3 · N-E | ratio ≤ 0.67 | 40/40 | winner/loser thresholds | EX-1/EX-2 *(Phase 1)* | unconditional |
| **S1** | crude session bucket ∈ {morning 9:00–12:00, afternoon 12:00–17:00, US overlap 17:00–close} | other buckets | R | M6 · N-S | 0.25R | 30/bucket | boundaries ±30 min | SS-1 | unconditional |
| **S5** | fund regime label (volatility × trend, unchanged from the fund's definition) | across labels | R | M6 · N-S | 0.25R | 20/cell | the fund's own ±10% boundary sweep | RK-2 | unconditional |
| **S6** | position held across the MCX session close | intraday trips entered in the same session bucket | R | M1 · N-S | 0.25R | 30/60 | "held across" ∈ {close, next-day open} | OV-1 | unconditional |
| **S10** | holding interval overlaps [T − 15 min, T + 30 min] of a scheduled release (EIA Wed, API Tue, OPEC meeting days) | trips in the same session bucket outside any window | R | M1 · N-S | 0.25R | 30/60 | window ∈ {−15/+30, −30/+60} min | EV-1 | unconditional (public calendar) |
| **S11** | his most recent 100 resolved trips | the 100 before | R | M1 · N-B at window level (permute window labels within 50-trip blocks) | 0.25R | 200 trips | window ∈ {75, 100, 150} | PR-1 | unconditional |
| **S12** | — (level test) | zero | P(E > 0), regime-standardised | M1 | — | 100 | winsorisation on/off | PR-1 | unconditional |
| **C1** | Edge Map cells, broad → narrow | same dimension | R | M6 · N-C | 0.25R | 20/cell | dimension order | — | unconditional |

**On E4′'s construction.** L_med is the trader's own median losing-trade magnitude over the training zone, so the test asks a question about him against his own baseline and needs no stop, recorded or mental. The random-exit null (N-E) along the same path gives the extra-loss distribution a trader with no exit skill would show after reaching −L_med; a trader who reliably leaves near his typical loss scores near zero; a trader who holds and hopes scores the accrual. The implied move EX-2 — leave at your typical loss — is conditional-class because it assumes a fill at that level, which is why it waits for Phase 1 (§11.1).

**On S11's null.** A monotone slope is a fitted point, so S11 is not a trend test. It is a two-window comparison with window labels permuted in 50-trip blocks, which holds the serial structure and breaks only the association between *recency* and outcome. Reported as a described fact — *"your last 100 trades ran 0.3R below the 100 before"* — and a PR-1 protective move, never as a forecast.

## Annex B — The candidate register

Not built in Phase 0. One line each; they enter through §13.3 when the core has proved the machinery. Ordered by expected value, and the first two are the likeliest promotions. **Promoted to the core on 3 Oct:** R7, S11 (from this register), with S6, S10 and R11 added directly; **retired:** B6, as the same question as B12.

**Strategy** — S8 profit concentration (share of net P&L from the top 5% of trades) · S9 expiry-day expectancy (crude's monthly expiry) · S3 instrument expectancy (dormant until the product widens past crude) · S4 long vs short · S6b holding-band expectancy beyond the overnight split · S7 entry-type (breakout vs pullback) · S2 day-of-week.
**Risk** — R9 tail-loss contribution · R4 drawdown response · R5 intraday risk escalation · R3 post-win size change · R6 correlated exposure (dormant until multi-instrument) · R10 risk after equity change.
**Execution** — E1 entry slippage · E3 premature exit against target · E8 re-entry after a stop-out in the same direction · E6 scaling out of winners (the scaling-in half is now R11) · E7 order-type effect · E9 exit-reason mix.
**Behaviour** — B3 post-loss frequency · B4 post-win expectancy · B7 drawdown-state expectancy · B9 streak chasing · B10 recovery trading in the last hour · B11 instrument switching after a loss (dormant until multi-instrument) · B8 session fatigue.
**Open to the field.** A behaviour the in-house trader or the founder has watched crude retail traders do and does not see above enters here as a one-line question with its seed; the register is the hypothesis inbox's Phase 0 substitute (§10).

## Annex C — Evidence object fields

| Field | Computed as |
|---|---|
| `claim` | The test's L1 template filled with the **pooled** posterior median, interval and n (§5.2 — display only) |
| `claim_level` | L1 at Likely/Established · L2 if ρ ≥ 0.80 · L3 only with a mechanism from the test's vocabulary · L4 only after PASS |
| `confidence_tier` | §5.2, from **promotion** evidence only |
| `promotion_evidence` | {P_train, m_train, P_hold, ρ, q, n, ε, s} — the record that decided the tier (§5.2: P_train is *is it real*, m_train against θ_min is *is it big enough*) |
| `effect` | {pooled median, 80% and 90% intervals (widened to the bootstrap if narrower, §6.2), P beyond θ_min, direction} |
| `evidence.trade_ids` / `slices` | The condition trips (primary membership) and the comparison cell; the perturbation folds with their estimates |
| `sample_size` | {n_condition, n_comparison, n_holdout} |
| `holdout_result` | P_hold, sign agreement, isolation n — from the isolation-only fit |
| `robustness` | ρ, pass/fail list, sweep shape ∈ {monotone, flat, flip}, `suspiciously_stable` flag |
| `null_model` | Generator, permutations, p_perm, the generator's validated FP rate at this version |
| `mde_at_sample` · `power_at_theta_min` (v1.0) | The minimum detectable effect at 80% power, one-sided, shuffle-inflated, from the realised condition and comparison counts and the trader's σ_R; and the power the test had at θ_min. Both stored on every null; the first drives the null's wording (§5.4a) |
| `theta_hold` · `n_hold` (v1.0) | The effect the hold-out was sized to replicate — max(θ_min, training posterior 20th percentile) — and the condition count that required (§4.6) |
| `price_path_resolution` (v1.0) | Tick / 1-second / bar interval used for MFE, MAE and capture, and the contract identity the path was taken from (§4.2); part of the Finding's version identity |
| `multiplicity` | Family, family size, BH q |
| `dependence` | Model interval width, bootstrap interval width, the ratio, which was reported |
| `economic_impact` | Currency, % of realised P&L, avoidable share (Annex F), R if a stop exists |
| `limitations` | Auto-generated: inferred risk unit · coarsened comparison cell · market gaps · weak prior (Phase 0–1) · L3 fragility flag |
| `recommended_actions` | Prescription ids, ranked and filtered by the risk screen |
| `dispute_state` · `lineage_hash` | T§6.1 · SHA-256 over every version stamp and input hash |

## Annex D — Deferred models
M5 negative-binomial counts (trades per hour under a state) · M7 experiment effect with window and regime covariates · M8 persistence · M9 empirical-Bayes population priors. Built with the tests that need them; M7 and M8 arrive with the quarterly and pooled reads (§7.2).

## Annex E — Process Score: structure fixed, calibration deferred
Findings map to one sub-score by family. Contribution c = w_tier · sign · min(1, |θ̂| / θ_ref) · min(1, n / n_ref), with w_tier = {Established 1.0, Likely 0.5, Exploratory 0} and θ_ref, n_ref **arbitrary and deferred**. Sub-score = shrunken sum, mapped to 0–100 against the reference population, 50 = median. Headline = weighted mean; v1 weights equal. **The band is propagated from the contributing posteriors, not asserted; no band, no score; a band wider than 25 points is "not enough evidence yet"; a sub-score with no Findings is unscored, never zero.** Weights are set on cohort A and validated on cohort B — never the same traders or periods, which is the circularity the second review caught. **Synthetic traders never define the reference.** Until the real population is large enough, the score is *provisional, non-comparable*.

**One open question the structure does not yet answer (raised in 2.1):** what makes a Trader Model complete enough for its headline score to be *comparable* between two traders? A trader with four scored sub-scores and one with two are not on the same footing, and treating an unscored sub-score as absent — correct — does not make the two headlines comparable. Two candidate rules, to be settled in Phase 1 calibration and not before: a minimum number of scored sub-scores for a comparable headline, or a completeness weight carried on the Card beside the band. Until then the headline is shown with its sub-scores and its band, and never as a rank against other traders.

## Annex F — Avoidable Loss: method fixed, parameters deferred

Attribution is hierarchical and mutually exclusive: each trade is assigned to at most one primary leak — the Established condition with the largest validated effect for this trader, ties to the larger sample. Per-trade, **losing trades only**:

```
A_i = 1[r_i < 0] · min( |r_i| , max( 0 , E_cf,i − r_i ) )
```

where E_cf,i is the posterior expectation in the matched comparison cell (instrument × volatility tercile, n ≥ 20, coarsened with the coarsening recorded), converted to currency by the trade's own risk unit. The inner term is the shortfall; the outer cap says a trade cannot have avoided more than it lost. A winner inside a leak contributes zero. Secondary memberships are reported qualitatively and never summed. Profit given up is a separate secondary figure, never added.

**The bound.** A_i is computed on every posterior draw; the trader sees the **5th percentile**, as "at least ₹X", with the median and 95th in the drawer. A thin history widens the distribution and lowers the claim — uncertainty shrinks the number, not the confidence language.

**Minimums (arbitrary, deferred):** ≥ 30 trades in primary leak conditions, ≥ 100 in comparison cells, ≥ 1 Established leak, and the bound above max(2% of realised loss, ₹5,000).

**Validation, with the noise requirement corrected.** On twin runs: coverage — the 5th percentile ≤ the true planted cost in ≥ 95% of runs (a violation is a blocking bug); recovery — median ratio to truth ≥ 0.5 at a planted effect of 2θ_min on histories whose condition count reaches the 80%-power count for that effect (§12.3; "medium effect, n = 300" was undefined and is withdrawn). On noise traders: Draft 1 said "must return zero", which is not a statistical requirement. The requirement is **a pre-registered false-attribution tolerance** — Avoidable Loss appears in ≤ 5% of noise runs (it needs an Established leak, and that rate is bounded at 5%), and where it appears the bound is ≤ 2% of realised loss in ≥ 95% of those runs.

## Annex G — References

[Bailey & López de Prado 2014, *The Deflated Sharpe Ratio*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551) · [Harvey, Liu & Zhu 2016, *…and the Cross-Section of Expected Returns*](https://academic.oup.com/rfs/article/29/1/5/1843824) · [Arnott, Harvey & Markowitz 2019, *A Backtesting Protocol in the Era of Machine Learning*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3275654) · Benjamini & Hochberg 1995, doi:10.1111/j.2517-6161.1995.tb02031.x · [Gelman, Hill & Yajima 2012](https://arxiv.org/abs/0907.2478) · [Kruschke 2018, *ROPE*](https://journals.sagepub.com/doi/10.1177/2515245918771304) · [Lakens, Scheel & Isager 2018, *Equivalence Testing*](https://journals.sagepub.com/doi/full/10.1177/2515245918770963) · [Talts et al. 2018, *Simulation-Based Calibration*](https://arxiv.org/abs/1804.06788) · [Politis & Romano 1994, *The Stationary Bootstrap*](https://doi.org/10.1080/01621459.1994.10476870) · Romano & Wolf 2005, doi:10.1111/j.1468-0262.2005.00615.x · White 2000, doi:10.1111/1468-0262.00152 · [Lipsitch, Tchetgen Tchetgen & Cohen 2010, *Negative Controls*](https://pubmed.ncbi.nlm.nih.gov/20335814/) · [Johari, Pekelis & Walsh 2022, *Always Valid Inference*](https://pubsonline.informs.org/doi/10.1287/opre.2021.2135) · [Brodersen et al. 2015, *CausalImpact*](https://projecteuclid.org/journals/annals-of-applied-statistics/volume-9/issue-1/Inferring-causal-impact-using-Bayesian-structural-time-series-models/10.1214/14-AOAS788.full) · [Kravitz & Duan 2014, *N-of-1 Trials: A User's Guide*](https://effectivehealthcare.ahrq.gov/products/n-1-trials/research-2014-5) · [Hernán & Robins 2016, *Target Trial Emulation*](https://academic.oup.com/aje/article-abstract/183/8/758/1739860) · [Nosek et al. 2018, *The Preregistration Revolution*](https://www.pnas.org/doi/10.1073/pnas.1708274114) · Wicherts et al. 2016, doi:10.3389/fpsyg.2016.01832 · [Manheim & Garrabrant 2018, *Goodhart's Law*](https://arxiv.org/abs/1803.04585) · [Odean 1998](https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00072) · [Coval & Shumway 2005](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2005.00723.x) · [Liu, Tsai, Wang & Zhu 2010](https://pubsonline.informs.org/doi/10.1287/mnsc.1090.1131) · Barber & Odean 2000, doi:10.1111/0022-1082.00226 · [Seru, Shumway & Stoffman 2010, *Learning by Trading*](https://academic.oup.com/rfs/article-abstract/23/2/705/1604374) · [Chague, De-Losso & Giovannetti 2020, *Day Trading for a Living?*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101).

## Annex H — Open questions carried forward

| Question | Why it matters | How it is settled | Owner · when |
|---|---|---|---|
| What share of partners clear each core test's `n_hold`, and its n_min? | How often Established is attainable at all — now a distribution to know rather than a dependency (§4.6, §12.3) | Count it in week 5 | Research · wk 5 |
| Does the CEO accept the §7.6 amendment? | Whether the loop can close in Phase 2 at all | Decision-log row | CEO · wk 1 |
| Are the nulls inside [2%, 8%] on noise? | Invented or hidden Findings | §5.4 validation | Research · wk 4 |
| Do the model intervals hold up against the bootstrap? | Overconfident uncertainty (§6.2) | The dependence audit | Research · wk 4 |
| ~~Can exit replays be bounded honestly at bar resolution?~~ **Answered 3 Oct by the data decision:** at bar resolution they cannot — the bias is 0.33/√(hold ÷ bar) and differs by holding time (§4.2) — so exit replays run at tick resolution or not at all. What remains open is the **fill assumption** for EX-1/EX-2 | Whether the conditional-class moves can be offered in Phase 1 | Slippage distribution at the stop level from the fund's crude tick history, applied as a haircut to every exit replay | Research · Phase 1 |
| Which broker exports carry contract/expiry, fills and stop orders? | Contract identity is a correctness requirement (§4.2); fills and stop orders decide whether R7 and R11 run at all | Ten exports per broker, counted field by field | Data · wk 2 |
| ~~Does market-context enrichment lift Findings enough to license data?~~ **Moot for crude** — the price series is held. The question returns, reshaped, when the product widens: **what is the per-instrument-family data cost** (tick history, calendar, regime definition) and does the lift justify it, measured as before on validated Findings at constant budget | A real cost line, per instrument family | Library with and without, 50 histories, same controls as Draft 2.1 specified | Research · Phase 1 |
| **Does the engine beat a strong, founder-written LLM baseline on the adversarial noise corpus?** | The diagnosis layer's validity moat, measured rather than argued (§15). Within five points on false positives and the differentiation claim goes to the thesis decision log | The pre-registered baseline run once on corpora A and the noise classes; reported in the week-8 scorecard | Research + founder · wk 5 |
| **What share of paying subscribers connect a broker by the end of their first month?** | Connection is the subscription's data path (§7.8, corrected); the share that does not connect is the share whose months carry the supply bias. No value is assumed | Counted in Phase 1 month one against the labelled-arbitrary 70% bar; below it, connection friction is the Experience Specification's first problem | Product · Phase 1 month 1 |
| What share of partners trade ≥ 5 times a week? | Whether the improvement loop serves the thesis's target band at all (§12.5) | Count it; report the three bands and the eligible-occasion rates | Product · wk 5 |
| What is the real between-trader spread in a move type's effect? | The pooled read's sample size is currently a planning figure, not a result (§7.4) | A power simulation on Phase 1 adoption data, before any pooled verdict is issued | Research · Phase 1 |
| What makes a Process Score comparable between two traders? | Annex E's open question | Phase 1 calibration | Research · Phase 1 |
| What δ_min do traders actually feel? | φ is arbitrary | Phase 0 interviews on the framing | Research + Product · wk 6 |
| How many traders per move type for the pooled read? | The Phase 2 plan (§7.1 says 10–63) | Measured as Phase 1 fills | Research · Phase 1 |
| When does the real reference population exist? | Process Score honesty | Count per stratum monthly | Research · Phase 1–2 |
| Can 20–50 design partners who trade MCX crude, with adequate histories, actually be recruited? | **The binding feasibility risk of the crude-first decision.** The partner corpus is the only one that can fail the product (§12.2); if it cannot be assembled, Phase 0 has a test-bed and no truth | Recruit against a named count before week 2 commits; if short, the gap state is widening the instrument set for *recruitment only* while keeping crude as the validation instrument | Product · wk 1–2 |
| What is an R-multiple on an option? | **Definitional, not calibrational, and it lands the moment the product widens past crude.** On a future, R is risk taken and MFE/MAE are clean. On a long option the premium path is not the underlying's path, so MFE is a different object; on a short option risk is unbounded, so R is convention-dependent or undefined. Most of what Indian retail trades is index options, so a CTR schema and an R convention built only for futures will have to be torn up rather than extended | Settle the convention **before** the schema freezes, even though options are out of Phase 0 scope — writing it down costs a week now and a rebuild later | Research + Data · wk 3 |

## Annex I — What changed from Draft 1, then from Draft 2

**Accepted from the first review** (over-engineering): the core library cut from 43 tests to 12 with a candidate register · models from 9 to 5 · moves from 15 to 4 · the Process Score deferred to Phase 1 with only its structure fixed · the synthetic grid cut from ~5,000 histories to ~600 plus noise · corpora reduced from five things with equal billing to three ranked by authority · concierge reports moved to week 3, by hand, before the machinery is finished · the isolation rule made workable so the design can iterate · the "not yet measurable" state promoted from footnote to the centre of §7 · provenance labels so an arbitrary number cannot hide inside a committed table · length cut by roughly a third, and split into three parts with different readers.

**Accepted from the second review** (methodology): the hold-out separation — promotion evidence and the displayed magnitude are now different quantities, and the pooled posterior can never decide a tier (§5.2) · null models rewritten as invariants, with the context null's stratification fixed and null validation promoted from an open question to a gate (§5.4) · the leakage test replaced with reproducibility-from-history plus a positive control on the detector (§4.4) · the four-zone arithmetic corrected, which raised the Established minimum from a wrong 90 to a correct 120 (§4.6) · serial dependence handled by day-level intercepts and the block bootstrap as interval authority (§6.2) · SBC's authority bounded, with a misspecification suite added (§6.4) · REFUTED split into directional and practical reason codes (§7.4) · "user-confirmed accuracy" renamed to user-confirmation rate (§12.4) · synthetic traders barred from the Process Score reference (§10) · the fund corpus barred from behavioural priors, with the Phase 0–1 cost stated (§6.3).

**Rejected, with reasons.** The first review's advice to reclassify committed thresholds as strawmen and leave them uncommitted: an arbitrary threshold is exactly the kind that must be fixed before looking, because setting it afterwards is fitting. The fix is to label its provenance and allow one revision window on data containing no real traders — not to loosen the commitment. The first review's advice to move the machinery into a second document: a specification that lives in two files where one is never written is worse than a long one with an annex, so the annex stays in the same file behind a clear boundary.

**Found by neither review, and the reason for the rebuild.** The experiment engine could not measure its own target. δ_floor = 0.05R with N capped at 150 needs 9,695 trades per window at typical retail dispersion. Every experiment would have returned "not yet measurable," and the loop — the thesis's whole differentiation — would have silently failed in Phase 2 after being built. The resolution is in §7: the trader-level endpoint becomes the process metric plus deterministic avoided-cost accounting; ΔE moves to the quarterly per-trader read and the pooled per-move-type read, where 10–63 traders suffice. **Efficacy is a population question; adherence is an individual question.** That conflicts with the frozen thesis and goes to the CEO as §7.6, rather than being quietly redefined here.

### What changed from Draft 2 → Draft 2.1

**The conflict closed.** Thesis v1.4 (1 October) decides the trader-level verdict on process and avoided cost, with Trader Improvement read at the quarterly and pooled-per-move-type levels. §7.6 was a question; §7.7 is now an inherited rule. Two consequences this document carries: the Phase 2 gate needs two target numbers, and the Experience Specification's wording is gated on research sign-off.

**My own bug, caught by the second review.** Draft 2's δ_min had N in its denominator while N was derived from δ_min — circular, and divergent when iterated. Their patch removed the circularity without removing the problem. The fix in §7.4 is to scope the threshold to the level where it means something: a behavioural process threshold at trader level with nothing statistical in it, an economic δ_pool for the library bar sized in traders, and **no pre-set bar at all** on the per-trader quarterly read, where the interval is simply reported — because a bar we can clear would have been chosen from the power, which is the sin the document exists to prevent.

**Accepted from the second review, beyond that:** verdicts split into implementation and efficacy dimensions, so `NO_PRACTICAL_EFFECT` stops sharing a word with `REFUTED` (§7.5) · the null generators given written algorithms, with N-S's construction corrected — resampling inside a session cannot break a session effect (§5.4) · shrinkage no longer described as multiplicity control (§5.5) · a second, adversarial class of noise trader, since an i.i.d. null is too easy to be a negative control, and the gates now read on it (§12.2) · the synthetic grid's arithmetic spelled out, 54 cells × 12 seeds (§12.2) · the golden set split into development fixtures and a frozen certification set (§4.2, §12.1) · the robustness denominator closed with mandatory and conditional perturbations and a minimum applicability rule (§5.3) · `suspiciously_stable` confirmed as a review flag with a written protocol, never a kill (§5.3) · the recognition sample pre-registered and drawn independently of reveal ranking, closing a feedback loop (§12.4) · the expert panel's three validity questions separated, with the generator rather than the panel holding ground truth on synthetic histories (§12.4) · determinism split between data artifacts and posterior computation (§12.1) · version severity decided by a compatibility run rather than by file type, so a prior update is not automatically minor (§14) · the pooled sample marked a planning figure pending a Phase 1 power simulation (§7.4) · enrichment lift measured on validated Findings at constant budget (Annex H) · the Research Gate reframed into four classes plus a feasibility gate, since partner confirmation and narration quality were never "correctness" (§15) · and Annex E's comparability question raised rather than left implicit.

**Accepted from the first review:** the low-frequency path promoted from a named state to a week-5 measurement with three identified options and a rule against choosing before the count exists (§12.5) · partner data's three uses untangled — training zones calibrate openly, isolation validates once, Phase 1 validates as a population — with the plain admission that the first framework version will be substantially revised by Phase 0 (§13.2) · the week-3 hand reports disciplined to manual execution with automatic rules, closing the loophole where patterns get discovered informally and formalised afterwards · the fund corpus's intervention-outcome rows given their single purpose, a weakly-informative algorithmic prior on move-type effectiveness for the Phase 2 pooled read (§12.2) · the candidate register named as the hypothesis inbox's Phase 0 substitute (§10).

**From the thesis amendment (T§10, v1.4):** the starter set is offered whole with overlap rather than count as the constraint, and PL-1 and PL-2 merged into one rule because they act on the same trades · replay demoted to illustration, barred from ranking, and stated as a ceiling rather than an expectation · "impact" defined as the hold-out-validated effect · the conditional forward figure given its permitted form, with the shrunk estimate, the visible conditional, and the stay-out-not-trade-more rule (§7.6, §11).

### What changed from Draft 2.1 → v1.0 (3 October 2026)

The CEO asked for every open conflict to be decided and the document rewritten to match. Each decision below is mine, with its reason; the CEO freezes by uploading. Where a decision could reasonably have gone another way, the alternative is named so that a reviewer can disagree with the reasoning rather than guess at it.

**The core library (Concept 6).** *Decided:* θ_min for conditional R tests is anchored to the library bar — 0.25R, the condition effect whose whole-history drag at 20% prevalence equals δ_pool — instead of the inherited 0.10R/0.15R. *Alternative rejected:* raising θ_min to 0.5R so that confident nulls become reachable; that would have made Established unattainable for a genuine 0.5R leak under the old criterion. The two jobs were separated instead (§5.2). *Found while checking the numbers for this version, and decided:* Draft 2.1's promotion criterion — 95% of the posterior beyond θ_min — had only 53% power on a real 0.5R leak at 60 condition trades, and anchoring θ_min at 0.25R would have cut that to 34%; it is replaced by the two-part ROPE form, *real* (P beyond 0 ≥ 0.95) and *big enough* (shrunk median beyond θ_min), which passes the same leak 80% of the time and a noise trader 5%. The tier values stay arbitrary-and-revisable-once; the structure is what changed. *Decided:* the hold-out is sized at θ_hold = max(θ_min, the training posterior's 20th percentile), because sizing it at θ_min silently made Established impossible for large effects on any test with a small θ_min — the opposite of what §4.6 promised. *Decided:* E4 → E4′, because the recorded stop is intent (§11.1a). *Decided:* R7 and S11 promoted, S6/S10/R11 added, B6 retired; the three additions are crude-market judgement rather than measurement, and the feasibility count (§15) is what tests them. *Alternative rejected:* splitting the library into trader-level and pooled-only tests; with θ_min and θ_hold separated there is no test that cannot produce a trader-level Finding on a large effect, so one library with one set of rules is both simpler and correct.

**The data scope (Concept 6, continued).** *Decided:* crude first, end to end, then widen — the CEO's own sequencing. *Carried:* MFE resolution as part of a test's identity (the 0.33/√(hold ÷ bar) bias, differential by holding time), contract identity as a correctness requirement, the fund's regime definition unchanged, partner recruitment as the binding feasibility risk with a recruitment-only widening as the escape, and the R-on-options convention written in week 3 before the schema freezes.

**The null (Concepts 3 and 6 together).** *Decided:* every null reports its MDE; "no problem found" only when MDE ≤ θ_min; otherwise the trader is told what size of leak was ruled out and what was not. *Why:* with θ_min at 0.25R the 2 Oct binary rule would have put nearly every null into the gap state, which is honest and useless; the MDE statement is honest and informative, and it is §7.5's describe-not-judge principle applied to a null.

**The starter moves (Concept 7).** *Decided:* five move types from six rules — PL-1/DL-1 as alternates with a pre-registered merge (B12 validated → DL-1 replaces PL-1), RK-1, SS-1, EV-1, OV-1 — all deletion or cap rules, all always-permitted. *Decided:* the adherence auto-stop is removed, because there is no adherence verdict to stop on (§7.5), and a non-adherent trader is as-offered data; the drawdown stop stays as a safety pause stated as a fact. *Decided:* exit moves become Phase 1 candidates rather than "out of scope", since tick data answers the replay question, but they stay out of the first eight weeks because they assume a fill. *Decided:* every core test gets a planted synthetic behaviour — seventeen, from three mechanisms — because recall on a test with no planted truth is unmeasured, and an unmeasured recall behind a gate is a hole in the gate.

**The Research Gate (Concept 8).** *Decided:* "medium effect" removed; recall is gated at 2θ_min on histories that reach the 80%-power count, and an honesty gate is added beneath it — below that count the null must carry an MDE at or above the planted effect in 95% of runs. *Why:* the old line asked for 80% recall at n = 300 where our own table shows 57% at 0.5R; a gate must test the engine's calibration, not whether physics permits the result. *Decided:* Class C confirmation is of the described fact, with "right facts, wrong reading" counted as confirmation of the fact; "top three" is defined as ranked by hold-out-validated effect and agreement is on cost, never cause; the feasibility gate reads on n_min with the n_hold share and the fills-availability share as two further columns; "missing stop data" is replaced by "exports without fills" as a starvation cause.

**Recurring data (the question the CEO caught).** *Conceded:* "few will re-upload" was an assumption with nothing behind it, and it conflated subscribing with supplying data. *Decided:* no value is assumed for the monthly supply rate among paying subscribers; it is an Annex H unknown measured in Phase 1 month one. *Decided:* connections stay in Phase 2 with a pre-committed trigger at 70% complete-month supply — the number is labelled arbitrary — and the selection-bias argument for connections is recorded as a validity argument that holds at any rate, which is the part that was never an assumption.

**Concepts 9 and 10, read against the above.** Low-frequency traders (§12.5) stay as a week-5 measurement with the decision deferred; nothing decided here changes that, and if the count comes back badly it is a thesis question about target market. The eight weeks (§13) absorb the new items — the recruitment count, the week-2 field checks, the options convention, the recall curves, the six-rule replay work — without the gate moving. Week 8's output is renamed **v1.1 — calibrated**, since this document is already v1.0.

**Corrected at freeze (3 Oct, late) — the recurring-data decision.** Not an addition: a reversal. The 3 Oct decision kept broker connections in Phase 2 with a trigger on the manual supply rate. A fourth review said connections must be the Phase 1 default, and the reason it is accepted is not the review's timeline argument but an inconsistency inside §7.8 itself: the section argues that manual supply is biased at *every* rate, then relies on a rate to decide when to fix it. The cost that drove the original decision was also overstated for a crude-first launch on a handful of brokers with read-only APIs. **Preserved for the record — the reversed decision:** *connections stay in Phase 2; if fewer than 70% of paying subscribers supply a complete month in month one, connections move to the front of the queue.* The CEO may restore it on cost grounds by replacing one paragraph; the research layer's position is that the measurement architecture does not work on a biased supply and the trigger did not protect against the bias. The same review's other items — a model adapter, registry-first build order, the LLM never computing a number — are Technical Design rules whose research-layer half already exists (§14, §15 Class D), and the intervention record's start is clarified in §7.8 and §10: the rows begin with the first adoption, the read waits for Phase 2.

**Added at freeze (3 Oct, late) — regenerability.** A third review made the harder case: a persistent agent with tools, memory and a broker connection can run this protocol, pre-commitment included, so methodology protects correctness and not uniqueness. Accepted. The research layer's answer is not to make the engine uncopyable but to make the one compounding asset — the intervention–adherence–outcome record — usable across years, which it is only if it stays on one framework version. §14 now carries the regenerability rule. The review names a frontier lab as the threat; the likelier copier is a broker, which holds the recurring data by default, and that is recorded as a thesis touch (J12) rather than argued here. **This was the last addition before freeze; one correction followed it** (above), which is a different category — a decision found inconsistent by review, the case the status line names. From here, further reviews are read, and their consequences are written to a post-freeze notes file, not to this document, until Phase 0 produces evidence that requires a major version.

**Added at freeze (3 Oct, evening) — the LLM baseline.** Two reviews of v1.0 argued the moat lives in the loop and the datasets rather than in the analysis; both are right about Phase 2 and both leave the doormat's first year unexamined, which is where the product must survive on its own. The founder asked the direct question — what do we have over a capable model given the same CSV — and the research layer's answer is four things, measured rather than asserted: pre-commitment, published error rates, the gated null, and data not in his file. §15 now carries a pre-registered baseline, with the prompt written by the founder so it is the strongest case for the model, run on the corpora the engine is already gated on, with one pre-committed consequence. One correction to the reviews is recorded here because it matters: a model with a code interpreter *can* run a hold-out or a permutation test; the edge is that it will not unless told, will not do it the same way twice, and has no measured error rate — pre-commitment and calibration, not computation. Nothing in the PRE-COMMIT layer moved; one measurement was added.

### Decisions taken in the walkthrough, 1–3 October 2026

Concepts were worked through one at a time with the CEO; each closed decision is recorded here and in T§23.1 where it touches the thesis (Annex J).

| # | Concept | Decision |
|---|---|---|
| 1 | **The confidence tiers** | Likely is the doormat's normal headline tier; Established is what a large leak on an adequate history earns. The arc never changes — only the words and the confidence badge. **And the zone requirement moves from a blanket 120 trades to a per-test rule in condition trades (§4.6)**, because the 120 and the 0.80 hold-out bar were set independently and did not meet: at 120 trades a 0.5R effect reaches only P_hold = 0.78. Lowering the hold-out bar to raise the qualifying share was considered and rejected — that is selecting the threshold from the outcome |
| 2 | **The fund corpus and its wall** | The boundary stands **as written**: the corpus stays inside the fund's environment, only pattern types, calibration curves and aggregate parameters leave, nothing from a trader ever enters, and the corpus never produces behavioural priors or enters the Process Score reference. Signed on that sentence specifically, because the research lead will push on it in week 3 |
| 3 | **The shuffle test** | Three things settled. **(a) The confident-null rule (§5.4a):** a null may be reported as "no problem found" only when the test had ≥ 80% power at its own θ_min; otherwise it is "Not enough evidence yet" with the trades needed. Draft 2.1 triggered the gap state only when a test could not *run*, which would have told 43% of traders with a real 0.5R leak at 300 trades that they were clean. Every null now stores `power_at_sample`. **(b)** A shuffle pass establishes that a gap is not chance and says nothing about cause — three mechanisms pass identically, and only one makes a behavioural prescription right. **(c)** The within-day shuffle half-misses damage that spreads across a whole day (61% → 35% detection); a day-level *null* was tested as the fix and has essentially zero power, so the remedy is a day-level *test* instead |
| 3b | **Cause, and whether we may name it** | **Withdrawn and replaced the same day.** The first ruling claimed that behavioural *consistency* separates "followed his plan" from "lost control"; the founder's challenge — *we only have trade-level data, so how would we know his system?* — exposed the simulation behind it as circular, and the claim fails on a consistent gambler and an erratic-by-design discretionary trader. **The rule now: trade-level data cannot contain intent, so the engine describes and never diagnoses.** Magnitude and consistency are reported as facts; neither selects a cause. Forbidden language extends to "your plan", "your system" and "your rule" alongside "revenge" and "tilt". Asking the trader one question was **considered and rejected** — it would buy only wording, at the cost of friction in a show built on the machine working harder than the user. Intent enters only when he volunteers it through the dispute path ("right facts, wrong reading"), never solicited and never inferred (§11.1a) |
| 3c | **The day-level test** | Added as **B12** — *do days that open with two losses end worse?* — taking the core from twelve to thirteen. The within-day shuffle preserves each day's total, so day-wide damage drops from 61% to 35% detection; a day-level *null* was tested as the fix and rejected (0.8% power on everything, because it preserves the link under test). The unit of the test changes instead (§11.1b) |
| 4 | **The library bar (δ_pool)** | Set at **0.05R** — about ₹10,000 a month, or 24% a year, for a trader risking ₹5,000 over 40 trades a month: the smallest improvement no trader would ignore. The sizing logic was also corrected: the study tests whether the pooled lower bound clears the bar, so the sample depends on the **gap** between a move's effect and the bar, not on the bar's height — which makes a low bar *cheaper*, not dearer. Draft 2.1's working 0.10R was rejected for needing 176 adopters to certify a move worth ₹30,000 a month. **A move that fails to certify is parked with its evidence and re-tested as adopters accumulate** — the bar decides what we recommend, never what we remember |
| 5 | **What the trader is told** | **No trader-level verdict.** He is given counts and an accounting — *"12 occasions, you traded 1, previously you'd have traded 11, worth at least ₹18,000"* — and no pass or fail. The 80% follow-rate gate is dropped: its defect was not its height but that we cannot resolve which side of it he is on (a true 75% measures above 80% between 21% and 34% of the time). Same principle as §11.1a, applied to adherence. **Adherence is not discarded — it enters the pooled read as a weight, not a gate**, and two estimates are reported per move type: the **as-offered** effect (all adopters, the number the business plans on, and the one δ_pool judges) and the **as-followed** effect (adherence as a covariate, read at full compliance, the number that says whether the rule is sound). A large gap between them is a design problem for the Experience Specification, not an evidence problem. **Creates one small thesis touch:** T§11.2 says a trader-level verdict "is decided on" process and avoided cost; there is now no such verdict, so the wording becomes "reported rather than verdicted" (§7.5) |
| 6 | **The price-data scope** | **Crude first, end to end, then widen.** Phase 0 and the first product test run on one instrument — MCX crude — and the product extends to the rest of what Indian retail trades only after the machinery has been proved on it. This resolves the four tests that the selection rule said should not depend on licensable market data: with the instrument's own price series, **E2** (exit capture), **R8** and **S5** (regime) are buildable, and the regime definition is taken unchanged from the fund's existing one so that it cannot have been tuned to produce trader findings — a market-data convention, not a behavioural prior, so the §12.2 wall holds. Three consequences are carried, not waved: **(a)** MFE resolution is part of a test's version identity, because bar-sampled MFE overstates capture by roughly 0.33/√(hold ÷ bar) and therefore overstates it *differently* for a scalper than for a swing trader — 1-minute bars suffice only for holds beyond ~45 minutes, so E2 requires tick or 1-second data; **(b)** the contract/expiry identifier becomes a CTR correctness requirement (§4.2), since crude rolls monthly and MFE must be computed against the contract actually traded, never a stitched series; **(c)** crude-only recruitment makes the design-partner pool the binding feasibility risk of Phase 0, since the partner corpus is the only one that can fail the product (§12.2). **The transfer is of machinery, not calibration** — prevalences, effect sizes and c_ref established on crude traders are crude-specific and are re-established per instrument family, which is a gate and not an assumption (Annex H) |
| 6a | **The library's thresholds** | **One library, three named quantities.** θ_min for conditional R tests is **0.25R**, derived from δ_pool at 20% reference prevalence rather than inherited from literature habit; θ_hold sizes the hold-out from the training posterior's conservative quantile, not from θ_min, so a large leak on a moderate history can reach Established; the MDE is reported on every null; and the promotion criterion is two-part — real, and big enough — rather than 95% of the posterior beyond θ_min, which had been quietly starving Established of power (§5.2). The walkthrough's proposal to split the library into trader-level and pooled-only tests was **withdrawn** once the three quantities were separated — nothing in the core is unable to produce a trader-level Finding on a large effect (§4.6, §5.2, §5.4a) |
| 6b | **E4 → E4′** | The loss-extension test is rewritten to need only the price path: *on losers that reached his own typical loss, how much more did he lose after that point?* The recorded stop is intent, which trade data cannot contain (§11.1a); a mental stop exists in no export. Same move (EX-2), now a Phase 1 candidate rather than out of scope, because tick-resolution crude data makes its replay boundable (§9, Annex A) |
| 6c | **The core becomes eighteen** | R7 (stop discipline) and S11 (edge persistence) promoted from the register; S6 (overnight carry), S10 (scheduled-event trading) and R11 (adding to losers) added for crude; B6 retired as covered by B12. R7 and R11 are **conditional** on fills or stop orders in the export. The three crude additions are market-structure judgement; the feasibility count (§15) is what tests them, and the register stays open to the founder's and the in-house trader's field knowledge (§9, Annex B) |
| 7 | **The starter moves** | Five move types from six rules — PL-1/DL-1 (alternates: B12 validated → DL-1 replaces PL-1), RK-1, SS-1, EV-1, OV-1 — all deletion or cap rules, all always-permitted. Exit moves are Phase 1 candidates. **The adherence auto-stop is removed**: §7.5 decided there is no adherence verdict, and a trader not following a rule is as-offered data, not a failed experiment. The drawdown stop remains as a safety pause stated as a fact. Every core test gets a planted synthetic behaviour (seventeen, three mechanisms), because a gate cannot rest on an unmeasured recall (§8, §11.1, §12.2) |
| 8 | **The Research Gate** | **"Medium effect" was undefined and, at the one size our own table gives, unreachable** — 80% recall demanded where §5.4 shows 57%. Replaced by recall ≥ 80% at 2θ_min on histories that reach the 80%-power count, plus an honesty gate: below that count the null must carry an MDE at or above the planted effect in 95% of runs. Class C confirmation is of the described fact (§11.1a), with "right facts, wrong reading" counted as confirming the fact; "top three" means ranked by hold-out-validated effect, agreement on cost never cause; the feasibility gate reads on n_min with the n_hold and fills-availability shares beside it (§15, §12.3) |
| 8b | **Recurring data** | The founder caught an assumption — *"why are we assuming he will not subscribe?"* — and it was conceded: nothing stood behind "few will re-upload", and it conflated subscribing with supplying data. **No supply rate is assumed.** The first decision kept connections in Phase 2 with a 70% supply-rate trigger; **corrected the same evening** after a review showed the trigger measured a rate while the bias — bad months go missing, by an amount the held data cannot estimate — exists at every rate. Connection is now the subscription's data path from Phase 1, built in Phase 0 weeks 5–8; manual months carry a sensitivity bound into pooled reads; the 70% now measures the connection rate (§7.8, Annex H) |
| 9–10 | **Low-frequency traders; the eight weeks** | Read against every decision above and left structurally unchanged: §12.5 stays a week-5 measurement with the choice deferred; §13 absorbs the recruitment count, the week-2 field checks, the options convention, the recall curves and the six-rule replay work without the gate moving. Week 8's output becomes **v1.1 — calibrated** |

## Annex J — Thesis touches created by the walkthrough, for one v1.5 pass

The thesis is frozen at v1.4 and wins every conflict (§1). None of the items below is a conflict: each is wording the thesis should carry to match a decision it has already accepted in principle, or a row its decision log and unknowns register do not yet hold. They are collected here so the amendment is one pass rather than six.

| # | Where in the thesis | Touch | Source |
|---|---|---|---|
| J1 | T§11.2 | *"A trader-level experiment verdict is decided on the process metric and the avoided-cost accounting"* → *"A trader-level experiment is reported rather than verdicted: the trader sees his adherence counts and the avoided-cost accounting as facts. Adherence enters the pooled read as a weight, not a gate."* | Concept 5 (§7.5) |
| J2 | T§23.1 decision log | New row, decided 2 Oct: **δ_pool = 0.05R** — the library bar, economic, sized in traders; a move that fails to certify is parked with its evidence, never deleted | Concept 4 (§7.4) |
| J3 | T§23.1 decision log | New row, decided 2 Oct: **no trader-level verdict**; the 80% follow-rate gate dropped because it cannot be resolved at the occasion counts a month produces | Concept 5 (§7.5) |
| J4 | T§23.1 decision log | New row, decided 3 Oct: **crude first, end to end, then everything Indian retail trades**; what transfers is machinery, calibration is re-established per instrument family as a gate | §1, §9 |
| J5 | T§23.1 decision log · Phase 1 scope | New row, decided 3 Oct and corrected the same evening: **a read-only broker connection is the subscription's data path from Phase 1**; manual upload is the doormat's path and a fallback. Connectors for the partners' brokers are built in Phase 0 weeks 5–8. The 70% bar now measures the connection rate and is labelled arbitrary | §7.8 |
| J6 | T§23.2 unknowns | New row: **the connection rate among paying subscribers**, and for the unconnected, the complete-month supply rate — distinct from willingness-to-pay and from retention, absent from the register, and the precondition for every post-diagnosis measurement | §7.8 |
| J7 | T§23.1 decision log | New row, due week 3: **the R-multiple convention for options** is written before the CTR schema freezes, though options are outside Phase 0 — because most of what the product will widen into is index options, and a futures-only R convention would have to be torn up rather than extended | Annex H |
| J8 | T§5.3 forbidden language | Extend the list with *"your plan", "your system", "your rule"* — the engine describes a behaviour and never attributes it to his intention in either direction | Concept 3b (§11.1a) |
| J9 | T§12.4 screen 5 · T§12.9 Ravi | Where the curated set is described as three rules, the Phase 0 set is five move types with the post-loss type having two alternates (pause or daily limit, decided by which test validated); Ravi's narrative needs no change beyond that count | Concept 7 (§11.1) |
| J10 | T§22 kill criteria · T§23.1 | A note that the most likely Phase 0 failure is the feasibility gate — the engine works and twenty crude partners with adequate histories could not be found — and that this is a market finding with a named escape (recruitment-only widening), not a kill | §15 |

| J11 | T§ differentiation · T§22 | The moat statement is sharpened from *"evidence-backed"* to *"pre-committed and measured"*: every test fixed and hashed before his data is seen; the engine's error rate published from noise corpora; five tests computed from data not in his file. And one kill-class finding is added: if the founder-written LLM baseline matches the engine's false-positive rate on realistic noise within five points, the diagnosis has no validity moat (§15). The 30-minute test — *could he reproduce this feature with a chat and his CSV?* — belongs in the PRD as a feature filter, not here | §2, §15 |

| J12 | T§ competition · T§19 · T§23.2 | **The likeliest copier is a broker, not a frontier lab.** A broker holds every trade as it happens — the recurring-data precondition of §7.8, with no re-upload, no trigger and no selection bias — and has distribution. The thesis's competitive section should treat brokers as the primary threat and, separately, as the channel; and the moat statement should name the one asset that stays unique after 1,000 traders and ten years: the intervention–adherence–outcome record on validated fingerprints, scored on one framework version. Everything else — tests, models, the evidence standard, the show — is copyable | §14 (regenerability), reviews of 3 Oct |

Nothing else in v1.4 moves. The Promise, the Canon, the four v1.4 DECIDED blocks and the three open rows of 1 October are untouched by anything decided here.
