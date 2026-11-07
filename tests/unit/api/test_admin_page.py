"""TICKET-848: /admin, a read-only window on what the app already records.

Every figure in here is invented, for traders and instruments that do not exist. The
page is seeded with the things most likely to leak (notes and refusals holding a rupee
figure) as well as with clean data, because a clean page proves nothing about either.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from services.production import demo
from services.production.accounts import auth
from services.production.accounts.deletion import delete_trader, remove_demo
from services.production.accounts.file_store import FileStore
from services.production.api import routes_events
from services.production.api import scope_map as SM
from services.production.api.app import create_app
from services.production.api.settings import Settings
from services.production.db import models as m
from services.production.db.session import make_session
from services.shared.schemas import scope_v1 as s
from tests.conftest import TEST_SECRET_KEY

ADMIN = "boss"
PASSWORD = "a-long-enough-password"
CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
TEMPLATES = Path("services/production/api/templates")
THEN = datetime(2026, 3, 2, 4, 30, tzinfo=UTC)
RUNNING = "aaa1111"
OLD = "bbb2222"

PLANTED_RUPEES = "₹98,765"
"""What a trader might type, or a refusal might carry. It must not reach the page."""


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("ADMIN_LOGIN_IDS", ADMIN)
    application = create_app()
    application.state.code_version = RUNNING
    return application


@pytest.fixture()
def engine(app):
    return app.state.engine


def add_trader(engine, login_id, *, dev=False, name=None, joined=THEN) -> int:
    with make_session(engine) as sess:
        trader = m.Trader(display_name=name or login_id.title(), login_id=login_id,
                          password_hash="not-a-real-hash", created_at=joined,
                          development_data=dev)
        sess.add(trader)
        sess.commit()
        return trader.id


def signed_in(app, trader_id: int | None = None) -> TestClient:
    client = TestClient(app, follow_redirects=False)
    if trader_id is not None:
        with make_session(app.state.engine) as sess:
            trader = sess.get(m.Trader, trader_id)
            password_hash = trader.password_hash if trader else "an account that has gone"
        session = auth.new_session(trader_id, password_hash, TEST_SECRET_KEY)
        client.cookies.set(auth.SESSION_COOKIE, auth.seal_session(session, TEST_SECRET_KEY))
    return client


def admin_client(app, engine) -> TestClient:
    return signed_in(app, add_trader(engine, ADMIN))


def admin_page(app, engine) -> str:
    response = admin_client(app, engine).get("/admin")
    assert response.status_code == 200, "the page itself did not draw"
    return response.text


def add_import(sess, trader_id, *, version=RUNNING, outcome=s.ImportOutcome.ACCEPTED_WITH_EXCLUSIONS,
               rejection=None, rows=(10, 8, 2), at=THEN, source="A", trips=0,
               raw_file_id=None) -> m.Import:
    if raw_file_id is None:
        raw = m.RawFile(trader_id=trader_id, sha256=f"{trader_id}-{at.isoformat()}-{version}",
                        original_name="tradebook.csv", size=1, stored_path="nowhere", uploaded_at=at)
        sess.add(raw)
        sess.flush()
        raw_file_id = raw.id
    imp = m.Import(trader_id=trader_id, raw_file_id=raw_file_id, source_account=source,
                   trips_reconstructed=trips,
                   adapter_id="made-up", adapter_version="1", filemap_version="1",
                   code_version=version, outcome=outcome, rejection_text=rejection,
                   rows_in=rows[0], rows_parsed=rows[1], rows_excluded=rows[2],
                   fees_available=False, version_no=1, created_at=at)
    sess.add(imp)
    sess.flush()
    return imp


def add_record(sess, trader_id, *, source="A", at=THEN) -> m.Import:
    """An upload the report can read: it is the import with trades that a report reads."""
    return add_import(sess, trader_id, source=source, at=at, trips=1)


def add_dwell(sess, trader_id, key, event_name="view", *, ms=60_000, surface="mirror_line", at=THEN):
    sess.add(m.DwellEvent(trader_id=trader_id, surface=surface, key=key, event=event_name,
                          at=at, duration_ms=ms))


def add_journal(sess, trader_id, import_id, *, opened=None) -> m.Journal:
    journal = m.Journal(trader_id=trader_id, import_id=import_id, unit=s.JournalUnit.DAY,
                        period_start="2026-03-02", period_end="2026-03-02", version_no=1,
                        generated_at=THEN, opened_at=opened, trip_ids="[]", sections="{}")
    sess.add(journal)
    sess.flush()
    return journal


def add_field_entry(sess, journal_id, value=f"felt fine at {PLANTED_RUPEES}", at=THEN):
    sess.add(m.JournalFieldEntry(journal_id=journal_id, field="note", value=value, entered_at=at,
                                 capture_phase=s.CapturePhase.AFTER_CLOSE))


def add_budget(sess, trader_id, at=THEN):
    sess.add(m.RiskBudgetDeclaration(trader_id=trader_id, value=Decimal(4321), unit="PCT",
                                     capital_amount=Decimal(876543), effective_from="2026-03-02",
                                     declared_at=at))


def add_charges(sess, trader_id, *, days="{}", at=THEN) -> m.ChargeStatement:
    raw = m.RawFile(trader_id=trader_id, sha256=f"charges-{trader_id}", original_name="charges.csv",
                    size=1, stored_path="nowhere", uploaded_at=at)
    sess.add(raw)
    sess.flush()
    return m.ChargeStatement(trader_id=trader_id, raw_file_id=raw.id, reader="made-up", days=days,
                             uploaded_at=at)


def add_consent(sess, trader_id, *, granted=True, purpose=s.ConsentPurpose.DIAGNOSIS, at=THEN):
    sess.add(m.ConsentEvent(trader_id=trader_id, purpose=purpose, scope="v1", terms_version="1",
                            granted=granted, at=at, method="web", wording_shown="the words"))


def seed_everything(engine, trader_id: int) -> None:
    """One of every row the page reads, with a rupee figure wherever free text can hold one."""
    with make_session(engine) as sess:
        add_consent(sess, trader_id)
        add_consent(sess, trader_id, granted=False, purpose=s.ConsentPurpose.ENGINE_TESTING)
        imp = add_import(sess, trader_id, version=OLD)
        add_import(sess, trader_id, outcome=s.ImportOutcome.REJECTED, rows=(1, 0, 0),
                   rejection=f"Refused, it adds up to {PLANTED_RUPEES}.", at=THEN + timedelta(hours=1))
        sess.add(m.ImportRow(import_id=imp.id, row_no=1, raw_text=f"made-up,{PLANTED_RUPEES}",
                             status="PARSED", reason=None, flag=s.RowFlag.SUSPECTED_DUPLICATE))
        sess.add(m.Trip(import_id=imp.id, trip_id="t1", trading_day="2026-03-02", gross=Decimal(55501),
                        fees=Decimal(55502), net=Decimal(55503), fees_available=False,
                        risk_unit_source=s.RiskUnitSourceV1.UNAVAILABLE))
        for key in SM.FACTS:
            add_dwell(sess, trader_id, key)
        add_dwell(sess, trader_id, "money", "drawer_open", ms=None)
        answer = m.ChapterFeedback(trader_id=trader_id, chapter=1, answer="wrong",
                                   import_id=imp.id, answered_at=THEN)
        sess.add(answer)
        sess.flush()
        sess.add(m.ChapterFeedbackReason(feedback_id=answer.id, reason="wrong_facts", given_at=THEN))
        sess.add(m.ReportFeedback(trader_id=trader_id, import_id=imp.id, answer="wrong",
                                  note=f"I made {PLANTED_RUPEES}", answered_at=THEN))
        sess.add(m.GuessAnswer(trader_id=trader_id, answer="unknown", labels_version="x",
                               import_id=imp.id, answered_at=THEN))
        sess.add(m.LeavingCardShown(trader_id=trader_id, copy_version="x", shown_at=THEN))
        sess.add(m.LeavingCardAnswer(trader_id=trader_id, outcome="answered",
                                     answer=f"it cost {PLANTED_RUPEES}", copy_version="x",
                                     answered_at=THEN))
        journal = add_journal(sess, trader_id, imp.id, opened=THEN)
        add_field_entry(sess, journal.id)
        sess.add(m.WtpAsked(trader_id=trader_id, journal_id=journal.id, asked_at=THEN))
        sess.add(m.WtpAnswer(trader_id=trader_id, journal_id=journal.id, answer="maybe",
                             free_text=f"not at {PLANTED_RUPEES}", uploads_so_far=1,
                             days_since_first_upload=1, asked_at=THEN))
        add_budget(sess, trader_id)
        sess.add(add_charges(sess, trader_id, days='{"2026-03-02": "55504"}'))
        sess.commit()


def view(app, engine) -> dict:
    from services.production.api import admin_view

    with make_session(engine) as sess:
        return admin_view.build(sess, running_version=app.state.code_version,
                                production=app.state.settings.production)


def row_of(the_view: dict, login_id: str) -> dict:
    return next(r for r in the_view["rows"] if r["login_id"] == login_id)


def row_counts(engine) -> dict[str, int]:
    with make_session(engine) as sess:
        return {t.name: sess.scalar(select(func.count()).select_from(t))
                for t in m.Base.metadata.sorted_tables}


# ---------- Who sees it ----------


def test_the_list_is_read_from_settings_trimmed_with_blanks_dropped(monkeypatch):
    monkeypatch.setenv("ADMIN_LOGIN_IDS", " boss , other,, ")
    assert Settings.from_env().admin_login_ids == frozenset({"boss", "other"})


@pytest.mark.parametrize("value", [None, "", "  ", " , ,"])
def test_an_empty_or_unset_list_means_no_admins_and_the_app_still_starts(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("ADMIN_LOGIN_IDS", raising=False)
    else:
        monkeypatch.setenv("ADMIN_LOGIN_IDS", value)
    assert Settings.from_env().admin_login_ids == frozenset()
    application = create_app()
    trader_id = add_trader(application.state.engine, ADMIN)
    assert signed_in(application, trader_id).get("/admin").status_code == 404


def test_a_settings_built_without_the_list_has_no_admins():
    built = Settings(database_url="sqlite://", file_store=Path("."), secret_key="k",
                     file_key="k", production=False)
    assert built.admin_login_ids == frozenset()


def test_an_admin_sees_the_page(app, engine):
    response = admin_client(app, engine).get("/admin")
    assert response.status_code == 200
    assert "<title>" in response.text


def test_a_signed_out_visitor_gets_the_same_404_as_any_unknown_address(app):
    client = signed_in(app)
    unknown, admin = client.get("/no-such-page"), client.get("/admin")
    assert admin.status_code == unknown.status_code == 404
    assert admin.text == unknown.text


def test_another_trader_gets_the_same_404_as_any_unknown_address(app, engine):
    client = signed_in(app, add_trader(engine, "someone"))
    unknown, admin = client.get("/no-such-page"), client.get("/admin")
    assert admin.status_code == 404
    assert admin.text == unknown.text


def test_a_login_id_differing_only_in_case_is_not_an_admin(app, engine):
    assert signed_in(app, add_trader(engine, ADMIN.upper())).get("/admin").status_code == 404


def test_a_trailing_slash_does_not_give_the_page_away_with_a_redirect(app):
    client = signed_in(app)
    unknown, admin = client.get("/no-such-page/"), client.get("/admin/")
    assert admin.status_code == 404
    assert admin.text == unknown.text


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
@pytest.mark.parametrize("who", ["signed out", "trader", "admin"])
def test_another_method_is_a_404_too_not_a_405_that_says_something_is_here(app, engine, method, who):
    ids = {"signed out": None, "trader": add_trader(engine, "someone"),
           "admin": add_trader(engine, ADMIN)}
    client = signed_in(app, ids[who])
    unknown, admin = client.request(method, "/no-such-page"), client.request(method, "/admin")
    assert admin.status_code == 404
    assert admin.text == unknown.text
    assert "allow" not in admin.headers


def test_a_method_refused_elsewhere_is_still_a_405(app):
    assert signed_in(app).delete("/signup").status_code == 405


def every_route(routes):
    """app.routes holds each include_router as a wrapper, so a flat walk finds no route at all."""
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from every_route(included.routes)
        else:
            yield route


def test_the_walk_of_the_routes_really_reaches_them(app):
    methods = {r.path: r.methods for r in every_route(app.routes) if isinstance(r, APIRoute)}
    assert "POST" in methods["/signup"], "a walk that misses this would pass whatever /admin did"


def test_only_get_routes_exist_under_admin(app):
    found = [r for r in every_route(app.routes)
             if isinstance(r, APIRoute) and r.path.startswith("/admin")]
    assert {r.path for r in found} == {"/admin", "/admin/"}
    for route in found:
        assert route.methods <= {"GET"}, route.path


def test_no_other_template_links_to_the_page():
    for path in TEMPLATES.rglob("*.html"):
        if path.name != "admin.html":
            assert "/admin" not in path.read_text(), path


def test_admin_is_no_role_on_the_account():
    assert not [c.name for c in m.Trader.__table__.columns
                if "admin" in c.name or "role" in c.name]


def test_the_page_has_no_form_or_control(app, engine):
    seed_everything(engine, add_trader(engine, "someone"))
    page = admin_page(app, engine)
    for tag in ("<form", "<button", "<input", "<select"):
        assert tag not in page, tag


# ---------- Sign-up cannot make an admin ----------


def sign_up(app, login_id):
    client = TestClient(app, follow_redirects=False)
    csrf = CSRF.search(client.get("/signup").text).group(1)
    return client.post("/signup", data={"login_id": login_id, "display_name": "Stranger",
                                        "password": PASSWORD, "csrf_token": csrf})


def traders_named(engine, login_id) -> int:
    with make_session(engine) as sess:
        return len(sess.scalars(select(m.Trader).where(m.Trader.login_id == login_id)).all())


def test_a_free_id_on_the_list_is_refused_at_sign_up_as_taken(app, engine):
    response = sign_up(app, ADMIN)
    assert response.status_code == 400
    assert "That login id is taken." in response.text
    assert traders_named(engine, ADMIN) == 0
    assert response.cookies.get(auth.SESSION_COOKIE) is None


def test_the_refusal_reads_exactly_as_a_really_taken_id_does(app, engine):
    add_trader(engine, "taken-already")
    def page_says(response):
        return re.sub(r'value="[^"]*"', "", response.text)
    assert page_says(sign_up(app, ADMIN)) == page_says(sign_up(app, "taken-already"))


def test_the_list_is_matched_after_trimming_as_a_login_id_is_stored(app, engine):
    response = sign_up(app, f"  {ADMIN}  ")
    assert response.status_code == 400
    assert traders_named(engine, ADMIN) == 0


def test_an_id_not_on_the_list_still_signs_up(app, engine):
    assert sign_up(app, "newcomer").status_code == 303
    assert sign_up(app, ADMIN.upper()).status_code == 303  # exact, like the check at /admin


def test_with_no_list_every_free_id_signs_up_and_none_is_an_admin(monkeypatch):
    monkeypatch.delenv("ADMIN_LOGIN_IDS", raising=False)
    application = create_app()
    assert sign_up(application, ADMIN).status_code == 303
    with make_session(application.state.engine) as sess:
        trader_id = sess.scalars(select(m.Trader.id)).one()
    assert signed_in(application, trader_id).get("/admin").status_code == 404


def test_an_admin_who_deleted_his_account_cannot_be_re_registered_by_a_stranger(app, engine):
    trader_id = add_trader(engine, ADMIN)
    with make_session(engine) as sess:
        store = FileStore(root=Path(os.environ["SCOPE_FILES"]), key=os.environ["SCOPE_FILE_KEY"])
        delete_trader(sess, store, trader=sess.get(m.Trader, trader_id))
        sess.commit()
    assert sign_up(app, ADMIN).status_code == 400
    assert traders_named(engine, ADMIN) == 0
    assert signed_in(app, trader_id).get("/admin").status_code == 404


def test_the_deploy_runbook_names_the_setting():
    assert "ADMIN_LOGIN_IDS" in Path("docs/runbooks/deploy.md").read_text()


# ---------- A view is logged, and is the only write ----------


def test_a_view_writes_one_admin_action_and_nothing_else(app, engine):
    seed_everything(engine, add_trader(engine, "someone"))
    client = admin_client(app, engine)
    before = row_counts(engine)
    assert client.get("/admin").status_code == 200
    after = row_counts(engine)
    assert {t: after[t] - before[t] for t in after if after[t] != before[t]} == {"admin_action": 1}


def test_the_action_names_the_account_by_id_so_no_login_id_outlives_a_deletion(app, engine):
    trader_id = add_trader(engine, ADMIN)
    signed_in(app, trader_id).get("/admin")
    with make_session(engine) as sess:
        action = sess.scalars(select(m.AdminAction)).one()
        assert (action.actor, action.action, action.target) == (f"trader:{trader_id}", "admin_view", None)
        assert action.at is not None


def test_a_refused_visit_writes_nothing(app, engine):
    client = signed_in(app, add_trader(engine, "someone"))
    before = row_counts(engine)
    client.get("/admin")
    signed_in(app).get("/admin")
    assert row_counts(engine) == before


# ---------- Hard limits ----------


def test_the_dwell_vocabulary_is_untouched():
    assert routes_events.SURFACES == {"mirror_line", "journal_section"}
    assert routes_events.EVENTS == {"view", "drawer_open", "leave"}


def test_the_page_carries_no_script(app, engine):
    page = admin_page(app, engine)
    assert "<script" not in page
    assert not re.search(r"\son[a-z]+=", page)


def test_other_pages_keep_the_layouts_scripts(app):
    assert '<script src="/static/js/htmx.min.js" defer></script>' in signed_in(app).get("/login").text


def test_no_rupee_sign_or_money_field_on_a_page_seeded_with_them(app, engine):
    trader_id = add_trader(engine, "someone")
    seed_everything(engine, trader_id)
    page = admin_page(app, engine)
    assert "₹" not in page
    assert "98,765" not in page
    # the budget, the capital, a trade, a day's charges
    for figure in ("4321", "876543", "55501", "55502", "55503", "55504"):
        assert figure not in page, figure
    for field in ("p&amp;l", "p&l", "pnl", "gross", "capital", "premium"):
        assert field not in page.lower(), field
    assert not re.search(r"\b(net|fees)\b", page.lower())


def test_a_note_shows_as_the_fact_of_a_note_and_the_answer_stands(app, engine):
    trader_id = add_trader(engine, "someone")
    seed_everything(engine, trader_id)
    row = row_of(view(app, engine), "someone")
    assert row["report"] == "Wrong, with a note"
    assert row["leaving"] == "answered"
    assert row["wtp"] == "maybe, with a note"


def test_no_free_text_of_any_kind_reaches_the_page(app, engine):
    trader_id = add_trader(engine, "someone")
    seed_everything(engine, trader_id)
    page = admin_page(app, engine)
    for typed in ("I made", "it cost", "felt fine", "not at", "adds up to", "the words"):
        assert typed not in page, typed


def test_a_rupee_sign_in_a_name_does_not_reach_the_page(app, engine):
    add_trader(engine, f"rich{PLANTED_RUPEES}", name=f"Mr {PLANTED_RUPEES}")
    page = admin_page(app, engine)
    assert "₹" not in page


def test_a_strangers_name_is_escaped_on_the_admins_page(app, engine):
    add_trader(engine, "someone", name="<script>alert('x')</script>")
    page = admin_page(app, engine)
    assert "<script" not in page
    assert "&lt;script&gt;" in page


def test_a_dwell_key_a_browser_made_up_never_reaches_the_page(app, engine):
    """/events takes any key without a digit, so a stored key is not known to be clean."""
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_dwell(sess, trader_id, "₹rupees<b>", "drawer_open", ms=None)
        add_dwell(sess, trader_id, "₹rupees<b>", "view")
        sess.commit()
    page = admin_page(app, engine)
    assert "₹" not in page and "rupees" not in page


# ---------- The cards ----------


def people_card(app, engine) -> tuple[int, int, int]:
    cards = view(app, engine)["cards"]
    return cards["signed_up"], cards["tried_demo"], cards["uploaded_real"]


def test_the_top_card_keeps_signing_up_the_demo_and_a_real_file_apart(app, engine):
    add_trader(engine, "only-signed-up")
    on_demo, on_real = add_trader(engine, "on-demo"), add_trader(engine, "on-real")
    with make_session(engine) as sess:
        add_record(sess, on_demo, source=demo.ACCOUNT)
        add_record(sess, on_real)
        sess.commit()
    assert people_card(app, engine) == (3, 1, 1)
    page = admin_page(app, engine)
    assert "Signed up / tried the demo / uploaded a real file" in page
    assert "4 / 1 / 1" in page  # the admin who asks has signed up too


def test_a_demo_only_account_has_a_demo_file_and_no_upload_of_a_real_one(app, engine):
    # TICKET-865: the demo is an upload to the pipeline, and must not read as one here.
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_record(sess, trader_id, source=demo.ACCOUNT)
        sess.commit()
    assert row_of(view(app, engine), "someone")["file"] == "demo"
    assert people_card(app, engine) == (1, 1, 0)


def test_a_real_only_account_has_a_real_file(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_record(sess, trader_id)
        sess.commit()
    assert row_of(view(app, engine), "someone")["file"] == "real"
    assert people_card(app, engine) == (1, 0, 1)


def test_the_demo_then_a_real_file_reads_real_because_the_real_upload_replaces_it(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_record(sess, trader_id, source=demo.ACCOUNT)
        sess.commit()
    with make_session(engine) as sess:
        store = FileStore(root=Path(os.environ["SCOPE_FILES"]), key=os.environ["SCOPE_FILE_KEY"])
        remove_demo(sess, store, trader=sess.get(m.Trader, trader_id))
        add_record(sess, trader_id, at=THEN + timedelta(days=1))
        sess.commit()
    assert row_of(view(app, engine), "someone")["file"] == "real"
    # remove_demo leaves no row of the demo, so nothing stored can say he ever tried it.
    assert people_card(app, engine) == (1, 0, 1)


def test_with_no_upload_the_file_is_none(app, engine):
    add_trader(engine, "someone")
    assert row_of(view(app, engine), "someone")["file"] == "none"


def test_a_refused_real_file_was_brought_but_gives_no_record_to_read(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_import(sess, trader_id, outcome=s.ImportOutcome.REJECTED, rows=(1, 0, 0))
        sess.commit()
    assert row_of(view(app, engine), "someone")["file"] == "none"
    assert people_card(app, engine) == (1, 0, 1)
    cards = view(app, engine)["cards"]
    assert cards["read_none"] == 0, "with no report there is nothing to have left unread"


def test_a_real_file_refused_while_the_demo_stands_leaves_the_report_on_the_demo(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_record(sess, trader_id, source=demo.ACCOUNT)
        add_import(sess, trader_id, outcome=s.ImportOutcome.REJECTED, rows=(1, 0, 0),
                   at=THEN + timedelta(hours=1))
        sess.commit()
    assert row_of(view(app, engine), "someone")["file"] == "demo"
    assert people_card(app, engine) == (1, 1, 1)


def test_the_file_column_is_drawn_for_each_trader(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_record(sess, trader_id, source=demo.ACCOUNT)
        sess.commit()
    page = admin_page(app, engine)
    assert "<th>File</th>" in page
    assert "<td>demo</td>" in page


def test_the_notes_say_what_the_file_column_and_the_card_cannot_know(app, engine):
    page = admin_page(app, engine)
    assert "<strong>File:</strong>" in page
    assert "A real upload removes the demo" in page
    assert "a refused file counts" in page


def test_a_demo_reader_is_counted_apart_from_a_real_file_reader(app, engine):
    # TICKET-865: 3 real readers (all, some, none) and 2 demo readers (some, none).
    every, some, none = (add_trader(engine, n) for n in ("every", "some", "none"))
    demo_some, demo_none = (add_trader(engine, n) for n in ("demo-some", "demo-none"))
    with make_session(engine) as sess:
        for trader_id in (every, some, none):
            add_record(sess, trader_id)
        for trader_id in (demo_some, demo_none):
            add_record(sess, trader_id, source=demo.ACCOUNT)
        for key in SM.FACTS:
            add_dwell(sess, every, key)
        add_dwell(sess, some, "money")
        add_dwell(sess, demo_some, "money")
        sess.commit()
    cards = view(app, engine)["cards"]
    assert (cards["read_all"], cards["stopped_early"], cards["read_none"]) == (1, 1, 1)
    assert (cards["demo_read_all"], cards["demo_stopped_early"], cards["demo_read_none"]) == (0, 1, 1)


def test_each_reading_card_says_which_group_it_counts(app, engine):
    page = admin_page(app, engine)
    assert "Of those who uploaded" not in page
    assert "Real-file readers: read all" in page
    assert "Demo readers: read all" in page
    assert "Of those whose report reads a real file." in page
    assert "Of those whose report reads the demo." in page


def test_said_wrong_says_how_many_of_them_are_on_the_demo(app, engine):
    on_real, on_demo = add_trader(engine, "on-real"), add_trader(engine, "on-demo")
    with make_session(engine) as sess:
        for trader_id, source in ((on_real, "A"), (on_demo, demo.ACCOUNT)):
            imp = add_record(sess, trader_id, source=source)
            sess.add(m.ChapterFeedback(trader_id=trader_id, chapter=1, answer="wrong",
                                       import_id=imp.id, answered_at=THEN))
        sess.commit()
    cards = view(app, engine)["cards"]
    assert (cards["said_wrong"], cards["said_wrong_demo"]) == (2, 1)
    assert "On the demo: 1." in admin_page(app, engine)


def test_said_wrong_counts_traders_not_answers(app, engine):
    trader_id, happy = add_trader(engine, "someone"), add_trader(engine, "happy")
    with make_session(engine) as sess:
        imp, other = add_import(sess, trader_id), add_import(sess, happy)
        for chapter in (1, 2):
            sess.add(m.ChapterFeedback(trader_id=trader_id, chapter=chapter, answer="wrong",
                                       import_id=imp.id, answered_at=THEN))
        sess.add(m.ChapterFeedback(trader_id=happy, chapter=1, answer="accurate",
                                   import_id=other.id, answered_at=THEN))
        sess.commit()
    assert view(app, engine)["cards"]["said_wrong"] == 1


def test_the_reveal_cards_stay_empty_whatever_later_steps_are_stored(app, engine):
    """/mirror/reveal writes nothing, and the budget and chapters are reachable without it."""
    seed_everything(engine, add_trader(engine, "someone"))
    cards = view(app, engine)["cards"]
    assert cards["reached_reveal"] == "—"
    assert cards["upload_to_reveal"] == "—"


def test_the_reveal_route_is_still_a_get_that_stores_nothing():
    """If it starts leaving a trace, the "—" above can become a count."""
    source = Path("services/production/api/routes_reveal.py").read_text()
    body = source[source.index('@router.get("/mirror/reveal"'):]
    assert "sess.add" not in body and "commit" not in body


def test_the_page_says_why_each_gap_is_a_gap(app, engine):
    page = admin_page(app, engine)
    for says in ("writes nothing", "not visible here", "no deploy table",
                 "not read by this deploy", "not that the figures are wrong"):
        assert says in page, says


# ---------- Facts read ----------


def test_the_count_of_facts_is_the_maps_never_a_literal(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_dwell(sess, trader_id, next(iter(SM.FACTS)))
        sess.commit()
    assert row_of(view(app, engine), "someone")["facts_read"] == f"1 of {len(SM.FACTS)}"
    assert view(app, engine)["fact_total"] == len(SM.FACTS)
    source = (TEMPLATES / "admin.html").read_text()
    assert "12" not in re.sub(r"{#.*?#}", "", source, flags=re.DOTALL)


@pytest.mark.parametrize("old", ["hold", "strike", "holding-time"])
def test_an_old_key_counts_as_the_fact_it_moved_to_and_only_once(app, engine, old):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_dwell(sess, trader_id, old)
        add_dwell(sess, trader_id, "math")
        sess.commit()
    assert row_of(view(app, engine), "someone")["facts_read"] == f"1 of {len(SM.FACTS)}"


def test_the_old_share_key_counts_as_worst_days_where_its_line_now_is(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_dwell(sess, trader_id, "share")
        add_dwell(sess, trader_id, "worst-days")
        sess.commit()
    assert row_of(view(app, engine), "someone")["facts_read"] == f"1 of {len(SM.FACTS)}"


def test_what_is_no_fact_is_not_counted(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_dwell(sess, trader_id, "no-such-fact")
        add_dwell(sess, trader_id, "money", surface="journal_section")
        add_dwell(sess, trader_id, "money", "drawer_open", ms=None)
        sess.commit()
    assert row_of(view(app, engine), "someone")["facts_read"] == f"0 of {len(SM.FACTS)}"


def test_read_all_and_stopped_early_split_the_readers(app, engine):
    everything, some, none = (add_trader(engine, n) for n in ("everything", "some", "none"))
    with make_session(engine) as sess:
        for trader_id in (everything, some, none):
            add_record(sess, trader_id)
        for key in SM.FACTS:
            add_dwell(sess, everything, key)
        add_dwell(sess, some, "money")
        sess.commit()
    cards = view(app, engine)["cards"]
    assert (cards["read_all"], cards["stopped_early"], cards["read_none"]) == (1, 1, 1)


def test_minutes_add_up_the_views_and_drawers_are_counted_apart(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_dwell(sess, trader_id, "money", ms=90_000)
        add_dwell(sess, trader_id, "run", ms=30_000)
        add_dwell(sess, trader_id, "clock", ms=None)
        add_dwell(sess, trader_id, "money", "drawer_open", ms=None)
        add_dwell(sess, trader_id, "money", "drawer_open", ms=None)
        sess.commit()
    row = row_of(view(app, engine), "someone")
    assert (row["minutes"], row["drawer_opens"]) == ("2 min", 2)


# ---------- One row per trader ----------


def step_of(app, engine, login_id="someone") -> str:
    return row_of(view(app, engine), login_id)["step"]


def test_the_furthest_step_starts_at_signed_up(app, engine):
    add_trader(engine, "someone")
    assert step_of(app, engine) == "signed up"


def test_each_stored_step_moves_the_furthest_step_on(app, engine):
    trader_id = add_trader(engine, "someone")

    def then(step, write):
        with make_session(engine) as sess:
            write(sess)
            sess.commit()
        assert step_of(app, engine) == step

    then("consented", lambda sess: add_consent(sess, trader_id))
    then("uploaded", lambda sess: add_import(sess, trader_id))
    with make_session(engine) as sess:
        import_id = sess.scalars(select(m.Import.id)).one()
    then("guess", lambda sess: sess.add(m.GuessAnswer(
        trader_id=trader_id, answer="unknown", labels_version="x", import_id=import_id,
        answered_at=THEN)))
    then("chapter 2", lambda sess: add_dwell(sess, trader_id, "run"))
    then("chapter 3", lambda sess: sess.add(m.ChapterFeedback(
        trader_id=trader_id, chapter=3, answer="accurate", import_id=import_id, answered_at=THEN)))
    then("chapter 4", lambda sess: add_dwell(sess, trader_id, "risk"))
    then("journal", lambda sess: add_journal(sess, trader_id, import_id, opened=THEN))
    then("budget", lambda sess: add_budget(sess, trader_id))


def test_the_furthest_step_of_a_demo_only_account_is_no_upload(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_record(sess, trader_id, source=demo.ACCOUNT)
        sess.commit()
    assert step_of(app, engine) == "loaded the demo"


def test_a_withdrawn_consent_alone_is_not_consented(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_consent(sess, trader_id, granted=False)
        sess.commit()
    assert step_of(app, engine) == "signed up"


def test_a_journal_generated_at_upload_is_no_step_and_none_written(app, engine):
    """Journals are generated by the upload itself, so a row says nothing about him."""
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_journal(sess, trader_id, add_import(sess, trader_id).id)
        sess.commit()
    row = row_of(view(app, engine), "someone")
    assert row["step"] == "uploaded"
    assert row["journals_written"] == 0


def test_journals_written_counts_journals_not_answers(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        imp = add_import(sess, trader_id)
        first, second = add_journal(sess, trader_id, imp.id), add_journal(sess, trader_id, imp.id)
        add_journal(sess, trader_id, imp.id)
        for journal in (first, first, second):
            add_field_entry(sess, journal.id)
        sess.commit()
    row = row_of(view(app, engine), "someone")
    assert row["journals_written"] == 2
    assert row["step"] == "journal"


def test_upload_health_reads_the_latest_file_and_counts_refusals_across_all(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_import(sess, trader_id, rows=(50, 50, 0))
        imp = add_import(sess, trader_id, rows=(10, 7, 2), at=THEN + timedelta(hours=1))
        for row_no, flag in enumerate((s.RowFlag.SUSPECTED_DUPLICATE, s.RowFlag.DUPLICATE_FILL_ID,
                                       s.RowFlag.TRADER_CONFIRMED_DUPLICATE, None)):
            sess.add(m.ImportRow(import_id=imp.id, row_no=row_no, raw_text="x", status="PARSED",
                                 flag=flag))
        add_import(sess, trader_id, outcome=s.ImportOutcome.REJECTED, rows=(1, 0, 0),
                   at=THEN + timedelta(hours=2))
        sess.commit()
    row = row_of(view(app, engine), "someone")
    assert row["rows_read"] == "7 of 10"
    assert row["rows_refused"] == 1, "of 10: 7 read, 2 set aside"
    assert row["uploads_refused"] == 1
    assert row["duplicates"] == 3


def test_a_trader_with_no_upload_shows_empty_health_rather_than_zeros(app, engine):
    add_trader(engine, "someone")
    row = row_of(view(app, engine), "someone")
    assert (row["rows_read"], row["rows_refused"], row["duplicates"]) == ("—", "—", "—")
    assert row["uploads_refused"] == 0


def test_a_byte_identical_upload_stores_nothing_so_only_the_first_counts(app, engine):
    """Through the real route: the second send of a file is refused before anything is written."""
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_consent(sess, trader_id)
        sess.commit()
    client = signed_in(app, trader_id)
    csrf = CSRF.search(client.get("/upload").text).group(1)
    ledger = {"file": ("ledger.csv", b"Date,Narration,Debit,Credit\n2026-03-02,made up,1,2\n", "text/csv")}
    assert client.post("/upload", files=ledger, data={"csrf_token": csrf}).status_code == 303
    assert client.post("/upload", files=ledger, data={"csrf_token": csrf}).status_code == 400
    assert row_of(view(app, engine), "someone")["uploads_refused"] == 1


def test_chapter_answers_show_with_a_reason_where_given(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        imp = add_import(sess, trader_id)
        wrong = m.ChapterFeedback(trader_id=trader_id, chapter=1, answer="wrong",
                                  import_id=imp.id, answered_at=THEN)
        sess.add_all([wrong, m.ChapterFeedback(trader_id=trader_id, chapter=2, answer="not_sure",
                                               import_id=imp.id, answered_at=THEN)])
        sess.flush()
        sess.add(m.ChapterFeedbackReason(feedback_id=wrong.id, reason="wrong_facts", given_at=THEN))
        sess.commit()
    assert row_of(view(app, engine), "someone")["chapters"] == [
        "Wrong: Wrong facts", "Not sure", "—"]


def test_there_is_a_feedback_column_for_each_chapter_that_asks(app, engine):
    add_trader(engine, "someone")
    the_view = view(app, engine)
    assert the_view["feedback_chapters"] == [c.number for c in SM.CHAPTERS if c.feedback]


def test_budget_shows_that_it_is_set_not_what_it_is(app, engine):
    trader_id = add_trader(engine, "someone")
    assert row_of(view(app, engine), "someone")["budget"] == "no"
    with make_session(engine) as sess:
        add_budget(sess, trader_id)
        sess.commit()
    assert row_of(view(app, engine), "someone")["budget"] == "set"


def test_last_activity_is_the_latest_of_dwell_journal_and_upload(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        imp = add_import(sess, trader_id, at=THEN)
        add_dwell(sess, trader_id, "money", at=THEN + timedelta(days=1))
        add_field_entry(sess, add_journal(sess, trader_id, imp.id).id, at=THEN + timedelta(days=2))
        sess.commit()
    assert row_of(view(app, engine), "someone")["last_activity"] == "04 Mar 2026 10:00"  # 04:30 UTC, in IST


LATER = THEN + timedelta(days=10)
LATER_WORDS = "12 Mar 2026 10:00"  # 04:30 UTC, in IST
"""Each source below is the one thing stored that late, so only it can give this time."""


def consent_at(sess, trader_id, imp):
    add_consent(sess, trader_id, at=LATER)


def withdrawal_at(sess, trader_id, imp):
    add_consent(sess, trader_id, granted=False, at=LATER)


def upload_at(sess, trader_id, imp):
    add_import(sess, trader_id, at=LATER)


def reading_at(sess, trader_id, imp):
    add_dwell(sess, trader_id, "money", at=LATER)


def chapter_answer_at(sess, trader_id, imp):
    sess.add(m.ChapterFeedback(trader_id=trader_id, chapter=1, answer="accurate", import_id=imp.id,
                               answered_at=LATER))


def chapter_reason_at(sess, trader_id, imp):
    answer = m.ChapterFeedback(trader_id=trader_id, chapter=1, answer="wrong", import_id=imp.id,
                               answered_at=THEN)
    sess.add(answer)
    sess.flush()
    sess.add(m.ChapterFeedbackReason(feedback_id=answer.id, reason="wrong_facts", given_at=LATER))


def report_answer_at(sess, trader_id, imp):
    sess.add(m.ReportFeedback(trader_id=trader_id, import_id=imp.id, answer="accurate",
                              answered_at=LATER))


def journal_opened_at(sess, trader_id, imp):
    add_journal(sess, trader_id, imp.id, opened=LATER)


def journal_written_at(sess, trader_id, imp):
    add_field_entry(sess, add_journal(sess, trader_id, imp.id).id, at=LATER)


def budget_at(sess, trader_id, imp):
    add_budget(sess, trader_id, at=LATER)


def charges_at(sess, trader_id, imp):
    sess.add(add_charges(sess, trader_id, at=LATER))


def guess_at(sess, trader_id, imp):
    sess.add(m.GuessAnswer(trader_id=trader_id, answer="unknown", labels_version="x",
                           import_id=imp.id, answered_at=LATER))


def leaving_shown_at(sess, trader_id, imp):
    sess.add(m.LeavingCardShown(trader_id=trader_id, copy_version="x", shown_at=LATER))


def leaving_answered_at(sess, trader_id, imp):
    sess.add(m.LeavingCardAnswer(trader_id=trader_id, outcome="answered", answer="words",
                                 copy_version="x", answered_at=LATER))


def would_pay_asked_at(sess, trader_id, imp):
    journal = add_journal(sess, trader_id, imp.id)
    sess.add(m.WtpAsked(trader_id=trader_id, journal_id=journal.id, asked_at=LATER))


def would_pay_answered_at(sess, trader_id, imp):
    journal = add_journal(sess, trader_id, imp.id)
    sess.add(m.WtpAnswer(trader_id=trader_id, journal_id=journal.id, answer="no",
                         uploads_so_far=1, days_since_first_upload=1, asked_at=LATER))


@pytest.mark.parametrize("source", [
    consent_at, withdrawal_at, upload_at, reading_at, chapter_answer_at, chapter_reason_at,
    report_answer_at, journal_opened_at, journal_written_at, budget_at, charges_at, guess_at,
    leaving_shown_at, leaving_answered_at, would_pay_asked_at, would_pay_answered_at,
], ids=lambda source: source.__name__)
def test_last_activity_counts_every_stored_action_of_his(app, engine, source):
    # TICKET-866: what needs an import has one at sign-up time, so it cannot give the time.
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        imp = add_import(sess, trader_id, at=THEN)
        source(sess, trader_id, imp)
        sess.commit()
    assert row_of(view(app, engine), "someone")["last_activity"] == LATER_WORDS


def test_a_journal_the_upload_generated_is_no_activity_of_his(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        imp = add_import(sess, trader_id, at=THEN)
        journal = add_journal(sess, trader_id, imp.id)
        assert journal.generated_at == THEN
        sess.commit()
    assert row_of(view(app, engine), "someone")["last_activity"] == "02 Mar 2026 10:00"


def test_an_account_that_only_signed_up_shows_its_sign_up_time_in_both(app, engine):
    add_trader(engine, "someone")
    row = row_of(view(app, engine), "someone")
    assert row["signed_up"] == row["last_activity"] == "02 Mar 2026 10:00"


def test_signed_up_stays_when_later_activity_moves_the_other(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_consent(sess, trader_id, at=LATER)
        sess.commit()
    row = row_of(view(app, engine), "someone")
    assert (row["signed_up"], row["last_activity"]) == ("02 Mar 2026 10:00", LATER_WORDS)


def test_an_account_stored_before_sign_up_times_were_kept_shows_no_time_and_sorts_last(app, engine):
    add_trader(engine, "old", joined=None)
    add_trader(engine, "someone")
    the_view = view(app, engine)
    row = row_of(the_view, "old")
    assert (row["signed_up"], row["last_activity"]) == ("—", "—")
    assert the_view["rows"][-1]["login_id"] == "old"


def test_the_table_sorts_by_last_activity_whatever_the_source(app, engine):
    add_trader(engine, "signed-up-late", joined=THEN + timedelta(days=2))
    budget_latest, uploaded = add_trader(engine, "budget-latest"), add_trader(engine, "uploaded")
    with make_session(engine) as sess:
        add_import(sess, uploaded, at=THEN + timedelta(days=1))
        add_budget(sess, budget_latest, at=THEN + timedelta(days=3))
        sess.commit()
    assert [r["login_id"] for r in view(app, engine)["rows"]] == [
        "budget-latest", "signed-up-late", "uploaded"]


def test_the_page_names_the_columns_and_says_the_time_is_a_floor(app, engine):
    add_trader(engine, "someone")
    page = admin_page(app, engine)
    assert "<th>Signed up</th><th>Last activity</th>" in page
    assert "Last seen" not in page
    assert "<strong>Last activity:</strong>" in page
    assert "a visit that writes nothing can't show" in page.replace("&#39;", "'")


# ---------- On current code ----------


def current(app, engine, login_id="someone") -> str:
    return row_of(view(app, engine), login_id)["on_current"]


def test_the_latest_import_is_held_against_the_running_version(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_import(sess, trader_id, version=OLD)
        sess.commit()
    assert current(app, engine) == "no"
    with make_session(engine) as sess:
        add_import(sess, trader_id, version=RUNNING, at=THEN + timedelta(hours=1))
        sess.commit()
    assert current(app, engine) == "yes"


def test_a_refused_file_on_this_deploy_does_not_hide_a_record_read_by_an_older_one(app, engine):
    """A refused file reads nothing. What he is looking at is still the old reading."""
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_import(sess, trader_id, version=OLD)
        add_import(sess, trader_id, version=RUNNING, outcome=s.ImportOutcome.REJECTED,
                   at=THEN + timedelta(hours=1))
        sess.commit()
    assert current(app, engine) == "no"


@pytest.mark.parametrize(("stamped", "running"), [("unknown", RUNNING), (OLD, "unknown")])
def test_an_unknown_version_cannot_be_compared(app, engine, stamped, running):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_import(sess, trader_id, version=stamped)
        sess.commit()
    app.state.code_version = running
    assert current(app, engine) == "—"


def test_no_file_read_has_nothing_to_compare(app, engine):
    trader_id = add_trader(engine, "someone")
    assert current(app, engine) == "—"
    with make_session(engine) as sess:
        add_import(sess, trader_id, outcome=s.ImportOutcome.REJECTED)
        sess.commit()
    assert current(app, engine) == "—"


def test_stale_is_drawn_in_red_and_in_words(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_import(sess, trader_id, version=OLD)
        sess.commit()
    page = admin_page(app, engine)
    assert re.search(r'class="[^"]*admin__stale[^"]*"[^>]*>no<', page)


def test_the_running_version_is_on_the_page(app, engine):
    assert RUNNING in admin_page(app, engine)


# ---------- The feed ----------


def feed_text(app, engine) -> list[str]:
    return [line["text"] for line in view(app, engine)["feed"]]


def test_the_feed_is_newest_first_and_says_who_and_what(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        imp = add_import(sess, trader_id, at=THEN)
        journal = add_journal(sess, trader_id, imp.id, opened=THEN + timedelta(hours=3))
        add_dwell(sess, trader_id, "money", "drawer_open", ms=None, at=THEN + timedelta(hours=1))
        sess.add(m.ChapterFeedback(trader_id=trader_id, chapter=2, answer="wrong", import_id=imp.id,
                                   answered_at=THEN + timedelta(hours=2)))
        add_field_entry(sess, journal.id, at=THEN + timedelta(hours=4))
        sess.commit()
    assert feed_text(app, engine) == [
        "someone wrote in a journal",
        "someone opened a journal",
        "someone answered Wrong on chapter 2",
        "someone opened a drawer: Where the money came from",
        "someone uploaded a file: 8 of 10 rows read",
        f"First import on code {RUNNING}",
    ]


def test_a_feed_line_says_the_demo_was_loaded_not_that_a_file_was_uploaded(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_record(sess, trader_id, source=demo.ACCOUNT)
        sess.commit()
    lines = feed_text(app, engine)
    assert "someone loaded the demo" in lines
    assert not [line for line in lines if "uploaded" in line]


def test_reading_the_demo_again_is_not_a_read_of_his_file(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        first = add_record(sess, trader_id, source=demo.ACCOUNT)
        add_import(sess, trader_id, source=demo.ACCOUNT, at=THEN + timedelta(days=1), trips=1,
                   raw_file_id=first.raw_file_id)
        sess.commit()
    lines = feed_text(app, engine)
    assert "someone loaded the demo" in lines
    assert "someone had the demo read again" in lines


def test_the_feed_has_a_limit(app, engine):
    from services.production.api import admin_view

    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        for i in range(admin_view.FEED_LENGTH + 5):
            add_dwell(sess, trader_id, "money", "drawer_open", ms=None, at=THEN + timedelta(minutes=i))
        sess.commit()
    assert len(view(app, engine)["feed"]) == admin_view.FEED_LENGTH


def test_a_refusal_built_from_our_own_words_gives_its_reason(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_import(sess, trader_id, outcome=s.ImportOutcome.REJECTED, rows=(1, 0, 0),
                   rejection="This looks like a funds ledger, and it has no prices. We need the "
                             "trade-level export: on MadeUpBroker it is called 'x' and is under y.")
        sess.commit()
    assert "someone had a file refused: a funds ledger, no prices" in feed_text(app, engine)


@pytest.mark.parametrize("rejection", [
    f"This looks like {PLANTED_RUPEES}, and it has no prices.",
    "This looks like a file of 98765, and it has no prices.",
    f"Refused, it adds up to {PLANTED_RUPEES}.",
    None,
])
def test_any_other_refusal_gives_its_outcome_and_no_words(app, engine, rejection):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_import(sess, trader_id, outcome=s.ImportOutcome.REJECTED, rows=(1, 0, 0),
                   rejection=rejection)
        sess.commit()
    assert "someone had a file refused" in feed_text(app, engine)


def test_the_real_refusal_sentences_all_pass_the_check():
    """Each header the format check can describe, through the real sentence builder."""
    from services.production.api import admin_view
    from services.production.ctr.intake import outcomes as oc

    for header in ("Narration,Debit", "P&L,Symbol", "Tax,Symbol", "a,b,c", "Price,Qty,Time,Other"):
        decision = oc.check_format(f"{header}\n1,2\n")
        assert decision.outcome is s.ImportOutcome.REJECTED, header
        reason = admin_view.refusal_reason(oc.rejection_for(decision))
        assert reason and not re.search(r"\d|₹", reason), header


def test_a_deploy_can_only_be_the_first_import_on_a_version(app, engine):
    trader_id, other = add_trader(engine, "someone"), add_trader(engine, "other")
    with make_session(engine) as sess:
        add_import(sess, trader_id, version=OLD, at=THEN)
        add_import(sess, other, version=OLD, at=THEN + timedelta(hours=1))
        add_import(sess, other, version=RUNNING, at=THEN + timedelta(hours=2))
        add_import(sess, other, version="unknown", at=THEN + timedelta(hours=3))
        sess.commit()
    versions = [t for t in feed_text(app, engine) if t.startswith("First import on code")]
    assert versions == [f"First import on code {RUNNING}", f"First import on code {OLD}"]


def test_feed_lines_for_a_day_and_a_whole_report_say_a_note_exists_and_no_more(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        imp = add_import(sess, trader_id)
        sess.add(m.ReportFeedback(trader_id=trader_id, import_id=imp.id, answer="accurate",
                                  answered_at=THEN))
        sess.add(m.ReportFeedback(trader_id=trader_id, import_id=imp.id, answer="wrong",
                                  trading_day="2026-03-02", note=PLANTED_RUPEES, answered_at=THEN))
        sess.commit()
    said = feed_text(app, engine)
    assert "someone answered Accurate on the whole report" in said
    assert "someone said 02 Mar 2026 looks wrong, with a note" in said


# ---------- The quiet panel ----------


def test_the_most_opened_drawer(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_dwell(sess, trader_id, "strike", "drawer_open", ms=None)
        add_dwell(sess, trader_id, "math", "drawer_open", ms=None)
        add_dwell(sess, trader_id, "money", "drawer_open", ms=None)
        sess.commit()
    assert view(app, engine)["quiet"]["most_opened"] == SM.FACTS["math"].title  # strike is math now


def test_with_no_reading_at_all_the_panel_is_empty_not_guessed(app, engine):
    add_trader(engine, "someone")
    assert view(app, engine)["quiet"]["most_opened"] == "—"


def test_wtp_answers_are_counted_by_answer_with_the_words_left_out(app, engine):
    seed_everything(engine, add_trader(engine, "someone"))
    quiet = view(app, engine)["quiet"]
    assert quiet["wtp"] == {"yes": 0, "no": 0, "maybe": 1}
    assert quiet["wtp_asked"] == 1


def test_deletions_and_declines_are_counted(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_consent(sess, trader_id, granted=False, purpose=s.ConsentPurpose.ENGINE_TESTING)
        sess.add(m.DeletionRecord(trader_id=999, requested_at=THEN, completed_at=THEN))
        sess.commit()
    quiet = view(app, engine)["quiet"]
    assert (quiet["consent_declines"], quiet["deletions"]) == (1, 1)


# ---------- Where readers stop ----------


def fact_row(the_view: dict, key: str) -> dict:
    title = SM.FACTS[key].title
    return next(f for c in the_view["fact_table"]["chapters"] for f in c["facts"]
                if f["title"] == title)


def test_the_table_is_in_report_order_with_every_fact_even_one_nobody_read(app, engine):
    # TICKET-870: the order is the map's, so a fact nobody opened is still a row of its own.
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_record(sess, trader_id)
        add_dwell(sess, trader_id, "not-told")  # the last fact, so a sort by reading would show it
        sess.commit()
    table = view(app, engine)["fact_table"]
    assert [(c["number"], c["name"]) for c in table["chapters"]] == [
        (c.number, c.name) for c in SM.CHAPTERS]
    assert [[f["title"] for f in c["facts"]] for c in table["chapters"]] == [
        [f.title for f in c.facts] for c in SM.CHAPTERS]
    nobody = fact_row(view(app, engine), "worst-days")
    assert (nobody["real_readers"], nobody["real_median"]) == (0, "—")
    assert fact_row(view(app, engine), "not-told")["real_readers"] == 1


def test_real_and_demo_readers_are_counted_apart_with_a_median_for_each(app, engine):
    # Real: 1, 2 and 10 minutes, so the middle one is 2 min. Demo: 30 s alone.
    real = [add_trader(engine, n) for n in ("one", "two", "three")]
    on_demo = add_trader(engine, "on-demo")
    with make_session(engine) as sess:
        for trader_id, ms in zip(real, (60_000, 120_000, 600_000), strict=True):
            add_record(sess, trader_id)
            add_dwell(sess, trader_id, "money", ms=ms)
        add_record(sess, on_demo, source=demo.ACCOUNT)
        add_dwell(sess, on_demo, "money", ms=30_000)
        sess.commit()
    row = fact_row(view(app, engine), "money")
    assert (row["real_readers"], row["real_median"]) == (3, "2 min")
    assert (row["demo_readers"], row["demo_median"]) == (1, "30 s")


def test_an_old_key_adds_to_the_fact_it_moved_to_for_one_reader(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_record(sess, trader_id)
        add_dwell(sess, trader_id, "strike", ms=60_000)
        add_dwell(sess, trader_id, "math", ms=60_000)
        sess.commit()
    row = fact_row(view(app, engine), "math")
    assert (row["real_readers"], row["real_median"]) == (1, "2 min")


def test_a_drawer_opened_is_no_reader_of_the_fact(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_record(sess, trader_id)
        add_dwell(sess, trader_id, "money", "drawer_open", ms=None)
        sess.commit()
    assert fact_row(view(app, engine), "money")["real_readers"] == 0


def test_a_trader_with_no_report_is_in_neither_group(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_dwell(sess, trader_id, "money")
        sess.commit()
    row = fact_row(view(app, engine), "money")
    assert (row["real_readers"], row["demo_readers"]) == (0, 0)
    assert view(app, engine)["fact_table"]["covers"] == "Covers 0 traders: 0 with a real file, 0 on the demo."


def test_the_table_says_how_many_traders_it_covers_because_the_group_is_small(app, engine):
    real, on_demo = add_trader(engine, "real"), add_trader(engine, "on-demo")
    add_trader(engine, "only-signed-up")
    with make_session(engine) as sess:
        add_record(sess, real)
        add_record(sess, on_demo, source=demo.ACCOUNT)
        sess.commit()
    covers = "Covers 2 traders: 1 with a real file, 1 on the demo."
    assert view(app, engine)["fact_table"]["covers"] == covers
    assert covers in admin_page(app, engine)


def test_one_trader_is_covered_in_the_singular(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_record(sess, trader_id)
        sess.commit()
    assert view(app, engine)["fact_table"]["covers"] == "Covers 1 trader: 1 with a real file, 0 on the demo."


def test_the_table_replaces_the_two_lines_and_keeps_the_floors_note(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_record(sess, trader_id)
        add_dwell(sess, trader_id, "unread", ms=60_000)
        sess.commit()
    page = admin_page(app, engine)
    assert "Least-read fact" not in page
    assert "Chapter 4, median" not in page
    assert "Where readers stop" in page
    assert f"Chapter 4 · {SM.chapter(4).name}" in page
    assert SM.FACTS["not-told"].title in page[page.index("Where readers stop"):]
    assert page.count("so these are floors") == 1, "the existing note stays as it was"
    assert "Readers and times here are floors" in page
    assert "whether that's the people or the measurement" in page


def test_the_table_says_reading_is_stored_by_trader_not_by_file(app, engine):
    assert "before a real upload counts under real" in admin_page(app, engine)


# ---------- Development accounts ----------


@pytest.mark.parametrize("path", [
    ("cards", "signed_up"), ("cards", "tried_demo"), ("cards", "uploaded_real"),
    ("cards", "read_all"), ("cards", "stopped_early"), ("cards", "read_none"),
    ("cards", "demo_read_all"), ("cards", "demo_stopped_early"), ("cards", "demo_read_none"),
    ("cards", "said_wrong"), ("cards", "said_wrong_demo"),
    ("quiet", "most_opened"), ("fact_table", "chapters"), ("fact_table", "covers"),
    ("quiet", "wtp"), ("quiet", "wtp_asked"), ("quiet", "consent_declines"),
    ("quiet", "deletions"),
])
def test_a_development_account_moves_no_count(app, engine, path):
    real = add_trader(engine, "real")
    with make_session(engine) as sess:  # a real reader, so a dev account has something to move
        add_record(sess, real)
        add_dwell(sess, real, "money", ms=60_000)
        sess.commit()
    section, name = path
    before = view(app, engine)[section][name]
    tester = add_trader(engine, "tester", dev=True)
    seed_everything(engine, tester)
    with make_session(engine) as sess:  # and it holds a demo as well as a real file
        add_record(sess, tester, source=demo.ACCOUNT, at=THEN + timedelta(days=1))
        sess.commit()
    assert view(app, engine)[section][name] == before


def test_a_development_account_has_no_row_and_no_line_and_is_listed_apart(app, engine):
    add_trader(engine, "real")
    seed_everything(engine, add_trader(engine, "tester", dev=True, name="Test Account"))
    the_view = view(app, engine)
    assert [r["login_id"] for r in the_view["rows"]] == ["real"]
    assert the_view["feed"] == []
    assert [(d["login_id"], d["name"]) for d in the_view["dev_accounts"]] == [("tester", "Test Account")]


def test_the_page_lists_development_accounts_under_their_own_heading(app, engine):
    add_trader(engine, "tester", dev=True)
    page = admin_page(app, engine)
    assert "Development accounts" in page
    assert page.index("Development accounts") < page.index("tester")


def test_a_deleted_account_cannot_be_told_apart_so_the_page_says_so(app, engine):
    page = admin_page(app, engine)
    assert "cannot be split" in page


# ---------- Features that are off ----------


@pytest.fixture()
def production_app(monkeypatch):
    monkeypatch.setenv("ADMIN_LOGIN_IDS", ADMIN)
    monkeypatch.setenv("SCOPE_PRODUCTION", "1")
    application = create_app()
    application.state.code_version = RUNNING
    return application


def test_guess_and_leaving_card_are_empty_while_off(production_app):
    engine = production_app.state.engine
    add_trader(engine, "someone")
    the_view = view(production_app, engine)
    row = row_of(the_view, "someone")
    assert (row["guess"], row["leaving"]) == ("—", "—")
    assert the_view["features_off"] == ["guess", "leaving card"]


def test_guess_and_leaving_card_say_no_while_on(app, engine):
    add_trader(engine, "someone")
    the_view = view(app, engine)
    row = row_of(the_view, "someone")
    assert (row["guess"], row["leaving"]) == ("no", "no")
    assert the_view["features_off"] == []


def test_what_was_stored_is_shown_even_with_the_feature_off(production_app):
    engine = production_app.state.engine
    seed_everything(engine, add_trader(engine, "someone"))
    row = row_of(view(production_app, engine), "someone")
    assert (row["guess"], row["leaving"]) == ("answered", "answered")


def test_nothing_answered_yet_draws_zero_and_empty_not_an_error(app, engine):
    add_trader(engine, "someone")
    the_view = view(app, engine)
    assert the_view["quiet"]["wtp"] == {"yes": 0, "no": 0, "maybe": 0}
    assert row_of(the_view, "someone")["wtp"] == "—"
    assert admin_client(app, engine).get("/admin").status_code == 200


# ---------- Cost ----------


def statements_for_one_load(app, engine, client) -> list[str]:
    seen: list[str] = []

    def note(_conn, _cursor, statement, _params, _context, _many):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", note)
    try:
        assert client.get("/admin").status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", note)
    return seen


def test_a_load_runs_the_same_queries_for_three_traders_as_for_thirty(app, engine):
    client = admin_client(app, engine)
    for i in range(3):
        seed_everything(engine, add_trader(engine, f"trader-{i}"))
    few = len(statements_for_one_load(app, engine, client))
    for i in range(3, 30):
        seed_everything(engine, add_trader(engine, f"trader-{i}"))
    assert len(statements_for_one_load(app, engine, client)) == few
    assert few < 40


def test_a_load_reads_no_trade_and_no_stored_file_row(app, engine):
    seed_everything(engine, add_trader(engine, "someone"))
    said = " ".join(statements_for_one_load(app, engine, admin_client(app, engine))).lower()
    assert not re.search(r"\b(from|join)\s+trip\b", said)
    assert "raw_text" not in said
    assert said.count("password_hash") == 1  # who is asking, as every page does; not the list


# ---------- How it is drawn ----------


def test_a_wide_table_scrolls_in_its_own_box(app, engine):
    add_trader(engine, "someone")
    page = admin_page(app, engine)
    assert 'class="admin__scroll"' in page
    css = Path("services/production/api/static/css/app.css").read_text()
    assert ".admin__scroll { overflow-x: auto;" in css


def test_the_new_styles_are_not_added_at_the_end_of_the_file():
    """The end of app.css is where every open PR adds its rules, so a clash is likeliest there."""
    css = Path("services/production/api/static/css/app.css").read_text()
    assert css.index(".admin__scroll") < css.index(".day-blocks__next")


# ---------- What traders told us [TICKET-876] ----------


def told(app, engine) -> dict:
    return view(app, engine)["told"]


def add_chapter_answer(sess, trader_id, import_id, chapter, answer, reasons=(), at=THEN):
    row = m.ChapterFeedback(trader_id=trader_id, chapter=chapter, answer=answer, import_id=import_id,
                            answered_at=at)
    sess.add(row)
    sess.flush()
    for reason in reasons:
        sess.add(m.ChapterFeedbackReason(feedback_id=row.id, reason=reason, given_at=at))


def add_report_answer(sess, trader_id, import_id, answer, *, day="", note=None, at=THEN):
    sess.add(m.ReportFeedback(trader_id=trader_id, import_id=import_id, answer=answer, trading_day=day,
                              note=note, answered_at=at))


def test_chapters_count_answers_with_reasons_and_reach(app, engine):
    one, two, three = add_trader(engine, "one"), add_trader(engine, "two"), add_trader(engine, "three")
    with make_session(engine) as sess:
        imp = add_import(sess, one)
        add_chapter_answer(sess, one, imp.id, 3, "wrong", ["wrong_facts"])
        add_chapter_answer(sess, two, imp.id, 3, "wrong", ["wrong_reading"])
        add_chapter_answer(sess, three, imp.id, 3, "not_sure")
        sess.commit()
    row = next(c for c in told(app, engine)["chapters"] if c["chapter"] == 3)
    assert (row["reached"], row["accurate"], row["not_sure"], row["wrong"]) == (3, 0, 1, 2)
    assert row["reasons"] == "Wrong facts 1, Right facts, wrong reading 1"


def test_the_whole_report_and_days_said_to_look_wrong_are_counted(app, engine):
    one, two = add_trader(engine, "one"), add_trader(engine, "two")
    with make_session(engine) as sess:
        imp = add_import(sess, one)
        later = add_import(sess, one, at=THEN + timedelta(hours=1))
        add_report_answer(sess, one, imp.id, "wrong")
        add_report_answer(sess, one, later.id, "accurate")  # his latest is the one counted
        add_report_answer(sess, two, imp.id, "wrong")
        add_report_answer(sess, one, imp.id, "wrong", day="2026-03-02")
        add_report_answer(sess, one, later.id, "wrong", day="2026-03-02")  # the same day again
        add_report_answer(sess, two, imp.id, "wrong", day="2026-03-02")
        sess.commit()
    said = told(app, engine)
    assert (said["report"]["accurate"], said["report"]["not_sure"], said["report"]["wrong"]) == (1, 0, 1)
    assert said["days_wrong"] == 2


def test_reports_waiting_are_those_since_wrong_reports_last_ran(app, engine):
    trader_id = add_trader(engine, "one")
    with make_session(engine) as sess:
        imp = add_import(sess, trader_id)
        add_report_answer(sess, trader_id, imp.id, "accurate", note="a note", at=THEN)
        add_report_answer(sess, trader_id, add_import(sess, trader_id).id, "accurate", at=THEN)
        add_report_answer(sess, trader_id, imp.id, "wrong", day="2026-03-02", at=THEN)
        sess.commit()
    assert told(app, engine)["waiting"] == 2
    with make_session(engine) as sess:
        sess.add(m.AdminAction(actor="admin", action="wrong_reports", target=None, at=THEN + timedelta(hours=1)))
        sess.commit()
    assert told(app, engine)["waiting"] == 0
    with make_session(engine) as sess:
        add_report_answer(sess, trader_id, imp.id, "wrong", day="2026-03-03", at=THEN + timedelta(hours=2))
        sess.commit()
    assert told(app, engine)["waiting"] == 1


def test_a_development_account_moves_nothing_here(app, engine):
    add_trader(engine, "real")
    before = told(app, engine)
    seed_everything(engine, add_trader(engine, "tester", dev=True))
    assert told(app, engine) == before


def test_would_pay_counts_those_with_a_note(app, engine):
    seed_everything(engine, add_trader(engine, "someone"))
    assert told(app, engine)["wtp_noted"] == 1


def test_the_panel_draws_counts_and_the_command_and_no_typed_word(app, engine):
    trader_id = add_trader(engine, "one")
    with make_session(engine) as sess:
        imp = add_import(sess, trader_id)
        add_report_answer(sess, trader_id, imp.id, "wrong", note="MARKER-TYPED-WORDS")
        sess.commit()
    page = admin_page(app, engine)
    assert "What traders told us" in page
    assert "wrong-reports" in page and "1 waiting" in page
    assert "MARKER-TYPED-WORDS" not in page
    assert page.index("What traders told us") < page.index("Would pay</dt>")

def test_the_page_says_how_many_development_accounts_it_left_out(app, engine):
    # TICKET-864: a low number on the cards must not be misread as every account there is.
    assert view(app, engine)["dev_left_out"] == "No development accounts are left out"
    add_trader(engine, "tester", dev=True)
    assert view(app, engine)["dev_left_out"] == "1 development account is left out"
    add_trader(engine, "tester2", dev=True)
    assert view(app, engine)["dev_left_out"] == "2 development accounts are left out"


def test_the_count_of_those_left_out_is_above_the_cards(app, engine):
    add_trader(engine, "tester", dev=True)
    page = admin_page(app, engine)
    assert page.index("1 development account is left out") < page.index("Signed up")
