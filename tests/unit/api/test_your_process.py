"""TICKET-1005: Your process, at /process.

One page that reads like an evaluation sheet: Risk, Sizing, Under drawdown, Day control and
Consistency, each a row of one or two counted lines, every figure opening its trades, no
adjective, no advice. On a new upload each line shows the earlier reading beside today's. The
rows are a registry of builders, so the Execution and Market rows can be added later without
touching the page. Every trade here is made up, and the expected figures are worked by hand in
the comments.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from services.production.api import scope_facts as SF
from services.production.api import trade_list as TL
from services.production.api.app import create_app
from services.production.db.session import make_engine, run_migrations
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.no_claims import CLAIM_PATTERNS, NEVER_USED
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def P():
    name = "services.production.api.process"
    assert importlib.util.find_spec(name), "no services/production/api/process.py"
    return importlib.import_module(name)


def trip(tid: str, day: str, net, lots: int = 1, hhmm: str = "10:00", option: bool = True,
         closed: str | None = None) -> mx.Trip:
    entry = datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=IST)
    leave = datetime.fromisoformat(f"{closed or day}T{hhmm}:00").replace(tzinfo=IST) + timedelta(minutes=20)
    seg = "OPT" if option else "EQ"
    sym = "NIFTY" if option else "WIDGETCO"
    return mx.Trip(trip_id=tid, symbol=sym, trading_day=day, entry_ts=entry, exit_ts=leave,
                   holding_seconds=int((leave - entry).total_seconds()), net=D(str(net)), lots=lots,
                   risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=option,
                   lines=(mx.TradeLine(sym, seg, "Buy", lots, None, None, D(str(net))),))


def line(rows, key: str):
    for row in rows:
        for ln in row.lines:
            if ln.key == key:
                return ln
    raise KeyError(key)


def text(ln) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", ln.text)).strip()


def build(trips, capital=None, earlier=None):
    p = P()
    before = p.Reading(earlier) if earlier is not None else None
    return p.build(p.Reading(trips, capital=capital), before)


# ---------- Risk ----------
# Losses: 500 (2 Mar), 400 (3 Mar), 300 (4 Mar), 100 (5 Mar), 50 (6 Mar): five, so the worst tenth
#   is under three and N is 3: 500 + 400 + 300 = 1,200.
# Wins: 900 (2 Mar), 700 (3 Mar), 200 (4 Mar), 100 (5 Mar). Best first: 900, then 900 + 700 = 1,600
#   reaches 1,200, so M is 2.
# Average winner (break_even's): (900 + 700 + 200 + 100) / 4 = 475. Five losses: too few for a rate.
# Days: 2 Mar +400, 3 Mar +300, 4 Mar -100, 5 Mar 0, 6 Mar -50. Total +550.
#   Best three: +400, +300, 0 (5 Mar) = 700; 700 / 550 = 127.3, so "127 of 100".
RISK = [
    trip("l1", "2026-03-02", -500), trip("w1", "2026-03-02", 900, hhmm="11:00"),
    trip("l2", "2026-03-03", -400), trip("w2", "2026-03-03", 700, hhmm="11:00"),
    trip("l3", "2026-03-04", -300), trip("w3", "2026-03-04", 200, hhmm="11:00"),
    trip("l4", "2026-03-05", -100), trip("w4", "2026-03-05", 100, hhmm="11:00"),
    trip("l5", "2026-03-06", -50),
]


def test_the_worst_trades_against_the_fewest_best_wins():
    ln = line(build(RISK), "worst")
    assert text(ln) == "Your 3 worst trades lost ₹1,200, as much as your best 2 wins made."
    assert ln.sets["worst"] == frozenset({"l1", "l2", "l3"})
    assert ln.sets["best-wins"] == frozenset({"w1", "w2"})


def test_more_than_all_your_wins():
    few = [t for t in RISK if t.trip_id not in ("w1", "w2")]  # wins 200 + 100 = 300 < 1,200
    assert text(line(build(few), "worst")) == "Your 3 worst trades lost ₹1,200, more than all your wins made."


def test_losses_smaller_than_the_average_winner_need_thirty_losses():
    assert "too few" in text(line(build(RISK), "small-losses"))
    # 30 losses: 20 of 100 and 10 of 500; ten wins of 300, so the average winner is 300.
    many = ([trip(f"a{i}", "2026-03-02", -100, hhmm=f"10:{i:02d}") for i in range(20)]
            + [trip(f"b{i}", "2026-03-03", -500, hhmm=f"10:{i:02d}") for i in range(10)]
            + [trip(f"c{i}", "2026-03-04", 300, hhmm=f"10:{i:02d}") for i in range(10)])
    ln = line(build(many), "small-losses")
    assert text(ln) == "67 of 100 losses were smaller than your average winner."  # 20 / 30
    assert ln.sets["small-losses"] == frozenset(f"a{i}" for i in range(20))


def test_the_three_best_days_against_the_total():
    ln = line(build(RISK), "best-days")
    assert text(ln) == "Your 3 best days made ₹700, 127 of 100 of your total."
    assert ln.sets["best-days"] == frozenset({"l1", "w1", "l2", "w2", "l4", "w4"})


def test_the_three_best_days_when_the_total_is_zero_or_below():
    # 2 Mar +100, 3 Mar +50, 4 Mar -400, 5 Mar -20: best three 100 + 50 - 20 = 130; overall -270.
    below = [trip("p", "2026-03-02", 100), trip("q", "2026-03-03", 50),
             trip("r", "2026-03-04", -400), trip("u", "2026-03-05", -20)]
    assert text(line(build(below), "best-days")) == "Your 3 best days made ₹130; your record overall −₹270."


def test_days_are_the_day_he_closed_as_the_calendar_counts_them():
    # Opened 2 Mar, closed 3 Mar: it is 3 Mar's.
    late = [trip("x", "2026-03-02", 500, closed="2026-03-03"), trip("y", "2026-03-02", 100),
            trip("z", "2026-03-04", 10)]
    assert line(build(late), "best-days").sets["best-days"] == frozenset({"x", "y", "z"})


# ---------- Sizing ----------
# 40 option trades: 30 at 1 lot (18 winners), 4 at 2 lots, 3 at 3 lots, 3 at 4 lots; and 2 share
# trades, left out. Median lots 1. The top tenth by lots is 4 trades: 4, 4, 4, 3, so "biggest" is
# 3 lots or more: 6 trades, too few for a rate. Usual (1 lot): 18 of 30 made money, 60 of 100.
# 30 of 40 at the usual 1 lot: 75 of 100; the rest from 2 to 4.
def sizing_record():
    out = [trip(f"u{i}", "2026-03-02", 100 if i < 18 else -100, hhmm=f"10:{i:02d}") for i in range(30)]
    out += [trip(f"two{i}", "2026-03-03", 50, lots=2, hhmm=f"10:{i:02d}") for i in range(4)]
    out += [trip(f"three{i}", "2026-03-04", 50, lots=3, hhmm=f"10:{i:02d}") for i in range(3)]
    out += [trip(f"four{i}", "2026-03-05", -50, lots=4, hhmm=f"10:{i:02d}") for i in range(3)]
    out += [trip(f"sh{i}", "2026-03-06", 10, lots=1, option=False, hhmm=f"10:{i:02d}") for i in range(2)]
    return out


def test_sizing_at_the_biggest_and_the_usual_size():
    ln = line(build(sizing_record()), "sizes")
    assert text(ln) == ("At your biggest sizes, 3 lots or more, 6 trades: too few for a rate; "
                        "at your usual size, 1 lot, you made money 60 of 100.")
    assert ln.sets["usual"] == frozenset(f"u{i}" for i in range(30))
    assert ln.sets["biggest"] == frozenset({*(f"three{i}" for i in range(3)), *(f"four{i}" for i in range(3))})


def test_the_share_of_trades_at_the_usual_size_with_shares_left_out():
    rows = build(sizing_record())
    assert text(line(rows, "usual-share")) == "75 of 100 trades at your usual 1 lot; the rest from 2 to 4 lots."
    assert text(line(rows, "left-out")) == "2 trades in shares are left out of this row."


def test_no_trades_in_lots():
    rows = build([trip("sh", "2026-03-02", 10, option=False)])
    sizing = next(r for r in rows if r.key == "sizing")
    assert sizing.empty == "No trades in lots."


# ---------- Under drawdown ----------
# Exits: 2 Mar +1,000 (high 1,000), 3 Mar -300 (700), 4 Mar -500 (200), 5 Mar +100 (300),
# 6 Mar +900 (1,200). The biggest drop is 800, from 2 Mar to 4 Mar.
# Inside: 3 trades on 3 days, 1 a day; lots 1, 2, 3, average 2. The rest: 2 trades on 2 days,
# 1 a day; 1 lot each. Both too few for a rate. Capital 10,000: 800 is 8 of 100 of it.
DROP = [trip("h", "2026-03-02", 1000), trip("d2", "2026-03-03", -300, lots=2),
        trip("d3", "2026-03-04", -500, lots=3), trip("r4", "2026-03-05", 100),
        trip("r5", "2026-03-06", 900)]


def test_inside_the_biggest_drop_against_the_rest():
    ln = line(build(DROP), "drop")
    assert text(ln) == ("In your biggest drop, 02 Mar 2026 to 04 Mar 2026: 1 trade a day, 2 lots on "
                        "average, 3 trades: too few for a rate. The rest of your record: 1 trade a day, "
                        "1 lot on average, 2 trades: too few for a rate.")
    assert ln.sets["drop"] == frozenset({"h", "d2", "d3"})
    assert ln.sets["rest"] == frozenset({"r4", "r5"})


def test_the_drop_against_capital_only_when_he_told_us():
    assert text(line(build(DROP, capital=D(10000)), "capital")) == (
        "Your biggest drop was 8 of 100 of the capital you told us.")
    with pytest.raises(KeyError):
        line(build(DROP), "capital")
    drawdown = next(r for r in build(DROP) if r.key == "drawdown")
    assert "No capital told." in drawdown.notes


# ---------- Day control ----------
# By day, exits in order: A (2 Mar) -200, -300, +600: running -200, -500, +100, so it dipped to -500
# and finished +100. B (3 Mar) -100, -400: -100, -500, and finished -500. C (4 Mar) -150.
# D (5 Mar) -50. Losing days: B -500, C -150, D -50; the median, the usual losing day, is -150.
# Down more than 150 at some point: A and B, 2 days. Finished lower than -150: B, 1 of them.
DAYS = [trip("a1", "2026-03-02", -200, hhmm="09:30"), trip("a2", "2026-03-02", -300, hhmm="10:30"),
        trip("a3", "2026-03-02", 600, hhmm="11:30"),
        trip("b1", "2026-03-03", -100, hhmm="09:30"), trip("b2", "2026-03-03", -400, hhmm="10:30"),
        trip("c1", "2026-03-04", -150), trip("e1", "2026-03-05", -50)]


def test_day_control_a_day_that_dips_and_recovers_and_one_that_keeps_falling():
    ln = line(build(DAYS), "day-control")
    assert text(ln) == ("Your usual losing day: −₹150. On 2 days you were down more than that at some "
                        "point; on 1 of them you finished lower than that.")
    assert ln.sets["dipped"] == frozenset({"a1", "a2", "a3", "b1", "b2"})
    assert ln.sets["fell"] == frozenset({"b1", "b2"})


def test_no_losing_days():
    rows = build([trip("g", "2026-03-02", 10)])
    assert next(r for r in rows if r.key == "day-control").empty == "No losing days."


# ---------- Consistency ----------

def test_months_that_made_money_from_the_month_candles():
    months = [trip("j", "2026-01-12", 300), trip("f", "2026-02-12", -100), trip("m", "2026-03-12", 50)]
    ln = line(build(months), "months")
    assert text(ln) == "Made money in 2 of 3 months."
    assert ln.sets["months"] == frozenset({"j", "m"})
    assert "/mirror/fact/hidden" in line(build(months), "halves").text


# ---------- What moved since his last file ----------

def test_each_line_shows_the_earlier_reading_beside_todays():
    earlier = [t for t in RISK if t.trip_id != "l1"]  # worst three: 400 + 300 + 100 = 800
    assert text(line(build(RISK, earlier=earlier), "worst")).endswith("made. ₹1,200, was ₹800.")


def test_no_earlier_figure_when_either_reading_is_below_the_minimum():
    earlier = [t for t in RISK if t.trip_id in ("l1", "l2", "w1")]  # two losses: no worst three
    assert ", was " not in text(line(build(RISK, earlier=earlier), "worst"))
    assert ", was " not in text(line(build(RISK), "worst"))


# ---------- The registry ----------

def test_the_rows_are_a_registry_of_builders():
    p = P()
    assert [b.__name__ for b in p.ROWS] == ["risk", "sizing", "under_drawdown", "day_control", "consistency"]
    assert [r.name for r in build(RISK)] == ["Risk", "Sizing", "Under drawdown", "Day control", "Consistency"]


def test_a_row_added_to_the_registry_reaches_the_page_and_the_trade_list(monkeypatch):
    p = P()

    def execution(reading):
        ids = frozenset(t.trip_id for t in reading.trips[:2])
        return p.Row("execution", "Execution", (p.Line("exec", ("Two trades.",), {"exec": ids}),))

    monkeypatch.setattr(p, "ROWS", [*p.ROWS, execution])
    assert build(RISK)[-1].name == "Execution"
    assert p.members(RISK, "exec") == frozenset({"l1", "w1"})


# ---------- Every count opens exactly its trades ----------

def _listed(href: str, record) -> int:
    query = {k: v[0] for k, v in parse_qs(urlparse(href).query).items()}
    return TL.listing("risk", SF.record_context(record), query, {})["shown"]


def test_every_figure_opens_exactly_its_trades():
    for record in (RISK, sizing_record(), DROP, DAYS):
        for row in build(record):
            for ln in row.lines:
                for key, ids in ln.sets.items():
                    href = P().href(key)
                    if not ids:  # a figure of 0 opens nothing: no link is drawn
                        assert f'href="{href}"' not in str(ln.text).replace("&amp;", "&")
                        continue
                    assert parse_qs(urlparse(href).query) == {"line": [key]}
                    assert _listed(href, record) == len(ids), key


def test_the_line_filter_is_on_the_factor_map():
    from services.production.api import factor_map
    assert any(f.name == "line" and f.quiet for f in TL.FILTERS)
    assert any("line" in f.filters for f in factor_map.FACTORS)


# ---------- On the page ----------

@pytest.fixture()
def client():
    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    c = sign_up(TestClient(create_app()), engine, "Y-1", "processreader")
    c.post("/upload/demo", data={"csrf_token": CSRF.search(c.get("/upload").text).group(1)},
           follow_redirects=False)
    return c


def main_of(html: str) -> str:
    return re.search(r"<main.*?</main>", html, re.DOTALL).group(0)


def test_the_page_its_rows_and_the_links_to_it(client):
    html = client.get("/process").text
    assert "Your process" in html
    for name in ("Risk", "Sizing", "Under drawdown", "Day control", "Consistency"):
        assert f">{name}<" in html, name
    assert 'href="/process"' in client.get("/").text
    assert 'href="/process"' in client.get("/mirror").text


def test_home_previews_three_rows(client):
    home = client.get("/").text
    preview = re.search(r'<section class="card process-preview".*?</section>', home, re.DOTALL)
    assert preview, "no preview on Home"
    names = re.findall(r'class="process-preview__name">([^<]+)<', preview.group(0))
    assert names == ["Risk", "Sizing", "Consistency"]


def test_it_follows_the_report_filter(client):
    whole = client.get("/process").text
    client.get("/mirror/filter", params={"period": "all", "book": "NIFTY options", "next": "/process"},
               follow_redirects=False)
    narrowed = client.get("/process").text
    assert whole != narrowed
    assert "NIFTY options" in narrowed


def text_of(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_every_link_on_it_opens(client):
    body = main_of(client.get("/process").text)
    hrefs = {h.replace("&amp;", "&") for h in re.findall(r'href="([^"#]+)"', body) if h.startswith("/mirror")}
    assert any("line=" in h for h in hrefs)
    for href in sorted(hrefs):
        assert client.get(href).status_code == 200, href


def test_no_claim_no_never_used_word_no_adjective_no_script(client):
    body = main_of(client.get("/process").text)
    assert "<script" not in body
    words = text_of(body).lower()
    assert not [w for w in NEVER_USED if re.search(rf"\b{re.escape(w)}\b", words)]
    assert not [p for p, _why in CLAIM_PATTERNS if re.search(p, words, re.IGNORECASE)]
    for word in ("good", "bad", "better", "worse", "strong", "weak", "stable", "your rule",
                 "your plan", "your system"):
        assert not re.search(rf"\b{word}\b", words), word
