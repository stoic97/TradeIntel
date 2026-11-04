"""Chapter 4 says what was read, and refused trades apart from it (TICKET-804).

"What we couldn't read: 40 of 40" put the count of rows READ beside a name saying the
opposite, so a file read in full looked like a file not read at all. Rendered through the
app's templates on the contract fixture, whose import is 40 rows, all read.
"""

from __future__ import annotations

from types import SimpleNamespace

from services.production.api import dial
from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from tests.unit.api.test_scope_chapters import IMP, TRIPS, chapter_page, readable
from tests.unit.api.test_scope_facts import fact_page
from tests.unit.api.test_scope_home import home_page


def _imp(**changes) -> SimpleNamespace:
    return SimpleNamespace(**{**vars(IMP), **changes})


def _hub_view(imp=IMP) -> dict:
    ctx = SF.record_context(TRIPS)
    return SF.home_view(SF.facts(ctx, imp), ctx)


def test_the_hub_slice_is_named_for_what_was_read():
    assert _hub_view()["items"][3]["name"] == "What we read"


def test_the_hub_slice_figure_stays_short_enough_for_its_wedge():
    """Seen in a browser: at four-digit rows the tail "of N rows" fits at no figure size, so
    the dial's layout gives up and the white centre covers its end."""
    assert _hub_view()["items"][3]["figure"] == "40 of 40"


def test_the_hub_page_says_it_in_full_under_the_dial():
    assert "What we read: 40 of 40 rows." in readable(home_page())


def test_the_drawn_dial_no_longer_says_could_not_read():
    svg = str(dial.scope_dial(_hub_view()))
    assert "couldn" not in svg and "could not" not in svg


def test_rows_are_grouped_and_a_partial_read_shows_the_gap():
    assert _hub_view(_imp(rows_in=1240, rows_parsed=1236))["items"][3]["figure"] == "1,236 of 1,240"
    page = readable(home_page(imp=_imp(rows_in=1240, rows_parsed=1236)))
    assert "What we read: 1,236 of 1,240 rows." in page


def test_chapter_four_is_named_what_we_read():
    assert S.chapter(4).name == "What we read"


def test_chapter_four_never_says_could_not_read_beside_the_figure():
    page = readable(chapter_page(4))
    assert "What we read" in page and "40 of 40 rows" in page
    assert "couldn't read" not in page and "could not read" not in page


def test_the_fact_page_is_named_what_we_read():
    page = readable(fact_page("unread"))
    assert S.FACTS["unread"].title == "What we read"
    assert "40 of 40 rows" in page


def test_refused_trades_are_stated_apart_on_the_hub():
    assert "2 trades we couldn't use." in readable(home_page(imp=_imp(trips_refused=2)))


def test_refused_trades_are_stated_apart_on_chapter_four():
    assert "2 trades we couldn't use." in readable(chapter_page(4, imp=_imp(trips_refused=2)))


def test_refused_trades_are_stated_apart_on_the_fact_page():
    assert "2 trades we couldn't use." in readable(fact_page("unread", imp=_imp(trips_refused=2)))


def test_one_refused_trade_reads_in_the_singular():
    assert "1 trade we couldn't use." in readable(chapter_page(4, imp=_imp(trips_refused=1)))


def test_nothing_refused_says_nothing():
    """Guard: once sold options count (TICKET-810) a new upload refuses none."""
    for page in (home_page(), chapter_page(4), fact_page("unread")):
        assert "couldn't use" not in readable(page)


def test_the_list_of_set_aside_rows_keeps_its_own_words():
    """Guard: those rows really were not read, so this sentence stays true and stays."""
    page = fact_page("unread", unread={"excluded": [], "rejected": [(9, "No date")],
                                       "refused": []})
    assert "Rows we could not read." in readable(page)
