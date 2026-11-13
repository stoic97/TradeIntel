# ADR 008: Market data we read, and what we may show

**Status.** Accepted on merge. **Date.** 2026-11-13. **Deciders.** Founder (TICKET-894).

## Context

The round-2 run measured T-001's entries against NIFTY index 1-minute bars from the Fyers history API.
Research Spec §9 chose crude first partly because "we hold the price series, so market context is no
longer a licence question". That sentence was about crude. Nobody had made it for NIFTY, and the
TICKET-893 extension means the crude series now comes from Fyers too, for every bar after 24 Dec 2025.

This record answers the four questions TICKET-894 asks. The Fyers answers come from the published API
terms and from the connected account itself, checked on 13 Nov 2026. The exchanges' own terms could not
be read (see Sources), and the record says where that leaves a gap.

## Decision

**No bar-derived figure is shown to anyone but T-001 yet, for any instrument family, crude included.**
That covers a paying trader and a free visitor on the demo file. It stays that way until both licences
below are held in writing for that family. The engine, the series and the screen may still be built,
tested and run for T-001 (below).

### 1. May we display it? No, not under the terms we hold today.

Fyers' API terms (fyers.in/terms-and-conditions-api, read 13 Nov 2026) say:

- **§12, Confidentiality.** Content returned from the APIs may be stored as a database, turned into a
  derivative work, distributed or "publicly display[ed]" to any third party "only upon the written
  consent of FYERS". A count such as "the minute before your entry moved your way in 41 of 60 trades" is
  derived from that content and shown to a third party. We have no such consent.
- **§11, Prohibitions.** Exchange data is to be used "only for legitimate, fair, and transparent
  trading", and not to develop "charting, technical tools" and similar products.
- **§8, End-users.** Platforms built on the APIs may be offered to *other clients of FYERS*, after
  "the required approvals from the relevant Exchange". Our traders are not necessarily Fyers clients.

So display needs two things, and they are separate:

1. **Fyers' written consent** under §12, for derived figures shown to people who may not be Fyers
   clients.
2. **The exchange's licence.** Fyers can't grant rights it doesn't hold, and its own §8 points at the
   exchange. NSE's data policy and NSE Indices' licensing pages are the source for NIFTY, but neither
   could be read here. Until they are, treat display of a NIFTY-derived figure as needing an NSE
   licence.

The demo file is no exception: a free visitor is a third party. If the demo is to show market context,
it uses a made-up series that lives in the repo and is labelled as such, as the tests already do. That
keeps the demo outside the licence question entirely.

### 2. What does it cost at 20 traders, and at 200?

**On Fyers, the money cost is close to nothing, and it doesn't grow with traders.** Spec §4.7.3 gives
one series per underlying, shared by every trader of it. So requests grow with the number of
underlyings, not the number of traders, and 20 and 200 traders cost the same. Measured and published
figures:

| | |
| --- | --- |
| API price | Free on the Standard plan. FYERS Prime is ₹499 + GST a month, or ₹4,990 + GST a year, per individual trading account. |
| Data API limits | Standard: 5 a second, 50 a minute, 5,000 a day. Prime: 10, 500 and 500,000. Going over the per-minute limit more than 3 times in a day blocks the account for the rest of that day. |
| One request | Up to 100 days of 1-minute bars. |
| A 1-minute backfill | About 34 requests for 9 years of one underlying. After that, one request a day per underlying. |
| Single stocks | One series per stock anyone trades, so 500 stocks is about 17,000 requests once (four days on Standard), then 500 a day. |

**Historical depth is where the plan matters.** Fyers' published table gives Standard one rolling year
of intraday history and Prime "entire available history, 5+ years". The connected account was asked
directly and serves 1-minute bars back to **14 Nov 2017**: a rolling 9 years, so this account gets
more than the Standard figure. A new account on Standard would cover a year of 1-minute bars, which is
less than a five-year upload. So a company account needs Prime, or must be measured before anyone
assumes otherwise.

**The licensed route has no price yet.** NSE Data & Analytics sells historical and minute data and
lists authorised vendors. One such vendor (TrueData) says redistribution needs the exchange's prior
written permission. No figure was published or reachable on 13 Nov, so the cost of the licence in
point 1 is the open number. It is a quote to ask for, not one to estimate.

### 3. Who holds the account, and what happens if it lapses?

**It is the fund's connection** (ADR 002): one Fyers client account and one API app, with the token
renewed by hand each trading day. It is not held by the company. That is a wall problem as well as a
licence one, because ADR 002 keeps fund credentials out of this product.

If that account lapses or its terms are ended:

- **No new bars.** Each series stops at its manifest's `as_of`. A claim about a later date refuses
  itself (spec §4.7.6; `SeriesManifest.covers`, TICKET-893), so no report silently goes wrong.
- **Stored bars may have to go too.** §15 ends the right to use the APIs on termination, and Fyers
  "shall delete all cached and stored content that was permitted". If stored bars must be deleted,
  every bar-derived figure in every report falls back to its "not available" state at once.
- **Prime can't be moved.** Fyers says Prime is "linked to your individual trading account".

So before any trader beyond T-001 sees a bar-derived figure, the connection moves to a
**company-held Fyers account and app**. That account then asks for the consent in point 1.

### 4. The fallback

There are two licensable routes, and neither is held today:

- **Fyers plus the exchange:** Fyers' written consent under §12, plus each exchange's licence for
  derived display.
- **An authorised data vendor** whose licence covers showing derived figures to our users. That
  needs NSE Data & Analytics' list of authorised vendors and a quote.

**Until one of them is held in writing, NIFTY market context does not ship beyond T-001.** The rest of
the report ships without it. A bar-derived fact shows its "not available" state with an honest line,
the same way it does when a series doesn't cover a trader's dates (§4.7.6). It never goes missing
silently.

### Also decided: the other families

All of them come from **the same connection on the same Fyers terms**. Fyers' terms define "Exchange"
as NSE, BSE and MCX, and §11–12 apply to all three, so one Fyers consent can cover every family.
**The exchange side splits three ways**, and each needs its own answer:

| Family | Exchange licence needed | 1-minute history this account serves (measured 13 Nov 2026) |
| --- | --- | --- |
| NIFTY 50, NIFTY BANK | NSE (index values: NSE Indices) | From 14 Nov 2017, a rolling 9 years |
| NSE single stocks | NSE | From 14 Nov 2017 (checked on one large stock) |
| SENSEX | BSE | From 28 May 2019, when the data starts |
| Crude, gold, silver | MCX | Asked with the near-month contract and `cont_flag=1`. Crude is in `crude_1m_current.csv`. Gold and silver both returned 2020 bars. |

**Crude is in this queue, not ahead of it.** Its bars after 24 Dec 2025 came from Fyers (TICKET-893).
Its bars before that are the fund's store, and that store's closes match Fyers' near-month continuous
series on all 124,586 bars from June to December 2025. Whatever the store's origin, holding a copy is
not a licence to show it. So §9's sentence holds for *reading* crude, but it does not settle *showing*
crude. Crude needs MCX's answer, as NIFTY needs NSE's.

## What can be built now

- **TICKET-889 (the series layer)** can be built as specified. It should carry, per family, whether
  display is permitted, and that should be **off for every family** until a later ADR records that
  family's licences. Then the screen checks one flag rather than this document.
- **TICKET-891's counts** run for T-001 and on the repo's made-up series.
- **The screen ticket** can be built and shown to T-001, with each bar-derived fact behind that flag.

## Next steps

These sit with Rikk: Pawan, 12 Nov, "everything Fyers-related sits with Rikk".

1. Open a company-held Fyers account and API app, and check its 1-minute history depth the way this
   record does.
2. From that account, write to Fyers for consent under §12 and §8 to show figures derived from API
   bars to users who may not be Fyers clients.
3. Ask NSE Data & Analytics, BSE and MCX for the licence and price for showing derived figures (not
   prices) to subscribers. Ask NSE Data & Analytics for its authorised-vendor list at the same time.
4. When a family's licences are held, a new ADR records them and supersedes this one for that family
   (ADRs are immutable, methodology "Rules"). It lands in the same PR that turns that family's display
   flag on.

## Alternatives considered

- **Show it, because the API returns it.** Rejected. The ticket asks us to read the terms rather than
  infer from what the API returns, and §12 says no.
- **Show crude now, because we hold it.** Rejected. See above: holding a copy is not a licence to show
  it.
- **Fall back to daily bars, which more sources give away.** Rejected by spec §4.7.1, which allows one
  interval and no coarser fallback.

## Sources (read 13 Nov 2026)

- Fyers API Terms & Conditions, https://fyers.in/terms-and-conditions-api (no date shown): §2, §8,
  §11, §12, §15.
- Fyers API plans and limits, https://fyers.in/api-docs/v3/getting-started/plans-and-limits/
  (updated 14 Oct 2026). Historical data limits:
  https://fyers.in/api-docs/v3/api/market-data/historical-data/. Prime pricing:
  https://fyers.in/prime.
- The connected account, read-only `history` calls: the earliest 1-minute start it accepts for NIFTY
  50, NIFTY BANK and a large NSE stock, SENSEX's first bars, and MCX gold and silver through
  `cont_flag=1`. Only counts and dates were recorded, never prices.
- TrueData, https://truedata.in/market-data-apis: redistribution needs prior written permission.
- **Not read:** NSE's Data Usage and Sharing Policy, NSE Data & Analytics' pricing and NSE Indices'
  licensing pages. All three timed out on 13 Nov. Point 1's exchange half and point 2's licence price
  rest on reading them, or on NSE's written reply in next step 3.
