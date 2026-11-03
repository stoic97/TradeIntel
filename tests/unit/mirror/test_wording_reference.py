"""The Mirror's wording, kept word for word now that the Scope tells it.

Handoff section 6: every Mirror sentence, heading and table label is used word for
word; only the figures vary. The Scope split the long page into Home, four chapters
and twelve fact pages, and the page itself is gone. Its words were frozen first, from
the page as it rendered on the 40-trip contract fixture, figures out, in
tests/fixtures/mirror_wording/mirror_v1.json (Phase 0).

That file is a golden in the Manual's sense: a recorded output, pinned on purpose. It
can no longer be re-recorded - there is no page to record - so it changes only by
hand, as a wording decision with a reason in its commit. This file holds every Scope
page to it: each sentence the Mirror said is still said, word for word, somewhere in
the Scope.
"""

from __future__ import annotations

from services.production.api import scope_map as S
from tests.unit.mirror.wording import (
    SHARE_NOT_A_PERCENTAGE,
    figures_out,
    is_figure_only,
    mirror_sentences,
    page_text,
    said_as_written,
    sentences,
    wording,
)

RETIRED = {
    "Your record": "the long page's title; Scope home's title is the kit's new one (D9)",
}
"""Mirror lines the Scope does not say, each with why. Nothing else may go."""


def scope_pages(client) -> dict[str, str]:
    """Every page of the Scope, as a reader sees it."""
    pages = {"/mirror": client.get("/mirror").text}
    for c in S.CHAPTERS:
        pages[S.chapter_href(c.number)] = client.get(S.chapter_href(c.number)).text
    for key in S.FACTS:
        pages[S.fact_href(key, lens=False)] = client.get(S.fact_href(key, lens=False)).text
    return {url: page_text(html) for url, html in pages.items()}


def test_a_figure_is_read_the_same_however_it_is_formatted():
    assert figures_out("Those five days came to -12,345.") == "Those five days came to [N]."
    assert figures_out("Those five days came to −₹12,34,567.") == "Those five days came to [N]."
    assert figures_out("That is 96% of your result") == "That is [N] of your result"
    assert figures_out("2.5×") == "[N]"
    assert figures_out("10:00") == "[N]"


def test_words_and_line_breaks_inside_a_sentence_are_kept_as_words():
    assert (figures_out("open a median of\n   12 minutes, your losers")
            == "open a median of [N] minutes, your losers")


def test_a_hyphen_inside_a_date_or_an_identifier_is_not_a_minus_sign():
    assert figures_out("2026-03-04") == "[N]-[N]-[N]"
    assert (figures_out("reading 40 rows with dhan_tradebook_v1.")
            == "reading [N] rows with dhan_tradebook_v1.")


def test_a_cell_holding_only_figures_is_data_not_wording():
    assert is_figure_only("[N]-[N]-[N]")
    assert is_figure_only("[N]")
    assert not is_figure_only("[N] trades")


def test_wording_keeps_headings_labels_and_sentences_and_drops_controls():
    html = (
        '<section class="panel"><h2>Your worst trading days</h2>'
        "<table><tr><th>Day</th><th>Net (gross)</th></tr>"
        "<tr><td>2026-03-04</td><td>-1,250</td></tr></table>"
        "<p>Those five days came to <strong>-6,100</strong>.</p>"
        '<p class="drawer-link"><button class="link">Show me those trades</button></p>'
        "</section>"
    )
    assert wording(html) == [{
        "key": "section-0",
        "blocks": ["Your worst trading days", "Day", "Net (gross)",
                   "Those five days came to [N]."],
    }]


def test_page_text_joins_inline_figures_and_reads_a_date_as_a_date():
    html = ('<p>Those five days came to <span class="num">−₹24,000</span>.</p>'
            "<td>2026-09-07</td><p>Your busiest was <span>07 Sep</span>, at</p>")
    assert page_text(html) == "Those five days came to [N]. [DATE] Your busiest was [DATE], at"


def test_the_reference_is_the_mirror_page_as_it_was():
    lines = mirror_sentences()
    assert lines[:2] == ["Counted from your file", "Your record"]
    assert "Nothing recommends a change." in lines
    assert set(RETIRED) <= set(lines)


def test_every_mirror_sentence_is_said_somewhere_in_the_scope(client):
    """On the fixture. The share's second state is not reached on it; the next test
    but one covers those two sentences."""
    second_state = set(sentences(SHARE_NOT_A_PERCENTAGE)) - {"Those five days came to [N]."}
    everything = " || ".join(scope_pages(client).values())
    unsaid = [line for line in mirror_sentences()
              if line not in RETIRED and line not in second_state
              and said_as_written(line) not in everything]
    assert unsaid == []


def test_a_retired_line_is_really_gone(client):
    everything = " || ".join(scope_pages(client).values())
    for line in RETIRED:
        assert line not in everything, line


def test_the_sentence_for_a_share_that_is_not_a_percentage_is_kept_too(client, engine):
    """One large winning trade on a new day turns the fixture trader's total positive.

    A positive total against negative worst days gives a negative share, which
    Appendix A never shows as a percentage, so the pages take the other sentence.
    """
    from datetime import datetime
    from decimal import Decimal

    from sqlalchemy import select

    from services.production.db import models as m
    from services.production.db.session import make_session
    from services.shared.schemas import scope_v1 as s_enums

    with make_session(engine) as sess:
        imp = sess.scalars(select(m.Import)).one()
        sess.add(m.Trip(
            import_id=imp.id, trip_id="t41", trading_day="2026-09-11",
            exchange="MCX", symbol="WIDGETOIL", segment="OPT", direction="LONG",
            entry_ts=datetime.fromisoformat("2026-09-11T09:30:00+05:30"),
            exit_ts=datetime.fromisoformat("2026-09-11T10:00:00+05:30"),
            quantity=100, entry_price=Decimal(100), exit_price=Decimal(100),
            gross=Decimal(100000), fees=Decimal(0), net=Decimal(100000),
            fees_available=False,
            risk_unit_source=s_enums.RiskUnitSourceV1("declared_budget")))
        sess.commit()

    worst = page_text(client.get("/mirror/fact/worst-days").text)
    for sentence in sentences(SHARE_NOT_A_PERCENTAGE):
        assert sentence in worst, sentence
    assert "of your result for the whole period, which was" not in worst
