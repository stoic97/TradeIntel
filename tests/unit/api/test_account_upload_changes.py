"""Each upload on the account page says what changed since the last one [TICKET-829].

Rows and days, read from the day versions that upload wrote, as its own review page does.
A day can keep its row count while a trade on it changes through pairing (TICKET-801),
so nothing here says a day is the same: only that its row count is.
"""

from __future__ import annotations

import html
import re
import types

from services.production.api.formatting import day
from services.production.ctr.intake import day_versions as dv
from tests.unit.api.templating import template_env
from tests.unit.api.test_upload import (  # noqa: F401
    DUPES,
    PNL,
    _two_days,
    client,
    engine,
    upload,
)

NS = types.SimpleNamespace


def version(trading_day: str, before: int, after: int) -> NS:
    return NS(trading_day=trading_day, rows_before=before, rows_after=after)


def rows_of(page: str) -> list[str]:
    body = page.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    cells = re.findall(r"<tr>(.*?)</tr>", body, re.DOTALL)
    return [html.unescape(" ".join(re.sub(r"<[^>]+>", " ", c).split())) for c in cells]


def line(change) -> str:
    imp = NS(id=7, outcome=NS(value="accepted"), rows_in=10, trips_reconstructed=2,
             created_at=NS(strftime=lambda _: "08 Sep 2026"))
    page = template_env().get_template("account.html").render(
        title="T", csrf_token="x", display_name="R", login_id="r", imports=[imp],
        changes={7: change})
    return rows_of(page)[0]


def test_a_change_adds_up_rows_across_days_and_names_the_ones_that_moved():
    """By hand: one day 4 to 6 (+2), one 3 to 3 (not changed), one 5 to 4 (-1). Net +1."""
    change = dv.upload_change([version("2026-09-03", 5, 4), version("2026-09-01", 4, 6),
                               version("2026-09-02", 3, 3)])
    assert change.rows == 1
    assert change.days == ("2026-09-01", "2026-09-03")


def test_a_day_new_to_scope_is_a_day_that_changed():
    change = dv.upload_change([version("2026-09-04", 0, 2)])
    assert change.rows == 2
    assert change.days == ("2026-09-04",)


def test_the_gate_line():
    change = dv.UploadChange(rows=2, days=("2026-09-04",))
    assert f"+2 rows, 1 day changed ({day('2026-09-04')}) Open" in line(change)


def test_rows_going_down_carry_a_true_minus_and_a_single_row_is_a_row():
    change = dv.UploadChange(rows=-1, days=("2026-09-04",))
    assert f"−1 row, 1 day changed ({day('2026-09-04')})" in line(change)


def test_days_that_cancel_out_print_no_rows():
    change = dv.UploadChange(rows=0, days=("2026-09-01", "2026-09-02"))
    named = f"{day('2026-09-01')}, {day('2026-09-02')}"
    assert f"10 rows, 2 trades 2 days changed ({named})" in line(change)


def test_past_three_days_it_says_how_many_more():
    days = ("2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-07")
    change = dv.UploadChange(rows=5, days=days)
    named = ", ".join(day(d) for d in days[:3])
    assert f"+5 rows, 5 days changed ({named} and 2 more)" in line(change)


def test_nothing_moved_is_said_as_row_counts_not_as_the_same_day():
    """Same counts do not mean same trades (TICKET-801)."""
    assert "Same row count on every day." in line(dv.UploadChange(rows=0, days=()))


def test_a_later_upload_says_what_it_added(client):  # noqa: F811
    """_two_days() is clean.csv plus 4 rows on a day clean.csv does not have."""
    upload(client, DUPES / "clean.csv")
    upload(client, content=_two_days())
    rows = rows_of(client.get("/account").text)
    assert f"+4 rows, 1 day changed ({day('2026-10-15')}) Open" in rows[0]


def test_a_first_upload_has_nothing_to_compare_with(client):  # noqa: F811
    upload(client, DUPES / "clean.csv")
    only = rows_of(client.get("/account").text)[0]
    assert "changed" not in only and "Same row count" not in only and "+" not in only


def test_a_first_upload_stays_first_after_a_later_one(client):  # noqa: F811
    upload(client, DUPES / "clean.csv")
    upload(client, content=_two_days())
    oldest = rows_of(client.get("/account").text)[-1]
    assert "changed" not in oldest and "Same row count" not in oldest


def test_an_upload_after_a_rejected_file_compares_with_the_last_file_read(client):  # noqa: F811
    upload(client, DUPES / "clean.csv")
    upload(client, content=PNL, name="pnl.csv")
    upload(client, content=_two_days())
    newest, rejected, _first = rows_of(client.get("/account").text)
    assert f"+4 rows, 1 day changed ({day('2026-10-15')})" in newest
    assert "not a tradebook Open" in rejected and "changed" not in rejected


def test_a_trader_who_starts_with_a_rejected_file_has_his_next_as_his_first(client):  # noqa: F811
    upload(client, content=PNL, name="pnl.csv")
    upload(client, DUPES / "clean.csv")
    newest = rows_of(client.get("/account").text)[0]
    assert "changed" not in newest and "Same row count" not in newest


def test_a_later_file_with_only_new_days_is_not_taken_for_a_first_upload(client):  # noqa: F811
    """Every day has no rows before it, which is how the review page spots a first
    upload. This list asks whether a file came before it."""
    first = (DUPES / "clean.csv").read_text()
    upload(client, content=first.encode())
    only_new = "\n".join([first.splitlines()[0], *_two_days().decode().splitlines()[-4:]]) + "\n"
    upload(client, content=only_new.encode())
    newest = rows_of(client.get("/account").text)[0]
    assert f"+4 rows, 1 day changed ({day('2026-10-15')})" in newest
