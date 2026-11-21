"""The admin page's Market data card (TICKET-998): what the server holds and whether Fyers is connected.

Per underlying the mapping names (``prices/underlyings.yaml``), kept whole by the sync: the last
day held and how many days behind that is, read from its manifest on disk, and what the last run
did for it. Then the stock days waiting, the login's state, and the two ways to connect. Counts and
dates only, never a price. The database reads arrive already made, in the page's one tallies
statement, so the card costs the page no query of its own.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from services.production.market import fyers
from services.production.market import token as market_token
from services.production.market.sync import KEPT_WHOLE
from services.shared.market import day_store as ds

ZONE = ZoneInfo("Asia/Kolkata")
NOT_RECORDED = "—"
SAID = {
    "connected": "Connected. The next run uses it.",
    "expired": "That code has expired or was used already. Log in again and paste the new address.",
    "refused": "That login didn't start from this page in the last ten minutes. Press Connect Fyers again.",
    "no-code": "There was no code in that address. Paste the whole address bar the login ended on.",
}


def _day(text: str | None) -> str:
    return datetime.fromisoformat(text).strftime("%d %b %Y") if text else NOT_RECORDED


def _when(at: datetime | None) -> str:
    return at.astimezone(ZONE).strftime("%d %b %Y %H:%M") if at is not None else NOT_RECORDED


def _run_line(summary: dict, underlying: str) -> str:
    line = summary.get(underlying)
    if not line:
        return NOT_RECORDED
    if line.get("broker"):
        return "the broker refused; the next run tries again"
    if line.get("note"):
        return line["note"].split(":")[0]
    refused = len(line.get("refused") or [])
    return f"{line.get('added', 0)} days added" + (f", {refused} refused" if refused else "")


def build(*, root: Path, now: datetime, expires: datetime | None, run_at: datetime | None,
          run_result: str | None, run_summary: str | None, waiting: int) -> dict:
    summary = json.loads(run_summary) if run_summary else {}
    rows = []
    for underlying in KEPT_WHOLE:
        held = None
        if (root / underlying / ds.MANIFEST).exists():
            try:
                held = ds.read_manifest(root / underlying)
            except (ValueError, KeyError, TypeError):
                held = None
        rows.append({
            "underlying": underlying,
            "last": held.as_of.strftime("%d %b %Y") if held else "no day files yet",
            "behind": str(held.days_behind(now.astimezone(ZONE).date())) if held else NOT_RECORDED,
            "run": _run_line(summary, underlying),
        })
    app = fyers.from_env()
    return {
        "configured": app is not None,
        "one_click": bool(app and app.comes_back_here),
        "login": market_token.state_line(expires, now=now),
        "rows": rows,
        "run": f"{_when(run_at)}, {run_result}" if run_at else "no run yet",
        "waiting": waiting,
        "said": None,
    }
