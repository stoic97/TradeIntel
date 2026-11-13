"""Every trader-facing page on made-up files, for proving a refactor changed nothing on screen.

Walks the site the way a trader's browser would, following links from each scene, so a page
nobody listed is still read. The scenes are the states a page can be in: signed out, signed
up, consented, the demo file, the demo with a number set, and a small file with too few trades
to say much. All of it is synthetic.

Run through ``test_figures``. What differs from one run to the next and is no part of what a
page says, the form token and today's date, is put aside by ``steady``.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urldefrag, urlsplit

from fastapi.testclient import TestClient
from sqlalchemy import update

from services.production.api import limits
from services.production.db import models as m
from services.production.db.session import make_session

CLEAN = Path("data/fixtures/duplicates/clean.csv")
HREF = re.compile(r'href="([^"]+)"')
CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
TOKEN = re.compile(r'(name="csrf_token"\s+value=")[^"]+(")')
META_TOKEN = re.compile(r'(hx-headers=\'\{"X-CSRF-Token":\s*")[^"]+')
LEFT_OUT = ("/static", "/admin", "/logout", "/account/delete", "/health")
VERSION = "aaa1111"
PASSWORD = "a-long-enough-password"


def steady(html: str, days: tuple[datetime, ...]) -> str:
    """The page without what is different every run. Nothing a trader's figures depend on."""
    html = TOKEN.sub(r"\1TOKEN\2", html)
    html = META_TOKEN.sub(r"\1TOKEN", html)
    for day in days:
        for shape in ("%d %b %Y", "%Y-%m-%d", "%d %B %Y"):
            html = html.replace(day.strftime(shape), "TODAY")
        html = html.replace(f"{day.day} {day.strftime('%b %Y')}", "TODAY")
    return html


def _links(html: str) -> list[str]:
    found = []
    for href in HREF.findall(re.sub("[\ue000\ue001]", "", html)):  # test_figures' markers
        path = urldefrag(href.replace("&amp;", "&")).url
        parts = urlsplit(path)
        if parts.scheme or parts.netloc or not path.startswith("/"):
            continue
        if not path.startswith(LEFT_OUT):
            found.append(path)
    return found


def crawl(client: TestClient, start: tuple[str, ...]) -> dict[str, tuple[int, str]]:
    """Every page reachable from these by a link, with its status."""
    seen: dict[str, tuple[int, str]] = {}
    queue = list(start)
    while queue:
        path = queue.pop(0)
        if path in seen:
            continue
        response = client.get(path, follow_redirects=False)
        seen[path] = (response.status_code, response.text)
        if response.status_code in (301, 302, 303, 307):
            queue.append(response.headers["location"])
        elif response.status_code == 200:
            queue.extend(_links(response.text))
    return seen


def _token(client: TestClient, path: str) -> str:
    return CSRF.search(client.get(path).text).group(1)


def _sign_up(client: TestClient, engine, login_id: str) -> None:
    client.cookies.clear()
    client.post("/signup", data={"login_id": login_id, "display_name": login_id.title(),
                                 "password": PASSWORD, "csrf_token": _token(client, "/signup")},
                follow_redirects=False)
    with make_session(engine) as sess:
        sess.execute(update(m.Trader).where(m.Trader.login_id == login_id).values(
            development_data=False))
        sess.commit()


def _consent(client: TestClient) -> None:
    client.post("/consent", data={"csrf_token": _token(client, "/consent"), "diagnosis": "yes",
                                  "engine_testing": "yes"},
                follow_redirects=False)


def _upload(client: TestClient, path: Path) -> None:
    client.post("/upload", files={"file": (path.name, path.read_bytes(), "text/csv")},
                data={"csrf_token": _token(client, "/upload")}, follow_redirects=False)


def scenes(app, engine) -> dict[str, dict[str, tuple[int, str]]]:
    client = TestClient(app, raise_server_exceptions=True)
    pages = {"signed out": crawl(client, ("/", "/login", "/signup"))}

    _sign_up(client, engine, "fresh")
    pages["signed up"] = crawl(client, ("/", "/consent", "/upload", "/account", "/mirror"))

    _consent(client)
    pages["consented"] = crawl(client, ("/", "/upload", "/account", "/budget", "/mirror", "/journals"))

    _sign_up(client, engine, "visitor")
    _consent(client)
    client.post("/upload/demo", data={"csrf_token": _token(client, "/upload")},
                follow_redirects=False)
    pages["demo"] = crawl(client, ("/", "/mirror", "/mirror/reveal", "/account", "/budget",
                                   "/journals", "/eligibility"))

    client.post("/budget", data={"csrf_token": _token(client, "/budget"), "value": "2000",
                                 "unit": "INR", "effective_from": "2024-01-01"},
                follow_redirects=False)
    pages["demo with a number"] = crawl(client, ("/mirror", "/mirror/chapter/4", "/budget"))

    _sign_up(client, engine, "smallfile")
    _consent(client)
    _upload(client, CLEAN)
    pages["small file"] = crawl(client, ("/", "/mirror", "/mirror/reveal", "/account", "/budget",
                                         "/journals", "/eligibility"))
    return pages


def digests(app, engine) -> dict[str, str]:
    app.state.code_version = VERSION
    now = datetime.now(UTC)
    days = (now, now.astimezone(limits.INDIA), now + timedelta(days=1), now - timedelta(days=1))
    out = {}
    for scene, pages in scenes(app, engine).items():
        for path, (status, html) in sorted(pages.items()):
            body = hashlib.sha256(steady(html, days).encode()).hexdigest()
            out[f"{scene} {path}"] = f"{status} {body}"
    return out
