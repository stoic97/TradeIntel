"""Batch 1 of Phase 4 (handoff 10): account, delete, not found, not open, invite.

Each page moves onto layout.html and the kit's markup and keeps the app's own words
(handoff 6, 11). The words are frozen here from the pages as they read before the
move; the only change is that counts are written by the count filter (1,240, not
1240). The kit's new lines on these screens - "Back to the Scope page", "I already
have an account · Sign in" - are not the app's words and wait for D9.
"""

from __future__ import annotations

import re
import types
from datetime import UTC, datetime

import pytest

from services.shared.schemas import scope_v1 as s
from tests.unit.api.templating import TEMPLATES, template_env


def upload(id_, outcome, rows, trades):
    return types.SimpleNamespace(id=id_, outcome=outcome, rows_in=rows,
                                 trips_reconstructed=trades,
                                 created_at=datetime(2026, 9, 8, tzinfo=UTC))


CONTEXT = {
    "account.html": {"display_name": "Ravi", "login_id": "ravi", "imports": [
        upload(3, s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS, 1240, 40),
        upload(4, s.ImportOutcome.REJECTED, 3, 0)]},
    "delete_confirm.html": {"error": "Tick the box to confirm."},
    "delete_done.html": {},
    "404.html": {},
    "not_open.html": {},
    "invite.html": {"code": "ABC", "error": "That login id is taken."},
}

SAID = {
    "account.html": (
        "Your account Ravi Signed in as ravi. Your uploads When What we read 08 Sep 2026 1,240 rows, 40 trades Open 08 Sep 2026 not a tradebook Open Upload a tradebook Your settings What you agreed to Sign out"
    ),
    "delete_confirm.html": (
        "Your data Delete everything Tick the box to confirm. This removes the file you uploaded, every trade we rebuilt from it, every Journal written from those trades, your risk figures, and the record of which lines you opened. It removes your account with them, so you will not be able to sign in again. Backups hold yesterday's copy, and they roll off within 30 days. After that your data is gone from those too. What we keep Two rows: that this account agreed to what we do with a tradebook, and that it asked to be deleted and was. No name, no trades, no figure worked out from them. What deleting cannot undo Your file and everything built from it can be removed at any time. What cannot be undone is that looking at your data informed decisions we have already made about the engine. This is the same as any research partnership, and we say so plainly. I have read this and I want everything deleted. Delete everything Back to your account — nothing has been deleted yet."
    ),
    "delete_done.html": (
        "Your data Deleted Your file, the trades rebuilt from it, your Journals and your account are gone from our database and from the server's disk. Backups roll off within 30 days. We kept two rows, and this is all they say: that this account agreed to what we do with a tradebook, and that it asked to be deleted and was. No name, no trades, no figure worked out from them. This page is the confirmation — we have no way to email you, and we did not keep an address to email."
    ),
    "404.html": (
        "Not found There is nothing at this address."
    ),
    "not_open.html": (
        "Scope Scope is not open yet The page that tells you what happens to your tradebook has not been checked yet. Someone other than the people who wrote it has to read it, and the deletion process has to be run end to end and confirmed, before anyone is asked to agree to it. Until both are done, this account cannot upload a file. Nothing is stored for you beyond the account itself, and nothing has been read. If you were expecting to start today, tell us and we will say where this stands."
    ),
    "invite.html": (
        "Create your account You were invited to Scope. Choose a login id and a password. That login id is taken. Your name Login id Password At least 12 characters. There is no email on your account, so keep this somewhere safe — a reset has to go through us. Create account"
    ),
}


def render(name: str) -> str:
    return template_env().get_template(name).render(title="T", csrf_token="x", **CONTEXT[name])


def words(html: str) -> str:
    """What the page says in its main column, as read aloud: decoration left out."""
    main = html.split("<main", 1)[1].split("</main>", 1)[0].split(">", 1)[1]
    main = re.sub(r'<span[^>]*aria-hidden="true"[^>]*>[^<]*</span>', " ", main)
    return " ".join(re.sub(r"<[^>]+>", " ", main).split())


@pytest.mark.parametrize("name", list(CONTEXT))
def test_the_page_stands_on_the_layout(name):
    source = (TEMPLATES / name).read_text()
    assert '{% extends "layout.html" %}' in source and "base.html" not in source
    assert '<link rel="stylesheet" href="/static/css/components.css">' in render(name)


@pytest.mark.parametrize("name", list(CONTEXT))
def test_it_says_what_it_said_before(name):
    assert words(render(name)) == SAID[name]


def test_account_is_the_kits_with_the_account_tab():
    page = render("account.html")
    assert '<h1 class="title fact__title">Ravi</h1>' in page
    assert '<a class="link" href="/imports/3">Open</a>' in page
    assert '<a class="btn btn--secondary btn--block account__upload" href="/upload">' in page
    assert '<a class="settings-row" href="/settings/consent">' in page
    assert 'href="/account" aria-current="page"' in page


def test_sign_out_is_on_the_account_page():
    """D6: the bottom nav has none, so this is the only way out (test_layout)."""
    form = render("account.html").split('<form method="post" action="/logout"', 1)[1]
    form = form.split("</form>", 1)[0]
    assert '<input type="hidden" name="csrf_token" value="x">' in form
    assert '<button class="btn btn--text" type="submit">Sign out</button>' in form


def test_delete_keeps_its_field_and_greys_the_button_until_ticked():
    page = render("delete_confirm.html")
    assert '<form method="post" action="/account/delete" class="delete-form">' in page
    assert 'class="choice__input delete-form__confirm" type="checkbox" name="understood" value="yes"' in page
    assert '<button class="btn btn--primary btn--block delete-form__submit" type="submit">' in page
    assert '<p class="field__error field__error--block" role="alert">Tick the box to confirm.</p>' in page


def test_invite_keeps_its_field_names_and_what_the_browser_needs():
    page = render("invite.html")
    for name, autocomplete in (("display_name", "name"), ("login_id", "username"),
                               ("password", "new-password")):
        assert f'name="{name}"' in page and f'autocomplete="{autocomplete}"' in page
    assert 'minlength="12"' in page
    assert '<form method="post" action="/invite/ABC">' in page


def test_no_page_in_this_batch_has_the_kits_new_lines():
    for name in CONTEXT:
        page = render(name)
        assert "Back to the Scope page" not in page and "I already have an account" not in page
