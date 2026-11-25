"""TICKET-1053: the Eligibility page says why its after-two-straight-losses count can differ.

Ruling A, 24 Nov: Eligibility counts every round trip; chapter 3 counts same-day trades. The
two stay different, so when they differ on a trader's file the page says why, in one line beside
the count. When they are equal the line is not drawn. Every trade here is made up.

  differs: l1 -100 and l2 -100 close on 01 Sep, then h1 opens 10:20 and is held to 02 Sep.
           Every trade: h1 follows two closed losses = 1. Same-day trades only: h1 is out = 0.
  equal:   the same two losses, then s3 opens 10:20 and closes 10:30 on 01 Sep: 1 and 1.
"""

from __future__ import annotations

import re

from tests.helpers.eligibility_page import eligibility_page_client, eligibility_page_engine

LINE = ("This page counts every trade. Your report counts same-day trades, so the two can "
        "differ when a position was held past the day.")


def _row(tid, entry, exit_, net):
    return {"trip_id": tid, "trading_day": entry[:10], "exchange": "MCX", "symbol": "WIDGETOIL",
            "entry_ts": f"{entry}:00+05:30", "exit_ts": f"{exit_}:00+05:30", "quantity": 100,
            "gross": str(net), "fees": "0", "net": str(net), "risk_unit_source": "declared_budget"}


LOSSES = [_row("l1", "2026-09-01T09:30", "2026-09-01T09:40", -100),
          _row("l2", "2026-09-01T10:00", "2026-09-01T10:10", -100)]
DIFFERS = LOSSES + [_row("h1", "2026-09-01T10:20", "2026-09-02T10:00", 50)]
EQUAL = LOSSES + [_row("s3", "2026-09-01T10:20", "2026-09-01T10:30", 50)]


def _text(rows):
    client = eligibility_page_client(eligibility_page_engine(), rows)
    page = client.get("/eligibility")
    assert page.status_code == 200
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page.text))


def test_the_line_is_on_the_page_when_the_two_counts_differ():
    text = _text(DIFFERS)
    assert "1 trades meet the condition" in text  # every trade: h1
    assert LINE in text


def test_the_line_is_not_on_the_page_when_the_two_counts_are_equal():
    text = _text(EQUAL)
    assert "1 trades meet the condition" in text  # every trade: s3; same-day: s3
    assert LINE not in text
    assert "held past the day" not in text
