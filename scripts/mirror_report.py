"""The Mirror: what this trader's own history says, with nothing inferred.

Research Spec's first screen and the only part of Scope that needs no model, no
corpus and no gate. Every number here is a count, a median or a share computed
directly from the trader's own fills. Nothing is a claim about cause, nothing is
a diagnosis, and nothing requires the engine to be right.

That boundary is the point. A Finding says "this pattern costs you 0.4R and here
is the evidence". A Mirror fact says "you held losers 2.3 times longer than
winners" and stops. The first needs the whole research gate behind it. The second
only needs the import to be correct, and it is the fastest honest thing we can
put in front of a human.

The report also states what it could NOT read and what it cannot yet test, using
the six result states, because a tool that hides its own limits is the thing we
are trying not to build.

Writes a self-contained HTML file to out/. Reads the export read-only. The output
holds one person's trading and is gitignored; nothing it computes belongs in the
repository (SR-006).

Usage:  uv run python scripts/mirror_report.py <export.csv> [--name "First Name"]
"""
from __future__ import annotations

import argparse
import hashlib
import html
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from services.production.ctr.adapters.dhan_tradebook import parse
from services.production.ctr.reconstruct import reconstruct
from services.research.library import b2

IST = ZoneInfo("Asia/Kolkata")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"

# What a test needs before it can say anything. Stated to the trader up front.
REQUIREMENTS = [
    ("Trades after two same-day losses", 30, "condition trades"),
    ("A comparison group to measure against", 60, "other trades in the same population"),
]


def hhmm(seconds: float) -> str:
    s = int(seconds)
    if s < 3600:
        return f"{s // 60} min"
    if s < 86400:
        return f"{s / 3600:.1f} hours"
    return f"{s / 86400:.1f} days"


def money(x: float) -> str:
    sign = "-" if x < 0 else ""
    v = abs(x)
    if v >= 1e7:
        return f"{sign}Rs {v / 1e7:.2f} cr"
    if v >= 1e5:
        return f"{sign}Rs {v / 1e5:.2f} L"
    return f"{sign}Rs {v:,.0f}"


def build(path: Path, display_name: str) -> Path:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    res = parse(path, trader_id="T01", raw_hash=digest)
    recon = reconstruct(res.fills, fees_available=res.fees_available)
    trips = sorted(recon.round_trips, key=lambda t: t.entry_ts)
    if not trips:
        raise SystemExit("no round trips reconstructed")

    net = {id(t): float(t.gross_pnl) - float(t.fees) for t in trips}
    days = sorted({t.entry_ts.date() for t in trips})
    by_day: dict = {}
    for t in trips:
        by_day.setdefault(t.entry_ts.date(), []).append(t)
    for v in by_day.values():
        v.sort(key=lambda t: t.entry_ts)

    wins = [t for t in trips if net[id(t)] > 0]
    losses = [t for t in trips if net[id(t)] < 0]
    total = sum(net.values())

    # --- where the money actually went -------------------------------------
    day_pnl = {d: sum(net[id(t)] for t in v) for d, v in by_day.items()}
    worst_days = sorted(day_pnl.items(), key=lambda kv: kv[1])[:5]
    median_count = statistics.median([len(v) for v in by_day.values()])
    worst_rows = "".join(
        f"<tr><td>{d:%a %d %b %Y}</td><td class=n>{money(p)}</td>"
        f"<td class=n>{len(by_day[d])}</td>"
        f"<td class=n>{len(by_day[d]) / median_count:.1f}x</td></tr>"
        for d, p in worst_days
    )
    worst_share = sum(p for _, p in worst_days) / total if total else 0
    busy_on_worst = sum(1 for d, _ in worst_days if len(by_day[d]) >= 2 * median_count)

    # --- the clock ----------------------------------------------------------
    hour_pnl: dict = {}
    hour_n: dict = {}
    for t in trips:
        h = t.entry_ts.hour
        hour_pnl[h] = hour_pnl.get(h, 0.0) + net[id(t)]
        hour_n[h] = hour_n.get(h, 0) + 1
    worst_hour = min(hour_pnl, key=lambda h: hour_pnl[h])
    best_hour = max(hour_pnl, key=lambda h: hour_pnl[h])
    hour_rows = "".join(
        f"<tr><td>{h:02d}:00 – {h:02d}:59</td><td class=n>{hour_n[h]}</td>"
        f"<td class=n>{money(hour_pnl[h])}</td></tr>"
        for h in sorted(hour_pnl, key=lambda h: hour_pnl[h])[:3]
    )

    # --- what changes when he is already down -------------------------------
    # "Already down" = two trades opened earlier today have already closed at a
    # loss. Pure bookkeeping on his own fills: no model, no threshold, no fit.
    after2, before2, skipped_pnl, skipped_n = [], [], 0.0, 0
    for v in by_day.values():
        for i, t in enumerate(v):
            closed_losses = sum(
                1 for e in v[:i] if e.exit_ts <= t.entry_ts and net[id(e)] < 0
            )
            (after2 if closed_losses >= 2 else before2).append(t)
            if closed_losses >= 2:
                skipped_pnl += net[id(t)]
                skipped_n += 1

    def rate(group):
        return sum(1 for t in group if net[id(t)] > 0) / len(group) if group else 0.0

    def avg_lots(group):
        return statistics.mean([t.quantity for t in group]) if group else 0.0

    r_after, r_before = rate(after2), rate(before2)
    lots_after, lots_before = avg_lots(after2), avg_lots(before2)
    days_with = sum(
        1 for v in by_day.values()
        if any(sum(1 for e in v[:i] if e.exit_ts <= t.entry_ts and net[id(e)] < 0) >= 2
               for i, t in enumerate(v))
    )

    # The replay: his result had he stopped for the day after the second loss.
    stopped_total = total - skipped_pnl
    helped = skipped_pnl < 0

    hold_w = statistics.median([t.holding_seconds for t in wins]) if wins else 0
    hold_l = statistics.median([t.holding_seconds for t in losses]) if losses else 0
    with_r = [t for t in trips if t.r_multiple is not None]
    sym_line = ", ".join(
        f"{s} ({c:,})" for s, c in Counter(t.symbol for t in trips).most_common(4)
    )

    obs = [
        b2.Obs(day=t.entry_ts.date().toordinal(), entry_at=t.entry_ts.timestamp(),
               exit_at=t.exit_ts.timestamp(), r=net[id(t)])
        for t in trips
    ]
    in_pop, cond = b2.population_and_condition(sorted(obs, key=lambda o: (o.day, o.entry_at)))
    n_cond, n_comp = int(cond.sum()), int(in_pop.sum() - cond.sum())
    can_run = n_cond >= 30 and n_comp >= 60

    doc = f"""<!doctype html>
<html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Your trading, counted</title>
<style>
  :root {{ --bg:#fbfaf8; --fg:#1c1b19; --dim:#6b6762; --line:#e3dfd9; --card:#fff;
    --accent:#8a5a2b; --good:#2f7d4f; --bad:#a8452f; }}
  @media (prefers-color-scheme:dark) {{
    :root:not([data-theme=light]) {{ --bg:#17161a; --fg:#ece9e4; --dim:#9b958d;
      --line:#2e2c31; --card:#1f1e23; --accent:#d59b63; --good:#6cc08b; --bad:#e08264; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:0 16px 80px; background:var(--bg); color:var(--fg);
    font:17px/1.65 ui-serif,Georgia,'Times New Roman',serif; }}
  main {{ max-width:700px; margin:0 auto; }}
  header {{ padding:60px 0 24px; }}
  h1 {{ font-size:30px; line-height:1.2; margin:0 0 12px; font-weight:600; letter-spacing:-.015em; }}
  h2 {{ font-size:12.5px; letter-spacing:.1em; text-transform:uppercase; color:var(--dim);
    margin:52px 0 16px; font-family:ui-sans-serif,system-ui,sans-serif; font-weight:600;
    padding-top:20px; border-top:1px solid var(--line); }}
  p {{ margin:0 0 15px; }}
  .lede {{ color:var(--dim); font-size:16px; }}
  .big {{ font-size:34px; font-weight:600; letter-spacing:-.025em; line-height:1.15;
    font-family:ui-sans-serif,system-ui,sans-serif; margin:0 0 6px; }}
  .big.good {{ color:var(--good); }} .big.bad {{ color:var(--bad); }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(145px,1fr)); gap:12px; margin:0 0 16px; }}
  .stat {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
  .stat b {{ display:block; font-size:23px; font-weight:600; letter-spacing:-.02em;
    font-family:ui-sans-serif,system-ui,sans-serif; }}
  .stat span {{ font-size:12.5px; color:var(--dim); font-family:ui-sans-serif,system-ui,sans-serif; }}
  table {{ width:100%; border-collapse:collapse; font-size:14.5px;
    font-family:ui-sans-serif,system-ui,sans-serif; margin:4px 0 14px; }}
  th,td {{ text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); }}
  th {{ font-size:11.5px; letter-spacing:.05em; text-transform:uppercase; color:var(--dim); font-weight:600; }}
  td.n {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .ok {{ color:var(--good); }} .no {{ color:var(--bad); }}
  .note {{ border-left:3px solid var(--accent); padding:4px 0 4px 18px; margin:22px 0;
    color:var(--dim); font-size:15.5px; }}
  footer {{ margin-top:56px; padding-top:20px; border-top:1px solid var(--line);
    font-size:13px; color:var(--dim); font-family:ui-sans-serif,system-ui,sans-serif; }}
  code {{ font-size:12px; }}
</style></head><body><main>

<header>
  <h1>{html.escape(display_name)}, we counted every trade you made.</h1>
  <p class=lede>{len(trips):,} trades across {len(days)} trading days, {days[0]:%B %Y} to
  {days[-1]:%B %Y}. Nothing below is an opinion or a diagnosis — it is arithmetic on your
  own fills. Where we have not tested something, we say so.</p>
  <p class=lede>What you trade: {sym_line}.</p>
</header>

<h2>Most of what happened to you happened on five days</h2>
<p class=big>{money(sum(p for _, p in worst_days))}</p>
<p>Your five worst days account for {abs(worst_share):.0%} of your entire result. Here they are.</p>
<table><tr><th>Day</th><th>Result</th><th>Trades</th><th>vs your normal day</th></tr>{worst_rows}</table>
<p>On a day you trade, you normally take {int(median_count)} trades.
{"On " + str(busy_on_worst) + " of these five days you took at least double that."
  if busy_on_worst else "Your trade count on these days was not unusual."}</p>

<h2>Your worst hours of the day</h2>
<table><tr><th>Hour you entered</th><th>Trades</th><th>Result</th></tr>{hour_rows}</table>
<p>Your worst hour to open a trade is <b>{worst_hour:02d}:00</b>; your best is
<b>{best_hour:02d}:00</b>. That is what happened, not advice — we have not tested whether
the difference is more than chance.</p>

<h2>What changes once you are already down</h2>
<p class=lede>On {days_with} days, two of your trades had already closed at a loss and you
kept going. Those {len(after2):,} trades are compared below with the {len(before2):,} you
took before that point.</p>
<div class=grid>
  <div class=stat><b>{r_before:.0%} &rarr; {r_after:.0%}</b><span>share of trades that made money</span></div>
  <div class=stat><b>{lots_before:.1f} &rarr; {lots_after:.1f}</b><span>average lots per trade</span></div>
  <div class=stat><b>{len(after2):,}</b><span>trades taken while already down two</span></div>
</div>
<p>{"You size up after two losses." if lots_after > lots_before * 1.1
   else "You size down after two losses." if lots_after < lots_before * 0.9
   else "Your position size barely changes after two losses."}
{"Your strike rate falls." if r_after < r_before - 0.02
   else "Your strike rate actually improves." if r_after > r_before + 0.02
   else "Your strike rate is essentially unchanged."}</p>

<h2>One rule, replayed over your own trades</h2>
<p class=lede>Suppose you had stopped trading for the day the moment your second loss closed.
Everything else identical — same trades, same sizes, same exits, just nothing new opened
after that point.</p>
<p class="big {'good' if helped else 'bad'}">{money(-skipped_pnl)}</p>
<p>That rule would have removed {skipped_n:,} trades and changed your result by
<b>{money(-skipped_pnl)}</b> — from {money(total)} to {money(stopped_total)}.
{"Stopping would have saved you money." if helped
   else "Stopping would have <b>cost</b> you money. The trades you took while already down were, in total, profitable."}</p>
<div class=note>This is a replay, not a prediction. It removes trades you actually took and
adds up what they actually made. It does not claim you would trade the same way under a rule,
and it is not evidence that the rule works — one history cannot establish that.</div>

<h2>How long you stay in</h2>
<div class=grid>
  <div class=stat><b>{hhmm(hold_w)}</b><span>median hold, winners</span></div>
  <div class=stat><b>{hhmm(hold_l)}</b><span>median hold, losers</span></div>
  <div class=stat><b>{(hold_l / hold_w if hold_w else 0):.2f}x</b><span>losers held longer</span></div>
</div>

<h2>What we could not read</h2>
<table><tr><th>Stage</th><th>Kept</th><th>Set aside</th></tr>
<tr><td>Rows in your file</td><td class=n>{len(res.fills):,}</td><td class=n>{len(res.rejected):,}</td></tr>
<tr><td>Trades reconstructed</td><td class=n>{len(trips):,}</td><td class=n>{len(recon.skipped):,}</td></tr>
<tr><td>Trades with a risk figure</td><td class=n>{len(with_r):,}</td><td class=n>{len(trips) - len(with_r):,}</td></tr>
</table>
<p class=lede>Your export carries no stop-loss orders, so for options we treat the premium you
paid as the risk. That is the most you could have lost, which is correct but conservative —
on trades you exit quickly it overstates what you really had at risk.</p>

<h2>What we have not told you</h2>
<p>Your history is {"long enough" if can_run else "not yet long enough"} to test the
after-two-losses pattern properly — {n_cond:,} such trades against {n_comp:,} comparable
ones, where we need 30 and 60. <b>We have not run that test.</b> The scale it measures
against was built for futures trading with stop orders, and your book is options. Running it
unchanged would most likely report "nothing found" because the yardstick is wrong, not
because there is nothing there. We would rather say that than show you a confident blank.</p>
<div class=note>Four things this page deliberately does not do: name a cause, score you
against other traders, claim a habit cost you money, or recommend a change.</div>

<h2>What would help us most</h2>
<p>Which of these did you already know? Which surprised you? Is anything here simply wrong
about how you trade? And what would you most want it to tell you that it does not?</p>

<footer>
Built {datetime.now(IST):%d %B %Y} from <code>{html.escape(path.name)}</code>,
sha256 <code>{digest[:16]}</code>. Research prototype — counted facts only, no validated
findings. Your file was read without being copied or modified.
</footer>
</main></body></html>"""

    OUT.mkdir(exist_ok=True)
    dest = OUT / f"mirror_{path.stem.lower().replace(' ', '_')}.html"
    dest.write_text(doc, encoding="utf-8")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export", type=Path)
    ap.add_argument("--name", default="Here")
    args = ap.parse_args()
    dest = build(args.export, args.name)
    print(f"wrote {dest.relative_to(ROOT)}")
    print("open it with:  open " + str(dest))


if __name__ == "__main__":
    main()
