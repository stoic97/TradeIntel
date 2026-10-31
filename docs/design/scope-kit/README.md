# PlusEV Scope — engineering kit

Plain files for a FastAPI + Jinja + htmx app. No React, no framework, no CDN, no external URLs:
every asset is served from `/static/`. Built from the PlusEV Scope design canvas and the
PlusEV Scope Design System (tokens and rules).

## Files

```
plusev-scope-kit/
├── README.md                     this file
├── components.html               every component as a plain HTML snippet, with its states (open in a browser)
├── static/
│   ├── css/
│   │   ├── tokens.css            every design-system token as CSS custom properties + @font-face
│   │   ├── components.css        every component, BEM classes named after the design system
│   │   └── motion.css            scope-in, scope-out, shrink-to-lens, fills-land, number-count, reduced motion
│   ├── icons/
│   │   ├── mark.svg              the PlusEV mark alone, currentColor
│   │   ├── favicon.svg, favicon-16.svg, favicon-16/32/48.png   white mark on a navy tile
│   │   └── app-icon.svg, app-icon-180/192/512.png               white mark on navy, full bleed (the OS rounds it)
│   ├── js/
│   │   └── scope-geometry.js     pure functions: dial layout, names, leaders, stacked figures, ticks, lens, charts, trade strip
│   └── fonts/
│       └── README.md             the 14 WOFF2 files to add (not included) and where to get them
└── screens/
    ├── *.html                    one Jinja template per screen (56) — phone screens, edge states, 3 desktop screens
    └── preview/*.html            the same templates rendered with placeholder values ([N], −₹[X], [dd mmm]) to look at
```

Two files you add yourself: the fonts (see `static/fonts/README.md`) and `static/js/htmx.min.js`
(self-hosted htmx 1.9 or 2.x; every screen loads it with `defer`).

## How the screens work

* Each file in `screens/` is a Jinja2 template and a complete page: it links `tokens.css`,
  `components.css` and `motion.css` and nothing else. No inline styles.
* Every value the server fills is written `{{ name }}` — e.g. `{{ share_percent }}`,
  `{{ five_day_sum }}`, `{{ whole_period_result }}`. Lists use `{% for %}`
  (`worst_days`, `trade_groups`, `latest_journals` …); states use `{% if %}` (`errors.password`,
  `share_shown`, `done`, `show_leaving_card` …).
* **Rupee values** come with a tone: for every rupee `x` the server also passes `x_tone` =
  `loss` | `gain` | `plain`, which picks the class `num--loss` / `num--gain` / `num--plain`
  (red and green only on signed rupees; on navy every rupee is white with its sign).
  Format rupees server-side with the sign as U+2212 (−) and the rupee sign U+20B9 (₹).
* **The Mirror's sentences** are in the templates word for word; only their figures are placeholders.
  Sentences that the engine writes itself (Journal sentences, the per-trade Mirror line) are passed in whole.
* **Owner slots** still open are left as named placeholders: `guess_question`, `guess_options`,
  `accepted_formats`, `leaving_card.*`, `founder_whatsapp_link`, `price`, `facts.*.per_trade_sentence`.
* Each template starts with a comment giving its screen and route.
* `screens/preview/` renders every template with sample placeholders (no trader numbers) so the
  pages can be checked in a browser; serve the kit root (`python -m http.server`) and open
  `/screens/preview/14-scope-home.html`. Delete the folder in the app.

## Screens → routes

Routes are proposals that match the prototype's flow; rename freely. `?enter=` parameters drive
the motion (see Motion).

| Template | Screen | Route |
|---|---|---|
| `screens/00-front-door.html` | 0 · scope.plusev.in · signed-out front door | `GET /  (signed out)` |
| `screens/01-scope-page.html` | 1 · Scope page (plusev.in) | `GET https://plusev.in/scope  (marketing site; same templates)` |
| `screens/02a-demo-guess.html` | 2a · Demo · guess | `GET /demo` |
| `screens/02b-demo-reveal.html` | 2b · Demo · reveal | `GET /demo/reveal?guess=…` |
| `screens/02c-demo-trades.html` | 2c · Demo · the trades | `GET /demo/trades` |
| `screens/03-create-account.html` | 3 · Create your account | `GET /invite/{code} · POST /invite/{code}` |
| `screens/04-sign-in.html` | 4 · Sign in | `GET /login · POST /login` |
| `screens/05-consent.html` | 5 · Before you upload (consent, in full) | `GET /consent · POST /consent` |
| `screens/05b-consent-ledger.html` | 5b · What you agreed to (consent ledger, from Account) | `GET /account/consent` |
| `screens/05c-consent-declined.html` | 5c · Consent declined | `GET /consent/declined` |
| `screens/06-upload.html` | 6 · Upload | `GET /upload · POST /upload` |
| `screens/07a-uploads-closed.html` | 7a · We cannot take a file from your broker yet | `GET /upload  (broker not checked)` |
| `screens/07b-not-a-tradebook.html` | 7b · What we read · not a tradebook | `GET /imports/{id}  (rejected)` |
| `screens/07c-not-open.html` | 7c · Scope is not open yet | `GET /consent  (consent page not yet checked)` |
| `screens/08-calculating.html` | 8 · Calculating (reading · done) | `GET /imports/{id}/reading  ·  hx-get /imports/{id}/status every 2 s (204 while reading, the done fragment when finished)` |
| `screens/09-import-check.html` | 9 · What we read (import check) | `GET /imports/{id}` |
| `screens/10-guess.html` | 10 · Guess | `GET /guess` |
| `screens/11-what-we-can-check.html` | 11 · What we can check (eligibility) | `GET /eligibility` |
| `screens/12-reveal.html` | 12 · The reveal (share / no share) | `GET /reveal?guess=…` |
| `screens/13-what-you-risk.html` | 13 · What you risk (one number) | `GET /risk · POST /risk` |
| `screens/14-scope-home.html` | 14 · Scope home | `GET /scope` |
| `screens/15-chapter-1-results.html` | 15 · Chapter 1 · Where your results came from | `GET /scope/results` |
| `screens/15-chapter-2-patterns.html` | 15 · Chapter 2 · Your patterns | `GET /scope/patterns` |
| `screens/15-chapter-3-behaviour.html` | 15 · Chapter 3 · Your behaviour | `GET /scope/behaviour` |
| `screens/15-chapter-4-couldnt-read.html` | 15 · Chapter 4 · What we couldn't read | `GET /scope/couldnt-read` |
| `screens/17-feedback.html` | 17 · Accurate / Not sure / Wrong (states) | `POST /scope/{chapter}/feedback  →  returns the .feedback partial` |
| `screens/16-f01-worst-days.html` | 16 · Fact · Your worst trading days | `GET /scope/results/worst-days` |
| `screens/16-f02-share.html` | 16 · Fact · Share of your result | `GET /scope/results/share` |
| `screens/16-f03-money.html` | 16 · Fact · Where the money came from | `GET /scope/results/money` |
| `screens/16-f04-hold.html` | 16 · Fact · How long you hold | `GET /scope/patterns/hold` |
| `screens/16-f05-strike.html` | 16 · Fact · Strike rate | `GET /scope/patterns/strike` |
| `screens/16-f06-run.html` | 16 · Fact · Longest losing run | `GET /scope/patterns/run` |
| `screens/16-f07-clock.html` | 16 · Fact · The clock | `GET /scope/patterns/clock` |
| `screens/16-f08-down.html` | 16 · Fact · Trading on while already down | `GET /scope/behaviour/down` |
| `screens/16-f09-busy.html` | 16 · Fact · Your busiest day | `GET /scope/behaviour/busy` |
| `screens/16-f10-read.html` | 16 · Fact · What we could not read | `GET /scope/couldnt-read/read` |
| `screens/16-f11-risk.html` | 16 · Fact · Trades with a risk figure | `GET /scope/couldnt-read/risk` |
| `screens/16-f12-not-told.html` | 16 · Fact · What we have not told you | `GET /scope/couldnt-read/not-told` |
| `screens/18-journals.html` | 18 · Your Journals | `GET /journals` |
| `screens/18b-journal.html` | 18b · One Journal (with the one question, shown once) | `GET /journals/{date} · POST /journals/{date}/note · POST /journals/{date}/trades/{n} · POST /price-question` |
| `screens/18c-earlier-journals.html` | 18c · Earlier Journals (catch-up) | `GET /journals/earlier` |
| `screens/19-leaving-card.html` | 19 · Leaving card · top of Your Journals, once, after the first Journal | `GET /journals  (show_leaving_card) · POST /leaving-card · POST /leaving-card/dismiss` |
| `screens/20-signed-in-home.html` | 20 · Home, signed in | `GET /  (signed in)` |
| `screens/21-account.html` | 21 · Account | `GET /account` |
| `screens/21b-delete.html` | 21b · Delete everything · tick the box to enable | `GET /account/delete · POST /account/delete` |
| `screens/21c-deleted.html` | 21c · Deleted | `GET /account/deleted` |
| `screens/edge-e1-slice-not-enough.html` | Edge · Slice · not enough trades yet | `GET /scope/patterns  (hold: not enough trades)` |
| `screens/edge-e2-fact-not-enough.html` | Edge · Fact · not enough trades yet | `GET /scope/patterns/hold  (not enough trades)` |
| `screens/edge-e3-slice-not-in-file.html` | Edge · Slice · not in your file | `GET /scope/couldnt-read  (risk: not in your file)` |
| `screens/edge-e4-fact-not-in-file.html` | Edge · Fact · not in your file | `GET /scope/couldnt-read/risk  (not in your file)` |
| `screens/edge-e5-per-trade.html` | Edge · Under two trades a day · per trade | `GET /scope/results  (normal day under two trades)` |
| `screens/edge-e6-no-instrument.html` | Edge · Instrument not set up | `GET /scope  (instrument not set up)` |
| `screens/edge-e7-no-trades.html` | Edge · No trades rebuilt · Your record, nothing to count yet | `GET /scope  (no trades)` |
| `screens/desktop-home.html` | Desktop · Scope home | `GET /scope  (≥ 1024 px)` |
| `screens/desktop-chapter-1.html` | Desktop · Chapter 1 | `GET /scope/results  (≥ 1024 px)` |
| `screens/desktop-fact-worst-days.html` | Desktop · Fact · Your worst trading days | `GET /scope/results/worst-days  (≥ 1024 px)` |


Desktop: the three desktop templates are the same routes at ≥ 1024 px. Choose the template
server-side (e.g. a `view=desktop` cookie set by a one-line media-query check) or merge them into
the phone templates with a media query — the components are shared.

## Component → screen

| Component | Class | Screens |
|---|---|---|
| Lockup | `.lockup` | 00-front-door, 01-scope-page, 14-scope-home, 20-signed-in-home, desktop-chapter-1, desktop-home |
| Chip | `.chip` | 01-scope-page, 02a-demo-guess, 02b-demo-reveal, 02c-demo-trades, 14-scope-home |
| Buttons | `.btn` | 01-scope-page, 02a-demo-guess, 02b-demo-reveal, 02c-demo-trades, 03-create-account, 04-sign-in, 05-consent, 05b-consent-ledger, 05c-consent-declined, 06-upload, 07a-uploads-closed, 07b-not-a-tradebook, 08-calculating, 09-import-check, 10-guess, 12-reveal, 13-what-you-risk, 15-chapter-1-results, 15-chapter-2-patterns, 15-chapter-3-behaviour, 17-feedback, 18b-journal, 19-leaving-card, 20-signed-in-home, 21-account, 21b-delete, 21c-deleted, desktop-chapter-1, edge-e1-slice-not-enough, edge-e5-per-trade, edge-e7-no-trades |
| Card | `.card` | 09-import-check, 18-journals, 18b-journal, 20-signed-in-home |
| Story card | `.story-card` | 15-chapter-1-results, 15-chapter-2-patterns, 15-chapter-3-behaviour, 15-chapter-4-couldnt-read, desktop-chapter-1, edge-e1-slice-not-enough, edge-e3-slice-not-in-file, edge-e5-per-trade |
| Figure + legend | `.figure` | 01-scope-page, 16-f01-worst-days, 16-f02-share, 16-f04-hold, 16-f05-strike, 16-f06-run, 16-f07-clock, 16-f09-busy, 16-f10-read, 16-f11-risk, desktop-fact-worst-days |
| Charts (inline SVG) | `.chart` | 01-scope-page, 15-chapter-1-results, 15-chapter-2-patterns, 15-chapter-3-behaviour, 15-chapter-4-couldnt-read, 16-f01-worst-days, 16-f02-share, 16-f04-hold, 16-f05-strike, 16-f06-run, 16-f07-clock, 16-f09-busy, 16-f10-read, 16-f11-risk, desktop-chapter-1, desktop-fact-worst-days, edge-e1-slice-not-enough, edge-e2-fact-not-enough, edge-e3-slice-not-in-file, edge-e5-per-trade |
| Data table | `.table` | 05b-consent-ledger, 09-import-check, 11-what-we-can-check, 15-chapter-3-behaviour, 15-chapter-4-couldnt-read, 16-f01-worst-days, 16-f02-share, 16-f03-money, 16-f04-hold, 16-f07-clock, 16-f08-down, 16-f10-read, 16-f11-risk, 21-account, desktop-fact-worst-days, edge-e4-fact-not-in-file |
| Facts list | `.facts-list` | 07b-not-a-tradebook, 09-import-check, 15-chapter-4-couldnt-read, 16-f10-read |
| Gross line | `.gross-line` | 09-import-check, 14-scope-home, 15-chapter-1-results, 15-chapter-2-patterns, 15-chapter-3-behaviour, 16-f01-worst-days, 16-f02-share, 16-f03-money, 16-f04-hold, 16-f05-strike, 16-f06-run, 16-f07-clock, 16-f08-down, 16-f09-busy, 16-f11-risk, desktop-chapter-1, desktop-fact-worst-days, desktop-home, edge-e2-fact-not-enough, edge-e4-fact-not-in-file, edge-e5-per-trade |
| Result states | `.result-state` | edge-e2-fact-not-enough, edge-e4-fact-not-in-file |
| Feedback row | `.feedback` | 15-chapter-1-results, 15-chapter-2-patterns, 15-chapter-3-behaviour, 17-feedback, desktop-chapter-1, edge-e1-slice-not-enough, edge-e5-per-trade |
| Bottom nav | `.bottom-nav` | 05b-consent-ledger, 14-scope-home, 15-chapter-1-results, 15-chapter-2-patterns, 15-chapter-3-behaviour, 15-chapter-4-couldnt-read, 17-feedback, 18-journals, 18b-journal, 18c-earlier-journals, 19-leaving-card, 20-signed-in-home, 21-account, edge-e1-slice-not-enough, edge-e3-slice-not-in-file, edge-e5-per-trade, edge-e6-no-instrument, edge-e7-no-trades |
| Lens and path | `.path` | 16-f01-worst-days, 16-f02-share, 16-f03-money, 16-f04-hold, 16-f05-strike, 16-f06-run, 16-f07-clock, 16-f08-down, 16-f09-busy, 16-f10-read, 16-f11-risk, 16-f12-not-told, desktop-fact-worst-days, edge-e2-fact-not-enough, edge-e4-fact-not-in-file |
| Trade record | `.trades` | 02c-demo-trades, 16-f01-worst-days, 16-f02-share, 16-f03-money, 16-f04-hold, 16-f05-strike, 16-f06-run, 16-f07-clock, 16-f08-down, 16-f09-busy, 16-f11-risk, desktop-fact-worst-days, edge-e2-fact-not-enough, edge-e4-fact-not-in-file |
| Scope dial | `.scope` | 14-scope-home, 15-chapter-1-results, 15-chapter-2-patterns, 15-chapter-3-behaviour, 15-chapter-4-couldnt-read, desktop-chapter-1, desktop-home, edge-e1-slice-not-enough, edge-e3-slice-not-in-file, edge-e5-per-trade |
| Reveal dial | `.reveal__dial` | 02b-demo-reveal, 12-reveal |
| Forms | `.field` | 03-create-account, 06-upload, 13-what-you-risk, 18b-journal, 19-leaving-card |
| Choice (checkbox/radio) | `.choice` | 05-consent, 13-what-you-risk, 18b-journal, 21b-delete |
| Guess options | `.guess` | 02a-demo-guess, 10-guess |
| Upload | `.upload` | 06-upload |
| Calculating (strip + ledger) | `.ledger` | 08-calculating |
| Journal index | `.journal-index` | 18-journals, 18c-earlier-journals, 19-leaving-card |
| Leaving card | `.leaving-card` | 19-leaving-card |
| Signed-in Scope card | `.scope-card` | 20-signed-in-home |
| Provenance line | `.provenance` | 09-import-check, 15-chapter-4-couldnt-read, 16-f10-read, 16-f12-not-told |


## Calculating (screen 8) — how it really works

* **Reading.** "Reading your file" and the trade strip as an illustration: three fixed sample trades rebuild in a CSS loop
  (`.calc-loop` in `motion.css`). It is not progress and reads nothing from the server: no counts, no status line, no amber.
  The page polls `GET /imports/{id}/status` every 2 s; answer **204** while the import runs (htmx does not swap, so the loop
  is never interrupted).
* **Done.** When the import has finished, answer 200 with the page rendered with `done=True`: "Your file is read.", the
  latest rebuilt trade (`latest_trade.fills[].x` placed to time across the trade's span, `x_first`, `x_last`), the final
  counts in ink (`import.rows_read`, `import.rows_total`, `import.trades_rebuilt`), "Every row is accounted for on the next
  screen." and Continue. The counts are never shown mid-import.
* Reduced motion: one still sample trade while reading. Preview both states in `screens/preview/08-calculating.html` and
  `08-calculating-done.html`.

## The mark and the lockup

The PlusEV mark is the expectation operator holding a trade: the brackets are the trade, the three dots its fills,
unevenly spaced on purpose. Copy it exactly from `static/icons/mark.svg` (or `MARK_PATHS` in the lockup). Never redraw,
respace or recolour it beyond `currentColor`.

```html
<svg viewBox="0 0 30 24" aria-hidden="true">
  <path d="M9.5 3 H3.5 V21 H9.5" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="square"/>
  <path d="M20.5 3 H26.5 V21 H20.5" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="square"/>
  <circle cx="15" cy="7" r="1.9" fill="currentColor"/>
  <circle cx="15" cy="11.8" r="1.9" fill="currentColor"/>
  <circle cx="15" cy="18" r="1.9" fill="currentColor"/>
</svg>
```

* **Lockup** (`.lockup`): the mark at the height of the wordmark, never larger (`--mark-size: 17px`, width × 1.25),
  `--mark-gap` 7 px, then **PlusEV** in IBM Plex Sans 600 at 17; **Scope** beneath in IBM Plex Mono 11. Ink on white,
  white on navy (inside `.stage`, `.screen--navy` or `.on-navy` it turns white by itself).
* **The mark alone** only where the name is already present: favicon (16, 32), app icon, browser tab. Every page's
  `<head>` already links `favicon.svg`, `favicon-32.png`, `favicon-16.png` and `app-icon-180.png` (apple-touch-icon).
  For a web manifest use `app-icon-192.png` and `app-icon-512.png`.
* **The trade strip** (a bar over its fills) is the product's motif — the Calculating loader, trade records, motion
  (`.strip`, `.calc__strip`, `trade_strip()`) — and is never the logo.

## The Scope dial and the charts — `scope-geometry.js`

Pure functions, commented for a line-by-line port to Python (a `scope_geometry.py` behind a Jinja macro):

* `sectors(n, is_home)` — slice angles. Home: dividers at 0/90/180/270, names on the diagonals.
  Chapter: fact 1 centred at twelve o'clock (n = 4 uses the diagonals).
* `ticks(...)` — bezel ticks every 2.5° in three weights: major at dividers, mid every 30°, minor between.
* `name_label(name, mid, …)` — upright names at the arc midpoint on a 12 px leader; right half
  left-aligned, left half right-aligned, twelve and six o'clock centred; two lines at most, three only for
  "Where the money came from", "Where your results came from", "What we have not told you".
* `stacked_split(fig)` and `layout_contents(...)` — the stacked-figure rule: one line where it fits,
  otherwise head at the slice-figure size over the rest at 11 px ("[N]" over "of [N]"; "[N] · [N]" over "min"),
  one figure size per view (Home ≥ 18 px), one shared radius when every slice fits.
* `build_dial(view, size)` → primitives; `render_dial_svg(dial)` → the inline SVG used in the screens
  (class names match `components.css`). The SVG in each screen template was laid out for the longest
  placeholders; **the server should run the port with the real figures**, because the stacked rule depends on width.
* `build_lens(n_facts, fact_index)` — the 56 px lens.
* `charts.<kind>(data…, w, h)` → `{ parts: [{role, d}] }` for worst, share, money, hold, strike, run, clock,
  down, busy, read, risk, notold; templates loop over `parts` and set `class="chart__{{ part.role }}"`.
* `trade_strip(fill_minutes, width)` — a trade drawn to time (ticks, dots, bar), with the fills-land delays.
* `scope_in_at(t, …)` — the scope-in timeline values, for anyone scripting frames.

## Motion — `motion.css`

* Cross-document View Transitions (`@view-transition { navigation: auto; }`); with htmx boosting set
  `htmx.config.globalViewTransitions = true`. Browsers without View Transitions fall back to the in-page keyframes.
* Links say where they came from; the server adds classes to `<html>` (each template has `class="{{ enter_class }}"`):

| Link | Goes to | `<html>` class |
|---|---|---|
| Home slice n | `/scope/<chapter>?enter=in&tap=n` | `vt-in vt-tap-n` |
| Chapter centre "Scope" | `/scope?enter=out&tap=<chapter>` | `vt-out vt-tap-<chapter>` |
| Chapter slice or story card | `/scope/<chapter>/<fact>?enter=lens` | `vt-lens` |
| Lens or chapter path link | `/scope/<chapter>?enter=back&fact=n` | `vt-back` |

* Scope in / out 480 ms, ease-in-out; shrink to lens / back 400 ms; fills-land 40 ms per fill, 160 ms pause,
  200 ms bar; number-count 600 ms once. `prefers-reduced-motion`: every Scope transition is a 120 ms
  crossfade, nothing moves, counts show at once, Calculating shows one still trade while reading.
* Pressed state before navigating: add `.is-leaving` to `.scope` and `.is-pressed` to the slice on pointerdown
  (one `hx-on:pointerdown` attribute, shown in `motion.css`).

## Not included

* Font files and `htmx.min.js` (add to `/static/`).
* The Python port of `scope-geometry.js` and the FastAPI routes themselves.
* Server copy for owner slots (listed above).
