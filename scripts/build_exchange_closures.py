"""Write the weekdays NSE and BSE were shut, from the exchanges' own daily bars (TICKET-895).

    uv run --with fyers-apiv3 python scripts/build_exchange_closures.py --token-file <path>

A monthly contract's symbol names its month, not its day: the exchange's rule gives the day
(its last expiry weekday), and a holiday on that day moves the expiry to the trading day
before. The holidays are read from what the exchange did: a weekday with no daily bar for
its index (NIFTY 50 and NIFTY BANK on NSE, SENSEX on BSE) was a closure. Through the
existing Fyers connection (ADR 008). Dates only: no price is written.

The token is read from a file outside the repository and never written anywhere. Run it
monthly with the crude refresh; a closure is never removed, only days added.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

OUT = Path("services/shared/market/exchange_closures.yaml")
IST = timezone(timedelta(hours=5, minutes=30))
INDICES = {"NSE": ("NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX"), "BSE": ("BSE:SENSEX-INDEX",)}
START = date(2017, 1, 1)


def trading_days(client, symbol: str, start: date, end: date) -> set[date]:
    """Every day the symbol has a daily bar, asked for a year at a time."""
    days: set[date] = set()
    at = start
    while at <= end:
        to = min(at + timedelta(days=364), end)
        time.sleep(1.3)  # under the 50-a-minute limit
        got = client.history({"symbol": symbol, "resolution": "D", "date_format": "1",
                              "range_from": at.isoformat(), "range_to": to.isoformat(),
                              "cont_flag": "1"})
        if got.get("s") != "ok":
            raise SystemExit(f"{symbol} {at}..{to}: {got.get('code')} {got.get('message')}")
        days |= {datetime.fromtimestamp(c[0], IST).date() for c in got.get("candles") or []}
        at = to + timedelta(days=1)
    return days


def closures(open_days: list[set[date]], start: date, end: date) -> tuple[list[date], list[date]]:
    """Weekdays no index traded, and weekend days any index did (muhurat, budget Sundays)."""
    shut, weekend = [], []
    day = start
    while day <= end:
        traded = any(day in d for d in open_days)
        if day.weekday() < 5 and not traded:
            shut.append(day)
        elif day.weekday() >= 5 and traded:
            weekend.append(day)
        day += timedelta(days=1)
    return shut, weekend


def render(through: date, found: dict[str, tuple[list[date], list[date]]]) -> str:
    lines = [
        "# Weekdays each exchange was shut, and weekend days it traded (TICKET-895).",
        "#",
        "# Read from the exchanges' own daily bars through the Fyers connection (ADR 008) by",
        "# scripts/build_exchange_closures.py: a weekday with no bar for the exchange's index was a",
        "# closure. Dates only. Used to date a monthly contract whose symbol names only its month:",
        "# the exchange's last expiry weekday, moved to the trading day before when it was shut.",
        "# Days after `through` are not known here; a date past it is not moved.",
        f"through: {through.isoformat()}",
        f"from: {START.isoformat()}",
        "exchanges:",
    ]
    for exchange, (shut, weekend) in found.items():
        lines.append(f"  {exchange}:")
        lines.append("    closed: [" + ", ".join(d.isoformat() for d in shut) + "]")
        lines.append("    weekend_sessions: [" + ", ".join(d.isoformat() for d in weekend) + "]")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--token-file", type=Path, required=True)
    p.add_argument("--through", type=date.fromisoformat,
                   default=datetime.now(IST).date() - timedelta(days=1))
    a = p.parse_args(argv)
    from fyers_apiv3 import fyersModel  # only the build needs the broker's library

    tok = json.loads(a.token_file.read_text(encoding="utf-8"))
    client = fyersModel.FyersModel(client_id=tok["client_id"], token=tok["access_token"],
                                   is_async=False, log_path="")
    found = {}
    for exchange, symbols in INDICES.items():
        days = [trading_days(client, s, START, a.through) for s in symbols]
        found[exchange] = closures(days, START, a.through)
        print(f"{exchange}: {len(found[exchange][0])} weekday closures, "
              f"{len(found[exchange][1])} weekend sessions", file=sys.stderr)
    OUT.write_text(render(a.through, found), encoding="utf-8")
    print(f"written: {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
