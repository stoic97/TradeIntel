"""TICKET-871: /admin's system health panel, for the failures that lose a trader silently.

A full disk, a capped sign-up or a byte-identical upload leave no row, so nothing else on
the page can show them. Each refusal here goes through the real route that refuses it, and
the disk answer is held against what the upload path itself does at the same reading.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from services.production.api import admin_health, limits
from services.production.api.app import create_app
from services.production.ctr.adapters import filemap
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import constants as k
from tests.unit.api.test_add_charges import FILE as CHARGES_TRADES
from tests.unit.api.test_add_charges import FULL
from tests.unit.api.test_admin_page import ADMIN, TEMPLATES, add_trader, signed_in
from tests.unit.api.test_rate_limits import sign_up as bare_sign_up
from tests.unit.api.test_rate_limits import stored_files
from tests.unit.api.test_upload import DUPES, sign_up, upload

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
CLEAN = DUPES / "clean.csv"
STARTED = datetime(2026, 3, 2, 4, 30, tzinfo=UTC)
LINE = k.UPLOADS_REFUSED_AT_DISK_PERCENT
CHARGES = FULL


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("ADMIN_LOGIN_IDS", ADMIN)
    return create_app()


@pytest.fixture()
def engine(app):
    return app.state.engine


@pytest.fixture()
def client(app, engine):
    return sign_up(TestClient(app), engine, "D-1", "visitor")


def set_disk(monkeypatch, percent) -> None:
    usage = shutil._ntuple_diskusage(total=100, used=percent, free=100 - percent)
    monkeypatch.setattr(limits.shutil, "disk_usage", lambda _path: usage)


def unverified(app, monkeypatch) -> None:
    app.state.settings = dataclasses.replace(app.state.settings, production=True)

    def unchecked(_map):
        raise filemap.UnverifiedFileMap("nobody has opened this broker's app")

    monkeypatch.setattr(filemap, "require_verified", unchecked)


def panel(app) -> dict:
    return admin_health.build(app)


def refused(app) -> dict[str, int]:
    return {line["label"]: line["count"] for line in panel(app)["refusals"]}


def only(app, label: str) -> None:
    """This refusal was counted once, and no other was counted at all."""
    assert {name: n for name, n in refused(app).items() if n} == {label: 1}


def admin_text(app) -> str:
    return signed_in(app, add_trader(app.state.engine, ADMIN)).get("/admin").text


# ---------- Would an upload work right now? ----------


def test_with_a_healthy_disk_an_upload_would_work(app):
    assert panel(app)["upload"]["answer"] == "Yes"


@pytest.mark.parametrize("percent", [LINE - 1, LINE, LINE + 1])
def test_the_answer_is_what_the_upload_path_itself_does_at_that_reading(app, engine, client,
                                                                       monkeypatch, percent):
    set_disk(monkeypatch, percent)
    response = upload(client, CLEAN)
    took_it = response.status_code != 503
    assert (panel(app)["upload"]["answer"] == "Yes") is took_it


def test_past_the_line_the_answer_says_no_and_why(app, monkeypatch):
    set_disk(monkeypatch, LINE)
    assert panel(app)["upload"]["answer"] == "No: the disk is past the refusal line"


def test_an_unverified_broker_map_in_production_is_a_no_with_its_broker(app, monkeypatch):
    unverified(app, monkeypatch)
    answer = panel(app)["upload"]["answer"]
    assert answer.startswith("No: ")
    assert "file map has not been verified" in answer


def test_an_unverified_map_outside_production_closes_nothing(app, monkeypatch):
    def unchecked(_map):
        raise filemap.UnverifiedFileMap("nobody has opened this broker's app")

    monkeypatch.setattr(filemap, "require_verified", unchecked)
    assert panel(app)["upload"]["answer"] == "Yes"


def test_both_reasons_are_given_when_both_hold(app, monkeypatch):
    set_disk(monkeypatch, LINE)
    unverified(app, monkeypatch)
    answer = panel(app)["upload"]["answer"]
    assert "the disk is past the refusal line" in answer
    assert "file map has not been verified" in answer


def test_a_disk_that_cannot_be_read_leaves_uploads_open_as_the_upload_path_does(app, monkeypatch):
    def broken(_path):
        raise OSError("no such disk")

    monkeypatch.setattr(limits.shutil, "disk_usage", broken)
    the_panel = panel(app)
    assert the_panel["upload"]["answer"] == "Yes"
    assert the_panel["disk"] == "Could not be read"


def test_the_page_says_one_account_can_still_be_capped(app):
    assert f"{k.UPLOADS_PER_ACCOUNT_PER_DAY} files in a day" in admin_text(app)


# ---------- Disk and sizes ----------


def test_the_disk_is_read_against_the_refusal_line(app, monkeypatch):
    set_disk(monkeypatch, 61)
    assert panel(app)["disk"] == f"61.0% used; uploads are refused at {LINE}%"


def test_reading_the_disk_for_the_page_refuses_nothing_and_logs_no_refusal(app, monkeypatch, caplog):
    set_disk(monkeypatch, LINE + 5)
    with caplog.at_level(logging.WARNING):
        panel(app)
    assert "uploads refused" not in caplog.text
    assert not any(refused(app).values())


@pytest.mark.parametrize(("size", "words"), [
    (0, "0 B"), (900, "900 B"), (2_560, "2.5 KB"), (5 * 1024 * 1024, "5.0 MB"),
    (3 * 1024 ** 3, "3.0 GB"),
])
def test_a_size_reads_in_the_unit_it_needs(size, words):
    assert admin_health.size_words(size) == words


def test_stored_files_are_added_up_through_their_folders(app):
    root = Path(os.environ["SCOPE_FILES"]) / "a" / "b"
    root.mkdir(parents=True)
    (root / "one").write_bytes(b"x" * 1024)
    (root.parent / "two").write_bytes(b"x" * 1024)
    assert panel(app)["stored_size"] == "2.0 KB"


def test_no_stored_files_yet_is_nothing_stored_not_an_error(app):
    assert panel(app)["stored_size"] == "0 B"


def test_the_database_size_counts_its_file_and_its_write_ahead_log(app):
    database = Path(app.state.engine.url.database)
    on_disk = database.stat().st_size
    wal = Path(f"{database}-wal")
    on_disk += wal.stat().st_size if wal.exists() else 0
    assert panel(app)["database_size"] == admin_health.size_words(on_disk)


def test_a_database_with_no_file_shows_no_size(app, monkeypatch):
    monkeypatch.setattr(admin_health, "_database_bytes", lambda _engine: None)
    assert panel(app)["database_size"] == "—"


# ---------- The running deploy ----------


def test_the_process_says_when_it_started_in_ist(app):
    app.state.started_at = STARTED
    assert panel(app)["started"] == "02 Mar 2026 10:00"


def test_a_new_app_records_when_it_started(app):
    assert datetime.now(UTC) - app.state.started_at < timedelta(minutes=5)


def test_the_page_shows_the_deploy_with_its_start(app):
    app.state.code_version = "aaa1111"
    app.state.started_at = STARTED
    assert '<span class="num">aaa1111</span>, started 02 Mar 2026 10:00' in admin_text(app)


# ---------- Refusals that leave no row ----------


def test_every_count_starts_at_nothing_and_each_is_named(app):
    assert refused(app) == {
        "Same file again": 0, "Daily file cap": 0, "Sign-up cap": 0, "File too large": 0,
        "Disk nearly full": 0, "Unverified broker map": 0,
    }


def test_a_byte_identical_upload_is_counted(app, client):
    upload(client, CLEAN)
    assert not any(refused(app).values()), "the first time is no refusal"
    upload(client, CLEAN)
    only(app, "Same file again")


def test_the_daily_cap_is_counted(app, engine, client):
    stored_files(engine, "visitor", k.UPLOADS_PER_ACCOUNT_PER_DAY, datetime.now(UTC))
    assert upload(client, CLEAN).status_code == 429
    only(app, "Daily file cap")


def test_the_sign_up_cap_is_counted(app):
    client = TestClient(app)
    for n in range(k.SIGNUPS_PER_IP_PER_HOUR):
        bare_sign_up(client, f"person-{n}")
    assert not any(refused(app).values())
    assert bare_sign_up(client, "one-too-many").status_code == 429
    only(app, "Sign-up cap")


def test_a_file_over_the_routes_own_size_is_counted(app, client):
    assert upload(client, content=b"x" * (k.MAX_UPLOAD_BYTES + 1)).status_code == 400
    only(app, "File too large")


def test_a_body_refused_before_it_is_read_is_counted(app, client):
    assert upload(client, content=b"x" * (k.MAX_REQUEST_BYTES + 1)).status_code == 413
    only(app, "File too large")


def test_a_nearly_full_disk_is_counted(app, client, monkeypatch):
    set_disk(monkeypatch, LINE)
    assert upload(client, CLEAN).status_code == 503
    only(app, "Disk nearly full")


def test_an_unverified_broker_map_is_counted(app, client, monkeypatch):
    unverified(app, monkeypatch)
    assert upload(client, CLEAN).status_code == 503
    only(app, "Unverified broker map")


def test_a_refused_upload_adds_a_count_and_no_row(app, engine, client):
    upload(client, CLEAN)
    with make_session(engine) as sess:
        before = sess.scalar(select(func.count()).select_from(m.RawFile))
    upload(client, CLEAN)
    with make_session(engine) as sess:
        assert sess.scalar(select(func.count()).select_from(m.RawFile)) == before


def test_an_ordinary_upload_counts_nothing(app, client):
    assert upload(client, CLEAN).status_code in (200, 303)
    assert not any(refused(app).values())


def test_a_kind_outside_the_list_is_refused_so_no_trader_id_can_be_a_count():
    counts = limits.SinceRestart()
    with pytest.raises(KeyError):
        counts.add("trader:7")
    assert set(counts.refusals()) == set(limits.REFUSAL_KINDS)


def test_counts_are_held_by_the_process_so_a_new_one_starts_again(app, client):
    upload(client, CLEAN)
    upload(client, CLEAN)
    assert any(refused(app).values())
    assert not any(refused(create_app()).values())


def test_the_page_labels_the_counts_since_restart(app, client):
    upload(client, CLEAN)
    upload(client, CLEAN)
    page = admin_text(app)
    assert "Refused since restart" in page
    assert "Server errors since restart" in page
    assert re.search(r"Same file again</dt><dd>1<", page)


def test_the_counts_say_who_they_leave_out(app, client):
    upload(client, CLEAN)
    upload(client, CLEAN)
    section = admin_text(app)
    section = section[section.index("System health"):section.index("Traders</h2>")]
    assert "visitor" not in section


def charges_client(app, engine, content: bytes) -> TestClient:
    """A trader with a record, sending a charges file for it."""
    client = sign_up(TestClient(app), engine, "C-1", "charges")
    assert upload(client, content=CHARGES_TRADES).status_code in (302, 303)
    with make_session(engine) as sess:
        url = f"/imports/{sess.scalars(select(m.Import.id)).one()}/charges"
    csrf = CSRF.search(client.get("/upload").text).group(1)
    client.post(url, files={"file": ("charges.csv", content, "text/csv")},
                data={"csrf_token": csrf}, follow_redirects=False)
    return client


def test_the_same_charges_file_again_is_counted(app, engine):
    client = charges_client(app, engine, CHARGES)
    assert not any(refused(app).values())
    with make_session(engine) as sess:
        url = f"/imports/{sess.scalars(select(m.Import.id)).one()}/charges"
    csrf = CSRF.search(client.get("/upload").text).group(1)
    client.post(url, files={"file": ("charges.csv", CHARGES, "text/csv")},
                data={"csrf_token": csrf}, follow_redirects=False)
    only(app, "Same file again")


def test_a_charges_file_over_the_size_is_counted(app, engine):
    charges_client(app, engine, b"x" * (k.MAX_UPLOAD_BYTES + 1))
    only(app, "File too large")


def test_the_charges_step_closed_in_production_is_counted(app, engine):
    client = sign_up(TestClient(app), engine, "C-1", "charges")
    assert upload(client, content=CHARGES_TRADES).status_code in (302, 303)
    csrf = CSRF.search(client.get("/upload").text).group(1)
    app.state.settings = dataclasses.replace(app.state.settings, production=True)
    with make_session(engine) as sess:
        url = f"/imports/{sess.scalars(select(m.Import.id)).one()}/charges"
    assert client.post(url, files={"file": ("c.csv", CHARGES, "text/csv")},
                       data={"csrf_token": csrf}, follow_redirects=False).status_code == 503
    only(app, "Unverified broker map")


# ---------- Server errors ----------


def broken_client(app) -> TestClient:
    def boom():
        raise RuntimeError("something nobody planned for")

    def missing():
        raise HTTPException(status_code=404)

    app.add_api_route("/boom", boom)
    app.add_api_route("/missing", missing)
    return TestClient(app, raise_server_exceptions=False)


def test_a_request_that_crashed_is_counted(app):
    client = broken_client(app)
    assert panel(app)["server_errors"] == 0
    assert client.get("/boom").status_code == 500
    assert panel(app)["server_errors"] == 1


def test_a_not_found_is_no_server_error(app):
    assert broken_client(app).get("/missing").status_code == 404
    assert panel(app)["server_errors"] == 0


def test_a_deliberate_refusal_is_no_server_error(app, client, monkeypatch):
    set_disk(monkeypatch, LINE)
    assert upload(client, CLEAN).status_code == 503
    assert panel(app)["server_errors"] == 0


# ---------- Backups, and how it is drawn ----------


def test_the_page_says_it_cannot_read_backups_and_points_to_the_runbook(app):
    page = admin_text(app).replace("&#39;", "'")
    assert "The app can't read backups" in page
    assert "says nothing about whether they ran" in page
    assert "docs/runbooks/deploy.md" in page


def test_the_runbook_the_page_points_to_covers_backups():
    assert "## 5. Backups and the drill" in Path("docs/runbooks/deploy.md").read_text()


def test_the_panel_sits_above_the_traders(app):
    page = admin_text(app)
    assert page.index("System health") < page.index("Traders</h2>")


def test_the_template_holds_no_number_of_its_own():
    source = (TEMPLATES / "admin.html").read_text()
    assert str(LINE) not in source
    assert str(k.UPLOADS_PER_ACCOUNT_PER_DAY) not in source


def test_a_view_of_the_panel_stores_nothing_of_its_own(app, engine):
    client = signed_in(app, add_trader(engine, ADMIN))
    assert client.get("/admin").status_code == 200
    with make_session(engine) as sess:
        assert sess.scalar(select(func.count()).select_from(m.AdminAction)) == 1
