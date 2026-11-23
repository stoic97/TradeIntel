"""TICKET-1032: Your wins and losses, the gap to break-even as a bar, and each book's win rate
against break-even, year by year.

Every trade here is made up, and every expected figure is worked by hand below. Same-day trades
only, as the math page reads them (math_by_book).
"""
from __future__ import annotations

import importlib
import importlib.util
import re
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from services.production.api.app import create_app
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def wg():
    name = "services.production.api.wins_gap"
    assert importlib.util.find_spec(name), "no services/production/api/wins_gap.py"
    return importlib.import_module(name)


_n = 0


def trades(symbol: str, year: int, wins: int, win_net: int, losses: int, loss_net: int) -> list[mx.Trip]:
    """wins at +win_net and losses at -loss_net, each opened and closed the same day."""
    global _n
    out = []
    for i, net in enumerate([win_net] * wins + [-loss_net] * losses):
        _n += 1
        entry = datetime(year, 3, 2, 10, 0, tzinfo=IST) + timedelta(days=i)
        out.append(mx.Trip(trip_id=f"t{_n}", symbol=symbol, trading_day=entry.date().isoformat(),
                           entry_ts=entry, exit_ts=entry + timedelta(minutes=10), holding_seconds=600,
                           net=D(net), lots=1, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID,
                           is_option=True))
    return out


# NIFTY options, 90 trades:
#   2024  16 wins of +300, 24 losses of -150: win 40.0; break-even 150 / (300 + 150) = 33.3
#   2025  12 wins of +200, 28 losses of -200: win 30.0; break-even 200 / 400 = 50.0
#   2026  5 wins of +100, 5 losses of -100: 10 trades, under 30: too few
#   whole 33 wins, 57 losses: win 33/90 = 36.7 -> 37 of 100;
#         average winner 7,700/33 = 233.33, average loser 9,700/57 = 170.18;
#         break-even 170.18 / 403.51 = 42.2 -> 42 of 100. Gap 42 - 37 = 5 more winners in every 100.
# Crude options, 60 trades:
#   2024  15 wins of +100, 15 losses of -100: win 50.0; break-even 50.0: at break-even
#   2025  12 wins of +300, 18 losses of -100: win 40.0; break-even 100 / 400 = 25.0
#   whole 27 wins, 33 losses: win 45.0 -> 45 of 100; average winner 5,100/27 = 188.89,
#         average loser 100; break-even 100 / 288.89 = 34.6 -> 35 of 100: 10 of 100 above it.
RECORD = (trades("NIFTY", 2024, 16, 300, 24, 150) + trades("NIFTY", 2025, 12, 200, 28, 200)
          + trades("NIFTY", 2026, 5, 100, 5, 100)
          + trades("CRUDEOIL", 2024, 15, 100, 15, 100) + trades("CRUDEOIL", 2025, 12, 300, 18, 100))


def view():
    return wg().view(mx.math_by_book(RECORD))


def bar(book):
    return next(b for b in view()["bars"] if b["book"] == book)


def plain(markup) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(markup))).strip()


# ---------- 1. the gap bar ----------

def test_one_bar_per_book_with_thirty_same_day_trades():
    assert [b["book"] for b in view()["bars"]] == ["NIFTY options", "Crude options"]


def test_the_bar_says_the_rate_what_it_needs_and_the_gap_in_counts():
    nifty, crude = bar("NIFTY options"), bar("Crude options")
    assert plain(nifty["line"]) == "37 of 100 · needs 42 of 100 · 5 more winners in every 100"
    assert plain(crude["line"]) == "45 of 100 · needs 35 of 100 · 10 of 100 above break-even"


def test_the_gap_is_break_even_minus_the_win_rate_as_shown():
    nifty = bar("NIFTY options")
    assert (nifty["win"], nifty["need"], nifty["gap"]) == (37, 42, 5)
    assert bar("Crude options")["gap"] == -10


def test_the_bar_marks_both_rates_and_shades_the_gap():
    svg = str(bar("NIFTY options")["svg"])
    assert 'class="wg-win"' in svg and 'class="wg-need"' in svg and "wg-gap" in svg
    assert 'viewBox="0 0 358' in svg and "<script" not in svg


def test_a_book_at_break_even_says_so():
    at_par = wg().view(mx.math_by_book(trades("CRUDEOIL", 2024, 15, 100, 15, 100)))
    assert plain(at_par["bars"][0]["line"]) == "50 of 100 · needs 50 of 100 · at break-even"


# ---------- 2. by year ----------

def test_each_book_draws_its_years_with_thirty_or_more():
    years = {b["book"]: b for b in view()["years"]}
    assert [p["year"] for p in years["NIFTY options"]["points"]] == ["2024", "2025"]
    assert [(p["win"], p["need"]) for p in years["NIFTY options"]["points"]] == [(40, 33), (30, 50)]
    assert [(p["win"], p["need"]) for p in years["Crude options"]["points"]] == [(50, 50), (40, 25)]


def test_a_thin_year_shows_its_count_and_too_few():
    nifty = next(b for b in view()["years"] if b["book"] == "NIFTY options")
    assert plain(nifty["thin"]) == "2026: 10 trades, too few"


def test_every_book_shares_one_scale():
    v = view()
    assert (v["lo"], v["hi"]) == (25, 50)
    svgs = [str(b["svg"]) for b in v["years"]]
    assert all("wg-you" in s and "wg-even" in s for s in svgs)


# ---------- 3, 4. the text, the words ----------

def test_a_text_table_carries_every_figure_in_of_100():
    table = plain(view()["table"])
    assert "NIFTY options 2024 40 trades 40 of 100 33 of 100" in table
    assert "NIFTY options 2026 10 trades too few" in table


def test_no_adjective_and_no_percent_sign():
    words = " ".join(plain(b["line"]) for b in view()["bars"]).lower()
    for w in ("improv", "worse", "better", "good", "bad"):
        assert w not in words
    assert "%" not in plain(view()["table"])


# ---------- on the page ----------

@pytest.fixture()
def demo(engine):
    client = sign_up(TestClient(create_app()), engine, "W-1", "visitor")
    client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
    return client


def test_the_math_page_carries_both_charts_with_no_script(demo):
    html = demo.get("/mirror/fact/math").text
    found = re.search(r'<section class="wins-gap".*?</section>', html, re.DOTALL)
    assert found, "no wins-gap section on the math page"
    section = found.group(0)
    assert "needs" in plain(section) and "<script" not in section
    assert html.index('class="wins-gap"') < html.index("How long you hold")
