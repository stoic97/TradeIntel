"""Table 1 has a third row: the trades taken when not down [TICKET-836].

Worked by hand. Day one, each trade closed before the next opens (the history
TICKET-832 works):

    -100  no two trades before it                  not down
    -200  only one trade before it                 not down
    +300  the two before both lost                 after two straight losses
    -50   two before it, the last one won          another trade that qualified
    -151  two before it, one of them won           another trade that qualified
    -25   the two before both lost                 after two straight losses

Day two:

    +40   no trade before it                       not down
    +20   one trade before it                      not down

Not down: 4 trades, -100 - 200 + 40 + 20 = -240, so -240 / 4 = -60.
After two straight losses: 2 trades, +300 - 25 = +275.
Other trades that qualified: 2 trades, -50 - 151 = -201.
4 + 2 + 2 = 8 trades, and -240 + 275 - 201 = -166 is the net of all eight.

On the Appendix A fixture: 17 + 7 + 16 = 40 trips; the 16 outside the population net
-5000, so -5000 / 16 = -312.5.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from services.production.api import formatting
from services.production.mirror import metrics as mx
from tests.unit.api.test_chapter_three_describes import DOWN, one_day
from tests.unit.api.test_scope_chapters import chapter_page, readable
from tests.unit.api.test_scope_facts import fact_page

FIXTURE = Path("tests/fixtures/mirror_contract")
HISTORY = DOWN + one_day([40, 20], "2026-09-02")
NOT_DOWN = "Trades taken when not down"
SAYS = (
    "Table 1 compares your trades opened right after two straight losses, "
    "your other trades opened once at least two earlier trades that day had closed, "
    "and your trades opened when fewer than two earlier trades that day had closed."
)
VERDICT = re.compile(r"\b(better|worse|best|worst|higher|lower|outperform\w*|beats?|improv\w*)\b", re.I)
PAGES = [lambda: fact_page("down", HISTORY), lambda: chapter_page(3, HISTORY)]
IDS = ["fact page", "card"]


def section(page: str) -> str:
    """Everything between Table 1's label and Table 2's."""
    found = re.search(r"Table 1</(?:p|span)>(.*?)Table 2</", page, re.DOTALL)
    assert found, "Table 1 is not followed by Table 2"
    return found[1]


def table_one(page: str) -> list[list[str]]:
    """Table 1's body rows, each cell as the trader reads it."""
    rows = []
    for row in re.findall(r"<tr>(.*?)</tr>", section(page), re.DOTALL):
        if "<td" in row:
            rows.append([readable(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)])
    return rows


# ---------- The figures ----------


def test_the_third_group_is_every_trade_in_neither_of_the_other_two():
    tl = mx.two_straight_losses(HISTORY)
    assert (tl.condition, tl.comparison, tl.outside) == (2, 2, 4)
    assert tl.condition_net == Decimal(275)
    assert tl.comparison_net == Decimal(-201)
    assert tl.outside_net == Decimal(-240)
    assert tl.outside_mean == Decimal(-60)


def test_the_three_rows_add_up_to_every_trade_the_table_is_counted_from():
    tl = mx.two_straight_losses(HISTORY)
    assert len(HISTORY) == 8
    assert tl.condition + tl.comparison + tl.outside == len(HISTORY)
    assert tl.condition_net + tl.comparison_net + tl.outside_net == Decimal(-166)


def test_no_trades_is_no_third_group():
    tl = mx.two_straight_losses([])
    assert (tl.outside, tl.outside_net, tl.outside_mean) == (0, Decimal(0), None)


def test_on_the_appendix_a_fixture_the_third_row_is_the_hand_calculated_one():
    trips = mx.load_trips(json.loads((FIXTURE / "main.json").read_text(encoding="utf-8")))
    want = json.loads((FIXTURE / "expected.json").read_text(encoding="utf-8"))
    tl = mx.two_straight_losses(trips)
    group = want["two_straight_losses"]
    assert tl.outside == group["outside_population_count"]
    assert tl.outside_net == Decimal(group["outside_population_net"])
    assert tl.outside_mean == Decimal("-312.5")  # -5000 / 16, by hand
    assert tl.condition + tl.comparison + tl.outside == want["totals"]["trips"]


# ---------- The page ----------


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_table_one_has_a_third_row_with_its_count_money_and_average(page):
    rows = table_one(page())
    assert len(rows) == 3
    assert [r[0] for r in rows[:2]] == ["After two straight losses", "Your other trades that qualified"]
    assert rows[2] == [
        NOT_DOWN,
        "4",
        readable(formatting.rupees(Decimal(-240))),
        readable(formatting.rupees(Decimal(-60), exact=True)),
    ]


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_the_rows_count_every_trade_once(page):
    assert sum(int(r[1]) for r in table_one(page())) == len(HISTORY)


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_table_one_says_what_it_compares(page):
    assert SAYS in readable(page())


@pytest.mark.parametrize("page", PAGES, ids=IDS)
def test_table_one_names_no_row_as_better_or_worse(page):
    text = readable(section(page()))
    assert NOT_DOWN in text and SAYS in text  # the new words are inside what is checked
    assert not VERDICT.search(text), VERDICT.search(text)


# ---------- The definition ----------


def test_definitions_v1_defines_not_down_beside_the_other_two():
    text = Path("docs/product/definitions_v1.md").read_text(encoding="utf-8")
    two = text.split("## 2.", 1)[1].split("## 3.", 1)[0]
    assert "**Not down" in two
    assert "TICKET-836" in two