"""TICKET-1031: days you can replay.

The day page draws the day's running result trade by trade, with its peak, its trough and its
close; it links to the day before and after; each of the five worst days carries the run page's
sentences where they hold; and the worst-days chart is sorted worst to best with the cumulative
result as a line. Every trade here is made up, and every figure is worked by hand below.
"""
from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import re
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from services.production.api import scope_facts as SF
from services.production.api.app import create_app
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.scope_chapters import IMP
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def need(module, name: str):
    assert hasattr(module, name), f"{module.__name__} has no {name}"
    return getattr(module, name)


def mod(name: str):
    assert importlib.util.find_spec(name), f"no {name}"
    return importlib.import_module(name)


def trip(tid: str, day: str, opened: str, closed: str, net: int, side: str, qty: int) -> mx.Trip:
    entry = datetime.fromisoformat(f"{day}T{opened}").replace(tzinfo=IST)
    leave = datetime.fromisoformat(f"{day}T{closed}").replace(tzinfo=IST)
    line = mx.TradeLine("NIFTY", "OPT", "Buy", qty, D(100), D(100), D(net), strike=D(24000),
                        option_type=side, entry_ts=entry)
    return mx.Trip(trip_id=tid, symbol="NIFTY", trading_day=day, entry_ts=entry, exit_ts=leave,
                   holding_seconds=int((leave - entry).total_seconds()), net=D(net), lots=qty // 75,
                   risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True, lines=(line,))


# 2 Mar, worked by hand, in exit order:
#   a1 09:20-09:30 CE 75  +500 -> +500   the peak, 09:30
#   a2 09:31-09:40 PE 75  -300 -> +200   switched from call to put
#   a3 09:41-09:50 PE 75  -400 -> -200
#   a4 09:52-10:00 CE 150 -600 -> -800   switched back; size 75 -> 150 after two losses; trough 10:00
#   a5 10:01-10:10 CE 150 +100 -> -700   the close
# Switches: 2. Back in within 2 minutes: gaps 60, 60, 120, 60 seconds -> 4 of 4.
# 3 Mar: one trade, +1,000. 4 Mar: -200 and -100, so -300.
# Days, worst to best: 2 Mar -700, 4 Mar -300, 3 Mar +1,000. Cumulative: -700, -1,000, 0.
DAY_A = [
    trip("a1", "2026-03-02", "09:20", "09:30", 500, "CE", 75),
    trip("a2", "2026-03-02", "09:31", "09:40", -300, "PE", 75),
    trip("a3", "2026-03-02", "09:41", "09:50", -400, "PE", 75),
    trip("a4", "2026-03-02", "09:52", "10:00", -600, "CE", 150),
    trip("a5", "2026-03-02", "10:01", "10:10", 100, "CE", 150),
]
RECORD = [
    *DAY_A,
    trip("b1", "2026-03-03", "10:00", "10:30", 1000, "CE", 75),
    trip("c1", "2026-03-04", "10:00", "10:10", -200, "PE", 75),
    trip("c2", "2026-03-04", "11:00", "11:10", -100, "PE", 75),
]


# ---------- 1. the day's running result ----------

def test_the_path_is_the_running_result_in_exit_order_with_peak_trough_and_close():
    path = need(mx, "day_path")(list(reversed(DAY_A)))  # given in any order, drawn in exit order
    assert [p.trip.trip_id for p in path.points] == ["a1", "a2", "a3", "a4", "a5"]
    assert [p.running for p in path.points] == [D(500), D(200), D(-200), D(-800), D(-700)]
    assert (path.peak.running, path.peak.exit_ts.strftime("%H:%M")) == (D(500), "09:30")
    assert (path.trough.running, path.trough.exit_ts.strftime("%H:%M")) == (D(-800), "10:00")
    assert path.close == D(-700)
    assert [p.switched for p in path.points] == [False, True, False, True, False]
    assert [p.lots for p in path.points] == [1, 1, 1, 2, 2]


def test_the_day_chart_says_the_peak_trough_and_close_and_draws_every_trade():
    view = mod("services.production.api.day_chart").view(need(mx, "day_path")(DAY_A))
    text = re.sub(r"<[^>]+>", "", str(view["said"]))
    assert text == "Up ₹500 at 09:30 at best; down ₹800 at 10:00 at worst; finished −₹700."
    svg = str(view["svg"])
    assert svg.count('class="daychart__dot') == 5
    assert svg.count("daychart__dot--switched") == 2
    assert "<polyline" in svg
    assert str(view["table"]).count("<tr>") == 1 + 5  # a heading, and a row a trade


def test_a_day_that_never_went_up_says_no_peak():
    view = mod("services.production.api.day_chart").view(need(mx, "day_path")(RECORD[-2:]))
    text = re.sub(r"<[^>]+>", "", str(view["said"]))
    assert not text.startswith("Up") and text.endswith("finished −₹300.")


# ---------- 2. the day before and after ----------

def test_previous_and_next_stop_at_the_record_s_first_and_last_days():
    assert need(mx, "day_neighbours")(RECORD, "2026-03-02") == (None, "2026-03-03")
    assert need(mx, "day_neighbours")(RECORD, "2026-03-03") == ("2026-03-02", "2026-03-04")
    assert need(mx, "day_neighbours")(RECORD, "2026-03-04") == ("2026-03-03", None)


# ---------- 3. the worst days told like the run page ----------

def test_a_day_s_story_reuses_the_run_page_s_facts():
    story = need(mx, "day_story")(DAY_A)
    assert story.flips == 2
    assert (story.size.losses_before, story.size.steps) == (2, [75, 150])
    assert (story.back_in.within, story.back_in.of) == (4, 4)


def test_a_size_step_after_a_win_says_nothing_about_losses():
    rose_after_a_win = [DAY_A[0], trip("w2", "2026-03-02", "09:31", "09:40", 50, "CE", 150)]
    assert need(mx, "day_story")(rose_after_a_win).size is None


def test_each_worst_day_carries_the_run_page_s_sentences_when_they_hold():
    figs = SF.facts(SF.record_context(RECORD), IMP)
    block = next(b for b in figs["worst-days"]["blocks"] if b["iso"] == "2026-03-02")
    assert "story" in block, "a worst day has no story"
    assert block["story"]["flips_words"] == "2 times"
    assert block["story"]["size_words"] == "After two losses you doubled your size (75 → 150)."
    assert (block["story"]["back_in"].within, block["story"]["back_in"].of) == (4, 4)
    quiet = next(b for b in figs["worst-days"]["blocks"] if b["iso"] == "2026-03-04")
    assert "story" in quiet
    assert not quiet["story"]["flips_words"] and not quiet["story"]["size_words"]


# ---------- 4. the worst-days chart, sorted and cumulative ----------

def test_the_worst_days_are_sorted_and_cumulative_and_end_at_the_record_s_result():
    sorted_days = need(SF, "days_worst_to_best")(RECORD)
    assert [d["iso"] for d in sorted_days] == ["2026-03-02", "2026-03-04", "2026-03-03"]
    assert [d["cumulative"] for d in sorted_days] == [D(-700), D(-1000), D(0)]
    assert sorted_days[-1]["cumulative"] == sum((t.net for t in RECORD), D(0))


def test_the_card_draws_the_cumulative_line_and_the_dial_keeps_the_kit_bars():
    figs = SF.facts(SF.record_context(RECORD), IMP)
    roles = [p["role"] for p in figs["worst-days"]["chart"]["parts"]]
    assert "stroke" in roles  # the cumulative line
    mini_roles = [p["role"] for p in figs["worst-days"]["mini"]["parts"]]
    assert "stroke" not in mini_roles  # the dial's mini stays the kit's chart


# ---------- on the pages ----------

@pytest.fixture()
def demo(engine):
    client = sign_up(TestClient(create_app()), engine, "R-1", "replayer")
    client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
    return client


def _days(client) -> list[str]:
    return _opened_days(client)  # not from /numbers: its day links open the closed-day list


def test_the_day_page_draws_the_day_and_links_its_neighbours(demo):
    days = _days(demo)
    first, second = days[0], days[1]
    html = demo.get(f"/mirror/day/{first}").text
    assert '<svg class="daychart' in html
    assert f'href="/mirror/day/{second}"' in html
    nav = re.search(r'<p class="body-small day-nav".*?</p>', html, re.DOTALL)
    assert nav, "no day-nav on the day page"
    assert "‹" not in nav.group(0)  # the first day has no day before
    html2 = demo.get(f"/mirror/day/{second}").text
    assert f'href="/mirror/day/{first}"' in html2
    assert "<script" not in re.search(r"<main.*?</main>", html, re.DOTALL).group(0)


def test_the_worst_days_page_draws_the_sorted_chart(demo):
    html = demo.get("/mirror/fact/worst-days").text
    assert "Your days, worst to best" in html
    assert "data-daypath" in html  # each worst day's line is the shared component


# ---------- review: a day is the day he opened; Your numbers counts the day he closed ----------
# A trade opened 4 Mar 15:10 and closed 5 Mar 09:20, worked by hand: running -200 (c1), -300 (c2),
# +200 (h1, +500, closed the next morning). It belongs to 4 Mar's page, as the five worst days
# count it (opened day); its time carries its date, and the page says it closed later.
HELD = dataclasses.replace(trip("h1", "2026-03-04", "15:10", "15:20", 500, "CE", 75),
                           exit_ts=datetime(2026, 3, 5, 9, 20, tzinfo=IST))
DAY_C_HELD = [RECORD[-2], RECORD[-1], HELD]


def test_a_trade_closed_on_a_later_day_carries_its_date_and_is_counted():
    view = mod("services.production.api.day_chart").view(need(mx, "day_path")(DAY_C_HELD))
    assert "finished <span class=\"num\">+₹200</span>" in str(view["said"])
    assert view.get("closed_later") == 1
    assert "5 Mar 09:20" in str(view["table"])
    assert "10:10" in str(view["table"])  # same-day closes keep a bare time


def test_a_day_with_no_late_close_says_nothing_about_it():
    view = mod("services.production.api.day_chart").view(need(mx, "day_path")(DAY_A))
    assert view.get("closed_later") == 0


def _opened_days(client) -> list[str]:
    """The demo's days, from the record itself: never from /numbers, whose links (since
    Your numbers counts the day a trade closed) open the closed-day list, not this page."""
    from services.production.db import models as m
    from services.production.db.session import make_session
    from services.production.mirror import loader
    with make_session(client.app.state.engine) as session:
        trips, _ = loader.load_for(session, session.query(m.Trader).one())
    return sorted({t.trading_day for t in trips})


def test_the_day_page_walks_from_the_first_day_to_the_last(demo):
    days = _opened_days(demo)
    assert len(days) >= 2
    first = demo.get(f"/mirror/day/{days[0]}").text
    last = demo.get(f"/mirror/day/{days[-1]}").text
    nav = lambda html: re.search(r'<p class="body-small day-nav".*?</p>', html, re.DOTALL).group(0)
    assert "‹" not in nav(first) and f'href="/mirror/day/{days[1]}"' in nav(first)
    assert "›" not in nav(last) and f'href="/mirror/day/{days[-2]}"' in nav(last)
    assert '<svg class="daychart' in first
