"""TICKET-1004 review (24 Nov): no shared card outlives its own remove, and a stopped card holds still.

1. Share challenge A, start challenge B: A's ``/c/<token>`` must not stay live with no route that
   can clear it. Starting a new challenge takes the earlier link down, and "Remove the link"
   clears every link of his, so no earlier card is public with nothing on his page to remove it.
2. A challenge stopped on day N reads "Stopped on day N of 10" after later uploads too, on his
   page and on the shared card: it is counted as at the moment it stopped, never recounted.

Made-up rules and the demo's made-up file; the cut-off below plays the part of a later upload.
"""
from __future__ import annotations

import importlib
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from tests.helpers.upload import CSRF, sign_up


def routes():
    return importlib.import_module("services.production.api.routes_challenge")


def signed_in(engine):
    client = sign_up(TestClient(create_app()), engine, "C-2", "holder")
    client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
    return client


def token(client, path="/challenge"):
    found = CSRF.search(client.get(path).text)
    assert found, f"no form on {path}"
    return found.group(1)


def set_rule(client):
    client.post("/rules/set", data={"factor": "most_trades", "value": "2",
                                    "csrf_token": token(client, "/rules/set?factor=most_trades")})


def start(client, engine):
    with make_session(engine) as sess:
        ids = list(sess.scalars(select(m.RuleDeclaration.id)))
    return client.post("/challenge/start", data={"length": "10", "rule": [str(i) for i in ids],
                                                 "csrf_token": token(client)}, follow_redirects=False)


def stop(client):
    client.post("/challenge/stop", data={"csrf_token": token(client)})


def share(client):
    client.post("/challenge/share", data={"csrf_token": token(client)})


def links(engine) -> list[str]:
    with make_session(engine) as sess:
        return [t for t in sess.scalars(select(m.Challenge.share_token).order_by(m.Challenge.id)) if t]


def public(link: str) -> int:
    return TestClient(create_app()).get(f"/c/{link}").status_code


# ---------- 1. an earlier card's link ----------

def test_starting_a_second_challenge_takes_the_first_ones_link_down(engine):
    client = signed_in(engine)
    set_rule(client)
    start(client, engine)
    stop(client)
    share(client)
    (first,) = links(engine)
    assert public(first) == 200
    assert start(client, engine).status_code == 303  # challenge B
    assert public(first) == 404
    assert links(engine) == []


def test_remove_the_link_clears_every_link_of_his(engine):
    client = signed_in(engine)
    set_rule(client)
    start(client, engine)
    stop(client)
    share(client)
    (first,) = links(engine)
    # An earlier card's link left over from before this fix: B is started with A's link still set.
    with make_session(engine) as sess:
        sess.add(m.Challenge(trader_id=sess.scalars(select(m.Trader.id)).one(), rule_ids="[]", length=10,
                             start_day="2027-01-04", started_at=sess.scalars(select(m.Challenge.started_at)).first(),
                             ended_at=sess.scalars(select(m.Challenge.ended_at)).first(), ended_how="stopped"))
        sess.commit()
    share(client)  # B's own link
    assert len(links(engine)) == 2
    client.post("/challenge/unshare", data={"csrf_token": token(client)})
    assert links(engine) == [] and public(first) == 404


def test_the_page_says_a_new_challenge_takes_the_link_down(engine):
    client = signed_in(engine)
    set_rule(client)
    start(client, engine)
    stop(client)
    share(client)
    assert "Starting a new challenge takes this link down." in client.get("/challenge").text


# ---------- 2. a stopped card holds still ----------

def test_a_stopped_card_reads_the_same_after_a_later_upload(engine, monkeypatch):
    client = signed_in(engine)
    set_rule(client)
    start(client, engine)
    r = routes()
    full = r.loader.load_for
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        days = sorted({t.trading_day for t in full(sess, trader)[0]})
        row = sess.scalars(select(m.Challenge)).one()
        row.start_day = days[0]  # the challenge's days are days his file holds
        sess.commit()
    # His file "as it was" when he stopped: only the first few trading days of it.
    cut = {"day": days[3]}

    def as_uploaded(sess, trader, imp=None):
        trips, got = full(sess, trader, imp)
        return [t for t in trips if cut["day"] is None or t.trading_day <= cut["day"]], got

    monkeypatch.setattr(r.loader, "load_for", as_uploaded)
    stop(client)
    share(client)
    before = client.get("/challenge").text
    said = before[before.index("Stopped on day"):].split("</p>")[0]
    assert not said.startswith("Stopped on day 10 of 10")
    (link,) = links(engine)
    shared_before = TestClient(create_app()).get(f"/c/{link}").text

    cut["day"] = None  # a later upload covers every day of the challenge
    after = client.get("/challenge").text
    assert said in after
    assert "Stopped on day 10 of 10" not in after
    shared_after = TestClient(create_app()).get(f"/c/{link}").text
    assert said in shared_before and said in shared_after
    assert date.fromisoformat(days[0])  # the made-up file's days are real dates
