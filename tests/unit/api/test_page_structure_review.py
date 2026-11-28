"""TICKET-1029 review (24 Nov): the filter sentence in the ruled words, and true while a book stays
chosen; the hidden page folds a book by its count (under 30 same-day trades), not by whether its
halves could be compared.

Made-up records: WIDGETOIL books of 29 and 30 trades on separate days; 30 trades all on one day.
"""
from __future__ import annotations

import dataclasses
import re
from datetime import timedelta

from services.production.api import report_filter as RF
from services.production.mirror import metrics as mx
from tests.helpers.scope_chapters import trips_from
from tests.helpers.scope_facts import fact_page

RULED = "Your last upload added no new days, so this shows everything."


def test_the_since_sentence_is_the_ruled_one():
    asked, got = RF.ReportFilter(RF.SINCE), RF.ReportFilter(RF.ALL)
    assert RF.dropped(asked, got) == RULED


def test_with_a_book_still_chosen_the_sentence_does_not_say_everything():
    asked, got = RF.ReportFilter(RF.SINCE, "Crude options"), RF.ReportFilter(RF.ALL, "Crude options")
    said = RF.dropped(asked, got)
    assert said.startswith("Your last upload added no new days") and "everything" not in said
    assert "Crude options" in said


def test_an_upload_that_added_no_new_days_drops_the_period_too():
    trips = trips_from([100, -50])
    assert RF.valid(RF.ReportFilter(RF.SINCE), trips, set()).period == RF.ALL


def book(n: int, symbol: str, one_day: bool = False) -> list[mx.Trip]:
    out = []
    for i, t in enumerate(trips_from([100 if k % 3 else -80 for k in range(n)])):
        t = dataclasses.replace(t, trip_id=f"{symbol}{i}", symbol=symbol)
        if one_day:
            first = trips_from([1])[0]
            entry = first.entry_ts + timedelta(minutes=i)
            t = dataclasses.replace(t, trading_day=first.trading_day, entry_ts=entry,
                                    exit_ts=entry + timedelta(minutes=1))
        out.append(t)
    return out


def fold_of(page: str) -> str:
    found = re.search(r'<details class="books-fold">(.*?)</details>', page, re.DOTALL)
    return found.group(1) if found else ""


def test_twenty_nine_trades_fold_and_thirty_do_not():
    small, big = book(29, "WIDGETOIL"), book(30, "GADGETCO")
    fold = fold_of(fact_page("hidden", small + big))
    assert mx.trade_book(small[0]) in fold and mx.trade_book(big[0]) not in fold


def test_thirty_trades_on_one_day_are_not_folded_under_a_row_that_says_under_thirty():
    # a counted book of 40 over 40 days, so the page draws its books and not the empty state
    one_day, small, counted = book(30, "GADGETCO", one_day=True), book(3, "WIDGETOIL"), book(40, "BOLTCORP")
    page = fact_page("hidden", one_day + small + counted)
    fold = fold_of(page)
    assert mx.trade_book(one_day[0]) not in fold and mx.trade_book(small[0]) in fold
    assert mx.trade_book(one_day[0]) in page
