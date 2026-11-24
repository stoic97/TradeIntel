"""TICKET-1084: Same way again says what it rests on, and The day after a big day is proven on the page.

Same way again (line 1, the left-out option, and line 2): a pair whose trade has no single
direction, such as a spread, is left out, and the page says how many; the page also says how many
pairs the comparison rests on, after a loss and after a win.

The day after a big day (line 3): on a hand-worked record the page reads its population, its
sentence and its table; with too few days it says how many days there are and how many it needs.

Every trade here is made up, and every figure is worked by hand in the comments below.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from html import unescape

from tests.helpers.back_in_b1 import leg, trip
from tests.helpers.scope_facts import fact_page


def text(html: str) -> str:
    """The page's main column as one line of words."""
    found = re.search(r"<main.*?</main>", html, flags=re.DOTALL)
    words = unescape(re.sub(r"<[^>]+>", " ", found.group(0) if found else html)).replace("\xa0", " ")
    return " ".join(words.split()).replace(" ;", ";").replace(" .", ".").replace(" ,", ",").replace(" :", ":")


# ---------- Same way again over 30 pairs in each group ----------
# One pair a day, each on its own day: a first trade 09:15-09:30, then the next trade 09:40-09:50.
# The first trade is a bought call (the underlying must rise).
#   After a loss (first trade -100), 32 days:
#     18 days the next trade is a bought call   -> the same way
#     12 days it is a bought put                -> the other way
#      2 days it is a call spread (two legs)    -> no single direction, left out
#   After a win (first trade +100), 30 days:
#      9 days the next trade is a bought call   -> the same way
#     21 days it is a bought put                -> the other way
# Pairs counted: 18 + 12 = 30 after a loss, 9 + 21 = 30 after a win, 60 in all; 2 left out.
# Rates: 18 / 30 = 60 of 100 after a loss; 9 / 30 = 30 of 100 after a win.

def _pairs() -> list:
    out, day = [], date(2026, 1, 5)
    plan = ([(-100, "same")] * 18 + [(-100, "other")] * 12 + [(-100, "spread")] * 2
            + [(100, "same")] * 9 + [(100, "other")] * 21)
    for first_net, way in plan:
        iso = day.isoformat()
        nxt = {"same": (leg("CE", "Buy", 50),),
               "other": (leg("PE", "Buy", 50),),
               "spread": (leg("CE", "Buy", 80), leg("CE", "Sell", -30))}[way]
        out += [trip(f"f{iso}", iso, "09:15", "09:30", first_net, leg("CE", "Buy", first_net)),
                trip(f"n{iso}", iso, "09:40", "09:50", 50, *nxt)]
        day += timedelta(days=1)
    return out


def test_same_way_says_how_many_pairs_it_rests_on():
    said = text(fact_page("same-way", trips=_pairs()))
    assert ("After a loss, your next trade went the same way 60 of 100 times; after a win, 30 of 100."
            in said), said
    assert "These rest on 60 pairs: 30 after a loss and 30 after a win." in said, said


def test_same_way_says_a_spread_pair_is_left_out_and_how_many():
    said = text(fact_page("same-way", trips=_pairs()))
    assert "2 pairs had a trade with no single direction, such as a spread, and are left out." in said, said


# ---------- The day after a big day, six traded days ----------
# Each trade is opened and closed on the same day, 2 lots, an option; a day is the day he closed.
#   Mon 02 Mar  +300            day net +300
#   Tue 03 Mar  -100, -100      day net -200
#   Wed 04 Mar  +100            day net +100
#   Thu 05 Mar  -25, -25        day net  -50
#   Fri 06 Mar  +150, +50       day net +200
#   Mon 09 Mar  -150, -150      day net -300
# Six days, so each tenth is the minimum of three: best 02, 06, 04 Mar (+300, +200, +100);
# worst of the rest 09, 03, 05 Mar (-300, -200, -50).
# The day after is the next day he traded:
#   after 02 Mar (best)  -> 03 Mar, 2 trades     after 03 Mar (worst) -> 04 Mar, 1 trade
#   after 04 Mar (best)  -> 05 Mar, 2 trades     after 05 Mar (worst) -> 06 Mar, 2 trades
#   after 06 Mar (best)  -> 09 Mar, 2 trades
# After best days: 3 days, 6 trades, 2 a day, 2 lots. After worst days: 2 days, 3 trades,
# 1.5 a day, 2 lots. Other days: none. Every group is under 30 trades, so no rate: "too few".

def _six_days() -> list:
    out = []
    for iso, nets in (("2026-03-02", [300]), ("2026-03-03", [-100, -100]), ("2026-03-04", [100]),
                      ("2026-03-05", [-25, -25]), ("2026-03-06", [150, 50]),
                      ("2026-03-09", [-150, -150])):
        for i, net in enumerate(nets):
            out.append(trip(f"{iso}-{i}", iso, f"09:{15 + i * 10:02d}", f"09:{20 + i * 10:02d}",
                            net, leg("CE", "Buy", net), lots=2))
    return out


def test_the_day_after_reads_its_sentence_on_the_page():
    said = text(fact_page("next-day", trips=_six_days()))
    assert ("On the days after your best days you took 2 trades a day at 2 lots; "
            "after your worst days, 1.5 at 2; usually no day.") in said, said


def test_the_day_after_reads_its_population_on_the_page():
    said = text(fact_page("next-day", trips=_six_days()))
    assert "Your days are the days you closed trades on." in said
    assert "Your best days: 02 Mar 2026, 06 Mar 2026, 04 Mar 2026." in said, said
    assert "Your worst days: 09 Mar 2026, 03 Mar 2026, 05 Mar 2026." in said, said
    assert "The day after is the next day you traded." in said


def test_the_day_after_table_counts_and_says_too_few_under_thirty():
    said = text(fact_page("next-day", trips=_six_days()))
    assert "After your best days 3 6 2.0 too few" in said, said
    assert "After your worst days 2 3 2.0 too few" in said, said
    assert "Your other days 0 0 — too few" in said, said


# ---------- The day after a big day, too few days ----------
# Drop 09 Mar: five traded days. Best three and worst three need six days, so nothing is drawn,
# and the page says how many days there are and how many it needs.

def test_with_too_few_days_the_page_says_how_many_and_how_many_it_needs():
    five = [t for t in _six_days() if t.trading_day != "2026-03-09"]
    said = text(fact_page("next-day", trips=five))
    assert "Not enough trades yet" in said
    assert ("You closed trades on 5 days. The day after a big day needs 6: "
            "your best 3 and your worst 3.") in said, said
    assert "On the days after your best days" not in said


# ---------- The win half reads "of 100" too ----------
# 40 days, each: a loss at 09:15, then y at 09:40 (after the loss), then z at 10:00 (after y, a win).
# x is a bought call. y is a call on days 0-29 (same way) and a put on 30-39 (other way):
#   after a loss 30 same, 10 other -> 30 / 40 = 75 of 100.
# z follows y. Days 0-19: y call, z call -> same. Days 20-29: y call, z put -> other.
#   Days 30-39: y put, z call -> other. After a win: 20 same, 20 other -> 20 / 40 = 50 of 100.

def _forty_days() -> list:
    out = []
    for i in range(40):
        iso = (date(2026, 1, 1) + timedelta(days=i)).isoformat()
        y_kind = "CE" if i < 30 else "PE"
        z_kind = "CE" if i < 20 or i >= 30 else "PE"
        out += [trip(f"x{i}", iso, "09:15", "09:30", -10),
                trip(f"y{i}", iso, "09:40", "09:50", 20, leg(y_kind, "Buy", 20)),
                trip(f"z{i}", iso, "10:00", "10:10", -5, leg(z_kind, "Buy", -5))]
    return out


def test_both_halves_of_the_same_way_line_read_of_100():
    said = text(fact_page("same-way", trips=_forty_days()))
    assert ("After a loss, your next trade went the same way 75 of 100 times; after a win, 50 of 100."
            in said), said
    assert "These rest on 80 pairs: 40 after a loss and 40 after a win." in said, said
