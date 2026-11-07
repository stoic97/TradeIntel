"""The caps that stand between an open sign-up and a small box [TICKET-847].

Sign-ups per connection per hour, uploads per account per day, a body size checked before
the body is read, and a disk that refuses a file before it fills. Each refusal says what
happened and when to try again. The last test here is the one that matters most: a trader
doing ordinary things never meets any of them.
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from services.production.api import limits
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.production.journal import constants as k
from tests.unit.api.test_upload import sign_up as sign_up_with_consent
from tests.unit.api.test_upload import upload

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
PASSWORD = "a-long-enough-password"
GOOD = Path("data/fixtures/demo/demo_tradebook.csv")
IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture()
def engine():
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def app(engine):
    return create_app()


def sign_up(client, login_id, password=PASSWORD):
    client.cookies.clear()
    csrf = CSRF.search(client.get("/signup").text).group(1)
    return client.post(
        "/signup",
        data={"login_id": login_id, "display_name": login_id, "password": password,
              "csrf_token": csrf},
        follow_redirects=False,
    )


def traders(engine) -> int:
    with make_session(engine) as sess:
        return sess.scalar(select(func.count()).select_from(m.Trader))


def raw_files(engine) -> int:
    with make_session(engine) as sess:
        return sess.scalar(select(func.count()).select_from(m.RawFile))


def files_on_disk() -> list[Path]:
    root = Path(os.environ["SCOPE_FILES"])
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def trader_id(engine, login_id) -> int:
    with make_session(engine) as sess:
        return sess.scalars(select(m.Trader.id).where(m.Trader.login_id == login_id)).one()


def stored_files(engine, login_id, count, at) -> None:
    """Files this account already sent, without paying to read each one."""
    owner = trader_id(engine, login_id)
    with make_session(engine) as sess:
        for n in range(count):
            sess.add(m.RawFile(trader_id=owner, sha256=f"{login_id}{at.isoformat()}{n}", original_name="old.csv",
                               size=1, stored_path="old", uploaded_at=at))
        sess.commit()


def full_disk(monkeypatch, percent) -> None:
    usage = shutil._ntuple_diskusage(total=100, used=percent, free=100 - percent)
    monkeypatch.setattr(limits.shutil, "disk_usage", lambda _path: usage)


# ---------- The numbers ----------


@pytest.mark.parametrize("name", ["SIGNUPS_PER_IP_PER_HOUR", "UPLOADS_PER_ACCOUNT_PER_DAY",
                                  "UPLOADS_REFUSED_AT_DISK_PERCENT", "MAX_REQUEST_BYTES"])
def test_each_cap_is_a_constant_with_its_argument(name):
    assert isinstance(getattr(k, name), int)
    assert len(k.ARGUMENTS[name]) > 40


def test_the_routes_hold_no_number_of_their_own():
    for path in ("routes_identity.py", "routes_upload.py", "routes_charges.py", "limits.py"):
        source = Path("services/production/api", path).read_text(encoding="utf-8")
        assert not re.search(r"(?i)(signups?|uploads?|percent|disk)\w*\s*=\s*\d", source), path


# ---------- Sign-ups, per connection, per hour ----------


def test_the_sign_up_past_the_cap_is_refused_and_makes_no_account(app, engine):
    client = TestClient(app)
    for n in range(k.SIGNUPS_PER_IP_PER_HOUR):
        assert sign_up(client, f"trader{n}").status_code == 303
    refused = sign_up(client, "one-too-many")
    assert refused.status_code == 429
    assert traders(engine) == k.SIGNUPS_PER_IP_PER_HOUR


def test_a_refused_sign_up_says_what_happened_and_when_to_try_again(app):
    client = TestClient(app)
    for n in range(k.SIGNUPS_PER_IP_PER_HOUR):
        sign_up(client, f"trader{n}")
    refused = sign_up(client, "one-too-many")
    assert "Too many accounts have been made from this connection" in refused.text
    assert re.search(r"Try again in \d+ minutes?\.", refused.text)
    assert 0 < int(refused.headers["Retry-After"]) <= 3600
    assert 'role="alert"' in refused.text


def test_another_connection_is_not_touched_by_the_cap(app):
    first = TestClient(app, client=("203.0.113.7", 50000))
    for n in range(k.SIGNUPS_PER_IP_PER_HOUR + 1):
        sign_up(first, f"trader{n}")
    assert sign_up(TestClient(app, client=("203.0.113.8", 50000)), "someone-else").status_code == 303


def test_a_mistake_does_not_use_up_the_cap(app):
    client = TestClient(app)
    for _ in range(k.SIGNUPS_PER_IP_PER_HOUR + 5):
        assert sign_up(client, "x", password="short").status_code == 400
    assert sign_up(client, "taken").status_code == 303
    for _ in range(k.SIGNUPS_PER_IP_PER_HOUR + 5):
        assert sign_up(client, "taken").status_code == 400
    assert sign_up(client, "free").status_code == 303


def test_a_refused_sign_up_spends_nothing_on_the_password(app, monkeypatch):
    client = TestClient(app)
    for n in range(k.SIGNUPS_PER_IP_PER_HOUR):
        sign_up(client, f"trader{n}")

    def never(_password):
        raise AssertionError("hashed a password for a sign-up it was going to refuse")

    monkeypatch.setattr("services.production.accounts.auth.hash_password", never)
    assert sign_up(client, "one-too-many").status_code == 429


def test_the_window_slides_a_slot_opens_an_hour_after_the_oldest():
    now = [1000.0]
    count = limits.HourlyCount(cap=2, clock=lambda: now[0])
    count.add("a")
    now[0] += 600
    count.add("a")
    assert count.wait_seconds("a") == 3000
    now[0] += 3000
    assert count.wait_seconds("a") == 0


def test_a_connection_that_went_quiet_is_forgotten():
    now = [1000.0]
    count = limits.HourlyCount(cap=2, clock=lambda: now[0])
    count.add("a")
    now[0] += 3601
    count.add("b")
    assert "a" not in count.held()


@pytest.mark.parametrize(("host", "same"), [
    ("2001:db8:1:2:aaaa::1", "2001:db8:1:2:bbbb::9"),  # one IPv6 customer holds a whole /64
    ("203.0.113.7", "203.0.113.7"),
    ("::ffff:203.0.113.7", "203.0.113.7"),
])
def test_one_network_is_one_connection(host, same):
    assert limits.network(host) == limits.network(same)


def test_two_ipv6_networks_are_two_connections():
    assert limits.network("2001:db8:1:2::1") != limits.network("2001:db8:1:3::1")


def test_a_connection_with_no_address_still_has_a_key():
    assert limits.network(None) == limits.network("")


def behind_caddy(app, forwarded_for=None, peer="127.0.0.1"):
    """What runs on the box: uvicorn's proxy handling, in front of the app, trusting Caddy."""
    headers = {"X-Forwarded-For": forwarded_for} if forwarded_for else None
    wrapped = ProxyHeadersMiddleware(app, trusted_hosts="127.0.0.1")
    return TestClient(wrapped, client=(peer, 50000), headers=headers)


def test_behind_the_proxy_each_visitor_has_their_own_cap(app):
    first = behind_caddy(app, "203.0.113.7")
    for n in range(k.SIGNUPS_PER_IP_PER_HOUR):
        assert sign_up(first, f"trader{n}").status_code == 303
    assert sign_up(first, "one-too-many").status_code == 429
    assert sign_up(behind_caddy(app, "203.0.113.8"), "someone-else").status_code == 303


def test_a_forwarded_header_from_anyone_but_the_proxy_buys_no_new_cap(app):
    for n in range(k.SIGNUPS_PER_IP_PER_HOUR):
        spoofing = behind_caddy(app, f"198.51.100.{n}", peer="203.0.113.7")
        assert sign_up(spoofing, f"trader{n}").status_code == 303
    last = behind_caddy(app, "198.51.100.200", peer="203.0.113.7")
    assert sign_up(last, "one-too-many").status_code == 429


def test_the_service_file_says_to_trust_the_proxy_on_this_box_only():
    unit = Path("deploy/scope.service").read_text(encoding="utf-8")
    assert "--proxy-headers" in unit
    assert "--forwarded-allow-ips 127.0.0.1" in unit
    caddy = Path("deploy/Caddyfile").read_text(encoding="utf-8")
    assert "trusted_proxies" not in caddy, "Caddy then passes on a visitor's own forwarded header"


def test_no_address_is_ever_written_down(app, engine):
    address = "203.0.113.77"
    client = TestClient(app, client=(address, 50000))
    for n in range(k.SIGNUPS_PER_IP_PER_HOUR + 1):
        sign_up(client, f"trader{n}")
    connection = engine.raw_connection()
    try:
        dump = "\n".join(connection.iterdump())
    finally:
        connection.close()
    assert address not in dump


def test_the_map_says_where_an_address_is_held():
    the_map = Path("docs/runbooks/data-flow-map.md").read_text(encoding="utf-8")
    assert "only in memory" in the_map


# ---------- Uploads, per account, per day ----------


def test_the_upload_past_the_cap_is_refused_and_stores_nothing(app, engine):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    stored_files(engine, "rikk", k.UPLOADS_PER_ACCOUNT_PER_DAY, datetime.now(UTC))
    before, on_disk = raw_files(engine), files_on_disk()
    refused = upload(client, path=GOOD)
    assert refused.status_code == 429
    assert raw_files(engine) == before
    assert files_on_disk() == on_disk


def test_a_refused_upload_says_what_happened_and_when_to_try_again(app, engine):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    stored_files(engine, "rikk", k.UPLOADS_PER_ACCOUNT_PER_DAY, datetime.now(UTC))
    refused = upload(client, path=GOOD)
    assert f"You have sent {k.UPLOADS_PER_ACCOUNT_PER_DAY} files today" in refused.text
    assert "Nothing was added. Try again tomorrow." in refused.text
    assert 0 < int(refused.headers["Retry-After"]) <= 86400
    assert 'role="alert"' in refused.text


def test_the_last_upload_under_the_cap_goes_through(app, engine):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    stored_files(engine, "rikk", k.UPLOADS_PER_ACCOUNT_PER_DAY - 1, datetime.now(UTC))
    assert upload(client, path=GOOD).status_code == 303


def midnight_ist() -> datetime:
    return datetime.combine(datetime.now(IST).date(), time.min, IST).astimezone(UTC)


def test_the_day_turns_over_at_midnight_in_india(app, engine):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    stored_files(engine, "rikk", k.UPLOADS_PER_ACCOUNT_PER_DAY, midnight_ist() - timedelta(minutes=1))
    assert upload(client, path=GOOD).status_code == 303


def test_a_file_just_after_midnight_in_india_counts_as_today(engine, app):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    stored_files(engine, "rikk", k.UPLOADS_PER_ACCOUNT_PER_DAY, midnight_ist())
    assert upload(client, path=GOOD).status_code == 429


def test_another_traders_files_do_not_count(app, engine):
    client = TestClient(app)
    sign_up_with_consent(client, engine, "U", "busy")
    stored_files(engine, "busy", k.UPLOADS_PER_ACCOUNT_PER_DAY, datetime.now(UTC))
    sign_up_with_consent(client, engine, "U", "quiet")
    assert upload(client, path=GOOD).status_code == 303


def test_a_refusal_still_reaches_the_page_when_htmx_sends_it(app, engine):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    stored_files(engine, "rikk", k.UPLOADS_PER_ACCOUNT_PER_DAY, datetime.now(UTC))
    csrf = CSRF.search(client.get("/upload").text).group(1)
    refused = client.post("/upload", files={"file": ("t.csv", GOOD.read_bytes(), "text/csv")},
                          data={"csrf_token": csrf}, headers={"HX-Request": "true"},
                          follow_redirects=False)
    assert refused.status_code == 429
    assert "Try again tomorrow." in refused.text
    page = client.get("/upload").text
    assert "e.detail.xhr.status >= 400" in page, "htmx would drop the refusal without this"


def charges_post(client, engine, login_id):
    owner = trader_id(engine, login_id)
    with make_session(engine) as sess:
        imp = sess.scalars(select(m.Import.id).where(m.Import.trader_id == owner)).first()
    url = f"/imports/{imp}/charges"
    csrf = CSRF.search(client.get(url).text).group(1)
    return client.post(url, files={"file": ("c.csv", b"a,b\n1,2\n", "text/csv")},
                       data={"csrf_token": csrf}, follow_redirects=False)


def test_a_charges_file_counts_as_an_upload_too(app, engine):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    assert upload(client, path=GOOD).status_code == 303
    stored_files(engine, "rikk", k.UPLOADS_PER_ACCOUNT_PER_DAY, datetime.now(UTC))
    refused = charges_post(client, engine, "rikk")
    assert refused.status_code == 429
    assert "Try again tomorrow." in refused.text


# ---------- The disk ----------


def test_a_nearly_full_disk_refuses_the_file_in_a_plain_sentence(app, engine, monkeypatch):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    before = raw_files(engine)
    full_disk(monkeypatch, k.UPLOADS_REFUSED_AT_DISK_PERCENT)
    refused = upload(client, path=GOOD)
    assert refused.status_code == 503
    assert "Our storage is nearly full, so we cannot take new files right now." in refused.text
    assert "Nothing was added. Try again tomorrow." in refused.text
    assert int(refused.headers["Retry-After"]) > 0
    assert raw_files(engine) == before
    assert files_on_disk() == []


def test_a_disk_just_under_the_line_takes_the_file(app, engine, monkeypatch):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    full_disk(monkeypatch, k.UPLOADS_REFUSED_AT_DISK_PERCENT - 1)
    assert upload(client, path=GOOD).status_code == 303


def test_a_nearly_full_disk_refuses_a_charges_file_too(app, engine, monkeypatch):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    assert upload(client, path=GOOD).status_code == 303
    full_disk(monkeypatch, k.UPLOADS_REFUSED_AT_DISK_PERCENT)
    assert charges_post(client, engine, "rikk").status_code == 503


def test_the_refusal_is_in_the_log_because_nobody_else_is_told(app, engine, monkeypatch, caplog):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    full_disk(monkeypatch, k.UPLOADS_REFUSED_AT_DISK_PERCENT)
    upload(client, path=GOOD)
    assert "disk" in caplog.text


def test_the_check_reads_the_nearest_folder_that_exists(tmp_path):
    assert 0 <= limits.disk_used_percent(tmp_path / "not" / "made" / "yet") <= 100


def test_a_disk_it_cannot_read_does_not_shut_uploads(app, engine, monkeypatch):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")

    def broken(_path):
        raise OSError("no such device")

    monkeypatch.setattr(limits.shutil, "disk_usage", broken)
    assert upload(client, path=GOOD).status_code == 303


# ---------- A body too big to read ----------


def test_a_body_past_the_cap_is_refused_before_it_is_read():
    """The form parser spools a whole body to disk before any route's own size check runs."""
    reached = []

    async def app(scope, receive, send):
        reached.append(scope["path"])

    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        raise AssertionError("read the body of a request it was going to refuse")

    import asyncio

    scope = {"type": "http", "method": "POST", "path": "/upload", "query_string": b"",
             "headers": [(b"content-length", str(k.MAX_REQUEST_BYTES + 1).encode())]}
    asyncio.run(limits.BodyCap(app, refuse=limits.plain_refusal)(scope, receive, send))
    assert reached == []
    assert sent[0]["status"] == 413


def test_the_person_sending_it_is_told_why(app, engine):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    before = raw_files(engine)
    refused = upload(client, content=b"x" * (k.MAX_REQUEST_BYTES + 1))
    assert refused.status_code == 413
    assert f"That file is larger than {k.MAX_UPLOAD_BYTES // (1024 * 1024)} MB." in refused.text
    assert raw_files(engine) == before


def test_nobody_needs_to_be_signed_in_to_be_refused(app):
    posted = TestClient(app).post(
        "/signup", content=b"x" * (k.MAX_REQUEST_BYTES + 1),
        headers={"content-type": "application/x-www-form-urlencoded"}, follow_redirects=False)
    assert posted.status_code == 413


def test_a_body_with_no_stated_length_is_stopped_at_the_cap():
    """No browser sends one, so it is counted as it arrives and the read stops at the cap."""
    import asyncio

    chunk = b"x" * (1024 * 1024)
    handed_over = []

    async def receive():
        return {"type": "http.request", "body": chunk, "more_body": True}

    async def app(scope, receive, send):
        while True:
            handed_over.append(len((await receive())["body"]))

    async def send(_message):
        raise AssertionError("nothing is sent from here")

    scope = {"type": "http", "method": "POST", "path": "/upload", "query_string": b"", "headers": []}
    with pytest.raises(HTTPException) as refused:
        asyncio.run(limits.BodyCap(app, refuse=limits.plain_refusal)(scope, receive, send))
    assert refused.value.status_code == 413
    assert sum(handed_over) <= k.MAX_REQUEST_BYTES


def test_the_real_app_answers_a_body_with_no_stated_length_past_the_cap(app, engine):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    before = raw_files(engine)

    def endless():
        for _ in range(50):
            yield b"x" * (1024 * 1024)

    posted = client.post("/upload", content=endless(),
                         headers={"content-type": "multipart/form-data; boundary=x"},
                         follow_redirects=False)
    assert posted.status_code == 413
    assert raw_files(engine) == before


def test_the_cap_leaves_room_for_the_form_around_a_file_at_the_byte_limit():
    assert k.MAX_REQUEST_BYTES > k.MAX_UPLOAD_BYTES


def test_a_file_at_the_byte_limit_gets_past_the_body_cap(app, engine):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    posted = upload(client, content=b"x" * k.MAX_UPLOAD_BYTES)
    assert posted.status_code != 413


def test_a_file_just_over_the_byte_limit_keeps_its_own_refusal(app, engine):
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    posted = upload(client, content=b"x" * (k.MAX_UPLOAD_BYTES + 1))
    assert posted.status_code == 400
    assert "larger than" in posted.text


def test_a_get_is_not_touched(app):
    assert TestClient(app).get("/signup").status_code == 200


# ---------- An ordinary trader ----------


def test_an_ordinary_trader_doing_ordinary_things_never_meets_a_cap(app, engine):
    """Signs up, sends a file, sends it again by mistake, sends a newer one and a wrong one,
    and a friend signs up on the same connection. Nothing here is refused by a cap."""
    client = sign_up_with_consent(TestClient(app), engine, "U", "rikk")
    good = GOOD.read_bytes()
    answers = [
        upload(client, content=good),
        upload(client, content=good),  # the same file again
        upload(client, content=good + b"\n"),  # a newer export
        upload(client, content=b"Symbol,Realised P&L\nWIDGETOIL,1500.00\n"),  # the wrong report
        client.get("/mirror"),
        client.get("/journals"),
    ]
    friend = TestClient(app)
    answers.append(sign_up(friend, "a-friend"))
    capped = {429, 503, 413}
    assert not [a.status_code for a in answers if a.status_code in capped]
    assert len(good) < k.MAX_UPLOAD_BYTES
    assert raw_files(engine) < k.UPLOADS_PER_ACCOUNT_PER_DAY


# ---------- Failed sign-ins [TICKET-872] ----------


def try_login(client, login_id, password):
    csrf = CSRF.search(client.get("/login").text).group(1)
    return client.post("/login", data={"login_id": login_id, "password": password, "csrf_token": csrf},
                       follow_redirects=False)


def from_network(app, n) -> TestClient:
    return TestClient(app, client=(f"{n % 200 + 1}.{n // 200 + 1}.0.9", 50000))


def fail_id(app, login_id, times):
    for n in range(times):
        assert try_login(from_network(app, n), login_id, "wrong").status_code == 400


def test_a_login_id_is_refused_past_its_cap_from_any_connection_even_with_the_right_password(app):
    sign_up(TestClient(app), "owner")
    fail_id(app, "owner", k.LOGIN_FAILURES_PER_ID_PER_HOUR)
    refused = try_login(from_network(app, 900), "owner", PASSWORD)
    assert refused.status_code == 429
    assert auth_cookie_absent(refused)


def auth_cookie_absent(response) -> bool:
    return "set-cookie" not in {key.lower() for key in response.headers}


def test_one_connection_is_refused_past_its_cap_across_login_ids(app):
    client = TestClient(app)
    for n in range(k.LOGIN_FAILURES_PER_IP_PER_HOUR):
        assert try_login(client, f"guess{n}", "wrong").status_code == 400
    assert try_login(client, "guess-another", "wrong").status_code == 429


def test_a_refusal_says_what_happened_and_when_to_try_again(app):
    fail_id(app, "owner", k.LOGIN_FAILURES_PER_ID_PER_HOUR)
    refused = try_login(from_network(app, 900), "owner", "wrong")
    assert "Too many failed sign-ins" in refused.text
    assert re.search(r"Try again in \d+ minutes?\.", refused.text)
    assert 0 < int(refused.headers["Retry-After"]) <= 3600
    assert 'role="alert"' in refused.text


def test_a_known_and_an_unknown_id_get_the_same_refusal(app):
    sign_up(TestClient(app), "owner")
    fail_id(app, "owner", k.LOGIN_FAILURES_PER_ID_PER_HOUR)
    fail_id(app, "nobody", k.LOGIN_FAILURES_PER_ID_PER_HOUR)
    known = try_login(from_network(app, 900), "owner", "wrong")
    unknown = try_login(from_network(app, 901), "nobody", "wrong")
    strip = lambda text: CSRF.sub("", re.sub(r"\d+ minutes?", "", text))
    assert (known.status_code, strip(known.text)) == (unknown.status_code, strip(unknown.text))


def test_a_correct_password_under_the_cap_works_and_counts_nothing(app):
    sign_up(TestClient(app), "owner")
    fail_id(app, "owner", k.LOGIN_FAILURES_PER_ID_PER_HOUR - 1)
    for n in range(3):
        assert try_login(from_network(app, 500 + n), "owner", PASSWORD).status_code == 303
    assert try_login(from_network(app, 900), "owner", PASSWORD).status_code == 303


def test_the_right_password_works_again_after_the_wait(app):
    now = [0.0]
    app.state.login_ids = limits.HourlyCount(cap=k.LOGIN_FAILURES_PER_ID_PER_HOUR, clock=lambda: now[0])
    sign_up(TestClient(app), "owner")
    fail_id(app, "owner", k.LOGIN_FAILURES_PER_ID_PER_HOUR)
    assert try_login(from_network(app, 900), "owner", PASSWORD).status_code == 429
    now[0] = limits.HOUR_SECONDS + 1
    assert try_login(from_network(app, 900), "owner", PASSWORD).status_code == 303


def test_a_capped_id_leaves_other_accounts_alone(app):
    sign_up(TestClient(app), "owner")
    fail_id(app, "someone-else", k.LOGIN_FAILURES_PER_ID_PER_HOUR)
    assert try_login(from_network(app, 900), "owner", PASSWORD).status_code == 303
