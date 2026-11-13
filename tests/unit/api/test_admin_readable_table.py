"""TICKET-868: the trader table reads on one screen, and a real problem stands out.

Every account here is made up. Still read-only: sorting and showing columns are plain links, with
no script and no form.
"""

from __future__ import annotations

import re
from datetime import timedelta

from sqlalchemy import select

from services.production.api import admin_view
from services.production.db import models as m
from services.production.db.session import make_session
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_admin_page import (  # noqa: F401
    ADMIN,
    THEN,
    add_import,
    add_trader,
    admin_client,
    app,
    engine,
    row_of,
    signed_in,
    view,
)

DEFAULT = ("Trader", "File", "Journey", "Facts read", "In the report", "Last activity", "Issues")


def page(app, engine, query=""):  # noqa: F811
    with make_session(engine) as sess:
        admin = sess.scalars(select(m.Trader.id).where(m.Trader.login_id == ADMIN)).first()
    client = signed_in(app, admin) if admin else admin_client(app, engine)
    return client.get(f"/admin{query}").text


def headers(html: str) -> list[str]:
    table = re.search(r'<table class="table admin__table admin__traders".*?</thead>', html, re.DOTALL)[0]
    return [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<th\b[^>]*>(.*?)</th>", table, re.DOTALL)]


def test_the_default_view_is_the_seven_columns(app, engine):  # noqa: F811
    assert headers(page(app, engine)) == list(DEFAULT)


def test_a_link_shows_every_column_and_loses_nothing(app, engine):  # noqa: F811
    html = page(app, engine, "?columns=all")
    columns = headers(html)
    for name in ("Login id", "Files uploaded", "First upload", "Days active", "Rows read",
                 "Would read differently", "Chapter 1 match?", "Whole report", "Journals opened",
                 "Journals written", "Budget", "Would pay", "Pay question", "Signed up"):
        assert name in columns, name
    assert 'href="/admin"' in html


def test_the_default_view_links_to_every_column(app, engine):  # noqa: F811
    assert 'href="/admin?columns=all"' in page(app, engine)


def test_the_trader_cell_says_who_with_the_login_id(app, engine):  # noqa: F811
    add_trader(engine, "someone", name="A Person")
    html = page(app, engine)
    assert "A Person" in html and "someone" in html


# ---------- Issues ----------


def test_no_issue_is_an_empty_cell(app, engine):  # noqa: F811
    add_trader(engine, "someone")
    assert row_of(view(app, engine), "someone")["issues"] == ""


def test_refused_files_rows_and_duplicates_merge_into_one(app, engine):  # noqa: F811
    trader = add_trader(engine, "someone")
    with make_session(engine) as sess:
        imp = add_import(sess, trader, rows=(10, 7, 2))
        add_import(sess, trader, outcome=s.ImportOutcome.REJECTED, rows=(1, 0, 0),
                   at=THEN + timedelta(hours=1))
        sess.add(m.ImportRow(import_id=imp.id, row_no=1, raw_text="made-up", status="PARSED",
                             reason=None, flag=s.RowFlag.SUSPECTED_DUPLICATE))
        sess.commit()
    assert row_of(view(app, engine), "someone")["issues"] == (
        "1 file refused, 1 row refused, 1 duplicate flagged")


def test_issues_count_in_the_plural(app, engine):  # noqa: F811
    trader = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_import(sess, trader, outcome=s.ImportOutcome.REJECTED, rows=(1, 0, 0))
        add_import(sess, trader, outcome=s.ImportOutcome.REJECTED, rows=(1, 0, 0),
                   at=THEN + timedelta(hours=1))
        sess.commit()
    assert row_of(view(app, engine), "someone")["issues"].startswith("2 files refused")


# ---------- Sorting, by plain links ----------


def order(app, engine, query=""):  # noqa: F811
    html = page(app, engine, query)
    body = re.search(r'<table class="table admin__table admin__traders".*?</table>', html, re.DOTALL)[0]
    return re.findall(r'<td class="admin__who">([^<]+)<', body)


def test_it_sorts_by_last_activity_by_default_and_by_name_on_a_link(app, engine):  # noqa: F811
    add_trader(engine, "zed", name="Zed", joined=THEN + timedelta(days=1))
    add_trader(engine, "amy", name="Amy", joined=THEN)
    assert order(app, engine)[:2] == ["Zed", "Amy"] or order(app, engine)[1:3] == ["Zed", "Amy"]
    names = order(app, engine, "?sort=name")
    assert names == sorted(names)


def test_issues_sort_the_problems_first(app, engine):  # noqa: F811
    fine, broken = add_trader(engine, "fine", name="Fine"), add_trader(engine, "broken", name="Broken")
    with make_session(engine) as sess:
        add_import(sess, fine, rows=(10, 10, 0), at=THEN + timedelta(days=2))
        add_import(sess, broken, outcome=s.ImportOutcome.REJECTED, rows=(1, 0, 0))
        sess.commit()
    assert order(app, engine, "?sort=issues")[0] == "Broken"


def test_a_sort_nobody_offered_is_the_default(app, engine):  # noqa: F811
    add_trader(engine, "someone")
    assert admin_client(app, engine).get("/admin?sort=password_hash").status_code == 200


def test_each_sortable_header_is_a_plain_link_that_keeps_the_view(app, engine):  # noqa: F811
    html = page(app, engine, "?columns=all")
    assert 'href="/admin?columns=all&amp;sort=name"' in html
    assert 'href="/admin?sort=name"' in page(app, engine)


def test_the_page_still_has_no_script_or_form(app, engine):  # noqa: F811
    html = page(app, engine, "?columns=all&sort=name")
    assert "<script" not in html
    assert "<form" not in html
    assert "<input" not in html


# ---------- What goes, what folds, what's named ----------


def test_the_drawers_are_gone(app, engine):  # noqa: F811
    html = page(app, engine, "?columns=all")
    assert "Drawer opens" not in html
    assert "Most-opened drawer" not in html
    assert "most_opened" not in view(app, engine)["quiet"]


def test_a_switched_off_feature_draws_no_column_and_the_page_says_so(app, engine, monkeypatch):  # noqa: F811
    monkeypatch.setattr(admin_view.GU, "ready", lambda _production: False)
    monkeypatch.setattr(admin_view.LC, "ready", lambda _production: False)
    html = page(app, engine, "?columns=all")
    assert "<th>Guess</th>" not in html
    assert "<th>Leaving card</th>" not in html
    assert "<strong>Switched off here:</strong> guess, leaving card" in html


def test_the_notes_fold_and_keep_their_words(app, engine):  # noqa: F811
    html = page(app, engine)
    fold = re.search(r"<details class=\"admin__fold\">.*?</details>", html, re.DOTALL)[0]
    for words in ("what the trader's report reads now", "the same check that offers them a re-read",
                  "each step with a stored trace", "so these are floors",
                  "A byte-identical re-upload is refused", "It is a floor: a visit that writes nothing",
                  "what a trader typed is not shown"):
        assert words in fold.replace("&#39;", "'"), words


def test_the_page_has_a_way_back_and_a_way_to_sign_out(app, engine):  # noqa: F811
    html = page(app, engine)
    assert '<a class="link" href="/">Home</a>' in html
    assert '<a class="link" href="/account">Account, to sign out</a>' in html


def test_the_quiet_panel_says_what_it_is(app, engine):  # noqa: F811
    html = page(app, engine)
    assert "quiet panel" not in html
    assert "Consent declines and deletions" in html  # would pay moved to "What traders told us" (876)


def test_a_trader_cell_and_header_stay_in_view():
    from pathlib import Path

    css = Path("services/production/api/static/css/app.css").read_text()
    assert re.search(r"\.admin__traders thead th \{[^}]*position: sticky", css)
    assert re.search(r"\.admin__who \{[^}]*position: sticky", css)


def test_a_feature_that_is_on_draws_its_column(app, engine, monkeypatch):  # noqa: F811
    monkeypatch.setattr(admin_view.GU, "ready", lambda _production: True)
    monkeypatch.setattr(admin_view.LC, "ready", lambda _production: True)
    html = page(app, engine, "?columns=all")
    assert "<th>Guess</th>" in html and "<th>Leaving card</th>" in html
