"""The reveal names its five days and says what they share [TICKET-816].

Worked by hand. Five worst days, worst first:
  2026-01-05  NIFTY +100 at 09:15, then crude -600, -400           -900  3 trades  first won
  2025-02-06  crude -200 at 18:00, then crude -300 at 21:30        -500  2 trades  first lost
  2024-04-08  crude -400 alone                                     -400  1 trade
  2024-05-09  crude -150, then a share -150 at 21:05               -300  2 trades  first lost
  2025-03-07  crude -100, then NIFTY +50                            -50  2 trades  first lost
Plus two winning days. The first trade lost and the rest also lost on 2 days (06 Feb, 09 May):
300 + 150 = 450 more. 07 Mar's rest made money, and 08 Apr has no rest. All five hold crude.
06 Feb and 09 May have a trade opened after 9 pm.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_reveal_page import reveal
from tests.unit.api.test_scope_chapters import readable


def t(day, at, net, symbol="CRUDEOIL", is_option=True):
    entry = datetime.fromisoformat(f"{day}T{at}:00+05:30")
    return mx.Trip(
        f"{day}-{at}", symbol, day, entry, entry + timedelta(minutes=10), 600, Decimal(net), 1,
        s.RiskUnitSourceV1.PREMIUM_PAID, is_option=is_option,
    )


TRIPS = [
    t("2026-01-05", "09:15", 100, "NIFTY"), t("2026-01-05", "10:00", -600), t("2026-01-05", "11:00", -400),
    t("2025-02-06", "18:00", -200), t("2025-02-06", "21:30", -300),
    t("2024-04-08", "19:00", -400),
    t("2024-05-09", "18:00", -150), t("2024-05-09", "21:05", -150, "Shree Cement", is_option=False),
    t("2025-03-07", "18:00", -100), t("2025-03-07", "19:00", 50, "NIFTY"),
    t("2025-06-02", "10:00", 900), t("2025-06-03", "10:00", 700),
]


def read():
    return mx.five_days_read(TRIPS)


def test_the_days_come_worst_first_with_their_books():
    assert [(r.trading_day, r.books, r.trades, r.net) for r in read().rows] == [
        ("2026-01-05", ("NIFTY", "crude"), 3, Decimal(-900)),
        ("2025-02-06", ("crude",), 2, Decimal(-500)),
        ("2024-04-08", ("crude",), 1, Decimal(-400)),
        ("2024-05-09", ("crude", "equity"), 2, Decimal(-300)),
        ("2025-03-07", ("crude", "NIFTY"), 2, Decimal(-50)),
    ]


def test_it_counts_the_days_a_lost_first_trade_was_followed_by_more_loss():
    assert (read().first_lost_days, read().lost_after_first) == (2, Decimal(450))


def test_it_names_a_book_every_day_holds():
    assert read().shared_book == "crude"


def test_it_names_no_book_when_a_day_lacks_it():
    without = [x for x in TRIPS if x.trading_day != "2024-04-08"] + [t("2024-04-08", "19:00", -400, "NIFTY")]
    assert mx.five_days_read(without).shared_book is None


def test_it_counts_the_days_with_a_trade_opened_after_nine():
    assert read().past_nine == 2


def test_the_worst_day_is_told_from_its_first_trade():
    story = read().story
    assert (story.trading_day, story.first_net, story.later, story.net) == (
        "2026-01-05", Decimal(100), 2, Decimal(-900),
    )


def test_a_single_trade_day_has_no_story():
    assert mx.five_days_read([t("2026-01-05", "10:00", -500)]).story is None


def test_a_day_that_finished_up_has_no_story():
    """Five worst days can still be winning days on a short history."""
    assert mx.five_days_read([t("2026-01-05", "10:00", 500), t("2026-01-05", "11:00", 100)]).story is None


def test_no_history_has_no_read():
    assert mx.five_days_read([]) is None


def page():
    return readable(reveal(TRIPS))


def test_the_page_has_the_heading():
    assert "<h1" in reveal(TRIPS) and "Your five worst days" in page()


def test_the_days_are_on_the_page_with_their_year():
    assert "05 Jan 2026 NIFTY, crude 3 trades −₹900" in page()
    assert "08 Apr 2024 crude 1 trade −₹400" in page()
    assert "09 May 2024 crude, equity 2 trades −₹300" in page()


def test_the_days_show_above_the_buttons():
    html = reveal(TRIPS)
    assert html.index("05 Jan 2026") < html.index("Show me those days")


def test_the_page_tells_the_worst_day():
    assert "05 Jan 2026: your first trade made ₹100. 2 trades later you were down ₹900." in page()


def test_a_first_trade_that_lost_reads_that_way():
    trips = [t("2026-01-05", "10:00", -100), t("2026-01-05", "11:00", -200)]
    assert "your first trade lost ₹100. 1 trade later you were down ₹300." in readable(reveal(trips))


def test_the_page_says_what_they_share():
    assert "On 2 of these days your first trade lost and you kept going: ₹450 more was lost after it." in page()
    assert "Every one of the five includes crude, and 2 ran past 9 pm." in page()


def test_one_day_reads_in_the_singular():
    trips = [t("2026-01-05", "10:00", -100), t("2026-01-05", "11:00", -200)]
    assert "On 1 of these days your first trade lost" in readable(reveal(trips))


def test_the_button_says_where_it_goes():
    assert '<a class="btn btn--text-on-navy" href="/budget">Next: what you risk</a>' in reveal(TRIPS)
    assert ">Continue<" not in reveal(TRIPS)


def test_a_share_that_is_not_a_percentage_still_names_the_days():
    trips = [t(f"2026-01-0{i}", "10:00", 100 * i) for i in range(1, 8)]
    assert "01 Jan 2026" in readable(reveal(trips))
