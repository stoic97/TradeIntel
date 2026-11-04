"""Worst days says what the five share, and Chapter 1 stops repeating itself [TICKET-817].

Every trade below is synthetic. The "in common" line follows the founder's ruling: only book,
hour of the first trade, number of trades and longest losing run; only when true of all five or
four of five; otherwise "They don't share a book, an hour or a size."

The main history, worked by hand. Quiet days are one trade of +10 in NIFTY at 09:20, so the
normal day is one trade:

    day          book    first   nets                     net    run
    2025-03-03   crude   18:05   -100 -100 -100 +10      -290      3
    2025-03-04   crude   18:30   -200 -100 +5            -295      2
    2025-03-05   crude   19:00   +20 -200 -200           -380      2
    2025-03-06   crude   17:10   -300 -200 +1            -499      2
    2025-03-07   NIFTY   09:20   -300 -300               -600      2

Other days: 2025-03-10 to 2025-03-19, eight trading days of +10, so +80 in all.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.production.mirror import feedback as FB
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_dates_with_year import FILE as UPLOAD_FILE
from tests.unit.api.test_scope_chapters import readable
from tests.unit.api.test_scope_facts import fact_page
from tests.unit.api.test_upload import CSRF, sign_up


def _day(day: str, at: str, nets: list[int], symbol: str = "CRUDEOIL", option=True) -> list[mx.Trip]:
    start = datetime.fromisoformat(f"{day}T{at}:00+05:30")
    return [
        mx.Trip(f"{day}-{n}", symbol, day, start + timedelta(minutes=10 * n),
                start + timedelta(minutes=10 * n + 5), 300, Decimal(net), 1,
                s.RiskUnitSourceV1.PREMIUM_PAID, is_option=option)
        for n, net in enumerate(nets)
    ]


QUIET = [t for d in ("10", "11", "12", "13", "14", "17", "18", "19")
         for t in _day(f"2025-03-{d}", "09:20", [10], "NIFTY")]

FOUR_CRUDE_EVENINGS = [
    *_day("2025-03-03", "18:05", [-100, -100, -100, 10]),
    *_day("2025-03-04", "18:30", [-200, -100, 5]),
    *_day("2025-03-05", "19:00", [20, -200, -200]),
    *_day("2025-03-06", "17:10", [-300, -200, 1]),
    *_day("2025-03-07", "09:20", [-300, -300], "NIFTY"),
    *QUIET,
]


def _in_common(trips: list[mx.Trip]) -> list[str]:
    return SF.worst_days_in_common(SF.record_context(trips))


# ---------- "In common", from the ruling's four things only ----------


def test_book_and_hour_on_the_same_four_days_read_as_one_sentence():
    assert _in_common(FOUR_CRUDE_EVENINGS)[0] == "4 of your 5 worst days were crude, after 5 pm."


def test_true_of_all_five_says_all_five():
    trips = [*_day("2025-03-03", "18:05", [-100, -100]), *_day("2025-03-04", "18:30", [-200, -100]),
             *_day("2025-03-05", "19:00", [-300, -100]), *_day("2025-03-06", "17:10", [-400, -100]),
             *_day("2025-03-07", "20:00", [-500, -100]), *QUIET]
    assert _in_common(trips)[0] == "All 5 of your worst days were crude, after 5 pm."


def test_book_and_hour_on_different_days_are_two_sentences():
    """Crude on the first four; after 5 pm on all but 3 Mar. Not the same four days."""
    trips = [*_day("2025-03-03", "09:20", [-100, 1]), *_day("2025-03-04", "18:30", [-200, 1]),
             *_day("2025-03-05", "19:00", [-300, 1]), *_day("2025-03-06", "17:10", [-400, 1]),
             *_day("2025-03-07", "18:00", [-500, 1], "NIFTY"), *QUIET]
    lines = _in_common(trips)
    assert "4 of your 5 worst days were crude." in lines
    assert "4 of your 5 worst days began after 5 pm." in lines


def test_the_number_of_trades_is_against_the_normal_day():
    assert ("All 5 of your worst days had more trades than your normal day of 1."
            in _in_common(FOUR_CRUDE_EVENINGS))


def test_the_longest_losing_run_is_the_most_all_of_them_reached():
    """The five runs are 3, 2, 2, 2, 2. All five reached 2, so that's what can be said."""
    assert ("All 5 of your worst days had at least 2 losses in a row."
            in _in_common(FOUR_CRUDE_EVENINGS))


def test_a_run_shared_by_four_uses_the_most_those_four_reached():
    trips = [*_day("2025-03-03", "09:20", [-100, -100, -100, 1], "A"),
             *_day("2025-03-04", "11:00", [-200, -100, -100, 1], "B"),
             *_day("2025-03-05", "13:00", [-300, -100, -100, 1], "C"),
             *_day("2025-03-06", "18:00", [-400, -100, -100, 1], "D"),
             *_day("2025-03-07", "19:00", [-900, 1, 1, 1], "E"), *QUIET]
    assert "4 of your 5 worst days had at least 3 losses in a row." in _in_common(trips)


def test_one_loss_is_not_a_run():
    trips = [*_day("2025-03-03", "09:20", [-100, 1], "A"), *_day("2025-03-04", "11:00", [-200, 1], "B"),
             *_day("2025-03-05", "13:00", [-300, 1], "C"), *_day("2025-03-06", "18:00", [-400, 1], "D"),
             *_day("2025-03-07", "19:00", [-500, 1], "E"), *QUIET]
    assert not [line for line in _in_common(trips) if "in a row" in line]


def test_a_day_of_two_books_counts_for_the_one_with_more_trades():
    """Crude on 3 Mar has one NIFTY trade beside three crude ones: it's a crude day."""
    trips = [*_day("2025-03-03", "18:05", [-100, -100, -100]),
             *_day("2025-03-03", "20:00", [1], "NIFTY"),
             *_day("2025-03-04", "18:30", [-200, 1]), *_day("2025-03-05", "19:00", [-300, 1]),
             *_day("2025-03-06", "17:10", [-400, 1]), *_day("2025-03-07", "09:20", [-500, 1], "NIFTY"),
             *QUIET]
    assert _in_common(trips)[0] == "4 of your 5 worst days were crude, after 5 pm."


def test_nothing_shared_says_so_in_the_founders_words():
    """Five books, three parts of the day split 2/2/1, one trade each like the normal day."""
    trips = [*_day("2025-03-03", "09:20", [-100], "A"), *_day("2025-03-04", "09:30", [-200], "B"),
             *_day("2025-03-05", "13:00", [-300], "C"), *_day("2025-03-06", "14:00", [-400], "D"),
             *_day("2025-03-07", "18:00", [-500], "E"), *QUIET]
    assert _in_common(trips) == []
    assert "They don't share a book, an hour or a size." in readable(fact_page("worst-days", trips))


def test_fewer_than_five_worst_days_claims_nothing_in_common():
    assert _in_common(_day("2025-03-03", "18:05", [-100, -100])) == []


def test_the_line_never_says_pattern_or_tendency():
    page = readable(fact_page("worst-days", FOUR_CRUDE_EVENINGS)).lower()
    for word in ("pattern", "tendency", "you tend to", "didn't stop"):
        assert word not in page


# ---------- The page leads with that, not the total ----------


def test_the_page_leads_with_what_they_share():
    page = readable(fact_page("worst-days", FOUR_CRUDE_EVENINGS))
    shared = page.index("4 of your 5 worst days were crude, after 5 pm.")
    assert shared < page.index("Your five worst days: −₹2,064")


def test_the_share_facts_one_new_row_is_one_line_here():
    """Worst five: 290 + 295 + 380 + 499 + 600 = 2,064. The other days made +80."""
    page = readable(fact_page("worst-days", FOUR_CRUDE_EVENINGS))
    assert "Your five worst days: −₹2,064. Your other 8 days: +₹80." in page


def test_nothing_shared_leads_with_the_rupees():
    trips = [*_day("2025-03-03", "09:20", [-100], "A"), *_day("2025-03-04", "09:30", [-200], "B"),
             *_day("2025-03-05", "13:00", [-300], "C"), *_day("2025-03-06", "14:00", [-400], "D"),
             *_day("2025-03-07", "18:00", [-500], "E"), *QUIET]
    html = fact_page("worst-days", trips)
    assert html.index("num--hero") < html.index("They don't share a book")


def test_the_page_no_longer_draws_the_daily_bars_or_the_table():
    html = fact_page("worst-days", FOUR_CRUDE_EVENINGS)
    assert "one bar per trading day" not in html
    assert "Net (gross)" not in readable(html)
    assert "vs your normal day" not in readable(html)


def test_the_normal_day_comparison_says_it_is_trades():
    """28 Feb style: 4 trades against a normal day of 1 is 4×, and it says of what."""
    assert "4× your normal day's trades" in readable(fact_page("worst-days", FOUR_CRUDE_EVENINGS))


# ---------- One block per day ----------


def _block(key: str) -> mx.DayBlock:
    blocks = mx.worst_day_blocks(FOUR_CRUDE_EVENINGS)
    return next(b for b in blocks if b.trading_day == key)


def test_there_is_a_block_for_each_of_the_five_worst_days_worst_first():
    days = [b.trading_day for b in mx.worst_day_blocks(FOUR_CRUDE_EVENINGS)]
    assert days == ["2025-03-07", "2025-03-06", "2025-03-05", "2025-03-04", "2025-03-03"]


def test_a_block_has_the_running_result_from_first_trade_to_last():
    assert _block("2025-03-03").running == (Decimal(-100), Decimal(-200), Decimal(-300), Decimal(-290))


def test_a_block_counts_what_came_after_the_first_trade():
    block = _block("2025-03-03")
    assert (block.first_net, block.later, block.later_lost) == (Decimal(-100), 3, 2)


def test_a_block_is_collapsed_and_opens_on_its_trades():
    html = fact_page("worst-days", FOUR_CRUDE_EVENINGS)
    assert html.count('<details class="day-block"') == 5
    assert not re.search(r'<details class="day-block"[^>]*\bopen\b', html)
    first = re.search(r'<details class="day-block".*?</details>', html, flags=re.DOTALL).group(0)
    assert first.index("</summary>") < first.index('class="trades"'), "the list opens on tap"


@pytest.mark.parametrize("words", [
    "07 Mar 2025", "NIFTY", "2 trades", "09:20 to 09:35", "−₹600",
    "First trade −₹300, then 1 more; 1 lost.",
])
def test_a_block_says_the_day_at_a_glance(words):
    summary = re.search(r"<summary.*?</summary>", fact_page("worst-days", FOUR_CRUDE_EVENINGS),
                        flags=re.DOTALL).group(0)
    assert words in readable(summary)


def test_a_block_draws_its_running_result():
    summary = re.search(r"<summary.*?</summary>", fact_page("worst-days", FOUR_CRUDE_EVENINGS),
                        flags=re.DOTALL).group(0)
    assert '<svg class="day-block__line"' in summary and "<polyline" in summary


def test_a_one_trade_day_reads_in_the_singular():
    trips = [*_day("2025-03-03", "09:20", [-100], "A"), *_day("2025-03-04", "09:30", [-200, 1], "B"),
             *_day("2025-03-05", "13:00", [-300, 1], "C"), *_day("2025-03-06", "14:00", [-400, 1], "D"),
             *_day("2025-03-07", "18:00", [-500, 1], "E"), *QUIET]
    assert "One trade: −₹100." in readable(fact_page("worst-days", trips))


def test_a_trade_held_past_the_day_says_so_in_the_span():
    trips = list(FOUR_CRUDE_EVENINGS)
    held = _day("2025-03-07", "09:20", [-300, -300], "NIFTY")[1]
    trips[trips.index(next(t for t in trips if t.trip_id == held.trip_id))] = mx.Trip(
        held.trip_id, held.symbol, held.trading_day, held.entry_ts,
        held.entry_ts + timedelta(days=3), 259200, held.net, 1, held.risk_unit_source)
    assert "09:20, last trade closed 10 Mar 2025" in readable(fact_page("worst-days", trips))


def test_each_block_asks_is_this_day_wrong():
    html = fact_page("worst-days", FOUR_CRUDE_EVENINGS)
    assert html.count("Is this day wrong?") == 5
    assert html.count('action="/mirror/feedback/day"') == 5


def test_the_next_button_shows_after_the_blocks_and_again_at_the_bottom():
    html = fact_page("worst-days", FOUR_CRUDE_EVENINGS)
    label = "Your 5 best and 5 worst trades"
    assert html.count(label) == 2
    assert html.rindex("</details>") < html.index(label)
    assert 'href="/mirror/fact/money"' in html


def test_every_trade_stays_within_reach():
    page = fact_page("worst-days", FOUR_CRUDE_EVENINGS)
    assert 'href="/mirror/fact/worst-days/trades"' in page


# ---------- Chapter 1 has two facts ----------


def test_chapter_one_has_two_facts():
    assert [f.key for f in S.chapter(1).facts] == ["worst-days", "money"]


def test_the_dial_says_findings_not_counts():
    ctx = SF.record_context(FOUR_CRUDE_EVENINGS)
    items = SF.chapter_view(1, SF.facts(ctx, _imp()))["items"]
    assert [i["figure"] for i in items] == ["5 days: −₹2,064", "Best trade +₹20"]


def _imp():
    from tests.unit.api.test_scope_chapters import IMP

    return IMP


# ---------- Through the app ----------


@pytest.fixture()
def client(scope_environment):
    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    signed_in = sign_up(TestClient(create_app()), engine, "WORST", "worst")
    token = CSRF.search(signed_in.get("/upload").text).group(1)
    sent = signed_in.post("/upload", files={"file": ("t.csv", UPLOAD_FILE.encode(), "text/csv")},
                          data={"csrf_token": token}, follow_redirects=False)
    assert sent.status_code == 303, sent.text
    signed_in.engine_for_test = engine
    return signed_in


def _flag(client, day: str, note: str = "It was a spread.", **more):
    html = client.get("/mirror/fact/worst-days").text
    return client.post("/mirror/feedback/day", data={
        "trading_day": day, "note": note, "csrf_token": CSRF.search(html).group(1), **more,
    }, follow_redirects=False)


def _a_worst_day(client) -> str:
    html = client.get("/mirror/fact/worst-days").text
    return re.search(r'name="trading_day" value="([\d-]+)"', html).group(1)


def test_the_share_page_goes_to_worst_days(client):
    gone = client.get("/mirror/fact/share", follow_redirects=False)
    assert gone.status_code == 303
    assert gone.headers["location"].startswith("/mirror/fact/worst-days")


def test_the_chapter_page_leads_on_to_chapter_two(client):
    html = client.get("/mirror/chapter/1").text
    assert "Chapter 2: your patterns" in readable(html)
    assert 'href="/mirror/chapter/2' in html


def test_a_flag_is_kept_with_its_day_and_note(client):
    day = _a_worst_day(client)
    assert _flag(client, day).status_code == 303
    with make_session(client.engine_for_test) as sess:
        row = sess.scalars(select(m.ReportFeedback)).one()
        assert (row.trading_day, row.answer, row.note) == (day, "wrong", "It was a spread.")


def test_a_flagged_day_says_so_and_stops_asking(client):
    day = _a_worst_day(client)
    _flag(client, day)
    html = client.get("/mirror/fact/worst-days").text
    assert "You told us this day looks wrong." in readable(html)
    assert html.count("Is this day wrong?") == 4


def test_a_second_flag_changes_nothing(client):
    day = _a_worst_day(client)
    _flag(client, day)
    _flag(client, day, note="Changed my mind.")
    with make_session(client.engine_for_test) as sess:
        assert sess.scalars(select(m.ReportFeedback)).one().note == "It was a spread."


def test_a_flag_on_a_day_not_on_the_list_is_refused(client):
    assert _flag(client, "2020-01-01").status_code == 400


def test_a_flag_needs_its_csrf_token(client):
    assert client.post("/mirror/feedback/day", data={"trading_day": "2024-06-14"},
                       follow_redirects=False).status_code == 403


def test_a_day_flag_does_not_use_up_the_reports_own_question(client):
    _flag(client, _a_worst_day(client))
    with make_session(client.engine_for_test) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        imp = sess.scalars(select(m.Import)).one()
        assert FB.report_answer(sess, trader, imp.id) is None
