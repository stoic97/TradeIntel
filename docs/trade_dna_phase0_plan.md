# PlusEV–TradeDNA · What happens next — the Phase 0 plan

*3 October 2026 · Child of Thesis v1.4 (→ v1.5 this week) and Research Specification v1.0 (frozen) · Owner: founder*

Three frozen documents say what the product is, what it promises, and how a claim earns the right to be made. None of them is the work. This page is the work, for the next nine weeks, with one owner per line.

## The six decisions behind the plan

| # | Decision | Why |
|---|---|---|
| 1 | **The PRD is written in week 8 from Phase 0's evidence.** This week: a skeleton with the **Input** and **Safety** sections written and the other ten as questions | The MVP three, the vocabulary, which tests ship and which moves partners adopt do not exist yet. Input and Safety do, and week 2's importer needs them |
| 2 | **Thesis v1.5 now, one sitting** — the twelve Annex J touches | Three of them (crude-first, connections in Phase 1, brokers as the copier) change what Phase 0 does; the team reads the thesis, and it must not disagree with the spec for eight weeks |
| 3 | **No Experience Specification yet.** The week-3 concierge report template is its v0 | The first show is on paper in week 3. It gets rewritten by watching three traders read it, not by writing it first |
| 4 | **Recruitment starts Monday, before the hash** | Signing is one session; finding twenty crude traders is two weeks and the binding risk (R-Spec §15) |
| 5 | The fund's own track (track record, memo) is **off this path** | Only if raising. Separate decision |
| 6 | **The research spec does not change** until Phase 0 hands back evidence | New ideas → candidate register (Annex B). New reviews → `post_freeze_notes.md` |

## Seats — who cannot be the same person

R-Spec §14 names six seats. A team of two or three fills them, with two exceptions that cannot be merged: **whoever runs the week-7 isolation read does not rule on it** (runner ≠ ruler), and **whoever writes a test does not validate it**. Name the people against the seats in week 1 and put it in the kickoff minutes.

| Seat | Owns | Can merge with |
|---|---|---|
| Research lead | Library, models, priors, corpora; runs analyses | Data engineer, product — not validator for his own tests |
| Validator | Reads isolation; records DOF | Anyone who did not write the test |
| In-house trader | Move mechanisms, risk classes, the cold read | Product |
| Data engineer | CTR, feature registry, determinism, connectors | Research lead |
| CEO / ruler | Verdicts on charged runs; majors; the monthly review | Nobody, for the rulings |
| Product | Screens, scorecards, recruitment, concierge sessions | In-house trader |

## Week 0 — this week (3–9 Oct)

| Do | Owner | Output |
|---|---|---|
| Move `trade_dna_research_spec_v1_0.md` to the top level — **done** | Founder | The freeze |
| **Start recruiting.** Post the partner brief in the places MCX crude retail traders actually are; screen for ≥ 200 crude trades over ≥ 3 months, willingness to export a tradebook, a 45-minute call. Target named: twenty by 16 Oct | Founder | A tracker with names, broker, trade count, status |
| Apply the twelve Annex J touches → **Thesis v1.5** | Claude drafts, founder freezes | `trade_dna_product_thesis_v1.5.md` |
| Write `framework_v1.yaml` — Part I of the spec, machine-readable: tiers, kills, nulls and their algorithms, families, θ_min per test, δ_pool, the risk envelope, the baseline procedure | Claude drafts, research lead owns | The file to be hashed |
| PRD skeleton — twelve sections, Input and Safety written, the rest as the question each must answer | Claude drafts | `prd_v0.1_skeleton.md` |
| Create `post_freeze_notes.md` | Founder | Where reviews go now |

## Week 1 — the commitment (12–16 Oct)

| Do | Owner | Output |
|---|---|---|
| **Kickoff session.** All seats. Read §1–§8 of the spec aloud. Disagreements are now or never. Sign. Hash `framework_v1.yaml` (SHA-256). Hash into the decision log and the minutes | CEO rules | The hash |
| Seats named in the minutes | CEO | — |
| AUTOPSY portability audit started — which categories generalise to external tradebooks | Research lead | A list, by week 2 |
| CTR specification and data contract v1, with contract/expiry and price-path resolution as correctness fields (§4.2) | Data engineer | Schema in the repo |
| Trademark search started | Founder | — |
| Recruitment continues — **the count is reported Friday** | Founder | Named partners / 20 |

**If fewer than twenty by Friday 16 Oct:** the recruitment-only widening opens (§15) — non-crude histories for correctness and calibration, crude kept as the validation instrument. Decide it that day, not in week 3.

## Week 2 — data in hand (19–23 Oct)

| Do | Owner | Output |
|---|---|---|
| Ten exports per partner broker, counted **field by field**: contract/expiry? fills? order types (SL/SL-M)? | Data engineer | The conditional tests' go/no-go (R7, R11) |
| Tick-history coverage for the contracts partners traded | Data engineer | E2 / E4′ go/no-go |
| **Concierge report template v0** from the thesis's six-screen arc: Mirror facts → Findings with tiers → evidence drawer → Avoidable Loss → the move → limitations → feedback control | Product + Claude | The Experience Spec's first draft, on paper |
| Synthetic generator: three mechanisms, seventeen flags; two noise classes (§12.2) | Research lead | Corpus A |
| CTR importer against development fixtures; certification set sealed by the validator | Data engineer | CTR v1 |

## Weeks 3–8 — the one thing per week

The full programme is R-Spec §13. The one thing that matters each week:

| Week | Dates | The one thing |
|---|---|---|
| 3 | 26–30 Oct | **Three concierge reports, by hand, on real partner histories, training zone only.** Manual execution, automatic rules. Watch each trader read it. Write down what he said, what he disputed, where he stopped reading |
| 4 | 2–6 Nov | SBC and M-SIM on the five models; nulls validated on noise; **the R-on-options convention written** before the schema freezes |
| 5 | 9–13 Nov | The eighteen tests on corpora A and B; recall-vs-sample curves; **the trade-frequency count; the n_min / n_hold shares; the LLM baseline run** (prompt written by the founder, before the run). *Diwali falls around 8 Nov — partners and the panel are unavailable that week; schedule accordingly* |
| 6 | 16–20 Nov | Replays and overlap checks for the six starter rules; **read-only broker connectors started** for the partners' brokers (§7.8) |
| 7 | 23–27 Nov | **The single isolation read**, all partner histories, final framework version. One degree of freedom. Expert panel. All concierge interviews done |
| 8 | 30 Nov–4 Dec | Calibrated values written in; the moves partners adopted; the scorecards; the Gate result → **Research Spec v1.1 — calibrated.** Then the PRD, the Experience Spec and the Technical Design are written from it, weeks 8–11 |

## What "done" means on 4 December

Not a working product. Not a subscriber. Eight weeks of evidence that the engine does not lie and that real traders exist to test it on:

- The hash matches everything shipped (Class A, D)
- The core tests fire on at least half the partner histories (feasibility)
- At least 60% of partners confirm the fact of a non-obvious Finding (thesis gate)
- The nulls sit inside [2%, 8%] on adversarial noise (Class B)
- The expert panel agrees ≥ 70% on the costliest three, against κ (Class C)
- The LLM baseline has been run and reported, whatever it says
- One or two starter moves adopted by real partners — the first rows of the record (§7.8)

**The most likely failure is the feasibility gate**: twenty crude partners could not be found, or the tests starve on real histories. That is a market finding with a named escape, not a kill.

## What Claude drafts next, in this order

1. **The recruitment kit** — one-page partner brief (what they get, what we need, what we never do), the screening questions, per-broker tradebook export instructions (Zerodha, Dhan, Angel One, Upstox, Fyers), consent language aligned to T§19.
2. **Thesis v1.5** — the twelve Annex J touches applied.
3. **`framework_v1.yaml`** — Part I, machine-readable, from the spec.
4. **PRD v0.1 skeleton** — Input and Safety written, ten questions.
5. **Concierge report template v0** — for week 2.
6. **Phase 0 engineering breakdown** — repo layout, CTR schema, feature registry, evidence object (Annex C) as code.

## The one thing not to do

Do not reopen the research spec. Around week 3 a concierge report will produce something the document did not predict and someone will want to fix the wording. The answer is: decision-log row; if it touches PRE-COMMIT, a major version after Phase 0. The document is the constitution. The work is the twenty traders and the three reports.
