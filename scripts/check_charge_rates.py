"""TICKET-911: has the statutory rate table gone stale? A job, separate from the product.

    uv run python scripts/check_charge_rates.py [--webhook URL]

It prices a fixed set of made-up orders twice for today: once with the table
(services/production/charges/rates.yaml), and once with the rates two brokers publish
(FYERS's charges list and Zerodha's charges page). If any component differs by more than a
paisa, or a page can't be read, it prints what moved, posts it to the webhook if one is given
(or set in SCOPE_ALERT_WEBHOOK), and exits 1. A person then reads the circular and adds a
row. **The job never edits the table**: an automatic update would silently rewrite history.

Made-up orders only. No trader's trade is ever read here.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.production.charges import rates as R

S, C = R.Segment, R.Component
FYERS = "https://fyers.in/charges-list.md"
ZERODHA = "https://zerodha.com/charges"
CRORE = Decimal(10_000_000)
TOLERANCE = Decimal("0.01")  # a paisa

ORDERS: tuple[tuple[R.Segment, str, Decimal], ...] = tuple(
    (seg, side, value)
    for seg, value in ((S.NSE_EQ_DELIVERY, Decimal(100_000)), (S.NSE_EQ_INTRADAY, Decimal(100_000)),
                       (S.NSE_FUT, Decimal(1_000_000)), (S.NSE_OPT, Decimal(10_000)),
                       (S.BSE_OPT, Decimal(10_000)), (S.MCX_FUT, Decimal(500_000)),
                       (S.MCX_OPT, Decimal(10_000)))
    for side in ("buy", "sell")
)
"""Round made-up orders: a value of turnover, or premium for options."""


def _pct(text: str) -> Decimal:
    return Decimal(text) / 100


def _per_crore(text: str) -> Decimal:
    return Decimal(text) / CRORE


def _first(pattern: str, text: str, what: str) -> str:
    m = re.search(pattern, text)
    if not m:
        raise ValueError(f"couldn't find {what}")
    return m.group(1)


def _rows(text: str, heading: str) -> dict[str, list[str]]:
    """A markdown table under ``### heading``: first cell -> the other cells. A row with an
    empty first cell continues the row above (FYERS puts BSE under NSE that way)."""
    part = text.split(f"### {heading}", 1)[1].split("\n## ", 1)[0].split("\n### ", 1)[0]
    out: dict[str, list[str]] = {}
    last = None
    for line in part.splitlines():
        if not line.startswith("|") or line.startswith("| ---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0]:
            last = cells[0]
            out[last] = cells[1:]
        elif last:
            out[last] = [f"{a} {b}".strip() for a, b in zip(out[last], cells[1:], strict=False)]
    return out


def fyers_rates(text: str) -> dict[tuple[R.Segment, R.Component, str], Decimal]:
    """The statutory rates on FYERS's charges list, keyed like the table."""
    eq, com = _rows(text, "Equity"), _rows(text, "Commodity")
    stt, exch, stamp = eq["STT/CTT"], eq["Exchange Transaction Charges"], eq["Stamp Duty"]
    out = {}
    for seg, i in ((S.NSE_EQ_DELIVERY, 0), (S.NSE_EQ_INTRADAY, 1), (S.NSE_FUT, 2), (S.NSE_OPT, 3)):
        sides = ("buy", "sell") if seg is S.NSE_EQ_DELIVERY else ("sell",)
        for side in sides:
            out[(seg, C.STT, side)] = _pct(_first(r"([\d.]+)%", stt[i], f"STT for {seg}"))
        nse = _pct(_first(r"NSE:\s*([\d.]+)%", exch[i], f"NSE charge for {seg}"))
        out.update({(seg, C.EXCHANGE, s): nse for s in R.SIDES})
        out[(seg, C.STAMP, "buy")] = _pct(_first(r"([\d.]+)%", stamp[i], f"stamp duty for {seg}"))
        out.update({(seg, C.SEBI, s): _per_crore(_first(r"₹\s*([\d.]+)\s*/\s*Crore", eq["SEBI Turnover Fee"][i], "SEBI fee"))
                    for s in R.SIDES})
        out.update({(seg, C.IPFT, s): _per_crore(_first(r"₹\s*([\d.]+)\s*/\s*Crore", eq["NSE IPFT"][i], "IPFT"))
                    for s in R.SIDES})
    bse = _pct(_first(r"Sensex:\s*([\d.]+)%", exch[3], "BSE SENSEX option charge"))
    out.update({(S.BSE_OPT, C.EXCHANGE, s): bse for s in R.SIDES})
    out.update({(S.BSE_OPT, C.SEBI, s): out[(S.NSE_OPT, C.SEBI, s)] for s in R.SIDES})
    out[(S.BSE_OPT, C.STT, "sell")] = out[(S.NSE_OPT, C.STT, "sell")]
    out[(S.BSE_OPT, C.STAMP, "buy")] = out[(S.NSE_OPT, C.STAMP, "buy")]
    for seg, i in ((S.MCX_FUT, 0), (S.MCX_OPT, 1)):
        out[(seg, C.CTT, "sell")] = _pct(_first(r"([\d.]+)%", com["STT/CTT"][i], f"CTT for {seg}"))
        mcx = _pct(_first(r"MCX-\s*Non-Agri:\s*([\d.]+)%", com["Exchange Transaction Charges"][i], f"MCX charge {seg}"))
        out.update({(seg, C.EXCHANGE, s): mcx for s in R.SIDES})
        out[(seg, C.STAMP, "buy")] = _pct(_first(r"([\d.]+)%", com["Stamp Duty"][i], f"stamp duty for {seg}"))
        out.update({(seg, C.SEBI, s): _per_crore(_first(r"₹\s*([\d.]+)\s*/\s*Crore", com["SEBI Turnover Fee"][i], "SEBI fee"))
                    for s in R.SIDES})
    gst = _pct(_first(r"([\d.]+)%\s*on", eq["GST"][0], "GST"))
    out.update({(seg, C.GST, s): gst for seg in R.REQUIRED for s in R.SIDES})
    return out


def _cells(page: str) -> list[str]:
    body = re.sub(r"<!--.*?-->", "", page, flags=re.DOTALL)  # an old layout is left commented out
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", body, flags=re.DOTALL)
    text = html.unescape(re.sub(r"<[^>]+>", "|", body))
    return [c.strip() for c in re.split(r"\s*\|\s*", text) if c.strip()]


EQUITY_HEAD = "Equity delivery|Equity intraday|F&O - Futures|F&O - Options|Brokerage"
STAMP = r"([\d.]+)% or ₹[\d,]+ / crore on buy side"


def zerodha_rates(page: str) -> dict[tuple[R.Segment, R.Component, str], Decimal]:
    """The statutory rates on Zerodha's charges page, keyed like the table. Equity and F&O are
    one table in the page's column order: delivery, intraday, futures, options. Then commodity."""
    joined = "|".join(_cells(page))
    eq = joined.split(EQUITY_HEAD, 1)[1].split("Commodity options", 1)[0]
    com = joined.split("Commodity options", 1)[1]
    cols = (S.NSE_EQ_DELIVERY, S.NSE_EQ_INTRADAY, S.NSE_FUT, S.NSE_OPT)
    out = {}
    stt = re.findall(r"([\d.]+)% (?:on buy & sell|on the sell side|on sell side \(on premium\))",
                     eq.split("STT/CTT", 1)[1].split("Transaction charges", 1)[0])
    nse = re.findall(r"NSE: ([\d.]+)%", eq.split("Transaction charges", 1)[1].split("GST", 1)[0])
    stamp = re.findall(STAMP, eq.split("Stamp charges", 1)[1])
    if len(stt) < 4 or len(nse) < 4 or len(stamp) < 4:
        raise ValueError("the equity table doesn't have its four columns")
    for i, seg in enumerate(cols):
        sides = ("buy", "sell") if seg is S.NSE_EQ_DELIVERY else ("sell",)
        out.update({(seg, C.STT, side): _pct(stt[i]) for side in sides})
        out.update({(seg, C.EXCHANGE, side): _pct(nse[i]) for side in R.SIDES})
        out[(seg, C.STAMP, "buy")] = _pct(stamp[i])
    out[(S.BSE_OPT, C.STT, "sell")] = out[(S.NSE_OPT, C.STT, "sell")]
    out[(S.BSE_OPT, C.STAMP, "buy")] = out[(S.NSE_OPT, C.STAMP, "buy")]
    out.update({(S.BSE_OPT, C.EXCHANGE, s): _pct(_first(r"BSE: ([\d.]+)% \(on premium\)", eq, "BSE options"))
                for s in R.SIDES})
    ctt = re.findall(r"([\d.]+)% on sell side", com.split("Transaction charges", 1)[0])
    out[(S.MCX_FUT, C.CTT, "sell")], out[(S.MCX_OPT, C.CTT, "sell")] = _pct(ctt[0]), _pct(ctt[1])
    mcx = re.findall(r"MCX: ([\d.]+)%", com)
    out.update({(S.MCX_FUT, C.EXCHANGE, s): _pct(mcx[0]) for s in R.SIDES})
    out.update({(S.MCX_OPT, C.EXCHANGE, s): _pct(mcx[1]) for s in R.SIDES})
    stamp_com = re.findall(STAMP, com)
    out[(S.MCX_FUT, C.STAMP, "buy")], out[(S.MCX_OPT, C.STAMP, "buy")] = _pct(stamp_com[0]), _pct(stamp_com[1])
    sebi = _per_crore(_first(r"SEBI charges\|₹(\d+) / crore", joined, "SEBI fee"))
    gst = _pct(_first(r"GST\|([\d.]+)% on", joined, "GST"))
    for seg in R.REQUIRED:
        out.update({(seg, C.SEBI, s): sebi for s in R.SIDES})
        out.update({(seg, C.GST, s): gst for s in R.SIDES})
    return out


def compare(published: dict, on: date) -> list[str]:
    """Made-up orders priced by the table against the same orders priced by ``published``.
    Only components the source publishes are compared."""
    found = []
    for seg, side, value in ORDERS:
        ours = R.statutory(seg, side, value, on)
        ours[C.EXCHANGE] = ours.get(C.EXCHANGE, Decimal(0)) + ours.pop(C.IPFT, Decimal(0))
        for comp, amount in ours.items():
            if comp is C.GST:
                continue  # GST follows from the components it is levied on, compared below
            key = (seg, comp, side)
            if key not in published:
                continue
            theirs = value * published[key]
            if comp is C.EXCHANGE:
                theirs += value * published.get((seg, C.IPFT, side), Decimal(0))
            if abs(theirs - amount) > TOLERANCE:
                found.append(f"{seg} {side} {comp}: the table gives Rs {amount:.4f} on a Rs {value} order, "
                             f"the page gives Rs {theirs:.4f}")
        g_key = (seg, C.GST, side)
        if g_key in published and published[g_key] != R.rate(seg, C.GST, side, on).rate:
            found.append(f"{seg} {side} GST: the page says {published[g_key]}, the table {R.rate(seg, C.GST, side, on).rate}")
    return found


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (rate check)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def run(on: date, fetch=_fetch) -> list[str]:
    alerts = []
    for name, url, parse in (("FYERS", FYERS, fyers_rates), ("Zerodha", ZERODHA, zerodha_rates)):
        try:
            published = parse(fetch(url))
        except Exception as exc:  # noqa: BLE001 - any failure to read a page is itself the alert
            alerts.append(f"{name}: couldn't read {url} ({exc}). Check the page by hand.")
            continue
        alerts += [f"{name}: {line}" for line in compare(published, on)]
    return alerts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--webhook", default=os.environ.get("SCOPE_ALERT_WEBHOOK"))
    args = ap.parse_args()
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()  # the table's dates are India's
    alerts = run(today)
    if not alerts:
        print(f"{today}: the table matches FYERS and Zerodha on every made-up order.")
        return 0
    message = (f"Charge rates may be stale ({today}). The table was NOT changed. Read the circular, "
               "then add a row to services/production/charges/rates.yaml:\n" + "\n".join(alerts))
    print(message)
    if args.webhook:
        body = json.dumps({"content": message[:1900]}).encode()
        req = urllib.request.Request(args.webhook, data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30)
    return 1


if __name__ == "__main__":
    sys.exit(main())
