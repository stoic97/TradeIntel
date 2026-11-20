"""After you clicked: the 30 minutes after each entry, beside random moments (TICKET-1001).

Reads what the bar-figure job stored (999: ``bar_trade_figure`` per trade, ``bar_path_summary``
per underlying) and never a bar: the page draws stored numbers only.

* **His paths follow the report filter.** Each trade's stored path is his; the median and middle
  half are worked out here from the trades the filter keeps.
* **The random band does not.** It is the one stored for the whole record's months, and the
  page says so.
* **One underlying at a time.** Twenty points of NIFTY is not twenty points of crude; with more
  than one, chips pick it, the one with the most measured trades first.
* **Thirty measured trades, or no chart** (``mx.CLOCK_MINIMUM_TRADES``). The count of trades
  measured and not, with the stored reasons, is always said.
* **A counted fact.** It says where the two medians end at minute 30, and nothing about chance:
  a claim that his entries beat or trail random moments is a finding, and needs its own test.

The chart is kit-shaped (``{w, h, parts}`` drawn by the ``chart`` macro), not one of the kit's
own charts, so it is not in ``scope_geometry.CHARTS``. Its gridlines are ``charts.ticks`` steps,
its minute labels ``charts.time_labels``, and its figures as text ``charts.text_table``.
"""

from __future__ import annotations

import json
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal

from markupsafe import Markup
from sqlalchemy import select

from services.production.api import charts, formatting
from services.production.api import scope_map as S
from services.production.api.figures import Figure
from services.production.db import models as m
from services.production.mirror import metrics as mx

HORIZON = 30
FAINT = 200
SHOWN_MINUTES = (1, 5, 10, 15, 20, 30)
PAGE_W, PAGE_H = 350, 180
PLOT_LEFT, PLOT_RIGHT, PLOT_TOP, PLOT_BOTTOM = 6, 44, 8, 22
NOT_WORKED_OUT = "its figures aren't worked out yet"
"""A trade with no stored row: the job for its import hasn't run since it was read."""


# ---------- reading what 999 stored ----------

def _decimals(raw: str | None) -> tuple[Decimal | None, ...]:
    if not raw:
        return ()
    return tuple(None if v is None else Decimal(v) for v in json.loads(raw))


def load(sess, imp) -> dict:
    """Everything stored for this import's bar figures, as plain values."""
    if imp is None:
        return {}
    trades = {
        r.trip_id: {"underlying": r.underlying, "reason": r.reason, "path": _decimals(r.path),
                    "short": r.short}
        for r in sess.scalars(select(m.BarTradeFigure).where(m.BarTradeFigure.import_id == imp.id))
    }
    random = {
        s.underlying: {"median": _decimals(s.random_median), "lo": _decimals(s.random_lo),
                       "hi": _decimals(s.random_hi), "count": s.randoms}
        for s in sess.scalars(select(m.BarPathSummary).where(m.BarPathSummary.import_id == imp.id))
    }
    job = sess.scalars(select(m.BarFigureJob).where(m.BarFigureJob.import_id == imp.id)).first()
    return {"trades": trades, "random": random, "job": job.state if job else None,
            "waiting_days": job.waiting_days if job else 0}


def measured_trip_ids(ctx: dict) -> set[str]:
    """The trades the fact draws: measured, of whatever underlying, among those the filter keeps."""
    stored = (ctx.get("bars") or {}).get("trades", {})
    return {t.trip_id for t in ctx["trips"]
            if (r := stored.get(t.trip_id)) is not None and r["reason"] is None and r["path"]}


# ---------- the numbers ----------

def _quantile(values: list[Decimal], q: Decimal) -> Decimal | None:
    if not values:
        return None
    v = sorted(values)
    pos = (len(v) - 1) * q
    low = int(pos)
    high = min(low + 1, len(v) - 1)
    return v[low] + (v[high] - v[low]) * (pos - low)


def _at(paths: list[tuple], q: Decimal) -> tuple[Decimal | None, ...]:
    return tuple(_quantile([p[k] for p in paths if len(p) > k and p[k] is not None], q)
                 for k in range(HORIZON + 1))


def _evenly(items: list, k: int) -> list:
    n = len(items)
    if n <= k:
        return list(items)
    return [items[i] for i in sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})]


def _end(series: tuple) -> Decimal | None:
    """Where a line ends at minute 30, or the last minute it reached."""
    for v in reversed(series[: HORIZON + 1]):
        if v is not None:
            return v
    return None


def whole(v: Decimal | None) -> int | None:
    """Points as a page says them: whole points, halves away from zero."""
    return None if v is None else int(v.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def view(ctx: dict, pick: str | None = None) -> dict:
    """The fact's figures for the trades in ``ctx`` (the report filter's), one underlying."""
    bars = ctx.get("bars") or {}
    stored = bars.get("trades", {})
    paths: dict[str, list[tuple]] = {}
    reasons: Counter = Counter()
    for t in ctx["trips"]:
        row = stored.get(t.trip_id)
        if row is None:
            reasons[NOT_WORKED_OUT] += 1
        elif row["reason"] or not row["path"]:
            reasons[row["reason"] or NOT_WORKED_OUT] += 1
        else:
            paths.setdefault(row["underlying"], []).append(row["path"])
    order = sorted(paths, key=lambda u: (-len(paths[u]), u))
    chosen = pick if pick in paths else (order[0] if order else None)
    his = paths.get(chosen, [])
    band = bars.get("random", {}).get(chosen, {})
    out = {
        "underlying": chosen,
        "measured": sum(len(p) for p in paths.values()),
        "measured_here": len(his),
        "not_measured": sum(reasons.values()),
        "reasons": sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0])),
        "minimum": mx.CLOCK_MINIMUM_TRADES,
        "enough": len(his) >= mx.CLOCK_MINIMUM_TRADES,
        "chips": [{"underlying": u, "trades": len(paths[u]), "on": u == chosen,
                   "href": f"{S.fact_href('after', lens=False)}?u={u}#after"}
                  for u in order] if len(order) > 1 else [],
        "his_median": _at(his, Decimal("0.5")), "his_q25": _at(his, Decimal("0.25")),
        "his_q75": _at(his, Decimal("0.75")),
        "random_median": band.get("median", ()), "random_lo": band.get("lo", ()),
        "random_hi": band.get("hi", ()),
        "faint": _evenly(his, FAINT),
    }
    out["his_end"] = whole(_end(out["his_median"]))
    out["random_end"] = whole(_end(out["random_median"])) or 0
    out.update(said(out["his_end"], "his"), **said(out["random_end"], "random"))
    return out


def said(n: int | None, who: str) -> dict:
    """How a sentence says where a line ends: whole points, without a sign, and which way."""
    if n is None:
        return {f"{who}_points": None, f"{who}_way": "", f"{who}_unit": "points"}
    return {f"{who}_points": abs(n), f"{who}_way": "your way" if n > 0 else "against you" if n < 0 else "",
            f"{who}_unit": "point" if abs(n) == 1 else "points"}


# ---------- the chart ----------

def _fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def geometry(v: dict, w: float = PAGE_W, h: float = PAGE_H, *, mini: bool = False) -> dict | None:
    """The chart as the kit's chart macro draws it: parts, each a path with a role. None when
    there aren't enough measured trades to draw."""
    if not v.get("enough"):
        return None
    left, right = (0, 0) if mini else (PLOT_LEFT, PLOT_RIGHT)
    top, bottom = (2, 2) if mini else (PLOT_TOP, PLOT_BOTTOM)
    series = [v["his_median"], v["his_q25"], v["his_q75"], v["random_lo"], v["random_hi"], v["random_median"]]
    seen = [x for s in series for x in s if x is not None]
    seen += [x for p in ([] if mini else v["faint"]) for x in p if x is not None]
    lo, hi, tick = charts.ticks(min(seen + [Decimal(0)]), max(seen + [Decimal(0)]))
    if lo == hi:
        hi = lo + tick
    span_x = w - left - right
    step = span_x / HORIZON

    def x(k: int) -> float:
        return left + k * step

    def y(val: Decimal) -> float:
        return top + float((hi - val) / (hi - lo)) * (h - top - bottom)

    def line(s: tuple) -> str:
        pts = [(k, val) for k, val in enumerate(s[: HORIZON + 1]) if val is not None]
        return "".join(("M" if i == 0 else "L") + f"{_fmt(x(k))} {_fmt(y(val))}" for i, (k, val) in enumerate(pts))

    def area(low: tuple, high: tuple) -> str:
        pts = [(k, a, b) for k, (a, b) in enumerate(zip(low[: HORIZON + 1], high[: HORIZON + 1], strict=False))
               if a is not None and b is not None]
        if not pts:
            return ""
        top_edge = "".join(("M" if i == 0 else "L") + f"{_fmt(x(k))} {_fmt(y(b))}" for i, (k, _a, b) in enumerate(pts))
        return top_edge + "".join(f"L{_fmt(x(k))} {_fmt(y(a))}" for k, a, _b in reversed(pts)) + "Z"

    def faint(paths: list[tuple]) -> str:
        """Every faint path in one d attribute, in whole pixels and relative steps: 200 paths stay
        a few tens of kilobytes."""
        out = []
        for p in paths:
            pts = [(k, val) for k, val in enumerate(p[: HORIZON + 1]) if val is not None]
            if len(pts) < 2:
                continue
            px = [(round(x(k)), round(y(val))) for k, val in pts]
            seg = [f"M{px[0][0]} {px[0][1]}"]
            seg += [f"l{a[0] - b[0]} {a[1] - b[1]}" for a, b in zip(px[1:], px[:-1], strict=True)]
            out.append("".join(seg))
        return "".join(out)

    parts = []
    if not mini:
        grid = []
        val = lo
        while val <= hi:
            grid.append(f"M{_fmt(left)} {_fmt(y(val))}H{_fmt(w - right)}")
            val += tick
        parts.append({"role": "ac-grid", "d": "".join(grid)})
    parts.append({"role": "ac-band", "d": area(v["random_lo"], v["random_hi"])})
    if not mini:
        parts.append({"role": "ac-faint", "d": faint(v["faint"])})
    parts.append({"role": "ac-mid", "d": area(v["his_q25"], v["his_q75"])})
    parts.append({"role": "ac-zero", "d": f"M{_fmt(left)} {_fmt(y(Decimal(0)))}H{_fmt(w - right)}"})
    parts.append({"role": "ac-random", "d": line(v["random_median"])})
    parts.append({"role": "ac-his", "d": line(v["his_median"])})
    labels = Markup("")
    if not mini:
        texts = [lbl.svg for lbl in charts.time_labels(
            [(x(k), k) for k in range(0, HORIZON + 1, 5)], kind="offset", y=h - 6, p="ac")]
        val = lo
        while val <= hi:
            said = f"{formatting.MINUS if val < 0 else ('+' if val > 0 else '')}{abs(val).normalize():f}"
            texts.append(Markup(f'<text x="{_fmt(w - right + 6)}" y="{_fmt(y(val) + 4)}" class="ac-axis">{said}</text>'))
            val += tick
        labels = Markup("".join(texts))
    return {"w": w, "h": h, "parts": [p for p in parts if p["d"]], "labels": labels}


def table(v: dict) -> Markup:
    """The chart's figures as a plain table, at minutes 1, 5, 10, 15, 20 and 30."""

    def pts(series: tuple, k: int):
        val = whole(series[k]) if len(series) > k else None
        return Figure(val, "points") if val is not None else "—"

    rows = [(f"{k} min", pts(v["his_median"], k), pts(v["his_q25"], k), pts(v["his_q75"], k),
             pts(v["random_lo"], k), pts(v["random_hi"], k)) for k in SHOWN_MINUTES]
    return charts.text_table(rows, ("After", "Your median", "Your 25%", "Your 75%",
                                    "Random 2.5%", "Random 97.5%"),
                             caption="Points the market moved your way after you clicked", p="ac")
