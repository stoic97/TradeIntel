# PlusEV Scope — engineering handoff

_v1 · 27 October 2026 · For the engineer building the new Scope UI and taking it live. **This is the one document to work from.** It replaces the navigation spec, user story, flow map, backend-gaps note, UI engineering plan, design-prompt kit, app–site connection note and launch runbook (all removed from the project on 27 Oct; their content is folded in here). Checked against `stoic97/TradeIntel` `main` at 1020a3c and `stoic97/plusev-web` `main` at 9bde8af, plus the founder's local working tree._

**Where it lives:** in the repo at `docs/product/scope_engineering_handoff_v1.md`, with the testing register beside it, and in the claude.ai Project "TradDNA" (ask the founder for access to read the PRD and other Project docs named in §15). Keep the two copies the same.

**If anything elsewhere disagrees with this document, this document wins.** That includes the design kit's README, older PRD text and any canvas note. Raise a conflict with the founder instead of guessing.

---

## 1. What you are building

PlusEV Scope reads a trader's broker tradebook, rebuilds his trades and shows him what they actually did, with every number opening to the trades behind it. v1 shows **the Mirror only**: the nine counted facts TradeIntel already computes. This build gives it a new interface:

- **The Scope:** a circular instrument that tells the Mirror's story in four chapters. Tap a chapter and the dial re-divides into that chapter's facts; tap a fact and the dial shrinks to a lens while the fact page tells it in full, down to every trade.
- **The aha:** right after upload, the trader guesses, then sees that his five worst days were most of his whole result.
- **Three words:** calm, precise, honest. The test: a sceptical trader trusts it within ten seconds.

The backend already computes every figure. This is mostly a **frontend rebuild inside the existing stack** plus seven small backend items (§9) and five new screens.

## 2. Where things stand

| Thing | State | Evidence |
|---|---|---|
| Code for import, accounts, consent, upload, Mirror, Journal, eligibility, deletion | Built and merged; about 700 tests | `main` |
| App on the droplet `139.59.38.160`, Caddy, systemd, backups | Running | `deploy/`, `docs/runbooks/deploy.md` |
| Deletion gate on the real server | **Done 22 Oct** through the page | `docs/runbooks/deletion-log.md` |
| Consent text reviewed (v1, read by Rikk on 22 Oct) | **Done, on `main`** (PR #2, 27 Oct) | `accounts/consent.py` |
| Site chrome in the app (navy hero, stacked lockup, Plex fonts) | **Done, on `main`** (PR #2) | `base.html`, `scope.css` |
| Link from plusev.in to scope.plusev.in | In `plusev-web/content/copy.ts` | — |
| `scope.plusev.in` with TLS | Believed live (the deletion gate ran through the page); **verify**: `dig +short scope.plusev.in` → `139.59.38.160`, padlock in a browser | — |
| New Scope UI | Designed and prototyped; **not built** | §3, step 2 |

## 3. Step 0: before you write code

| # | Who | Action |
|---|---|---|
| 1 | Founder | ~~Commit and push consent v1 and the site chrome~~ **Done 27 Oct, PR #2.** |
| 2 | Founder | **The design in the repo.** Done: `docs/design/screens/` (81 screens, pre-polish look) and `screens/latest/` (final dial and motion), with `docs/design/README.md` saying which to trust. **To follow:** the engineering kit in `docs/design/scope-kit/` and the final full export replacing `screens/`. |
| 3 | Founder | **Share the two Claude Design canvases with the engineer** (Share menu on each): "PlusEV Scope Prototype" (the clickable prototype, Play mode) and "PlusEV Scope Design System" (tokens, components, brand book). |
| 4 | Founder | **Decisions in §13.** D1 and D5 answered 27 Oct; D2 is open but doesn't block Phases 0–3. |
| 4b | Founder | **Brand PR for the font rule.** The brand docs are mirrored from `plusev-web/docs/brand/` and change only by PR (their README, "How to make a change"). `BRAND_RULES_CARD.md` "How it looks" and C12 still say "Serif for display"; the 26 Oct decision (§7 here) needs a `docs/brand-…` PR with a change-log row, then the Project mirror refreshed. Not blocking the build: §7 of this document is what to build. |
| 5 | Engineer | Read this document, open the prototype in Play, then open `docs/design/scope-kit/components.html` and `screens/preview/` in a browser. |

## 4. Navigation: the Scope

### Levels

| Level | Screen | What's on it | Tap goes to |
|---|---|---|---|
| 1 | **Scope home** | The dial in four equal chapters on a navy stage; the headline figure in the white centre disc; below on white, the Mirror's opening line and the gross line | A chapter |
| 2 | **Chapter** | The dial re-divided into that chapter's facts (2–4); the ink arc on the rim shows where the chapter sat on Home; the centre ring holds the chapter name and "Scope". Below on white: one story card per fact, in slice order, then "Does this match your trading?" (chapters 1–3) | A fact (slice or story card); the centre goes back to Home |
| 3 | **Fact** | White page. The 56 px lens pinned top-left with the path beside it on one line (`Scope › Where your… › Your worst trading days`); the Mirror's sentences, figures, tables; then "The trades behind this": every trade, never a sample | Nothing except the lens and the path |

**Two gestures only.** Scope in: tap a slice or a story card. Scope out: tap the centre ring, the lens or a path segment. The phone's back gesture goes up one level (real URLs, §8). **Two taps from Home to any fact; never more than three.** No search, filters, tabs, dropdowns, text fields, next/previous fact or "related" anywhere in the Scope.

### Chapters and facts (the Mirror's own headings)

| # | Chapter | Facts, in slice order | Fact key |
|---|---|---|---|
| 1 | Where your results came from | Your worst trading days · Share of your result · Where the money came from | `worst-days` · `share` · `money` |
| 2 | Your patterns | How long you hold · Strike rate · Longest losing run · The clock | `hold` · `strike` · `run` · `clock` |
| 3 | Your behaviour | Trading on while already down · Your busiest day | `down` · `busiest` |
| 4 | What we couldn't read | What we could not read · Trades with a risk figure · What we have not told you | `unread` · `risk` · `not-told` |

Opening all four chapters covers the whole Mirror. Chapter 4 is the honest close and has no feedback question.

### States and edge cases

| Case | Behaviour |
|---|---|
| Not enough trades for a fact | The slice and card still appear, in the "not enough trades yet" state ("[N] trades, and it needs [N]."). Never hidden, never an all-clear |
| Field not in the file (e.g. no stop column, no budget) | "Not in your file" state; "We do not estimate what is not in your file." |
| Under two trades on a normal day | Day views switch to per trade and say so |
| Instrument not set up | `mirror_no_profile` page in place of the Scope |
| No trades rebuilt | `mirror_empty` page in place of the Scope |
| Arriving straight at a fact (from the reveal or a link) | Lens and full path shown at once |
| No finding | Never "No issues detected" |

Result states differ in border, fill and marker, not colour alone: **counted · not enough trades yet · not in your file**. A fourth, *not yet tested*, is reserved for the research spec and not used in v1.

### Scaling later (not v1; build so it fits)

The dial takes 2–5 sectors. Later: Risk becomes a fifth chapter; a chapter past five facts gains groups (three taps); the fact page gains the research record's slots above the trades. Same components.

## 5. Screens and routes

Screen numbers match the PNG names in `docs/design/screens/`. **Routes here override the kit README's proposals.** Stage = navy; record = white.

| # | Screen | Route | Status | Notes |
|---|---|---|---|---|
| 0 | Front door, signed out | `/` | Restyle `home.html` | Navy door |
| 1 | Scope page | plusev.in/scope | Restyle (plusev-web) | Navy door |
| 2a–2c | Demo on an invented trader: guess, reveal, its trades | plusev.in/scope | New (plusev-web, static) | Stores nothing; TR-010 |
| 3 | Create your account | `/invite/{code}` | Restyle | Name, login id, password (≥ 12). **No email anywhere in v1** (ADR-007) |
| 4 | Sign in | `/login` | Restyle | One error for any failure |
| 5, 5b, 5c | Consent, what you agreed to, consent declined | `/consent`, `/settings/consent` | Restyle; 5c new | Consent text in full from `consent.py` |
| 6, 7a, 7b, 7c | Upload, broker not open, not a tradebook, Scope not open | `/upload` | Restyle | |
| 8 | Calculating | during `POST /upload` | New | D1 = (a): the strip animates as "Reading your file" while the request runs, then the real final counts; no live counts, no backend change |
| 9 | Import check | `/imports/{id}` | Restyle | Exit goes to 10, not 13 |
| 10 | Guess | `/guess` | New | B6; labels TR-009 |
| 11 | What we can check | `/eligibility` | Restyle | One tap from the guess; back returns to the guess |
| 12 | The reveal | `/mirror/reveal` | New | §7 |
| 13 | One number | `/budget` | Restyle; moved | Now straight after the reveal (TR-008) |
| 14 | Scope home | `/mirror` | New | Replaces the long Mirror page |
| 15 | Chapter 1–4 | `/mirror/chapter/{n}` | New | |
| 16 | Fact (12) | `/mirror/fact/{key}` | New | Keys in §4 |
| 17 | Accurate / Not sure / Wrong | `POST /mirror/chapter/{n}/feedback` | New | B4 |
| 18, 18b, 18c | Journals, one Journal, earlier Journals | `/journals`, `/journals/{id}`, `/journals/catch-up` | Restyle | WTP question stays inside the Journal |
| 19 | Leaving card | top of `/journals`, once, after the first Journal | New | B7; D2 |
| 20 | Home, signed in | `/` (signed in) | New | Headline card, latest Journals, upload |
| 21, 21b, 21c | Account, delete, deleted | `/account`, `/account/delete` | Restyle | Delete is one page with a checkbox |
| Edge | Six edge-state screens | as above | New / restyle | §4 |
| Desktop | Scope home, Chapter 1, worst-days fact at 1440 | same routes | New | Dial beside the story |

**Journey order:** sign up → consent → upload → calculating → import check → guess → reveal → one number → Scope home → Journal → leaving card. `landing_for()` in `routes_identity.py` decides where a returning trader lands.

**Navigation chrome:** in-app pages use a bottom nav **Scope · Journal · Account** (Scope active in blue). Sign out moves to the Account page (D6). Fact pages have no bottom nav.

## 6. Wording

| Source | Used for | Rule |
|---|---|---|
| `templates/mirror.html` (and the drawer captions in `routes_mirror.DRAWERS`) | Every Mirror sentence, heading and table label | **Word for word.** Only the figures are variables |
| The app's other templates and `accounts/consent.py` | Every other existing screen | **Word for word**, including the consent text, delete page, upload-closed and instrument pages |
| `docs/design/scope-kit/README.md`, new-copy list | Lines the app has no wording for (captions, card lines, guess, calculating, leaving card, signed-in home) | **Pending copy-owner sign-off (D9).** Build with them; don't invent more |
| `journal/prose.py`, `journal/wtp.py`, `routes_journal.PER_TRIP_PROMPTS` | Journal sentences, the price question, per-trade questions | As in code |
| `Brand Strategy/BRAND_RULES_CARD.md`, "The words" | Tagline "See what your tradebook has been hiding.", status line "In development.", master message, "No buy or sell calls, ever.", the honest-limit line, the CTA | Fixed, verbatim; only the founder changes them |

**Never:** guaranteed, profitable, winning, signal, tip, guru, mentor, fund, platform, tilt, emotional, psychology, disease, cure, DNA, revenge, "AI-powered", a bare "R", any opening date, a score or grade, a cause, advice, a comparison with other traders, "No issues detected", "your plan / your system / your rule" (TR-006). The existing no-claims test enforces most of this; extend it to every new template.

**No line may promise an email.** There is no email service (ADR-007). The deletion page is the receipt.

## 7. Visual design

The design system canvas is the reference; `docs/design/scope-kit/tokens.css` is the code form. The rules in short:

**Colour roles**

| Role | Hex | Use |
|---|---|---|
| page | `#FFFFFF` | White record |
| surface | `#F5F8FD` | Cards, story cards |
| hairline | `#DDE4F1` | Rules, tracks |
| ink | `#0B1733` | All body text; the navy stage |
| muted | `#3F4F82` | Inactive bottom-nav tabs only |
| faint | `#5D6B96` | Small labels, column heads (4.92:1 on surface) |
| action blue | `#04408D` | Only things you can tap, on white |
| gain / loss | `#0D7A3F` / `#B42318` | Only signed rupee figures, on white |
| building | `#8A5A00` | Only a ledger state still in progress. Under D1 (a) Calculating has no moving counts, so it doesn't use it |

- **Navy for the stage and the doors, white for the record.** Navy: Scope home and chapters (the dial), the reveal, the front door and the Scope page. Everything else is white.
- **On navy, taps are white,** never blue. Rupee figures on navy are white with their sign; they turn red/green again on the white story card below.
- **Body text is ink.** The gross line is one plain 13 px ink line, never a box: "Your export has no charges column, so every rupee figure below is gross — before brokerage and taxes. We do not estimate what is not in your file."
- **Fonts:** IBM Plex Mono for every number, figure, state and label (tabular figures); IBM Plex Sans semibold for headings and UI; Source Serif 4 only for the Mirror's sentences. Self-hosted only, **with latin-ext** so ₹ renders (§8, T2).
- **Type scale:** mono hero 56 / large 32 / medium 22 / small 15 / label 11; Sans title 34 / heading 22 / card title 17 / UI 15; serif 22 on fact pages, 19 on cards; gross line 13.
- Spacing on a 4 px base; card radius 16; controls pill; at most two elevation levels; hairlines 1 and 1.5 px. No gradients, glow, glass or shadows beyond elevation 1. One motion per screen. Touch targets ≥ 44 px; text ≥ 4.5:1.
- **The mark:** the bracket mark already in `base.html` (D5). Lockup: the mark at the wordmark's height, "PlusEV" in Plex Sans semibold, "Scope" beneath in Plex Mono; ink on white, white on navy; the mark alone only for favicon, app icon and tab.

**The Scope dial** (geometry functions in `scope-geometry.js`, to port to Python):
- Phone dial 260 px; lens 56 px; desktop dial 440 px in a 640 px stage, story beside it.
- Bezel: outer tick ring with three weights (major at each divider, mid every 30°, minor between), white hairlines at reduced opacity on navy; a thin inner ring where the ink arc runs. Dividers stop short of the centre and the bezel.
- **Names are upright and horizontal, never curved.** Each sits outside the bezel at its slice's arc midpoint on a 12 px hairline leader. Right half: left-aligned. Left half: right-aligned. Twelve or six o'clock: centred. On Home they sit in the four corners. Two lines maximum; three allowed only for "Where the money came from", "Where your results came from" and "What we have not told you".
- **Slice contents** are upright and centred on the bisector: slice number on its own line 4 px above the figure, then the figure, then a mini chart (≤ 24 px, white on navy). Home slice figures ≥ 18 px, never smaller than the names.
- **Stacked figures:** one line where the wedge holds it; otherwise the head at figure size with the rest beneath in 11 px mono ("[N]" over "of [N]"; "[N]·[N]" over "min"). Layout must run on real values, which is why the geometry runs on the server.
- Chapter fact positions after scope-in: 1 fact at twelve; 2 at twelve and six; 3 at twelve, four and eight; 4 on the diagonals.
- States: pressed (wedge lifts one tone), focus (ring just inside the wedge edge, white on navy), opened (a dot near the rim, reading progress, never a score).

**The reveal (12, and 2b in the demo):** navy screen; "You guessed: [label]." small at top; the dial with the five worst days as one white slice from twelve o'clock to their share, the [N]% in the white centre; then the Mirror's two sentences; "Show me those days" (white button → worst-days fact with lens and path) and "Continue" (→ one number). **Second state** when `ShareOfTotal.shown_as_percentage` is false: no slice, no figure in the centre, and the Mirror's other sentence ("Your result for the whole period was −₹[X]. The other [N] days were net ±₹[X].").

**Fact page:** hero figure 56 (32 on How long you hold, shown as "[N] min · [N] min" over "winners · losers"); 32 px around it; the gross line straight under the sentences; figures 96 px tall with a mono "Figure N · …" caption, tables labelled "Table N"; then 72 px and a 3 px ink rule before "The trades behind this". Each day's header (and the column heads) is pinned under the lens bar while its trades scroll. Each trade: its label line, one row (Trade · In · Out · Held · Net (gross)), its trade strip drawn to time, its fills (Time · Side · Qty · Price · Row in your file).

**Calculating (8), per D1 (a):** white; the trade strip as hero. While `POST /upload` runs, the strip animates as an illustration (fills landing as dots, a pause, then the bar) under "Reading your file", **with no counts**: the import is synchronous, so none exist yet. When the response arrives, show the real final "Rows read [N] of [N]" and "Trades rebuilt [N]" in mono 22, ink, the latest rebuilt trade drawn in the strip, "Every row is accounted for on the next screen." and "Continue". Don't use the prototype's "Still counting. These figures come from the server as it reads." line or the amber counts: under (a) they would describe something that doesn't happen. **Never show a figure the server hasn't reported.** **No polling:** the kit's README describes polling every 2 s with a 204 while reading; that needs a background job (D1 option b) and is **not** used. Under (a), post the upload with HTMX (`hx-post`, the reading state as the `hx-indicator`), and answer with the done state, whose Continue goes to `/imports/{id}`; without JavaScript the form posts normally and lands on `/imports/{id}` as today. The done-state heading "Your file is read." is new copy (D9).

**Motion**

| Transition | Duration | What happens |
|---|---|---|
| Scope in (tap a chapter) | 480 ms, ease-in-out | 0–120: tapped wedge lifts, others fade to 20%, names fade out, old centre text fades out by 240 · 120–320: the whole dial, ticks included, rotates the wedge's midpoint to twelve · 320–480: wedge opens to the full circle, new dividers draw in from the centre 40 ms apart, ink arc draws, new names and centre text fade in |
| Scope out (tap the centre) | 480 ms | Exact reverse |
| Shrink to lens (tap a fact) | 400 ms | Wedge turns blue; the navy stage's bottom edge rises to become the lens bar while the dial shrinks into the lens; the navy wipes off the bar; title and figure rise 16 px (no fade) |
| Back from a fact | 400 ms | Exact reverse: the navy grows down from the lens bar |
| Fills land | 40 ms per dot, 160 ms pause, 200 ms bar | Calculating and trade strips |
| Number count | 600 ms | Figures counting up (real values only) |
| Reduced motion | 120 ms crossfade | Nothing moves |

## 8. Technical approach

Stack stays: FastAPI + Jinja + HTMX, one stylesheet, `dwell.js`. No SPA, no chart library, no CDN. The rendered HTML may reference no absolute URL except `https://plusev.in` (`tests/unit/api/test_app_skeleton.py`).

| # | Decision |
|---|---|
| T1 | Tokens as CSS custom properties: bring `tokens.css`, `components.css` and `motion.css` from the kit into `static/`; retire the old `scope.css` rules they replace |
| T2 | **Fonts: add the latin-ext WOFF2 files** for IBM Plex Sans, IBM Plex Mono and Source Serif 4 to `api/static/fonts/` (the current files are latin only, so ₹ falls back to a system font). Same fix in plusev-web: `subsets: ["latin", "latin-ext"]` in `app/layout.tsx` (three places) |
| T3 | The dial is **server-rendered SVG** from one Jinja macro backed by a Python port of `scope-geometry.js` (`services/production/api/scope_geometry.py`), measured with real values. Unit-test the port against the JS on the kit's sample values |
| T4 | Charts are server-rendered SVG macros (share bar, daily net, diverging best/worst, paired bars, trades per day, by hour, run squares, hold dots, trade strip) |
| T5 | Real URLs per level (§5) so back, deep links and the reveal's link work |
| T6 | Motion with the View Transitions API via `hx-boost` and HTMX `transition:true`, CSS from `motion.css`; unsupported browsers switch instantly. The kit's `?enter=` parameter tells the page which transition to play |
| T7 | Pages format, they don't compute: fact pages read `_mirror_context()` and the existing trade lists. One place decides each figure (`mirror/metrics.py`) |
| T8 | `base.html` gets two blocks, `stage` (navy) and `content` (white), chosen per page; the bottom nav replaces the header nav in-app |

## 9. Backend work (testing register TR-012)

| # | Item | Size | Notes |
|---|---|---|---|
| B1 | Instrument symbol on each trade | XS | `trip.symbol` into `mirror/loader.py` and `mx.Trip` |
| B2 | Chart series: net and trade count per trading day; minutes held per trade | S | From `Trip.trading_day`, `net`, `holding_seconds`; `_by_day` exists |
| B3 | Trade lists for strike rate, longest losing run, busiest day | S | New `DRAWERS` keys; data exists (`LosingRun.trip_ids`, day counts, win/loss); captions from the kit's new-copy list |
| B4 | Accurate / Not sure / Wrong: table, migration, endpoint; one answer per chapter (1–3) per trader; three optional reasons | S | Wrong facts · Right facts, wrong reading · I've already changed this |
| B5 | **Fills under each trade**, with "Row in your file" | L | `RoundTrip.fill_ids` exists at reconstruction but the `trip` table doesn't keep it; needs a migration (trip → fill link, parsed fill fields) and a route. **May follow v1** (D4): the trade list is then the end of a fact page |
| B6 | The guess: table + route; one answer (a label or "I don't know") before the reveal | S | Labels from TR-009 |
| B7 | Leaving card: the answer and a "shown once" flag | XS | |

Dwell events stay as they are, keyed by fact page (`surface: mirror_line`).

## 10. Build phases

| Phase | What | Done when |
|---|---|---|
| 0 · Foundations | §3 done; T1, T2, T8; component macros (buttons, cards, table, gross line, result states, bottom nav, lens and path, trade record) | One restyled existing page matches the design system; ₹ renders in Plex |
| 1 · The Scope | T3–T5, T7 without motion; Scope home, four chapters, 12 fact pages, edge states; B1–B3; the geometry port | Every fact two taps from Home; every figure from `metrics`; wording tests pass |
| 2 · The journey | Calculating, guess, reveal (both states), one-number move, signed-in home, front door; B4, B6 | The flow plays end to end on the synthetic 40-trade history |
| 3 · Motion | T6 for every transition in §7; reduced motion | Plays on Chrome and Safari; instant elsewhere |
| 4 · Restyle the rest | Every remaining existing page, the leaving card (B7) | The brand checks in §11 pass on every page |
| 5 · Fills (B5) | Migration, route, trade records with fills | Every fact page shows fills (can follow v1) |
| 6 · Check and ship | Browser walk, the ten-second test with 3–5 traders, deploy (§12) | §12 verification passes |

## 11. Tests and checks

- Every Mirror sentence on the Scope pages matches `mirror.html` word for word (extend the existing wording tests); every existing screen keeps the app's wording.
- The no-claims / never-use test runs over every new template.
- The no-absolute-URL test covers every new page.
- Each fact page lists every trade behind it; the count matches the fact.
- The reveal shows the second state whenever `shown_as_percentage` is false.
- Feedback: one answer per chapter per trader; reasons optional.
- The geometry port matches the JS for the kit's sample values; no label collides at 2, 3, 4 or 5 sectors.
- Manual: 390 px wide with no sideways scroll (tables scroll inside their box); contrast ≥ 4.5:1; reduced motion; back gesture goes up one level; only the lens and path are tappable on a fact page.

## 12. Ship it

Deploy as `docs/runbooks/deploy.md` describes (as root on the droplet; migrations for B4–B7 are applied by `init-db`, which calls `run_migrations`):

```
cd /srv/scope && git pull
UV_PYTHON_INSTALL_DIR=/opt/uv/python uv sync --frozen --no-group research
chown -R scope:scope /srv/scope
sudo -u scope env $(grep -v '^#' /etc/scope/scope.env | xargs) \
    .venv/bin/python -m services.production.api.cli init-db
systemctl restart scope && journalctl -u scope -n 20 --no-pager   # wait for "Application startup complete"
```

**Verify, in order:**
1. `dig +short scope.plusev.in` → `139.59.38.160`; `https://scope.plusev.in` loads with a padlock.
2. `make test` green in TradeIntel; `npm run lint && npm run typecheck && npm test && npm run build` green in plusev-web.
3. A real (not development-data) account reaching `/consent` sees the consent page, not "Scope is not open yet".
4. On the server, with a fixture account: sign up → consent → upload `data/fixtures/demo/demo_tradebook.csv` → calculating → import check → guess → reveal → one number → Scope home → each chapter → each fact → Journal → leaving card → delete. Then add a row to `docs/runbooks/deletion-log.md`.
5. ₹ renders in Plex on the server (not a fallback font).
6. `/scope/data` on plusev-web, the consent text and `docs/runbooks/data-flow-map.md` say the same thing about storage, access and backups.
7. Invite the first trader with the `invite --code <code>` command from `deploy.md` §4 (it prints a `127.0.0.1` URL; substitute `https://scope.plusev.in`), and send code and link together.

## 13. Decisions

| # | Decision | Options | Recommendation | Answer |
|---|---|---|---|---|
| D1 | **Calculating**: the import runs synchronously inside `POST /upload`, so no live counts exist while it runs | (a) Show the strip as a plain "Reading your file" state during the request, then the real final counts on arrival; (b) background job + progress endpoint | (a) for v1 | **(a)**, founder, 27 Oct |
| D2 | **WhatsApp link** on the leaving card is an absolute URL the skeleton test refuses | (i) the founder's WhatsApp group, `https://chat.whatsapp.com/KKn9At6cW5JJlkkB3uamGr` (tracking parameters removed); (ii) a 1:1 chat, `https://wa.me/<number>`, which matches the 24 Oct rule "1:1 WhatsApp before any group"; (iii) `mailto:team@plusev.in` | Either WhatsApp option needs the host exempted by name in `test_app_skeleton.py` (as `plusev.in` is) and a row in the data-flow map | **Open**, founder. Needed by Phase 4 (leaving card) |
| D3 | **Guess labels and question** (TR-009) | Research seat freezes them; build with placeholders | — | |
| D4 | **Fills (B5)** in v1 or after | Ship v1 with the trade list as the end of a fact page | After v1 | |
| D5 | **The mark**: the app and plusev.in draw the bracket-and-dots mark; the design drew a bar-with-dots glyph | Pick one | — | **The bracket mark** (`plusev-web/app/mark.tsx`, already in `base.html`), founder, 27 Oct. The trade strip is the product's motif only (loader, trade records, motion), never the logo |
| D6 | **Sign out** once the header nav goes | On the Account page | Account page | |
| D7 | ~~"In development." tag~~ | **Resolved:** it is the brand's fixed status line (`BRAND_RULES_CARD.md`, changeable only by the founder). Keep it | — | Keep |
| D8 | **₹[price] in the willingness-to-pay question** vs the "no cost figure" brand rule | Keep the figure (research question) or drop it | — | |
| D9 | **New copy** in the kit's list | Copy owner signs off before Phase 4 | — | |
| D10 | ~~The founder's WhatsApp link~~ | Folded into D2 | — | — |

## 14. Open tickets that are not this build

- **TD-023:** the B2 recall test doesn't reproduce from the repository (the one known red).
- **TD-029 / TD-024:** Dhan's `Quantity/Lot` meaning for size figures.
- **TD-031:** plain names for the 19 library checks on the eligibility page (it shows identifiers today).
- **TD-030:** B12's `20/40_days` reading.
- MCX crude tick size and NIFTY lot size for further instrument profiles.
- Testing register TR-001 to TR-007 (costs, two-readout test, NSE crude, sold options, commodity futures, never-use words, correctness published).

## 15. Documents

**Read these** (claude.ai project "TradDNA" unless a repo path):
- This document.
- `claude/scope_testing_register_v1.md` (repo copy: `docs/product/scope_testing_register_v1.md`): every open bug, feature and change; new items go here.
- Frozen PRD `scope_prd_v1_2_frozen.md` and `claude/scope_prd_v1_2_amendments.md`: product rules not restated here.
- `claude/trade_dna_product_thesis_v1.5.md` and `trade_dna_research_spec_v1_0.md`: background only; nothing in this build depends on them.
- `Brand Strategy/BRAND_RULES_CARD.md` and `C12_distinctive_assets_v1_2.md`: brand rules. **Typography is as in §7 of this document** (decided 26 Oct; it replaced "serif for display").
- Repo: `docs/runbooks/` (deploy, data-flow map, deletion), `docs/adr/` (ADR-007 is the runtime), `docs/deferrals.md` (TD tickets), `docs/design/` (the kit and the screens, after §3).

**History, don't build from:** `scope_v1_build_plan_v1.md`, `scope_v1_technical_design_v1.md`, `scope_v1_build_completion_v1.md` (its "nothing deployed" status is out of date), `scope_thin_slice_plan_v1.md`, the `_v1_1` brand files where a `_v1_2` exists, and the older Phase 0 and thesis files.

## 16. Decision log (design phase, 24–27 October 2026)

| Date | Decision |
|---|---|
| 24 Oct | Risk number moves to straight after the reveal; what-we-can-check becomes one line on the guess screen (TR-008). Research seat freezes the ten guess labels (TR-009). The demo lives on the website (TR-010) |
| 26 Oct | The Mirror's seven sections become four chapters; Home → chapter → fact, two taps (TR-011). v1 shows the Mirror only; the shell scales to five chapters and groups |
| 26 Oct | Fonts: Plex Mono for numbers, Plex Sans for headings and UI, Source Serif 4 only for the Mirror's sentences. Three words: calm, precise, honest |
| 26 Oct | The Scope is the interactive stage: a dial divided into chapters that re-divides into facts on tap (replaces the 2×2 card grid and the aperture path) |
| 27 Oct | Sign-up and sign-in match the code: login id and password, no email; every email promise removed (ADR-007) |
| 27 Oct | Every existing screen uses the app's own wording; the deletion and instrument pages use the code's text exactly |
| 27 Oct | Navy for the stage and the doors, white for the record; body text in ink; the gross line as one plain line |
| 27 Oct | Reveal: the dial version, with a second state when the share isn't a percentage |
| 27 Oct | Fact page: single measure, figure as hero, pinned day headers, tighter trade records |
| 27 Oct | Dial names upright and horizontal at arc midpoints; slice numbers on their own line; stacked figures on purpose |
| 27 Oct | Motion: scope-in rotates the dial like a focus ring; shrink-to-lens collapses the navy upward; no colour crossfades |
