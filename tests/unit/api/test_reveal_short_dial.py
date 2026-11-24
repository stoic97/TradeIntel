"""On a record of fewer than five days the reveal's dial draws no share slice and no percentage.

Ruling (24 Nov 2026, under the founder's delegation): when the reveal shows every day he has, a
share of 100% is true by construction and states no fact (the sentence test, DECISIONS 7 Nov).
The dial keeps a centre figure, what those days came to, and its accessible label says it.

Made-up records, worked by hand:
  ONE   1 day:  2026-01-05 -600.                    Total -600.
  TWO   2 days: 2026-01-05 -600, 2026-01-06 -200.   Total -800.
  SIX   6 days: -500, -400, -300, -200, -100, -50.  Worst five -1,500 of losses -1,550: the share
        is shown as before.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.reveal_page import reveal


def t(day, net):
    entry = datetime.fromisoformat(f"{day}T10:00:00+05:30")
    return mx.Trip(
        f"{day}-x", "CRUDEOIL", day, entry, entry + timedelta(minutes=10), 600, Decimal(net), 1,
        s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True, lines=(),
    )


ONE = [t("2026-01-05", -600)]
TWO = [t("2026-01-05", -600), t("2026-01-06", -200)]
SIX = [t(f"2026-01-0{i + 5}", -100 * (5 - i)) for i in range(5)] + [t("2026-02-02", -50)]


def dial(trips) -> str:
    html = reveal(trips)
    m = re.search(r'<svg class="reveal__svg".*?</svg>', html, re.DOTALL)
    assert m, "the reveal draws its dial"
    return m.group(0)


@pytest.mark.parametrize("trips,total", [(ONE, "600"), (TWO, "800")], ids=["one day", "two days"])
def test_a_short_record_draws_no_share(trips, total):
    svg = dial(trips)
    assert "reveal__slice" not in svg
    assert "%" not in svg
    label = re.search(r'aria-label="([^"]*)"', svg).group(1)
    assert "slice" not in label and "%" not in label
    assert "came to" in label and total in label
    assert total in re.sub(r"<[^>]+>", "", svg), "the centre says what his days came to"


def test_six_days_keep_the_share_slice():
    svg = dial(SIX)
    assert "reveal__slice" in svg
    assert "%" in svg
    assert "as one slice of your whole result" in svg
