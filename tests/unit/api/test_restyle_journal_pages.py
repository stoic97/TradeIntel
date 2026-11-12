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
import types
from decimal import Decimal
from pathlib import Path

import pytest

from services.shared.schemas import scope_v1 as s
from tests.unit.api.templating import TEMPLATES, template_env

NS = types.SimpleNamespace


def an_import(outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS, fees=False):
    return NS(id=7, outcome=outcome,
              rejection_text="This looks like a profit-and-loss statement.",
              rows_in=1240, rows_parsed=1236, rows_excluded=4, trips_reconstructed=410,
              fees_available=fees, density_default_unit="day", code_version="abc123",
              adapter_id="dhan_tradebook_v1")


def row(n, why=""):
    return NS(row_no=n, reason=why, raw_text="2026-09-07,NIFTY,BUY,50,101.5")


def day(d, before, after, shrank=False, diff="new"):
    return NS(trading_day=d, rows_before=before, rows_after=after, day_shrank=shrank,
              diff=NS(value=diff))


def journal(id_, start, end, version=1, opened=True):
    return NS(id=id_, period_start=start, period_end=end, version_no=version,
              opened_at=opened)


PROMPTS = (("planned_sl", "Where was your stop?"), ("rationale", "What was the trade?"),
           ("stop_existed_at_entry", "Was the stop on the chart when you entered? yes / no"))

CONTEXT = {
    "import_review.html#first": {
        "imp": an_import(), "rejected": [row(12, "no price")],
        "groups": {"g1": [row(30), row(31)]}, "excluded": [], "first_upload": True,
        "changed_days": [], "shrunk_days": [],
        "days": [day("2026-09-07", 0, 120), day("2026-09-08", 0, 90)]},
    "import_review.html#later": {
        "imp": an_import(fees=True), "rejected": [], "groups": {}, "excluded": [],
        "first_upload": False, "changed_days": ["2026-09-08"], "shrunk_days": ["2026-09-08"],
        "days": [day("2026-09-07", 120, 120, diff="unchanged"),
                 day("2026-09-08", 90, 80, shrank=True)]},
    "import_review.html#refused": {
        "imp": an_import(outcome=s.ImportOutcome.REJECTED), "rejected": [], "groups": {},
        "excluded": [], "days": [], "first_upload": True},
    "journals.html": {
        "latest": [journal(3, "2026-09-08", "2026-09-08", version=2, opened=False),
                   journal(2, "2026-09-07", "2026-09-07")],
        "total": 8, "catch_up_count": 3},
    "journals.html#none": {"latest": [], "total": 0, "catch_up_count": 0},
    "journals_catch_up.html": {"journals": [journal(1, "2026-09-01", "2026-09-02")]},
    "journal.html": {
        "journal": journal(3, "2026-09-08", "2026-09-08", version=2),
        "paragraphs": ["You took 8 trades.", "Your worst came at 10:00."],
        "rows": [{"trip_id": "t1", "label": "Trade 1", "net": Decimal(-1200)}],
        "answers": {"t1": {"planned_sl": NS(value="100"), "rationale": None,
                           "stop_existed_at_entry": None}},
        "prompts": PROMPTS, "fees_available": False, "note": NS(value="tired"),
        "ask_wtp": True, "wtp_question": "Would you pay for this?"},
}

SAID = {
    "import_review.html#first": (
        "‹ Home Your upload What we read Rows in the file 1,240 rows Rows we could read 1,236 rows Rows set aside 4 rows Trades rebuilt 410 trades See your record — what these trades say, with the trades behind every line. This export has no charges column, so every rupee figure from it is gross — before brokerage and taxes. We do not estimate what is not in the file. 1 row we could not read Kept, not discarded. Each one says why. Row Why 12 no price Possible duplicates (1 group) Identical rows can be two real fills a second apart, or the same trade recorded twice. We cannot tell from the file, so we kept all of them. You can tell. 2 identical rows 2026-09-07,NIFTY,BUY,50,101.5 This is one trade recorded twice Days in this upload 2 trading days, from 2026-09-07 to 2026-09-08. All of them are new to Scope. Show all 2 days Every day, with its row count Day Rows 2026-09-07 120 2026-09-08 90 Journal unit for this upload: day. Read by Scope version abc123 using dhan_tradebook_v1. Every figure above can be reproduced from your file and these versions. See your record"
    ),
    "import_review.html#later": (
        "‹ Home Your upload What we read Rows in the file 1,240 rows Rows we could read 1,236 rows Rows set aside 4 rows Trades rebuilt 410 trades See your record — what these trades say, with the trades behind every line. Days in this upload Since your last upload, 1 day changed: 08 Sep 2026. 08 Sep 2026 has fewer rows than before. Show all 2 days Day Rows before Rows now 2026-09-07 120 120 unchanged 2026-09-08 90 80 fewer than before Journal unit for this upload: day. Read by Scope version abc123 using dhan_tradebook_v1. Every figure above can be reproduced from your file and these versions. See your record"
    ),
    "import_review.html#refused": (
        "‹ Home Your upload What we read This looks like a profit-and-loss statement. Upload a different file"
    ),
    "journals.html": (
        "Journals Your Journals One for every complete trading day in what you have uploaded — 8 Journals so far. Each one is written from your trades and needs nothing from you. 2026-09-08 version 2 unread 2026-09-07 You have 3 earlier Journals. Read them one at a time, or go to your record."
    ),
    "journals.html#none": (
        "Journals Your Journals Your Journals start with your first upload. Send us a tradebook and one is written for every complete trading day in it."
    ),
    "journals_catch_up.html": (
        "Journals Earlier Journals Everything behind the five most recent, newest first. Back to the latest. 2026-09-01 – 2026-09-02"
    ),
    "journal.html": (
        "Journal 2026-09-08 Your Journals Version 2. A later upload changed this period. The earlier version is kept. You took 8 trades. Your worst came at 10:00. Your own note Nothing on this page is required. Anything you want to add about this period? tired Save The trades, one at a time In the order you opened them. Result is gross — your export carries no charges. Trade 1 — −₹1,200 Where was your stop? What was the trade? Was the stop on the chart when you entered? yes / no Save One question, and it changes nothing about your account Would you pay for this? Yes No Maybe If not, what would change that? Send"
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
