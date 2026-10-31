"""How a figure is written on a page: one place, for every page (handoff section 7).

Pages format and never compute (T7). So a figure reaches a template as a value and
leaves through one of four filters: rupees, tone, count, minutes. Each is decided
here and nowhere else, which is what lets a test say how every rupee in the product
reads.

Rupees are Indian: ₹12,34,567, grouped as Indian brokers and every trader's own P&L
group them, with the true minus (U+2212), not a hyphen. A result carries its sign,
+₹ or −₹, as the kit draws it; an amount (a budget, a price) does not. Figures are cut
to whole rupees toward zero, exactly as the templates have always cut them, so no
figure on any page changes; only how it is written does.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from services.production.api.formatting import count, indian_grouping, minutes, rupees, tone

MINUS = "\u2212"


@pytest.mark.parametrize("n,written", [
    (0, "0"), (7, "7"), (999, "999"), (1000, "1,000"), (99999, "99,999"),
    (100000, "1,00,000"), (1234567, "12,34,567"), (123456789, "12,34,56,789"),
])
def test_indian_grouping_is_three_digits_then_pairs(n, written):
    assert indian_grouping(n) == written


@pytest.mark.parametrize("value,written", [
    (Decimal("-12345.67"), f"{MINUS}₹12,345"),
    (Decimal(4500), "+₹4,500"),
    (Decimal(1234567), "+₹12,34,567"),
    (0, "₹0"),
    (-3, f"{MINUS}₹3"),
])
def test_a_result_is_written_with_its_sign_and_the_rupee_sign(value, written):
    assert rupees(value) == written


def test_the_minus_is_the_true_minus_not_a_hyphen():
    assert "-" not in rupees(Decimal(-1)) and MINUS in rupees(Decimal(-1))


def test_an_amount_is_written_without_a_plus():
    """A budget or a price is not a result; it has no sign to show."""
    assert rupees(1500000, signed=False) == "₹15,00,000"


def test_figures_are_cut_toward_zero_as_the_templates_always_cut_them():
    """int() did this in every template; the filter keeps it so no figure changes."""
    assert rupees(Decimal("999.99")) == "+₹999"
    assert rupees(Decimal("-999.99")) == f"{MINUS}₹999"
    assert rupees(Decimal("-0.40")) == "₹0"


@pytest.mark.parametrize("value,expected", [
    (Decimal(-12345), "loss"), (Decimal(4500), "gain"), (0, "plain"),
    (Decimal("-0.40"), "plain"),  # printed as ₹0, so it is not coloured as a loss
])
def test_the_tone_follows_the_figure_as_printed(value, expected):
    assert tone(value) == expected


def test_a_count_is_grouped_the_same_way():
    assert count(40) == "40"
    assert count(123456) == "1,23,456"


@pytest.mark.parametrize("seconds,written", [
    (1800, "30"), (1799, "29"), (Decimal("5400.0"), "90"), (59, "0"),
])
def test_minutes_are_whole_minutes_cut_as_before(seconds, written):
    assert minutes(seconds) == written


def test_the_apps_templates_have_the_filters():
    from services.production.api.app import TEMPLATES

    rendered = TEMPLATES.env.from_string(
        "{{ a|rupees }} {{ a|tone }} {{ b|rupees(signed=False) }} {{ c|count }} {{ s|minutes }}"
    ).render(a=Decimal(-1234), b=500000, c=123456, s=600)
    assert rendered == f"{MINUS}₹1,234 loss ₹5,00,000 1,23,456 10"


# Pages format, they don't compute (T7). For every page on layout.html, an expression
# printed into the page may call a filter but may not do arithmetic: a sum, a ratio or
# an int() cut belongs in mirror/metrics.py or in the filters above, where it is tested.

ARITHMETIC = re.compile(r"\s[-+*/%]\s|//|\|\s*(?:int|float|round|sum|abs)\b|\.format\(")
EXPRESSION = re.compile(r"{{(.*?)}}", re.DOTALL)
STRING = re.compile(r"\"[^\"]*\"|'[^']*'")


def arithmetic_in(source: str) -> list[str]:
    """Each printed expression that computes, with its string literals ignored."""
    return [e.strip() for e in EXPRESSION.findall(source) if ARITHMETIC.search(STRING.sub("", e))]


def test_the_arithmetic_check_catches_what_the_old_templates_did():
    assert arithmetic_in("{{ (holding.winners_median_seconds / 60)|int }}")
    assert arithmetic_in('{{ "{:,}".format(day.net|int) }}')
    assert arithmetic_in('{{ "%.1f"|format(day.trips / days.normal_day|float) }}')
    assert arithmetic_in("{{ risk.counts[a] + risk.counts[b] }}")


def test_the_arithmetic_check_lets_formatting_through():
    assert not arithmetic_in("{{ day.net|rupees }} {{ trades|count }} {{ s|minutes }}")
    assert not arithmetic_in('{{ "num--" ~ day.net|tone }} {{ "vt-in - x" }}')


def layout_templates() -> list[Path]:
    root = Path("services/production/api/templates")
    return [p for p in sorted(root.rglob("*.html"))
            if p.name in {"layout.html", "_components.html"}
            or "scope" in p.relative_to(root).parts  # the Scope's pages and their parts
            or '{% extends "layout.html" %}' in p.read_text()]


def test_no_page_on_the_layout_computes_a_figure():
    assert layout_templates(), "layout.html itself must be found"
    for path in layout_templates():
        assert not arithmetic_in(path.read_text()), path
