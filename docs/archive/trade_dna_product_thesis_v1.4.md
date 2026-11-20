# PlusEV–TradeDNA · Trader Intelligence — Product Thesis v1.4 — Baseline (Frozen)

*1 October 2026 · Companion: Brainstorm Workbook v1.1 (frozen; referenced as B§) · Supersedes Thesis v1.3*

**Status: BASELINE, FROZEN on 30 September 2026; amended 1 October 2026 (v1.4).** From here, every change requires a decision-log entry (§23.1). New ideas go to the workbook; evidence changes the workbook; a promoted decision changes this document; this document produces the Research Specification, the Experience Specification, the Technical Design and the PRD (Appendix D). Two operational items are open and do not block the baseline: the Phase 0 start date, set at kickoff, and counsel's confirmation of the regulatory posture, a gate before Phase 1.

**What v1.4 changed, and why — the amendment of 1 October 2026.** Writing the Research Specification established, by arithmetic rather than judgement, that an individual trader's risk-adjusted expectancy cannot be measured inside any window he will wait through: at the typical retail per-trade dispersion of about 1.4R, separating a 0.1R improvement needs roughly 2,400 trades in each of the before and after windows — nearly three years per window at fifteen trades a week, against a thesis cap of 150 trades. The v1.3 verdict rule would therefore have produced no verdicts at all, ever. Four consequences follow, and they are the whole of this amendment:

1. **A trader-level verdict is decided on process and avoided cost** — did he follow the rule, and what did his own historical rates say the avoided situations were worth. Trader Improvement keeps its definition and is read where it is measurable: a per-trader quarterly review, and a pooled read per move type, which needs 10–63 traders rather than thousands of trades (Canon 9, Promise 4, §11.2, §18.1, Appendix A3).
2. **The curated set is offered whole, and "exactly one primary" is rescoped** to the pooled study of move types. It was protecting the attribution of an individual improvement that is not measurable with one move either, so it limited the trader without buying us anything. The real constraint is overlap, not count (Canon 8, §10, §11.2).
3. **Replay is illustration, not evidence**, and may never select a move. "Impact" in the Next Best Move ranking is the validated effect that survived the hold-out — never the replay's improvement, which is an in-sample fitted quantity (§10).
4. **The forward statement has one permitted form** — conditional arithmetic on his own measured, conservatively shrunk rates, never a forecast of returns (§5.2, §10).

Nothing else moves. The founding idea, the other Canon points, the Twelve Laws, the show, Avoidable Loss, the trust architecture and the roadmap phases stand as frozen.

**Tags.** **FACT (internal)** — proven by PlusEV's own systems or data · **FACT (external)** — carries a source (Appendix F) · **DECIDED** · **HYPOTHESIS** — our belief awaiting validation · **UNKNOWN** · **EXPERIMENT** · **PARKED**. A claim about the world without a source is a HYPOTHESIS, however obvious it feels.

**How to read.** §0 is the position, the twelve questions this thesis answers, and the Canon inherited from the frozen workbook. §1 is the founding idea, intact. §2–5: problem, product, why us, what we can know. §6–11: the intelligence. §12: the show. §13–15: value exchange, loop, business. §16–20: competition, moat, metrics, trust, technology. §21–23: roadmap, risks, decisions. Appendices: the four specifications (Avoidable Loss, Process Score, North Star, experiment safety), schema, glossary, document map, provenance, sources.

**What v1.3 changed** (Reviews I and J, and the founder's judgment, 30 September): the Canon's lineage is stated rather than claimed identical; the risk-envelope invariant replaces "no financial risk"; a minimum practically important improvement (δ_min) enters the PASS criterion; "global readiness costs nothing now" is withdrawn; every external fact is sourced or re-tagged (Appendix F); six screens and the interest engine's ranking are marked as implementation hypotheses under frozen principles; the twelve questions, the market data behind "why now", the Process Score posture, the existential risks (§22.1) and the 12-month picture (§21) are added; the two blocking rows become operational gates; Avoidable Loss is frozen as the signature output with its mathematics a calibration item. Nothing in the founding idea changed.

**This document is the master index, not the permanent home of every subsystem.** Appendix D lists the six documents it splits into after Phase 0.

---

## 0. The thesis

**In one sentence.** Trade DNA transforms a trader's trade-level history into an evidence-backed computational model of how they trade; it shows them where their edge comes from and where it leaks, gives them their next best move, measures whether it worked, and keeps updating the model — delivered as a show they cannot stop watching and can prove is true.

**The category we are building.** Not an AI trading journal, not a psychology analyser, not a coach: **Trader Intelligence**. The doormat is the first product that exposes that capability; the Trader Model is the asset; the platform is what grows around it.

**North Star.** Understand the trader → identify edge and leakage → prescribe the next best move → measure what changed → update the Trader Model.

**The standard.** Don't tell the trader a story about himself. Reconstruct his trading reality from evidence, show him where he stands, give him the next best move, and prove whether it made him better.

**The map metaphor — DECIDED.** Trade DNA is a map of how you trade: the Edge Map and Leak Map are the terrain; archetype and Process Score are your position; Next Best Move is the route; the experiment is the drive; each DNA version is the journey log; the DNA Map is the mini-map you navigate by.

### The questions this thesis answers — from Workbook §1
The thesis behind the thesis. Every section below exists to answer one of these; a feature that answers none is decoration. Where each answer lives:

| # | The question | Answered in |
|---|---|---|
| 1 | Which three outputs would make a trader say, *"PlusEV found something I could never have found myself"*? | §10 — the flagship outputs and the MVP three (Phase 0 decides) |
| 2 | What can we reliably know from 100–500 trades — and how do we say the rest honestly? | §5, §6.2, Appendix A1's minimums |
| 3 | How does a trader *know* we were right, without taking our word for it? | §6 (the evidence drawer), §11.3, §17 (published results), Promise 1 |
| 4 | What is genuinely valuable to a trader who is losing and has no demonstrated edge? | §3.3, §6.2 |
| 5 | What makes a trader finish all six screens — and share the last one? | §12, §13 (the DNA Card) |
| 6 | What would make a trader come back every week without being nagged? | §12.7, §14 |
| 7 | What would a prop firm, a broker or an educator pay for? | §15.4 |
| 8 | How do we prove PlusEV *caused* an improvement, not the market? | §11.2, Appendix A3 |
| 9 | What makes the brand trusted when a hedge fund owns the product? | §19, Promise 10 |
| 10 | What is the smallest thing we can ship that proves the brain behind the show is extraordinary? | §21 — Phase 0 concierge and the MVP definition of done |
| 11 | What must PlusEV understand about traders — and do with that understanding — that a journal, a broker or a generic AI cannot? | §16, §17 — the loop and the standard |
| 12 | What would we regret building in year one? | §22, §23.3 |

**What "legendary" would mean — ambitions, stated as HYPOTHESES, not facts**
- That we define a category and publish the standard others are measured against.
- That we are known as the product whose success metric is the trader measurably getting better, rather than analytics engagement. *(HYPOTHESIS: differentiation by outcome, not by feature.)*
- That the free doormat becomes the most shared artifact in retail trading. *(HYPOTHESIS; the doormat proxy in §18 measures it.)*
- That the Process Score becomes the number the industry uses for a trader's process. *(HYPOTHESIS; the market decides — §7.4.)*
- That the product compounds on three levels: each trader's model deepens; the population sharpens every diagnosis; the intervention-outcome record learns what works for whom.
- That it is trusted because it is inspectable, and because the trader's data never touches the fund.
- Ten-year picture (HYPOTHESIS): every serious trader has a Trade DNA; the Trader Model is the standard representation of a trader; PlusEV is the operating system around it; capital finds process.

*Epistemic note: this document argues for evidence over narrative. Its own ambitions are held to the same rule — none of the above is written as a fact until it is measured.*

### The Trader Promise — DECIDED (public)
1. Every claim about you comes with the trades behind it.
2. We tell you when we don't know.
3. We show your strength before your leak.
4. You always know your next best move — whether you kept to the last one, what it saved you, and what the evidence says it does for traders like you.
5. Process over P&L: we judge how you trade, not whether the market was kind this month.
6. We never show you a number the evidence does not support.
7. We never ask for anything that only benefits us.
8. No buy or sell calls. Ever.
9. No experiment we give you will raise your risk limits, or ask you to risk more so that we can measure something.
10. Your data is yours: it never touches our fund, and it is deleted when you say so.

### The Twelve Laws — DECIDED (internal)
1. **Value before extraction** — every data request is earned by unlocking value for the trader.
2. **Evidence before narrative** — a compelling explanation never outranks the evidence.
3. **Fact is not hypothesis** — observable behaviour and inferred psychology stay separate.
4. **Process is not outcome** — winning does not prove a good process; losing does not prove a bad one.
5. **Confidence is part of the insight** — uncertainty is visible and meaningful.
6. **Try to kill the insight** — every candidate faces adversarial validation before promotion.
7. **Compute everything, reveal by interest, test one thing at a time** — priority = impact × confidence × actionability × relevance.
8. **Every recommendation is testable, and none of them widens the risk envelope** — advice becomes a measurable experiment inside the trader's own risk limits (§11.4).
9. **Machine effort exceeds user effort** — PlusEV reconstructs and analyses; the trader never becomes the data engineer.
10. **Optimise for improvement** — engagement is a means; a better trading process is the outcome.
11. **The reveal engine may select, order, deepen and narrate; it may never create or alter a Finding.** The interest engine serves the trader's understanding, never the company's capture rate.
12. **Every component has a written objective, and nothing ships without one.** If we cannot say what a screen, a model or a move is *for*, in one sentence that can be measured, we do not know what we are building. The objective comes before the code and before the score.

### The Canon — inherited from the frozen Brainstorm Workbook v1.1, with post-freeze decisions recorded
*Lineage:* Workbook v1.1 (frozen 29 September, the thinking floor) → the founder's decisions of 30 September → this thesis (the build floor). Items 1–7 and 9–14 are the workbook's, word for word. Item 8 is the workbook's rule extended by the move stack (v1.2). Item 15 records the two post-freeze decisions — market and name. Item 16 is the one post-freeze addition — the Measurement Layer. The workbook's Canon is not rewritten; the workbook's header records this lineage.

1. Trade DNA is PlusEV's doormat: a free, one-time, evidence-backed diagnosis of how a trader trades — the front door to the PlusEV platform, deliberately not the final product.
2. The input is trade-level data — every trade, fills where available — never a P&L number, reconstructed into the Canonical Trade Record.
3. The atomic unit is the Finding: a claim with evidence, sample size, effect size, confidence tier and a lifecycle. Nothing reaches a trader that is not a promoted Finding.
4. The Evidence Standard governs everything: Fact → Pattern → Hypothesis → Action → Validation; tiers Established / Likely / Exploratory; adversarial validation; false-discovery control; hold-out within the trader's own history; "Not enough evidence yet" is a valid result.
5. The Trader Model has four DNAs — Strategy, Risk, Execution, Behaviour — plus Process Health, summarised as a Process Score that sits on top of the diagnosis and never replaces it. Market/Regime DNA is the fifth dimension, later. Archetypes are emergent, probabilistic summaries, never the lens.
6. The signature number is Avoidable Loss — the cost of behaviour the trader could have avoided, stated conservatively in his currency. The Process Score is our candidate for the category's standard number; the market decides whether it becomes one.
7. The deterministic research engine is the source of truth for every number. AI is the research interface and orchestrator — import mapping, narration, explanation, orchestration, and hypothesis proposals to humans — and can never create or alter a Finding.
8. The engine computes every relevant prescription and ranks them as Next Best Move by the **validated effect that survived the hold-out**, never by the replay; the show reveals them as the trader's interest shows, and shows the whole route, not one step. **He may adopt the whole curated set**, provided every move is risk-reducing: moves acting on disjoint trade sets run in parallel and are each measured separately, and moves acting on the same trades are merged into one rule before being offered. Every move is replayed on his own history first — as illustration, labelled in-sample — with length and success criteria set by the measurement design before it starts, and never widens his risk envelope (§11.4). **"Exactly one primary" governs the pooled study of move types** (§11.2), not what the trader may do.
9. North Star: Trader Improvement — the change in risk-adjusted expectancy per trade versus the pre-intervention baseline, regime-adjusted, with process-quality guardrails. **It is read where it is measurable: a per-trader quarterly review, and a pooled read per move type.** A trader-level experiment verdict is decided on the process metric and the avoided-cost accounting (§11.2, Appendix A3). Engagement depth is a leading indicator only.
10. The show is the product: a six-screen doormat arc, one cognitive job per screen, interactive and animated evidence, a DNA Map, hooked from the first screen, basic to depth, built for short attention spans — and insight-dense on every screen.
11. Every action is a signal. Everything that must survive the Evidence Standard is computed before the show; what to show next is computed while he reads, from his activity and his responses. The first aha is never behind an ask.
12. Value exchange is reciprocity: every ask has a product reason the trader can understand; no ask that only benefits PlusEV; no phone number until an alert product exists.
13. Growth is built in: the DNA Card, the monthly DNA, educators and prop firms, and public research from consented aggregates.
14. Trust is architecture: an entity-level wall between Trade DNA data and the fund; least privilege; transparent deletion; read-only connections; counsel before launch; every Finding traceable to evidence, method and version.
15. Sequence by uncertainty: Phase 0 Discover (concierge, 20–50 design partners) → Phase 1 Doormat → Phase 2 Loop → Phase 3 Platform → Phase 4 Scale. Launch: **India first, global-ready — decided.** Product name: **PlusEV–TradeDNA — decided**, always under the PlusEV house brand, with the composite mark filed after the week-2 trademark search.
16. Every component states its objective and is scored against it — every engine, model, Finding type, screen, move and ritual. Scores are inputs to human decisions, never automatic changes to what a trader sees. The definitions are the asset.

---

## 1. The idea as conceived — kept intact — FACT (internal: the founding record)

- **PlusEV platform infrastructure** — a one-stop solution for all serious traders. **Doormat → Trade DNA**: the first thing every trader steps on.
- **We own a hedge fund. We will be a platform** — so that every serious trader has a PlusEV subscription. **Brand:** after ten years, every trader is on PlusEV.
- **Input:** trade-level data. **Trader:** retail on mobile; serious traders who read, chart and have a system; algo and advanced traders; prop firms. **Output:** a full diagnosis, presented like a mini-map.
- **The framework** is built from a high level of human psychology, research papers and data, trader behaviour and what traders need and value, trader satisfaction, and trader type. It tags the data and the trader; the tag determines the diagnosis and the way to present it. Basic stats → archetype → advanced quant analysis → curate the diagnosis: first establish that this is pure value, then give him what he needs to understand — what will work.
- **The framework is the most important asset of the engine.** It behaves as the world's best quant researcher: identifies the archetype on the spot; knows the complete range of market participants from gambler to Renaissance; knows where the user is standing, what would be valuable for that archetype, and what the next best move is from where he is. Every piece of information is processed to make the diagnosis the best it can be; the user never waits.
- **The journey:** ① home page — catchy, one button → ② upload → ③ computation, never boring → ④ the presentation of the diagnosis → ⑤ exit with positivity, trust, and the brand remembered.
- **The first screen:** two or three basic stats, a chart, three or four pointers — what he already knows (trust) and something he did not (realisation). Then value to his trading system, interactively.
- **Properties of one complete show:** P-1 north-star value using the highest form of intelligence; P-2 easy to grasp; P-3 engagement and a growing exchange; P-4 the low attention span of the masses; P-5 brand consistency; P-6 modern design and animation.
- **Value exchange:** when he is engaged, we ask — name, email, trading style, instruments, subscription — distributed, with smartness about when to ask what; real value traded for his action, his data and his money.

## 2. The problem — HYPOTHESIS (the framing we build on; the measured facts behind it are in §3.3 and §4.1)

Trading software is rich in data and poor in understanding. A trader with thousands of trades still cannot answer: Where is my edge? In which market states does it survive? Which behaviour destroys it? What has that cost me? Am I profitable because the process is sound or because the outcome was kind? What is my next best move — and did the last one work? Journals log. Analytics report. Brokers describe. AI chat narrates. The opportunity is to discover the few high-impact truths a trader cannot see alone, show them in a way he cannot look away from, and prove whether acting on them helped.

## 3. What we are building, and for whom

### 3.1 Four products, one progression — DECIDED

| Product | The trader's question | Value rung | Phase |
|---|---|---|---|
| Diagnostic engine | Understand me — where do I stand? | Stop the bleed · protect the edge | 0–1 |
| Research engine | Find my edge — and where it disappears | Protect the edge | 1–2 |
| Intervention system | What is my next best move — and did it work? | Change what you're ready to change · know what worked | 2 |
| Platform | Run my trading through PlusEV | Grow over time | 3–4 |

### 3.2 The value ladder — to the trader — DECIDED
1. **Stop the bleed.** Avoidable Loss, in his currency.
2. **Protect the edge.** Where he actually wins, with evidence.
3. **Change what you're ready to change — and know what worked.** Next Best Move: every relevant prescription computed and ranked, the route shown whole, as many moves adopted as he is ready for — one measured at a time so the answer is real.
4. **Grow over time.** A model of himself that evolves.

A feature that does not sit on a rung is not built.

### 3.3 The honest market — FACT (external, Appendix F) · DECIDED
Most retail traders lose, and in our launch market this is measured, not assumed: SEBI found that 93% of individual equity F&O traders lost money over FY22–FY24, with aggregate net losses above ₹1.8 lakh crore, and that 91% lost in FY25 [F1, F3]. The product must be genuinely useful to a losing trader: quantify avoidable losses, say plainly when there is no demonstrated edge yet, and give a responsible next best move. This is also the regulatory-safe posture (§19).

### 3.4 Who we serve — DECIDED
- **Go-to-market personas** are separate from the **diagnostic taxonomy** (methodology, horizon, market, capital, maturity, risk profile, behavioural profile, regime sensitivity).
- **First:** the serious discretionary trader — 100–2,000 trades, broker app, wants to know why results don't match effort. The retail-on-mobile trader enters through the same free doormat and is served honestly.
- **Second:** systematic and algo traders via Strategy DNA — AUTOPSY's native job.
- **B2B:** prop firms first, then brokers and educators (§15.4).
- **Launch: India first, built global-ready — DECIDED.** The Indian market is huge — roughly 96 lakh unique individual F&O traders across the top thirteen brokers in FY25, and one of the largest retail derivatives populations in the world [F3] — and PlusEV's team, data and market knowledge are here. **What "global-ready" means, precisely:** the canonical data and model layers are designed market-agnostic where practical — instrument, currency, session, calendar and charge model are parameters, not assumptions — while market-specific expansion (localisation, tax and charge engines, broker integrations, data licensing, entity and payment structure, support) is deferred and paid for when a market is opened, never in advance. Instruments at launch: NSE/BSE cash and F&O, MCX.

### 3.5 The name — DECIDED: **PlusEV–TradeDNA**, under the house brand

A search on 29 September found **tradedna.in**, a live Indian F&O journal doing post-trade behavioural analytics — revenge trading, tilt, overtrading from the tradebook, an Indian charge engine, Mumbai data residency, an explicit no-signals compliance posture. Also **TraderDNA**, **trade-dna.com**, **Arxion's Trader DNA Profile**, and, in adjacent categories, **DNA Markets** (a CFD broker), **DNA Funded** (a prop firm) and **TradersDNA** (media).

The name is decided in full knowledge of that. The story, the vocabulary family (DNA Card, DNA Map, Monthly DNA, "your DNA v1.1") and the instant comprehension across Hindi-English audiences are worth more than a cleaner search result — **provided the house-brand structure is treated as part of the name, not a styling choice.**

**The structure — DECIDED, and binding:**
- **PlusEV is always first and largest.** The lockup is PlusEV above, TradeDNA beneath. Never "TradeDNA" standalone; never "DNA" alone, which is where the broker and the prop firm live.
- **PlusEV is the searchable token.** URL: plusev.in/dna. Share text and Card: "My PlusEV DNA — Breakout-leaning · Process Score 58." Page titles lead with PlusEV. Within a month traders say "my PlusEV DNA," which nobody else can claim.
- **We file the composite,** PlusEV–TradeDNA, in IP India classes 9, 36, 41 and 42 — far more registrable than the bare word — after the week-2 search. WIPO check for the global path.
- **The exit stays cheap.** If global expansion collides, we rename the product line, not the company. Users who know PlusEV follow us.
- **Not defensible as a bare word,** and the thesis says so: we compete on the loop and the published standard (§16), never on owning "DNA."

Shortlist retired but recorded: Tradeprint · Edgeproof · Reroute · Bearing.

## 4. Why now, why PlusEV

### 4.1 Why now — FACT (external, Appendix F) where a reference is given; HYPOTHESIS where marked
- **The losing majority is measured, and it is large.** Of more than 1 crore individual traders in equity F&O studied by SEBI, 93% lost money across FY22–FY24, with aggregate net losses above ₹1.8 lakh crore; the average loss was about ₹2 lakh per trader; only 1% earned more than ₹1 lakh after costs; and more than 75% of loss-makers kept trading [F1]. In FY25, 91% lost, and net losses rose 41% to ₹1,05,603 crore [F3]. "Effort without results" is not a niche complaint; it is the median experience.
- **The population is young, large, and consolidating around the trader who stays.** Unique individual F&O traders grew from 7.1 lakh in FY19 to 45.2 lakh in FY22 [F2] and to roughly 96 lakh across the top thirteen brokers in FY25 [F3]; the under-30 share rose from 31% in FY23 to 43% in FY24 [F1]. The regulator's own measures are thinning the crowd — unique traders fell from 61.4 lakh in Q1 FY25 to 42.7 lakh in Q4 FY25 [F3] — which concentrates the market on exactly the trader who remains and wants to get better. An honest process product is timely, not late.
- **Trade-level data is in every trader's hands — HYPOTHESIS until Phase 0 counts it.** Indian brokers export tradebooks and P&L statements; whether the top brokers' exports support fill-level reconstruction is verified in Phase 0 with ten exports per broker (§23.2).
- **Explanation is cheap; a research-grade engine is rare — HYPOTHESIS.** Language models make narration nearly free, so the scarce asset moves to the engine that decides what is true.
- **The category rewards logging, not improvement — HYPOTHESIS.** Its incentives are visible in every product we verified (§16); the journaling category's size is UNKNOWN and belongs to the category study.

A mass, measured problem; a data path that exists; a category not yet built around proof.

### 4.2 What PlusEV has — FACT (internal)
- A research discipline built to fight overfitting — pre-registered hypotheses, thresholds committed before measurement, a runner ≠ ruler firewall, robustness as part of acceptance, frozen candidates, a one-shot hold-out read — encoded here as architecture (§8.2).
- AUTOPSY: a trade-diagnostics framework producing category scores — execution capture, exit taxonomy, risk profile, setup quality, regime.
- Market-context infrastructure: a backtest engine, validated minute data, regime and structure analysis, for covered instruments.
- A trader's eye in-house, to seed the intervention library and the gold standard.

### 4.3 What PlusEV does not yet have — FACT · UNKNOWN
Market-data coverage beyond crude for the launch instruments (UNKNOWN) · a canonical trade-record layer for messy external data (§9) · consumer product, UX, distribution and brand · team capacity beyond the fund (UNKNOWN) · regulatory clarity (UNKNOWN) · a registered mark for the composite name (§3.5; filed after the week-2 search).

### 4.4 The strategic role — DECIDED
Deliver unusually high-value intelligence quickly, earn trust through evidence, create a persistent Trader Model, and make the natural next step a deeper PlusEV relationship.

## 5. Epistemic boundaries

### 5.1 What the system can know — DECIDED (product language)

| Evidence class | Inferable? | Product language |
|---|---|---|
| Direct facts | Yes | "Your median holding time is…" |
| Conditional patterns | Often, with sample | "After two losses, your expectancy falls to…" |
| Behavioural signatures | Yes, as observable patterns | "Your behaviour is consistent with…" |
| Internal emotional state | No | Never claimed |
| Causal mechanism | Sometimes; needs design | Labelled hypothesis unless validated |
| Future performance | Never with certainty | Never presented as guaranteed |
| **The arithmetic implication of his own measured rates** (v1.4) | **Yes, conditionally** | "If those rates hold, operating only outside this condition puts your average at +0.12R instead of −0.05R" — the shrunk estimate, the conditional shown, and a statement about his process rather than about the market (§10) |

### 5.2 The hierarchy of claims — DECIDED (company-wide language)

| Level | Wording | Example |
|---|---|---|
| Historical association | "was associated with" | "Trades after two losses were associated with lower results." |
| Robust pattern | "persists across slices" | "…and this held across instruments, sessions and your last 100 trades." |
| Research hypothesis | "may represent" | "This may represent a behavioural leak." |
| **Conditional implication** (v1.4) | "if those rates hold, … would be" | "If those rates hold, staying out of this condition puts your average at +0.12R." — arithmetic on his own shrunk rates; never "will be" |
| **Adherence and avoided cost** (v1.4) | "you kept to it" · "you avoided" | "You hit 12 post-loss moments and took 2. The 10 you skipped were worth at least ₹18,000 at your own historical rate." — a count and an accounting, never a claim that he improved |
| Validated intervention | "changing this produced" | "Across traders like you, waiting 30 minutes produced …" — earned by the pooled read (§11.2), not by one trader's window |

### 5.3 Behavioural inference, not psychology — DECIDED
Trader States are observable conditional states — after two consecutive losses, after a large win, drawdown beyond X, first hour, after a size increase, expiry day — never latent emotions, in code or in copy.

### 5.4 Small samples — DECIDED (the method) · HYPOTHESIS (that it rescues 100–300-trade histories; Phase 0 tests it, §23.2)
**Population-informed individual estimation**: hierarchical (Bayesian) pooling shrinks an individual's estimates toward what is typical for traders with a similar fingerprint, with confidence reflecting both. A data-learning effect, not "everyone improves everyone." The pooling methodology is specified directionally here and calibrated in the Research Specification; the honest-gap states (§6.2) are what the product says when pooling is not enough.

## 6. The Finding — the atomic unit — DECIDED

- **Evidence object.**

```
finding_id · trader_model_version · claim · claim_level · dna · evidence (trade_ids, slices, market_context)
· sample_size · effect_size · baseline · confidence_tier · stability · holdout_result · adversarial_checks
· limitations · economic_impact (currency, % equity, avoidable_share, R if stop) · recommended_actions (ranked)
· interest_signals · dispute_state · framework_version
```

- **Lifecycle.** candidate → validated → promoted → shown → confirmed / disputed → acted → measured → updated or retired.
- **Confidence tiers.** *Established* — shown as diagnosis. *Likely* — shown with uncertainty visible. *Exploratory* — "worth watching"; never a prescription.
- **Curation.** Priority = impact × confidence × actionability × relevance.

### 6.1 Disagreement handling — DECIDED (was a gap in v1.1)
When a trader marks a Finding **Wrong** or **Not sure**, the product responds — silence would cost the trust the feedback control exists to build.

| Layer | What happens |
|---|---|
| Immediately, in the show | The evidence drawer opens rather than a defence: the trades, the slices, the hold-out. Copy: "Here's what we saw. If this still looks wrong, tell us why." One optional tap: *wrong facts · right facts, wrong reading · I've already changed this.* |
| To this trader's model | The Finding's `dispute_state` is set. "Right facts, wrong reading" demotes the hypothesis layer but keeps the pattern. "Wrong facts" suspends the Finding from his diagnosis and from Next Best Move until reviewed, and any prescription depending on it is re-ranked out. "Already changed" re-scopes the Finding to the period before the change and re-runs it on recent trades. |
| Statistically, across traders | Dispute rate is tracked per Finding *type*. Above a pre-registered threshold, that test is flagged for research review — it is a signal that the test, the thresholds or the wording is wrong, not that the trader is. |
| Back to the trader | If review changes the Finding, he is told in the next weekly review or monthly DNA: "You told us X was wrong. You were right — here's what changed." Nothing is silently dropped. |
| Audit | Disputes are reviewed weekly in Phase 0–1 and monthly after; the dispute-rate table is part of the Evaluation Framework (§11.3), and published accuracy (§17) is computed net of upheld disputes. |

**The rule when engine and trader disagree:** we do not overturn a validated Finding because it is unwelcome, and we do not dismiss a trader who says it is wrong. We show the evidence, log the dispute, and let calibration decide — with his diagnosis suspended in the meantime.

### 6.2 "Not enough evidence yet" — the experience — DECIDED (was a gap in v1.1)
Two distinct states, never conflated:

| State | Meaning | What the trader sees |
|---|---|---|
| **Not enough evidence yet** | The data cannot support a claim: too few trades, an ambiguous reconstruction, missing market context, or nothing survived validation | What we *can* establish, listed as facts; what we are watching, as Exploratory; exactly what would resolve it ("about 40 more trades with stops recorded, or your March–June history"); a next best move that is a data move, not a trading move |
| **No demonstrated edge yet** | The data is adequate and no positive-expectancy condition survives validation — a real finding, not a gap | Said plainly and without shame; Avoidable Loss still shown, because the cost of leaks is measurable even with no edge; the next best move is protective — reduce size, paper-trade the closest-to-positive setup, focus on a process metric — with a path back and a re-check date |

- Framing rule: never an error screen, never an apology, never a dead end. Every such screen ends with something true and something to do.
- In the doormat these can replace screens 3 or 5; the arc never breaks. In the subscription they appear as a status on the DNA Map with a countdown to the next re-check.
- This is a first-class result (Law 5 and Promise 2), and Phase 0 tests whether it reads as honesty or as failure (B§14).

## 7. The Trader Model — DECIDED

| DNA | Question | Examples |
|---|---|---|
| Strategy DNA | What does he trade and where is the edge? | setup, direction, instrument, regime, session, expectancy surface |
| Risk DNA | How is risk taken and how does it change? | size, leverage, drawdown response, concentration, escalation |
| Execution DNA | Does realised execution match intent? | timing, slippage, capture efficiency (MFE/MAE), exits, holding |
| Behaviour DNA | How does behaviour change under observable states? | post-loss reaction, overtrading, premature exits, reactive sizing |

- **Process Health** beside P&L: good outcome / poor process, poor outcome / strong process, lucky-but-fragile, and no demonstrated edge yet.
- **Archetypes are emergent** — Observe → Diagnose → Profile → Archetype; probabilistic and multi-dimensional; used softly to weight priors; always beside the individual estimate.
- **Market/Regime DNA** is the fifth dimension; PARKED beyond MVP.
- **The model is versioned** with diffs — the journey log (§14).
- **The Process Score** is specified in **Appendix A2**; its calibration is a Phase 0 deliverable. **The posture — DECIDED:** we launch with the Process Score as *our* standard for process quality — inside the diagnosis from Phase 1, on the public DNA Card once convergent and predictive validity are demonstrated (A2). We say we want it to become the category's standard; we never say it is. The market grants that title, and the published methodology is how the score earns it.

## 8. The intelligence stack — DECIDED

| Layer | Function | Output |
|---|---|---|
| Ingestion | Tradebooks; later read-only connections | Raw trade events |
| Reconstruction | Fills → positions → round trips | Canonical Trade Record |
| Market enrichment | Contemporaneous market state | Contextual trade records |
| Feature engine | Deterministic features | Feature set |
| Research engine | The pre-registered test library; agents propose within the protocol | Candidate Findings |
| Validation engine + evidence registry | Try to disprove; robustness; store evidence objects | Validated Findings |
| Trader Model | Four DNAs; Process Score | Versioned DNA |
| Curation engine | Prioritise | Diagnosis set |
| Next Best Move engine | Score every relevant prescription; replay; rank | Ranked prescription library |
| Measurement engine | Evaluate the response | Verdict and outcome record |
| Interest engine | While he reads: what to reveal, deepen, narrate, ask | Live reveal plan |
| Narration layer | Explain promoted Findings only | The show |

### 8.1 The evidence-first pipeline
```
Trades → Canonical Trade Record → Facts → Patterns
      → Strategy / Risk / Execution / Behaviour evidence → Provisional archetype (probabilistic)
      → Diagnosis → Next Best Move (all prescriptions, ranked) → Reveal by interest
```

### 8.2 Research discipline as architecture
```
Insight Generator → Validation Engine → Evidence Registry → Insight Promotion → Narrative Composer → Presentation
```
Fixed research protocol + user-specific estimation + fixed promotion rules. Runner ≠ ruler; commit before measure; robustness with acceptance; a monotone slope is a fitted point; zero degradation is a red flag; hold-out within the trader's own history. The composer reads evidence objects only.

### 8.3 AI as the research interface and orchestrator — DECIDED
**The research engine is the scientist; AI is the research desk — the interface and orchestration layer around it.** The deterministic engine is the source of truth for every number.
1. **Import mapping** — proposes column mappings for a messy export; the trader confirms on one screen.
2. **Agentic research under the protocol** — runs the pre-registered library per trader, proposes which tests to prioritise, attempts to kill candidates; the validator rules.
3. **Narration at the trader's level** — composed from evidence objects with a faithfulness check: every number in the prose must match an evidence object or the screen does not ship.
4. **"Explain this"** — §8.5.
5. **The hypothesis inbox** — from population patterns the model proposes new candidate tests to the research team, who pre-register or discard them. AI proposes; the protocol governs; humans pre-register; the machine validates.

### 8.4 Learning across users — DECIDED
Population priors update as traders join (governed, consented, anonymised). Intervention outcomes pool by behavioural fingerprint × condition. Prescriptions are A/B-tested among equally ranked candidates. Every feedback label calibrates the engine. **Framework versioning is specified in §8.6.**

### 8.5 "Explain this" — specification — DECIDED (was a gap in v1.1)

- **Scope.** It answers only from the evidence registry and the trader's own CTR: what a Finding claims, which trades are behind it, how the number was computed, what the confidence means, what would change it, how a prescription follows from it, and what a term means.
- **Out of scope, always.** Predictions of future performance or market direction; any buy/sell view on a position; speculation about his emotions or life; claims about other traders' data; anything requiring a computation the engine has not run and validated.
- **When it cannot answer:** "I don't have evidence for that." Then what it does have, and — if the question is worth answering — it becomes a candidate test in the hypothesis inbox rather than an answer.
- **Architecture.** Question → retrieve the evidence objects for that Finding → compose → faithfulness check → render. Every number in an answer must resolve to a field in a retrieved evidence object; unresolved numbers block the answer, not a caveat on it.
- **Evaluation before ship.** A fixed question set per Finding type run on synthetic traders with known ground truth; a hallucination suite of unanswerable and adversarial questions ("prove I'm a good trader", "should I go long tomorrow", "what was my emotion here"); a refusal-quality review. Gate: zero unresolved numbers on the fixed set, and no answer outside scope on the adversarial suite.
- **Phase 1 minimum viable version:** per-Finding, from a fixed intent set (what · which trades · how computed · how confident · what would change it), templated answers with model-composed language, no free-form conversation. Free-form "Ask your DNA" over the registry is Phase 2, after the faithfulness harness has run in production.

### 8.6 Framework versioning — DECIDED (was a gap in v1.1)

| Question | Rule |
|---|---|
| What counts as a version change | **Major** — a new or removed test, a changed promotion rule, a changed Process Score formula. **Minor** — a new threshold within an existing test, a prior update, a copy change. Every Finding and every score carries the exact `framework_version`. |
| When diagnoses recompute | Majors recompute every active trader's model on the next login or upload. Minors recompute on the next natural refresh. |
| What the trader sees | On a major: a diff, framed as improvement — "We improved our engine. What changed for you: one leak downgraded to Likely after a stricter post-loss test; your Process Score moved 58 → 55 because Execution is now measured against a hold-out." Old versions stay readable; scores are labelled with their version. |
| Running experiments | Never re-baselined mid-flight. An experiment completes on the framework version it started on, and its verdict is stamped with that version. If a major would change the primary metric, the trader is told the verdict will be computed on the original version and the model updates after. |
| Archiving | Every version of a trader's model is retained (subject to §19.4) with its version, inputs hash and diff — the journey log. |
| Process Score continuity | A major that changes the formula publishes a mapping note and shows both scores for one cycle. The published methodology is versioned like the engine. |
| Governance | A major requires: pre-registration of the change, a run on the synthetic and noise test-beds, a re-run of the gold standard, and the CEO's sign-off as ruler. Never shipped silently. |

## 9. The canonical data layer — DECIDED

- **Trade reconstruction is core infrastructure.** The **Canonical Trade Record (CTR)** — fills → positions → round trips (partials, scale-ins and scale-outs, multi-leg options, expiry settlements, fees, symbol changes, currency) → market-enriched event stream — is the layer every future PlusEV product uses.
- **The real input is Trader data × Market data × Temporal context.**

| Priority | Data | Reason |
|---|---|---|
| P0 | timestamp, instrument, side, quantity, entry, exit, fees, realised P&L | Minimum deterministic analysis |
| P0 | fills and order events where available | Round-trip and execution reconstruction |
| P0 | market context for covered instruments | Conditional diagnosis and edge analysis |
| P1 | equity, capital, leverage | Normalise risk and scale |
| P1 | stop, target, intended action | Execution and risk fidelity |
| P2 | journal, thesis, confidence, emotion | Human context where machine evidence is thin |

- **Import contract + intelligent mapping**, not "any CSV." Phase 1 supports the launch market's top broker exports plus one documented generic template. Data-quality scoring, missing-data handling and a retention policy are part of the record; quality is a diagnosis input, never a guess.

## 10. The diagnosis — flagship outputs — DECIDED

| The trader's question | Output | Design principle |
|---|---|---|
| Where do I stand? | The Mirror | Recognisable facts first; identity second |
| What is this costing me? | **Avoidable Loss** (Appendix A1) | Conservative, in his currency, as a share of his loss |
| Where do I win? | Edge Map | Contextual; broad → narrow |
| Where do I bleed? | Leak Map / No-Trade Zone + Cost of Behaviour | Loss prevention first; quantified |
| Why does this happen? | Trader States + hypotheses | Evidence first; confidence visible |
| Is my process sound? | Process Health + Process Score (Appendix A2) | The score never replaces the diagnosis |
| What should I do? | **Next Best Move** — every relevant prescription ranked; Replay; The Experiment | All computed, revealed by interest, the whole set adoptable |
| What is my trading identity? | DNA Card | Shareable, privacy-safe, consent-gated |
| What can't you tell me? | Not Enough Evidence Yet (§6.2) | Honesty as a feature |

- **Next Best Move — DECIDED (v1.4).** Every relevant intervention is scored (impact × confidence × actionability × relevance), replayed on his history, and ranked. The top move shows by default; the rest reveal as interest shows; the **whole route is visible from the start** so a trader with three leaks sees the programme, not a trickle.
  - **Where a move comes from — the direction of the logic matters.** The engine first establishes, under the Evidence Standard, which of his conditions carry positive expectancy and which carry negative. The rule follows: *operate inside the validated positive conditions, stay out of the validated negative ones.* It is a forward-facing instruction derived from validated facts — never the output of a search for whichever rule most improves his history.
  - **"Impact" is the validated effect — DECIDED (v1.4).** Impact in the ranking is the Finding's effect size as it survived the hold-out and the robustness set. **The replay's improvement never enters the ranking.** Choosing the rule whose replay looks best is curve-fitting a trader's past, exactly as freezing the best parameter of a sweep is curve-fitting a backtest; the Laws forbid it (Law 6, and "a monotone slope is a fitted point").
  - **Replay is illustration, not evidence — DECIDED (v1.4).** It shows what an already-validated Finding was worth: *"operating this way would have saved you at least ₹1.4 lakh."* It is labelled in-sample wherever it appears, it is a **ceiling rather than an expectation** — a deletion replay assumes the removed trades would not have been replaced, which a compulsive trader would have done — and it may never select, rank or promote a move.
- **The move stack — DECIDED (v1.4; supersedes the v1.3 one-primary rule at trader level).** He may adopt the **whole curated set**, because a trader facing ₹1.4 lakh of avoidable loss across three leaks should not wait through three sequential experiments to act on the second one. The constraint is overlap, not count:
  - **Moves on disjoint trade sets run in parallel.** Pause after losses, cap risk per trade, skip a negative session: post-loss and last-hour states collide on roughly 3% of trades, so each move's adherence and avoided cost stay separable.
  - **Moves on the same trade set are merged into one rule before being offered.** "Pause after two losses" and "fixed size after two losses" act on the same trades — and the Risk DNA finding says he sizes up *because* he just lost — so they become a single rule: *after two losses, wait 30 minutes, and return at normal size.* One rule, one adherence count, one avoided-cost figure. Two competing rules over one set of trades are never offered.
  - **Attribution is unaffected by how many he takes**, because both reported quantities are per-rule counts rather than statistical inferences: adherence is counted against each rule's own eligible occasions, and every avoided trade is assigned to exactly one rule by the same mutually-exclusive rule that stops Avoidable Loss double-counting overlapping leaks (Appendix A1).
  - **A sequenced programme** remains available where he prefers it, or where merging is not possible: the engine shows the order and why this one is first, with each move's replay.
  - **"Exactly one primary" now governs the pooled study** (§11.2). Traders adopting different bundles is the variation that pooled read needs, not noise in it.
- **The forward statement — DECIDED (v1.4), one permitted form.** The product may state the arithmetic implication of his own measured rates, conditionally and with the conservative estimate: *"your trades outside this condition averaged +0.12R and inside it −0.4R; if those rates hold, operating only outside it puts your average at +0.12 instead of −0.05."* Three rules bind it. The figure uses the **shrunk** estimate, never the raw one, because the condition we single out as his best is the one most likely to have been flattered by luck. The conditional — *if those rates hold* — is shown, not buried, and the monthly review is where he learns whether they still do. And the rule is always "stay out of the negative zone", never "trade more inside the positive one": concentrating into a narrow edge invites forced marginal setups, which degrades the very edge being protected. **This is a statement about his own process, never a forecast of returns or of the market** (§5.2, §19.2).
- **Avoidable Loss — frozen as the signature output; its mathematics are not frozen.** Appendix A1 is the method we commit to *test* — hierarchical attribution, a counterfactual baseline, the conservative bound — and Phase 0 validates it on synthetic traders with known ground truth before any trader sees the number. The output is Canon; the formula and its parameters are calibration items (§23.1).
- **The intervention library** is seeded by the ten archetypal stories in Workbook §11 — the revenge trader, the size-up-after-loss trader, the overtrader, the scared winner, the losing trader with a real edge, the profitable-but-fragile trader, the session trader, the high-volatility leverage trader, the prop trader who blew a funded account, the trader with no demonstrated edge. Each pairs a Finding type with the move it implies; the Research Specification carries them forward as pre-registered tests and risk-classified prescriptions (§11.4).
- **The MVP three (HYPOTHESIS, Phase 0 decides):** Avoidable Loss with its biggest leak · the edge worth protecting · Next Best Move with its replay.
- **Edge Map, broad → narrow:** time → regime → instrument → state; a dimension is added only when evidence supports it; minimum sample per cell.
- **Cost rules:** currency and % of equity always; R only when a stop exists; otherwise an inferred risk unit, labelled.

## 11. Research methodology — DECIDED

### 11.1 The Evidence Standard
Fact → Pattern → Hypothesis → Action → Validation. Every Finding carries sample size, effect size, confidence tier, stability, hold-out persistence, economic significance and actionability. Adversarial validation before promotion; false-discovery control across the thousands of conditions the engine can test; a bounded candidate space that grows only with evidence.

### 11.2 Experiments — amended in v1.4

**Two levels, and v1.3 confused them.** Efficacy is a population question; adherence is an individual question. The arithmetic that forces the split is in the header and in Appendix A3.

**At the trader level — what each experiment decides.**
- **The primary endpoint is the process metric:** did he follow the rule, counted against that rule's own eligible occasions. Readable in under three weeks at fifteen trades a week.
- **The secondary endpoint is the avoided-cost accounting:** the situations the rule kept him out of, priced at his own validated historical rates and stated as a conservative "at least" figure. The counting carries no sampling error; only the rate does, and it arrives with its interval from the diagnosis. It is **accounting, not proof that he improved**, and the copy says so.
- **The whole curated set may be adopted** (§10). Each move carries its own adherence count and its own avoided-cost figure.
- **ΔE is not the trader-level endpoint.** It is reported at his quarterly review once enough Reserve trades exist, and the pre-registration tells him so before the experiment starts, in his own words: *"we'll know in about six weeks whether you kept to this; whether it moved your numbers takes longer, and we'll tell you at your quarterly review."*
- **N is set by the measurement design** for the process endpoint — prevalence of the eligible state, baseline follow-rate, target follow-rate, power (Appendix A3). "The next 30 trades" is a consumer label only.
- **Verdicts are pre-registered:** PASS / PARTIAL / REFUTED with routing written before the start, each carrying a reason code so that "right but not worth it" and "wrong" are never conflated (Appendix A3).

**At the population level — what decides whether a move works.**
- **One credited primary per pooled study.** A move type's effect is established across traders, which needs 10–63 traders at 40–80 trades each rather than thousands of trades from one person.
- **Design:** randomisation among equally ranked prescriptions, staggered starts, adoption bundles recorded exactly, and matched comparison groups once the population exists. Traders adopting different bundles supplies the variation the study needs.
- **A move type that cannot earn a pooled pass leaves the library**, whatever its replays looked like.

**Causal rigor, unchanged in principle.** Baseline, intervention window, comparable period, regime adjustment, a process metric and an outcome metric; replay labelled in-sample throughout and never treated as evidence of effect (§10).

### 11.3 The Evaluation Framework

| Validation | Question | How |
|---|---|---|
| 1 Computation | Are the numbers right? | Unit and golden tests on the CTR and every metric |
| 2 Reproducibility | Same data, same Finding? | Deterministic runs; version-stamped, hashed |
| 3 Statistical defensibility | Survives the Evidence Standard? | Synthetic traders with planted behaviours (recall); pure-noise traders (false positives) |
| 4 Recognition | Does the trader say "that's me"? | Accurate / Not sure / Wrong; dispute rates per Finding type (§6.1) |
| 5 Intervention | Does behaviour change? | Adoption and adherence |
| 6 Persistence | Does improvement last? | Post-experiment windows; longitudinal DNA |

- **Expert gold standard:** independent traders and researchers diagnose anonymised histories blind; the engine is scored on precision, false-positive rate, agreement, actionability and user-confirmed accuracy.
- **Targets (HYPOTHESIS, calibrated in Phase 0):** user-confirmed accuracy ≥ 80% of Established Findings; expert agreement ≥ 70% on the top-three leaks; false positives on noise traders < 5%.

### 11.4 Intervention safety — the risk-envelope invariant — DECIDED (was a gap in v1.1; made precise in v1.3)

**No prescribed experiment may widen a trader's defined risk envelope, or require additional financial exposure, in order to generate evidence.** The envelope is his own, fixed before the experiment starts: risk per trade, maximum position and leverage, trades per day, and the maximum loss over the experiment window. We do not promise a market outcome — nobody can — we promise that no rule we give him asks him to risk more than he already does. This outranks every measurement objective, and it is Promise 9.

| Always permitted | Permitted with conditions | Never |
|---|---|---|
| Reduce size; cap risk per trade; cap trades per day; cooldown after losses; skip a No-Trade Zone; paper-trade a setup; record a stop or a plan; track a process metric | Exit-rule changes (hold to target, trail) — only when the replay shows no increase in modelled loss per trade and a stop is defined; a re-entry rule — only within the existing risk cap; a session or instrument change — only at equal or lower size | Increasing size, leverage, frequency or exposure; widening or removing a stop; testing scaling behaviour by risking more; any rule whose expected risk per trade exceeds his current baseline |

- **The screen, before any experiment starts:** current risk per trade, risk per trade under the rule, and the maximum loss over the experiment window under the rule — with the rule blocked if the second exceeds the first.
- **Uncertain-risk rules are not offered.** If the replay cannot bound the risk change, the prescription stays in the library and is never surfaced as a move.
- **Standing stop rule.** Any experiment auto-terminates if his drawdown in the window exceeds a pre-set fraction of the pre-experiment baseline, or if adherence collapses — and the product says so plainly: "We're stopping this experiment. Your drawdown is beyond where we should be testing anything."
- **Audit.** Every prescription in the library carries a risk classification from this table, reviewed by the in-house trader and the research lead before it may be prescribed.

## 12. The show — the product experience — DECIDED (principles) · HYPOTHESIS (the mechanism)

**What is frozen here, and what is a hypothesis.** Frozen: the principles — low cognitive friction, a rapid first aha, progressive depth, insight density on every screen, strength before leak, never shame, animation as evidence, the DNA Map, the two clocks, and the bound on the reveal engine (Law 11). HYPOTHESIS, calibrated in Phase 0: **six** as the screen count, the exact arc in §12.4, "under five minutes," and the interest engine's ranking method. If Phase 0 shows that screens 3 and 4 should merge, the arc changes and the principle does not. Canon 10 names six screens because six is the current design; what the Canon freezes is the show as the product, not the count.

**The Phase 1 minimum.** A rules-based reveal from a small signal set — dwell, drawer opens, Accurate / Not sure / Wrong, "show me more," skips — over material computed before the show. A learned ranking is built only if Phase 0–1 evidence shows that revealing by interest materially lifts acceptance or adoption over a fixed order; the interest engine's own scorecard (§18.4) is the test, and an engine that cannot beat a fixed deck is not built. The two clocks stay: the evidence clock is non-negotiable because it protects the numbers; the reveal clock is honoured by rules before it is honoured by a model.

### 12.1 Properties (P-1 … P-6, restored)
P-1 north-star value on every screen, using the highest form of intelligence · P-2 easy to read and grasp · P-3 engagement and a growing exchange · P-4 built for short attention spans · P-5 brand consistency from day one · P-6 modern design and animation where the animation *is* the evidence. Plus: insight density on every screen; evidence inspectable down to the trades; Accurate / Not sure / Wrong on every Finding.

### 12.2 Format and presentation technique
- **Format.** A vertical, story-style narrative — swipe or scroll — web, mobile-first. Six screens in the doormat (the current design hypothesis; the principles above are what is frozen); each screen one cognitive job: claim → evidence → implication → optional action → confidence → feedback.
- **The hook.** Screen one is the Mirror. Screen two is the Surprise with Avoidable Loss counting up, and the promise of what follows.
- **Animation as evidence.** Charts draw themselves; the trades behind a claim light up on the timeline; the cost counts up; the No-Trade Zone shades in over his real trades. Nothing moves that is not evidence.
- **The DNA Map.** A persistent mini-map: the four DNAs as regions, his position, the terrain, the route, the journey. It fills in as screens are revealed; in the subscription it is the home screen.
- **The computation stage.** Specified in §12.6.
- **The evidence drawer.** Every claim opens to the trades, slices and hold-out.
- **Two clocks.** The **evidence clock** runs before the show: reconstruction, enrichment, the pre-registered library, validation, the Process Score, Next Best Move and the replays of the top moves — no number produced under time pressure. The **reveal clock** runs while he reads (§12.3). The founding rule — the user never waits — holds on both.
- **Pacing.** Three or four points a screen at most; one visual; one action. First aha under three minutes from upload (HYPOTHESIS).

### 12.3 The interest engine — computed while he reads
- **Signals:** dwell, scroll speed, skips, drawer opens, Accurate / Not sure / Wrong, "show me more," "explain this," replays watched, saves, shares — and, for a returning trader, earlier sessions.
- **Computed live:** the next screen selected and narrated; the second and third moves' replays prepared while he reads the first; a drill-down computed on demand from the precomputed record, within the fixed protocol, returning "Not enough evidence yet" when a slice is too small.
- **How responses change the plan:** Accurate promotes the moves tied to that Finding; a dispute pulls evidence forward and demotes dependent moves (§6.1); heavy "explain this" shifts vocabulary plainer; no execution problems means no execution screens.
- **The bound (Law 11):** live computation may select, order, deepen and narrate; never create a Finding, alter a number already shown, or bypass validation.
- **Ask timing:** only after value has landed; low-friction early; never before the first aha.

### 12.4 The doormat arc — six screens, under five minutes (the beliefs are DECIDED; the count and the arc are the HYPOTHESIS Phase 0 calibrates)

| # | Screen | Belief | Mechanic | Reveal-more |
|---|---|---|---|---|
| 1 | Mirror | "This understands my trading." | Recognisable facts, a visual snapshot, probabilistic identity, the DNA Map appears | Full snapshot stats |
| 2 | Surprise + Avoidable Loss | "It found something I did not know — and it matters." | One Established pattern; the cost counting up; the avoidable share; the promise | The trades behind it; the state |
| 3 | Your edge | "I know where my process works." | The strength worth protecting — or an honest no-edge-yet (§6.2) | Edge Map one dimension deeper |
| 4 | Your biggest leak | "I know what destroys it." | Leak Map lite; mechanism shown observably; Process Health | Other leaks ranked; Trader States |
| 5 | Next Best Move | "I know what to do, I can see what it would have saved me, and I know what I'll be shown next." | The ranked set — top move expanded — each with its Replay as illustration, the risk screen (§11.4), the conditional forward figure, the protocol, "start tracking" | The rest of the set, ranked, with their replays |
| 6 | Exit | "I trust PlusEV and want it to keep working." | DNA Card with Process Score, save by email, continue / connect | — |

### 12.5 The subscription arc — DECIDED (was a gap in v1.1)

The home screen is the **DNA Map**: four regions, his position, the active route, the journey line. Everything below hangs off it. The arc is adaptive, not a fixed deck — modules are ordered by the same priority as Findings, and a module with nothing to say is not shown.

| Module | What it holds | When it surfaces |
|---|---|---|
| **DNA Map (home)** | Position, Process Score with sub-scores and band, active experiment, last diff | Always |
| **Your edge** | Edge Map, drill-downs, strength to protect, regime sensitivity | Always |
| **Your leaks** | Leak Map / No-Trade Zone, Avoidable Loss trend, Trader States | Always |
| **Next Best Move** | The ranked live list with replays, risk classification and why-this-order | Always; re-ranks after every verdict and upload |
| **The Experiment** | Protocol, adherence, progress against criteria, the pre-registered verdict, history of past verdicts | While one is active; otherwise the last verdict |
| **Findings library** | Every Finding by DNA and tier, with evidence drawers, disputes and their outcomes | Always |
| **Ask your DNA** | Grounded conversation over the registry (Phase 2) | Always, Phase 2 |
| **Weekly review** | §12.7 | Weekly |
| **Monthly DNA** | §12.7 | Monthly |
| **Benchmarks** | "Traders like you," consented and anonymised | Phase 3 |
| **Data & trust** | Connections, consent ledger, export, delete | Always |

### 12.6 The computation stage — technical specification — DECIDED (was a gap in v1.1)

It is theatre driven by real events, never a fake progress bar. The pipeline emits a typed event per stage; the UI renders what it receives.

| Stage | Event payload | Typical time |
|---|---|---|
| Parse & map | rows read, columns mapped, quality flags | < 2 s |
| Reconstruct | fills in, round trips out, unresolved positions | 2–10 s |
| Enrich | trades enriched, instruments covered, context gaps | 5–20 s |
| Features | feature count | < 5 s |
| Research | tests run, candidates raised — streamed as they complete | 10–40 s |
| Validate | candidates killed, survivors, by reason | 5–20 s |
| Model & score | DNAs built, Process Score with band | < 5 s |
| Moves | prescriptions scored, replays run, ranked | 5–20 s |

- **Target: under 60 seconds** for a 500-trade history; the trader sees real counts throughout ("212 tested · 207 killed · 5 survived").
- **Honesty rule:** the numbers on screen are the real counts. If a stage is fast, it says so; the stage is never padded to look impressive.
- **Failure handling.** Partial failure degrades rather than aborts: no market context → the affected tests are skipped and the trader is told which parts are unavailable and why. Reconstruction failure is the one hard stop — with the specific rows that failed and a fix-and-retry path. Timeout → the diagnosis is completed asynchronously and delivered by email, with the arc resuming where it stopped. Every failure is logged with the input hash for replay.
- **No fabricated progress.** If the backend is silent, the UI holds; it does not animate forward.

### 12.7 Retention rituals — DECIDED (was a gap in v1.1)

| | **Weekly review** | **Monthly DNA** |
|---|---|---|
| Purpose | Keep the active experiment alive | Show the journey |
| Contents | Experiment progress against pre-registered criteria; adherence (process, never P&L praise); trades in leak states this week; any new Exploratory pattern; one line of market context where it explains the week | The DNA diff (what changed and why); Process Score and sub-score movement with the band; verdicts closed this period; Avoidable Loss trend; the re-ranked Next Best Move; a refreshed DNA Card |
| Delivery | In-app module + a short email; opening it is an interest signal | In-app + email + the Card, built to share |
| Personalisation | Sections ordered by the interest engine; sections with nothing to say are omitted rather than padded | Same; the diff leads |
| Guardrail | Never nags, never celebrates P&L, never manufactures an update — "nothing material changed this week" is a valid review | Same |

### 12.8 Emotional design and vocabulary
Never shame. Strength before leak. "Your behaviour," not "you." Cost → mechanism → fix; every leak ends with a next best move. Celebrate process, not P&L. Write for the losing majority with respect — they are the market.

**The vocabulary is the positioning.** Words we use: behaviour, pattern, consistent with, evidence, confidence, experiment, process, move, map. Words we never use: disease, cure, psychology as a claim, tilt, emotional, guarantee, signal, call, tip. The full list lives in Workbook §13 and moves to the Experience Specification as the narration layer's lexicon; the faithfulness check (§8.3) enforces it alongside the numbers.

### 12.9 Narrative user story
Ravi, 34, trades Nifty and Bank Nifty options: 420 trades over eight months, net −₹2.1 lakh. He uploads his tradebook; four columns confirmed in one click; the computation stage reconstructs 1,140 fills into 420 round trips, tests 212 hypotheses, kills 207, and reports five survived. The DNA Map appears and fills.
- **Mirror:** 420 trades; 68% in the first 90 minutes; median hold 14 minutes; 71% Bank Nifty; win rate 44%; average winner 1.3× average loser. He nods.
- **Surprise + Avoidable Loss:** after two consecutive losses his next trade comes within six minutes in 62% of cases, at 1.7× normal size, expectancy −0.4R versus +0.1R otherwise (n = 71; held across instruments and his last 100 trades). The counter stops at **₹1.4 lakh, stated as "at least"** — about two-thirds of his loss. Established. He opens the drawer and sees the 71 trades.
- **Your edge:** Tuesday-to-Thursday first-hour breakouts with a defined stop, +0.35R over 96 trades, held in the hold-out. Likely. Worth protecting.
- **Your biggest leak:** the post-loss re-entry, shown as time-to-next-trade, size ratio and conditional expectancy. Process Score 41 (band 36–46), Behaviour sub-score 22. Not a word about anger. He taps *Not sure* on a secondary Finding; the drawer opens with its trades, and the Finding is flagged for review rather than defended.
- **Next Best Move:** three rules, shown as one route. **One:** after two losses, wait 30 minutes and return at normal size — the pause and the sizing merged, because the evidence says he sizes up *because* he just lost. **Two:** cap risk per trade at his own median. **Three:** skip the last hour, where his expectancy is −0.2R. The risk screen shows risk per trade unchanged or lower on all three. Replay, labelled as illustration on his own history: *operating this way would have saved you at least ₹1.4 lakh.* And the forward line: *your trades outside these conditions averaged +0.12R; if those rates hold, staying out of them puts your average there instead of −0.05R.* He adopts all three — they act on different trades, so each is tracked on its own. Tracking: his next 40 trades; each rule's success is its own follow-rate ≥ 80%; auto-stop if drawdown exceeds the pre-set bound.
- **Exit:** DNA Card — *Breakout-leaning · post-loss leak · Process Score 41* — and one ask: an email to save the report.
Six weeks later, 58 trades in: **the pause rule — 11 of 12 post-loss moments, no trade. The risk cap — 55 of 58 trades inside it. The last hour — skipped on 9 of 10 days.** Avoided, at his own rates: **at least ₹31,000**, broken out per rule. His Process Score moves 41 → 58 (band 53–63) because the Findings behind it have changed state, and DNA v1.1 marks the post-loss leak *contained*. What the product does **not** claim is that his expectancy improved: 58 trades cannot carry that, and the screen says the quarterly review is where it gets read. What it does say is that across 40 traders running the same pause rule, the pooled estimate is +0.14R — so the rule he kept to is a rule that works. He subscribes because the system understood him before it asked, and then showed him he had actually changed.

## 13. Value exchange and growth — DECIDED

| Stage | Value unlocked | Ask (with its product reason) |
|---|---|---|
| Before upload | The promise and the Trader Promise | None |
| After the first Finding | Personal relevance | Optional name |
| After the diagnosis | Save and return | Email |
| When a sharper diagnosis is possible | Better Risk and Execution DNA | Stops, intent, equity (optional) |
| When continuous analysis is valuable | Live, longitudinal DNA | Read-only broker connection |
| When alerts solve a real problem | Real-time protection | Notification permission — phone only if an alert product exists |
| When recurring value is proven | Continuous intelligence | Subscription |

- Rules: every ask has a product reason; no ask that only benefits PlusEV; the first aha is never behind registration; the subscription is capability revelation, not a paywall.
- **DNA Card:** probabilistic archetype, edge signature, one strength, one leak, the Process Score; no P&L unless he chooses; consent-gated.
- **Funnel:** Visitor → Upload → First aha → Trust → Finding accepted → Next Best Move → Experiment → Return → Subscription.
- **Distribution as mechanisms:** the DNA Card; the monthly DNA; educators and creators as the first channel; prop firms and communities; public research from consented aggregates; referral by comparison.

## 14. The learning loop and longitudinal DNA — DECIDED

| Step | System behaviour | Record |
|---|---|---|
| Observe | Detect a repeatable pattern | Finding |
| Prioritise | Rank every relevant intervention | Next Best Move |
| Prescribe | Replay; classify risk; write protocol, criteria and routing | Experiment |
| Run | Observe trading; track adherence; watch the stop rule | Behaviour + market context |
| Measure | Compare against the pre-registered baseline | Verdict and outcome metrics |
| Update | Change confidence and DNA state | New model version + diff |

Longitudinal DNA: initial → 100 trades → month 3 → 6 → 12. The diff is the retention email and the journey log on the Map. The **intervention-outcome dataset** is the asset that compounds (§17).

## 15. Business model and platform path

| Layer | Promise | Role | Status |
|---|---|---|---|
| Trade DNA (doormat) | Understand yourself from your own trades | Free acquisition and trust | DECIDED |
| Longitudinal DNA (subscription) | PlusEV keeps learning about you | Recurring revenue | DECIDED |
| Platform | Intelligence turned into tooling | ARPU and retention | Scope UNKNOWN (Phase 3) |
| B2B | Prop firms, brokers, educators | Distribution and enterprise revenue | HYPOTHESIS (§15.4) |
| Capital | Validated trader intelligence meets capital | Governed expansion | PARKED (Phase 4) |

### 15.1 Cost to serve — HYPOTHESIS
The deterministic engine costs pennies per report; narration and explanation cost cents; market-data licensing is the real cost line and depends on the launch market.

### 15.2 Pricing hypotheses
India ₹999–1,999 / month (intelligence) and ₹3,999–4,999 / month (pro); global $19–29 and $79–99; prop-firm seats; enterprise API. India is volume and brand; B2B and global are ARPU.

### 15.3 Willingness-to-pay test plan — DECIDED (was a gap in v1.1)
- **Phase 0 (qualitative, n = 20–50):** after the concierge report, **Van Westendorp** four questions (too cheap / cheap / expensive / too expensive) plus one commitment question — "if this existed on Monday at ₹X, would you subscribe today?" — asked at a price randomised per partner. Output: an acceptable range and the value drivers in their words.
- **Phase 1 (quantitative, n ≥ 200 doormat completers):** **Gabor-Granger** on the two strongest tiers to build a demand curve and locate the revenue-maximising point, with a reservation-price question for the pro tier.
- **Phase 2 (live):** two price points A/B-tested at launch, held for a full billing cycle, measured on conversion **and** 90-day retention — never conversion alone, because a price that converts and churns is worse than one that does neither.
- **Guardrails.** No discount that cannot be sustained; no price experiment on existing subscribers; India and global priced independently; B2B seats priced from value delivered per trader, not from consumer ARPU.

### 15.4 B2B go-to-market — DECIDED (was a gap in v1.1)
- **Target, in order:** prop firms (the sharpest pain — they lose money when funded traders blow accounts, and they have no process model); then educators and creators (proof their students improve; also the consumer acquisition channel); then brokers (retention and engagement; the slowest sale and the largest data agreement).
- **The pitch to prop firms:** *evaluate and develop on process, not only on P&L targets.* Which candidates are lucky-but-fragile; which funded traders are in a known leak state before the account breaks; before/after Process Score across a cohort.
- **Proof before scale:** one paid pilot with one mid-size prop firm — 50–200 traders, a fixed fee, a 90-day term, and one pre-registered outcome (for example, a reduction in rule-breach rate or in accounts lost to a single behavioural state). Publish the result with their consent; that case study is the sales asset.
- **Packaging:** per-trader seats with volume tiers; a dashboard first, an API later. Never a white-label before the PlusEV brand exists in the market (§23.3).
- **The line we do not cross:** the trader's individual diagnosis belongs to the trader. A firm sees what its trader consents to share. No surveillance product, however well it would sell.

### 15.5 Capital and hiring — HYPOTHESIS · UNKNOWN
- **Phase 0–1 are self-fundable** on the current team plus one or two hires; the real costs are data licensing and time.
- **The milestone that would justify a raise** is not a finished product but a proven engine: Phase 1 launch criteria met and an early retention signal from Phase 2. Raising before the engine is proven buys pressure to ship the show without the brain.
- **Use of funds, if raised:** the research and data team, market-data licensing for the launch instruments, compliance and counsel, and the first distribution spend — in that order.
- **Fallback:** the B2B pilot and the subscription fund Phase 2–3 at a slower pace. The thesis does not require external capital to be true.
- **Hiring sequence.** Phase 0: research lead (statistics and behavioural inference) and data engineer (CTR) are the two that cannot be borrowed; product, design and counsel fractional; the in-house trader part-time. Phase 1 adds a full-stack engineer for the show and moves design to full-time. Phase 2 adds a second engineer, support, and B2B ownership. In-house always: the research engine, the CTR and anything touching trader data. Outsourceable: brand, illustration, marketing, parts of the front-end. Budget and location sit with the CEO, set at the Phase 0 kickoff.

## 16. Competitive position — HYPOTHESIS, to validate

**Verified 29 September 2026** by direct search [F5–F10]. This table is provisional until the category study; nothing in it is repeated as fact in a deck or a sales page, and "what we have not seen them do" is never restated as "what they cannot do."

| Who | What they do | What we have not seen them do | Structural reason |
|---|---|---|---|
| **tradedna.in** — Indian F&O journal | Post-trade behavioural analytics for NSE/BSE F&O: revenge trading, tilt, overtrading found from the tradebook; Indian charge engine (STT, stamp duty, SEBI fees); data resident in Mumbai; explicit "no buy/sell signals" compliance posture | An evidence standard with confidence tiers; market-context reconstruction; replay and pre-registered experiments; a longitudinal model; population priors | Built as a journal with behavioural tagging; the closest competitor in our launch market and the sharpest reason our differentiation must be the loop, not the insight |
| **TraderDNA** | Journal that reads patterns, flags mistakes, names where the edge is; archetype assessment; dashboard widgets; AI coach on your data; Telegram alerts | Same list | Journal economics; insight without validation |
| **Edgemap** | Upload a broker CSV; reads the whole history; day-of-week and session breakdowns; post-loss behaviour tracking; free journal, paid AI coach | Same list | Same |
| **EdgeGhost** | Futures journal that reconstructs trades and sessions automatically from NinjaTrader and Tradovate fills; behavioural insights from execution data | Same list | Notable: fill-level reconstruction is not unique to us — the CTR is table stakes, not the moat |
| **Arxion** | "Trader DNA Profile" — behavioural profile across patience, risk, execution, discipline, consistency, from trade history and journal, via a consistent rubric | Statistical validation, experiments, longitudinal proof | Rubric scoring, not inference under an evidence standard |
| **trade-dna.com** | "Trade DNA™" psychology questionnaire → archetype, risk framework, development plan | Anything computed from real trades | Questionnaire product |
| Broker-native analytics | Free, in-app, accurate fills | Descriptive; single-broker; conflicted | Brokers earn on activity |
| Prop-firm dashboards | Targets, rule breaches | Evaluation, not development | Built for the firm's risk |
| AI chat over a CSV | Fast narrative | Invented numbers; no validation; no memory | No deterministic engine or registry |
| Human coaches | Judgment, empathy | Expensive, unscalable, unvalidated | Human time |

- **What this changes.** "Upload your trades, find your post-loss leak" is no longer a claim only we can make — in India it is already on sale. The differentiation hypothesis is therefore **not** the insight but the loop and the standard behind it: *evidence with confidence tiers → diagnosis → ranked next best move → replay → risk-bounded pre-registered experiment → measured improvement → updated model*, backed by fund-grade research discipline and published evaluation results.
- **Unverified.** An earlier review cited Hygentra as having launched a Trader DNA capability. A search on 29 September did not surface it; the claim is unverified and sits in the category study, not in this table.
- **Study plan:** a 30-day category study; sign up for and use the three closest products; ten interviews with their users; a feature-by-feature audit against our loop; quarterly refresh.

## 17. Moat — HYPOTHESIS, ordered by defensibility
1. The intervention-outcome dataset — what works for which trader under which conditions.
2. The confirmation dataset — trader-confirmed and disputed labels at scale (§6.1).
3. **The measurement layer** — a scored, lineage-tracked record of which of our own components actually produce improvement (§18.2–18.5). It compounds silently and it is the hardest thing on this list to start late: a competitor can copy a feature, but not five years of knowing which of their own components work.
4. Population-informed estimation that rescues weak individual samples.
5. Longitudinal Trader Models and decision histories.
6. A validated pattern library with promotion rules.
7. Canonical trading-data and market-context infrastructure. *(Downgraded from first in v1.1: EdgeGhost shows fill-level reconstruction is achievable by others. Necessary, not sufficient.)*
8. The Trade DNA ontology and evidence registry.
9. Brand trust in a published Evidence Standard and published evaluation results, including accuracy net of upheld disputes.
10. The Process Score as a candidate category standard, with a published methodology.
11. Fund-derived research discipline and market knowledge, under strict governance and separation.

## 18. Metrics and the Measurement Layer — DECIDED

### 18.1 Product metrics

- **North Star — Trader Improvement.** Specified mathematically in **Appendix A3**.

| Layer | Measures |
|---|---|
| North star (v1.4) | **Share of move types with a pooled pass**, and **share of traders meeting their process threshold**; ΔE per Appendix A3 at the quarterly and pooled reads; Avoidable Loss reduced. Never an average of ΔE across traders, which the largest accounts would dominate |
| Activation | Upload completion → first verified Finding → six screens completed |
| Trust | Accurate / Not sure / Wrong rates; dispute outcomes; drawer opens; "explain this" use |
| Action (v1.4) | Moves adopted per trader out of the set offered; adherence per rule; avoided cost accrued |
| Learning (v1.4) | Pooled reads completed per move type; verdict distribution with reason codes; move types retired for failing their pooled read |
| Retention | Return with new data; monthly DNA opens; weekly review opens |
| Growth | DNA Card shares; referral rate; educator and prop-firm channel volume |
| Commercial | Free → paid conversion; subscription retention; B2B adoption |
| Guardrails | Nothing rewards more screens, more asks or more P&L volatility; P&L alone is never the score; no metric may be improved by withholding value |

### 18.2 The Measurement Layer — what it is and why it is the differentiation

Every competitor we verified can tell a trader what is wrong with his process. We have not seen one that can say what is wrong with its own. **PlusEV turns its own research discipline inward: every engine, model, Finding type, screen, move, ritual and narration template states an objective and is scored against it.** The same reason a trader needs Process Health rather than P&L — outcomes are noisy, process is diagnosable — applies to us.

Three commitments define it:
- **Objectives before scores (Law 12).** Nothing ships without a one-sentence, measurable objective. The definitions are where the intelligence goes; the arithmetic afterwards is easy.
- **Human-decided (Law 11, extended).** A score is an input to a human decision. No score automatically promotes, demotes, reorders or retires anything a trader sees. An auto-optimising show is an engagement-bait machine with no brake, and it would break runner ≠ ruler.
- **Every objective traces to the North Star.** A component's objective must state how it contributes to a trader measurably improving. A component that cannot answer that question is decoration, and the definition exercise is what exposes it.

### 18.3 Two kinds of score, never conflated

| | **Correctness** | **Utility** |
|---|---|---|
| Question | Is it right? | Did it help? |
| Ground truth | Synthetic traders, golden datasets, replay, the gold standard | The North Star, via validated proxies |
| Feedback | Instant, deterministic, cheap | Delayed, sparse, confounded |
| Applies to | CTR, features, every test, Process Score, Avoidable Loss, narration, "explain this" | Findings, screens, moves, the show, the rituals, the interest engine |
| Available from | Phase 1 — needs no users at all | Phase 2+, when the population can support it |

Conflating them is how a team "improves" a screen that is beautiful, engaging and wrong. Every component scorecard names which kind it carries; most carry both.

### 18.4 The component scorecards — the definitions

Each component type has: an **objective** (one measurable sentence), the **score** it is judged by, its **guardrails** (which cannot degrade while the score rises), its **link to the North Star**, and its **minimum sample** before the score is read at all. These definitions are living and owned — the research lead owns engine and Finding definitions, product owns screen, move and ritual definitions — and each is versioned like the framework.

| Component | Objective (what it is *for*) | Score | Guardrails | North-Star link |
|---|---|---|---|---|
| **Reconstruction (CTR)** | Turn a broker export into what the trader actually did, losing nothing and inventing nothing | Correctness: round-trip fidelity against hand-verified truth; unresolved-position rate; fee accuracy | No silent drops; quality flags always surfaced | Everything downstream is wrong if this is wrong |
| **Market enrichment** | Attach the market state that makes a behaviour conditional rather than absolute | Correctness: coverage rate, point-in-time accuracy (no look-ahead). Utility: Findings-per-trader with enrichment minus without | Zero look-ahead; gaps declared, never imputed | Conditional Findings are the ones traders act on |
| **A single test in the library** (e.g. post-loss re-entry) | Detect one specific, mechanistically plausible leak or strength with enough power to act on | Correctness: recall on synthetic traders with that behaviour planted; false-positive rate on noise traders. Utility: promotion rate, trader-confirmation rate, dispute rate, adoption rate of its moves, and PASS rate of experiments born from it | Dispute rate below its pre-registered ceiling; no drift in false positives after a version change | A test whose Findings never produce a PASS is a test that does not help anyone |
| **Validation engine** | Kill everything that cannot survive the trader's own hold-out and a perturbation | Correctness: false positives on noise traders near zero; stability of promotion decisions on split histories | Recall must not fall while precision rises — over-killing is also failure | Wrong Findings destroy trust faster than missing ones |
| **Risk DNA** *(and each of the four DNAs)* | **Risk DNA:** determine how much risk this trader takes, how it changes with state and outcome, and what that costs him — well enough that a risk prescription can be written and measured | Correctness: sizing and drawdown reconstruction against hand-verified accounts; inferred-risk-unit accuracy where no stop exists. Utility: share of traders for whom it produces at least one Established Finding; confirmation rate; PASS rate of risk-class experiments; contribution to Avoidable Loss explained | Coverage must not be bought with weak Findings; the sub-score band must stay inside its width ceiling | Risk behaviour is the largest single source of avoidable loss in retail trading (HYPOTHESIS — Phase 0 tests it) |
| **Process Score** | Compress the diagnosis into one honest, comparable number without ever replacing it | Correctness: test–retest stability on split histories; convergent validity against the gold standard; gaming resistance. Utility: predictive validity — does a higher score at T predict lower avoidable loss at T+1 | Band width ceiling; no score without a band; comprehension in interviews | It is the number the category may adopt — but only if it predicts something |
| **Avoidable Loss** | Give the trader the true, conservative cost of what he could have avoided | Correctness: never exceeds planted cost on synthetics; recovers ≥ half of it; zero on noise traders. Utility: "does this feel fair" rate; its effect on progression past screen 2 | Fairness rate above floor — a number read as an accusation has failed even if it is right | It is the hook; a hook that feels unfair loses the trader before any move |
| **A Finding type** | Tell the trader something true, non-obvious and actionable about himself | Confirmation rate, non-obviousness rate, dispute rate, action rate, and downstream PASS rate | Non-obviousness cannot be traded for confirmation (telling people what they know scores well and helps nobody) | A Finding earns its place by changing what he does |
| **A screen** | Do one cognitive job: produce one specific belief in the trader | Utility: belief-formed rate (asked in Phase 0, proxied in Phase 1 by progression and drawer opens), drop-off rate, time-on-screen against intent | Progression must not be bought with drop-off elsewhere; engagement is never the score alone | The doormat proxy chains to improvement |
| **The show (end to end)** | Take a stranger from upload to trust to an adopted move in under five minutes | Completion rate, first-aha time, Finding-acceptance rate, move-adoption rate | No component of it may improve by withholding value (Law 11) | It is the only path to the loop |
| **The interest engine** | Reveal what this trader most needs next, sooner than a fixed deck would | Utility: does a revealed-by-interest order beat a fixed order on acceptance and adoption, in a controlled comparison | Dispute rate, drawer use and ask-refusal rate must not rise; no reveal decision may withhold a Finding he would have seen | Better ordering should show up as more moves adopted, not more taps |
| **A prescription (move type)** | Change one behaviour, inside the trader's risk envelope, with a measurable effect | Utility: adoption rate, adherence rate, PASS rate against δ_min, mean ΔE when passed, persistence after the window | Risk classification must hold; no move may widen the envelope (§11.4) | This is the North Star, directly |
| **Narration / "explain this"** | Explain a Finding at the trader's level without adding a single unsupported number | Correctness: faithfulness pass rate (must be 100% to ship), refusal correctness on the adversarial suite. Utility: comprehension, "explain this" re-ask rate | Zero unresolved numbers; no scope violations | A true Finding he does not understand is not a Finding he can act on |
| **Weekly review / monthly DNA** | Bring him back to an experiment he is running, or to a model that changed | Open rate, return-with-data rate, experiment-completion lift versus no-ritual control | Never nags; "nothing material changed" must be an acceptable output | Completion is what produces a verdict |

### 18.5 The credit chain — what makes RCA a query instead of an investigation

Scores without lineage cannot explain anything. Every output carries the IDs of everything that produced it:

```
upload_id → ctr_version → enrichment_version → test_id @ framework_version
  → finding_id (tier, confirmation, dispute_state)
    → screen_id @ reveal_position, narration_template_id
      → move_id (risk_class, replay_result)
        → experiment_id → verdict, ΔE, adherence
```

Every event — a screen shown, a drawer opened, a label given, a move adopted, a verdict reached — is logged against that chain. Then RCA is a query: *the experiments that failed last quarter — which tests produced their Findings, at which framework version, on which screen, in which narration template, for which archetype?* And the same chain answers the opposite question: *what produced our passes?*

**Sequencing, and this is the part that cannot be deferred:** the chain is instrumented in **Phase 1**, because retrofitting lineage is brutally expensive, while scores on 50 Phase 0 traders are noise. Correctness scorecards also start in Phase 1 — they need synthetic traders, not users. Utility scores switch on in Phase 2 as volume allows, each with its minimum sample declared in advance.

### 18.6 The three dangers, and the guards

- **Goodhart.** A score becomes a target and the component games it. Guard: every utility score is **paired with guardrails** from the table above, and a component that improves while a guardrail degrades is recorded as a **regression**, not an improvement.
- **Unearned proxies.** A screen's nearest measurable outcome is progression, not ΔE. Guard: a proxy must be **validated against the North Star before it is trusted**, and re-validated each year; a proxy that stops predicting improvement is retired rather than optimised. Proxies are earned exactly like Findings.
- **Name collision.** The trader's Risk **sub-score** (Appendix A2) and our Risk module's **quality score** must never share a name or a screen. Internal component scores are never shown to a trader and never used to rank what he sees.

### 18.7 The review ritual

A monthly **measurement review**: every component's scorecard against its objective, every guardrail breach, the RCA queries for the period's failures, and a decision list — keep, fix, re-define the objective, or retire. The CEO rules it, as with the fund's research. Correctness results are published from Phase 1 (§17); utility scores stay internal until the loop is proven.

## 19. Trust, security, regulation — DECIDED

```
PlusEV Platform Entity ── no individual trade access ──▶ Trade DNA Data Environment
                                                              │ governed, consented aggregates only
                                                              ▼
                                                        Research / Model Layer

PlusEV Fund ── independently controlled ──▶ Investment data          (no path from Trade DNA data to the fund)
```

### 19.1 The wall
Entity-level: legal, technical and organisational controls together — separate infrastructure accounts; encryption at rest and in transit; role-based least-privilege access with audit logs; no individual data to the fund; aggregates only with consent and anonymisation; independent audit at scale. Read-only connections. Every Finding traceable to evidence, methodology and version. Public promise: we never trade against you and never sell your flow.

### 19.2 Jurisdiction — UNKNOWN → counsel
India: the DPDP Act, SEBI's investment-adviser and research-analyst regulations, exchange data licensing. EU: GDPR. US: investment-advice boundaries. **Posture:** process observations and experiments on the trader's own behaviour; Next Best Move is always a process rule, never a trade; counsel review before launch in each jurisdiction.

### 19.3 The consent ledger — DECIDED (was a gap in v1.1)

| Question | Rule |
|---|---|
| What is recorded | One row per consent event: purpose, scope, terms version, timestamp, method, and the exact wording shown |
| Which purposes are separable | (a) process my data to produce my diagnosis — required for the product; (b) retain my model between sessions; (c) use my anonymised data in population priors; (d) include my anonymised data in published research; (e) share a named summary with a third party (a prop firm or educator); (f) marketing contact. Each is opt-in independently; (a) is the only one without which the product cannot run, and refusing any other never degrades his diagnosis |
| How it is captured | Explicit, unbundled, per purpose, at the moment the purpose becomes real — never a single tick-box at signup |
| Withdrawal | One screen, any purpose, any time, effective immediately for future processing; withdrawing (c) removes him from future prior computations |
| Audit | Append-only, versioned, exportable; the trader can see his own ledger; deletion requests and their completion are rows in it |

### 19.4 Deletion — DECIDED (was a gap in v1.1)

| Deleted on request | Retained, and why |
|---|---|
| Raw uploads and the CTR | Consent-ledger rows and the deletion record itself — legal proof the deletion happened |
| All Findings, the Trader Model and every version | Irreversibly anonymised aggregates already incorporated into published research or population priors, where no individual can be re-identified — stated plainly before he confirms |
| Experiments, verdicts, replays | Financial and tax records where law requires, for paid accounts only |
| Feedback and dispute labels tied to his identity | — |
| Account, contact details, connections (revoked first) | — |

- **Timeline:** live systems within 7 days; backups within 30; a confirmation email that names what was removed and what was retained, with the reason.
- **Verification:** he can request a post-deletion export, which returns only what was lawfully retained.
- **Population priors:** his contribution is removed from the next recomputation. Priors are recomputed on a schedule, so the removal is real but not instantaneous — and the deletion confirmation says so.
- **Anonymisation is not a loophole:** if a cohort is small enough that anonymisation is doubtful, his contribution is dropped rather than kept.

### 19.5 Language models
A hosted frontier model composes and explains from evidence objects only; automated faithfulness checks; no fine-tuning on user data without consent; the deterministic engine is built in-house.

## 20. Technology stance — DECIDED (choices marked "or equivalent" are the team's to finalise)

- **Principles.** Deterministic, reproducible core (hashed inputs, versioned outputs); AI at the interface (§8.3); an evaluation harness in CI; privacy by design; one canonical data model; two clocks; the show as a server-driven, procedurally generated narrative.

| Concern | Choice | Why |
|---|---|---|
| Engine | Python; pandas/Polars; DuckDB; the existing backtest and AUTOPSY code generalised | Reuse; the team's strength |
| Statistics | Hierarchical Bayesian models (PyMC or NumPyro, or equivalent); pre-registered test library; FDR control; power calculators; conservative bounds per Appendix A1 | Population-informed estimation; honest uncertainty |
| Data | Event-sourced trade store on Postgres + object storage; CTR schema; encryption; audit logs; append-only consent ledger | Reproducibility and trust |
| AI | Hosted frontier LLM for mapping, narration, explanation and conversation; agent orchestration under the fixed protocol; faithfulness checks; hypothesis inbox | Explanation is cheap; Findings are not |
| The show | Web app (React/Next.js or equivalent); vertical story format; animated evidence (D3 or equivalent); a live reveal service consuming activity events; a typed event stream for the computation stage (§12.6); DNA Map; Card export; mobile-first | Fast to build; shareable; never waits |
| Evaluation | Golden datasets; synthetic and noise traders; narration faithfulness tests; "explain this" hallucination suite; expert gold standard | Proof, not claims |
| Connections | Phase 2: the launch market's broker APIs, read-only, consented | Longitudinal DNA and alerts |
| Privacy | Consent ledger; deletion pipeline; RBAC; differential privacy for published aggregates (later) | The wall in practice |

## 21. Roadmap — DECIDED (durations HYPOTHESIS)

| Stage | Goal | Gate | Duration |
|---|---|---|---|
| 0 — Discover | CTR v1; AUTOPSY generalised; Evidence Standard v1 with committed thresholds; Appendices A1–A3 calibrated; **the component objectives and scorecards written (§18.4)**; synthetic test-bed; concierge reports for 20–50 partners; expert gold-standard pilot; show storyboard on paper; trademark filing | ≥ 60% of partners confirm a non-obvious Established Finding; ≥ 30% adopt a move; the MVP three chosen; the vocabulary set; every component has a written objective | 6–8 weeks |
| 1 — Doormat | Import contract; six-screen arc with the DNA Map, animated evidence, interest engine, "explain this" v1; the MVP three plus Replay; the move stack; feedback and disputes; DNA Card; email save; **the credit chain instrumented and correctness scorecards live** | Upload completion ≥ 60%; Finding acceptance ≥ 70%; first aha < 3 min; six-screen completion ≥ 50%; noise-trader false positives < 5%; every shipped component emits its lineage | 10–12 weeks |
| 2 — Loop | Accounts; experiments with verdicts; longitudinal DNA and diffs; weekly review; monthly DNA; Ask your DNA; first broker connections; subscription; pricing test; **utility scorecards and the monthly measurement review live**; **the first pooled reads per move type** | **Two numbers, both set before Phase 2 starts (§23.1):** a share of traders meeting their process threshold, and a share of move types with a pooled pass. Month-3 retention target met | 12–16 weeks |
| 3 — Platform | B2B pilot → product; benchmarks; infrastructure tools; Market/Regime DNA; parallel experiments with matched groups | The shared Trader Model powers adjacent products; B2B revenue | 2027 |
| 4 — Scale | New markets, integrations, capital ecosystem | Economics and governance justify it | 2028+ |

**The first thirty days.** Week 1: kickoff — set the Phase 0 start and review dates; AUTOPSY portability audit; data contract v1 and CTR spec; commit Evidence Standard thresholds and the δ_min calibration rule; start the trademark search. Week 2: recruit 20–50 partners; collect ten exports per launch broker; start the synthetic and noise test-bed; brief counsel. Weeks 3–4: CTR v1 reconstructing real exports; first generalised categories; first three concierge reports; the six-screen storyboard with real numbers; Appendices A1–A3 drafted against real data; counsel's posture confirmed on the actual report language. Weeks 5–8: all reports and interviews; gold-standard pilot; MVP three and vocabulary; composite-mark filing; Phase 1 build list.

**The 12-month picture — HYPOTHESIS: the targets the roadmap is aimed at, set once more at the Phase 0 review.** Twelve months after the Phase 0 kickoff, the doormat is live in India on the top broker exports with **10,000+ completed diagnoses** and six-screen completion above 50%; **1,000+ experiments** have closed with pre-registered verdicts, at least **25% PASS against δ_min** (Appendix A3) and a PASS rate that rises across framework versions; **1,000+ paying subscribers** hold month-3 retention at target; correctness scorecards are published and the first Process Score validation study is released; **one paid prop-firm pilot** is complete with a published case study; every shipped component emits its credit chain; there have been zero regulatory incidents; and the second market is a decision made on evidence, not on appetite. Half of these numbers will be wrong; they exist so the team knows which half.

**MVP definition of done (v1)**

| Must have | Done when |
|---|---|
| One ingestion path | A real launch-market tradebook imports, normalises and reconstructs reliably |
| Evidence engine | Numbers deterministic, versioned, auditable |
| The MVP three + Mirror + Card | Avoidable Loss with its leak, the edge worth protecting, Next Best Move with Replay, the Mirror, the Card with Process Score |
| The show | Six screens, DNA Map, animated evidence, interest engine, "explain this" v1, under five minutes |
| Evidence UX | The trades behind every major Finding are inspectable |
| Concierge validation | 20–50 real traders evaluated before the show is polished |
| Confidence handling | Weak Findings suppressed; both honest-gap states designed (§6.2) |
| Feedback loop | Accurate / Not sure / Wrong plus the dispute path (§6.1) |
| Experiment record | One intervention through Replay, risk classification, live run and verdict |

## 22. Risks, failure modes, kill criteria — DECIDED

| Risk | Severity | Countermeasure |
|---|---|---|
| False or fitted Findings | Critical | Evidence registry, adversarial validation, hold-out, tiers, noise-trader tests |
| Overfitting / false discovery | Critical | Pre-registered library, multiple-testing control, robustness |
| Bad reconstruction | Critical | CTR with deterministic reconstruction; quality as input |
| Advice / compliance drift | Critical | Process language; Next Best Move is a process rule; counsel; non-goals |
| An experiment harms a trader | Critical | §11.4 invariant; risk screen; auto-stop rule |
| Fund-data trust | Critical | Entity-level wall; public promise; audit |
| Name and category collision | High | §3.5: the house-brand structure is binding; composite mark filed after the week-2 search; the exit stays cheap — rename the product line, never the company |
| A competitor ships the insight first | High | Differentiate on the loop and the standard, not the insight (§16) |
| Beautiful but shallow show | High | Insight density; evidence drawer; doormat proxy |
| True but boring show | High | P-4 and P-6 enforced; hook on screen one; animated evidence |
| Scope explosion | High | One market, one ingestion path, the MVP three |
| No retention | High | Experiments with verdicts; diffs; monthly DNA |
| LLM hallucination | High | Evidence objects only; faithfulness checks; "explain this" gate |
| Overclaimed Avoidable Loss | High | Appendix A1 conservative bound and minimum sample |
| Copycats | High | Compounding intervention and confirmation data; publish the standard |

- **Kill criteria.** Phase 0: fewer than half of partners confirm any non-obvious Finding → stop and rework before any UI. Phase 1: upload completion < 40%; Finding acceptance < 60%; six-screen completion < 30%. Phase 2 (v1.4): adherence collapses — fewer than half of adopters meet any rule's process threshold; **or** no move type earns a pooled pass within 90 days of reaching its minimum trader count.
- **Pivots.** A pure diagnostic and research tool without interventions; a B2B evaluation product for prop firms on the Process Score; Strategy DNA for systematic traders.

### 22.1 What could make this thesis wrong — the existential register — DECIDED (added in v1.3)

The table above is about failing to execute. This one is about being wrong. Each row names a belief the thesis rests on, the evidence that would change it, and what we would do. It is reviewed at every phase gate; a belief that fails is recorded in the decision log with the pivot taken, never quietly reworded.

| The belief | The evidence that would show it is wrong | The response |
|---|---|---|
| **The engine can be built:** Findings that survive the Evidence Standard exist at 100–500 trades | Phase 0: fewer than half of the partners receive a non-obvious Established Finding even with population priors and market context | Wrong as a consumer product. Retreat to Strategy DNA for systematic traders and B2B evaluation, where samples are large; the show waits for a brain |
| **Traders act on evidence:** a validated Finding changes behaviour | Phase 1–2: acceptance high, adoption below 15%, adherence collapsing inside the window | The loop is the wrong retention engine. The product becomes diagnosis plus research; the intervention system is rebuilt around habit design before it is sold |
| **Improvement is measurable in a retail window** | Phase 2: ΔE intervals rarely clear δ_min even where adherence holds; most verdicts are "not yet measurable" | The North Star is right but too slow for consumers. Re-anchor the product cycle on process metrics, with ΔE as the quarterly audit rather than the weekly hook |
| **The market is large enough:** serious Indian traders who will pay for process | WTP range below cost to serve; unique F&O traders keep falling [F3]; free-to-paid conversion under 2% | India becomes brand and B2B; the subscription moves to the global tier earlier than planned |
| **The loop and the standard differentiate; the insight does not** | The category study or the launch shows a verified competitor shipping experiments with verdicts and published accuracy — or traders showing no preference for evidence over narrative | Compete on the Measurement Layer and the intervention-outcome dataset alone, or license the engine to firms instead of owning the consumer |
| **A funded competitor cannot buy the asset** | A competitor raises heavily and offers free longitudinal analytics with broker integrations | The compounding datasets — intervention outcomes, confirmations — are the only defence: accelerate the credit chain and consented population data; publish the standard early |
| **Regulation permits process observations without adviser registration** | Counsel: Next Best Move is advice under SEBI's regulations as worded | Register, or reword the moves; if neither is viable, the intervention system moves B2B, where firms coach their own traders |
| **The trust wall is believable:** a fund-owned product can hold retail data | Phase 1: upload completion collapses at the trust screen and interviews name the fund | Spin the data environment into a separate entity with an independent audit before scale, and say so on screen one |

## 23. Decisions, unknowns, non-goals

### 23.1 Decision log

| Decision | Status | Owner · Date |
|---|---|---|
| Input = trade-level data; Canonical Trade Record | Decided | — |
| Free, one-time doormat; value before any ask | Decided | — |
| Evidence Standard, hierarchy of claims, Twelve Laws, Trader Promise | Decided | — |
| The Finding as atomic unit; evidence-first pipeline; archetypes emergent | Decided | — |
| Compute all prescriptions; Next Best Move ranked; the move stack; reveal by interest | Decided | — |
| One credited **primary** experiment; the risk-envelope invariant (v1.3 wording; was "no financial risk") | Decided | — · 30 Sep 2026 |
| Avoidable Loss, Process Score, North Star, experiment safety specifications | Decided as method (Appendices A1–A4); parameters calibrate in Phase 0 | Research · [ ] |
| **Avoidable Loss frozen as the signature output; its attribution mathematics are a Phase 0 calibration item, not frozen** | **Decided** (v1.3) | Research · Phase 0 |
| **PASS requires the credible interval's lower bound to exceed δ_min, plus adherence, guardrails and no confound** | **Decided** as method (v1.3); the δ_min calibration rule is a Research Specification item | Research · Phase 0, week 1 |
| **Process Score posture: our standard at launch, inside the diagnosis first; the market decides the category** | **Decided** (v1.3) | — · 30 Sep 2026 |
| **The show: principles frozen; six screens, the arc and the interest engine's ranking are implementation hypotheses; Phase 1 minimum is rules-based reveal** | **Decided** (v1.3) | Product · Phase 0 review |
| Disagreement handling; honest-gap experience; "explain this" v1; framework versioning; subscription arc; computation stage; rituals | Decided | — |
| Consent ledger; deletion process | Decided | — |
| WTP test plan; B2B sequence and pilot; hiring sequence | Decided | — |
| **Launch: India first, global-ready** | **Decided** | CEO · 30 Sep 2026 |
| **Name: PlusEV–TradeDNA, house brand binding** | **Decided**; composite mark filed after the week-2 search | CEO · 30 Sep 2026 |
| **The Measurement Layer: objectives before scores, human-decided, credit chain in Phase 1** | **Decided**; the component definitions (§18.4) are a Phase 0 deliverable | Research / Product · [ ] |
| **Amendment 1 — a trader-level verdict is decided on the process metric and the avoided-cost accounting; Trader Improvement is read at the quarterly and pooled-per-move-type levels; the company North Star becomes the share of move types with a pooled pass plus the share of traders meeting their process threshold** | **Decided** (v1.4) — forced by the arithmetic in the header and Appendix A3 | CEO · 1 Oct 2026 |
| **Amendment 2 — the full curated set is offered; moves on disjoint trade sets run in parallel and are measured separately; moves on the same trades are merged into one rule; "exactly one primary" is rescoped to the pooled study** | **Decided** (v1.4) | CEO · 1 Oct 2026 |
| **Replay is illustration, not evidence, and never selects a move; "impact" in the ranking is the hold-out-validated effect** | **Decided** (v1.4) | CEO · 1 Oct 2026 |
| **The forward statement has one permitted form: conditional arithmetic on his own shrunk rates, never a forecast of returns** | **Decided** (v1.4); counsel confirms the wording with the rest of the posture | CEO · 1 Oct 2026 · Counsel · [ ] |
| **Phase 2 gate: the two target numbers** | **Open** — both set before Phase 2 starts, not after | Product with Research · [ ] |
| **Trade-frequency count in Phase 0** — what share of design partners trade ≥ 5 times a week; the low-frequency segmentation decision rests on it | **Open** — a week-5 measurement, not a guess | Product · Phase 0 wk 5 |
| **Phase 0 start date and review date** | **Operational gate** — set at kickoff; does not block the baseline | CEO · [ ] |
| **Regulatory posture** | **Gate before Phase 1** — counsel's confirmation on the actual report language (§19.2); does not block the baseline | Counsel · Phase 0, week 3 |
| The MVP three | Proposed; Phase 0 decides | Product · [ ] |
| External capital | Open; not required for Phase 0–1 | CEO · [ ] |

*Frozen as v1.3 — Baseline on 30 September 2026; amended to v1.4 on 1 October 2026 by the four rows above. The operational gates are tracked here and in Workbook §0.5; closing them is a decision-log entry, not a new version. From here, every change to this document is a row in this table.*

### 23.2 Unknowns register

| Unknown | Why it matters | Current belief | Confidence | How to test | Cost of being wrong | Deadline · Owner |
|---|---|---|---|---|---|---|
| The second market (the first is decided: India, §3.4) | When and where global-ready is cashed in | Not before Phase 3; chosen on evidence | Low | Phase 2 retention and B2B signal; a category study in the candidate market | Expansion cost with no lift | Phase 3 · CEO |
| AUTOPSY portability | Weeks versus a rebuild | Categories generalise; setup and exit rules are strategy-specific | Medium | Audit; three external tradebooks | Phase 0 slips | Week 1 · Eng |
| Design-partner access | Phase 0 needs 20–50 histories | Reachable | Medium | Recruit and count | No calibration data | Week 2 · Product |
| Composite-mark registrability (the name is decided: §3.5) | Brand and discovery | PlusEV–TradeDNA is registrable as a composite in classes 9, 36, 41, 42 | Medium | Trademark search, then filing | Rename the product line, never the company | Week 2 · CEO |
| δ_min calibration | Whether PASS means a real improvement | Set per trader from baseline variance, fee load and trade frequency | Low evidence | Simulation on synthetic traders; partner equity curves | Passes that nobody can feel | Phase 0 · Research |
| Avoidable Loss attribution | The signature number's honesty | Hierarchical attribution with a conservative bound works | Low evidence | Appendix A1 on synthetic traders with known ground truth | The hook becomes an accusation | Phase 0 · Research |
| Process Score calibration | Whether one number can be honest | Yes, with sub-scores and a band | Medium | Gold standard; partner reaction; gaming tests | A score that misleads | Phase 0–1 · Research |
| Market-context enrichment lift | Data-licensing decision | High | Low evidence | 50 tradebooks with and without | Data cost, no lift | Phase 0 · Research |
| Small-sample viability | Whether Findings survive at 100–300 trades | Priors make it workable | Medium | Synthetic test-bed; partners | Too many honest gaps | Phase 0 · Research |
| Export data quality | Reconstruction feasibility | Top brokers' exports are usable | Medium | Ten exports per broker | Ingestion failure | Phase 0 · Eng |
| Competitive differentiation | Whether the loop is enough | The loop and the standard differentiate; the insight does not | Low evidence | Category study; use the three closest products | Building a better journal | Phase 0–1 · Product |
| Regulatory classification | Legality and language | Analytics, if worded as process | Medium | Counsel opinion | Relaunch | Before Phase 1 · Counsel |
| Willingness to pay | Business model | ₹999–1,999 for serious traders | Low | §15.3 | Wrong tiering | Phase 1 · Product |

### 23.3 What we will NOT do — DECIDED
No buy/sell calls · no copy trading · no social feed · no P&L leaderboards · no selling data or order flow · no fine-tuning on user data without consent · no experiment that widens a trader's risk envelope · no surveillance product for firms over their traders' individual diagnoses · no 30 broker integrations before Phase 2 · no capital allocation before Phase 4 and only with regulatory clearance · no consumer mobile app before the web doormat works · no white-label before the PlusEV brand exists · no AI chat as the primary interface before the evidence standard is proven · no real-time alerts before broker-connection maturity · no pre-trade blocking before regulatory clarity · no P&L as the success metric · no entertainment without insight, and no insight without a show worth watching · no shaming language · no manufactured insights · no cherry-picked cut-offs · no overclaimed confidence · no data to the fund · no phone number as an early ask · no paywall on the first aha.

---

# Appendix A — The four specifications

## A1. Avoidable Loss — attribution and bound

**Definition.** The portion of realised loss over the analysed history that is attributable to Established leak conditions, stated conservatively, in the trader's currency.

**The attribution problem.** One trade can sit in four leak conditions at once — after two losses, high volatility, oversized, outside the edge regime. Giving each the full loss counts it four times.

**The rule — hierarchical, mutually exclusive attribution.**
1. Each trade is assigned to **at most one** primary leak condition: the Established condition with the largest validated conditional effect for that trader, ties broken by the larger sample.
2. Per-trade avoidable amount = the trade's realised result minus its **counterfactual baseline**: the trader's own expectancy in the nearest comparable state without the leak condition, matched on instrument and volatility bucket, and only where that comparison cell meets the minimum sample.
3. Only the shortfall counts. A winning trade inside a leak condition contributes zero, never a negative. This is deliberately conservative: it understates rather than overstates.
4. Secondary conditions are reported qualitatively ("these trades were also in high volatility") and never add to the total.
5. Per-leak subtotals are shown; the headline is their sum, which by construction cannot exceed total realised loss.

**Counterfactual assumption, stated in the product.** It assumes the rest of his behaviour is unchanged and the market unchanged — a floor estimate of what avoiding that condition would have been worth, not a promise of a different past. The copy says so in one line.

**The bound.** Every conditional effect is a hierarchical Bayesian posterior; Avoidable Loss is computed from the **conservative end of the 90% credible interval** — the fifth percentile of the shortfall distribution. Presentation: **"at least ₹X"**, never "approximately". A small sample produces a lower bound, which is correct: uncertainty should shrink the claim, not the confidence language around it.

**Minimum conditions to show it at all.** At least 30 trades in the leak condition and at least 100 in comparable non-leak states; at least one Established leak; the conservative bound must exceed both 2% of total realised loss and a currency floor (₹5,000 or equivalent). Otherwise the screen becomes "Not enough evidence yet" (§6.2). A profitable trader sees the same computation expressed as profit given up, with the same floor logic.

**Validation.** On synthetic traders with planted leaks of known cost: the estimate must never exceed the true planted cost (a conservative-bound violation is a blocking bug), and should recover at least half of it. On noise traders it must return zero.

**Status.** The output is frozen; the method above is the candidate we commit to test; the parameters — the 30/100-trade minimums, the 2% and ₹5,000 floors, the fifth percentile — are calibration items that Phase 0 sets against real and synthetic data. A change to the method after Phase 0 is a major framework version (§8.6) and a decision-log row.

## A2. The Process Score

**What it is.** A 0–100 headline with four sub-scores — Strategy, Risk, Execution, Behaviour — and a confidence band, computed only from that trader's own Findings, with a published methodology. It never appears without the diagnosis behind it.

**Inputs.** Established Findings at full weight; Likely at reduced weight; Exploratory at zero. Every Finding maps to a sub-score by its DNA and enters as a signed, effect-sized contribution — a validated strength adds, a validated leak subtracts, scaled by its effect relative to the trader's own baseline.

**Composition.** Each sub-score is the weighted aggregate of its Findings mapped onto 0–100, where 50 is the population median for traders with a comparable fingerprint. The headline is a weighted mean of the four; the v1 weights are equal, and Phase 0 sets them from which sub-score best predicts subsequent improvement. The weights are published, versioned, and changed only by a major framework version (§8.6).

**The confidence band.** Propagated from the posterior uncertainty of the contributing Findings and the trader's sample size. A thin history yields a wide band — for example 41 (36–46) — and the band is always shown with the number. No band, no score.

**When there is no score.** Fewer than 50 reconstructed trades, no Established or Likely Finding in any sub-score, or a band wider than 25 points → "Not enough evidence yet," with what is needed. A sub-score with no Findings shows as unscored, never as zero: absence of evidence is not a poor process.

**Resistance to gaming.**
- No-trade gaming: a dormant trader's score decays toward "stale, not scored", never upward.
- Sample gaming: contributions are sample-weighted, so a handful of cherry-picked trades cannot move the headline.
- Selective upload: the score is stamped with the completeness of the history; a partial upload is labelled as such on the Card.
- Micro-trade gaming: contributions are weighted by risk, so trivial trades cannot inflate a sub-score.
- Feedback gaming: the trader's own Accurate/Wrong labels never feed the score. They calibrate the engine, not his number.

**Validation.** Test–retest stability on split histories; convergent validity against the expert gold standard's ranking; predictive usefulness — does a higher score at T predict lower avoidable loss at T+1 (the only test that makes it meaningful); comprehension in Phase 0 interviews ("what does this number mean to you?"); and gaming simulations on synthetic traders. **Until convergent and predictive validity are demonstrated, the score stays internal to the diagnosis and off the public DNA Card.** The Card is not a vanity metric before it is an honest one.

**Versioning.** A formula change is a major version: a mapping note is published, both scores shown for one cycle, and every historical score keeps its version stamp.

## A3. Trader Improvement — the North Star formula

**Definition.** ΔE = E_post[R] − E_baseline[R], regime-adjusted, with process guardrails, where R is the risk-normalised result per trade. **Unchanged in v1.4; what changed is where it is read.**

**Where ΔE is read — amended v1.4.** The formula below is unaltered. The amendment concerns the level it is applied at, and it is forced by arithmetic rather than preference. At a typical retail per-trade dispersion of σ_R ≈ 1.4, the trades needed **in each of the baseline and post windows** to detect a shift δ at 80% power are:

| δ | 0.05R | 0.10R | 0.15R | 0.30R | 0.50R | 0.75R |
|---|---|---|---|---|---|---|
| trades per window | 9,695 | 2,424 | 1,077 | 269 | 97 | 43 |

A good behavioural rule moves overall expectancy by roughly 0.1R, which needs about 2,400 trades per window — nearly three years per window at fifteen trades a week, against the thesis's 150-trade cap. **An individual trader's ΔE is therefore not measurable inside any window he will wait through, with one move or with several.** Consequently:

- **A trader-level verdict does not use ΔE.** It uses the process metric and the avoided-cost accounting (§11.2).
- **ΔE is read at his quarterly review**, computed exactly as below, once enough Reserve trades exist, and reported with its interval and the honest statement when the interval is too wide to decide.
- **ΔE is read per move type across traders**, which is what establishes whether a move works: separating a move type's effect needs roughly 10–63 traders at 40–80 trades each, depending on the effect size and between-trader spread. The pooled estimate is a hierarchical model across adopters, with adoption bundles recorded so that parallel moves can be separated.
- **PASS at either of those reads** keeps the v1.3 rule in full: the lower bound of ΔE's credible interval must exceed δ_min, plus adherence at or above its floor, no guardrail breach and no material confound.
- **Verdict reason codes (v1.4)** — the external vocabulary stays PASS / PARTIAL / REFUTED, and every verdict additionally carries a code so that the intervention-outcome dataset never conflates two different facts: `no_practical_effect` (a benefit is likely but smaller than δ_min — the hypothesis is right and not worth it, so the move's priority drops and the Finding stands) versus `no_directional_effect` (the interval excludes benefit — the Finding itself is demoted) versus `harmful`. PARTIAL carries `adherence`, `confounded`, `guardrail`, `stopped` or `inconclusive`.
- **The avoided-cost figure is not a form of ΔE** and is never added to it. It is an accounting identity over avoided situations, priced at the trader's own validated conditional rate and reported as a conservative "at least". Its only uncertainty is in the rate, which carries its interval from the diagnosis.

| Element | Specification |
|---|---|
| **R** | Result per trade divided by the risk unit: the defined stop where one exists; otherwise the inferred risk unit (position size × instrument volatility at entry), labelled as inferred. The unit is fixed at experiment start and not re-derived mid-window. |
| **Baseline** | The N trades immediately before the prescription, where N is the power-derived experiment length, extended backwards to the last framework version change or the last completed experiment, whichever is nearer. |
| **Post window** | The N trades from the experiment start; incomplete windows are not scored. |
| **Regime adjustment** | Both windows are re-weighted to a common regime mix using the trader's own regime-conditional expectancies; if a regime present in one window is absent in the other, its trades are excluded from both and the exclusion is reported. |
| **Fees** | Always net of fees and taxes; the Indian charge model is part of the CTR. |
| **Outliers** | Winsorised at the 2.5th and 97.5th percentiles of the trader's own R distribution; the unwinsorised figure is reported alongside, and a large gap between them is itself a Finding about concentration. |
| **Minimum observations** | The lesser of the power-derived N and 25 trades in each window; below that the verdict is "not yet measurable," never a weak PASS. |
| **Uncertainty and δ_min** | ΔE is reported with a credible interval. PASS requires the **lower bound** of that interval to exceed **δ_min**, the minimum practically important improvement — never merely to exclude zero, and never a positive point estimate alone. δ_min is fixed per trader before the experiment starts, from his baseline R variance, fee load and trade frequency, so that a PASS is an improvement worth more than the fees over the window and visible in his own equity curve; the calibration rule is a Research Specification item set in Phase 0 (a floor such as 0.05R is the working assumption, not the rule). A statistically significant +0.003R is not a PASS. |
| **Adherence** | Reported separately, never blended into ΔE. Adherence below the pre-registered floor routes to PARTIAL regardless of ΔE, because an unfollowed rule was not tested. |
| **Confounds** | A change of strategy, instrument mix or sizing regime during the window flags the verdict as confounded; the experiment is re-run rather than credited. |
| **Process guardrails** | A PASS also requires no deterioration in drawdown behaviour, execution quality or the avoidable-loss rate. Improvement bought with more risk is not improvement. |
| **Aggregate reporting** (v1.4) | The company North Star is the **share of move types with a pooled PASS**, plus the **share of traders meeting their process threshold** — never an average of ΔE across traders, which the largest accounts would dominate, and never a count of trader-level experiments "passing", which the arithmetic above rules out. |

## A4. Experiment safety — see §11.4
The risk-envelope invariant, the permitted/conditional/never table, the pre-start risk screen, the auto-stop rule and the library-wide risk classification are specified in §11.4 and are part of this appendix by reference.

---

# Appendix B — Data schema (v1)

| Field | Type | Required | Purpose |
|---|---|---|---|
| timestamp | ISO 8601 | Yes | Time of day, session, sequence |
| instrument | string | Yes | Market, tick size, normalisation |
| side | enum | Yes | Long / short |
| quantity | float | Yes | Size |
| entry_price | float | Yes | Entry |
| exit_price | float | Yes | Exit |
| fees | float | Yes | Net P&L (Indian charge model: STT, stamp duty, exchange and SEBI fees, GST) |
| realised_pnl | float | Yes | Outcome |
| fill_id / order_id | string | If available | Round-trip reconstruction |
| stop_price | float | No | R calculation |
| target_price | float | No | Exit efficiency |
| intended_entry / intended_exit | float | No | Execution quality |
| account_equity | float | No | % risk |
| leverage | float | No | Risk profile |
| order_type | enum | No | Execution analysis |
| strategy_tag | string | No | Setup analysis |
| thesis / confidence / rule_followed / emotional_state | text · enum · bool · enum | No | Behavioural context |
| PlusEV-enriched (computed) | — | — | volatility, ATR, trend_state, regime, volume, relative_volume, session, distance_to_levels, prior_day_structure, event_regime, preceding_trade_state, account_state, market_state |

# Appendix C — Glossary
PlusEV–TradeDNA (the product; "Trade DNA" in running text) · PlusEV · AUTOPSY (internal engine) · Canonical Trade Record · Finding · Evidence Standard · Confidence tiers · Four DNAs · Process Health · Process Score · Avoidable Loss · Trader States · Edge Map · Leak Map / No-Trade Zone · Next Best Move · The move stack · Replay · The Experiment · Risk envelope (§11.4) · δ_min (Appendix A3) · DNA Map · Interest engine · Two clocks · DNA Card · Monthly DNA · Hypothesis inbox · Measurement Layer · Credit chain (§18.5) · Doormat / Loop / Platform. Definitions as used throughout this document.

# Appendix D — Document map — DECIDED

This thesis is the master index. After Phase 0 it splits, and each child owns its subsystem while this document keeps the Canon, the strategy and the links.

| Document | Owns | Drawn from |
|---|---|---|
| **Product Thesis** (this, trimmed) | Why, what, principles, user value, strategic role, Canon | §0–5, §13–18, §22–23 |
| **Research Specification v1** | Evidence Standard, statistics, validation, interventions, the four appendices, the component scorecards | §6, §11, §18.2–18.7, Appendix A |
| **Experience Specification** | The show, arcs, interest engine, computation stage, rituals | §12 |
| **Technical Design** | Architecture, CTR, AI, infrastructure, versioning | §8–9, §20 |
| **Strategy** | Business model, GTM, B2B, pricing, moat, competition | §15–17 |
| **PRD v1** | What Phase 1 ships | §21 |

**The next artifact is the Research Specification**, because the remaining question is no longer "what should we build?" but "can we make the intelligence correct enough that the product deserves to exist?"

# Appendix E — Provenance
- **The founding idea (28 Sep):** §1 in full.
- **Reviews A–D (28 Sep):** the Evidence Standard, four DNAs, flagship outputs, interventions and experiments, longitudinal DNA, compliance, evidence-first pipeline, behavioural inference, claims hierarchy, evaluation framework, evidence objects, the wall, the four-products progression, competition, kill criteria, pricing, non-goals, emotional design, the user story.
- **ChatGPT thesis and workbook (29 Sep):** the Laws, epistemic boundaries, the intelligence stack, the reciprocity table, metric layers, the definition of done, the flywheel, the signature-output principle.
- **DeepSeek brainstorm and thesis (29 Sep):** "Trader data × Market data × Temporal context," archetypal user stories, glossary and schema, "how the gap might close," non-goals, the computation stage as intelligence, "your DNA this month."
- **v1.1 (29 Sep):** the map metaphor and the DNA Map; Next Best Move; the interest engine on two clocks; Avoidable Loss as signature number; the Process Score; the show as the product with P-1 to P-6 restored; AI as the research desk; distribution as mechanisms; the first thirty days.
- **Reviews G and H, and v1.2 (29 Sep):** "Decision Draft" status; one credited *primary* experiment; ambitions marked as hypotheses; AI reworded as research interface and orchestrator; the four specifications; Law 11 and Promises 6 and 9; disagreement handling; the honest-gap experience; "explain this"; framework versioning; the subscription arc; the computation stage; the retention rituals; the consent ledger; the deletion process; the WTP test plan; the B2B plan; hiring and capital; the verified competitive table and the name finding; the moat re-ordered; the document map.
- **The founder's session of 30 Sep:** the move stack — the route shown whole, several moves adoptable, exactly one credited — and the value ladder reworded from "change one thing"; India confirmed as the launch market; PlusEV–TradeDNA decided with the house brand binding; and **the Measurement Layer (§18.2–18.7, Law 12)** — every engine, model, Finding, screen, move and ritual with a written objective and a score against it, correctness separated from utility, the credit chain for RCA, human-decided throughout, and the definitions named as the place the hard work goes.
- **The amendment of 1 Oct (v1.4):** writing the Research Specification produced the arithmetic that an individual trader's ΔE is unmeasurable in any window he will wait through, which would have left the v1.3 verdict rule producing no verdicts at all. Four changes follow: the trader-level verdict moves to the process metric plus avoided-cost accounting, with ΔE read at the quarterly and pooled-per-move-type levels; the full curated set is offered, with overlap rather than count as the constraint and "exactly one primary" rescoped to the pooled study; replay is demoted to illustration and barred from selecting a move, with "impact" defined as the hold-out-validated effect; and the forward statement is given one permitted form — conditional arithmetic on the trader's own shrunk rates. Two reviews of the Research Specification's Draft 2 contributed the first; the founder's question about why only one solution is given, and whether attribution survives several, produced the second, third and fourth.
- **Reviews I and J, and the v1.3 freeze (30 Sep):** the Canon's lineage stated (I); the risk-envelope invariant in place of "no financial risk" (I); δ_min in the PASS criterion (I); "global readiness costs nothing" withdrawn (I); external facts sourced or re-tagged, with Appendix F (I); six screens and the interest engine's ranking as implementation hypotheses under frozen principles, with a rules-based Phase 1 minimum (I); Avoidable Loss frozen as output, not formula (I); "none can" claims removed from the competitive framing (I); the twelve questions with their answer map (J); the market data behind "why now" (J); the Process Score posture (J); the existential register §22.1 (J); the 12-month picture (J); Workbook §11 and §13 referenced from §10 and §12 (J). The founder's judgment: the two blocking rows became operational gates — a start date is set at a kickoff, and counsel's confirmation is a gate on Phase 1, not a fact the thesis waits for — and the document was frozen.

# Appendix F — Sources

External facts in this document carry a bracketed reference to a row here, retrieved on the date shown. A claim about the world with no row here is a HYPOTHESIS, whatever it sounds like.

| Ref | Source | Used for | Retrieved |
|---|---|---|---|
| **F1** | SEBI press release, 23 September 2024 — *Updated SEBI study reveals 93% of individual traders incurred losses in equity F&O between FY22 and FY24; aggregate losses exceed ₹1.8 lakh crores over three years.* https://www.sebi.gov.in/media-and-notifications/press-releases/sep-2024/updated-sebi-study-reveals-93-of-individual-traders-incurred-losses-in-equity-fando-between-fy22-and-fy24-aggregate-losses-exceed-1-8-lakh-crores-over-three-years_86906.html | §3.3, §4.1: 93% lost over FY22–FY24; aggregate net losses above ₹1.8 lakh crore; more than 1 crore individual traders studied; average loss about ₹2 lakh; 1% earned more than ₹1 lakh after costs; more than 75% of loss-makers continued trading; under-30 share 31% (FY23) → 43% (FY24) | 30 Sep 2026 |
| **F2** | SEBI, January 2023 — *Study: Analysis of Profit and Loss of Individual Traders dealing in Equity F&O Segment.* https://www.sebi.gov.in/reports-and-statistics/research/jan-2023/study-analysis-of-profit-and-loss-of-individual-traders-dealing-in-equity-fando-segment_67525.html · reported by Business Standard, 25 January 2023: https://www.business-standard.com/amp/article/markets/sebi-study-suggests-89-retail-traders-in-equity-f-o-suffered-losses-123012501466_1.html | §4.1: 89% lost in FY22; unique individual F&O traders 7.1 lakh (FY19) → 45.2 lakh (FY22) | 30 Sep 2026 |
| **F3** | Business Standard, 7 July 2025 — *Net losses of traders in F&O widens in FY25: SEBI study.* https://www.business-standard.com/amp/markets/news/net-losses-of-traders-in-fo-widens-in-fy25-sebi-study-125070701221_1.html | §3.3, §3.4, §4.1, §22.1: 91% lost in FY25; net losses ₹1,05,603 crore (FY25) versus ₹74,812 crore (FY24), +41%; about 96 lakh unique individual F&O traders across the top thirteen brokers; unique traders 61.4 lakh (Q1 FY25) → 42.7 lakh (Q4 FY25) | 30 Sep 2026 |
| **F4** | News on AIR, 23 September 2024 — *SEBI study reveals individual traders face severe losses in equity F&O segment.* https://www.newsonair.gov.in/sebi-study-reveals-individual-traders-face-severe-losses-in-equity-fo-segment | Corroboration of F1 | 30 Sep 2026 |
| **F5** | tradedna.in — https://tradedna.in/ | §3.5, §16 | 29 Sep 2026 |
| **F6** | TraderDNA — https://traderdna.me/ | §16 | 29 Sep 2026 |
| **F7** | Edgemap — https://getedgemap.com/ | §16 | 29 Sep 2026 |
| **F8** | EdgeGhost — https://alternativeto.net/software/edgeghost/about | §16 | 29 Sep 2026 |
| **F9** | Arxion Labs, Trader DNA Profile — https://arxionlabs.com/trader-dna-profile | §16 | 29 Sep 2026 |
| **F10** | trade-dna.com — https://trade-dna.com/ | §16 | 29 Sep 2026 |

**Not sourced, and therefore not FACT:** the usability of the top brokers' exports for fill-level reconstruction (HYPOTHESIS; Phase 0 counts it); the size of the journaling category (UNKNOWN; category study); Hygentra's claimed Trader DNA capability (unverified, §16); every competitor's *inability* to do anything (we record only what we have not seen). Sources are re-verified at each phase gate; a figure older than a year is re-sourced or re-tagged.
