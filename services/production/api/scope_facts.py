"""What each fact shows on the Scope: its figure, its state, its charts, its dial slice.

Pages format, they don't compute (handoff T7). Every figure here is one metrics.py
decided; this module only picks which one a fact leads with, draws its charts with
scope_geometry, and works out the few counts a sentence needs that metrics returns
as a list (the days a run crossed, the hours that had a trade). The templates write
the rest with the formatting filters.

A fact is in one of three states (handoff 4): counted (state ""), not enough trades
yet ("not-enough"), or not in the file ("not-in-file"). A fact in a state still has
its slice and its card - never hidden - and its figure is a dash.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal

from markupsafe import Markup

from services.production.api import after_closed as ACL
from services.production.api import charts, day_chart, dial, findings, formatting
from services.production.api import scope_geometry as G
from services.production.api import scope_map as S
from services.production.api.figures import Figure
from services.production.mirror import metrics as mx
from services.shared.conditions import b2_shuffle, multiplicity
from services.shared.schemas import scope_v1 as s

COUNTED = s.ResultState.COUNTED_FACT
CARD_W = 302  # a story card's chart width (the kit's chapter screens)
PAGE_W, PAGE_H = 350, 96  # a fact page's figure (the kit's fact screens)
CARD_H = {
    "worst": 84,
    "share": 56,
    "money": 150,
    "strike": 40,
    "run": 40,
    "clock": 84,
    "busy": 84,
    "backin": 84,
    "sameway": 56,
    "nextday": 70,
    "after-close": 84,
}
INDIA_OFFSET = timedelta(hours=5, minutes=30)
NOT_TOLD = 4
"""What we have not told you: the four things its first sentence names - a cause, a
score, a cost, a change. Counted from the sentence, which is the Mirror's own."""


def record_context(trips: list[mx.Trip]) -> dict:
    """Every Appendix A figure the Mirror and the Scope read, computed once.

    Moved here from routes_mirror so a page test reads the same figures the route
    does. The last five are PRD 6.3's comparison: trades after two straight losses
    against the rest, on strike rate and average lots.
    """
    same_day = mx.same_day_trips(trips)
    # Chapter 3 reads the same trades as Chapter 2 [TICKET-855]: a position held past the day
    # moves none of its figures.
    two_losses = mx.two_straight_losses(same_day)
    after = mx.subset(same_day, two_losses.condition_trip_ids)
    rest = mx.complement(same_day, two_losses.condition_trip_ids)
    return {
        "worst_days": mx.five_worst_days(trips),
        "share": mx.share_of_losses(trips),
        "day_blocks": mx.worst_day_blocks(trips),
        "days": mx.day_counts(same_day),
        "file_trading_days": len({t.trading_day for t in trips}),
        "best": mx.best_five(same_day),
        "worst": mx.worst_five(same_day),
        "held_past_day": mx.held_past_day(trips),
        "money_found": mx.money_found(trips),
        "past_number": mx.trades_past_number(trips),
        "two_losses": two_losses,
        "next_trades": mx.next_trades(same_day),
        "day_after": mx.day_after(trips),
        "strike": mx.strike_rate(same_day),
        "break_even": mx.break_even(same_day),
        "lots": mx.average_lots(trips),
        "holding": mx.holding_time(same_day),
        "hours": mx.result_by_hour(same_day),
        "clocks": mx.clocks_by_book(same_day),
        "run": mx.longest_losing_run(trips),
        "costliest_run": mx.costliest_losing_run(trips),
        "risk": mx.risk_figure_counts(trips),
        "five_days": mx.five_days_read(trips),
        "loss_sizes": mx.loss_sizes(same_day),
        "premium_paid": mx.premium_by_book(same_day),
        "book_math": mx.math_by_book(same_day),
        "book_row_minimum": mx.BOOK_ROW_MINIMUM,
        "book_halves": mx.book_halves(trips),
        "previous_result": mx.previous_result_figures(trips),
        "trips": trips,
        "after_strike": mx.strike_rate(after),
        "after_lots": mx.average_lots(after),
        "rest_strike": mx.strike_rate(rest),
        "rest_lots": mx.average_lots(rest),
        "days_with_the_condition": len({t.trading_day for t in after}),
        # The days it could happen on: days he closed a same-day trade, the trades chapter 3
        # reads (855), named as such wherever the count is said, the Journal's included.
        "same_day_days": len({t.trading_day for t in same_day}),
    }


def _f(value) -> float:
    return float(value) if value is not None else 0.0


def _chart(kind: str, ctx: dict, imp, w: float, h: float, mini: bool):
    """The chart a fact draws, at a size; None where the fact has nothing to draw."""
    trips = ctx["trips"]
    if kind == "after-close":  # stored figures only; not a kit chart, so not in G.CHARTS
        return ACL.geometry(ACL.view(ctx), w, h, mini=mini)
    if kind == "worst":
        if mini:  # the dial's mini is the kit's chart, held to it byte for byte
            return G.chart_worst([_f(d.net) for d in mx.daily_series(trips)], w, h)
        days = days_worst_to_best(trips)
        return G.chart_worst_sorted([_f(d["net"]) for d in days],
                                    [_f(d["cumulative"]) for d in days], w, h)
    if kind == "share":
        share = ctx["share"]
        if not share.shown_as_percentage:
            return None  # a share that is not a percentage is not drawn as one
        return G.chart_share(_f(share.share_percent) / 100, w, h, mini)
    if kind == "money":
        return G.chart_money(
            [_f(t.net) for t in ctx["best"]], [_f(t.net) for t in ctx["worst"]], w, h
        )
    if kind == "strike":
        st = ctx["strike"]
        return G.chart_strike(st.wins, st.losses, st.scratches, w, h, mini)
    if kind == "run":
        run = ctx["run"]
        start = next((i for i, t in enumerate(trips) if t.trip_id in set(run.trip_ids)), 0)
        return G.chart_run(len(trips), start, run.length, w, h, mini)
    if kind == "clock":  # the book the figure comes from; each book's own is in _clock_view
        return _chart_of(mx.lead_clock(ctx["clocks"]), w, h)
    if kind == "down":
        tl = ctx["two_losses"]
        return G.chart_down(_f(tl.condition_mean), _f(tl.comparison_mean), w, h, mini)
    if kind == "backin":
        nt = ctx["next_trades"]
        if not nt.back_in_enough:
            return None  # under 30 in a group, nothing is set side by side (B1's minimum)
        return G.chart_backin([_f(nt.minutes[t.trip_id]) for t in nt.after_loss],
                              [_f(nt.minutes[t.trip_id]) for t in nt.comparison],
                              _f(nt.loss_median), _f(nt.comparison_median), w, h, mini)
    if kind == "sameway":
        nt = ctx["next_trades"]
        return G.chart_sameway(nt.same_after_loss, nt.other_after_loss, nt.same_after_win,
                               nt.other_after_win, w, h, mini)
    if kind == "nextday":
        rows = _next_day_rows(ctx["day_after"])
        return G.chart_nextday(*(_f(r["per_day"] or 0) for r in rows), w, h, mini)
    if kind == "busy":
        days = ctx["days"]
        return G.chart_busy(days.counts, _f(days.normal_day), w, h)
    if kind == "read":
        return G.chart_read(imp.rows_parsed, imp.rows_in, w, h, mini)
    if kind == "risk":
        c = ctx["risk"].counts
        # The kit's chart has four bands. A spread's maximum loss is recorded and never
        # divided by, as the premium is; an uncapped position has nothing to measure.
        nothing = (c[s.RiskUnitSourceV1.UNAVAILABLE] + c[s.RiskUnitSourceV1.INFERRED_ATR]
                   + c[s.RiskUnitSourceV1.UNCAPPED])
        return G.chart_risk(
            c[s.RiskUnitSourceV1.DECLARED_BUDGET],
            c[s.RiskUnitSourceV1.DEFINED_STOP],
            c[s.RiskUnitSourceV1.PREMIUM_PAID] + c[s.RiskUnitSourceV1.STRUCTURE_MAX_LOSS],
            nothing,
            w,
            h,
            mini,
        )
    return G.chart_notold(w, h, mini)


def _mini(key: str, ctx: dict, imp) -> tuple[dict | None, str]:
    """A fact's chart on its dial wedge, and what it shows in words.

    One of the kit's straight forms at the dial's MINI size, drawn from the figures the fact's own
    page is built from. A fact that no form fits, or that has nothing to draw, has none.
    """
    w, h, rupees, count = dial.MINI_W, dial.MINI_H, formatting.rupees, formatting.count
    if key == "hidden":
        rows = [r for r in ctx["book_halves"] if r.state is COUNTED]
        if not rows:
            return None, ""
        row = max(rows, key=lambda r: r.trades)
        one, two = row.first.net_per_trade, row.second.net_per_trade
        return G.chart_pair(_f(one), _f(two), w, h), (
            f"{row.book}: {rupees(one)} a trade in the first half, {rupees(two)} in the second."
        )
    if key == "worst-days":
        sh = ctx["share"]
        return G.chart_split(_f(sh.five_day_sum), _f(sh.other_days_net), w, h), (
            f"Five worst days {rupees(sh.five_day_sum)}; "
            f"the other {count(sh.other_days_count)} days {rupees(sh.other_days_net)}."
        )
    if key == "share":
        return _chart("share", ctx, imp, w, h, True), ""
    if key == "money":
        if not ctx["best"] or not ctx["worst"]:
            return None, ""
        best, worst = ctx["best"][0].net, ctx["worst"][0].net
        return G.chart_pair(_f(best), _f(worst), w, h), (
            f"Best trade {rupees(best)}; worst trade {rupees(worst)}."
        )
    if key == "math":
        rate, even = ctx["strike"].rate_percent, ctx["break_even"].percent
        if rate is None:
            return None, ""
        said = f"{formatting.out_of_a_hundred(rate)} trades made money"
        if even is not None:
            said += f"; break-even at {formatting.out_of_a_hundred(even)}"
        return G.chart_meter(_f(rate) / 100, None if even is None else _f(even) / 100, w, h), said + "."
    if key == "run":
        ids = set(ctx["run"].trip_ids)
        nets = [t.net for t in ctx["trips"] if t.trip_id in ids]
        return G.chart_steps([_f(v) for v in nets], w, h), (
            f"{count(len(nets))} losses in a row, {rupees(sum(nets, Decimal(0)))} in all."
        )
    if key == "clock":
        lead = mx.lead_clock(ctx["clocks"])
        if lead is None:
            return None, ""
        mark = [hr.hour for hr in lead.hours].index(lead.largest.hour)
        return G.chart_hours([_f(hr.net) for hr in lead.hours], mark, w, h), (
            f"{_hour_words(lead.largest.hour)} hour {rupees(lead.largest.net)}; "
            f"every hour {rupees(lead.net)}."
        )
    if key == "down":
        tl = ctx["two_losses"]
        if tl.condition_mean is None or tl.comparison_mean is None:
            return None, ""
        return G.chart_pair(_f(tl.condition_mean), _f(tl.comparison_mean), w, h), (
            f"After two straight losses {rupees(tl.condition_mean)} a trade; "
            f"other trades {rupees(tl.comparison_mean)}."
        )
    if key == "busiest":
        days = ctx["days"]
        texts = [count(days.busiest_trips), count(days.normal_day)]
        return G.chart_counts(days.busiest_trips, _f(days.normal_day), w, h, texts), (
            f"{texts[0]} trades on the busiest day; {texts[1]} on a normal day."
        )
    if key == "unread":
        return _chart("read", ctx, imp, w, h, True), (
            f"{count(imp.rows_parsed)} of {count(imp.rows_in)} rows read."
        )
    return None, ""  # the risk figure and what we have not told you: no form fits them


def _state(key: str, ctx: dict) -> str:
    if key == "after-close" and not ACL.view(ctx)["enough"]:
        return "not-enough"  # under 30 measured losing trades, or none worked out yet
    if key == "clock" and not ctx["hours"]:
        return "not-enough"  # every trade was held past its day
    if key == "hidden" and not any(r.state is COUNTED for r in ctx["book_halves"]):
        return "not-enough"  # no book has the minimum of same-day trades
    if key == "risk" and ctx["risk"].showable == 0:
        return "not-in-file"  # no stop column and no budget: the kit's edge state e4
    metric = {
        "worst-days": "worst_days",
        "share": "share",
        "math": "holding",  # both a winner and a loser, or there is nothing to balance
        "run": "run",
        "down": "two_losses",
        "back-in": "next_trades",
        "next-day": "day_after",
        "busiest": "days",
    }.get(key)
    if key == "same-way" and ctx["next_trades"].way_state is not COUNTED:
        return "not-enough"
    if metric and ctx[metric].state is not COUNTED:
        return "not-enough"
    return ""


# ---------- What you do next (chapter 3): counts and his own medians, never a claim ----------

NEXT_DAY_GROUPS = (("best", "After your best days"), ("worst", "After your worst days"),
                   ("other", "Your other days"))


def _minutes(m: Decimal | None) -> int | None:
    return None if m is None else int(m.quantize(Decimal(1), rounding="ROUND_HALF_UP"))


def _minutes_said(m: Decimal | None) -> str:
    n = _minutes(m)
    return f"{formatting.count(n)} {'minute' if n == 1 else 'minutes'}"


def _rate(part: int, whole: int) -> Decimal:
    return Decimal(part) * 100 / Decimal(whole)


def _plain(value: Decimal | None) -> str:
    """A count when whole, else to one decimal: trades a day and lots are averages."""
    if value is None:
        return ""
    if value == value.to_integral_value():
        return formatting.count(int(value))
    return formatting.lots(value)


def _w(value, noun: str, how: str = "count", opens: str | None = None) -> Markup:
    """A figure in a sentence, written through its filter and opening its trades."""
    written = formatting._FIGURE_FILTERS[how](Figure(value, noun, opens=opens))
    return Markup('<span class="num">{}</span>').format(written)


def _amount(value: Decimal, noun: str, opens: str | None = None) -> Markup:
    if value == value.to_integral_value():
        return _w(int(value), noun, "count", opens)
    return _w(value, noun, "lots", opens)


def _next_day_rows(da) -> list[dict]:
    rows = []
    for g, label in NEXT_DAY_GROUPS:
        trips, days = da.groups[g], da.days_in[g]
        lots = mx.average_lots(list(trips)).mean
        rows.append({
            "group": g, "label": label, "trades": len(trips), "days": days,
            "per_day": Decimal(len(trips)) / days if days else None,
            "lots": Decimal(lots) if lots is not None else None,
            "won": sum(t.is_win for t in trips),
            "rate": _rate(sum(t.is_win for t in trips), len(trips))
            if len(trips) >= mx.CLOCK_MINIMUM_TRADES else None,
            "href": S.see_all_href("next-day", next_day=g) if trips else None,
        })
    return rows


def _back_in_view(ctx: dict) -> dict:
    """B1, as the founder ruled it on 24 Nov 2026: after a loss against after a win or a level
    trade. Under 30 in either group the page says how many and that they are too few, and
    compares nothing."""
    nt = ctx["next_trades"]
    loss_href = S.see_all_href("back-in", after="loss")
    other_href = S.see_all_href("back-in", after="win-or-level")
    n_loss, n_other = len(nt.after_loss), len(nt.comparison)
    if not nt.back_in_enough:
        line = Markup("{} {} came next after a loss and {} after a win or a level trade: too few "
                      "to set side by side. Each needs {}.").format(
            _w(n_loss, "trades", opens=loss_href if n_loss else None),
            "trade" if n_loss == 1 else "trades",
            _w(n_other, "trades", opens=other_href if n_other else None),
            _w(mx.B1_MINIMUM, "trades"))
        m_loss = m_other = None
    else:
        m_loss, m_other = _minutes(nt.loss_median), _minutes(nt.comparison_median)
        line = Markup("After a loss your next trade came a median {} {} later; "
                      "after a win or a level trade, {}.").format(
            _w(m_loss, "minutes", opens=loss_href), "minute" if m_loss == 1 else "minutes",
            _w(m_other, "minutes", opens=other_href))
    return {
        "line": line,
        "groups": [
            {"label": "After a loss", "trades": n_loss, "median": m_loss, "href": loss_href},
            {"label": "After a win or a level trade", "trades": n_other, "median": m_other,
             "href": other_href},
        ],
    }


def _same_way_view(ctx: dict) -> dict:
    nt = ctx["next_trades"]
    loss_n = nt.same_after_loss + nt.other_after_loss
    win_n = nt.same_after_win + nt.other_after_win
    loss_href, win_href = S.see_all_href("same-way", after="loss"), S.see_all_href("same-way", after="win")
    least = mx.CLOCK_MINIMUM_TRADES
    if loss_n >= least and win_n >= least:
        line = Markup("After a loss, your next trade went the same way {} times; after a win, {}.").format(
            _w(_rate(nt.same_after_loss, loss_n), "trades", "out_of_a_hundred", loss_href),
            _w(int(_rate(nt.same_after_win, win_n).quantize(Decimal(1), rounding="ROUND_HALF_UP")),
               "of 100", opens=win_href))
    else:
        line = Markup("After a loss, your next trade went the same way {} of {} times; ").format(
            _w(nt.same_after_loss, "trades", opens=loss_href if loss_n else None), _w(loss_n, "trades"))
        if win_n:
            line += Markup("after a win, {} of {}.").format(
                _w(nt.same_after_win, "trades", opens=win_href), _w(win_n, "trades"))
        else:
            line += Markup("after a win, no trade came next.")
        line += Markup(" Too few for a rate: a rate needs 30 trades in each group.")
    return {
        "line": line,
        "groups": [
            {"label": "After a loss", "same": nt.same_after_loss, "other": nt.other_after_loss, "href": loss_href},
            {"label": "After a win", "same": nt.same_after_win, "other": nt.other_after_win, "href": win_href},
        ],
        "no_direction": nt.no_direction,
        "scratch": nt.scratch,
    }


def _next_day_view(ctx: dict) -> dict:
    da = ctx["day_after"]
    rows = _next_day_rows(da)
    best, worst, other = rows

    def part(r, full: bool) -> Markup:
        if not r["days"]:
            return Markup("no day")
        out = Markup("{} trades a day" if full else "{}").format(_amount(r["per_day"], "trades a day", r["href"]))
        if r["lots"] is not None:
            out += Markup(" at {} lots" if full else " at {}").format(_amount(r["lots"], "lots"))
        return out

    line = (Markup("On the days after your best days you took ") + part(best, True)
            + Markup("; after your worst days, ") + part(worst, False)
            + Markup("; usually ") + part(other, False) + Markup("."))
    return {"line": line, "rows": rows,
            "best_days": [formatting.day(d) for d in da.best],
            "worst_days": [formatting.day(d) for d in da.worst]}


def _trades_said(n: int) -> str:
    return f"{formatting.count(n)} {'trade' if n == 1 else 'trades'}"


def _figure(key: str, ctx: dict, imp) -> Figure:
    """The figure a fact leads with, as its slice and its card show it, and what it counts."""
    if key == "after-close":
        return ACL.figure(ACL.view(ctx))
    if key == "hidden":
        return Figure(f"{formatting.count(_counted_days(ctx))} days", "days")
    if key == "worst-days":
        return Figure(formatting.rupees(ctx["worst_days"].sum), "rupees")
    if key == "share":
        share = ctx["share"]
        if share.shown_as_percentage:
            return Figure(f"{share.share_percent}%", "percent", of="your losses")
        return Figure(formatting.rupees(share.total), "rupees")  # the second state leads with the whole result
    if key == "money":
        found = ctx["money_found"]
        return Figure(formatting.rupees(
            found.same_day_net if found.same_day_count else ctx["held_past_day"].net
        ), "rupees")
    if key == "math":
        return Figure(f'{formatting.out_of_a_hundred(ctx["strike"].rate_percent)} trades', "trades")
    if key == "run":
        return Figure(f"{formatting.count(ctx['run'].length)} trades", "trades")
    if key == "clock":  # the hour with the largest result across the books: what happened there
        return Figure(f"{_hour_words(mx.lead_clock(ctx['clocks']).largest.hour)} hour", "hour")
    if key == "down":  # the trades right after two losses: the fact, as its wedge counts it
        return Figure(_trades_said(ctx["two_losses"].condition), "trades")
    if key == "back-in":
        nt = ctx["next_trades"]
        if not nt.back_in_enough:
            return Figure(_trades_said(len(nt.after_loss)), "trades")
        return Figure(_minutes_said(nt.loss_median), "minutes")
    if key == "same-way":
        nt = ctx["next_trades"]
        after_loss = nt.same_after_loss + nt.other_after_loss
        if after_loss >= mx.CLOCK_MINIMUM_TRADES:
            return Figure(formatting.out_of_a_hundred(_rate(nt.same_after_loss, after_loss)), "trades")
        return Figure(f"{formatting.count(nt.same_after_loss)} of {formatting.count(after_loss)}", "trades")
    if key == "next-day":
        best = _next_day_rows(ctx["day_after"])[0]
        return Figure(f"{_plain(best['per_day'])} a day", "trades a day")
    if key == "busiest":
        return Figure(f"{ctx['days'].busiest_vs_normal}×", "times your normal day")
    if key == "unread":
        return Figure(f"{formatting.count(imp.rows_parsed)} of {formatting.count(imp.rows_in)} rows", "rows")
    if key == "risk":
        return Figure(f"{formatting.count(ctx['risk'].showable)} of {formatting.count(len(ctx['trips']))} trades",
                      "trades")
    return Figure(str(NOT_TOLD), "things we have not told you")


def _busiest_story(ctx: dict) -> dict | None:
    """The busiest day as its page tells it: metrics counted it, this words the parts."""
    if not ctx["days"].busiest_day:
        return None
    st = mx.busiest_day_story(mx.same_day_trips(ctx["trips"]), ctx["days"].busiest_day)
    drawn = [(t.side, _f(t.net)) for t in st.strip]
    what = f"{st.book} trade" if st.strip_is_the_book else "option trade"
    spread_holds = st.median_hold_seconds is not None and not st.holds_alike
    return {
        "day": formatting.day(st.day),
        "trades": st.trades,
        "net": st.net,
        "book": st.book,
        "book_trades": st.book_trades,
        "book_net": st.book_net,
        "strike": f"{st.strike.normalize():f}" if st.strike is not None else None,
        "strikes": st.strikes,
        "lots": st.lots,
        "lots_low": st.lots_low,
        "lots_high": st.lots_high,
        "switches": st.switches,
        "one_side": {"CE": "calls", "PE": "puts"}.get(st.one_side),
        "only_positions": st.only_positions,
        "started": formatting.time_of_day(st.started) if st.started else "",
        "ended": formatting.time_of_day(st.ended) if st.ended else "",
        "holding_each": formatting.minutes_in_words(st.median_hold_seconds) if st.holds_alike else None,
        "median_hold": formatting.minutes_in_words(st.median_hold_seconds) if spread_holds else None,
        "longest_hold": formatting.minutes_in_words(st.longest_hold_seconds, about=False) if spread_holds else None,
        "held_past_day": st.held_past_day,
        "strip": G.chart_call_put(drawn, PAGE_W, PAGE_H) if drawn else None,
        "strip_caption": f"The {len(drawn)} {what}{'' if len(drawn) == 1 else 's'} that day, in order.",
        "strip_has_positions": any(t.side == "both" for t in st.strip),
    }



NOT_ENOUGH_YET = "not enough trades yet"
HIDDEN_COLUMNS = ("First half", "Second half", "All its days")
HIDDEN_ROWS = (
    ("days", "Days traded"),
    ("green_days", "Green days"),
    ("green_months", "Green months"),
    ("new_high", "Days since a new high"),
    ("net_per_trade", "Net per trade"),
    ("win", "You win"),
    ("break_even", "Break even at"),
)
"""The plain-counts page's rows (TICKET-910), in the order its table writes them. New copy (D9)."""


def _counted_days(ctx: dict) -> int:
    """Trading days with a same-day trade: what the plain-counts page counts from."""
    return len({t.trading_day for t in mx.same_day_trips(ctx["trips"])})


def _hidden_link(text: str, noun: str, href: str):
    """A count on the plain-counts page, opening the trades it was counted from (TICKET-905)."""
    return formatting.opens(Figure(text, noun, opens=href))


def _hidden_cell(half, href: str, row: str):
    """One count of one half, written, and opening that half's trades."""
    if row == "days":
        return _hidden_link(formatting.count(half.days), "days", href)
    if row == "green_days":
        return (_hidden_link(formatting.count(half.green_days), "days", href) + " ("
                + _hidden_link(formatting.out_of_a_hundred(half.green_day_percent), "percent", href) + ")")
    if row == "green_months":
        return (_hidden_link(formatting.count(half.green_months), "months", href) + " of "
                + _hidden_link(formatting.count(half.months), "months", href))
    if row == "new_high":
        if half.days_since_high is None:
            return "no new high yet"
        return _hidden_link(formatting.count(half.days_since_high), "days", href)
    if row == "net_per_trade":
        return _hidden_link(formatting.rupees(half.net_per_trade), "rupees", href)
    if half.math.win_percent is None:
        return NOT_ENOUGH_YET
    if row == "win":
        return _hidden_link(formatting.out_of_a_hundred(half.math.win_percent), "percent", href)
    if half.math.break_even_percent is None:
        return "\u2014"
    return _hidden_link(formatting.out_of_a_hundred(half.math.break_even_percent), "percent", href)


def _trades_word(n: int) -> str:
    return "trade" if n == 1 else "trades"


def _count_link(n: int, href: str | None):
    """A count of trades inside a sentence, as a figure, opening them when there are any."""
    return formatting.opens(Figure(formatting.count(n), _trades_word(n), opens=href if n else None))


def _previous_rows(ctx: dict) -> dict[str, list[dict]]:
    """The hiding page's two figures for previous result (TICKET-919), per book, as written.

    Every figure goes through Figure with its noun and opens its own trades; each carries its
    band and its two labels. The page decides nothing: the chance line reads the band through
    the |inside filter, and a figure inside its band is the result, never a blank."""
    out: dict[str, list[dict]] = {}
    for r in ctx.get("previous_result", ()):
        after = f"a {r.state}"
        record_href = S.see_all_href("hidden", book=r.book, after=r.state)
        n = len(r.record_ids)
        row = {
            "state": r.state,
            "record": _hidden_link(formatting.rupees(r.record_net), "rupees", record_href),
            "record_words": Markup("net on {} {} opened right after {} that day").format(
                _count_link(n, record_href), _trades_word(n), after),
            "record_band": r.record_band,
            "record_finding": findings.of_figure("hidden.record"),
            "then": NOT_ENOUGH_YET,
            "then_words": "",
            "then_band": r.then_band,
            "then_finding": findings.of_figure("hidden.then"),
        }
        if r.reached:
            k = len(r.then_ids)
            then_href = (S.see_all_href("hidden", book=r.book, after=r.state, then="yes")
                         if k else None)
            minimum = formatting.opens(Figure(formatting.count(r.minimum), "trades"))
            if not k:  # nothing was picked: said plainly, with no figure and no verdict on it
                row["then"] = Markup(
                    "no trade after {} was opened while your earlier ones after {}, {} or more,"
                    " were down overall").format(after, after, minimum)
            else:
                row["then"] = formatting.opens(
                    Figure(formatting.rupees(r.then_net), "rupees", opens=then_href))
                row["then_words"] = Markup(
                    "net on {} {} opened right after {} that day while your earlier ones after {},"
                    " {} or more, were down overall").format(
                    _count_link(k, then_href), _trades_word(k), after, after, minimum)
        out.setdefault(r.book, []).append(row)
    return out


def _hidden_view(ctx: dict) -> dict:
    """The plain-counts page (TICKET-910): each book's own halves, as its table writes them.

    Every count opens the same-day trades of its book and half, built here from the rows
    metrics.book_halves decided, never by a page. The p sits beside the change in net per trade
    it checks. Nothing here is called a finding, ranked or priced."""
    books = []
    previous = _previous_rows(ctx)
    for r in ctx["book_halves"]:
        every = S.see_all_href("hidden", book=r.book)
        if r.state is not COUNTED:
            books.append({"book": r.book, "counted": False, "n": r.trades,
                          "trades": _hidden_link(formatting.count(r.trades), "trades", every),
                          "previous": previous.get(r.book, [])})
            continue
        halves = (
            (r.first, S.see_all_href("hidden", book=r.book, half="first")),
            (r.second, S.see_all_href("hidden", book=r.book, half="second")),
            (r.whole, every),
        )
        rows = []
        for row, label in HIDDEN_ROWS:
            rows.append({"label": label, "control": None,
                         "cells": [_hidden_cell(half, href, row) for half, href in halves]})
            if row == "net_per_trade":
                change = _hidden_link(formatting.rupees(r.change_in_net_per_trade), "rupees", every)
                p = r.control.p if r.control is not None else None
                checked = (NOT_ENOUGH_YET if p is None
                           else _hidden_link(f"{p:.3f}", "share of shuffles", every))
                rows.append({"label": "Change, second half against first", "control": None,
                             "cells": ["", "", change]})
                rows.append({"label": "Whole days shuffled between the halves: p",
                             "control": "net-per-trade", "cells": ["", "", checked]})
        books.append({"book": r.book, "counted": True, "n": r.trades, "columns": HIDDEN_COLUMNS, "rows": rows,
                      "previous": previous.get(r.book, [])})
    return {"books": books, "held": ctx["held_past_day"], "draws": mx.halves_shuffle.DRAWS}


def _break_even_lines(ctx: dict) -> list[dict]:
    """What it would have taken each book to break even: the amount per winner, from the same
    row as the math page's table. A book under the minimum has no row to read, and a book that
    made back what it lost has nothing to say. Which lever to pull isn't ours to say."""
    rows = (book.whole for book in ctx["book_math"])
    return [
        {"book": row.label, "more": row.winner_gap}
        for row in rows
        if row.state is s.ResultState.COUNTED_FACT and row.winner_gap is not None and row.winner_gap > 0
    ]



NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
"""As the ruled lines say them: "After four losses". Past ten, a figure."""
TIMELINE_H, CARD_TIMELINE_H = 170, 96
NIGHT_SHARE = 0.06  # the width a left-out night takes on a run's timeline
HOUR_SECONDS = 60 * 60
SPAN_CLOSE_ENOUGH = 10 * 60  # within this of a whole hour, a span says the hour without "about"


def _number(n: int) -> str:
    return NUMBER_WORDS[n] if 0 <= n < len(NUMBER_WORDS) else formatting.count(n)


def _book_words(book: str) -> str:
    """A book mid-sentence: crude options, stocks and ETFs. An exchange's name stays as written."""
    head = book.split(" ")[0]
    return book if head.isupper() else book[0].lower() + book[1:]


def _books_words(books: list[str]) -> str:
    if len(books) > 3:
        return f"{len(books)} books"
    words = [_book_words(b) for b in books]
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def _days_words(days: list[str]) -> str:
    if len(days) == 1:
        return formatting.day(days[0])
    return f"{formatting.day(days[0])} to {formatting.day(days[-1])}"


def _span_words(seconds: int) -> str:
    """How long a run took on one day. Near a whole hour it says that hour; else "about"."""
    if seconds < HOUR_SECONDS:
        minutes = max(1, seconds // 60)
        return f"in {minutes} minute{'' if minutes == 1 else 's'}"
    hours = (seconds + HOUR_SECONDS // 2) // HOUR_SECONDS
    close = abs(seconds - hours * HOUR_SECONDS) <= SPAN_CLOSE_ENOUGH
    return f"in {'' if close else 'about '}{_number(hours)} hour{'' if hours == 1 else 's'}"


def _lead_words(story: mx.RunStory) -> str:
    """The headline's first half: the count, and how long it took if that can be said."""
    count = "1 loss" if story.length == 1 else f"{formatting.count(story.length)} losses in a row"
    if len(story.days) > 1:
        return f"{count}, across {len(story.days)} days"
    return f"{count}, {_span_words(story.span_seconds)}" if story.same_day else count


def _size_words(size: mx.SizeRise | None) -> str | None:
    """Doubled or tripled only where the steps are exactly that; otherwise raised."""
    if size is None:
        return None
    before = "one loss" if size.losses_before == 1 else f"{_number(size.losses_before)} losses"
    base = size.steps[0]
    multiples = [step / base for step in size.steps[1:]]
    if multiples == [2.0, 3.0]:
        did = "doubled your size, then tripled it"
    elif multiples == [2.0]:
        did = "doubled your size"
    elif multiples == [3.0]:
        did = "tripled your size"
    else:
        did = "raised your size"
    steps = " → ".join(formatting.count(step) for step in size.steps)
    return f"After {before} you {did} ({steps})."


def _flips_words(flips: int) -> str | None:
    if not flips:
        return None
    return "once" if flips == 1 else f"{formatting.count(flips)} times"


def _story_words(story) -> dict:
    """The run page's three lines, from a run or a day: switches, a size step, re-entries.
    The run page and each of the five worst days say them through ``scope/_story_lines.html``."""
    return {"flips_words": _flips_words(story.flips), "size_words": _size_words(story.size),
            "back_in": story.back_in}


def days_worst_to_best(trips: list) -> list[dict]:
    """Every trading day, worst to best (ties: earlier date first), with the running total
    of the days so far. The last total is the record's result: the shape is the share."""
    out, total = [], Decimal(0)
    for d in sorted(mx.daily_series(trips), key=lambda d: (d.net, d.trading_day)):
        total += d.net
        out.append({"iso": d.trading_day, "day": formatting.day(d.trading_day), "net": d.net,
                    "cumulative": total})
    return out


def _timeline_x(moments: list) -> dict:
    """Each moment's place across the timeline: each date its own stretch, in proportion to
    how long it runs, with a fixed gap for each night left out. x maps each moment to its place;
    the rest is what the hour ticks need."""
    dates = sorted({m.date() for m in moments})
    spans = {
        d: (min(m for m in moments if m.date() == d), max(m for m in moments if m.date() == d))
        for d in dates
    }
    seconds = {d: (spans[d][1] - spans[d][0]).total_seconds() for d in dates}
    total = sum(seconds.values())
    room = 1 - NIGHT_SHARE * (len(dates) - 1)
    # A date with one moment still takes some room, or its trades would stack on a line.
    weights = {d: (seconds[d] / total if total else 1 / len(dates)) for d in dates}
    weights = {d: max(w, 0.1) for d, w in weights.items()}
    scale = room / sum(weights.values())
    placed, starts, x = {}, {}, 0.0
    for d in dates:
        width = weights[d] * scale
        starts[d] = (x, width)
        x += width + NIGHT_SHARE
    for m in moments:
        start, width = starts[m.date()]
        d = m.date()
        placed[m] = start + (width * (m - spans[d][0]).total_seconds() / seconds[d] if seconds[d] else width / 2)
    return {"x": placed, "breaks": [starts[d][0] - NIGHT_SHARE / 2 for d in dates[1:]], "spans": spans, "starts": starts, "seconds": seconds}


def _timeline(story: mx.RunStory) -> dict:
    """What chart_run_timeline draws for this run and the first trade after it."""
    shown = [*story.trades, story.after] if story.after else list(story.trades)
    laid = _timeline_x([t.entry_ts for t in shown] + [t.exit_ts for t in shown])
    x_of = laid["x"]
    sizes: dict[str, int] = {}
    for t in shown:
        if mx.call_or_put(t) and t.lines[0].quantity:
            sizes[t.symbol] = max(sizes.get(t.symbol, 0), t.lines[0].quantity)
    points = []
    for t, running in story.running:
        side = mx.call_or_put(t)
        size = None
        if side and t.lines[0].quantity:
            size = t.lines[0].quantity / sizes[t.symbol]
        points.append(
            {"x": x_of[t.exit_ts], "y": _f(running), "size": size,
             "kind": {"CE": "call", "PE": "put"}.get(side, "plain")}
        )
    hours = []
    for d, (start, end) in laid["spans"].items():
        tick = start.replace(minute=0, second=0, microsecond=0)
        while tick <= end:
            if tick >= start:
                offset, width = laid["starts"][d]
                seconds = laid["seconds"][d]
                hours.append(offset + (width * (tick - start).total_seconds() / seconds if seconds else 0))
            tick = tick + timedelta(hours=1)
    run_end = max(x_of[t.exit_ts] for t in story.trades)
    return {
        "start_x": x_of[story.trades[0].entry_ts],
        "points": points,
        "band": (x_of[story.trades[0].entry_ts], run_end),
        "breaks": laid["breaks"],
        "hours": hours,
    }


def _axis_label(moment, many_dates: bool) -> str:
    time = moment.strftime("%H:%M")
    return f"{formatting.day(moment.date().isoformat())} {time}" if many_dates else time


def _summary_words(story: mx.RunStory) -> str:
    """One run as a line says it: how many, when, in what."""
    count = "1 loss" if story.length == 1 else f"{formatting.count(story.length)} losses"
    return f"{count}, {_days_words(story.days)}, {_books_words(story.books)}"


def _run_view(ctx: dict) -> dict:
    """The run's page and card: its story, in words, with its charts. Nothing here is counted:
    metrics.run_story decides every figure."""
    trips = ctx["trips"]
    story = mx.run_story(trips, ctx["run"].trip_ids)
    if story is None:
        return {"story": None, "timeline": None, "card_timeline": None}
    costliest = ctx["costliest_run"]
    other = None
    if costliest.trip_ids != ctx["run"].trip_ids:
        worst = mx.run_story(trips, costliest.trip_ids)
        other = {"summary": _summary_words(worst), "net": worst.net}
    plan = _timeline(story)
    shown = [*story.trades, story.after] if story.after else list(story.trades)
    moments = [t.entry_ts for t in shown] + [t.exit_ts for t in shown]
    many_dates = len({m.date() for m in moments}) > 1
    closes_with_a_name = not story.same_day or (
        story.after is not None and story.after.trading_day != story.last_day
    )
    opened = story.trades[0].entry_ts.strftime("%H:%M")
    view = {
        "lead": _lead_words(story),
        "when": _days_words(story.days),
        "what": _books_words(story.books),
        "net": story.net,
        "summary": _summary_words(story),
        "costliest": other,
        "flips_words": _flips_words(story.flips),
        "size_words": _size_words(story.size),
        "back_in": story.back_in,
        "after": S.trade(
            story.after, trips.index(story.after) + 1, story.gaps.get(story.after.trip_id)
        ) if story.after else None,
        "closed_on": formatting.day(story.last_day) if closes_with_a_name else "That day",
        "last_day_net": story.last_day_net,
        "started": f"on {formatting.day(story.days[0])} at {opened}" if len(story.days) > 1 else f"at {opened}",
        "axis_from": _axis_label(min(moments), many_dates),
        "axis_to": _axis_label(max(moments), many_dates),
        "has_call": any(p["kind"] == "call" for p in plan["points"]),
        "has_put": any(p["kind"] == "put" for p in plan["points"]),
        "has_plain": any(p["kind"] == "plain" for p in plan["points"]),
        "lowest": story.lowest,
        "last": story.last,
    }
    return {
        "story": view,
        "timeline": G.chart_run_timeline(**plan, w=PAGE_W, h=TIMELINE_H),
        "card_timeline": G.chart_run_timeline(**plan, w=CARD_W, h=CARD_TIMELINE_H),
    }


def span_words(minutes: int) -> str:
    """How long a run took, as a sentence says it: minutes under the hour, then hours."""
    if minutes < 60:
        return f"{minutes} minute{'' if minutes == 1 else 's'}"
    hours = round(minutes / 60)
    return f"{hours} hour{'' if hours == 1 else 's'}"


def _flagged_days(ctx: dict, figs: dict) -> dict:
    """The two days the report's ending points at (ruling on TICKET-825): where the longest
    losing run began, and the worst of the five worst days that is not that day."""
    flagged: dict = {"run": None, "worst": None}
    run = ctx["run"]
    if not figs["run"]["state"] and run.days:
        shown = mx.subset(ctx["trips"], run.trip_ids)
        minutes = (max(t.exit_ts for t in shown) - min(t.entry_ts for t in shown)).seconds // 60
        flagged["run"] = {
            "iso": run.days[0], "day": formatting.day(run.days[0]), "losses": run.length,
            "day_count": len(run.days), "span": None if run.crosses_days else span_words(minutes),
        }
    if not figs["worst-days"]["state"]:
        for d in ctx["worst_days"].days:
            if not flagged["run"] or d.trading_day != flagged["run"]["iso"]:
                flagged["worst"] = {"iso": d.trading_day, "day": formatting.day(d.trading_day),
                                    "trades": d.trips, "net": d.net}
                break
    return flagged


SHARED_BY_AT_LEAST = 4
"""The founder's ruling: "in common" only when true of all five days or of four of the five."""

SHORTEST_RUN = 2
"""One loss is not a run."""

def _part_of_day(hour: int) -> str:
    """The day as a trader splits it: morning, the NSE afternoon, the crude evening."""
    if hour < 12:
        return "before noon"
    return "between noon and 5 pm" if hour < 17 else "after 5 pm"


def _shared(labels: dict[str, str | None]) -> tuple[str, frozenset[str]] | None:
    """The label that at least four of the five days have, and those days."""
    counts = Counter(label for label in labels.values() if label is not None)
    if not counts:
        return None
    label, count = counts.most_common(1)[0]
    if count < SHARED_BY_AT_LEAST:
        return None
    return label, frozenset(day for day, value in labels.items() if value == label)


def _of_the_five(count: int) -> str:
    return "All 5 of your worst days" if count == 5 else f"{count} of your 5 worst days"


def worst_days_in_common(ctx: dict) -> list[str]:
    """What the five worst days share, from the ruling's four things only, each said as a count.

    Book, hour of the first trade, number of trades, longest losing run; true of all five or of
    four. Nothing here is a new number or a cause. An empty list means nothing is shared, and
    the page says so.
    """
    blocks = ctx["day_blocks"]
    if len(blocks) < 5:
        return []

    lines = []
    book = _shared({b.trading_day: b.book for b in blocks})
    hour = _shared({b.trading_day: _part_of_day(b.first_in.hour) for b in blocks})
    book_words = formatting.book_in_a_sentence(book[0]) if book else ""
    if book and hour and book[1] == hour[1]:
        lines.append(f"{_of_the_five(len(book[1]))} were {book_words}, {hour[0]}.")
    else:
        if book:
            lines.append(f"{_of_the_five(len(book[1]))} were {book_words}.")
        if hour:
            lines.append(f"{_of_the_five(len(hour[1]))} began {hour[0]}.")

    normal = ctx["days"].normal_day
    busier = sum(b.trades > normal for b in blocks)
    if busier >= SHARED_BY_AT_LEAST:
        lines.append(f"{_of_the_five(busier)} had more trades than your normal day of {normal}.")

    runs = sorted(b.longest_run for b in blocks)
    if runs[0] >= SHORTEST_RUN:
        lines.append(f"{_of_the_five(5)} had at least {runs[0]} losses in a row.")
    elif runs[1] >= SHORTEST_RUN:
        lines.append(f"{_of_the_five(4)} had at least {runs[1]} losses in a row.")
    return lines


def _day_span(block: mx.DayBlock) -> str:
    start = f"{block.first_in:%H:%M}"
    if block.last_out.date().isoformat() == block.trading_day:
        return f"{start} to {block.last_out:%H:%M}"
    return f"{start}, last trade closed {formatting.day(block.last_out.date().isoformat())}"


def _day_went(block: mx.DayBlock) -> str:
    if block.trades == 1:
        return f"One trade: {formatting.rupees(block.net)}."
    return (f"First trade {formatting.rupees(block.first_net)}, then {block.later} more {'trade' if block.later == 1 else 'trades'}; "
            f"{block.later_lost} lost.")


def _day_block(block: mx.DayBlock, ctx: dict) -> dict:
    normal = ctx["days"].normal_day
    only = [t for t in ctx["trips"] if t.trading_day == block.trading_day]
    times = f"{block.trades / float(normal):.1f}".removesuffix(".0") if normal else None
    return {
        "iso": block.trading_day,
        "day": formatting.day(block.trading_day),
        "books": ", ".join(block.books),
        "trades": block.trades,
        "span": _day_span(block),
        "net": block.net,
        "went": _day_went(block),
        "line": day_chart.mini(mx.day_path(only)),  # the day page's path, drawn small
        "story": _story_words(mx.day_story(only)),
        "vs_normal": f"{times}× your normal day's trades" if times else None,
        "groups": S.groups("worst-days", ctx, only=only),
    }


def facts(ctx: dict, imp) -> dict[str, dict]:
    """Every fact's figure, state, card chart, mini chart and the counts its card needs."""
    trips = ctx["trips"]
    series = mx.daily_series(trips)
    out: dict[str, dict] = {}
    for key, fact in S.FIGURES.items():
        state = _state(key, ctx)
        kind = fact.chart
        behind = len(S.trades_behind(key, ctx))
        lead = Figure("—", "no figure yet") if state else _figure(key, ctx, imp)
        opens = None if state else _opens(key, ctx)
        mini, mini_label = (None, "") if state else _mini(key, ctx, imp)
        out[key] = {
            "key": key,
            "finding": findings.of(key),  # both labels, or Unlabelled before any page
            "title": fact.title,
            "state": state,
            "figure": str(lead),
            "opens": opens,
            "lead_figure": Figure(lead.value, lead.noun, of=lead.of, opens=opens),
            "noun": lead.noun,
            "href": S.fact_href(key),
            "trade_count": behind,
            "see_all": S.see_all_href(key) if behind > S.INLINE_TRADES else None,
            "chart": None
            if state or kind not in CARD_H
            else _chart(kind, ctx, imp, CARD_W, CARD_H[kind], False),
            "mini": mini,
            "mini_label": mini_label,
        }
    out["worst-days"].update(
        first_day=formatting.day(series[0].trading_day) if series else "",
        last_day=formatting.day(series[-1].trading_day) if series else "",
    )
    counted_days = sorted({t.trading_day for t in mx.same_day_trips(trips)})
    out["busiest"].update(
        first=formatting.day(counted_days[0]) if counted_days else "",
        last=formatting.day(counted_days[-1]) if counted_days else "",
        busiest_date=formatting.day(ctx["days"].busiest_day) if ctx["days"].busiest_day else "",
    )
    out["busiest"]["story"] = _busiest_story(ctx)
    out["hidden"].update(_hidden_view(ctx))
    out["math"]["lead_lines"] = _break_even_lines(ctx)
    two_losses = ctx["two_losses"]
    same_day = mx.same_day_trips(trips)
    check = mx.post_loss_check(same_day) if same_day else None
    out["down"]["post_loss_level"] = check.level if check else None
    out["down"]["post_loss_needs"] = None if check is None or check.level != "not_enough" else {
        "condition": max(0, b2_shuffle.MIN_CONDITION - check.n_condition),
        "comparison": max(0, b2_shuffle.MIN_COMPARISON - check.n_comparison),
    }
    out["down"]["post_loss_sentence"] = (
        mx.post_loss_sentence_may_show(same_day)
        and two_losses.condition_mean is not None
        and two_losses.comparison_mean is not None
    )
    if not out["back-in"]["state"]:
        out["back-in"].update(_back_in_view(ctx))
    if not out["same-way"]["state"]:
        out["same-way"].update(_same_way_view(ctx))
    if not out["next-day"]["state"]:
        out["next-day"].update(_next_day_view(ctx))
    out["money"]["days"] = [formatting.day(t.trading_day) for t in ctx["best"] + ctx["worst"]]
    # The card names each group's days beside its words, in the bars' order (the kit's chart
    # itself is byte for byte, so the dates can't go inside it).
    out["money"]["best_days"] = [formatting.day(t.trading_day) for t in ctx["best"]]
    out["money"]["worst_days"] = [formatting.day(t.trading_day) for t in ctx["worst"]]
    out["money"]["held"] = ctx["held_past_day"]
    options = mx.option_result(trips)
    out["not-told"].update(
        options=options,
        options_amount=abs(options.net) if options else None,  # the sentence says lost or made
        flagged=_flagged_days(ctx, out),
    )
    out["math"]["held"] = ctx["held_past_day"]
    out["run"]["day_count"] = len(ctx["run"].days)
    out["run"]["start_day"] = formatting.day(ctx["run"].days[0]) if ctx["run"].days else None
    out["run"].update(_run_view(ctx))
    for key, fact in S.FIGURES.items():  # the fact page's figure: full width, 96 px
        out[key]["page_chart"] = (
            None if out[key]["state"] else _chart(fact.chart, ctx, imp, PAGE_W, PAGE_H, False)
        )
    normal = ctx["days"].normal_day
    out["worst-days"]["rows"] = [
        {
            "day": formatting.day(d.trading_day),
            "net": d.net,
            "trades": d.trips,
            # Exactly as the Mirror page printed it, "%.1f" of a float: moving the
            # sum here changes where it is done, never the figure (2.25 stays 2.2).
            "vs_normal": f"{d.trips / float(normal):.1f}" if normal else None,
        }
        for d in ctx["worst_days"].days
    ]
    sorted_days = days_worst_to_best(trips)
    out["worst-days"].update(
        sorted_days_table=charts.text_table(
            [(d["day"], Figure(d["net"], "rupees"), Figure(d["cumulative"], "rupees"))
             for d in sorted_days],
            ("Day", "Result", "Running total, worst day first"),
            caption="Your days, worst to best"),
        in_common=worst_days_in_common(ctx),
        blocks=[_day_block(b, ctx) for b in ctx["day_blocks"]],
        all_trades_href=S.see_all_href("worst-days"),
    )
    for key, fig in out.items():  # the chapter's dial: a wedge says what it says with no label
        fig["wedge"] = _no_answer(fig["state"]) if fig["state"] else _chapter_wedge(key, ctx, fig)
    out["money"]["pairs"] = [
        {
            "best": b,
            "worst": w,
            "best_day": formatting.day(b.trading_day),
            "worst_day": formatting.day(w.trading_day),
        }
        for b, w in zip(ctx["best"], ctx["worst"], strict=False)
    ]
    out["money"].update(
        found=ctx["money_found"],
        best_rows=S.ranked(ctx["best"], ctx),
        worst_rows=S.ranked(ctx["worst"], ctx),
        held_groups=[]
        if out["money"]["see_all"]
        else S.groups("money", ctx, only=ctx["held_past_day"].trips),
    )
    out["share"]["worst_day_count"] = len(ctx["worst_days"].days)
    c = ctx["risk"].counts
    out["risk"]["nothing"] = c[s.RiskUnitSourceV1.UNAVAILABLE] + c[s.RiskUnitSourceV1.INFERRED_ATR]
    out["risk"]["sizes"] = ctx["loss_sizes"]
    out["risk"]["premium"] = ctx["premium_paid"]
    out["risk"]["no_budget"] = c[s.RiskUnitSourceV1.DECLARED_BUDGET] == 0
    out["risk"]["structure"] = c[s.RiskUnitSourceV1.STRUCTURE_MAX_LOSS]
    out["risk"]["uncapped"] = c[s.RiskUnitSourceV1.UNCAPPED]
    out["risk"]["uncapped_trades"] = sum(t.uncapped for t in trips)  # a budget does not cap it
    out["clock"]["held"] = ctx["held_past_day"]
    out["clock"].update(_clock_view(ctx))
    out["after-close"].update(after_close_page(ctx))
    return out


def after_close_page(ctx: dict, pick: str | None = None) -> dict:
    """The after-you-closed page for one underlying: its view and its chart at the page's size.
    The route passes the chip the trader picked."""
    v = ACL.view(ctx, pick)
    return {"view": v, "page_chart": ACL.geometry(v)}


def _zone_words(trip: mx.Trip) -> str:
    """Which time an hour is in: the loader gives each instrument's in its own zone."""
    if trip.entry_ts.utcoffset() == INDIA_OFFSET:
        return "India time"
    name = getattr(trip.entry_ts.tzinfo, "key", None) or trip.entry_ts.tzname()
    return f"{name} time"


def _hour_words(hour: int) -> str:
    return f"{hour:02d}:00"


def _chart_of(clock: mx.BookClock, w: float, h: float) -> dict:
    """One book's hours, drawn as the kit draws the clock."""
    few = [i for i, hr in enumerate(clock.hours) if hr.small_sample]
    return G.chart_clock([_f(hr.net) for hr in clock.hours], few, w, h)


def _clock_view(ctx: dict) -> dict:
    """The clocks as the page draws them: books of 30 trades first, the rest behind a toggle.

    A history with no book that size leads with its biggest, so the page is never only a toggle.
    """
    zones: dict[str, set[str]] = {}
    for t in mx.same_day_trips(ctx["trips"]):
        zones.setdefault(mx.trade_book(t), set()).add(_zone_words(t))
    views = []
    for number, c in enumerate(ctx["clocks"], start=1):
        hours = [
            {
                "label": _hour_words(h.hour),
                "href": S.see_all_href("clock", book=c.book, hour=h.hour),
                "net": h.net,
                "trades": h.trips,
                "per_trade": h.per_trade,
                "small_sample": h.small_sample,
                "win_rate": h.win_rate,
            }
            for h in c.hours
        ]
        views.append(
            {
                "number": number,
                "book": c.book,
                "zone": " and ".join(sorted(zones[c.book])),
                "trades": c.trips,
                "hours": hours,
                "first_hour": hours[0]["label"],
                "last_hour": hours[-1]["label"],
                "largest": c.largest,
                "largest_label": _hour_words(c.largest.hour),
                "other": c.larger_per_trade,
                "other_label": _hour_words(c.larger_per_trade.hour) if c.larger_per_trade else "",
                "hides_a_rate": any(
                    h.win_rate_state is not COUNTED for h in c.hours
                ),
                "chart": _chart_of(c, CARD_W, CARD_H["clock"]),
                "page_chart": _chart_of(c, PAGE_W, PAGE_H),
            }
        )
    wide = [v for v in views if v["trades"] >= mx.CLOCK_MINIMUM_TRADES] or views[:1]
    lead = mx.lead_clock(ctx["clocks"])
    return {
        "clocks": wide,
        "other_clocks": views[len(wide):],
        "rate_minimum": mx.CLOCK_MINIMUM_TRADES,
        "lead_book": lead.book if lead else "",
        "lead": lead.largest if lead else None,
        "lead_label": _hour_words(lead.largest.hour) if lead else "",
    }


def _chapter_wedge(key: str, ctx: dict, fig: dict) -> dict:
    """Each fact's wedge on its chapter's dial (TICKET-880). Same figures its page shows."""
    if key == "hidden":
        n = formatting.count(_counted_days(ctx))
        return _wedge(Figure(n, "days", of="traded, in two halves"))
    if key == "worst-days":
        return _wedge(Figure(len(ctx["worst_days"].days), "days",
                             of=f"came to {formatting.rupees(ctx['worst_days'].sum)}"))
    if key == "money" and ctx["best"]:
        # A phone's wedge: the same words on two lines; a plus may go, never a minus (ruled 14 Nov).
        net = ctx["best"][0].net
        best = formatting.rupees(net)
        # Five digits and up run into a phone dial's centre ring: the toolkit's short form there
        # (₹11.5k). The desktop wedge and the page keep the whole figure.
        phone_best = charts.short(net) if abs(net) >= 10 * charts.THOUSAND else best.removeprefix("+")
        return _wedge(Figure(best, "rupees", of="your best trade"), shown=best,
                      phone="best\ntrade", phone_shown=phone_best)
    if key == "math":
        return _wedge(Figure(ctx["strike"].rate_percent, "trades", of="trades made money"),
                      shown=formatting.out_of_a_hundred(ctx["strike"].rate_percent))
    if key == "run":
        n = ctx["run"].length
        return _wedge(Figure(formatting.count(n), "loss" if n == 1 else "losses", of="in a row"),
                      phone_shown=f"{formatting.count(n)} lost")
    if key == "clock":
        hour = fig["figure"].removesuffix(" hour")
        return _wedge(Figure(hour, "hour", of="the hour of your largest result"),
                      phone="largest\nhour", shown=hour)
    if key == "down":
        return _wedge(_of(_trades(ctx["two_losses"].condition), "right after two losses"))
    if key == "back-in":
        nt = ctx["next_trades"]
        if not nt.back_in_enough:  # under B1's 30 a group, the count and "too few", never a median
            n = len(nt.after_loss)
            return _wedge(Figure(formatting.count(n), "trade" if n == 1 else "trades",
                                 of="after a loss, too few"))
        m = _minutes(nt.loss_median)
        return _wedge(Figure(m, "minutes", of="median wait after a loss"), shown=f"{formatting.count(m)} min")
    if key == "same-way":
        return _wedge(Figure(fig["figure"], "trades", of="the same way after a loss"), shown=fig["figure"])
    if key == "next-day":
        return _wedge(Figure(fig["figure"], "trades", of="trades after your best days"), shown=fig["figure"])
    if key == "busiest":
        on_day = fig["busiest_date"].replace(" ", chr(0xA0))  # a date holds together
        return _wedge(_of(_trades(ctx["days"].busiest_trips), f"on your busiest day, {on_day}"),
                      phone=f"busiest day,\n{on_day}")
    if key == "unread":
        read, _, whole = fig["figure"].removesuffix(" rows").partition(" of ")
        return _wedge(Figure(read, "rows", of=f"of {whole} rows read"), shown=read)
    if key == "risk":
        measured, _, whole = fig["figure"].removesuffix(" trades").partition(" of ")
        return _wedge(Figure(measured, "trades", of=f"of {whole} trades have a risk figure"),
                      phone=f"of {whole}\ntrades", shown=measured)
    if key == "after-close":
        v = ACL.view(ctx)
        return _wedge(Figure(formatting.count(v["came_back"]), "trades",
                             of=f"of {formatting.count(v['losers'])} losing trades came back past your entry"),
                      phone="came back\nafter you closed", shown=formatting.count(v["came_back"]))
    if key == "not-told":
        return _wedge(Figure(NOT_TOLD, "things", of="we have not told you"), phone="not told",
                      phone_shown=f"{NOT_TOLD} items")
    return _wedge(Figure(fig["figure"], fig["noun"], of="on same-day trades"), shown=fig["figure"])


def _opens(key: str, ctx: dict) -> str | None:
    """Every trade behind a fact's figure, from the same record that decided it (TICKET-905).
    The clock's figure is one hour of one book, so it opens that hour. A fact that counts rows
    or things rather than trades opens nothing."""
    if key not in TRADES_BEHIND:
        return None
    if not S.trades_behind(key, ctx):
        return None
    if key == "clock":
        lead = mx.lead_clock(ctx["clocks"])
        if lead is not None:
            return S.see_all_href("clock", book=lead.book, hour=lead.largest.hour)
    return S.see_all_href(key)


TRADES_BEHIND = frozenset(S.FACTS) - {"unread", "not-told"}
"""The facts whose figure has trades behind it: the same set the trade lists serve."""

HUB_FACT = {1: "worst-days", 2: "math", 3: "busiest", 4: "risk"}
"""Which fact each chapter's hub wedge takes its figure from, and so what it opens."""


def _list_row(f, fig: dict, item: dict) -> dict:
    """A fact said under the phone dial (Fact.on_phone_dial), in its desktop wedge's own words."""
    state = fig["state"]
    return {
        "key": f.key,
        "title": f.title,
        "href": S.fact_href(f.key),
        "state": state,
        "said": None if state else Figure(item["figure"], item.get("noun") or fig["noun"]),
        "of": (item.get("label") or "").replace("\n", " "),
        "finding": fig["finding"],
    }


def chapter_view(n: int, figs: dict[str, dict]) -> dict:
    """The chapter's dial, for the dial macro: its facts as slices, its name in the centre.

    On a phone the dial keeps the wedges main had for it: a fact off it
    (``Fact.on_phone_dial``) is said in ``phone_list`` under the dial instead, and the desktop
    dial draws every fact, in chapter order, from ``desktop_items``. A chapter with every fact on
    its dial has neither, and is drawn as it always was."""
    c = S.chapter(n)
    items, every, rows = [], [], []
    for f in c.facts:
        fig = figs[f.key]
        item = {
            "name": f.title,
            **fig["wedge"],
            "href": fig["opens"],  # the trades behind the wedge's figure, or nothing (TICKET-905)
            "state": fig["state"],
            "chart": "" if fig["state"] else f.chart,
        }
        if item["chart"]:
            if fig["mini"] is None:
                item["chart"] = ""  # a share that is not a percentage draws no bar
            else:
                item["mini"] = fig["mini"]
                if fig["mini_label"]:
                    item["miniLabel"] = fig["mini_label"]
        every.append(item)
        if f.on_phone_dial:
            items.append(item)
        else:
            rows.append(_list_row(f, fig, item))
    view = {
        "kind": "chapter",
        "items": items,
        "centre": {"name": c.name, "scopeHref": S.home_href(tap=n)},
    }
    if rows:
        view.update(desktop_items=every, phone_list=rows)
    return view


WIDE_COUNT = 100
LABEL_WIDTH = 12
"""Characters on a wedge's line under its figure, at the kit's 11 px, before it breaks."""


def _lines(words: str) -> str:
    """A wedge's words broken for its width, whole words only, and where they say to break."""
    lines: list[str] = []
    for part in words.split("\n"):
        start = len(lines)
        for word in part.split(" "):
            if len(lines) > start and len(lines[-1]) + 1 + len(word) <= LABEL_WIDTH:
                lines[-1] += f" {word}"
            else:
                lines.append(word)
    return "\n".join(lines)


def _wedge(figure: Figure, phone: str | None = None, shown: str | None = None,
           phone_shown: str | None = None) -> dict:
    """A wedge states a fact: cover its rim label and read it aloud, and it still says something
    (TICKET-880). So it is a figure with its noun, and what that figure is of. A phone's wedge
    has less room than a desktop's, so it can give the same fact in fewer words."""
    item = {"figure": shown or figure.with_noun, "label": _lines(figure.of or ""), "state": "",
            "noun": figure.noun}  # the noun its words are in, for a fact said under the phone dial
    if phone is not None:
        item["phone_label"] = _lines(phone)
    if phone_shown is not None:
        item["phone_figure"] = phone_shown
    return item


def _no_answer(state: str) -> dict:
    return {"figure": "—", "label": "", "state": state}


def _trades(n: int) -> Figure:
    return Figure(formatting.count(n), "trade" if n == 1 else "trades")


def _trades_wedge(n: int, of: str, phone: str) -> dict:
    """A count of trades in a hub wedge. Past 99 it is too wide beside its noun on a phone, and
    a third line has no room either, so there the count stands on its own over the short words."""
    figure = _of(_trades(n), of)
    if n < WIDE_COUNT:
        return _wedge(figure, phone=phone)
    return _wedge(figure, phone=phone, phone_shown=formatting.count(n))


def _of(figure: Figure, of: str) -> Figure:
    return Figure(figure.value, figure.noun, of=of)


def _answer_one(ctx: dict) -> dict:
    """Where your results came from: the five days, and how far past a normal day each was."""
    worst, normal = ctx["worst_days"], ctx["days"].normal_day
    if len(worst.days) < 5:
        return {"state": "not-enough", "wedge": _no_answer("not-enough")}
    least = min(d.trips / float(normal) for d in worst.days) if normal else 0
    share = ctx["share"]
    days = Figure(len(worst.days), "days")
    if share.shown_as_percentage:
        wedge = _wedge(_of(days, f"lost {share.share_percent}% of all you lost"),
                       phone=f"lost {share.share_percent}%")
    else:
        wedge = _wedge(_of(days, f"came to {formatting.rupees(worst.sum)}"),
                       phone=formatting.rupees(worst.sum))
    return {
        "state": "",
        "days_word": _number(len(worst.days)).capitalize(),
        "share": share,
        "worst_sum": worst.sum,
        "worst_loss": abs(worst.sum),
        "at_least": int(least) if least >= 2 else None,
        "wedge": wedge,
    }


def _answer_two(ctx: dict, figs: dict[str, dict]) -> dict:
    """Your patterns: the strike rate against what it would take, on same-day trades."""
    too_few = len(mx.same_day_trips(ctx["trips"])) < mx.BOOK_ROW_MINIMUM
    state = "not-enough" if too_few else figs["math"]["state"]
    if state:
        return {"state": state, "wedge": _no_answer(state)}
    strike, even = ctx["strike"], ctx["break_even"]
    return {"state": "", "strike": strike, "even": even,
            "wedge": _wedge(Figure(strike.rate_percent, "trades", of="trades made money"),
                            phone="made money", shown=formatting.out_of_a_hundred(strike.rate_percent))}


def _answer_three(ctx: dict, figs: dict[str, dict]) -> dict:
    """Your behaviour: the busiest day and what followed two losses. It says a direction only
    where the file's own test lets it (post_loss_sentence_may_show)."""
    state = figs["busiest"]["state"]
    if state or not figs["busiest"]["story"]:
        return {"state": state or "not-enough", "wedge": _no_answer(state or "not-enough")}
    story = figs["busiest"]["story"]
    return {
        "state": "",
        "story": story,
        "after_two": ctx["two_losses"].condition,
        "says_direction": bool(figs["down"].get("post_loss_sentence")),
        "wedge": _trades_wedge(story["trades"], "on your busiest day", "busiest day"),
    }


def _answer_four(ctx: dict, figs: dict[str, dict], number: Decimal | None) -> dict:
    """What we read: the honest close, which is what no figure can be worked out without."""
    uncapped = figs["risk"]["uncapped_trades"]
    past = ctx["past_number"]
    if number is not None and past.measured:
        wedge = _trades_wedge(past.count, "past your number", "past number")
    elif number is not None:  # set after these trades: no count, or "0" reads as a clean record
        wedge = _wedge(Figure("your", "number", of="is set"), shown="number")
    elif uncapped:
        wedge = _trades_wedge(uncapped, "we could not size", "not sized")
    else:
        wedge = _wedge(Figure("no", "number", of="is set yet"))
    return {"state": "", "number": number, "past": past, "uncapped": uncapped, "wedge": wedge}


def hub_answers(ctx: dict, figs: dict[str, dict], number: Decimal | None = None) -> dict[int, dict]:
    """Each chapter's answer on the hub: the figures its row says and its wedge shortens. All of
    them are the objects the chapter's own page renders, never worked out again."""
    return {1: _answer_one(ctx), 2: _answer_two(ctx, figs), 3: _answer_three(ctx, figs),
            4: _answer_four(ctx, figs, number)}


def home_view(
    ctx: dict,
    imp,
    *,
    gross: bool = False,
    opened: frozenset[int] = frozenset(),
    number: Decimal | None = None,
    answers: dict[int, dict] | None = None,
    figs: dict[str, dict] | None = None,
) -> dict:
    """Home's dial: each chapter's answer in its wedge, the trader's result in the centre. Read
    is the dot on the rim, and no words in the wedge. Each wedge opens the trades behind its
    figure (TICKET-905); one whose figure has none behind it is drawn plain."""
    figs = figs or facts(ctx, imp)
    answers = answers or hub_answers(ctx, figs, number)
    items = [
        {
            "name": c.name,
            **answers[c.number]["wedge"],
            "opened": c.number in opened,
            "href": _hub_opens(c.number, answers[c.number], figs),
        }
        for c in S.CHAPTERS
    ]
    caption = ["your result,", "before charges"] if gross else ["your result for", "the whole period"]
    centre = {"figure": formatting.rupees(ctx["share"].total), "captionLines": caption}
    return {"kind": "home", "items": items, "centre": centre}


def _hub_opens(n: int, answer: dict, figs: dict[str, dict]) -> str | None:
    """The trades behind a hub wedge's figure: its chapter's fact's own list. Chapter 4's wedge
    counts trades only when it says how many went past his number or couldn't be sized."""
    if answer.get("state"):
        return None
    if n == 4:
        past, uncapped = answer.get("past"), answer.get("uncapped")
        counts_trades = (past is not None and past.count) or (answer.get("number") is None and uncapped)
        if not counts_trades:
            return None
    return figs[HUB_FACT[n]]["opens"]


def home_context(
    ctx: dict, imp, opened: frozenset[int] = frozenset(), number: Decimal | None = None
) -> dict:
    """What Scope home shows: the verdict, the books, each chapter's answer, a way in."""
    figs = facts(ctx, imp)
    answers = hub_answers(ctx, figs, number)
    return {
        "view": home_view(ctx, imp, gross=not imp.fees_available, opened=opened, answers=answers,
                          figs=figs),
        "verdict": mx.verdict(ctx["trips"]),
        "chapters": [
            {
                "number": c.number,
                "name": c.name,
                "href": S.chapter_href(c.number, from_home=True),
                "opened": c.number in opened,
                "answer": answers[c.number],
            }
            for c in S.CHAPTERS
        ],
        "two_losses": ctx["two_losses"],
        "post_loss": figs["down"],
        # How many of the finding bar's fixed list run today, and how long the list is.
        "checks_run": len(mx.CHECKS_RUN),
        "checks_listed": len(multiplicity.family()),
    }


def short_answers(figs: dict[str, dict]) -> dict[str, str]:
    """Each page's answer in a few words, for All pages (TICKET-903): its chapter wedge, read
    aloud, so the panel and the dial say the same thing."""
    out = {}
    for key in S.FACTS:
        wedge = figs[key]["wedge"]
        out[key] = " ".join(f"{wedge['figure']} {wedge['label']}".split())
    return out


REVEAL_C = 150  # the reveal's dial: 300 x 300, the outer ring at 149.5 (kit screen 12)
REVEAL_SLICE_CIRCUMFERENCE = "622.04"  # 2 pi x 99, the slice's radius, as the kit writes it


def reveal_days(ctx: dict) -> dict:
    """How many days the reveal is about, from his file: his five worst, or every day he has
    when he has fewer than five. The page never says "five" about days he does not have."""
    n = len(ctx["worst_days"].days)
    word = _number(n)
    if n >= 5:
        title = "Your five worst days"
    elif n == 1:
        title = "Your one trading day"
    else:
        title = f"Your {word} trading days"
    return {"count": n, "word": word, "all_of_them": n < 5, "title": title}


def reveal_view(ctx: dict) -> dict:
    """The reveal's dial (handoff 7): the five worst days as one white slice from twelve
    o'clock to their share, the share in the centre. Its bezel and ring are the
    Scope's own (scope_geometry), at the kit's 300 px; a test holds them to the kit.

    Shown only when the share is a percentage (Appendix A); otherwise no slice and no
    figure, and the Mirror's other sentence says the whole result.
    """
    rr = G.radii(REVEAL_C)
    share = ctx["share"]
    # Every day he has is on the page below five: a share of 100% is true by construction and
    # states nothing, so the dial draws no slice and says what those days came to instead.
    short = len(ctx["worst_days"].days) < 5
    view = {
        "shown": share.shown_as_percentage and not short,
        "short": short,
        "outer": G.circle(REVEAL_C, REVEAL_C, rr["outer"]),
        "inner": G.circle(REVEAL_C, REVEAL_C, rr["inner"]),
        "ticks": G.ticks(REVEAL_C, REVEAL_C, rr, [0]),
        "circumference": REVEAL_SLICE_CIRCUMFERENCE,
    }
    if view["shown"]:
        fraction = _f(share.share_percent) / 100
        view["slice_length"] = G.fmt(float(REVEAL_SLICE_CIRCUMFERENCE) * fraction)
        view["edge_tick"] = G.radial(
            REVEAL_C, REVEAL_C, 360 * fraction, rr["majorStart"], rr["tickEnd"]
        )
    return view
