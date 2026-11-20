"""Moved out of tests/unit/api/test_restyle_journal_pages.py by TICKET-945, so that no test file imports another."""

from __future__ import annotations

import types
from decimal import Decimal

from services.production.journal import month_view
from services.shared.schemas import scope_v1 as s

NS = types.SimpleNamespace


def an_import(outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS, fees=False):
    return NS(
        id=7,
        outcome=outcome,
        rejection_text="This looks like a profit-and-loss statement.",
        rows_in=1240,
        rows_parsed=1236,
        rows_excluded=4,
        trips_reconstructed=410,
        fees_available=fees,
        density_default_unit="day",
        code_version="abc123",
        adapter_id="dhan_tradebook_v1",
    )


def row(n, why=""):
    return NS(row_no=n, reason=why, raw_text="2026-09-07,NIFTY,BUY,50,101.5")


def day(d, before, after, shrank=False, diff="new"):
    return NS(
        trading_day=d, rows_before=before, rows_after=after, day_shrank=shrank, diff=NS(value=diff)
    )


def journal(id_, start, end, version=1, opened=True):
    return NS(id=id_, period_start=start, period_end=end, version_no=version, opened_at=opened)


PROMPTS = (
    ("planned_sl", "Where was your stop?"),
    ("rationale", "What was the trade?"),
    ("stop_existed_at_entry", "Was the stop on the chart when you entered? yes / no"),
)


CONTEXT = {
    "import_review.html#first": {
        "imp": an_import(),
        "rejected": [row(12, "no price")],
        "groups": {"g1": [row(30), row(31)]},
        "excluded": [],
        "first_upload": True,
        "changed_days": [],
        "shrunk_days": [],
        "days": [day("2026-09-07", 0, 120), day("2026-09-08", 0, 90)],
    },
    "import_review.html#later": {
        "imp": an_import(fees=True),
        "rejected": [],
        "groups": {},
        "excluded": [],
        "first_upload": False,
        "changed_days": ["2026-09-08"],
        "shrunk_days": ["2026-09-08"],
        "days": [
            day("2026-09-07", 120, 120, diff="unchanged"),
            day("2026-09-08", 90, 80, shrank=True),
        ],
    },
    "import_review.html#refused": {
        "imp": an_import(outcome=s.ImportOutcome.REJECTED),
        "rejected": [],
        "groups": {},
        "excluded": [],
        "days": [],
        "first_upload": True,
    },
    "journals.html": {
        "latest": [
            journal(3, "2026-09-08", "2026-09-08", version=2, opened=False),
            journal(2, "2026-09-07", "2026-09-07"),
        ],
        "total": 8,
        "catch_up_count": 3,
    },
    "journals.html#none": {"latest": [], "total": 0, "catch_up_count": 0},
    # TICKET-906: the catch-up list is a month calendar. One day worth a look and answered,
    # and a two-day Journal in the strip under the grid.
    "journals_catch_up.html": {
        "shown": month_view.month(["2026-09-08"], None),
        "days": {"2026-09-08": journal(3, "2026-09-08", "2026-09-08")},
        "offered": {3: "worth"},
        "answered": {"2026-09-08"},
        "strip": [journal(1, "2026-09-01", "2026-09-02")],
        "prev_title": None,
        "next_title": None,
    },
    "journal.html": {
        "journal": journal(3, "2026-09-08", "2026-09-08", version=2),
        "paragraphs": ["You took 8 trades.", "Your worst came at 10:00."],
        "rows": [{"trip_id": "t1", "label": "Trade 1", "net": Decimal(-1200)}],
        "answers": {
            "t1": {"planned_sl": NS(value="100"), "rationale": None, "stop_existed_at_entry": None}
        },
        "prompts": PROMPTS,
        "fees_available": False,
        "note": NS(value="tired"),
        "ask_wtp": True,
        "wtp_question": "Would you pay for this?",
    },
}
