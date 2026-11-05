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

from markupsafe import Markup

from services.production.api import dial, formatting
from services.production.api import scope_geometry as G
from services.production.api import scope_map as S
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s

COUNTED = s.ResultState.COUNTED_FACT
CARD_W = 302  # a story card's chart width (the kit's chapter screens)
PAGE_W, PAGE_H = 350, 96  # a fact page's figure (the kit's fact screens)
CARD_H = {
    "worst": 84,
    "share": 56,
    "money": 150,
    "hold": 80,
    "strike": 40,
    "run": 40,
    "clock": 84,
    "busy": 84,
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
    two_losses = mx.two_straight_losses(trips)
    same_day = mx.same_day_trips(trips)
    after = mx.subset(trips, two_losses.condition_trip_ids)
    rest = mx.complement(trips, two_losses.condition_trip_ids)
    return {
        "worst_days": mx.five_worst_days(trips),
        "share": mx.share_of_losses(trips),
        "day_blocks": mx.worst_day_blocks(trips),
        "days": mx.day_counts(trips),
        "best": mx.best_five(same_day),
        "worst": mx.worst_five(same_day),
        "held_past_day": mx.held_past_day(trips),
        "past_number": mx.trades_past_number(trips),
        "two_losses": two_losses,
        "strike": mx.strike_rate(same_day),
        "break_even": mx.break_even(same_day),
        "lots": mx.average_lots(trips),
        "holding": mx.holding_time(same_day),
        "hours": mx.result_by_hour(same_day),
        "clocks": mx.clocks_by_book(same_day),
        "run": mx.longest_losing_run(trips),
        "risk": mx.risk_figure_counts(trips),
        "five_days": mx.five_days_read(trips),
        "loss_sizes": mx.loss_sizes(same_day),
        "premium_paid": mx.premium_by_book(same_day),
        "trips": trips,
        "after_strike": mx.strike_rate(after),
        "after_lots": mx.average_lots(after),
        "rest_strike": mx.strike_rate(rest),
        "rest_lots": mx.average_lots(rest),
        "days_with_the_condition": len({t.trading_day for t in after}),
    }


def _f(value) -> float:
    return float(value) if value is not None else 0.0


def _chart(kind: str, ctx: dict, imp, w: float, h: float, mini: bool):
    """The chart a fact draws, at a size; None where the fact has nothing to draw."""
    trips = ctx["trips"]
    if kind == "worst":
        return G.chart_worst([_f(d.net) for d in mx.daily_series(trips)], w, h)
    if kind == "share":
        share = ctx["share"]
        if not share.shown_as_percentage:
            return None  # a share that is not a percentage is not drawn as one
        return G.chart_share(_f(share.share_percent) / 100, w, h, mini)
    if kind == "money":
        return G.chart_money(
            [_f(t.net) for t in ctx["best"]], [_f(t.net) for t in ctx["worst"]], w, h
        )
    if kind == "hold":
        held = mx.holding_series(mx.same_day_trips(trips))  # one holding would blank the axis
        wins = [x / 60 for x in held.winners_seconds]
        losses = [x / 60 for x in held.losers_seconds]
        return G.chart_hold(wins, losses, max([*wins, *losses, 1]), w, h, mini)
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


def _state(key: str, ctx: dict) -> str:
    if key == "clock" and not ctx["hours"]:
        return "not-enough"  # every trade was held past its day
    if key == "risk" and ctx["risk"].showable == 0:
        return "not-in-file"  # no stop column and no budget: the kit's edge state e4
    metric = {
        "worst-days": "worst_days",
        "share": "share",
        "hold": "holding",
        "strike": "strike",
        "run": "run",
        "down": "two_losses",
        "busiest": "days",
    }.get(key)
    if metric and ctx[metric].state is not COUNTED:
        return "not-enough"
    return ""


def _figure(key: str, ctx: dict, imp) -> str:
    """The figure a fact leads with, as its slice and its card show it."""
    if key == "worst-days":
        return formatting.rupees(ctx["worst_days"].sum)
    if key == "share":
        share = ctx["share"]
        if share.shown_as_percentage:
            return f"{share.share_percent}%"
        return formatting.rupees(share.total)  # the second state leads with the whole result
    if key == "money":
        return f"{formatting.count(len(S.trades_behind('money', ctx)))} trades"
    if key == "hold":
        h = ctx["holding"]
        w, lo = (
            formatting.minutes(h.winners_median_seconds),
            formatting.minutes(h.losers_median_seconds),
        )
        return f"{w} · {lo} min"
    if key == "strike":
        return f"{ctx['strike'].rate_percent}%"
    if key == "run":
        return f"{formatting.count(ctx['run'].length)} trades"
    if key == "clock":  # the hour with the largest result across the books: what happened there
        return _hour_words(mx.lead_clock(ctx["clocks"]).largest.hour)
    if key == "down":
        return formatting.count(ctx["two_losses"].population)
    if key == "busiest":
        return f"{ctx['days'].busiest_vs_normal}×"
    if key == "unread":
        return f"{formatting.count(imp.rows_parsed)} of {formatting.count(imp.rows_in)} rows"
    if key == "risk":
        return f"{formatting.count(ctx['risk'].showable)} of {formatting.count(len(ctx['trips']))}"
    return str(NOT_TOLD)


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
    return (f"First trade {formatting.rupees(block.first_net)}, then {block.later} more; "
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
        "line": Markup(G.day_line(block.running)),
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
        out[key] = {
            "key": key,
            "title": fact.title,
            "state": state,
            "figure": "—" if state else _figure(key, ctx, imp),
            "href": S.fact_href(key),
            "trade_count": behind,
            "see_all": S.see_all_href(key) if behind > S.INLINE_TRADES else None,
            "chart": None
            if state or kind not in CARD_H
            else _chart(kind, ctx, imp, CARD_W, CARD_H[kind], False),
            "mini": None if state else _chart(kind, ctx, imp, dial.MINI_W, dial.MINI_H, True),
        }
    out["worst-days"].update(
        first_day=formatting.day(series[0].trading_day) if series else "",
        last_day=formatting.day(series[-1].trading_day) if series else "",
    )
    out["busiest"].update(
        first=out["worst-days"]["first_day"],
        last=out["worst-days"]["last_day"],
        busiest_date=formatting.day(ctx["days"].busiest_day) if ctx["days"].busiest_day else "",
    )
    two_losses = ctx["two_losses"]
    out["down"]["post_loss_sentence"] = (
        mx.post_loss_sentence_may_show(trips)
        and two_losses.condition_mean is not None
        and two_losses.comparison_mean is not None
    )
    out["money"]["days"] = [formatting.day(t.trading_day) for t in ctx["best"] + ctx["worst"]]
    out["money"]["held"] = ctx["held_past_day"]
    options = mx.option_result(trips)
    out["not-told"].update(
        options=options,
        options_amount=abs(options.net) if options else None,  # the sentence says lost or made
        flagged=_flagged_days(ctx, out),
    )
    held = mx.holding_series(mx.same_day_trips(trips))
    out["hold"]["max_seconds"] = max([*held.winners_seconds, *held.losers_seconds, 0])
    out["hold"]["held"] = ctx["held_past_day"]
    out["run"]["day_count"] = len(ctx["run"].days)
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
    out["worst-days"].update(
        in_common=worst_days_in_common(ctx),
        blocks=[_day_block(b, ctx) for b in ctx["day_blocks"]],
        next_href=S.fact_href("money", lens=False),
        all_trades_href=S.see_all_href("worst-days"),
    )
    if not out["worst-days"]["state"]:
        out["worst-days"]["finding"] = (
            f"{len(ctx['worst_days'].days)} days: {formatting.rupees(ctx['worst_days'].sum)}"
        )
    if ctx["best"]:
        out["money"]["finding"] = f"Best trade {formatting.rupees(ctx['best'][0].net)}"
    out["money"]["pairs"] = [
        {
            "best": b,
            "worst": w,
            "best_day": formatting.day(b.trading_day),
            "worst_day": formatting.day(w.trading_day),
        }
        for b, w in zip(ctx["best"], ctx["worst"], strict=False)
    ]
    out["hold"].update(winner_count=len(held.winners_seconds), loser_count=len(held.losers_seconds))
    out["share"]["worst_day_count"] = len(ctx["worst_days"].days)
    out["strike"]["held"] = ctx["held_past_day"]
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
    return out


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
    next_chapter = S.chapter(S.chapter_of("clock")[0].number + 1)
    return {
        "clocks": wide,
        "other_clocks": views[len(wide):],
        "rate_minimum": mx.CLOCK_MINIMUM_TRADES,
        "lead_book": lead.book if lead else "",
        "lead": lead.largest if lead else None,
        "lead_label": _hour_words(lead.largest.hour) if lead else "",
        "next": {
            "label": f"Chapter {next_chapter.number}: {next_chapter.name}",
            "href": S.chapter_href(next_chapter.number),
        },
    }


def chapter_view(n: int, figs: dict[str, dict]) -> dict:
    """The chapter's dial, for the dial macro: its facts as slices, its name in the centre."""
    c = S.chapter(n)
    items = []
    for f in c.facts:
        fig = figs[f.key]
        item = {
            "name": f.title,
            "figure": fig.get("finding", fig["figure"]),
            "href": fig["href"],
            "state": fig["state"],
            "chart": "" if fig["state"] else f.chart,
        }
        if item["chart"]:
            if fig["mini"] is None:
                item["chart"] = ""  # a share that is not a percentage draws no bar
            else:
                item["mini"] = fig["mini"]
        items.append(item)
    return {
        "kind": "chapter",
        "items": items,
        "centre": {"name": c.name, "scopeHref": S.home_href(tap=n)},
    }


def home_view(ctx: dict, *, gross: bool = False, opened: frozenset[int] = frozenset()) -> dict:
    """Home's dial: the four chapters as ways in, the trader's result in the centre.

    A slice is too narrow for a finding, and a bare number on it says nothing, so each says
    whether it has been read; the findings sit in the list under the dial.
    """
    items = [
        {
            "name": c.name,
            "figure": "Read" if c.number in opened else "Open",
            "opened": c.number in opened,
            "href": S.chapter_href(c.number, from_home=True),
        }
        for c in S.CHAPTERS
    ]
    caption = ["your result,", "before charges"] if gross else ["your result for", "the whole period"]
    centre = {"figure": formatting.rupees(ctx["share"].total), "captionLines": caption}
    return {"kind": "home", "items": items, "centre": centre}


def _start(opened: frozenset[int]) -> dict | None:
    """Where the button goes: chapter 1 at first, then the first chapter still unread."""
    unread = [c.number for c in S.CHAPTERS if c.number not in opened]
    if not unread:
        return None
    label = f"Next: chapter {unread[0]}" if opened else f"Start with chapter {unread[0]}"
    return {"label": label, "href": S.chapter_href(unread[0], from_home=True)}


def home_context(ctx: dict, imp, opened: frozenset[int] = frozenset()) -> dict:
    """What Scope home shows: the verdict, the books, a finding per chapter, a way in."""
    figs = facts(ctx, imp)
    best = max(ctx["trips"], key=lambda t: t.net)
    states = {
        1: "not-enough" if len(ctx["worst_days"].days) < 5 else "",
        2: figs["hold"]["state"],
        3: figs["down"]["state"],
        4: "",
    }
    return {
        "view": home_view(ctx, gross=not imp.fees_available, opened=opened),
        "verdict": mx.verdict(ctx["trips"]),
        "chapters": [
            {
                "number": c.number,
                "name": c.name,
                "href": S.chapter_href(c.number, from_home=True),
                "opened": c.number in opened,
                "state": states[c.number],
            }
            for c in S.CHAPTERS
        ],
        "start": _start(opened),
        "best_was_held": best.net > 0 and not best.closed_same_day,
        "worst_days": ctx["worst_days"],
        "holding": ctx["holding"],
        "two_losses": ctx["two_losses"],
    }


REVEAL_C = 150  # the reveal's dial: 300 x 300, the outer ring at 149.5 (kit screen 12)
REVEAL_SLICE_CIRCUMFERENCE = "622.04"  # 2 pi x 99, the slice's radius, as the kit writes it


def reveal_view(ctx: dict) -> dict:
    """The reveal's dial (handoff 7): the five worst days as one white slice from twelve
    o'clock to their share, the share in the centre. Its bezel and ring are the
    Scope's own (scope_geometry), at the kit's 300 px; a test holds them to the kit.

    Shown only when the share is a percentage (Appendix A); otherwise no slice and no
    figure, and the Mirror's other sentence says the whole result.
    """
    rr = G.radii(REVEAL_C)
    share = ctx["share"]
    view = {
        "shown": share.shown_as_percentage,
        "outer": G.circle(REVEAL_C, REVEAL_C, rr["outer"]),
        "inner": G.circle(REVEAL_C, REVEAL_C, rr["inner"]),
        "ticks": G.ticks(REVEAL_C, REVEAL_C, rr, [0]),
        "circumference": REVEAL_SLICE_CIRCUMFERENCE,
    }
    if share.shown_as_percentage:
        fraction = _f(share.share_percent) / 100
        view["slice_length"] = G.fmt(float(REVEAL_SLICE_CIRCUMFERENCE) * fraction)
        view["edge_tick"] = G.radial(
            REVEAL_C, REVEAL_C, 360 * fraction, rr["majorStart"], rr["tickEnd"]
        )
    return view
