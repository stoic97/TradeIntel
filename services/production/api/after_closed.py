"""After you closed: the 30 minutes after each exit, and the losing trades the market came back on.

Reads what the bar-figure job stored (``bar_trade_figure.after_exit``, ``took``; TICKET-1009) and
never a bar: the page draws stored numbers only.

* **"Came back past your entry."** A losing trade (his result below zero) came back when, within
  the 30 minutes after he closed, the underlying in the trade's direction passed the price he
  was measured from at entry: some after-exit value plus what he took is above zero. No
  threshold of ours.
* **Every hold length counts.** The bias on minute bars (TD-004) is in the best price reached
  *while held*; the minutes after the exit are read the same way for a short trade as a long one.
* **One underlying at a time,** the one with the most measured losing trades first: points of
  NIFTY and points of crude don't add up.
* **Thirty measured losing trades, or no line** (``mx.CLOCK_MINIMUM_TRADES``). The count of trades
  measured and not, with the stored reasons, is always said.
* **What happened, never what he would have made.** The page counts the trades and draws the
  median paths; it says nothing about when he should have closed.
"""

from __future__ import annotations

import json
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal

from markupsafe import Markup
from sqlalchemy import select

from services.production.api import formatting
from services.production.api import scope_map as S
from services.production.api.figures import Figure
from services.production.db import models as m
from services.production.mirror import metrics as mx

KEY = "after-close"
HORIZON = 30
SHOWN_MINUTES = (1, 5, 10, 15, 20, 30)
PAGE_W, PAGE_H = 350, 160
NOT_WORKED_OUT = "its figures aren't worked out yet"
"""A trade with no stored after-exit path: the job for its import hasn't run since this was built."""
STEPS = (Decimal(1), Decimal(2), Decimal("2.5"), Decimal(5))


# ---------- reading what the job stored ----------

def _decimals(raw: str | None) -> tuple[Decimal | None, ...]:
    if not raw:
        return ()
    return tuple(None if v is None else Decimal(v) for v in json.loads(raw))


def load(sess, imp) -> dict:
    """Each trade's stored after-exit path and what he took, as plain values."""
    if imp is None:
        return {}
    rows = sess.scalars(select(m.BarTradeFigure).where(m.BarTradeFigure.import_id == imp.id))
    return {r.trip_id: {"underlying": r.underlying, "reason": r.reason,
                        "took": Decimal(r.took) if r.took is not None else None,
                        "after_exit": _decimals(r.after_exit)} for r in rows}


# ---------- the numbers ----------

def came_back_at(after_exit: tuple, took: Decimal) -> int | None:
    """The first minute after the exit at which the market stood past his entry, or None."""
    for k, v in enumerate(after_exit[: HORIZON + 1]):
        if k and v is not None and v + took > 0:
            return k
    return None


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    v = sorted(values)
    mid = len(v) // 2
    return v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2


def _median_path(paths: list[tuple]) -> tuple[Decimal | None, ...]:
    return tuple(_median([p[k] for p in paths if len(p) > k and p[k] is not None])
                 for k in range(HORIZON + 1))


def whole(v: Decimal | None) -> int | None:
    return None if v is None else int(v.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def view(ctx: dict, pick: str | None = None) -> dict:
    """The fact's figures for the trades in ``ctx`` (the report filter's), one underlying."""
    stored = ctx.get("bars_after_close") or {}
    losers: dict[str, list] = {}
    winners: dict[str, list] = {}
    reasons: Counter = Counter()
    for t in ctx["trips"]:
        row = stored.get(t.trip_id)
        if row is None or (not row["reason"] and (not row["after_exit"] or row["took"] is None)):
            reasons[NOT_WORKED_OUT] += 1
        elif row["reason"]:
            reasons[row["reason"]] += 1
        elif t.net < 0:
            losers.setdefault(row["underlying"], []).append((t, row))
        elif t.net > 0:
            winners.setdefault(row["underlying"], []).append((t, row))
    order = sorted(losers, key=lambda u: (-len(losers[u]), u))
    chosen = pick if pick in losers else (order[0] if order else None)
    mine = losers.get(chosen, [])
    back = [(t, came_back_at(row["after_exit"], row["took"])) for t, row in mine]
    back = [(t, k) for t, k in back if k is not None]
    out = {
        "underlying": chosen,
        "losers": len(mine),
        "came_back": len(back),
        "came_back_ids": [t.trip_id for t, _k in back],
        "came_back_minute": {t.trip_id: k for t, k in back},
        "measured": sum(len(v) for v in losers.values()) + sum(len(v) for v in winners.values()),
        "not_measured": sum(reasons.values()),
        "reasons": sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0])),
        "minimum": mx.CLOCK_MINIMUM_TRADES,
        "enough": len(mine) >= mx.CLOCK_MINIMUM_TRADES,
        "chips": [{"underlying": u, "trades": len(losers[u]), "on": u == chosen,
                   "href": f"{S.fact_href(KEY, lens=False)}?u={u}#after-close"}
                  for u in order] if len(order) > 1 else [],
        "losers_median": _median_path([row["after_exit"] for _t, row in mine]),
        "winners_median": _median_path([row["after_exit"] for _t, row in winners.get(chosen, [])]),
        "winners": len(winners.get(chosen, [])),
    }
    out["rows"] = [{"minute": k, "losers": whole(_at(out["losers_median"], k)),
                    "winners": whole(_at(out["winners_median"], k))} for k in SHOWN_MINUTES]
    return out


def _at(series: tuple, k: int) -> Decimal | None:
    return series[k] if len(series) > k else None


def figure(v: dict) -> Figure:
    """The fact's lead: how many of his measured losing trades came back past the entry."""
    return Figure(f"{formatting.count(v['came_back'])} of {formatting.count(v['losers'])} trades", "trades")


# ---------- the chart ----------

def _fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _step(span: Decimal) -> Decimal:
    """A round gridline step that puts about four lines across the span."""
    raw = span / 4 if span > 0 else Decimal(1)
    power = Decimal(1)
    while power * 10 <= raw:
        power *= 10
    while power > raw:
        power /= 10
    return next((s * power for s in STEPS if s * power >= raw), 10 * power)


def geometry(v: dict, w: float = PAGE_W, h: float = PAGE_H, *, mini: bool = False) -> dict | None:
    """The two median paths as the kit's chart macro draws them. None without enough trades."""
    if not v.get("enough"):
        return None
    left, right, top, bottom = (0, 0, 2, 2) if mini else (6, 40, 8, 20)
    seen = [x for s in (v["losers_median"], v["winners_median"]) for x in s if x is not None] + [Decimal(0)]
    lo, hi = min(seen), max(seen)
    step = _step(hi - lo)
    lo = (lo / step).to_integral_value(rounding="ROUND_FLOOR") * step
    hi = (hi / step).to_integral_value(rounding="ROUND_CEILING") * step
    if lo == hi:
        hi = lo + step
    span_x = w - left - right

    def x(k: int) -> float:
        return left + k * span_x / HORIZON

    def y(val: Decimal) -> float:
        return top + float((hi - val) / (hi - lo)) * (h - top - bottom)

    def line(s: tuple) -> str:
        pts = [(k, val) for k, val in enumerate(s[: HORIZON + 1]) if val is not None]
        return "".join(("M" if i == 0 else "L") + f"{_fmt(x(k))} {_fmt(y(val))}" for i, (k, val) in enumerate(pts))

    parts = []
    if not mini:
        grid, val = [], lo
        while val <= hi:
            grid.append(f"M{_fmt(left)} {_fmt(y(val))}H{_fmt(w - right)}")
            val += step
        parts.append({"role": "acl-grid", "d": "".join(grid)})
    parts.append({"role": "acl-zero", "d": f"M{_fmt(left)} {_fmt(y(Decimal(0)))}H{_fmt(w - right)}"})
    parts.append({"role": "acl-winners", "d": line(v["winners_median"])})
    parts.append({"role": "acl-losers", "d": line(v["losers_median"])})
    labels = Markup("")
    if not mini:
        texts, val = [], lo
        while val <= hi:
            said = f"{formatting.MINUS if val < 0 else ('+' if val > 0 else '')}{abs(val).normalize():f}"
            texts.append(f'<text x="{_fmt(w - right + 6)}" y="{_fmt(y(val) + 4)}" class="acl-axis">{said}</text>')
            val += step
        labels = Markup("".join(texts))
    return {"w": w, "h": h, "parts": [p for p in parts if p["d"]], "labels": labels}

