"""TICKET-858: a trader reads a date one way, and a day's total one way, on the made-up demo."""

from __future__ import annotations

import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from services.production.api.app import create_app

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
MONTHS = "January|February|March|April|June|July|August|September|October|November|December"
OTHER_FORMATS = (r"\b\d{4}-\d{2}-\d{2}\b", rf"\b\d{{1,2}} (?:{MONTHS})\b", r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")


def token(client, path: str) -> str:
    return CSRF.search(client.get(path).text).group(1)


def text(html: str) -> str:
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.DOTALL)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).replace("\xa0", " ").split())


@pytest.fixture()
def client():
    client = TestClient(create_app(), follow_redirects=False)
    client.post("/signup", data={"login_id": "visitor", "display_name": "Visitor",
                                 "password": "a-long-enough-password",
                                 "csrf_token": token(client, "/signup")})
    client.post("/consent", data={"diagnosis": "yes", "engine_testing": "yes",
                                  "csrf_token": token(client, "/consent")})
    client.post("/upload/demo", data={"csrf_token": token(client, "/upload")})
    client.post("/budget", data={"csrf_token": token(client, "/budget"), "value": "2000",
                                 "unit": "INR", "effective_from": "2024-01-01"})
    return client


def journal_links(client) -> list[str]:
    return re.findall(r'href="(/journals/\d+)"', client.get("/journals").text)


def test_no_page_writes_a_date_a_second_way(client):
    paths = ["/", "/mirror", "/journals", "/journals/catch-up", "/budget", "/account", "/imports/1",
             "/mirror/fact/worst-days", "/mirror/fact/not-told", *journal_links(client)]
    assert len(paths) > 9
    for path in paths:
        page = text(client.get(path).text)
        for pattern in OTHER_FORMATS:
            assert not re.search(pattern, page), (path, re.search(pattern, page))


def test_a_days_total_is_the_same_on_home_and_its_journal(client):
    home = client.get("/").text
    rows = re.findall(r'href="(/journals/\d+)".*?</a>', home, flags=re.DOTALL)
    assert rows
    for match in re.finditer(r'<a [^>]*href="(/journals/\d+)"[^>]*>.*?</a>', home, flags=re.DOTALL):
        figures = re.findall(r"[−+]₹[\d,]+", text(match.group(0)))
        if figures:
            assert f"Net {figures[-1]}." in text(client.get(match.group(1)).text), match.group(1)
