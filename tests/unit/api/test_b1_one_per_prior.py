"""TICKET-1006, B1 parity: "back in" is B1's time to next entry, one observation per prior trip.

B1 (Research Spec v1.0, Annex A.2): prior trip lost, against prior trip won or flat; outcome, the time
to the next entry. Two trades opened after one loss, before either closes, are one prior and one
next entry: the first. Same way again still pairs every trade with its previous one.

Hand-worked: e1 loses, closing 09:30. e2 opens 09:40 (10 minutes); e3 opens 09:50 while e2 is open,
so its previous is still e1, but it is not e1's next entry. e2 wins at 10:30; e4 opens 10:35.
Back in: after a loss, e2 only (10 min); after a win or level, e4 only (5 min).
"""
from decimal import Decimal

from services.production.mirror import metrics as mx
from tests.helpers.back_in_b1 import trip

E = [
    trip("e1", "2026-04-01", "09:15", "09:30", -100),
    trip("e2", "2026-04-01", "09:40", "10:30", 50),
    trip("e3", "2026-04-01", "09:50", "10:00", -20),
    trip("e4", "2026-04-01", "10:35", "10:40", 30),
]


def test_a_loss_followed_by_two_entries_is_one_observation():
    nt = mx.next_trades(E)
    assert [t.trip_id for t in nt.after_loss] == ["e2"]
    assert nt.loss_median == Decimal(10)


def test_the_comparison_is_one_observation_per_prior_too():
    nt = mx.next_trades(E)
    assert [t.trip_id for t in nt.comparison] == ["e4"]
    assert nt.comparison_median == Decimal(5)
    assert set(nt.back_in_group_of) == {"e2", "e4"}


def test_same_way_still_pairs_every_trade_with_its_previous():
    nt = mx.next_trades(E)
    assert nt.group_of["e3"] == "loss"  # e3's previous is e1: a pair for same way again


# ---------- the B1 fixture (PAIRS), re-pinned for one observation per prior ----------
# a3 finished level, closing 10:20. a4 opens 10:25: a3's next entry (5 min). a5 opens 10:35 while a4
# is open; its previous is still a3, but it is not a3's next entry, so it is not a back-in observation.
# After a loss:                 a2 (4), b2 (6)          -> 2 trades
# After a win or a level trade: a3 (11), a4 (5), a6 (5) -> 3 trades; sorted 5, 5, 11 -> median 5
import re

from services.production.api import scope_facts as SF
from services.production.api import trade_list as TL
from tests.helpers.back_in_b1 import PAIRS
from tests.helpers.scope_chapters import IMP


def _words(markup) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", str(markup)).split()).replace(" ,", ",").replace(" .", ".")


def test_the_fixture_counts_each_prior_once():
    nt = SF.record_context(PAIRS)["next_trades"]
    assert sorted(t.trip_id for t in nt.after_loss) == ["a2", "b2"]
    assert sorted(t.trip_id for t in nt.comparison) == ["a3", "a4", "a6"]
    assert nt.comparison_median == Decimal(5)
    ctx = SF.record_context(PAIRS)
    shown = [TL.listing("back-in", ctx, q, {})["shown"] for q in ({}, {"after": "loss"}, {"after": "win-or-level"})]
    assert shown == [5, 2, 3]


def test_the_page_says_the_counts_of_one_per_prior():
    f = SF.facts(SF.record_context(PAIRS), IMP)["back-in"]
    assert _words(f["line"]) == (
        "2 trades came next after a loss and 3 after a win or a flat trade: too few to set "
        "side by side. Each needs 30.")
    assert [g["trades"] for g in f["groups"]] == [2, 3]
