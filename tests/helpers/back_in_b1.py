"""Made-up trades for B1's "back in" (TICKET-1006): the same records test_back_in_b1 writes out,
shared here so a second test file need not import a test file."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from services.production.api import scope_facts as SF
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.scope_chapters import IMP

D = Decimal
IST = ZoneInfo("Asia/Kolkata")


# The same made-up trades as test_what_you_do_next's PAIRS, written out here: a test file does
# not import another test file.
def leg(kind: str | None, side: str, net) -> mx.TradeLine:
    seg = "OPT" if kind else "FUT"
    return mx.TradeLine("NIFTY", seg, side, 1, None, None, D(str(net)),
                        strike=D("24000") if kind else None, option_type=kind)


def trip(tid, day, opened, closed, net, *legs, lots=1):
    entry = datetime.fromisoformat(f"{day}T{opened}:00").replace(tzinfo=IST)
    leave = datetime.fromisoformat(f"{day}T{closed}:00").replace(tzinfo=IST)
    lines = legs or (leg("CE", "Buy", net),)
    return mx.Trip(trip_id=tid, symbol="NIFTY", trading_day=day, entry_ts=entry, exit_ts=leave,
                   holding_seconds=int((leave - entry).total_seconds()), net=D(str(net)), lots=lots,
                   risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True, lines=lines)


PAIRS = [
    trip("a1", "2026-03-02", "09:15", "09:30", -100),
    trip("a2", "2026-03-02", "09:34", "09:50", 200),
    trip("a3", "2026-03-02", "10:01", "10:20", 0, leg("PE", "Buy", 0)),
    trip("a4", "2026-03-02", "10:25", "10:40", -50, leg("PE", "Buy", -50)),
    trip("a5", "2026-03-02", "10:35", "10:45", 30),
    trip("a6", "2026-03-02", "10:50", "11:00", -20, leg("CE", "Buy", -60), leg("CE", "Sell", 40)),
    trip("b1", "2026-03-03", "09:20", "09:40", -300, leg("PE", "Sell", -300)),
    trip("b2", "2026-03-03", "09:46", "10:00", 100, leg("CE", "Sell", 100)),
]


def facts_of(record):
    return SF.facts(SF.record_context(record), IMP)


def words(markup) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", str(markup)).split()).replace(" ,", ",").replace(" .", ".").replace(" ;", ";")


# ---------- the level trade lands in the comparison group (PAIRS) ----------
# a3 finished level (0) and closed at 10:20. a4 opened 10:25 and a5 10:35, each with a3 as the
# last trade closed before it opened, so both come after a level trade: 5 and 15 minutes.
# After a loss:                a2 (4), b2 (6)                         -> 2 trades, median 5
# After a win or a level trade: a3 (11), a6 (5), a4 (5), a5 (15)       -> 4 trades, median 8
#   sorted 5, 5, 11, 15: the middle two are 5 and 11, so the median is 8.


# ---------- 29 against 30, and 30 against 30 ----------
# One pair a day, each on its own day, so each next trade has exactly one trade before it:
#   the trade before 09:15-09:30, the next one opening a set number of minutes after 09:30.
# After a loss: 30 days, each 10 minutes later              -> 30 trades, median 10
# After a win:  20 days, each 20 minutes later
# After level:  10 days (or 9), each 30 minutes later
#   30 in the comparison group: twenty 20s then ten 30s; the 15th and 16th are both 20 -> 20.
#   29 in the comparison group: one level day fewer -> too few, nothing compared.


def paired(n_loss: int, n_win: int, n_level: int) -> list:
    out, day = [], date(2026, 1, 5)
    for prior_net, gap, n in ((-100, 10, n_loss), (100, 20, n_win), (0, 30, n_level)):
        for _ in range(n):
            iso = day.isoformat()
            opens = f"09:{30 + gap:02d}" if 30 + gap < 60 else f"10:{30 + gap - 60:02d}"
            closes = f"10:{30 + gap - 60 + 5:02d}" if 30 + gap >= 60 else f"09:{30 + gap + 5:02d}"
            out += [trip(f"p{iso}", iso, "09:15", "09:30", prior_net),
                    trip(f"n{iso}", iso, opens, closes, 50)]
            day += timedelta(days=1)
    return out
