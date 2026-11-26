"""TICKET-1030: each chapter card and fact opens with its sharpest counted line.

Copy and order only: every figure here already exists on the page. Every record here is made up,
and the expected words are worked by hand in the comments.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from services.production.api import scope_facts as SF
from services.production.api.app import create_app
from services.production.db.session import make_engine, run_migrations
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.no_claims import CLAIM_PATTERNS, NEVER_USED
from tests.helpers.scope_chapters import IMP, chapter_page, readable, trips_from
from tests.helpers.scope_facts import fact_page
from tests.helpers.upload import CSRF, sign_up

D = Decimal


def at(day: int, hhmm: str, net: int, tid: str) -> mx.Trip:
    """A ten-minute trade on the given September day, opened at hh:mm India time."""
    entry = datetime.fromisoformat(f"2026-09-{day:02d}T{hhmm}:00+05:30")
    return mx.Trip(tid, "WIDGETOIL", entry.date().isoformat(), entry, entry + timedelta(minutes=10), 600,
                   D(net), 1, s.RiskUnitSourceV1.DECLARED_BUDGET)


# ---------- 1. Your wins and losses opens with the gap ----------
# 6 winners of 200 and 15 losers of 150: the average winner 200 is bigger than the loser 150.
# Win rate 6 / 21 = 28.57, "29 of 100". Break-even 150 / (200 + 150) = 42.86, "43 of 100".
# More winners needed: 43 - 29 = 14 in every 100.
GAP = trips_from([200] * 6 + [-150] * 15)


def test_the_gap_is_worked_from_the_pages_own_figures():
    figs = SF.facts(SF.record_context(GAP), IMP)
    gap = figs["math"].get("gap")
    assert gap, "no gap on the math fact"
    assert (gap["winner"], gap["loser"], gap["more"]) == (D(200), D(150), 14)


def test_wins_and_losses_opens_with_the_gap_on_its_card_and_page():
    line = ("Your winners are bigger than your losers (₹200 against ₹150). At this size you need 14 "
            "more winners in every 100 to break even.")
    assert line in readable(chapter_page(2, GAP))
    page = readable(fact_page("math", GAP))
    assert line in page
    assert page.index(line) < page.index("trades made money")


def test_no_gap_line_when_the_winner_is_not_bigger():
    small = trips_from([100] * 6 + [-150] * 15)  # winner 100 against loser 150
    assert SF.facts(SF.record_context(small), IMP)["math"].get("gap", "missing") is None
    assert "Your winners are bigger" not in readable(chapter_page(2, small))


# ---------- 2. The clock: the costliest hour, and the evening session rolled up ----------
# One book (WIDGETOIL options: a made-up Trip is an option by default). Hours, by the hour opened:
#   10:00  +100 (two trades, +60 and +40)
#   18:00  -300
#   20:00  -200
# Largest hour: 18:00, -300, a loss, so "costliest". All hours: -400. From 17:00 (MCX's evening
# session opens then, services/shared/market/series.EVENING_OPENS): -300 - 200 = -500.
CLOCK = [at(1, "10:05", 60, "a"), at(2, "10:10", 40, "b"), at(3, "18:05", -300, "c"),
         at(4, "20:05", -200, "d")]


def test_the_evening_session_is_a_sum_of_the_hour_rows():
    figs = SF.facts(SF.record_context(CLOCK), IMP)
    book = figs["clock"]["clocks"][0]
    assert book.get("costliest") is True
    assert book.get("evening"), "no evening roll-up"
    assert (book["evening"]["after"], book["evening"]["total"]) == (D(-500), D(-400))


def test_the_clock_says_costliest_hour_never_largest_result_for_a_loss():
    card = readable(chapter_page(2, CLOCK))
    assert "Costliest hour: −₹300 at 18:00" in card
    page = readable(fact_page("clock", CLOCK))
    assert "Your costliest hour: −₹300 at 18:00, in WIDGETOIL options." in page
    assert "The largest result in any one hour" not in page
    assert "WIDGETOIL options: trades opened from 17:00 came to −₹500, of −₹400 in all." in page


def test_a_book_with_no_evening_trades_has_no_evening_line():
    day_only = [at(1, "10:05", 60, "a"), at(2, "11:10", -40, "b")]
    book = SF.facts(SF.record_context(day_only), IMP)["clock"]["clocks"][0]
    assert book.get("evening", "missing") is None


# ---------- 4. The costliest run is drawn beside the longest ----------
# Losses: four of 10 in a row (the longest, -40), a win, then two of 500 (the costliest, -1,000).
RUNS = trips_from([-10, -10, -10, -10, 50, -500, -500, 50])


def test_the_costliest_run_is_drawn_when_it_is_not_the_longest():
    figs = SF.facts(SF.record_context(RUNS), IMP)
    assert figs["run"].get("costliest_timeline") is not None
    page = fact_page("run", RUNS)
    assert re.search(r'<details class="run__costliest"', page)
    assert "Your costliest run, drawn" in readable(page)


# ---------- 5. The busiest day's headline is trades, not a ratio ----------

def test_the_busiest_headline_is_trades_against_the_usual_day():
    many = [at(1, f"1{i}:05", 10, f"m{i}") for i in range(6)] + [at(d, "10:05", 10, f"o{d}") for d in (2, 3)]
    # Days: 1 Sep 6 trades, 2 Sep 1, 3 Sep 1. Normal day (median) 1. Busiest 6.
    figs = SF.facts(SF.record_context(many), IMP)
    assert str(figs["busiest"]["figure"]) == "6 trades, against your usual 1"


# ---------- 3, 6, 7 on the demo, through the app ----------

@pytest.fixture()
def client():
    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    c = sign_up(TestClient(create_app()), engine, "S-1", "stingreader")
    c.post("/upload/demo", data={"csrf_token": CSRF.search(c.get("/upload").text).group(1)}, follow_redirects=False)
    return c


def test_after_two_losses_leads_with_its_averages(client):
    page = readable(client.get("/mirror/fact/down").text)
    lead = re.search(r"After two straight losses you averaged [^.]*\.", page)
    assert lead, "no averages line"
    assert page.index(lead.group(0)) < page.index("No difference")


def test_the_hub_leads_chapter_one_with_the_worst_days_and_moves_the_bar_line(client):
    hub = readable(client.get("/mirror").text)
    # The demo's five worst days lost more than the rest moved: the line holds.
    assert re.search(r"Your five worst days: −₹[\d,]+\. Your other \d+ days: [+−]?₹[\d,]+\.", hub)
    assert "Every finding here clears a bar" not in hub
    told = readable(client.get("/mirror/fact/not-told").text)
    assert "Every finding here clears a bar" in told


def test_the_hidden_card_leads_with_a_count_not_its_scaffolding(client):
    chapter = readable(client.get("/mirror/chapter/1").text)
    assert "Plain counts, not a finding: each book" not in chapter


# ---------- 8. every new line passes the claims check ----------

def test_the_new_lines_make_no_claim(client):
    for path in ("/mirror", "/mirror/chapter/1", "/mirror/chapter/2", "/mirror/fact/down", "/mirror/fact/clock",
                 "/mirror/fact/run", "/mirror/fact/busiest"):
        # not-told names a cause and a cost only to say the report does neither; test_no_claims
        # exempts it by name, so it is read for the never-used words only, below.
        main = re.search(r"<main.*?</main>", client.get(path).text, re.DOTALL).group(0)
        text = re.sub(r"<[^>]+>", " ", main).lower()
        assert not [w for w in NEVER_USED if re.search(rf"\b{re.escape(w)}\b", text)], path
        assert not [p for p, _why in CLAIM_PATTERNS if re.search(p, text, re.IGNORECASE)], path
    told = re.sub(r"<[^>]+>", " ", client.get("/mirror/fact/not-told").text).lower()
    assert not [w for w in NEVER_USED if re.search(rf"\b{re.escape(w)}\b", told)]
