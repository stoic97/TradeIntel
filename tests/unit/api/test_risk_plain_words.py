"""Chapter 4 says why there is no risk figure, and shows the losses beside the question
[TICKET-824]. Same hand-worked losses as tests/unit/mirror/test_loss_sizes.py."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_scope_chapters import chapter_page, readable, trips_from
from tests.unit.api.test_scope_facts import fact_page
from tests.unit.api.test_upload import client, engine, upload  # noqa: F401

LOSSES = [-100 * i for i in range(1, 21)]
GUIDE = (
    "Half your losing trades lost ₹1,000 or less. Three in four ₹1,500 or less. "
    "Nine in ten ₹1,800 or less. One in twenty lost more than ₹1,900. Your biggest: ₹2,000."
)
LABEL = "Stocks, ETFs and futures: no premium to measure against"
OLD_LABEL = "Nothing we could use"
PAID = "On a typical option trade you paid ₹1,000, and made or lost about 4% of it."
MEANT = "What you meant to risk is where you'd have exited, and that isn't in your file."


def history(source):
    options = [
        replace(t, is_option=True, premium=Decimal(1000))
        for t in trips_from([30, -40, 50, -30, 40, -50] * 4, source)
    ]
    return options + trips_from(LOSSES, source)


def nothing():
    return history(s.RiskUnitSourceV1.UNAVAILABLE)


def premium():
    return history(s.RiskUnitSourceV1.PREMIUM_PAID)


def budget():
    return history(s.RiskUnitSourceV1.DECLARED_BUDGET)


def test_it_says_what_an_option_cost():
    assert PAID in readable(fact_page("risk", nothing()))


def test_it_says_what_is_not_in_the_file():
    assert MEANT in readable(fact_page("risk", nothing()))


def test_with_a_budget_it_does_not_say_the_number_is_missing():
    page = readable(fact_page("risk", budget()))
    assert PAID in page and MEANT not in page


def test_the_losses_show_beside_the_question():
    assert (
        "Half your losing trades lost" in readable(fact_page("risk", nothing()))
        and "Your biggest:" in readable(fact_page("risk", premium()))
    )


def test_too_few_losses_show_no_guide():
    assert "Half your losing trades" not in readable(fact_page("risk", trips_from([-5, 9])))


def test_the_guide_suggests_no_number():
    page = readable(fact_page("risk", nothing())).lower()
    assert "we suggest" not in page and "you should" not in page


def test_with_no_budget_it_offers_to_set_one():
    assert '<a class="link" href="/budget">Set your number</a>' in fact_page("risk", premium())


def test_with_a_budget_it_does_not():
    assert "Set your number" not in fact_page("risk", budget())


def test_it_goes_on_to_the_last_fact():
    assert 'href="/mirror/fact/not-told"' in fact_page("risk", nothing())
    assert 'href="/mirror/fact/not-told"' in fact_page("risk", budget())


def test_the_fact_page_uses_the_new_label():
    page = readable(fact_page("risk", premium()))
    assert LABEL in page and OLD_LABEL not in page


def test_the_card_uses_the_new_label():
    page = readable(chapter_page(4, premium()))
    assert LABEL in page and OLD_LABEL not in page


def test_the_trade_group_uses_the_new_label():
    assert OLD_LABEL not in readable(fact_page("risk", premium()))


def test_the_budget_page_shows_the_guide(client, engine, monkeypatch):  # noqa: F811
    """On a real upload. The fixture's file has a few losses, so the minimum comes down."""
    monkeypatch.setattr(mx, "LOSS_SIZES_MINIMUM", 1)
    upload(client, content=_with_a_loss())
    assert "Half your losing trades lost ₹100 or less." in " ".join(client.get("/budget").text.split())


def test_the_budget_page_says_nothing_with_too_few(client, engine):  # noqa: F811
    upload(client, content=_with_a_loss())
    assert "Half your losing trades" not in client.get("/budget").text


def test_the_budget_page_says_nothing_with_no_upload(client):  # noqa: F811
    assert "Half your losing trades" not in client.get("/budget").text


def test_an_old_refusal_reads_in_plain_words(client, engine):  # noqa: F811
    """Stored before sold options were counted. New uploads refuse none of them."""
    upload(client, content=_with_a_loss())
    with make_session(engine) as sess:
        imp = sess.scalars(select(m.Import)).first()
        sess.add(m.SkippedTrip(
            import_id=imp.id,
            reason="a short option position is outside ctr_v1: the R convention is not decided",
        ))
        sess.commit()
    page = client.get("/mirror/fact/unread").text
    assert "A sold option. Scope did not count these when this file was read." in page
    assert "ctr_v1" not in page and "R convention" not in page


def _with_a_loss() -> bytes:
    from tests.unit.api.test_upload import _two_days

    loss = (
        "2026-10-15,13:30:00,WIDGETOIL 19 NOV 5100 CALL,BUY,INTRADAY,MCX,"
        "Commodity,100,53.00,5300.00,Traded\n"
        "2026-10-15,14:30:00,WIDGETOIL 19 NOV 5100 CALL,SELL,INTRADAY,MCX,"
        "Commodity,100,52.00,5200.00,Traded\n"
    )
    return _two_days() + loss.encode()
