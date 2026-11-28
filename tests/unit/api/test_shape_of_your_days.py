"""TICKET-1007: the shape of your days, four sections on Your numbers.

Your books on your worst days, your days by how many trades you took, your first 30 minutes,
and trades held overnight. Counts only: no section says which group is better. Every count
opens exactly its trades in the trade list. Every trade here is made up and the expected values
are worked by hand in the comments.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from services.production.api import numbers as N
from services.production.api import scope_facts as SF
from services.production.api import trade_list as TL
from services.production.api.app import create_app
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.no_claims import CLAIM_PATTERNS, NEVER_USED
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def fn(name: str):
    assert hasattr(N, name), f"numbers has no {name}()"
    return getattr(N, name)


def trip(tid: str, opened: str, net: str, closed: str | None = None, segment: str = "OPT",
         symbol: str = "NIFTY") -> mx.Trip:
    entry = datetime.fromisoformat(opened).replace(tzinfo=IST)
    leave = datetime.fromisoformat(closed).replace(tzinfo=IST) if closed else entry.replace(
        minute=min(entry.minute + 5, 59))
    line = mx.TradeLine(symbol, segment, "Buy", 1, None, None, D(net), entry_ts=entry)
    return mx.Trip(trip_id=tid, symbol=symbol, trading_day=entry.date().isoformat(), entry_ts=entry,
                   exit_ts=leave, holding_seconds=int((leave - entry).total_seconds()), net=D(net),
                   lots=1, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID,
                   is_option=segment == "OPT", lines=(line,))


# Three books: NIFTY options (8 trades, under 20, so "Other options"), Futures (CRUDEOIL),
# Stocks and ETFs (TATASTEEL). A day is the day he closed (993).
#   Mon 2 Feb  a1 opt 09:20 -100   a2 fut 09:10 -50   a3 share 10:00 +30       -> -120, 3 trades
#   Tue 3 Feb  b1 opt 09:50 -200   b2 fut 17:05 -100 (MCX evening)              -> -300, 2 trades
#   Wed 4 Feb  c1 opt 11:00 +500   g1 fut opened Tue 22:00, closed Wed -60      -> +440, 2 trades
#   Thu 5 Feb  d1 opt 09:15 -40                                                 ->  -40, 1 trade
#   Fri 6 Feb  e2 share 10:00 +10                                               ->  +10, 1 trade
#   Mon 9 Feb  e1 opt opened Fri 6 Feb 14:00, closed Mon 09:30 +80 (a weekend)
#              f1 opt 09:40 -10   f2 opt 10:10 -10   f3 opt 11:10 -10           ->  +50, 4 trades
# Total 13 trades, +40.
RECORD = [
    trip("a1", "2026-02-02T09:20", "-100"),
    trip("a2", "2026-02-02T09:10", "-50", segment="FUT", symbol="CRUDEOIL"),
    trip("a3", "2026-02-02T10:00", "30", segment="EQ", symbol="TATASTEEL"),
    trip("b1", "2026-02-03T09:50", "-200"),
    trip("b2", "2026-02-03T17:05", "-100", segment="FUT", symbol="CRUDEOIL"),
    trip("g1", "2026-02-03T22:00", "-60", closed="2026-02-04T10:00", segment="FUT", symbol="CRUDEOIL"),
    trip("c1", "2026-02-04T11:00", "500"),
    trip("d1", "2026-02-05T09:15", "-40"),
    trip("e2", "2026-02-06T10:00", "10", segment="EQ", symbol="TATASTEEL"),
    trip("e1", "2026-02-06T14:00", "80", closed="2026-02-09T09:30"),
    trip("f1", "2026-02-09T09:40", "-10"),
    trip("f2", "2026-02-09T10:10", "-10"),
    trip("f3", "2026-02-09T11:10", "-10"),
]


def _listed(href: str) -> int:
    query = {k: v[0] for k, v in parse_qs(urlparse(href).query).items()}
    return TL.listing("risk", SF.record_context(RECORD), query, {})["shown"]


def _query(href: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(href).query).items()}


# ---------- 2. your books on your worst days ----------
# Six traded days: the worst tenth, at least 5, from the days that lost (TICKET-1050: a day he
# made money is never called worst), worst first: 3 Feb -300, 2 Feb -120, 5 Feb -40.
# Books, the verdict's split: Other options, Futures, Stocks and ETFs.
#   3 Feb: options -200 lost, futures -100 lost, shares none     -> every book traded lost
#   2 Feb: options -100 lost, futures -50 lost, shares +30 made  -> not (3 books, 2 lost)
#   5 Feb: options -40 lost, nothing else                         -> every book traded lost
# "On your 3 worst days, every book you traded lost on 2."

def test_the_worst_tenth_of_days_at_least_five_worst_first():
    view = fn("worst_books")(RECORD)
    assert view["shown"] is True
    assert [d["day"] for d in view["days"]] == ["2026-02-03", "2026-02-02", "2026-02-05"]
    assert view["books"] == ["Other options", "Futures", "Stocks and ETFs"]


def test_each_book_on_a_worst_day_lost_made_money_or_didnt_trade():
    view = fn("worst_books")(RECORD)
    states = {d["day"]: [c["state"] for c in d["cells"]] for d in view["days"]}
    assert states["2026-02-03"] == ["lost", "lost", "none"]
    assert states["2026-02-02"] == ["lost", "lost", "made"]
    assert states["2026-02-05"] == ["lost", "none", "none"]


def test_the_line_counts_days_every_book_he_traded_lost():
    view = fn("worst_books")(RECORD)
    assert (view["count"], view["all_lost"]) == (3, 2)  # the sentence is the template's (TICKET-1050)


def test_cells_are_toned_by_sign():
    view = fn("worst_books")(RECORD)
    cells = {d["day"]: d["cells"] for d in view["days"]}
    assert cells["2026-02-03"][0]["tone"].startswith("ch-cell ch-cell--loss-")
    assert cells["2026-02-02"][2]["tone"].startswith("ch-cell ch-cell--gain-")
    assert cells["2026-02-03"][2]["tone"] == "ch-cell ch-cell--surface"


def test_a_single_book_record_has_no_grid():
    one = [t for t in RECORD if t.is_option]
    assert fn("worst_books")(one)["shown"] is False


def test_a_worst_day_and_its_book_cells_open_exactly_their_trades():
    view = fn("worst_books")(RECORD)
    day = view["days"][0]
    assert _query(day["href"]) == {"closed_day": "2026-02-03"}
    assert _listed(day["href"]) == 2
    futures = day["cells"][1]
    assert _query(futures["href"]) == {"closed_day": "2026-02-03", "book_group": "Futures"}
    assert _listed(futures["href"]) == 1
    assert day["cells"][2]["href"] is None  # no trades: nothing to open


# ---------- 3. your days by how many trades you took ----------
# Trades per day: 2 Feb 3, 3 Feb 2, 4 Feb 2, 5 Feb 1, 6 Feb 1, 9 Feb 4. Sorted 1 1 2 2 3 4.
# Cut points his own: the third and two-thirds days, 1 and 2.
#   1 trade:          5, 6 Feb   2 days, 2 trades, -40+10  = -30
#   2 trades:         3, 4 Feb   2 days, 4 trades, -300+440 = +140
#   3 or more trades: 2, 9 Feb   2 days, 7 trades, -120+50 = -70

def test_days_in_thirds_by_his_own_cut_points():
    thirds = fn("day_trades")(RECORD)["thirds"]
    assert [(t["label"], t["days"], t["trades"], t["net"]) for t in thirds] == [
        ("1 trade", 2, 2, D(-30)), ("2 trades", 2, 4, D(140)), ("3 or more trades", 2, 7, D(-70))]
    assert all(t["rate"] is None for t in thirds)  # under 30 days: too few


def test_ties_at_a_cut_point_stay_together():
    # Days with 1, 2, 2, 2, 3, 5 trades: both cut points fall on 2, so every 2-trade day is in
    # the first third, the middle third is empty and is left out.
    days = [1, 2, 2, 2, 3, 5]
    record = [trip(f"t{d}{k}", f"2026-03-{d + 1:02d}T10:{k:02d}", "10")
              for d, n in enumerate(days) for k in range(n)]
    thirds = fn("day_trades")(record)["thirds"]
    assert [(t["label"], t["days"]) for t in thirds] == [("1–2 trades", 4), ("3 or more trades", 2)]


def test_made_money_days_from_thirty_days():
    record = [trip(f"x{i}", f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}T10:00", "10" if i < 20 else "-5")
              for i in range(31)]
    third = fn("day_trades")(record)["thirds"][0]
    assert third["days"] == 31 and third["rate"] == D("64.5")  # 20 of 31 days


def test_a_third_opens_exactly_its_trades():
    thirds = fn("day_trades")(RECORD)["thirds"]
    assert _query(thirds[2]["href"]) == {"day_trades": "3-plus"}
    assert [_listed(t["href"]) for t in thirds] == [2, 4, 7]


# ---------- 4. your first 30 minutes ----------
# NSE opens 09:15 (NIFTY, TATASTEEL), MCX 09:00 (CRUDEOIL); from each, 30 minutes.
#   First 30 minutes: a1 09:20 -100, a2 MCX 09:10 -50, d1 09:15 -40, f1 09:40 -10 -> 4, -200
#   The rest: a3, b1 09:50, b2 MCX 17:05 (the evening is not a second open), c1, e1, e2, f2,
#             f3, g1 MCX 22:00 -> 9 trades, +240

def test_first_thirty_minutes_from_each_instruments_own_open():
    view = fn("first_half_hour")(RECORD)
    assert [(r["name"], r["trades"], r["net"]) for r in view["rows"]] == [
        ("First 30 minutes", 4, D(-200)), ("The rest", 9, D(240))]
    assert view["left_out"] == 0


def test_an_mcx_evening_trade_is_not_an_opening_trade():
    assert hasattr(TL, "opening"), "trade_list has no opening reader"
    assert TL.opening(RECORD[4], {}) == (1, "rest", "The rest")  # b2, 17:05 on MCX
    assert TL.opening(RECORD[1], {}) == (0, "first-30", "First 30 minutes")  # a2, 09:10 on MCX


def test_the_opening_rows_open_exactly_their_trades():
    rows = fn("first_half_hour")(RECORD)["rows"]
    assert _query(rows[0]["href"]) == {"opening": "first-30"}
    assert [_listed(r["href"]) for r in rows] == [4, 9]


# ---------- 5. held overnight ----------
# Options and futures only; the two shares (a3, e2) are counted apart.
#   Overnight: e1 +80 (Fri to Mon, 3 days), g1 -60 (1 day)       -> 2 trades, +20
#   Same day: a1 a2 b1 b2 c1 d1 f1 f2 f3                         -> 9 trades, -20

def test_overnight_against_same_day_with_shares_apart():
    view = fn("overnight")(RECORD)
    assert [(r["name"], r["trades"], r["net"]) for r in view["rows"]] == [
        ("Held overnight", 2, D(20)), ("Closed the same day", 9, D(-20))]
    assert view["shares"] == 2


def test_the_longest_hold_is_named_in_days_across_a_weekend():
    view = fn("overnight")(RECORD)
    assert view["longest"] == 3


def test_the_longest_hold_opens_the_trades_held_that_long_not_a_day_page():
    """The longest hold is a figure about one trade: it opens the trades held that many days
    (TICKET-1050), not the day page and not every trade closed the day it ended. e1, 3 days."""
    href = fn("overnight")(RECORD)["longest_href"]
    assert "/mirror/day/" not in href
    assert _query(href) == {"held_days": "3"}
    assert _listed(href) == 1


def test_the_overnight_rows_open_exactly_their_trades():
    rows = fn("overnight")(RECORD)["rows"]
    assert _query(rows[0]["href"]) == {"overnight": "overnight"}
    assert [_listed(r["href"]) for r in rows] == [2, 9]


# ---------- 6. the filters: on the risk list only, and on the map ----------

def test_the_new_filters_are_on_the_risk_list_only_and_on_the_map():
    from services.production.api import factor_map
    named = {f.name: f for f in TL.FILTERS}
    for name in ("day_trades", "opening", "overnight"):
        assert name in named, name
        assert named[name].only == frozenset({"risk"}), name
    on_map = {k for f in factor_map.FACTORS for k in f.filters}
    assert {"day_trades", "opening", "overnight", "closed_day"} <= on_map


# ---------- 1, 7, 8. on the page ----------

@pytest.fixture()
def demo(engine):
    client = sign_up(TestClient(create_app()), engine, "S-1", "visitor")
    client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
    return client


SECTIONS = ("worst-books", "day-trades", "opening", "overnight")


def test_four_sections_after_when_you_trade(demo):
    html = demo.get("/numbers").text
    for sid in SECTIONS:
        assert f'id="{sid}"' in html, sid
    at = [html.index(f'id="{s}"') for s in SECTIONS]
    assert html.index('id="when"') < at[0] < at[1] < at[2] < at[3]
    assert at[3] < html.index("By how close to expiry you closed")
    for heading in ("Your books on your worst days", "Your days by how many trades you took",
                    "Your first 30 minutes", "Held overnight"):
        assert heading in html


def test_no_script_no_claim_and_no_verdict(demo):
    html = demo.get("/numbers").text
    for sid in SECTIONS:
        found = re.search(rf'<section class="[^"]*" id="{sid}">.*?</section>', html, re.DOTALL)
        assert found, sid
        section = found.group(0)
        assert "<script" not in section
        text = re.sub(r"<[^>]+>", " ", section).lower()
        assert not [w for w in NEVER_USED if re.search(rf"\b{re.escape(w)}\b", text)], sid
        assert not [p for p, _ in CLAIM_PATTERNS if re.search(p, text, re.IGNORECASE)], sid
        for word in (r"\bbest\b", r"\bworse\b", r"\bbetter\b", r"\bgood\b", r"\bbad\b"):
            assert re.search(word, text) is None, (sid, word)


def test_the_filters_answer_on_the_list(demo):
    for name, value in (("opening", "first-30"), ("overnight", "overnight")):
        page = demo.get(f"/mirror/fact/risk/trades?{name}={value}")
        assert page.status_code == 200
        assert f'name="{name}"' in page.text and f'value="{value}" selected' in page.text, name
