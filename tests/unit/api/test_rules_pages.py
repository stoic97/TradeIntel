"""The screens where a trader sets his own rules by tapping, and the page that counts them.

His rules, our counting, never our suggestion: no text box, nothing chosen in advance,
nothing ranked or praised, and a rule is never edited once set.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import func, select

from services.production.db import models as m
from services.production.db.session import make_session
from services.production.rules import adherence as A
from services.production.rules import chips
from tests.conftest import TEST_FILE_KEY
from tests.unit.api.test_read_again import send
from tests.unit.api.test_read_again import words as _words
from tests.unit.api.test_upload import CSRF, client, engine  # noqa: F401

SCREENS = ("/rules", "/rules/today", "/rules/set", "/rules/set?factor=most_trades",
           "/rules/click", "/rules/click?book=Other")
NUDGES = ("recommend", "we suggest", "suggested", "best", "better", "good rule", "you should", "try ")
NOT_OURS = ("your rule", "your plan", "your system")  # the framework's own language rule


def words(page: str) -> str:
    """Read aloud: a tag closing just before a full stop leaves no space before it."""
    return _words(page).replace(" .", ".")


def token(client) -> str:  # noqa: F811
    return CSRF.search(client.get("/rules/today").text).group(1)


def declarations(engine) -> list[m.RuleDeclaration]:  # noqa: F811
    with make_session(engine) as sess:
        return list(sess.scalars(select(m.RuleDeclaration).order_by(m.RuleDeclaration.id)))


def test_every_screen_opens_signed_in(client):  # noqa: F811
    for path in SCREENS:
        assert client.get(path).status_code == 200, path


def test_signed_out_they_ask_for_sign_in(engine):  # noqa: F811
    from fastapi.testclient import TestClient

    from services.production.api.app import create_app
    for path in SCREENS:
        assert TestClient(create_app()).get(path, follow_redirects=False).status_code == 303


def test_no_screen_has_a_text_input(client):  # noqa: F811
    send(client)
    pages = [client.get(p).text for p in SCREENS]
    pages.append(client.post("/rules/click", data={"book": "Other", "reason": "My setup",
                                                    "csrf_token": token(client)}).text)
    for page in pages:
        assert "<textarea" not in page
        for tag in re.findall(r"<input[^>]*>", page):
            assert 'type="hidden"' in tag, tag


def test_nothing_is_chosen_in_advance_ranked_or_praised(client):  # noqa: F811
    send(client)
    for path in SCREENS:
        page = client.get(path).text
        for mark in ("checked", "selected", 'aria-pressed="true"', "recommended", "btn--primary"):
            assert mark not in page.split("<main", 1)[1], (path, mark)
        said = words(page).lower()
        for nudge in NUDGES + NOT_OURS:
            assert nudge not in said, (path, nudge)


def test_the_chips_are_shown_alike_in_their_listed_order(client):  # noqa: F811
    page = client.get("/rules/today").text
    for key in chips.BEFORE_SESSION:
        f = chips.FACTORS[key]
        form = page[page.index(f'name="factor" value="{key}"'):]
        form = form[:form.index("</form>")]
        assert re.findall(r'name="value" value="(\d+)"', form) == [str(v) for v in f.values]
        assert len(set(re.findall(r'<button class="([^"]+)"', form))) == 1


def test_a_tap_sets_a_dated_rule_for_today(client, engine):  # noqa: F811
    before = datetime.now(UTC)
    r = client.post("/rules/today", data={"factor": "most_trades", "value": "3",
                                          "csrf_token": token(client)}, follow_redirects=False)
    assert r.status_code == 303
    (rule,) = declarations(engine)
    assert (rule.factor, rule.value, rule.screen) == ("most_trades", 3, "before_session")
    assert rule.applies_from == rule.applies_to and rule.declared_at >= before
    assert rule.text == "At most 3 trades in a day"
    assert "At most 3 trades in a day" in words(client.get("/rules/today").text)


def test_a_chip_the_lists_dont_hold_is_refused(client, engine):  # noqa: F811
    for data in ({"factor": "most_trades", "value": "7"}, {"factor": "most_lots", "value": "2"},
                 {"factor": "nonsense", "value": "1"}, {"factor": "most_trades", "value": "x"}):
        r = client.post("/rules/today", data={**data, "csrf_token": token(client)})
        assert r.status_code == 400, data
    assert declarations(engine) == []


def test_a_rule_is_never_edited_a_newer_one_is_added(client, engine):  # noqa: F811
    for value in ("3", "5"):
        client.post("/rules/today", data={"factor": "most_trades", "value": value,
                                          "csrf_token": token(client)})
    first, second = declarations(engine)
    assert (first.value, second.value) == (3, 5) and first.declared_at <= second.declared_at
    assert issubclass(m.RuleDeclaration, m._InsertOnly)
    routes = {getattr(r, "path", "") for r in client.app.routes}
    assert not [p for p in routes if p.startswith("/rules") and ("edit" in p or "{" in p)]


def test_a_standing_rule_takes_two_taps_and_counts_from_then_on(client, engine):  # noqa: F811
    page = client.get("/rules/set").text
    assert 'href="/rules/set?factor=most_lots"' in page
    r = client.post("/rules/set", data={"factor": "most_lots", "value": "2",
                                        "csrf_token": token(client)}, follow_redirects=False)
    assert r.status_code == 303
    (rule,) = declarations(engine)
    assert rule.applies_to is None and rule.screen == "standing"


def test_count_and_cost_come_first_and_not_enough_trades_yet_renders(client, engine):  # noqa: F811
    send(client)  # six trades, early January 2024, no charges column
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        sess.add(m.RuleDeclaration(trader_id=trader.id, text="At most 5 lots a trade",
                                   declared_at=datetime(2024, 1, 1, tzinfo=UTC), factor="most_lots",
                                   value=5, applies_from="2024-01-01", applies_to=None,
                                   screen="standing"))
        sess.commit()
    said = words(client.get("/rules").text)
    assert "6 trades counted. Your file has no charges, so their cost isn't known." in said
    assert "Not enough trades yet: 6 of 30." in said
    assert said.index("6 trades counted") < said.index("Not enough trades yet")
    assert "Kept on" not in said


def test_at_the_number_stated_at_the_start_it_says_how_often_it_was_kept(client, engine, monkeypatch):  # noqa: F811
    send(client)
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        sess.add(m.RuleDeclaration(trader_id=trader.id, text="At most 5 lots a trade",
                                   declared_at=datetime(2024, 1, 1, tzinfo=UTC), factor="most_lots",
                                   value=5, applies_from="2024-01-01", applies_to=None,
                                   screen="standing"))
        sess.commit()
    monkeypatch.setattr(A, "VERDICT_AT", 6)
    said = words(client.get("/rules").text)
    assert "Kept on 6 of 6 trades." in said
    assert "Not enough trades yet" not in said


def test_before_a_trade_two_taps_store_a_note_and_show_his_own_counts(client, engine):  # noqa: F811
    send(client)
    page = client.get("/rules/click").text
    books = re.findall(r'href="/rules/click\?book=([^"]+)"', page)
    assert "Other" in books and len(books) >= 2
    r = client.post("/rules/click", data={"book": "Other", "reason": "My setup",
                                          "csrf_token": token(client)})
    said = words(r.text)
    assert "Noted: Other, My setup." in said
    assert "In Other your file has 6 trades" in said
    with make_session(engine) as sess:
        assert sess.scalar(select(func.count()).select_from(m.PreTradeNote)) == 1
    bad = client.post("/rules/click", data={"book": "Other", "reason": "Because I said so",
                                            "csrf_token": token(client)})
    assert bad.status_code == 400


def test_deleting_the_account_takes_his_rules_and_notes(client, engine, tmp_path):  # noqa: F811
    from services.production.accounts import deletion
    from services.production.accounts.file_store import FileStore
    client.post("/rules/today", data={"factor": "most_trades", "value": "3", "csrf_token": token(client)})
    client.post("/rules/click", data={"book": "Other", "reason": "News", "csrf_token": token(client)})
    store = FileStore(tmp_path, TEST_FILE_KEY)
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        found = deletion.nothing_remains(sess, store, trader.id)
        assert {"rule_declaration", "pre_trade_note"} <= set(found)
        deletion.delete_trader(sess, store, trader=trader)
        sess.commit()
        assert deletion.nothing_remains(sess, store, trader.id) == []


def test_home_leads_to_the_rules(client):  # noqa: F811
    send(client)
    assert 'href="/rules"' in client.get("/").text
