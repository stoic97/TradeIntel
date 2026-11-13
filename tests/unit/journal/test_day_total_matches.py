"""TICKET-858: the Journal writes a day's total the way every other page does."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.production.api import formatting
from services.production.journal import prose


@pytest.mark.parametrize("amount", ["-1235.50", "-1234.50", "-0.50", "1235.50", "0", "-123456.75"])
def test_prose_and_the_pages_write_the_same_figure(amount):
    assert prose._rupees(amount) == formatting.rupees(Decimal(amount))


def test_a_total_is_cut_not_rounded_and_grouped_the_indian_way():
    assert prose._rupees("-1235.50") == "−₹1,235"
    assert prose._rupees("-123456.75") == "−₹1,23,456"


def test_a_date_in_a_sentence_is_the_one_format():
    assert prose._date("2026-08-05") == "05 Aug 2026"
