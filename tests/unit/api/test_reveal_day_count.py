"""The reveal never says "five" about days he does not have; the count comes from his file.

Three made-up records, worked by hand:
  TWO     2 traded days: 2026-01-05 -600 and 2026-01-06 -200. Both are his "worst"; 2 days.
  FIVE    5 traded days: -500, -400, -300, -200, -100. Exactly five.
  SEVEN   7 traded days: the five above plus +900 and +700. The worst five are the losing ones.
Each is rendered and read as text.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from services.production.api import scope_facts as SF
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


TWO = [t("2026-01-05", -600), t("2026-01-06", -200)]
FIVE = [t(f"2026-01-0{i + 5}", -100 * (5 - i)) for i in range(5)]
SEVEN = FIVE + [t("2026-02-02", 900), t("2026-02-03", 700)]


def page(trips):
    return readable(reveal(trips))


def test_two_days_never_say_five():
    text = page(TWO)
    assert "five" not in text.lower()
    assert "Your two trading days" in text
    assert "Those two days came to" in text


def test_the_title_comes_from_his_file():
    assert hasattr(SF, "reveal_days"), "the count is decided in one place, from his file"
    assert SF.reveal_days(SF.record_context(TWO))["title"] == "Your two trading days"
    assert SF.reveal_days(SF.record_context(FIVE))["title"] == "Your five worst days"
    assert SF.reveal_days(SF.record_context(SEVEN))["title"] == "Your five worst days"


def test_one_day_says_that_day():
    text = page([t("2026-01-05", -600)])
    assert "five" not in text.lower()
    assert "Your only trading day" in text
    assert "That day came to" in text


@pytest.mark.parametrize("trips", [FIVE, SEVEN], ids=["exactly five", "more than five"])
def test_five_or_more_days_read_as_before(trips):
    text = page(trips)
    assert "Your five worst days" in text
    assert "five days came to" in text or "of your losses" in text
