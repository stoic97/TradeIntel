# Scope — testing register

*Opened 24 October 2026 · Owner: founder · Updated 27 October 2026 (TR-011 to TR-014; the build itself is in `claude/scope_engineering_handoff_v1.md`) · PRD v1.2 is closed (23 Oct): Scope is in testing, and every bug, feature and change goes here. The next PRD is written from this register, not from memory.*

**How an entry works.** One row per item. *Kind* is bug, feature, change or process. *Source* names the document or session that raised it. *Gate* is what must be true before it ships. An item leaves this register only into the next PRD, or as rejected with its reason. Research-layer deferrals stay in TradeIntel `docs/deferrals.md` and are cross-referenced here, not copied.

## Open

| # | Item | Kind | Source | Gate | Owner |
|---|---|---|---|---|---|
| TR-001 | **What costs took from his result, in the Mirror.** His charges beside his gross result, as a counted past fact. Shown only when charges are in his file; until then every figure stays labelled *gross*. An estimate from the Indian charge model only if the founder rules for it, labelled *estimate* wherever it appears. Never phrased as advice to trade less or change broker | Feature | Thesis v1.5 decision 2 | TD-002 ruled at the kickoff; a charges export mapped for the first broker; a hand-calculated fixture per PRD Appendix A | Founder rules · Harshad builds |
| TR-002 | **The two-readout test in the concierge script.** After guess-first and the Mirror: the same history as an AI-journal-style narrative (frontier model, the founder-written baseline prompt) and as the Mirror with drawers, in random order. *"Which would you act on? Why?"* What he opens is logged. Synthetic history with a planted truth by default; his own only with consent to the named external service | Process | Thesis v1.5 decision 3, §22.1; Component 8 §K question 6 | The reading rule pre-registered before the first session; the synthetic history and both readouts prepared and frozen | Founder with research seat |
| TR-003 | **NSE crude oil in the first lane.** Recruitment is open (site register C18). Reading an NSE crude trip needs its instrument profile from NSE's own contract specification, and a ruling on which market series S-family tests read | Change | Thesis v1.5 decision 4 | TradeIntel TD-032 closed | Harshad · research seat for the series ruling |
| TR-004 | **A sold option.** `ctr_v1` refuses one today; a bought option already carries the premium as its risk unit | Change | Thesis v1.5 decision 4 (J7 brought forward) | TradeIntel TD-001: the short-option R convention written | Research seat with data |
| TR-005 | **A commodity future.** The Dhan adapter maps every commodity row to an option, so a crude future cannot be represented | Bug | TradeIntel TD-025; the lane now names futures | TD-025 closed, with a fixture per shape and the Dhan golden unchanged | Harshad |
| TR-006 | **Three more never-use words in narration:** *"your plan", "your system", "your rule"* — the engine never attributes a behaviour to his intention. The Journal's own field for the stop he planned is his declaration and is unaffected | Change | Thesis v1.5 §5.3 (Annex J, J8) | The rendered-page test that fails on a never-use word extended to these | Harshad |
| TR-007 | **Correctness published, both halves.** B2's false-positive rate with its cluster envelope beside recall by effect size, on `plusev.in/research` or `/evidence` | Feature | Thesis v1.5 decision 6; site register C65 (held) | TradeIntel TD-033: recall written up and signed; C65 moved to true | Research seat signs · founder publishes |
| TR-008 | **Flow order change.** The risk number moves from before the reveal to right after it; what-we-can-check becomes one line on the guess screen. The aha comes first, and the PRD v1.2 order (risk budget → eligibility → Mirror) changes in the next PRD | Change | Flow map, frozen 24 Oct; now handoff §5 | Budget route reached from the reveal; eligibility summary line on the guess screen; full list one tap away | Harshad |
| TR-009 | **The ten guess labels.** Written and frozen by the research seat before the first session; the label set is the instrument the gate reads | Process | Flow map; v2 intake register §4.1 | Labels frozen, with "I don't know" as its own option | Research seat |
| TR-010 | **The demo lives on the website**, beside the Scope page, on a sample trader with a planted flaw; stores nothing | Feature | Flow map | Synthetic history and planted truth frozen; built in plusev-web | Founder · engineer |
| TR-011 | **The Mirror as the Scope.** The seven sections in four chapters (Where your results came from · Your patterns · Your behaviour · What we couldn't read). The Scope is a dial: Home in four chapters, a chapter re-divides into its facts, a fact shrinks the dial to a lens over a page with every trade behind it. Two taps to any fact; nothing tappable on a fact but the lens and path. Mirror wording unchanged | Change | Design phase 24–27 Oct; spec in `claude/scope_engineering_handoff_v1.md` §4–§7 | Handoff §11 checks pass; every Mirror sentence still matches `mirror.html`; every Mirror line still emits its dwell event | Founder (design) · engineer builds |
| TR-012 | **Backend for the new Scope.** B1 instrument symbol · B2 chart series · B3 trade lists for strike rate, losing run and busiest day · B4 Accurate / Not sure / Wrong · B5 fills under each trade · B6 the guess · B7 the leaving card | Feature | Backend check against TradeIntel main (1020a3c), 24–27 Oct; handoff §9 | Each with a migration where needed, a route and a fixture; v1 may ship without B5 and keep the trade list as the end | Engineer |
| TR-013 | **₹ renders in a fallback font.** The self-hosted Plex and Source Serif files in the app, and plusev-web's `next/font` subsets, are latin only; ₹ (U+20B9) is in latin-ext | Bug | Font check, 26–27 Oct | latin-ext WOFF2 files added in `api/static/fonts/`; `subsets: ["latin", "latin-ext"]` in plusev-web `app/layout.tsx` | Engineer |
| TR-014 | **Consent v1 and the site chrome are not on `main`.** 26 files are modified in the founder's local TradeIntel working tree (consent v1 reviewed by Rikk on 22 Oct; the navy hero chrome on every template) | Process | Repo check, 27 Oct | Committed and pushed; `git status` clean | Founder |

## Done in this change (24 Oct), recorded so the next PRD does not re-open them

| # | Item | Where |
|---|---|---|
| TR-D1 | "Nothing you have reads it" removed from the Scope page and the house page — journals do read the tradebook | plusev-web `content/copy.ts`, `content/house.ts` |
| TR-D2 | SEBI figures taken from SEBI's own studies; register C10 true; still off the Scope page | plusev-web `content/claims.ts` |
| TR-D3 | First lane widened to NSE crude in the instruments list, locked to register C18 by its test | plusev-web `content/instruments.ts` |
| TR-D4 | Register C23's evidence corrected (B2 is built); C65 added, held | plusev-web `content/claims.ts` |

## Done in the design phase (24–27 Oct)

| # | Item | Where |
|---|---|---|
| TR-D5 | Sign-up and sign-in match the code (login id and password); every email promise removed from the design — there is no email in v1 (ADR-007) | Handoff §5, §6 |
| TR-D6 | Every existing screen in the design uses the app's own wording | Handoff §6 |
| TR-D7 | Deletion gate run on the server through the page, 22 Oct | TradeIntel `docs/runbooks/deletion-log.md` |
