"""TICKET-1090: a short record is never told "five worst days"; every page counts them one way.

The report's wording for the worst days counted is worst_count: "five" at five, the counted
figure below five ("Your 2 worst days"). The Home and Journal flag, the upload re-read row and
the reveal all say it. Records worked by hand, one trip a day, all losing:
  ONE    1 day:  -600.
  TWO    2 days: -600, -200.
  FOUR   4 days: -400, -300, -200, -100.
  FIVE   5 days: -500, -400, -300, -200, -100.
  SEVEN  7 days: the five above plus +900 and +700; the worst five are the losing ones.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from services.production.api import days_worth_a_look as worth
from services.production.api import routes_upload as up
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.reveal_page import reveal
from tests.helpers.scope_chapters import readable


def t(day, net):
    entry = datetime.fromisoformat(f"{day}T10:00:00+05:30")
    return mx.Trip(
        f"{day}-x", "CRUDEOIL", day, entry, entry + timedelta(minutes=10), 600, Decimal(net), 1,
        s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True, lines=(),
    )


ONE = [t("2026-01-05", -600)]
TWO = [t("2026-01-05", -600), t("2026-01-06", -200)]
FOUR = [t(f"2026-01-0{i + 5}", -100 * (4 - i)) for i in range(4)]
FIVE = [t(f"2026-01-0{i + 5}", -100 * (5 - i)) for i in range(5)]
SEVEN = FIVE + [t("2026-02-02", 900), t("2026-02-03", 700)]

SHORT = [(ONE, "1"), (TWO, "2"), (FOUR, "4")]


def flag_labels(trips):
    return [f.label for flags in worth.flags_by_day(trips).values() for f in flags
            if "worst" in f.label]


def row_labels(trips):
    return [label for label in up._headline_figures(trips) if "worst" in label]


@pytest.mark.parametrize("trips,n", SHORT, ids=["one", "two", "four"])
def test_a_short_record_flag_never_says_five(trips, n):
    labels = flag_labels(trips)
    assert labels, "a losing day in a short record is still one of its worst days"
    for label in labels:
        assert "five" not in label.lower()
        assert f"your {n} worst day" in label


def test_flag_wording_for_one_and_two_days():
    assert flag_labels(ONE) == ["This was your 1 worst day"]
    assert set(flag_labels(TWO)) == {"This was one of your 2 worst days"}


@pytest.mark.parametrize("trips", [FIVE, SEVEN], ids=["exactly five", "more than five"])
def test_five_or_more_flag_says_five(trips):
    labels = flag_labels(trips)
    assert len(labels) == 5
    assert set(labels) == {"This was one of your five worst days"}


@pytest.mark.parametrize("trips,n", SHORT, ids=["one", "two", "four"])
def test_a_short_record_row_is_labelled_with_the_real_count(trips, n):
    (label,) = row_labels(trips)
    assert "five" not in label.lower()
    assert label == f"Your {n} worst day" + ("" if n == "1" else "s")


@pytest.mark.parametrize("trips", [FIVE, SEVEN], ids=["exactly five", "more than five"])
def test_five_or_more_row_says_five(trips):
    assert row_labels(trips) == ["Your five worst days"]


def test_the_reveal_says_it_the_way_the_report_does():
    two = readable(reveal(TWO))
    assert "five" not in two.lower()
    assert "Your 2 worst days" in two
    assert "Those 2 days came to" in two
    assert "your two" not in two.lower()
    one = readable(reveal(ONE))
    assert "five" not in one.lower()
    assert "Your 1 worst day" in one
    assert "That day came to" in one


@pytest.mark.parametrize("trips", [FIVE, SEVEN], ids=["exactly five", "more than five"])
def test_the_reveal_at_five_or_more_reads_as_before(trips):
    text = readable(reveal(trips))
    assert "Your five worst days" in text


def test_every_page_says_the_same_words_for_two_days():
    reveal_text = readable(reveal(TWO))
    (row,) = row_labels(TWO)
    assert row in reveal_text, "the upload row and the reveal title are one wording"
    assert all(row.lower() in label.lower() for label in flag_labels(TWO)), "and the flag too"


def test_no_counted_days_never_reaches_the_reveal(client, monkeypatch):
    from services.production.api import routes_mirror
    monkeypatch.setattr(routes_mirror.loader, "load_for", lambda *a, **k: ([], None))
    r = client.get("/mirror/reveal", follow_redirects=True)
    text = r.text.lower()
    assert "zero" not in text
    assert "worst days" not in text and "worst day" not in text
