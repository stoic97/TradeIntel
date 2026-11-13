"""TICKET-862: every date a trader sees is the day in India, not the server's.

T-001 (6 Nov): the Account page dated a read 05 Nov although it was already 6 Nov in
India. The database keeps instants in UTC (db.types.AwareDateTime), and India is UTC+05:30,
so anything stamped after 18:30 UTC is already the next day for the trader. The whole
reconstruction is IST (the Dhan adapter attaches it, the loader converts every trade to its
profile's zone); a page that renders a row's own timestamp has to do the same.

The instant used throughout is 19:00 UTC on 5 Nov: 00:30 on 6 Nov in India.
"""

from __future__ import annotations

import re
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest

from services.production.api import formatting
from tests.unit.api.templating import template_env

NS = types.SimpleNamespace
LATE_IN_UTC = datetime(2026, 11, 5, 19, 0, tzinfo=UTC)
IN_INDIA = "06 Nov 2026"
ON_THE_SERVER = "05 Nov 2026"


# ---------- one helper, and the boundary it sits on ----------

@pytest.mark.parametrize(("utc", "expected"), [
    (datetime(2026, 11, 5, 18, 29, tzinfo=UTC), "05 Nov 2026"),  # 23:59 IST
    (datetime(2026, 11, 5, 18, 30, tzinfo=UTC), "06 Nov 2026"),  # 00:00 IST
    (LATE_IN_UTC, IN_INDIA),
    (datetime(2026, 12, 31, 20, 0, tzinfo=UTC), "01 Jan 2027"),   # a new year, too
])
def test_an_instant_is_dated_by_the_day_in_india(utc, expected):
    assert formatting.local_day(utc) == expected


def test_a_naive_timestamp_is_refused_not_guessed():
    """Same rule as the database (ctr_v1 4.3): no zone, no date."""
    with pytest.raises(ValueError):
        formatting.local_day(datetime(2026, 11, 5, 19, 0))  # noqa: DTZ001 - naive on purpose


# ---------- every page that dates a row by its own timestamp ----------

def render(name: str, **context) -> str:
    return template_env().get_template(name).render(title="T", csrf_token="x", **context)


def test_the_account_page_dates_a_late_read_by_the_day_in_india():
    """The defect as reported: an upload (or a read again) after 18:30 UTC."""
    imp = NS(id=7, outcome=NS(value="accepted"), rows_in=10, trips_reconstructed=2,
             source_account="A", created_at=LATE_IN_UTC)
    page = render("account.html", display_name="R", login_id="r", imports=[imp], changes={})
    rows = page.split("Your uploads", 1)[1]
    assert IN_INDIA in rows and ON_THE_SERVER not in rows


def test_the_consent_ledger_dates_an_event_by_the_day_in_india():
    event = NS(at=LATE_IN_UTC, purpose=NS(value="diagnosis"), granted=True, terms_version="1")
    page = render("consent_ledger.html", text=NS(purposes=[]), state={}, events=[event])
    ledger = page.split("Your ledger", 1)[1]
    assert IN_INDIA in ledger and ON_THE_SERVER not in ledger


def test_the_budget_page_dates_a_declaration_by_the_day_in_india():
    d = NS(effective_from="2026-11-06", unit="INR", value=5000, capital_amount=None,
           declared_at=LATE_IN_UTC, retrospective=False)
    page = render("budget.html", declarations=[d], today="2026-11-06",
                  default_from="2026-11-06", error=None, past_number=None)
    recorded = page.split("What you have told us", 1)[1]
    assert IN_INDIA in recorded and ON_THE_SERVER not in recorded


def test_home_dates_its_import_by_the_day_in_india():
    """The signed-in home names the day its record was read."""
    source = Path("services/production/api/routes_home.py").read_text(encoding="utf-8")
    assert "imported=formatting.local_day(imp.created_at)" in source


# ---------- the whole product, for the same mistake ----------

CODE = [p for d in ("api", "journal", "mirror", "accounts", "eligibility", "charges")
        for p in Path("services/production", d).rglob("*.py")]
TEMPLATES = sorted(Path("services/production/api/templates").rglob("*.html"))
# A row's own timestamp (created_at, declared_at, uploaded_at, event.at ...) turned straight
# into a date or a string, with no conversion to India in between.
RAW_INSTANT = re.compile(r"\b(?:\w+_at|at)\.(?:date\(\)|strftime\(|isoformat\(\)\[:10\])")


def test_no_template_formats_a_timestamp_itself():
    """A template dates an instant with |local_day, and a trading day with |day. A strftime
    in a template is a date written from whatever zone the value happens to be in."""
    for path in TEMPLATES:
        assert "strftime(" not in path.read_text(encoding="utf-8"), path


def test_no_code_dates_a_stored_instant_without_converting_it():
    found = [f"{p}:{n}: {line.strip()}"
             for p in CODE for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
             if RAW_INSTANT.search(line) and "astimezone" not in line]
    assert found == []


def test_the_trades_are_already_in_india_when_the_report_reads_them():
    """Why the report's own dates need nothing here: the loader converts every trade to its
    profile's zone (IST for MCX and NSE) before any page sees it."""
    loader = Path("services/production/mirror/loader.py").read_text(encoding="utf-8")
    assert "entry_ts=entry_ts.astimezone(zone)" in loader
    assert "exit_ts=exit_ts.astimezone(zone)" in loader
