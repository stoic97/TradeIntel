"""A quantity that is not whole lots is a page, not a 500 [TICKET-1103].

The loader refuses a quantity no lot size divides (MisdeclaredQuantityUnit) and an
instrument with no profile (UnknownInstrument). The Mirror, the budget, the factors and
the reveal already turn that into the "record is not ready" page; the other routes let it
out as a bare 500. The file below is synthetic: one share-option the profile gives a lot
of 500 on that date, traded 10 units at a time, so the count is not whole lots.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.helpers.read_again import HEADER, send, words

@pytest.fixture()
def client(client):
    """The signed-in client, but a server error comes back as a 500, as a trader would get it."""
    quiet = TestClient(client.app, raise_server_exceptions=False)
    quiet.cookies.update(client.cookies)
    return quiet


NAME = "RELIANCE 26 FEB 2500 CALL"


def _row(day: str, time: str, side: str, value: int) -> str:
    return (f"{day},{time},{NAME},{side},INTRADAY,NSE,Derivative,10,{value / 10:.2f},"
            f"{value:.2f},Traded")


FILE = "\n".join([
    HEADER,
    _row("2026-02-02", "09:30:00", "BUY", 25000),
    _row("2026-02-02", "10:00:00", "SELL", 26000),
]).encode() + b"\n"

SECOND = "\n".join([
    HEADER,
    _row("2026-02-02", "09:30:00", "BUY", 25000),
    _row("2026-02-02", "10:00:00", "SELL", 26000),
    _row("2026-02-03", "09:30:00", "BUY", 25000),
    _row("2026-02-03", "10:00:00", "SELL", 26500),
]).encode() + b"\n"


def _named(response) -> None:
    assert response.status_code != 500
    assert "RELIANCE" in words(response.text)


def test_an_upload_of_a_misdeclared_quantity_is_not_a_500(client):
    response = send(client, FILE, "first.csv")
    assert response.status_code != 500
    followed = client.get(response.headers["location"]) if response.status_code in (302, 303) else response
    assert followed.status_code != 500


def test_an_upload_with_an_earlier_import_names_the_instrument(client):
    send(client, FILE, "first.csv")
    response = send(client, SECOND, "second.csv")
    assert response.status_code != 500
    page = client.get(response.headers["location"]) if response.status_code in (302, 303) else response
    _named(page)


def test_home_is_not_a_500(client):
    send(client, FILE, "first.csv")
    response = client.get("/", follow_redirects=True)
    assert response.status_code != 500


@pytest.mark.parametrize("path", ["/journals", "/eligibility", "/replay", "/rules"])
def test_the_other_pages_are_not_a_500(client, path):
    send(client, FILE, "first.csv")
    response = client.get(path, follow_redirects=True)
    assert response.status_code != 500, path
