"""Chapter 2 leads with what it would take to break even, and always has a way on [TICKET-837].

The overview's lead reads the same row as "The math of your trading", so the two can't disagree.
It says the amount per winner and stops there: which lever to pull is not ours to say. A book
under the minimum gets no line, and neither does a book that already made back what it lost.
"""

from __future__ import annotations

import os
import re
import shutil
from html import unescape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.production.api import formatting, limits
from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.production.api.app import create_app
from services.production.db.session import make_engine, run_migrations
from services.production.mirror import metrics as mx
from tests.unit.api.test_math_of_trading import make
from tests.unit.api.test_scope_chapters import IMP, chapter_page, readable
from tests.unit.api.test_upload import sign_up, upload

DEMO = Path("data/fixtures/demo/demo_tradebook.csv")
CTA = "Chapter 3, your behaviour: what you did after losing"
FEEDBACK = "Does this match your trading?"


def losing_book(symbol, n=30, start_id=0):
    """Two winners of 100 for each loser of 300: winners would need 150 each, so 50 more."""
    return make(([100, 100, -300] * n)[:n], symbol=symbol, start_id=start_id)


def lead_lines(trips):
    return SF.facts(SF.record_context(trips), IMP)["math"]["lead_lines"]


def lead_sentences(trips) -> list[str]:
    text = readable(chapter_page(2, trips))
    return re.findall(r"In [^.]*?, break-even takes [^.]*? more per winner\.", text)


# ---------- The lead line ----------


def test_a_losing_book_gets_a_line():
    assert lead_sentences(losing_book("WIDGET")) == [
        "In WIDGET options, break-even takes ₹50 more per winner."
    ]


def test_the_line_reads_the_same_figure_as_the_math_page():
    trips = losing_book("WIDGET")
    row = next(b for b in mx.math_by_book(mx.same_day_trips(trips))).whole
    assert lead_lines(trips) == [{"book": row.label, "more": row.winner_gap}]
    text = readable(chapter_page(2, trips))
    assert formatting.rupees(row.winner_gap, signed=False) in text


def test_each_book_gets_its_own_line_biggest_first():
    trips = losing_book("BIGGER", 60) + losing_book("SMALLER", 30, start_id=100)
    assert [line["book"] for line in lead_lines(trips)] == ["BIGGER options", "SMALLER options"]


def test_a_book_under_thirty_same_day_trades_gets_no_line():
    assert lead_lines(losing_book("WIDGET", 29)) == []


def test_a_book_at_thirty_gets_its_line():
    assert len(lead_lines(losing_book("WIDGET", 30))) == 1


def test_a_book_that_made_back_what_it_lost_gets_no_line():
    assert lead_lines(make(([300, 100, -100] * 10), symbol="WIDGET")) == []


def test_a_book_that_exactly_broke_even_gets_no_line():
    assert lead_lines(make(([100, -100] * 15), symbol="WIDGET")) == []


def test_a_held_position_is_not_counted_as_the_math_page_doesnt_count_it():
    trips = losing_book("WIDGET") + make([5000], symbol="WIDGET", days_held=3, start_id=500)
    assert lead_lines(trips)[0]["more"] == 50


def test_a_book_is_lower_cased_inside_the_sentence():
    assert SF.facts is not None
    trips = losing_book("WIDGET")
    line = lead_lines(trips)[0]
    assert formatting.book_in_a_sentence("Crude options") == "crude options"
    assert line["book"] == "WIDGET options"


def test_the_line_names_no_lever():
    text = readable(chapter_page(2, losing_book("WIDGET"))).lower()
    for said in ("something changed in your entries", "you should", "try ", "cut your", "hold your"):
        assert said not in text


def test_the_line_comes_before_the_first_fact():
    html = chapter_page(2, losing_book("WIDGET"))
    assert html.index("more per winner.") < html.index('class="story-list"')


def test_the_line_comes_after_the_sentence_that_says_rupees_below_are_gross():
    html = chapter_page(2, losing_book("WIDGET"))
    assert html.index("before brokerage and taxes") < html.index("more per winner.")


def test_other_chapters_have_no_such_line():
    for n in (1, 3, 4):
        assert "more per winner." not in chapter_page(n, losing_book("WIDGET"))


# ---------- The way on, as served ----------


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    root = tmp_path_factory.mktemp("two")
    healthy = shutil._ntuple_diskusage(total=100, used=50, free=50)  # conftest's patch comes later
    patch = pytest.MonkeyPatch()
    patch.setattr(limits.shutil, "disk_usage", lambda _path: healthy)
    saved = {k: os.environ.get(k) for k in ("SCOPE_DB", "SCOPE_FILES", "SCOPE_SECRET_KEY", "SCOPE_FILE_KEY")}
    from services.production.accounts.file_store import generate_key

    os.environ.update(SCOPE_DB=f"sqlite:///{(root / 'd.db').as_posix()}", SCOPE_FILES=str(root / "files"),
                      SCOPE_SECRET_KEY="x" * 40, SCOPE_FILE_KEY=generate_key())
    try:
        engine = make_engine(os.environ["SCOPE_DB"])
        run_migrations(engine)
        client = sign_up(TestClient(create_app()), engine, "U", "demo")
        assert upload(client, path=DEMO).status_code == 303
        got = {path: client.get(path).text for path in (
            "/mirror/chapter/1", "/mirror/chapter/2", "/mirror/chapter/3", "/mirror/chapter/4",
            S.fact_href("math"), S.fact_href("run"), S.fact_href("clock"))}
        engine.dispose()
    finally:
        patch.undo()
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return got


def links(html: str) -> list[tuple[str, str]]:
    found = re.findall(r'<a class="btn[^"]*" href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.DOTALL)
    return [(unescape(h), unescape(re.sub(r"<[^>]+>", "", t)).strip()) for h, t in found]


def test_the_overview_ends_with_a_button_into_chapter_three(pages):
    assert (S.chapter_href(3), CTA) in links(pages["/mirror/chapter/2"])


def test_the_button_comes_after_the_feedback_question(pages):
    html = pages["/mirror/chapter/2"]
    assert html.index(FEEDBACK) < html.index(unescape(CTA).split(",")[0] + ",")


def test_chapter_one_keeps_its_own_button(pages):
    assert (S.chapter_href(2), "Chapter 2: your patterns") in links(pages["/mirror/chapter/1"])


def test_the_other_chapters_get_no_new_button(pages):
    for n in (3, 4):
        assert CTA not in pages[f"/mirror/chapter/{n}"]


def test_the_math_page_goes_to_the_next_fact(pages):
    assert (S.fact_href("run"), "Next: Longest losing run") in links(pages[S.fact_href("math")])


def test_the_run_page_goes_to_the_next_fact(pages):
    hrefs = [h for h, _ in links(pages[S.fact_href("run")])]
    assert S.fact_href("clock") in hrefs


def test_the_last_fact_goes_to_chapter_three(pages):
    assert S.chapter_href(3) in [h for h, _ in links(pages[S.fact_href("clock")])]


def test_a_run_with_no_story_still_has_a_way_on():
    figs = SF.facts(SF.record_context(make([100, 100, 100] * 12, symbol="WIDGET")), IMP)
    assert figs["run"]["next"] == {"label": "Next: The clock", "href": S.fact_href("clock")}
    template = Path("services/production/api/templates/scope/facts/run.html").read_text(encoding="utf-8")
    assert "next_fact(f.next)" in template


def test_the_overviews_line_on_the_demo_file_is_served(pages):
    assert "more per winner." in unescape(pages["/mirror/chapter/2"])
