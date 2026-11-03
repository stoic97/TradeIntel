"""The Mirror's wording, frozen before the Scope rebuild replaces its page.

Handoff section 6: every Mirror sentence, heading and table label is used word for
word; only the figures vary. The Scope splits today's one page into four chapters and
twelve fact pages, after which mirror.html is no longer a page a trader sees and can
no longer be what the new pages are checked against. So its words are taken now, from
the page as it renders on the 40-trip contract fixture, figures out, and kept in
tests/fixtures/mirror_wording/mirror_v1.json.

That file is a golden in the Manual's sense: a recorded output, pinned on purpose. It
is rewritten only by running this file with FREEZE_MIRROR_WORDING=1, and only when the
wording is meant to change -- a decision with a reason in its commit, never a side
effect of a test run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from tests.unit.mirror.wording import figures_out, is_figure_only, wording

REFERENCE = Path("tests/fixtures/mirror_wording/mirror_v1.json")


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


def test_the_mirror_says_exactly_what_the_reference_says(client):
    current = wording(client.get("/mirror").text)
    if os.environ.get("FREEZE_MIRROR_WORDING") == "1":
        REFERENCE.parent.mkdir(parents=True, exist_ok=True)
        REFERENCE.write_text(json.dumps(
            {"source": "/mirror rendered on tests/fixtures/mirror_contract/main.json",
             "sections": current},
            indent=2, ensure_ascii=False) + "\n")
    assert REFERENCE.exists(), (
        "No wording reference yet. Freeze it once, on purpose: "
        "FREEZE_MIRROR_WORDING=1 pytest tests/unit/mirror/test_wording_reference.py")
    assert current == json.loads(REFERENCE.read_text())["sections"]


# The sentence mirror.html prints when the share is not a percentage (Appendix A: a
# positive total, or worst days larger than the whole). The 40-trip fixture never
# reaches it, so it is not in the frozen reference above; it is written here from the
# template, figures out, and the test below proves the template still prints exactly
# this. The reveal's second state (handoff section 7) reuses it word for word.
SHARE_NOT_A_PERCENTAGE = (
    "Those five days came to [N]. Your result for the whole period was [N]. "
    "The other [N] days were net [N]."
)


def test_the_sentence_for_a_share_that_is_not_a_percentage_is_kept_too(client, engine):
    """One large winning trade on a new day turns the fixture trader's total positive.

    A positive total against negative worst days gives a negative share, which
    Appendix A never shows as a percentage, so the page takes its other sentence.
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

    blocks = [b for section in wording(client.get("/mirror").text)
              for b in section["blocks"]]
    assert SHARE_NOT_A_PERCENTAGE in blocks
