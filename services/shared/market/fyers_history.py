"""Asking the broker for 1-minute bars: the one place the symbol and the request are chosen.

``scripts/extend_crude_series.py`` (TICKET-893) and the server's market sync (TICKET-998) both read
bars through here, so a futures series is the same construction whichever one wrote the day.

**The near month.** The broker serves a continuous future (``cont_flag=1``) relative to the
contract asked for, so asking with the nearest unexpired contract gives the near-month series,
the roll convention in ``services.shared.market.series``. Asked with the second contract it
returns the next month's series instead, about 23 points off for crude. An expired contract is an
invalid symbol to the broker, so the first month it still knows is the near month.

**The request.** At most 100 days of 1-minute bars a request (``CHUNK_DAYS`` spans 99 and the
seconds to the end of the last). Bars come back stamped by epoch seconds at the start of their
minute and are turned into naive IST, the series' clock. Prices are written as the broker sent
them, to its own precision: ``repr`` of the float, so a price keeps every decimal the broker sent
and a whole price drops its ".0".

The client is anything with Fyers' ``history(data)``. Nothing here sleeps or paces: the server
wraps its client in ``production.market.fyers.Paced``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
CHUNK_DAYS = 99  # the broker answers at most 100 days of 1-minute bars per request
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


class Refused(Exception):
    """The broker didn't give what was asked for, and the message says why."""


def history(client, symbol: str, start: datetime, end: datetime) -> dict:
    return client.history({"symbol": symbol, "resolution": "1", "date_format": "0",
                           "range_from": str(int(start.timestamp())), "range_to": str(int(end.timestamp())),
                           "cont_flag": "1"})


def near_month_symbol(client, today: date, root: str = "CRUDEOIL") -> str:
    """The nearest contract of ``root`` that the broker still knows, as an MCX futures symbol."""
    end = datetime(today.year, today.month, today.day, 23, 59, tzinfo=IST)
    for ahead in range(4):
        y, m = divmod(today.month - 1 + ahead, 12)
        symbol = f"MCX:{root}{(today.year + y) % 100:02d}{MONTHS[m]}FUT"
        if history(client, symbol, end - timedelta(days=5), end).get("s") == "ok":
            return symbol
    raise Refused(f"no {root} contract from {today:%b %Y} on is known to the broker")


def price_text(value) -> str:
    """A price as the broker sent it: every decimal kept, a whole price without its ".0"."""
    text = repr(float(value))
    return text.removesuffix(".0")


def fetch(client, symbol: str, start: date, end: date) -> dict[datetime, list[str]]:
    """Bars from the start of ``start`` to the end of ``end``, IST naive, start of minute."""
    out: dict[datetime, list[str]] = {}
    s = datetime(start.year, start.month, start.day, tzinfo=IST)
    stop = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=IST)
    while s <= stop:
        e = min(s + timedelta(days=CHUNK_DAYS), stop)
        r = history(client, symbol, s, e)
        if r.get("s") != "ok":
            raise Refused(f"the broker refused {symbol} {s:%Y-%m-%d} to {e:%Y-%m-%d}: {r.get('message', r)}")
        for c in r.get("candles") or []:
            t = datetime.fromtimestamp(c[0], IST).replace(tzinfo=None)
            out[t] = [price_text(v) for v in c[1:5]] + [str(int(c[5] or 0))]
        s = e + timedelta(seconds=1)
    return out
