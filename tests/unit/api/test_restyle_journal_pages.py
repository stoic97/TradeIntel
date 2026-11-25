"""Batch 3 of Phase 4 (handoff 10): the import check and the Journal pages.

Each page moves onto layout.html and the kit's markup and keeps the app's own words
(handoff 6, 11), frozen here from the pages as they read before the move. Two things
change, both on purpose: counts are written by the count filter (1,240), and a
Journal's trade result by the rupees filter (−₹1,200, not -1,200) - the route now
hands the page the figure instead of a string it formatted itself. And the import
check no longer adds up its own days: the route says whether it is a first upload
(T7, test_formatting's arithmetic check).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.helpers.restyle_journal_pages import CONTEXT, PROMPTS
from tests.unit.api.templating import TEMPLATES, template_env

SAID = {
    "import_review.html#first": (
        "‹ Home Your upload What we read Rows in the file 1,240 rows Rows we could read 1,236 rows Rows set aside 4 rows Trades rebuilt 410 trades See your record — what these trades say, with the trades behind every line. This export has no charges column, so every rupee figure from it is gross — before brokerage and taxes. We do not estimate what is not in the file. 1 row we could not read Kept, not discarded. Each one says why. Row Why 12 no price Possible duplicates (1 group) Identical rows can be two real fills a second apart, or the same trade recorded twice. We cannot tell from the file, so we kept all of them. You can tell. 2 identical rows 2026-09-07,NIFTY,BUY,50,101.5 This is one trade recorded twice Days in this upload 2 trading days, from 07 Sep 2026 to 08 Sep 2026. All of them are new to Scope. Show all 2 days Every day, with its row count Day Rows 07 Sep 2026 120 08 Sep 2026 90 Journal unit for this upload: day. Read by Scope version abc123 using dhan_tradebook_v1. Every figure above can be reproduced from your file and these versions. See your record"
    ),
    "import_review.html#later": (
        "‹ Home Your upload What we read Rows in the file 1,240 rows Rows we could read 1,236 rows Rows set aside 4 rows Trades rebuilt 410 trades See your record — what these trades say, with the trades behind every line. Days in this upload Since your last upload, 1 day changed: 08 Sep 2026. 08 Sep 2026 has fewer rows than before. Show all 2 days Day Rows before Rows now 07 Sep 2026 120 120 unchanged 08 Sep 2026 90 80 fewer than before Journal unit for this upload: day. Read by Scope version abc123 using dhan_tradebook_v1. Every figure above can be reproduced from your file and these versions. See your record"
    ),
    "import_review.html#refused": (
        "‹ Home Your upload What we read This looks like a profit-and-loss statement. Upload a different file"
    ),
    "journals.html": (
        "Journals Your Journals One for every complete trading day in what you have uploaded — 8 Journals so far. Each one is written from your trades and needs nothing from you. 08 Sep 2026 updated unread 07 Sep 2026 You have 3 earlier Journals. Read them one at a time, or go to your record."
    ),
    "journals.html#none": (
        "Journals Your Journals Your Journals start with your first upload. Send us a tradebook and one is written for every complete trading day in it."
    ),
    # TICKET-906 (gate 1): the catch-up list became a month calendar, so its sentence about
    # "every other day, newest first" went - the calendar holds every day. New words, pending
    # D9: the month's name, Mon-Sun, "worth a look" / "answered" (read aloud on a cell) and
    # the two key labels. "Back to your Journals" is the page's own earlier link.
    "journals_catch_up.html": (
        "Journals Earlier Journals Back to your Journals. September 2026 Mon Tue Wed Thu Fri Sat Sun 1 2 3 4 5 6 7 8, worth a look, answered 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 Worth a look Answered 01 Sep 2026 – 02 Sep 2026"
    ),
    "journal.html": (
        "Journal 08 Sep 2026 Your Journals Version 2. A later upload changed this period. The earlier version is kept. You took 8 trades. Your worst came at 10:00. Your own note Nothing on this page is required. Anything you want to add about this period? tired Save The trades, one at a time In the order you opened them. Result is gross — your export carries no charges. Trade 1 — −₹1,200 Where was your stop? What was the trade? Was the stop on the chart when you entered? yes / no Save One question, and it changes nothing about your account Would you pay for this? Yes No Maybe If not, what would change that? Send"
    ),
}


def render(case: str) -> str:
    name = case.split("#")[0]
    return template_env().get_template(name).render(
        title="T", csrf_token="x", changed_ids={3}, earlier_id=2, **CONTEXT[case]
    )


def words(html: str) -> str:
    """What the page says in its main column, as read aloud: decoration left out."""
    main = html.split("<main", 1)[1].split("</main>", 1)[0].split(">", 1)[1]
    main = re.sub(r'<span[^>]*aria-hidden="true"[^>]*>[^<]*</span>', " ", main)
    text = " ".join(re.sub(r"<[^>]+>", " ", main).split())
    return re.sub(r"\( | (?=[).,])", lambda m: m.group(0).strip(), text)


@pytest.mark.parametrize("name", sorted({c.split("#")[0] for c in CONTEXT}))
def test_the_page_stands_on_the_layout(name):
    source = (TEMPLATES / name).read_text()
    assert '{% extends "layout.html" %}' in source and "base.html" not in source


@pytest.mark.parametrize("case", list(CONTEXT))
def test_it_says_what_it_said_before(case):
    assert words(render(case)) == SAID[case]


def test_the_import_check_does_not_add_up_its_days():
    """It summed rows_before to tell a first upload; the route says so now."""
    source = (TEMPLATES / "import_review.html").read_text()
    assert "|sum" not in source and "first_upload" in source  # <summary> is not a sum
    route = Path("services/production/api/routes_upload.py").read_text()
    assert "first_upload = sum(d.rows_before for d in days) == 0" in route


def test_the_import_check_is_the_kits_ledger():
    page = render("import_review.html#first")
    assert '<dl class="facts-list">' in page and "<dd>1,240 rows</dd>" in page
    assert '<a class="link import__next" href="/guess">' in page
    assert '<div class="screen__actions"><a class="btn btn--primary btn--block" href="/guess">' in page
    assert 'action="/imports/7/confirm-duplicates"' in page and 'name="dup_group" value="g1"' in page


def test_a_journals_trade_result_is_written_by_the_rupees_filter():
    page = render("journal.html")
    assert '<span class="num num--label num--loss">−₹1,200</span>' in page
    route = Path("services/production/api/routes_journal.py").read_text()
    assert '"net": t["net"]}' in route


def test_the_journal_pages_are_on_the_journal_tab():
    for case in ("journals.html", "journals_catch_up.html", "journal.html"):
        assert 'href="/journals" aria-current="page"' in render(case), case


def test_a_journal_keeps_its_field_names():
    page = render("journal.html")
    for name, _ in PROMPTS:
        assert f'name="{name}"' in page
    assert '<textarea class="field__input field__textarea" name="value" rows="3">tired</textarea>' in page
    assert 'name="free_text"' in page and 'action="/journals/3/wtp"' in page
