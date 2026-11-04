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
        "days": mx.day_counts(trips),
        "best": mx.best_five(same_day),
        "worst": mx.worst_five(same_day),
        "held_past_day": mx.held_past_day(trips),
        "two_losses": two_losses,
        "strike": mx.strike_rate(trips),
        "lots": mx.average_lots(trips),
        "holding": mx.holding_time(same_day),
        "hours": mx.result_by_hour(same_day),
        "run": mx.longest_losing_run(trips),
        "risk": mx.risk_figure_counts(trips),
        "past_number": mx.trades_past_number(trips),
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
    if kind == "clock":
        hours = ctx["hours"]
        few = [i for i, hr in enumerate(hours) if hr.small_sample]
        return G.chart_clock([_f(hr.net) for hr in hours], few, w, h)
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
    if key == "clock":
        return f"{formatting.count(len(ctx['hours']))} hours"
    if key == "down":
        return formatting.count(ctx["two_losses"].population)
    if key == "busiest":
        return f"{ctx['days'].busiest_vs_normal}×"
    if key == "unread":
        return f"{formatting.count(imp.rows_parsed)} of {formatting.count(imp.rows_in)} rows"
    if key == "risk":
        return f"{formatting.count(ctx['risk'].showable)} of {formatting.count(len(ctx['trips']))}"
    return str(NOT_TOLD)


def facts(ctx: dict, imp) -> dict[str, dict]:
    """Every fact's figure, state, card chart, mini chart and the counts its card needs."""
    trips = ctx["trips"]
    series = mx.daily_series(trips)
    out: dict[str, dict] = {}
    for key, fact in S.FACTS.items():
        state = _state(key, ctx)
        kind = fact.chart
        out[key] = {
            "key": key,
            "title": fact.title,
            "state": state,
            "figure": "—" if state else _figure(key, ctx, imp),
            "href": S.fact_href(key),
            "trade_count": len(S.trades_behind(key, ctx)),
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
    out["money"]["days"] = [formatting.day(t.trading_day) for t in ctx["best"] + ctx["worst"]]
    # Home's wedge is too narrow for "rows" at four-digit counts (TICKET-804), so home says
    # the full figure under the dial instead.
    out["unread"]["hub_figure"] = f"{formatting.count(imp.rows_parsed)} of {formatting.count(imp.rows_in)}"
    out["money"]["held"] = ctx["held_past_day"]
    held = mx.holding_series(mx.same_day_trips(trips))
    out["hold"]["max_seconds"] = max([*held.winners_seconds, *held.losers_seconds, 0])
    out["hold"]["held"] = ctx["held_past_day"]
    out["run"]["day_count"] = len(ctx["run"].days)
    for key, fact in S.FACTS.items():  # the fact page's figure: full width, 96 px
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
    c = ctx["risk"].counts
    out["risk"]["nothing"] = c[s.RiskUnitSourceV1.UNAVAILABLE] + c[s.RiskUnitSourceV1.INFERRED_ATR]
    out["risk"]["structure"] = c[s.RiskUnitSourceV1.STRUCTURE_MAX_LOSS]
    out["risk"]["uncapped"] = c[s.RiskUnitSourceV1.UNCAPPED]
    out["risk"]["uncapped_trades"] = sum(t.uncapped for t in trips)  # a budget does not cap it
    hours = ctx["hours"]
    out["clock"]["held"] = ctx["held_past_day"]
    out["clock"].update(
        first_hour=f"{hours[0].hour:02d}" if hours else "",
        last_hour=f"{hours[-1].hour:02d}" if hours else "",
    )
    return out


def chapter_view(n: int, figs: dict[str, dict]) -> dict:
    """The chapter's dial, for the dial macro: its facts as slices, its name in the centre."""
    c = S.chapter(n)
    items = []
    for f in c.facts:
        fig = figs[f.key]
        item = {
            "name": f.title,
            "figure": fig["figure"],
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


LEADS = {1: "share", 2: "hold", 3: "down", 4: "unread"}
"""The fact each chapter's Home slice leads with (the kit's design, 14 · Scope home):
the share, the two holds, the occasions after two losses, the rows read."""


def home_view(figs: dict[str, dict], ctx: dict) -> dict:
    """Home's dial: the four chapters in equal slices, the five days' share in the centre.

    When the share is not a percentage (Appendix A), the centre says the whole
    period's result instead, in the Mirror's words, and slice 1 leads with it too.
    """
    items = []
    for c in S.CHAPTERS:
        lead = figs[LEADS[c.number]]
        items.append(
            {
                "name": c.name,
                "figure": lead.get("hub_figure", lead["figure"]),
                "state": lead["state"],
                "href": S.chapter_href(c.number, from_home=True),
            }
        )
    share = ctx["share"]
    if share.shown_as_percentage:
        centre = {
            "figure": f"{share.share_percent}%",
            "captionLines": ["of your losses", "in five days"],
        }
    else:
        centre = {
            "figure": formatting.rupees(share.total),
            "captionLines": ["your result for", "the whole period"],
        }
    return {"kind": "home", "items": items, "centre": centre}


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
