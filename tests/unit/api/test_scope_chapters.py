"""The four chapter pages: what each fact leads with, its state, and the page itself.

Rendered through the app's templates with the Mirror's 40-trade fixture, so the
figures are the ones a trader with that history would see. The route around these
templates (sign-in, consent, 404) is tested in tests/unit/mirror/test_scope_routes.py.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.production.api import dial, formatting
from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.api.templating import template_env

TRIPS = mx.load_trips(json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text()))
IMP = SimpleNamespace(
    id=7,
    code_version="fixturesha",
    adapter_id="dhan_tradebook_v1",
    rows_in=40,
    rows_parsed=40,
    rows_excluded=0,
    trips_reconstructed=40,
    trips_refused=0,
    fees_available=False,
)


def trips_from(nets: list[int], source=s.RiskUnitSourceV1.DECLARED_BUDGET) -> list[mx.Trip]:
    """A made-up history: one ten-minute trade a day at 09:15, one day after another."""
    start = datetime.fromisoformat("2026-09-01T09:15:00+05:30")
    out = []
    for i, net in enumerate(nets):
        entry = start + timedelta(days=i)
        out.append(
            mx.Trip(
                f"t{i}",
                "WIDGETOIL",
                entry.date().isoformat(),
                entry,
                entry + timedelta(minutes=10),
                600,
                Decimal(net),
                1,
                source,
            )
        )
    return out


def chapter_page(n: int, trips=TRIPS, imp=IMP) -> str:
    ctx = SF.record_context(trips)
    figs = SF.facts(ctx, imp)
    return (
        template_env()
        .get_template("scope/chapter.html")
        .render(
            title=S.chapter(n).name,
            chapter=S.chapter(n),
            view=SF.chapter_view(n, figs),
            facts=figs,
            imp=imp,
            trading_day_count=len(ctx["days"].counts),
            sources=s.RiskUnitSourceV1,
            **ctx,
        )
    )


CTX = SF.record_context(TRIPS)
FIGS = SF.facts(CTX, IMP)


# ---------- What each fact leads with ----------


def test_each_fact_leads_with_the_figure_metrics_decided():
    share, h = CTX["share"], CTX["holding"]
    assert FIGS["worst-days"]["figure"] == formatting.rupees(CTX["worst_days"].sum)
    assert FIGS["share"]["figure"] == f"{share.share_percent}%"
    assert FIGS["money"]["figure"] == "10 trades"
    assert FIGS["hold"]["figure"] == (
        f"{formatting.minutes(h.winners_median_seconds)} · "
        f"{formatting.minutes(h.losers_median_seconds)} min"
    )
    assert FIGS["strike"]["figure"] == f"{CTX['strike'].rate_percent}%"
    assert FIGS["run"]["figure"] == f"{CTX['run'].length} trades"
    assert FIGS["clock"]["figure"] == f"{len(CTX['hours'])} hours"
    assert FIGS["down"]["figure"] == str(CTX["two_losses"].population)
    assert FIGS["busiest"]["figure"] == f"{CTX['days'].busiest_vs_normal}×"
    assert FIGS["unread"]["figure"] == "40 of 40"
    assert FIGS["risk"]["figure"] == f"{CTX['risk'].showable} of 40"
    assert FIGS["not-told"]["figure"] == "4"


@pytest.mark.parametrize("key", list(S.FACTS))
def test_every_fact_counts_the_trades_behind_it(key):
    assert FIGS[key]["trade_count"] == len(S.trades_behind(key, CTX))


def test_on_the_fixture_every_fact_is_counted():
    assert {k: f["state"] for k, f in FIGS.items()} == dict.fromkeys(S.FACTS, "")


# ---------- States: never hidden, never an all-clear ----------


def test_a_history_with_no_losers_says_not_enough_on_the_facts_that_need_one():
    figs = SF.facts(SF.record_context(trips_from([100, 200, 300, 50])), IMP)
    for key in ("hold", "run"):
        assert figs[key]["state"] == "not-enough", key
        assert figs[key]["figure"] == "—"
        assert figs[key]["chart"] is None and figs[key]["mini"] is None


def test_no_stop_and_no_budget_is_not_in_the_file():
    figs = SF.facts(SF.record_context(trips_from([100, -50], s.RiskUnitSourceV1.UNAVAILABLE)), IMP)
    assert figs["risk"]["state"] == "not-in-file" and figs["risk"]["figure"] == "—"


def test_a_share_that_is_not_a_percentage_leads_with_the_whole_result_and_draws_no_bar():
    """A positive result with losing worst days: 'a percentage' would be nonsense (App. A)."""
    trips = trips_from([-100, -50, -20, -10, -5, 900])  # worst five lose, the whole wins
    ctx = SF.record_context(trips)
    assert not ctx["share"].shown_as_percentage
    figs = SF.facts(ctx, IMP)
    assert figs["share"]["figure"] == formatting.rupees(ctx["share"].total)
    assert figs["share"]["chart"] is None and figs["share"]["mini"] is None
    page = chapter_page(1, trips)
    assert "Your result for the whole period was" in page
    assert "% of your result" not in page


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_a_chapter_in_states_still_draws(n):
    page = chapter_page(n, trips_from([100, 200, 300, 50], s.RiskUnitSourceV1.UNAVAILABLE))
    assert page.count('<a class="story-card') == len(S.chapter(n).facts)


# ---------- The chapter's dial ----------


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_the_dial_has_a_slice_per_fact_in_slice_order(n):
    view = SF.chapter_view(n, FIGS)
    assert [i["name"] for i in view["items"]] == [f.title for f in S.chapter(n).facts]
    assert view["centre"] == {"name": S.chapter(n).name, "scopeHref": S.home_href(tap=n)}
    svg = str(dial.scope_dial(view))
    assert svg.count('<a class="scope__slice') == len(S.chapter(n).facts)
    for f in S.chapter(n).facts:
        assert f'href="{S.fact_href(f.key).replace("&", "&amp;")}"' in svg


def test_a_slice_in_a_state_is_marked_and_draws_no_mini_chart():
    figs = SF.facts(SF.record_context(trips_from([100, 200, 300, 50])), IMP)
    svg = str(dial.scope_dial(SF.chapter_view(2, figs)))
    assert svg.count("scope__slice--not-enough") == 2  # hold and run
    assert svg.count('class="scope__mini') == 2  # strike and clock


# ---------- The page ----------


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_a_chapter_page_is_the_kits_shape(n):
    page = chapter_page(n)
    c = S.chapter(n)
    assert f'<p class="label">CHAPTER {n} OF 4</p>' in page
    assert f'<h1 class="title fact__title">{c.name}</h1>'.replace("'", "&#39;") in page
    assert f"{len(c.facts)} facts, counted from your file." in page
    assert '<header class="stage on-navy" aria-label="The Scope">' in page
    assert page.count('<a class="story-card') == len(c.facts)
    for f in c.facts:  # each card opens its fact, in slice order
        assert f'href="{S.fact_href(f.key)}"' in page
    hrefs = re.findall(r'<a class="story-card[^"]*" href="([^"]+)"', page)
    assert hrefs == [S.fact_href(f.key) for f in c.facts]
    assert 'aria-current="page">Scope</a>' in page  # the bottom nav, on Scope


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_nothing_unwritten_reaches_the_page(n):
    page = chapter_page(n)
    for leak in ("None", "{{", "{%", "[N]", "[X]", "undefined"):
        assert leak not in page, leak


def test_the_gross_line_shows_only_without_a_charges_column():
    assert "every rupee figure below is gross" in chapter_page(1)
    with_fees = SimpleNamespace(**{**vars(IMP), "fees_available": True})
    assert "every rupee figure below is gross" not in chapter_page(1, imp=with_fees)


def test_the_honest_close_carries_the_lineage():
    page = chapter_page(4)
    assert (
        "Computed from import 7 by Scope version fixturesha, reading 40 rows with "
        "dhan_tradebook_v1."
    ) in page
    assert "Computed from import" not in chapter_page(1)


SENTENCES = {  # the Mirror's own sentences (mirror.html), as the cards tell them
    1: [
        "Those five days came to",
        "% of your result for the whole period, which was",
        "Your best five and worst five, by result.",
        "Ties are listed with the earlier trade first. Nothing is trimmed or capped.",
    ],
    2: [
        "Your winners were open a median of",
        "minutes, your losers",
        "That is a ratio of",
        "Your strike rate was",
        "winners against",
        "Your longest run of consecutive losers was",
    ],
    3: [
        "occasions you opened a trade after two earlier trades that day had already closed",
        "of those, the two most recent had both lost.",
        "After two straight losses",
        "Your other trades that qualified",
        "Every other trade",
        "A trade still open when the next one started does not count as closed.",
        "A scratch trade ends the run.",
        "Your normal day is",
        "Your busiest was",
    ],
    4: [
        "Rows in your file",
        "Rows we read",
        "Rows set aside",
        "Trades reconstructed",
        "Trades refused",
        "no — figures are gross",
        "Your declared budget",
        "Your stop",
        "Premium paid",
        "Nothing we could use",
        "no — recorded, never divided by",
        "Premium paid is the most you could have lost on an option, not what you had at risk,",
        "so it is counted here and used nowhere else.",
        "Nothing above names a cause. Nothing scores you, against yourself or anyone else.",
        "Nothing estimates what a habit cost you. Nothing recommends a change.",
        "These are counts from your own file, and that is all they are.",
        "The checks that could say more need work we have not finished and evidence we have",
        "not earned.",
    ],
}


def readable(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html).replace("&#39;", "'").replace("&amp;", "&")
    return " ".join(text.split())


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_every_card_tells_the_mirrors_sentences(n):
    page = readable(chapter_page(n))
    for sentence in SENTENCES[n]:
        assert sentence in page, sentence


def test_every_sentence_here_is_in_the_mirror_word_for_word():
    """In mirror.html or its drawer captions (routes_mirror.DRAWERS): handoff 6."""
    mirror = " ".join(
        (
            Path("services/production/api/templates/mirror.html").read_text()
            + Path("services/production/api/routes_mirror.py").read_text()
        ).split()
    )
    mirror = mirror.replace("“", '"').replace("”", '"')
    for sentences in SENTENCES.values():
        for sentence in sentences:
            assert sentence.replace("“", '"').replace("”", '"') in readable(mirror), sentence


def test_level_trades_are_mentioned_only_when_there_are_some():
    assert CTX["strike"].scratches == 0 or "finished level" in readable(chapter_page(2))
    none_level = chapter_page(2, trips_from([100, -50, 30, -20]))
    assert "finished level" not in none_level
