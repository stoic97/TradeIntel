"""TICKET-1001 gate 11: After you clicked makes no claim, on every page that shows it.

The fact page (drawn, and under 30), its trade list and chapter 2's card are read as rendered:
none says "skill", "edge", "luck" or "beat", and none trips the report-wide never-used words or
claim patterns. Every figure is made up.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from services.production.api import after_clicked as AC
from services.production.db import models as m
from services.production.db.session import make_session
from tests.helpers.no_claims import CLAIM_PATTERNS, NEVER_USED

H = AC.HORIZON
GATE_WORDS = ("skill", "edge", "luck", "beat")


def _flat(n: int) -> tuple[Decimal, ...]:
    return (Decimal(0),) + (Decimal(n),) * H


def _store(engine, measured: int, reasons: list[str]):
    trips = json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text(encoding="utf-8"))
    with make_session(engine) as sess:
        imp = sess.scalars(select(m.Import)).first()
        for i, t in enumerate(trips):
            if i < measured:
                path = json.dumps([str(v) for v in _flat(1 + i % 9)])
                sess.add(m.BarTradeFigure(import_id=imp.id, trip_id=t["trip_id"], underlying="WIDGETOIL",
                                          reason=None, way="3", against="1", took="2", path=path, short=False))
            elif i - measured < len(reasons):
                sess.add(m.BarTradeFigure(import_id=imp.id, trip_id=t["trip_id"], underlying="WIDGETOIL",
                                          reason=reasons[i - measured], short=False))
        zeros = json.dumps(["0"] * (H + 1))
        sess.add(m.BarPathSummary(import_id=imp.id, underlying="WIDGETOIL", measured=measured, randoms=measured,
                                  his_median=zeros, his_q25=zeros, his_q75=zeros, random_median=zeros,
                                  random_lo=json.dumps(["-4"] * (H + 1)), random_hi=json.dumps(["4"] * (H + 1)),
                                  faint="[]"))
        sess.commit()


def _words(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).lower()


def _no_claims(html: str) -> None:
    words = _words(html)
    for claim in GATE_WORDS:
        assert not re.search(rf"\b{claim}", words), claim
    for word in NEVER_USED:
        assert not re.search(rf"\b{re.escape(word)}\b", words), word
    for pattern, why in CLAIM_PATTERNS:
        assert not re.search(pattern, words), why


@pytest.mark.parametrize("measured", [34, 12])
def test_the_fact_page_makes_no_claim_drawn_or_under_30(client, engine, measured):
    _store(engine, measured, ["no market data"] * 3)
    page = client.get("/mirror/fact/after")
    assert page.status_code == 200
    section = page.text[page.text.index('id="after"'):]
    _no_claims(section[: section.index("</section>")])


def test_its_trade_list_and_chapter_card_make_no_claim(client, engine):
    _store(engine, 34, [])
    trades = client.get("/mirror/fact/after/trades")
    assert trades.status_code == 200
    _no_claims(trades.text[trades.text.index("<main"):])
    chapter = client.get("/mirror/chapter/2").text
    assert "After you clicked" in chapter
    _no_claims(chapter[chapter.index("<main"):])
