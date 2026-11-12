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
from decimal import ROUND_HALF_UP, Decimal

from markupsafe import Markup

from services.production.api import dial, formatting
from services.production.api import scope_geometry as G
from services.production.api import scope_map as S
from services.production.api.figures import Figure
from services.production.mirror import metrics as mx
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
        "math": "holding",  # both a winner and a loser, or there is nothing to balance
        "run": "run",
        "down": "two_losses",
        "busiest": "days",
    }.get(key)
    if metric and ctx[metric].state is not COUNTED:
        return "not-enough"
    return ""


def _figure(key: str, ctx: dict, imp) -> Figure:
    """The figure a fact leads with, as its slice and its card show it, and what it counts."""
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
        return Figure(f"{ctx['strike'].rate_percent}%", "percent")
    if key == "run":
        return Figure(f"{formatting.count(ctx['run'].length)} trades", "trades")
    if key == "clock":  # the hour with the largest result across the books: what happened there
        return Figure(_hour_words(mx.lead_clock(ctx["clocks"]).largest.hour), "hour")
    if key == "down":
        return Figure(formatting.count(ctx["two_losses"].population), "trades")
    if key == "busiest":
        return Figure(f"{ctx['days'].busiest_vs_normal}×", "times your normal day")
    if key == "unread":
        return Figure(f"{formatting.count(imp.rows_parsed)} of {formatting.count(imp.rows_in)} rows", "rows")
    if key == "risk":
        return Figure(f"{formatting.count(ctx['risk'].showable)} of {formatting.count(len(ctx['trips']))}",
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


def _next_fact(key: str) -> dict:
    return {"label": f"Next: {S.FACTS[key].title}", "href": S.fact_href(key)}


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


def chapter_next(n: int) -> dict | None:
    """The button that ends a chapter's overview, where it has one."""
    labels = {1: "Chapter 2: your patterns", 2: "Chapter 3, your behaviour: what you did after losing"}
    return {"label": labels[n], "href": S.chapter_href(n + 1)} if n in labels else None


def _chapter_four(ctx: dict) -> dict:
    """The way out of chapter 3, by chapter 4's own title. The number is mentioned only while
    chapter 4 still offers to take it (its risk fact, with no declared budget)."""
    c = S.chapter(4)
    return {
        "label": f"Chapter {c.number}: {c.name}",
        "href": S.chapter_href(c.number),
        "names_the_number": ctx["risk"].counts[s.RiskUnitSourceV1.DECLARED_BUDGET] == 0,
    }


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
        lead = Figure("—", "no figure yet") if state else _figure(key, ctx, imp)
        out[key] = {
            "key": key,
            "title": fact.title,
            "state": state,
            "figure": str(lead),
            "noun": lead.noun,
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
    counted_days = sorted({t.trading_day for t in mx.same_day_trips(trips)})
    out["busiest"].update(
        first=formatting.day(counted_days[0]) if counted_days else "",
        last=formatting.day(counted_days[-1]) if counted_days else "",
        busiest_date=formatting.day(ctx["days"].busiest_day) if ctx["days"].busiest_day else "",
    )
    out["busiest"]["story"] = _busiest_story(ctx)
    out["busiest"]["chapter_four"] = out["down"]["chapter_four"] = _chapter_four(ctx)
    out["down"]["next"] = _next_fact("busiest")
    out["math"]["next"] = _next_fact("run")
    out["run"]["next"] = _next_fact("clock")
    out["math"]["lead_lines"] = _break_even_lines(ctx)
    two_losses = ctx["two_losses"]
    out["down"]["post_loss_sentence"] = (
        mx.post_loss_sentence_may_show(mx.same_day_trips(trips))
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
    out["worst-days"].update(
        in_common=worst_days_in_common(ctx),
        blocks=[_day_block(b, ctx) for b in ctx["day_blocks"]],
        next_href=S.fact_href("money", lens=False),
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
    money_chapter, _ = S.chapter_of("money")
    next_chapter = S.chapter(money_chapter.number + 1)
    out["money"].update(
        found=ctx["money_found"],
        best_rows=S.ranked(ctx["best"], ctx),
        worst_rows=S.ranked(ctx["worst"], ctx),
        held_groups=[]
        if out["money"]["see_all"]
        else S.groups("money", ctx, only=ctx["held_past_day"].trips),
        next={
            "number": next_chapter.number,
            "name": next_chapter.name,
            "href": S.chapter_href(next_chapter.number),
        },
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


def _chapter_wedge(key: str, ctx: dict, fig: dict) -> dict:
    """Each fact's wedge on its chapter's dial (TICKET-880). Same figures its page shows."""
    if key == "worst-days":
        return _wedge(Figure(len(ctx["worst_days"].days), "days",
                             of=f"came to {formatting.rupees(ctx['worst_days'].sum)}"))
    if key == "money" and ctx["best"]:
        return _wedge(Figure(formatting.rupees(ctx["best"][0].net), "rupees", of="your best trade"),
                      shown=formatting.rupees(ctx["best"][0].net))
    if key == "math":
        return _wedge(Figure(ctx["strike"].rate_percent, "trades", of="trades made money"),
                      shown=_out_of_a_hundred(ctx["strike"].rate_percent))
    if key == "run":
        n = ctx["run"].length
        return _wedge(Figure(formatting.count(n), "loss" if n == 1 else "losses", of="in a row"),
                      phone_shown=f"{formatting.count(n)} lost")
    if key == "clock":
        return _wedge(Figure(str(fig["figure"]), "hour", of="the hour of your largest result"),
                      phone="largest\nhour", shown=str(fig["figure"]))
    if key == "down":
        return _wedge(_of(_trades(ctx["two_losses"].condition), "right after two losses"))
    if key == "busiest":
        on_day = fig["busiest_date"].replace(" ", chr(0xA0))  # a date holds together
        return _wedge(_of(_trades(ctx["days"].busiest_trips), f"on your busiest day, {on_day}"),
                      phone=f"busiest day,\n{on_day}")
    if key == "unread":
        read, _, whole = fig["figure"].removesuffix(" rows").partition(" of ")
        return _wedge(Figure(read, "rows", of=f"of {whole} rows read"), shown=read)
    if key == "risk":
        measured, _, whole = fig["figure"].partition(" of ")
        return _wedge(Figure(measured, "trades", of=f"of {whole} trades have a risk figure"),
                      phone=f"of {whole}\ntrades", shown=measured)
    if key == "not-told":
        return _wedge(Figure(NOT_TOLD, "things", of="we have not told you"), phone="not told",
                      phone_shown=f"{NOT_TOLD} items")
    return _wedge(Figure(fig["figure"], fig["noun"], of="on same-day trades"), shown=fig["figure"])


def chapter_view(n: int, figs: dict[str, dict]) -> dict:
    """The chapter's dial, for the dial macro: its facts as slices, its name in the centre."""
    c = S.chapter(n)
    items = []
    for f in c.facts:
        fig = figs[f.key]
        item = {
            "name": f.title,
            **fig["wedge"],
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
    item = {"figure": shown or figure.with_noun, "label": _lines(figure.of or ""), "state": ""}
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


def _out_of_a_hundred(rate) -> str:
    """A rate as a count: "46 of 100". Rounded as a person says it, half up."""
    whole = Decimal(str(rate)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return f"{whole} of 100"


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
                            phone="made money", shown=_out_of_a_hundred(strike.rate_percent))}


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
) -> dict:
    """Home's dial: each chapter's answer in its wedge, the trader's result in the centre. Read
    is the dot on the rim, and no words in the wedge."""
    answers = answers or hub_answers(ctx, facts(ctx, imp), number)
    items = [
        {
            "name": c.name,
            **answers[c.number]["wedge"],
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


def home_context(
    ctx: dict, imp, opened: frozenset[int] = frozenset(), number: Decimal | None = None
) -> dict:
    """What Scope home shows: the verdict, the books, each chapter's answer, a way in."""
    figs = facts(ctx, imp)
    answers = hub_answers(ctx, figs, number)
    return {
        "view": home_view(ctx, imp, gross=not imp.fees_available, opened=opened, answers=answers),
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
        "start": _start(opened),
        "two_losses": ctx["two_losses"],
        "post_loss": figs["down"],
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
